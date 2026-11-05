from __future__ import annotations

import re
from dataclasses import replace
from typing import Any

from recreation_extractor.conventions import PROJECT_CODE_PATTERN
from recreation_extractor.hierarchy.dependency_graph import (
    DependencyEdgeKind,
    DependencyGraph,
    DependencyGraphEdge,
    DependencyGraphNode,
    DependencyStatus,
    dependency_edge_id,
    dependency_metrics,
    dependency_node_id,
)
from recreation_extractor.pid_stitch.electrical_graph import is_user_facing_equipment_tag
from recreation_extractor.pid_stitch.models import BoundsDict


DEPENDENCY_RULESET = "dependency_rules_v1"
VFD_RULE_ID = "dependency.vfd.v1"

RATING_OR_ANNOTATION_RE = re.compile(
    r"^(?:"
    r"\d+(?:\.\d+)?\s*(?:KV|V|OHM|Ω)(?:[-/]\d+(?:\.\d+)?\s*(?:KV|V|OHM|Ω)?)*"
    r"|\d+(?:\.\d+)?[A-Z]?(?:AF|AT|A|KVA|KW|PF|N)?"
    r"|(?:AA|FA)\s+\d{3,5}KVA"
    r"|M\d+"
    r"|(?:27|32|46|47|49|50|51|52|59|81|86|87)(?:/[0-9]{2})?[A-Z]{0,2}(?:-[A-Z0-9]+)?"
    r")$",
    re.IGNORECASE,
)
DRAWING_REF_RE = re.compile(r"^(?:" + PROJECT_CODE_PATTERN + r"|[A-Z]{1,3})-[A-Z]{1,4}-\d{3,}[A-Z0-9-]*$", re.IGNORECASE)
MECHANICAL_ASSET_RE = re.compile(
    r"^(?:"
    r"R-[A-Z0-9]+(?:-[A-Z0-9]+)+(?:\s+\([A-Z0-9 ]+\))?"
    r"|(?:P|FAN|EF|SF|RF|AHU|MAU|FCU|VAV|HX|CH|CHW|CW|HHW)-[A-Z0-9][A-Z0-9-]*"
    r")$",
    re.IGNORECASE,
)
MOTOR_TAG_RE = re.compile(r"^(?:MTR-[A-Z0-9][A-Z0-9-]*|[A-Z0-9][A-Z0-9-]*-MTR(?:-[A-Z0-9]+)?|R-[A-Z0-9]+(?:-[A-Z0-9]+)*-MTR)$", re.IGNORECASE)
CONTROL_PANEL_RE = re.compile(r"^(?:BAS|PLC|DDC|CP|LCP|MCP|CPNL|CONTROL)-?[A-Z0-9][A-Z0-9-]*$|^[A-Z0-9-]+-CP-\d+[A-Z0-9-]*$", re.IGNORECASE)
INSTRUMENT_ASSET_RE = re.compile(r"^(?:PDIT|PDT|PIT|FIT|TIT|LIT|AIT|PT|FT|TT|LT|PI|FI|TI|FE|TE|AT)[ -]?\d+[A-Z0-9-]*$", re.IGNORECASE)
GENERATOR_OR_BACKUP_RE = re.compile(r"^(?:GEN|ATS|UPS)-?[A-Z0-9][A-Z0-9-]*$", re.IGNORECASE)
TRANSFORMER_RE = re.compile(r"^(?:XFMR|TR|TX)-?[A-Z0-9][A-Z0-9-]*$", re.IGNORECASE)

PARENT_EDGE_KINDS = {
    "attached_to_line",
    "device_on_equipment",
    "equipment_on_section",
    "feeds_panel",
    "panel_schedule_feeds",
    "panel_circuit",
    "power_source",
}
STATUS_RANK: dict[str, int] = {"needs_review": 0, "inferred": 1, "confirmed": 2}


def build_dependency_graph(project_id: str, semantic_graph: Any, electrical_graph: Any) -> DependencyGraph:
    raw_nodes = [*_graph_nodes(electrical_graph), *_graph_nodes(semantic_graph)]
    dependency_nodes_by_tag: dict[str, DependencyGraphNode] = {}
    raw_to_dependency_tag: dict[str, str] = {}

    for raw_node in raw_nodes:
        tag = _node_tag(raw_node)
        kind = _node_kind(raw_node)
        metadata = _node_metadata(raw_node)
        if not is_dependency_equipment_tag(tag, kind, metadata):
            continue
        canonical_tag = normalize_dependency_tag(tag)
        dependency_node = _dependency_node(raw_node, canonical_tag)
        existing = dependency_nodes_by_tag.get(canonical_tag)
        dependency_nodes_by_tag[canonical_tag] = _merge_dependency_nodes(existing, dependency_node) if existing else dependency_node
        raw_to_dependency_tag[_node_id(raw_node)] = canonical_tag

    edges_by_key: dict[tuple[str, str, str], DependencyGraphEdge] = {}
    review_items: list[dict[str, Any]] = []
    electrical_nodes_by_id = {_node_id(node): node for node in _graph_nodes(electrical_graph)}
    electrical_parent_edges = _electrical_parent_edges(electrical_graph)
    vfd_nodes = [node for node in _graph_nodes(electrical_graph) if _is_vfd_tag(_node_tag(node)) and _node_id(node) in raw_to_dependency_tag]

    for vfd_node in vfd_nodes:
        vfd_tag = raw_to_dependency_tag[_node_id(vfd_node)]
        vfd = dependency_nodes_by_tag[vfd_tag]
        matched = _vfd_matched_nodes(vfd, dependency_nodes_by_tag)
        commissioning_targets = matched["driven"] or [vfd]

        for target in commissioning_targets:
            if target.id != vfd.id:
                _add_edge(
                    edges_by_key,
                    vfd,
                    target,
                    "requires_drive",
                    status="inferred",
                    confidence=min(0.86, max(vfd.confidence, target.confidence)),
                    rule_id=VFD_RULE_ID,
                    evidence_ids=[*vfd.sourceEvidenceIds, *target.sourceEvidenceIds],
                    metadata=_dependency_metadata(
                        vfd,
                        target,
                        "requires_drive",
                        dependency_path=[target.tag, vfd.tag],
                        match="shared_equipment_root",
                    ),
                )
            _add_upstream_power_dependencies(
                target,
                vfd_node,
                dependency_nodes_by_tag,
                raw_to_dependency_tag,
                electrical_nodes_by_id,
                electrical_parent_edges,
                edges_by_key,
            )
            _add_vfd_component_dependencies(target, vfd, matched, edges_by_key)

        if not matched["driven"]:
            review_items.append(_review_item(vfd, "missing_vfd_driven_equipment", f"Expected driven equipment not found for {vfd.tag}"))
        if not matched["control"] and not matched["instrument"]:
            review_items.append(_review_item(vfd, "missing_vfd_control_source", f"Expected control source not found for {vfd.tag}"))

    nodes = sorted(_nodes_referenced_by_edges(dependency_nodes_by_tag, edges_by_key), key=lambda node: (_node_sort_rank(node), node.tag))
    edges = sorted(edges_by_key.values(), key=lambda edge: (edge.targetTag, _edge_sort_rank(edge), edge.sourceTag))
    qa = {"reviewItems": review_items, "warnings": [item["message"] for item in review_items]}
    return DependencyGraph(projectId=project_id, nodes=nodes, edges=edges, metrics=dependency_metrics(nodes, edges), qa=qa)


def is_dependency_equipment_tag(tag: str, kind: str, metadata: dict[str, Any] | None = None) -> bool:
    metadata = metadata or {}
    upper = normalize_dependency_tag(tag)
    if not upper:
        return False
    if "BUS" in upper:
        return False
    if upper in {"POWER", "CONTROL", "FEEDBACK", "PERMISSIVE", "INTERLOCK", "NOTE", "NOTES"}:
        return False
    if upper.startswith("ROOM ") or upper.startswith("RM "):
        return False
    if RATING_OR_ANNOTATION_RE.fullmatch(upper) or DRAWING_REF_RE.fullmatch(upper):
        return False
    if is_user_facing_equipment_tag(upper):
        return True
    if MOTOR_TAG_RE.fullmatch(upper):
        return True
    if CONTROL_PANEL_RE.fullmatch(upper):
        return True
    equipment_class = str(metadata.get("equipmentClass") or metadata.get("assetClass") or "").lower()
    if equipment_class in {"control_panel", "plc", "bas_panel", "motor", "pump", "fan", "ahu", "mau"}:
        return True
    if MECHANICAL_ASSET_RE.fullmatch(upper):
        return True
    if kind == "instrument" and (bool(metadata.get("asset")) or bool(metadata.get("requiredForOperation")) or INSTRUMENT_ASSET_RE.fullmatch(upper)):
        return True
    return False


def normalize_dependency_tag(tag: str) -> str:
    return re.sub(r"\s+", " ", str(tag or "").strip().upper())


def _add_upstream_power_dependencies(
    target: DependencyGraphNode,
    vfd_node: Any,
    dependency_nodes_by_tag: dict[str, DependencyGraphNode],
    raw_to_dependency_tag: dict[str, str],
    electrical_nodes_by_id: dict[str, Any],
    electrical_parent_edges: dict[str, list[Any]],
    edges_by_key: dict[tuple[str, str, str], DependencyGraphEdge],
) -> None:
    queue: list[tuple[str, int, list[str]]] = [(_node_id(vfd_node), 0, [target.tag, normalize_dependency_tag(_node_tag(vfd_node))])]
    visited: set[str] = set()
    while queue:
        child_id, depth, dependency_path = queue.pop(0)
        if child_id in visited:
            continue
        visited.add(child_id)
        for source_edge in electrical_parent_edges.get(child_id, []):
            parent_id = _edge_target_id(source_edge)
            parent_node = electrical_nodes_by_id.get(parent_id)
            if parent_node is None:
                continue
            parent_dependency_tag = raw_to_dependency_tag.get(parent_id)
            if parent_dependency_tag:
                source = dependency_nodes_by_tag[parent_dependency_tag]
                kind = _power_dependency_kind(source, depth)
                next_dependency_path = [*dependency_path, source.tag]
                _add_edge(
                    edges_by_key,
                    source,
                    target,
                    kind,
                    status=_edge_status(source_edge),
                    confidence=_edge_confidence(source_edge),
                    rule_id=VFD_RULE_ID,
                    evidence_ids=[*_edge_evidence(source_edge)],
                    metadata=_dependency_metadata(
                        source,
                        target,
                        kind,
                        dependency_path=next_dependency_path,
                        source_graph_edge_id=_edge_id(source_edge),
                    ),
                )
            queue.append((parent_id, depth + 1, [*dependency_path, normalize_dependency_tag(_node_tag(parent_node))]))


def _vfd_matched_nodes(
    vfd: DependencyGraphNode,
    dependency_nodes_by_tag: dict[str, DependencyGraphNode],
) -> dict[str, list[DependencyGraphNode]]:
    root = _vfd_equipment_root(vfd.tag)
    matched: dict[str, list[DependencyGraphNode]] = {"driven": [], "motor": [], "control": [], "instrument": []}
    for candidate in dependency_nodes_by_tag.values():
        if candidate.id == vfd.id:
            continue
        candidate_root = _equipment_root(candidate.tag)
        if _is_motor_tag(candidate.tag) and _roots_match(root, candidate_root):
            matched["motor"].append(candidate)
            continue
        if _is_driven_equipment_tag(candidate.tag) and _roots_match(root, candidate_root):
            matched["driven"].append(candidate)
            continue
        if _is_control_panel_tag(candidate.tag, candidate.metadata):
            matched["control"].append(candidate)
            continue
        if _is_instrument_dependency(candidate):
            matched["instrument"].append(candidate)
    return matched


def _add_vfd_component_dependencies(
    target: DependencyGraphNode,
    vfd: DependencyGraphNode,
    matched: dict[str, list[DependencyGraphNode]],
    edges_by_key: dict[tuple[str, str, str], DependencyGraphEdge],
) -> None:
    for motor in matched["motor"]:
        _add_edge(
            edges_by_key,
            motor,
            target,
            "requires_motor",
            status="inferred",
            confidence=0.78,
            rule_id=VFD_RULE_ID,
            evidence_ids=[*motor.sourceEvidenceIds, *target.sourceEvidenceIds, *vfd.sourceEvidenceIds],
            metadata=_dependency_metadata(motor, target, "requires_motor", dependency_path=[target.tag, motor.tag], match="shared_equipment_root"),
        )
    for control in matched["control"]:
        _add_edge(
            edges_by_key,
            control,
            target,
            "requires_control_panel",
            status="needs_review",
            confidence=0.68,
            rule_id=VFD_RULE_ID,
            evidence_ids=[*control.sourceEvidenceIds, *target.sourceEvidenceIds, *vfd.sourceEvidenceIds],
            metadata=_dependency_metadata(control, target, "requires_control_panel", dependency_path=[target.tag, control.tag], match="control_panel_candidate"),
        )
    for instrument in matched["instrument"]:
        if not _instrument_matches_target(instrument, target):
            continue
        _add_edge(
            edges_by_key,
            instrument,
            target,
            "requires_instrument",
            status="needs_review",
            confidence=0.64,
            rule_id=VFD_RULE_ID,
            evidence_ids=[*instrument.sourceEvidenceIds, *target.sourceEvidenceIds, *vfd.sourceEvidenceIds],
            metadata=_dependency_metadata(instrument, target, "requires_instrument", dependency_path=[target.tag, instrument.tag], match="instrument_required_for_operation"),
        )


def _dependency_metadata(
    source: DependencyGraphNode,
    target: DependencyGraphNode,
    kind: DependencyEdgeKind,
    *,
    dependency_path: list[str],
    match: str = "",
    source_graph_edge_id: str = "",
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "sourceDiscipline": source.discipline,
        "targetDiscipline": target.discipline,
        "sourcePage": source.page,
        "sourcePath": source.metadata.get("sourcePath"),
        "dependencyPath": " <- ".join(_unique([tag for tag in dependency_path if tag])),
        "commissioningUse": _commissioning_use(kind, source, target),
    }
    if match:
        metadata["match"] = match
    if source_graph_edge_id:
        metadata["sourceGraphEdgeId"] = source_graph_edge_id
    return metadata


def _commissioning_use(kind: DependencyEdgeKind, source: DependencyGraphNode, target: DependencyGraphNode) -> str:
    if kind == "requires_drive":
        return f"{target.tag} cannot complete functional performance testing until drive/speed control {source.tag} is installed, powered, and ready."
    if kind == "requires_power":
        return f"Local electrical source {source.tag} must be energized and available before {target.tag} run testing."
    if kind == "requires_upstream_distribution":
        return f"Upstream distribution {source.tag} must be accepted so downstream power is reliable for {target.tag} testing."
    if kind == "requires_motor":
        return f"Motor {source.tag} must be checked as part of the pump start/run chain for {target.tag}."
    if kind == "requires_control_panel":
        return f"Controls/BAS source {source.tag} must be ready for start-stop, permissive, alarm, and status checks for {target.tag}."
    if kind == "requires_instrument":
        return f"I&C point {source.tag} should be verified because it supplies proof, feedback, or protection used during {target.tag} testing."
    return f"{source.tag} is a prerequisite dependency for commissioning {target.tag}."


def _add_edge(
    edges_by_key: dict[tuple[str, str, str], DependencyGraphEdge],
    source: DependencyGraphNode,
    target: DependencyGraphNode,
    kind: DependencyEdgeKind,
    *,
    status: DependencyStatus,
    confidence: float,
    rule_id: str,
    evidence_ids: list[str],
    metadata: dict[str, Any],
) -> None:
    if source.id == target.id:
        return
    key = (source.tag, target.tag, kind)
    existing = edges_by_key.get(key)
    evidence = _unique([*(existing.sourceEvidenceIds if existing else []), *evidence_ids])
    if existing:
        edges_by_key[key] = replace(
            existing,
            status=_best_status(existing.status, status),
            confidence=max(existing.confidence, confidence),
            sourceEvidenceIds=evidence,
            metadata={**metadata, **existing.metadata},
        )
        return
    edges_by_key[key] = DependencyGraphEdge(
        id=dependency_edge_id(kind, source.tag, target.tag),
        sourceId=source.id,
        targetId=target.id,
        sourceTag=source.tag,
        targetTag=target.tag,
        kind=kind,
        label=kind,
        status=status,
        confidence=confidence,
        ruleId=rule_id,
        sourceEvidenceIds=evidence,
        metadata=metadata,
    )


def _dependency_node(raw_node: Any, tag: str) -> DependencyGraphNode:
    metadata = dict(_node_metadata(raw_node))
    discipline = str(metadata.get("discipline") or _discipline_for_node(raw_node))
    return DependencyGraphNode(
        id=dependency_node_id(tag),
        tag=tag,
        kind=_dependency_kind(raw_node),
        discipline=discipline,
        description=str(metadata.get("equipmentDescription") or metadata.get("iandcDescription") or metadata.get("description") or ""),
        sourceFileId=_node_source_file_id(raw_node),
        sourcePageId=_node_source_page_id(raw_node),
        page=_node_page(raw_node),
        bounds=_node_bounds(raw_node),
        sourceEvidenceIds=_node_evidence(raw_node),
        confidence=_node_confidence(raw_node),
        metadata={**metadata, "sourceNodeIds": [_node_id(raw_node)], "ruleset": DEPENDENCY_RULESET},
    )


def _merge_dependency_nodes(existing: DependencyGraphNode | None, incoming: DependencyGraphNode) -> DependencyGraphNode:
    if existing is None:
        return incoming
    keep = existing if _node_preference(existing) <= _node_preference(incoming) else incoming
    other = incoming if keep is existing else existing
    metadata = {
        **other.metadata,
        **keep.metadata,
        "sourceNodeIds": _unique([*list(map(str, other.metadata.get("sourceNodeIds", []))), *list(map(str, keep.metadata.get("sourceNodeIds", [])))]),
    }
    return replace(
        keep,
        description=keep.description or other.description,
        sourceEvidenceIds=_unique([*keep.sourceEvidenceIds, *other.sourceEvidenceIds]),
        confidence=max(keep.confidence, other.confidence),
        metadata=metadata,
    )


def _nodes_referenced_by_edges(
    dependency_nodes_by_tag: dict[str, DependencyGraphNode],
    edges_by_key: dict[tuple[str, str, str], DependencyGraphEdge],
) -> list[DependencyGraphNode]:
    referenced = {edge.sourceId for edge in edges_by_key.values()} | {edge.targetId for edge in edges_by_key.values()}
    return [node for node in dependency_nodes_by_tag.values() if node.id in referenced]


def _electrical_parent_edges(electrical_graph: Any) -> dict[str, list[Any]]:
    parent_edges: dict[str, list[Any]] = {}
    for edge in _graph_edges(electrical_graph):
        if _edge_kind(edge) not in PARENT_EDGE_KINDS:
            continue
        source_id = _edge_source_id(edge)
        target_id = _edge_target_id(edge)
        if not source_id or not target_id:
            continue
        parent_edges.setdefault(source_id, []).append(edge)
    return parent_edges


def _power_dependency_kind(source: DependencyGraphNode, depth: int) -> DependencyEdgeKind:
    upper = source.tag.upper()
    equipment_class = str(source.metadata.get("equipmentClass") or "").lower()
    if GENERATOR_OR_BACKUP_RE.fullmatch(upper) or equipment_class in {"generator", "ats", "ups"}:
        return "requires_backup_power"
    if TRANSFORMER_RE.fullmatch(upper) or equipment_class == "transformer":
        return "requires_transformer"
    return "requires_power" if depth == 0 else "requires_upstream_distribution"


def _vfd_equipment_root(tag: str) -> str:
    upper = normalize_dependency_tag(tag)
    if upper.startswith("VFD-"):
        upper = upper[4:]
    elif upper.startswith("VFD"):
        upper = upper[3:].lstrip("-")
    return _equipment_root(upper)


def _equipment_root(tag: str) -> str:
    upper = normalize_dependency_tag(tag)
    upper = re.sub(r"-(?:MTR|MOTOR)(?:-[A-Z0-9]+)?$", "", upper)
    return upper


def _roots_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return left == right or left in right or right in left


def _is_vfd_tag(tag: str) -> bool:
    return normalize_dependency_tag(tag).startswith("VFD")


def _is_motor_tag(tag: str) -> bool:
    return bool(MOTOR_TAG_RE.fullmatch(normalize_dependency_tag(tag)))


def _is_control_panel_tag(tag: str, metadata: dict[str, Any] | None = None) -> bool:
    metadata = metadata or {}
    equipment_class = str(metadata.get("equipmentClass") or metadata.get("assetClass") or "").lower()
    return equipment_class in {"control_panel", "plc", "bas_panel"} or bool(CONTROL_PANEL_RE.fullmatch(normalize_dependency_tag(tag)))


def _is_driven_equipment_tag(tag: str) -> bool:
    upper = normalize_dependency_tag(tag)
    if _is_motor_tag(upper) or _is_control_panel_tag(upper):
        return False
    return bool(MECHANICAL_ASSET_RE.fullmatch(upper))


def _is_instrument_dependency(node: DependencyGraphNode) -> bool:
    if node.kind != "instrument":
        return False
    metadata = node.metadata
    return bool(metadata.get("requiredForOperation")) or bool(metadata.get("controlledEquipmentTag")) or bool(INSTRUMENT_ASSET_RE.fullmatch(node.tag))


def _instrument_matches_target(instrument: DependencyGraphNode, target: DependencyGraphNode) -> bool:
    metadata = instrument.metadata
    direct_target = normalize_dependency_tag(
        str(metadata.get("controlledEquipmentTag") or metadata.get("equipmentTag") or metadata.get("targetEquipmentTag") or "")
    )
    if direct_target and direct_target == target.tag:
        return True
    target_root = _equipment_root(target.tag)
    instrument_tag = normalize_dependency_tag(instrument.tag)
    return bool(target_root and (target_root in instrument_tag or instrument_tag in target_root))


def _review_item(target: DependencyGraphNode, review_type: str, message: str) -> dict[str, Any]:
    return {
        "id": f"depqa_{review_type}_{target.id}",
        "type": review_type,
        "targetTag": target.tag,
        "status": "open",
        "message": message,
        "sourceEvidenceIds": list(target.sourceEvidenceIds),
    }


def _dependency_kind(raw_node: Any) -> str:
    tag = _node_tag(raw_node)
    metadata = _node_metadata(raw_node)
    if _is_vfd_tag(tag):
        return "vfd"
    if _is_motor_tag(tag):
        return "motor"
    if _is_control_panel_tag(tag, metadata):
        return "control_panel"
    equipment_class = str(metadata.get("equipmentClass") or "").lower()
    if equipment_class:
        return equipment_class
    return _node_kind(raw_node)


def _discipline_for_node(raw_node: Any) -> str:
    system = _node_system(raw_node).upper()
    tag = _node_tag(raw_node).upper()
    if _node_kind(raw_node) == "instrument":
        return "Instrumentation & Control"
    if "BAS" in system or _is_control_panel_tag(tag, _node_metadata(raw_node)):
        return "Controls / BAS"
    if _is_motor_tag(tag) or _is_driven_equipment_tag(tag):
        return "Mechanical"
    if system == "ELEC" or _is_vfd_tag(tag) or is_user_facing_equipment_tag(tag):
        return "Electrical"
    return "Mechanical"


def _edge_sort_rank(edge: DependencyGraphEdge) -> int:
    order = {
        "requires_drive": 10,
        "requires_power": 20,
        "requires_upstream_distribution": 30,
        "requires_transformer": 40,
        "requires_backup_power": 50,
        "requires_driven_equipment": 60,
        "requires_motor": 70,
        "requires_control_panel": 80,
        "requires_instrument": 90,
    }
    return order.get(edge.kind, 99)


def _node_sort_rank(node: DependencyGraphNode) -> int:
    if _is_driven_equipment_tag(node.tag):
        return 0
    if node.kind == "vfd":
        return 1
    if node.discipline == "Electrical":
        return 2
    if node.kind == "motor":
        return 3
    if node.kind == "control_panel":
        return 4
    if node.kind == "instrument":
        return 5
    return 6


def _node_preference(node: DependencyGraphNode) -> int:
    if node.discipline == "Electrical":
        return 0
    if node.bounds:
        return 1
    return 2


def _best_status(left: DependencyStatus, right: DependencyStatus) -> DependencyStatus:
    return left if STATUS_RANK[left] >= STATUS_RANK[right] else right


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _graph_nodes(graph: Any) -> list[Any]:
    return list(getattr(graph, "nodes", []) or [])


def _graph_edges(graph: Any) -> list[Any]:
    return list(getattr(graph, "edges", []) or [])


def _node_id(node: Any) -> str:
    return str(getattr(node, "id", ""))


def _node_kind(node: Any) -> str:
    return str(getattr(node, "kind", ""))


def _node_tag(node: Any) -> str:
    return str(getattr(node, "tag", ""))


def _node_system(node: Any) -> str:
    return str(getattr(node, "system", ""))


def _node_source_file_id(node: Any) -> str:
    return str(getattr(node, "sourceFileId", ""))


def _node_source_page_id(node: Any) -> str:
    return str(getattr(node, "sourcePageId", ""))


def _node_page(node: Any) -> int | None:
    value = getattr(node, "page", None)
    return value if isinstance(value, int) else None


def _node_bounds(node: Any) -> BoundsDict | None:
    value = getattr(node, "bounds", None)
    return dict(value) if isinstance(value, dict) else None  # type: ignore[return-value]


def _node_evidence(node: Any) -> list[str]:
    return [str(item) for item in (getattr(node, "sourceEvidenceIds", []) or []) if item]


def _node_confidence(node: Any) -> float:
    value = getattr(node, "confidence", 0.0)
    return float(value) if isinstance(value, int | float) else 0.0


def _node_metadata(node: Any) -> dict[str, Any]:
    value = getattr(node, "metadata", {})
    return dict(value) if isinstance(value, dict) else {}


def _edge_id(edge: Any) -> str:
    return str(getattr(edge, "id", ""))


def _edge_kind(edge: Any) -> str:
    return str(getattr(edge, "kind", ""))


def _edge_source_id(edge: Any) -> str:
    return str(getattr(edge, "sourceId", ""))


def _edge_target_id(edge: Any) -> str:
    return str(getattr(edge, "targetId", ""))


def _edge_status(edge: Any) -> DependencyStatus:
    value = str(getattr(edge, "status", "inferred") or "inferred")
    return value if value in STATUS_RANK else "inferred"  # type: ignore[return-value]


def _edge_confidence(edge: Any) -> float:
    value = getattr(edge, "confidence", 0.0)
    return float(value) if isinstance(value, int | float) else 0.0


def _edge_evidence(edge: Any) -> list[str]:
    return [str(item) for item in (getattr(edge, "sourceEvidenceIds", []) or []) if item]
