from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Literal

from recreation_extractor.conventions import BUILDING_CODE_PATTERN, BUILDING_CODES, PROJECT_CODE_PATTERN
from recreation_extractor.pid_stitch.models import BoundsDict, PageEvidence, TextSpan


ElectricalNodeKind = Literal["equipment", "line_tag", "device", "section", "continuation", "circuit"]
ElectricalEdgeKind = Literal[
    "attached_to_line",
    "device_on_line",
    "device_on_equipment",
    "equipment_on_section",
    "feeds_panel",
    "continuation_on_line",
    "continues_to",
    "power_source",
    "panel_schedule_feeds",
    "panel_circuit",
]

ELECTRICAL_RULESET = "electrical_one_line_v1"

SHEET_REF_RE = re.compile(r"\b" + PROJECT_CODE_PATTERN + r"-[A-Z0-9][A-Z0-9_.-]*\b", re.IGNORECASE)
EXTERNAL_DRAWING_REF_RE = re.compile(r"\b[A-Z]+-[A-Z]+-\d{2,}\b", re.IGNORECASE)
SWITCHGEAR_RE = re.compile(r"\b" + BUILDING_CODE_PATTERN + r"[A-Z0-9]*?(?:MSWG|SWG|SS|MDP)[A-Z0-9-]*\b", re.IGNORECASE)
SWITCH_SECTION_LABEL_RE = re.compile(r"\bSW\s+[A-Z0-9]{1,4}\b", re.IGNORECASE)
TARGET_EQUIPMENT_RE = re.compile(r"\b" + BUILDING_CODE_PATTERN + r"(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{4,}\b", re.IGNORECASE)
PANEL_SCHEDULE_EQUIPMENT_RE = re.compile(r"\b(?:" + BUILDING_CODE_PATTERN + r"(?=[A-Z0-9-]*\d)[A-Z0-9][A-Z0-9-]{4,}|GEN-\d[A-Z0-9-]*|(?:ATS|UPS|MCC|VFD|PANEL|PNL|SWBD|SWGR|XFMR|TR|TX)-?[A-Z0-9][A-Z0-9-]*)\b", re.IGNORECASE)
ELECTRICAL_EQUIPMENT_RE = re.compile(r"\b(?:VFD|MCC|PANEL|PNL|SWBD|SWGR|XFMR|TR|TX)-?[A-Z0-9][A-Z0-9-]*\b", re.IGNORECASE)
BUS_RE = re.compile(r"\b(?:\d{3,5}A\s+'?SWING'?\s+BUS|\d{3,5}A\s+BUS|(?:480Y/277V|13\.8KV|4160V)[^\\n]{0,80})\b", re.IGNORECASE)
FEEDER_RE = re.compile(r"\b(?:800N|1200N|1600AF|1600AT|5000AF|5000AT|1200A|5000A)\b", re.IGNORECASE)
TRANSFORMER_RE = re.compile(r"\b(?:AA|FA)\s+\d{3,5}KVA\b", re.IGNORECASE)
GENERATOR_TAG_RE = re.compile(r"\bGEN-\d[A-Z0-9-]*\b", re.IGNORECASE)
ELECTRICAL_DEVICE_RE = re.compile(
    r"\b(?:"
    r"\d{2}-[A-Z]\d+[A-Z0-9-]*"
    r"|(?:27|32|46|47|49|50|51|52|59|81|86|87)[A-Z]{0,2}"
    r"|(?:METER|RELAY|BKR|CB|CT|PT|VT|VFD|MCC|PANEL|XFMR|TR|TX)-?[A-Z0-9-]*"
    r"|(?:ATS|GEN|UPS)-?\d[A-Z0-9-]*"
    r"|M\d+"
    r"|\d{3,5}A(?:F|T)?"
    r")\b",
    re.IGNORECASE,
)

GUIDE_ABBREVIATION_CODES = {
    "AC",
    "ATS",
    "BKR",
    "CB",
    "CT",
    "EPMS",
    "FMCS",
    "GEN",
    "GFCI",
    "GFI",
    "LCP",
    "MCC",
    "MDP",
    "MSWG",
    "OFCI",
    "PNL",
    "PP",
    "PT",
    "SS",
    "SWBD",
    "SWG",
    "SWGR",
    "TR",
    "TX",
    "UPS",
    "VFD",
    "VT",
    "XFMR",
}

EQUIPMENT_TAG_SCHEMA_FIELDS = ["BUILDING", "POWER SYSTEM", "VOLTAGE", "COMPONENT", "LEVEL", "GRID LOCATION"]


@dataclass(frozen=True)
class ElectricalGraphNode:
    id: str
    kind: ElectricalNodeKind
    tag: str
    system: str
    sourceFileId: str
    sourcePageId: str
    page: int
    bounds: BoundsDict
    sourceEvidenceIds: list[str]
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ElectricalGraphEdge:
    id: str
    kind: ElectricalEdgeKind
    sourceId: str
    targetId: str
    label: str
    lineTag: str
    system: str
    sourceEvidenceIds: list[str]
    confidence: float
    status: Literal["confirmed", "inferred", "needs_review"]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ElectricalRelationshipGraph:
    projectId: str
    nodes: list[ElectricalGraphNode]
    edges: list[ElectricalGraphEdge]
    metrics: dict[str, Any]
    qa: dict[str, Any]

    def to_visual_qa(self) -> dict[str, Any]:
        return {
            "metrics": dict(self.metrics),
            "qa": dict(self.qa),
            "nodes": [asdict(node) for node in self.nodes],
            "edges": [asdict(edge) for edge in self.edges],
        }


def build_electrical_relationship_graph(
    project_id: str,
    pages: list[PageEvidence],
    source_paths: dict[str, str],
) -> ElectricalRelationshipGraph:
    document_profile = _document_profile(pages, source_paths)
    nodes: list[ElectricalGraphNode] = []
    node_by_key: dict[tuple[str, int, str, str], ElectricalGraphNode] = {}
    primary_by_page: dict[tuple[str, int], ElectricalGraphNode] = {}
    special_nodes: list[ElectricalGraphNode] = []
    special_edges: list[ElectricalGraphEdge] = []
    special_page_keys: set[tuple[str, int]] = set()

    for page in pages:
        if not _is_electrical_hierarchy_page(page, source_paths):
            continue
        feeder_tree = _overall_oneline_tree(page, source_paths) or _generator_feeder_tree(page, source_paths) or _switchgear_feeder_tree(page, source_paths)
        if feeder_tree is None:
            continue
        tree_nodes, tree_edges = feeder_tree
        special_nodes.extend(tree_nodes)
        special_edges.extend(tree_edges)
        special_page_keys.add((page.sourceFileId, page.page))

    for page in sorted(pages, key=lambda item: (item.sourceFileId, item.page, item.id)):
        if not _is_electrical_hierarchy_page(page, source_paths):
            continue
        if (page.sourceFileId, page.page) in special_page_keys:
            continue

        page_nodes: list[ElectricalGraphNode] = []
        for span_index, span in enumerate(page.textSpans):
            for kind, regex, confidence in (
                ("line_tag", SWITCHGEAR_RE, 0.9),
                ("line_tag", BUS_RE, 0.82),
                ("equipment", TARGET_EQUIPMENT_RE, 0.84),
                ("equipment", ELECTRICAL_EQUIPMENT_RE, 0.84),
                ("equipment", TRANSFORMER_RE, 0.78),
                ("equipment", GENERATOR_TAG_RE, 0.9),
                ("device", ELECTRICAL_DEVICE_RE, 0.76),
            ):
                for match_index, match in enumerate(regex.finditer(span.text or "")):
                    tag = _normalize_tag(match.group(0))
                    if not _useful_tag(tag):
                        continue
                    if kind in {"line_tag", "equipment", "device"} and _is_to_reference_target(page, span):
                        continue
                    if kind == "equipment" and (page.sourceFileId, page.page, "line_tag", tag) in node_by_key:
                        continue
                    if kind == "device" and _device_is_redundant(tag, node_by_key, page):
                        continue
                    key = (page.sourceFileId, page.page, kind, tag)
                    if key in node_by_key:
                        continue
                    node = ElectricalGraphNode(
                        id=_node_id(kind, page.id, tag),
                        kind=kind,  # type: ignore[arg-type]
                        tag=tag,
                        system="ELEC",
                        sourceFileId=page.sourceFileId,
                        sourcePageId=page.id,
                        page=page.page,
                        bounds=_match_bounds(span, match_index),
                        sourceEvidenceIds=[f"{page.id}:span:{span_index}"],
                        confidence=confidence,
                        metadata=_node_metadata(kind, tag, span, source_paths.get(page.sourceFileId)),
                    )
                    node_by_key[key] = node
                    nodes.append(node)
                    page_nodes.append(node)

        primary = _primary_line_node(page_nodes)
        if primary is not None:
            primary_by_page[(page.sourceFileId, page.page)] = primary

    generic_pages = [page for page in pages if (page.sourceFileId, page.page) not in special_page_keys and _is_electrical_hierarchy_page(page, source_paths)]

    nodes.extend(special_nodes)
    switchgear_nodes, switchgear_edges = _switchgear_hierarchy(project_id, generic_pages, source_paths, node_by_key)
    nodes.extend(switchgear_nodes)

    continuation_nodes = _continuation_nodes(project_id, generic_pages, source_paths)
    nodes.extend(continuation_nodes)
    panel_schedule_nodes, panel_schedule_edges = _panel_schedule_tree(pages, source_paths)
    nodes.extend(panel_schedule_nodes)

    edges: list[ElectricalGraphEdge] = [*special_edges, *switchgear_edges, *panel_schedule_edges]
    nodes, edges = _merge_matching_incoming_references(nodes, edges)
    page_nodes_by_page: dict[tuple[str, int], list[ElectricalGraphNode]] = {}
    for node in nodes:
        page_nodes_by_page.setdefault((node.sourceFileId, node.page), []).append(node)

    edges.extend(_line_tag_hierarchy_edges(page_nodes_by_page, primary_by_page))

    generator_source_ids = {
        node.id
        for node in nodes
        if node.kind == "equipment" and str(node.metadata.get("equipmentClass") or "") == "generator"
    }
    generator_source_ids.update(edge.sourceId for edge in edges if edge.kind == "power_source")
    for node in nodes:
        if node.kind != "equipment":
            continue
        if node.id in generator_source_ids:
            continue
        page = _page_for_node(node, pages)
        line, line_source = _best_line_node(node, page_nodes_by_page.get((node.sourceFileId, node.page), []), page)
        if line is None or line.id == node.id:
            continue
        confidence = 0.88 if line_source == "linework_geometry" else 0.78 if _same_page_distance(node, line) <= 650.0 else 0.62
        edges.append(
            ElectricalGraphEdge(
                id=_edge_id("attached_to_line", node.id, line.id),
                kind="attached_to_line",
                sourceId=node.id,
                targetId=line.id,
                label=line.tag,
                lineTag=line.tag,
                system="ELEC",
                sourceEvidenceIds=[*node.sourceEvidenceIds, *line.sourceEvidenceIds],
                confidence=confidence,
                status="inferred" if confidence >= 0.7 else "needs_review",
                metadata={"source": line_source},
            )
        )

    equipment_edges = {edge.sourceId: edge for edge in edges if edge.kind == "attached_to_line"}
    for node in nodes:
        if node.kind != "device":
            continue
        page_nodes = page_nodes_by_page.get((node.sourceFileId, node.page), [])
        page = _page_for_node(node, pages)
        equipment = _containing_equipment_node(node, page_nodes, page) or _nearest_equipment_node(node, page_nodes)
        if equipment is not None and _same_page_distance(node, equipment) <= 280.0:
            parent_edge = equipment_edges.get(equipment.id)
            line_tag = parent_edge.lineTag if parent_edge else ""
            edge_source = "enclosure_containment" if page is not None and _share_enclosure(node, equipment, page) else "nearest_equipment"
            confidence = 0.88 if edge_source == "enclosure_containment" else 0.82 if _same_page_distance(node, equipment) <= 160.0 else 0.68
            edges.append(
                ElectricalGraphEdge(
                    id=_edge_id("device_on_equipment", node.id, equipment.id),
                    kind="device_on_equipment",
                    sourceId=node.id,
                    targetId=equipment.id,
                    label=equipment.tag,
                    lineTag=line_tag,
                    system="ELEC",
                    sourceEvidenceIds=[*node.sourceEvidenceIds, *equipment.sourceEvidenceIds],
                    confidence=confidence,
                    status="inferred" if confidence >= 0.7 else "needs_review",
                    metadata={"source": edge_source},
                )
            )
            continue
        line, line_source = _best_line_node(node, page_nodes, page)
        if line is None:
            continue
        if line_source != "linework_geometry" and _is_electrical_line_annotation(node.tag) and _same_page_distance(node, line) <= 520.0:
            line_source = "electrical_line_annotation"
        confidence = 0.88 if line_source == "linework_geometry" else 0.82 if line_source == "electrical_line_annotation" else 0.78 if _same_page_distance(node, line) <= 420.0 else 0.62
        edges.append(
            ElectricalGraphEdge(
                id=_edge_id("device_on_line", node.id, line.id),
                kind="device_on_line",
                sourceId=node.id,
                targetId=line.id,
                label=line.tag,
                lineTag=line.tag,
                system="ELEC",
                sourceEvidenceIds=[*node.sourceEvidenceIds, *line.sourceEvidenceIds],
                confidence=confidence,
                status="inferred" if confidence >= 0.7 else "needs_review",
                metadata={"source": line_source},
            )
        )

    line_nodes_by_tag = {node.tag: node for node in nodes if node.kind == "line_tag"}
    for node in continuation_nodes:
        primary = primary_by_page.get((node.sourceFileId, node.page))
        if primary is not None:
            edges.append(
                ElectricalGraphEdge(
                    id=_edge_id("continuation_on_line", node.id, primary.id),
                    kind="continuation_on_line",
                    sourceId=node.id,
                    targetId=primary.id,
                    label=primary.tag,
                    lineTag=primary.tag,
                    system="ELEC",
                    sourceEvidenceIds=[*node.sourceEvidenceIds, *primary.sourceEvidenceIds],
                    confidence=0.82,
                    status="confirmed",
                    metadata={"source": "to_see_drawing_reference"},
                )
            )
        target_tag = str(node.metadata.get("targetTag") or "")
        target = line_nodes_by_tag.get(target_tag)
        if target is not None and primary is not None and target.id != primary.id and (target.sourceFileId, target.page) != (node.sourceFileId, node.page):
            if _has_loaded_incoming_reference_for_target(target, primary, nodes, edges):
                continue
            edges.append(
                ElectricalGraphEdge(
                    id=_edge_id("continues_to", primary.id, target.id),
                    kind="continues_to",
                    sourceId=primary.id,
                    targetId=target.id,
                    label=target.tag,
                    lineTag=target.tag,
                    system="ELEC",
                    sourceEvidenceIds=[*node.sourceEvidenceIds, *target.sourceEvidenceIds],
                    confidence=0.74,
                    status="needs_review",
                    metadata={"source": "loaded_target_tag", "continuationNodeId": node.id},
                )
            )

    edges.extend(_loaded_upstream_reference_edges(nodes, edges))
    nodes, edges, duplicate_dedupe = _merge_cross_page_duplicate_equipment_tags(nodes, edges)
    nodes, compound_dedupe = _annotate_resolved_compound_targets(nodes)
    nodes = _annotate_document_profile(nodes, document_profile)
    cross_page_dedupe = {**duplicate_dedupe, **compound_dedupe}

    for node in nodes:
        node.metadata.setdefault("discipline", "Electrical")
        node.metadata.setdefault("ruleset", ELECTRICAL_RULESET)
    for edge in edges:
        edge.metadata.setdefault("discipline", "Electrical")
        edge.metadata.setdefault("ruleset", ELECTRICAL_RULESET)

    return ElectricalRelationshipGraph(
        projectId=project_id,
        nodes=nodes,
        edges=edges,
        metrics=_metrics(nodes, edges, pages, source_paths, document_profile, cross_page_dedupe),
        qa=_qa(nodes, edges),
    )


def _has_loaded_incoming_reference_for_target(
    target: ElectricalGraphNode,
    upstream: ElectricalGraphNode,
    nodes: list[ElectricalGraphNode],
    edges: list[ElectricalGraphEdge],
) -> bool:
    nodes_by_id = {node.id: node for node in nodes}
    expected_upstream_tag = _normalize_tag(upstream.tag)
    for edge in edges:
        if edge.kind != "attached_to_line" or edge.sourceId != target.id:
            continue
        parent = nodes_by_id.get(edge.targetId)
        if parent is None or parent.metadata.get("source") != "incoming_sheet_reference":
            continue
        if (parent.sourceFileId, parent.page) == (upstream.sourceFileId, upstream.page):
            continue
        if _normalize_tag(str(parent.metadata.get("upstreamTag") or "")) == expected_upstream_tag:
            return True
    return False


def _merge_matching_incoming_references(
    nodes: list[ElectricalGraphNode],
    edges: list[ElectricalGraphEdge],
) -> tuple[list[ElectricalGraphNode], list[ElectricalGraphEdge]]:
    incoming_nodes = [
        node
        for node in nodes
        if node.kind == "line_tag" and node.metadata.get("source") == "incoming_sheet_reference"
    ]
    real_line_nodes_by_tag: dict[str, list[ElectricalGraphNode]] = {}
    for node in nodes:
        if node.kind != "line_tag" or node.metadata.get("source") == "incoming_sheet_reference":
            continue
        real_line_nodes_by_tag.setdefault(_normalize_tag(node.tag), []).append(node)

    redirect: dict[str, str] = {}
    replacement_by_id: dict[str, ElectricalGraphNode] = {}
    for incoming in incoming_nodes:
        candidates = [
            candidate
            for candidate in real_line_nodes_by_tag.get(_normalize_tag(incoming.tag), [])
            if candidate.page <= incoming.page
        ]
        if not candidates:
            continue
        canonical = min(candidates, key=lambda node: (abs(node.page - incoming.page), node.page, node.bounds["y"], node.bounds["x"], node.id))
        redirect[incoming.id] = canonical.id
        replacement_by_id[canonical.id] = _merge_incoming_reference_metadata(replacement_by_id.get(canonical.id, canonical), [incoming])

    grouped: dict[tuple[str, str], list[ElectricalGraphNode]] = {}
    for node in incoming_nodes:
        if node.id in redirect:
            continue
        if node.kind != "line_tag" or node.metadata.get("source") != "incoming_sheet_reference":
            continue
        upstream_tag = _normalize_tag(str(node.metadata.get("upstreamTag") or ""))
        if not upstream_tag:
            continue
        sheet_ref = _normalize_tag(str(node.metadata.get("sheetRef") or ""))
        grouped.setdefault((sheet_ref or _normalize_tag(node.tag), upstream_tag), []).append(node)

    for incoming_nodes in grouped.values():
        if len(incoming_nodes) < 2:
            continue
        canonical = min(incoming_nodes, key=lambda node: (node.page, node.bounds["y"], node.bounds["x"], node.id))
        duplicate_nodes = [node for node in incoming_nodes if node.id != canonical.id]
        replacement_by_id[canonical.id] = _merge_incoming_reference_metadata(canonical, duplicate_nodes)
        for duplicate in duplicate_nodes:
            redirect[duplicate.id] = canonical.id

    if not redirect:
        return nodes, edges

    next_nodes = [replacement_by_id.get(node.id, node) for node in nodes if node.id not in redirect]
    next_edges: list[ElectricalGraphEdge] = []
    seen_edges: set[tuple[str, str, str, str, str]] = set()
    for edge in edges:
        source_id = redirect.get(edge.sourceId, edge.sourceId)
        target_id = redirect.get(edge.targetId, edge.targetId)
        dedupe_key = (edge.kind, source_id, target_id, edge.label, str(edge.metadata.get("source") or ""))
        if dedupe_key in seen_edges:
            continue
        seen_edges.add(dedupe_key)
        if source_id == edge.sourceId and target_id == edge.targetId:
            next_edges.append(edge)
            continue
        next_edges.append(
            replace(
                edge,
                id=_edge_id(edge.kind, source_id, target_id),
                sourceId=source_id,
                targetId=target_id,
            )
        )
    return next_nodes, next_edges


def _merge_incoming_reference_metadata(
    canonical: ElectricalGraphNode,
    incoming_nodes: list[ElectricalGraphNode],
) -> ElectricalGraphNode:
    all_nodes = [canonical, *incoming_nodes]
    source_evidence_ids = _unique_strings([evidence_id for node in all_nodes for evidence_id in node.sourceEvidenceIds])
    sheet_refs = _unique_strings(
        [
            str(node.metadata.get("sheetRef") or "")
            for node in incoming_nodes
            if str(node.metadata.get("sheetRef") or "")
        ]
    )
    metadata = dict(canonical.metadata)
    if sheet_refs:
        metadata["sheetRefs"] = _unique_strings([*(metadata.get("sheetRefs") or []), *sheet_refs])
        metadata.setdefault("sheetRef", sheet_refs[0])
    return replace(canonical, sourceEvidenceIds=source_evidence_ids, metadata=metadata)


def _loaded_upstream_reference_edges(
    nodes: list[ElectricalGraphNode],
    existing_edges: list[ElectricalGraphEdge],
) -> list[ElectricalGraphEdge]:
    existing_ids = {edge.id for edge in existing_edges}
    line_nodes_by_tag: dict[str, list[ElectricalGraphNode]] = defaultdict_list(nodes)
    edges: list[ElectricalGraphEdge] = []
    for incoming in nodes:
        if incoming.kind != "line_tag" or incoming.metadata.get("source") != "incoming_sheet_reference":
            continue
        upstream_tag = _normalize_tag(str(incoming.metadata.get("upstreamTag") or ""))
        if not upstream_tag:
            continue
        candidates = [
            candidate
            for candidate in line_nodes_by_tag.get(upstream_tag, [])
            if candidate.id != incoming.id and (candidate.sourceFileId, candidate.page) != (incoming.sourceFileId, incoming.page)
            and candidate.metadata.get("source") != "incoming_sheet_reference"
        ]
        if not candidates:
            continue
        source = min(candidates, key=lambda candidate: (abs(candidate.page - incoming.page), candidate.sourceFileId, candidate.id))
        edge_id = _edge_id("continues_to", source.id, incoming.id)
        if edge_id in existing_ids:
            continue
        edges.append(
            ElectricalGraphEdge(
                id=edge_id,
                kind="continues_to",
                sourceId=source.id,
                targetId=incoming.id,
                label=incoming.tag,
                lineTag=incoming.tag,
                system="ELEC",
                sourceEvidenceIds=[*source.sourceEvidenceIds, *incoming.sourceEvidenceIds],
                confidence=0.82,
                status="confirmed",
                metadata={"source": "loaded_upstream_tag_to_sheet_reference", "discipline": "Electrical", "ruleset": ELECTRICAL_RULESET},
            )
        )
    return edges


def _annotate_resolved_compound_targets(
    nodes: list[ElectricalGraphNode],
) -> tuple[list[ElectricalGraphNode], dict[str, Any]]:
    alias_index: dict[str, list[ElectricalGraphNode]] = {}
    for node in nodes:
        for alias in _node_match_aliases(node.tag):
            alias_index.setdefault(alias, []).append(node)

    resolved_count = 0
    annotated: list[ElectricalGraphNode] = []
    for node in nodes:
        aliases = _compound_equipment_aliases(node.tag)
        if len(aliases) < 2:
            annotated.append(node)
            continue

        resolved_nodes: list[ElectricalGraphNode] = []
        resolved_aliases: list[str] = []
        for alias in aliases:
            matches = [
                candidate
                for candidate in alias_index.get(alias, [])
                if candidate.id != node.id and (candidate.sourceFileId, candidate.page) != (node.sourceFileId, node.page)
            ]
            if not matches:
                continue
            resolved_aliases.append(alias)
            resolved_nodes.append(min(matches, key=lambda candidate: (candidate.page, candidate.bounds["y"], candidate.bounds["x"], candidate.id)))

        metadata = dict(node.metadata)
        metadata["expandedAliasTags"] = aliases
        if len(resolved_aliases) == len(aliases):
            resolved_count += 1
            metadata["resolvedAliasTags"] = resolved_aliases
            metadata["resolvedByNodeIds"] = _unique_strings([candidate.id for candidate in resolved_nodes])
            metadata["suppressInEquipmentFlow"] = True
        annotated.append(replace(node, metadata=metadata))

    return annotated, {
        "resolvedCompoundTargets": resolved_count,
        "compoundTargets": sum(1 for node in nodes if len(_compound_equipment_aliases(node.tag)) > 1),
    }


def _merge_cross_page_duplicate_equipment_tags(
    nodes: list[ElectricalGraphNode],
    edges: list[ElectricalGraphEdge],
) -> tuple[list[ElectricalGraphNode], list[ElectricalGraphEdge], dict[str, Any]]:
    duplicate_groups: dict[str, list[ElectricalGraphNode]] = {}
    for node in nodes:
        if node.kind not in {"line_tag", "equipment"}:
            continue
        tag = _owner_base_tag(node.tag)
        if not _is_actual_equipment_tag(tag):
            continue
        duplicate_groups.setdefault(tag, []).append(node)

    redirect: dict[str, str] = {}
    replacement_by_id: dict[str, ElectricalGraphNode] = {}
    skip_outgoing_edges_from_redirected: set[str] = set()
    merged_tags: list[str] = []
    for tag, group in duplicate_groups.items():
        page_keys = {(node.sourceFileId, node.page) for node in group}
        if len(group) < 2 or len(page_keys) < 2:
            continue
        canonical = min(group, key=_duplicate_canonical_rank)
        duplicates = [node for node in group if node.id != canonical.id]
        if not duplicates:
            continue
        replacement_by_id[canonical.id] = _merge_duplicate_equipment_metadata(canonical, duplicates, tag)
        for duplicate in duplicates:
            redirect[duplicate.id] = canonical.id
            if canonical.metadata.get("source") == "incoming_sheet_reference":
                skip_outgoing_edges_from_redirected.add(duplicate.id)
        merged_tags.append(tag)

    if not redirect:
        return nodes, edges, {"mergedDuplicateTags": 0, "mergedDuplicateNodes": 0}

    next_nodes = [replacement_by_id.get(node.id, node) for node in nodes if node.id not in redirect]
    next_edges: list[ElectricalGraphEdge] = []
    seen_edges: set[tuple[str, str, str, str, str]] = set()
    for edge in edges:
        if edge.sourceId in skip_outgoing_edges_from_redirected:
            continue
        source_id = redirect.get(edge.sourceId, edge.sourceId)
        target_id = redirect.get(edge.targetId, edge.targetId)
        if source_id == target_id:
            continue
        dedupe_key = (edge.kind, source_id, target_id, edge.label, str(edge.metadata.get("source") or ""))
        if dedupe_key in seen_edges:
            continue
        seen_edges.add(dedupe_key)
        if source_id == edge.sourceId and target_id == edge.targetId:
            next_edges.append(edge)
            continue
        next_edges.append(
            replace(
                edge,
                id=_edge_id(edge.kind, source_id, target_id),
                sourceId=source_id,
                targetId=target_id,
            )
        )

    return next_nodes, next_edges, {
        "mergedDuplicateTags": len(merged_tags),
        "mergedDuplicateNodes": len(redirect),
    }


def _duplicate_canonical_rank(node: ElectricalGraphNode) -> tuple[int, int, float, float, str]:
    source = str(node.metadata.get("source") or "")
    source_rank = {
        "generator_feeder_equipment": 0,
        "switchgear_ofci_owner_tag": 0,
        "switchgear_corner_label": 1,
        "incoming_sheet_reference": 1,
        "bottom_arrow_target": 4,
    }.get(source, 3)
    kind_rank = 0 if node.kind == "equipment" else 1
    return (source_rank, kind_rank, node.page, node.bounds["y"], node.id)


def _merge_duplicate_equipment_metadata(
    canonical: ElectricalGraphNode,
    duplicates: list[ElectricalGraphNode],
    tag: str,
) -> ElectricalGraphNode:
    all_nodes = [canonical, *duplicates]
    metadata = dict(canonical.metadata)
    metadata["canonicalTag"] = tag
    metadata["mergedFromNodeIds"] = _unique_strings([node.id for node in duplicates])
    metadata["mergedSourcePages"] = [
        {"sourceFileId": node.sourceFileId, "page": node.page, "sourcePageId": node.sourcePageId}
        for node in sorted(all_nodes, key=lambda item: (item.sourceFileId, item.page, item.id))
    ]
    metadata["crossPageDedupe"] = "exact_equipment_tag"
    return replace(
        canonical,
        sourceEvidenceIds=_unique_strings([evidence_id for node in all_nodes for evidence_id in node.sourceEvidenceIds]),
        metadata=metadata,
    )


def _annotate_document_profile(
    nodes: list[ElectricalGraphNode],
    document_profile: dict[str, Any],
) -> list[ElectricalGraphNode]:
    annotated: list[ElectricalGraphNode] = []
    for node in nodes:
        tag_profile = _equipment_tag_profile(node.tag, document_profile)
        if not tag_profile:
            annotated.append(node)
            continue
        metadata = dict(node.metadata)
        metadata["tagProfile"] = tag_profile
        metadata["documentGuideComponent"] = tag_profile["componentCode"]
        metadata["documentGuideDescription"] = tag_profile["componentDescription"]
        if node.kind in {"line_tag", "equipment"} and not metadata.get("equipmentClass"):
            equipment_class = _component_equipment_class(str(tag_profile.get("componentCode") or ""))
            if equipment_class:
                metadata["equipmentClass"] = equipment_class
        if node.kind in {"line_tag", "equipment", "section"} and tag_profile.get("complete") is False:
            metadata["suppressInEquipmentFlow"] = True
            metadata.setdefault("reviewReason", "incomplete_equipment_tag")
        annotated.append(replace(node, metadata=metadata))
    return annotated


def _equipment_tag_profile(tag: str, document_profile: dict[str, Any]) -> dict[str, Any]:
    component_codes = _profile_component_codes(document_profile)
    if not component_codes:
        return {}
    upper = _owner_base_tag(_normalize_tag(tag))
    if _is_electrical_rating_or_annotation(upper):
        return {}
    compound_aliases = _compound_equipment_aliases(upper)
    if compound_aliases:
        first_profile = _equipment_tag_profile(compound_aliases[0], document_profile)
        if first_profile:
            return {**first_profile, "rawTag": upper, "compoundAliases": compound_aliases}
        return {}
    if GENERATOR_TAG_RE.fullmatch(upper) and "GEN" in component_codes:
        return {
            "source": "document_guide",
            "rawTag": upper,
            "componentCode": "GEN",
            "componentDescription": component_codes["GEN"],
            "prefix": "",
            "building": "",
            "powerSystem": "",
            "level": "",
            "gridLocation": "",
            "complete": True,
            "missingFields": [],
        }

    for code in sorted(component_codes, key=lambda value: (-len(value), value)):
        match = re.fullmatch(rf"(?P<prefix>{BUILDING_CODE_PATTERN}[A-Z0-9-]*?){re.escape(code)}(?P<suffix>[A-Z0-9-]*)", upper)
        if not match:
            continue
        prefix = match.group("prefix")
        suffix = match.group("suffix")
        level = ""
        grid_location = ""
        missing_fields: list[str] = []
        suffix_match = re.fullmatch(r"(?P<level>\d+)(?P<grid>[A-Z]\d+(?:-\d+)?)", suffix)
        if suffix_match:
            level = suffix_match.group("level")
            grid_location = suffix_match.group("grid")
        else:
            level_match = re.match(r"(?P<level>\d+)", suffix)
            if level_match:
                level = level_match.group("level")
            else:
                missing_fields.append("level")
            missing_fields.append("gridLocation")
        return {
            "source": "document_guide",
            "rawTag": upper,
            "componentCode": code,
            "componentDescription": component_codes[code],
            "prefix": prefix,
            "building": prefix[:2] if prefix.startswith(BUILDING_CODES) else "",
            "powerSystem": prefix[2:] if prefix.startswith(BUILDING_CODES) else prefix,
            "level": level,
            "gridLocation": grid_location,
            "complete": len(missing_fields) == 0,
            "missingFields": missing_fields,
        }
    return {}


def _profile_component_codes(document_profile: dict[str, Any]) -> dict[str, str]:
    values = document_profile.get("equipmentComponentCodes")
    return values if isinstance(values, dict) else {}


def _component_equipment_class(component_code: str) -> str:
    code = component_code.upper()
    if code == "GEN":
        return "generator"
    if code == "MDP":
        return "main_distribution_panel"
    if code in {"MSWG", "SWG", "SWGR", "SWBD"}:
        return "main_switchgear" if code == "MSWG" else "switchgear"
    if code == "SS":
        return "substation"
    if code == "MCC":
        return "motor_control_center"
    if code == "VFD":
        return "vfd"
    if code in {"TR", "TX", "XFMR"}:
        return "transformer"
    if code in {"PNL", "PANEL", "PP"}:
        return "panel"
    if code == "LCP":
        return "lighting_control_panel"
    if code == "UPS":
        return "ups"
    if code == "ATS":
        return "automatic_transfer_switch"
    return ""


def _node_match_aliases(tag: str) -> list[str]:
    normalized = _normalize_tag(tag)
    aliases = [normalized]
    owner_base = _owner_base_tag(normalized)
    if owner_base != normalized:
        aliases.append(owner_base)
    aliases.extend(_compound_equipment_aliases(normalized))
    return _unique_strings([alias for alias in aliases if alias])


def _compound_equipment_aliases(tag: str) -> list[str]:
    upper = _owner_base_tag(_normalize_tag(tag))
    match = re.fullmatch(r"(" + BUILDING_CODE_PATTERN + r"[A-Z0-9-]*?)([A-Z])(\d{1,3})\s*&\s*([A-Z])(\d{1,3})", upper)
    if match:
        prefix, first_letter, first_number, second_letter, second_number = match.groups()
        return [f"{prefix}{first_letter}{first_number}", f"{prefix}{second_letter}{second_number}"]
    full_match = re.fullmatch(r"(" + BUILDING_CODE_PATTERN + r"[A-Z0-9-]*?[A-Z]\d{1,3})\s*&\s*(" + BUILDING_CODE_PATTERN + r"[A-Z0-9-]*?[A-Z]\d{1,3})", upper)
    if full_match:
        return [full_match.group(1), full_match.group(2)]
    return []


def defaultdict_list(nodes: list[ElectricalGraphNode]) -> dict[str, list[ElectricalGraphNode]]:
    grouped: dict[str, list[ElectricalGraphNode]] = {}
    for node in nodes:
        grouped.setdefault(node.tag, []).append(node)
    return grouped


def _unique_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        unique.append(value)
    return unique


def _panel_schedule_tree(
    pages: list[PageEvidence],
    source_paths: dict[str, str],
) -> tuple[list[ElectricalGraphNode], list[ElectricalGraphEdge]]:
    nodes: list[ElectricalGraphNode] = []
    edges: list[ElectricalGraphEdge] = []
    node_by_key: dict[tuple[str, int, str, str], ElectricalGraphNode] = {}

    for page in sorted(pages, key=lambda item: (item.sourceFileId, item.page, item.id)):
        profile = _electrical_page_profile(page, source_paths)
        if profile is None or profile.get("drawingType") != "panel_schedule":
            continue

        schedules = _panel_schedule_blocks(page)
        for schedule_index, schedule in enumerate(schedules):
            designation = str(schedule.get("designation") or "")
            supply_chain = schedule.get("supplyChain") if isinstance(schedule.get("supplyChain"), list) else []
            if not designation or not supply_chain:
                continue

            chain_nodes: list[ElectricalGraphNode] = []
            for chain_index, tag in enumerate([*supply_chain, designation]):
                tag_text = _normalize_tag(str(tag))
                if not tag_text:
                    continue
                source = "panel_schedule_designation" if tag_text == designation else "panel_schedule_supply_from"
                node = _ensure_panel_schedule_node(
                    nodes,
                    node_by_key,
                    page,
                    source_paths,
                    kind="line_tag",
                    tag=tag_text,
                    bounds=schedule["bounds"],
                    evidence_id=f"{page.id}:panel-schedule:{schedule_index}:node:{chain_index}",
                    confidence=0.94 if tag_text == designation else 0.9,
                    metadata={
                        "source": source,
                        "rawSupplyFrom": schedule.get("rawSupplyFrom", ""),
                    },
                )
                chain_nodes.append(node)

            for parent, child in zip(chain_nodes, chain_nodes[1:]):
                if _panel_schedule_child_is_generator_root(child):
                    continue
                edges.append(
                    ElectricalGraphEdge(
                        id=_edge_id("panel_schedule_feeds", child.id, parent.id),
                        kind="panel_schedule_feeds",
                        sourceId=child.id,
                        targetId=parent.id,
                        label=parent.tag,
                        lineTag=child.tag,
                        system="ELEC",
                        sourceEvidenceIds=_unique_strings([*child.sourceEvidenceIds, *parent.sourceEvidenceIds]),
                        confidence=0.9,
                        status="confirmed",
                        metadata={
                            "source": "panel_schedule_supply_from",
                            "rawSupplyFrom": schedule.get("rawSupplyFrom", ""),
                            "discipline": "Electrical",
                            "ruleset": ELECTRICAL_RULESET,
                        },
                    )
                )

            designation_node = chain_nodes[-1] if chain_nodes else None
            if designation_node is None:
                continue
            for circuit in schedule.get("circuits", []):
                if not isinstance(circuit, dict):
                    continue
                circuit_number = str(circuit.get("number") or "").strip()
                description = _clean_panel_circuit_description(str(circuit.get("description") or ""))
                if not circuit_number or not description:
                    continue
                circuit_tag = f"{designation} CKT {circuit_number}"
                circuit_node = _ensure_panel_schedule_node(
                    nodes,
                    node_by_key,
                    page,
                    source_paths,
                    kind="circuit",
                    tag=circuit_tag,
                    bounds=circuit.get("bounds") if isinstance(circuit.get("bounds"), dict) else schedule["bounds"],
                    evidence_id=f"{page.id}:panel-schedule:{schedule_index}:circuit:{circuit_number}",
                    confidence=0.88,
                    metadata={
                        "source": "panel_schedule_circuit",
                        "circuitNumber": circuit_number,
                        "equipmentDescription": description,
                        "panelDesignation": designation,
                        "rawSupplyFrom": schedule.get("rawSupplyFrom", ""),
                    },
                )
                edges.append(
                    ElectricalGraphEdge(
                        id=_edge_id("panel_circuit", circuit_node.id, designation_node.id),
                        kind="panel_circuit",
                        sourceId=circuit_node.id,
                        targetId=designation_node.id,
                        label=designation_node.tag,
                        lineTag=designation_node.tag,
                        system="ELEC",
                        sourceEvidenceIds=_unique_strings([*circuit_node.sourceEvidenceIds, *designation_node.sourceEvidenceIds]),
                        confidence=0.88,
                        status="confirmed",
                        metadata={"source": "panel_schedule_circuit", "discipline": "Electrical", "ruleset": ELECTRICAL_RULESET},
                    )
                )

    return nodes, edges


def _panel_schedule_child_is_generator_root(node: ElectricalGraphNode) -> bool:
    return node.kind == "line_tag" and bool(GENERATOR_TAG_RE.fullmatch(node.tag))


def _ensure_panel_schedule_node(
    nodes: list[ElectricalGraphNode],
    node_by_key: dict[tuple[str, int, str, str], ElectricalGraphNode],
    page: PageEvidence,
    source_paths: dict[str, str],
    *,
    kind: ElectricalNodeKind,
    tag: str,
    bounds: BoundsDict,
    evidence_id: str,
    confidence: float,
    metadata: dict[str, Any],
) -> ElectricalGraphNode:
    key = (page.sourceFileId, page.page, kind, tag)
    existing = node_by_key.get(key)
    if existing is not None:
        return existing
    node = ElectricalGraphNode(
        id=_node_id(kind, page.id, f"panel_schedule_{tag}"),
        kind=kind,
        tag=tag,
        system="ELEC",
        sourceFileId=page.sourceFileId,
        sourcePageId=page.id,
        page=page.page,
        bounds=bounds,
        sourceEvidenceIds=[evidence_id],
        confidence=confidence,
        metadata={
            "sourcePath": source_paths.get(page.sourceFileId),
            "discipline": "Electrical",
            "ruleset": ELECTRICAL_RULESET,
            **metadata,
        },
    )
    node_by_key[key] = node
    nodes.append(node)
    return node


def _panel_schedule_blocks(page: PageEvidence) -> list[dict[str, Any]]:
    label_spans = [
        span
        for span in sorted(page.textSpans, key=lambda item: (item.y, item.x))
        if "DESIGNATION" in span_text(span).upper()
    ]
    schedules: list[dict[str, Any]] = []
    for index, label in enumerate(label_spans):
        designation = _panel_schedule_label_value(page, label, "DESIGNATION")
        if not designation:
            continue
        next_label = label_spans[index + 1] if index + 1 < len(label_spans) else None
        bounds = _panel_schedule_bounds(page, label, next_label)
        supply_label = _nearest_panel_schedule_label(page, label, bounds, "SUPPLY FROM")
        if supply_label is None:
            continue
        raw_supply = _panel_schedule_label_text(page, supply_label, "SUPPLY FROM", bounds)
        supply_chain = _panel_supply_chain(raw_supply)
        if not supply_chain:
            continue
        schedules.append(
            {
                "designation": designation,
                "rawSupplyFrom": raw_supply,
                "supplyChain": supply_chain,
                "bounds": bounds,
                "circuits": _panel_schedule_circuits(page, bounds),
            }
        )
    return schedules


def _panel_schedule_bounds(page: PageEvidence, label: TextSpan, next_label: TextSpan | None) -> BoundsDict:
    x_margin = 90.0
    y_margin = 18.0
    x = max(0.0, label.x - x_margin)
    y = max(0.0, label.y - y_margin)
    width = min(page.width - x, max(460.0, page.width * 0.22))
    y_limit = page.height * 0.96
    if next_label is not None and abs(next_label.x - label.x) <= width * 0.45 and next_label.y > label.y:
        y_limit = min(y_limit, next_label.y - y_margin)
    return {"x": x, "y": y, "width": width, "height": max(1.0, y_limit - y)}


def _nearest_panel_schedule_label(page: PageEvidence, anchor: TextSpan, bounds: BoundsDict, label: str) -> TextSpan | None:
    label_text = label.upper()
    candidates = [
        span
        for span in page.textSpans
        if _span_in_bounds(span, bounds)
        and span.y >= anchor.y - 8.0
        and label_text in span_text(span).upper()
    ]
    return min(candidates, key=lambda span: abs(span.y - anchor.y) + abs(span.x - anchor.x), default=None)


def _panel_schedule_label_value(page: PageEvidence, label_span: TextSpan, label: str) -> str:
    bounds = _panel_schedule_bounds(page, label_span, None)
    text = _panel_schedule_label_text(page, label_span, label, bounds)
    tags = _panel_equipment_tags(text)
    return tags[0] if tags else ""


def _panel_schedule_label_text(page: PageEvidence, label_span: TextSpan, label: str, bounds: BoundsDict) -> str:
    label_re = re.compile(rf"{re.escape(label)}\s*:?", re.IGNORECASE)
    parts: list[str] = []
    same_text = label_re.sub("", span_text(label_span), count=1).strip(" :-")
    if same_text:
        parts.append(same_text)
    row_y = _center_of_span(label_span)["y"]
    row_spans = [
        span
        for span in page.textSpans
        if span is not label_span
        and _span_in_bounds(span, bounds)
        and abs(_center_of_span(span)["y"] - row_y) <= max(8.0, label_span.height)
        and span.x >= label_span.x
    ]
    parts.extend(span_text(span) for span in sorted(row_spans, key=lambda item: item.x) if span_text(span))
    return _normalize_tag(" ".join(parts))


def _panel_supply_chain(raw_supply: str) -> list[str]:
    tags = _panel_equipment_tags(raw_supply)
    return _unique_strings(tags)


def _panel_equipment_tags(text: str) -> list[str]:
    return _unique_strings([_normalize_tag(match.group(0)) for match in PANEL_SCHEDULE_EQUIPMENT_RE.finditer(text or "")])


def _panel_schedule_circuits(page: PageEvidence, bounds: BoundsDict) -> list[dict[str, Any]]:
    header_spans = [
        span
        for span in page.textSpans
        if _span_in_bounds(span, bounds) and span_text(span).upper() == "CKT"
    ]
    if not header_spans:
        return []
    ckt_header = min(header_spans, key=lambda span: (span.y, span.x))
    ckt_center_x = _center_of_span(ckt_header)["x"]
    circuits: list[dict[str, Any]] = []
    seen_numbers: set[str] = set()
    for span in sorted(page.textSpans, key=lambda item: (item.y, item.x)):
        text = span_text(span)
        if not _span_in_bounds(span, bounds) or _center_of_span(span)["y"] <= _center_of_span(ckt_header)["y"] + 8.0:
            continue
        if abs(_center_of_span(span)["x"] - ckt_center_x) > 72.0:
            continue
        if not re.fullmatch(r"\d{1,3}", text):
            continue
        number = text.lstrip("0") or text
        if number in seen_numbers:
            continue
        description, description_bounds = _panel_circuit_description_for_row(page, span, bounds)
        description = _clean_panel_circuit_description(description)
        if not description:
            continue
        seen_numbers.add(number)
        circuits.append({"number": number, "description": description, "bounds": description_bounds or span_bounds(span)})
    return circuits


def _panel_circuit_description_for_row(page: PageEvidence, ckt_span: TextSpan, bounds: BoundsDict) -> tuple[str, BoundsDict | None]:
    row_y = _center_of_span(ckt_span)["y"]
    candidates = [
        span
        for span in page.textSpans
        if span is not ckt_span
        and _span_in_bounds(span, bounds)
        and abs(_center_of_span(span)["y"] - row_y) <= max(8.0, ckt_span.height)
        and span.x > ckt_span.x + ckt_span.width
    ]
    text_spans = [
        span
        for span in sorted(candidates, key=lambda item: item.x)
        if _looks_like_panel_circuit_description(span_text(span))
    ]
    if not text_spans:
        return "", None
    first = text_spans[0]
    return span_text(first), span_bounds(first)


def _looks_like_panel_circuit_description(text: str) -> bool:
    upper = _normalize_tag(text)
    if not upper or not re.search(r"[A-Z]", upper):
        return False
    if upper in {"CKT", "EQUIPMENT DESCRIPTION", "BREAKER RATING", "LOAD", "TOTAL", "PHASE", "A", "B", "C"}:
        return False
    if re.fullmatch(r"\d+(?:\.\d+)?(?:A|KVA|KW)?", upper):
        return False
    return True


def _clean_panel_circuit_description(description: str) -> str:
    cleaned = _normalize_tag(description).strip(" -")
    if not cleaned or not re.search(r"[A-Z]", cleaned):
        return ""
    if cleaned.startswith(("SPARE", "SPACE", "FUTURE")):
        return ""
    return cleaned


def _span_in_bounds(span: TextSpan, bounds: BoundsDict) -> bool:
    center = _center_of_span(span)
    return bounds["x"] <= center["x"] <= bounds["x"] + bounds["width"] and bounds["y"] <= center["y"] <= bounds["y"] + bounds["height"]


def _continuation_nodes(project_id: str, pages: list[PageEvidence], source_paths: dict[str, str]) -> list[ElectricalGraphNode]:
    del project_id
    nodes: list[ElectricalGraphNode] = []
    seen: set[tuple[str, int, str, str]] = set()
    for page in pages:
        if not _is_electrical_hierarchy_page(page, source_paths):
            continue
        lines = [span for span in sorted(page.textSpans, key=lambda item: (item.y, item.x)) if span_text(span)]
        for index, span in enumerate(lines):
            if span_text(span).upper() != "TO":
                continue
            window = lines[index : index + 8]
            window_text = " ".join(span_text(item) for item in window)
            target = _target_after_to(window)
            sheet = _first_match(SHEET_REF_RE, window_text)
            if not target and not sheet:
                continue
            label = f"TO {target or 'UNKNOWN'}"
            if sheet:
                label = f"{label} / {sheet.upper()}"
            key = (page.sourceFileId, page.page, target, sheet)
            if key in seen:
                continue
            seen.add(key)
            bounds = _union_bounds(window[: min(len(window), 5)])
            nodes.append(
                ElectricalGraphNode(
                    id=_node_id("continuation", page.id, f"{target}_{sheet}_{index}"),
                    kind="continuation",
                    tag=label,
                    system="ELEC",
                    sourceFileId=page.sourceFileId,
                    sourcePageId=page.id,
                    page=page.page,
                    bounds=bounds,
                    sourceEvidenceIds=[f"{page.id}:continuation:{index}"],
                    confidence=0.84 if target and sheet else 0.66,
                    metadata={"targetTag": target, "sheetRef": sheet, "sourcePath": source_paths.get(page.sourceFileId)},
                )
            )
    return nodes


def _line_tag_hierarchy_edges(
    page_nodes_by_page: dict[tuple[str, int], list[ElectricalGraphNode]],
    primary_by_page: dict[tuple[str, int], ElectricalGraphNode],
) -> list[ElectricalGraphEdge]:
    edges: list[ElectricalGraphEdge] = []
    for page_key, page_nodes in page_nodes_by_page.items():
        primary = primary_by_page.get(page_key)
        if primary is None:
            continue
        line_nodes = [node for node in page_nodes if node.kind == "line_tag" and node.id != primary.id]
        bus_nodes = [node for node in line_nodes if _is_bus_tag(node.tag)]
        for bus in bus_nodes:
            edges.append(
                ElectricalGraphEdge(
                    id=_edge_id("attached_to_line", bus.id, primary.id),
                    kind="attached_to_line",
                    sourceId=bus.id,
                    targetId=primary.id,
                    label=primary.tag,
                    lineTag=primary.tag,
                    system="ELEC",
                    sourceEvidenceIds=[*bus.sourceEvidenceIds, *primary.sourceEvidenceIds],
                    confidence=0.84,
                    status="inferred",
                    metadata={"source": "electrical_bus_under_primary"},
                )
            )

        for line in line_nodes:
            if _is_bus_tag(line.tag) or not _is_feeder_line_tag(line.tag, primary.tag):
                continue
            parent = _nearest_node(line, bus_nodes) if bus_nodes else primary
            if parent is None or parent.id == line.id:
                continue
            edge_source = "electrical_feeder_under_bus" if _is_bus_tag(parent.tag) else "electrical_feeder_under_primary"
            edges.append(
                ElectricalGraphEdge(
                    id=_edge_id("attached_to_line", line.id, parent.id),
                    kind="attached_to_line",
                    sourceId=line.id,
                    targetId=parent.id,
                    label=parent.tag,
                    lineTag=parent.tag,
                    system="ELEC",
                    sourceEvidenceIds=[*line.sourceEvidenceIds, *parent.sourceEvidenceIds],
                    confidence=0.78,
                    status="inferred",
                    metadata={"source": edge_source},
                )
            )
    return edges


def _switchgear_hierarchy(
    project_id: str,
    pages: list[PageEvidence],
    source_paths: dict[str, str],
    node_by_key: dict[tuple[str, int, str, str], ElectricalGraphNode],
) -> tuple[list[ElectricalGraphNode], list[ElectricalGraphEdge]]:
    del project_id
    nodes: list[ElectricalGraphNode] = []
    edges: list[ElectricalGraphEdge] = []

    for page in pages:
        if not _is_electrical_hierarchy_page(page, source_paths):
            continue
        owner_nodes = _switchgear_owner_nodes(page, source_paths)
        nodes.extend(owner_nodes)
        for owner in owner_nodes:
            line = node_by_key.get((page.sourceFileId, page.page, "line_tag", _owner_base_tag(owner.tag)))
            if line is None:
                continue
            edges.append(
                ElectricalGraphEdge(
                    id=_edge_id("equipment_on_section", line.id, owner.id),
                    kind="equipment_on_section",
                    sourceId=line.id,
                    targetId=owner.id,
                    label=owner.tag,
                    lineTag=line.tag,
                    system="ELEC",
                    sourceEvidenceIds=[*line.sourceEvidenceIds, *owner.sourceEvidenceIds],
                    confidence=0.94,
                    status="confirmed",
                    metadata={"source": "switchgear_owner_line_tag"},
                )
            )

        section_nodes = _switchgear_section_nodes(page, source_paths)
        nodes.extend(section_nodes)
        for section in section_nodes:
            owner = _nearest_node(section, owner_nodes)
            if owner is None or abs(_center_of_bounds(section.bounds)["x"] - _center_of_bounds(owner.bounds)["x"]) > page.width * 0.45:
                continue
            edges.append(
                ElectricalGraphEdge(
                    id=_edge_id("equipment_on_section", section.id, owner.id),
                    kind="equipment_on_section",
                    sourceId=section.id,
                    targetId=owner.id,
                    label=owner.tag,
                    lineTag=owner.tag,
                    system="ELEC",
                    sourceEvidenceIds=[*section.sourceEvidenceIds, *owner.sourceEvidenceIds],
                    confidence=0.9,
                    status="confirmed",
                    metadata={"source": "switchgear_ofci_section_owner"},
                )
            )
        if not section_nodes:
            continue

        transformer_nodes = _switchgear_transformer_nodes(page, source_paths, section_nodes)
        nodes.extend(transformer_nodes)
        for transformer in transformer_nodes:
            section = _nearest_node(transformer, section_nodes)
            if section is None:
                continue
            edges.append(
                ElectricalGraphEdge(
                    id=_edge_id("equipment_on_section", transformer.id, section.id),
                    kind="equipment_on_section",
                    sourceId=transformer.id,
                    targetId=section.id,
                    label=section.tag,
                    lineTag=section.tag,
                    system="ELEC",
                    sourceEvidenceIds=[*transformer.sourceEvidenceIds, *section.sourceEvidenceIds],
                    confidence=0.86,
                    status="confirmed",
                    metadata={"source": "switchgear_section_label"},
                )
            )

        breaker_nodes = _switchgear_breaker_nodes(page, source_paths, section_nodes, transformer_nodes)
        nodes.extend(breaker_nodes)
        for breaker in breaker_nodes:
            parent = _nearest_node(breaker, transformer_nodes) or _nearest_node(breaker, section_nodes)
            if parent is None:
                continue
            edges.append(
                ElectricalGraphEdge(
                    id=_edge_id("device_on_equipment", breaker.id, parent.id),
                    kind="device_on_equipment",
                    sourceId=breaker.id,
                    targetId=parent.id,
                    label=parent.tag,
                    lineTag=parent.tag,
                    system="ELEC",
                    sourceEvidenceIds=[*breaker.sourceEvidenceIds, *parent.sourceEvidenceIds],
                    confidence=0.78,
                    status="inferred",
                    metadata={"source": "switchgear_breaker_cell"},
                )
            )

        panel_nodes = [
            node
            for (source_file_id, page_number, _kind, _tag), node in node_by_key.items()
            if source_file_id == page.sourceFileId and page_number == page.page and node.kind == "line_tag" and "MDP" in node.tag
        ]
        for panel in panel_nodes:
            if panel.bounds["y"] < page.height * 0.58:
                continue
            parent = _nearest_node(panel, breaker_nodes) or _nearest_node(panel, transformer_nodes) or _nearest_node(panel, section_nodes)
            if parent is None:
                continue
            edges.append(
                ElectricalGraphEdge(
                    id=_edge_id("feeds_panel", panel.id, parent.id),
                    kind="feeds_panel",
                    sourceId=panel.id,
                    targetId=parent.id,
                    label=parent.tag,
                    lineTag=panel.tag,
                    system="ELEC",
                    sourceEvidenceIds=[*panel.sourceEvidenceIds, *parent.sourceEvidenceIds],
                    confidence=0.74,
                    status="inferred",
                    metadata={"source": "switchgear_cell_panel_label"},
                )
            )

    return nodes, edges


def _overall_oneline_tree(
    page: PageEvidence,
    source_paths: dict[str, str],
) -> tuple[list[ElectricalGraphNode], list[ElectricalGraphEdge]] | None:
    if not _is_overall_oneline_page(page):
        return None

    source_ref = _overall_hv_yard_source(page)
    switchgear_candidates = _overall_switchgear_candidates(page)
    mv_switchgear = next((candidate for candidate in switchgear_candidates if "MSWG" in candidate["tag"]), None)
    generators = _generator_feeder_equipment(page)
    generator = generators[0] if generators else None
    eps_candidates = [
        candidate
        for candidate in switchgear_candidates
        if "SWG" in candidate["tag"] and "MSWG" not in candidate["tag"]
    ]
    eps_switchgear = None
    if generator is not None and eps_candidates:
        generator_center = _center_of_span(generator["span"])
        below_generator = [
            candidate
            for candidate in eps_candidates
            if _center_of_span(candidate["span"])["y"] >= generator_center["y"]
        ]
        eps_switchgear = min(
            below_generator or eps_candidates,
            key=lambda candidate: abs(_center_of_span(candidate["span"])["x"] - generator_center["x"]) + abs(_center_of_span(candidate["span"])["y"] - generator_center["y"]),
        )

    if source_ref is None or mv_switchgear is None or generator is None or eps_switchgear is None:
        return None

    nodes: list[ElectricalGraphNode] = []
    edges: list[ElectricalGraphEdge] = []

    source_span = source_ref["span"]
    hv_yard = ElectricalGraphNode(
        id=_node_id("line_tag", page.id, f"overall_hv_yard_{source_ref['tag']}_{int(source_span.x)}"),
        kind="line_tag",
        tag=source_ref["tag"],
        system="ELEC",
        sourceFileId=page.sourceFileId,
        sourcePageId=page.id,
        page=page.page,
        bounds=span_bounds(source_span),
        sourceEvidenceIds=[f"{page.id}:overall-hv-yard-source:{source_ref['index']}"],
        confidence=0.94,
        metadata={
            "sourcePath": source_paths.get(page.sourceFileId),
            "source": "overall_oneline_external_source",
            "sheetRef": source_ref.get("sheetRef", ""),
            "equipmentClass": "switchgear",
            "discipline": "Electrical",
            "ruleset": ELECTRICAL_RULESET,
        },
    )
    nodes.append(hv_yard)

    mv_span = mv_switchgear["span"]
    mv_node = ElectricalGraphNode(
        id=_node_id("line_tag", page.id, f"overall_mv_{mv_switchgear['tag']}_{int(mv_span.x)}"),
        kind="line_tag",
        tag=mv_switchgear["tag"],
        system="ELEC",
        sourceFileId=page.sourceFileId,
        sourcePageId=page.id,
        page=page.page,
        bounds=span_bounds(mv_span),
        sourceEvidenceIds=[f"{page.id}:overall-mv-switchgear:{mv_switchgear['index']}"],
        confidence=0.96,
        metadata={
            "sourcePath": source_paths.get(page.sourceFileId),
            "source": "overall_oneline_mv_switchgear",
            "equipmentClass": "main_switchgear",
            "discipline": "Electrical",
            "ruleset": ELECTRICAL_RULESET,
        },
    )
    nodes.append(mv_node)
    edges.append(
        ElectricalGraphEdge(
            id=_edge_id("attached_to_line", mv_node.id, hv_yard.id),
            kind="attached_to_line",
            sourceId=mv_node.id,
            targetId=hv_yard.id,
            label=hv_yard.tag,
            lineTag=hv_yard.tag,
            system="ELEC",
            sourceEvidenceIds=[*mv_node.sourceEvidenceIds, *hv_yard.sourceEvidenceIds],
            confidence=0.94,
            status="confirmed",
            metadata={"source": "overall_oneline_hv_yard_feed", "discipline": "Electrical", "ruleset": ELECTRICAL_RULESET},
        )
    )

    generator_span = generator["span"]
    generator_node = ElectricalGraphNode(
        id=_node_id("equipment", page.id, f"overall_generator_{generator['tag']}_{int(generator_span.x)}"),
        kind="equipment",
        tag=generator["tag"],
        system="ELEC",
        sourceFileId=page.sourceFileId,
        sourcePageId=page.id,
        page=page.page,
        bounds=span_bounds(generator_span),
        sourceEvidenceIds=[f"{page.id}:overall-generator:{generator.get('index', 0)}"],
        confidence=0.96,
        metadata={
            "sourcePath": source_paths.get(page.sourceFileId),
            "source": "overall_oneline_generator_root",
            "equipmentClass": "generator",
            "discipline": "Electrical",
            "ruleset": ELECTRICAL_RULESET,
        },
    )
    nodes.append(generator_node)

    eps_span = eps_switchgear["span"]
    eps_node = ElectricalGraphNode(
        id=_node_id("line_tag", page.id, f"overall_eps_{eps_switchgear['tag']}_{int(eps_span.x)}"),
        kind="line_tag",
        tag=eps_switchgear["tag"],
        system="ELEC",
        sourceFileId=page.sourceFileId,
        sourcePageId=page.id,
        page=page.page,
        bounds=span_bounds(eps_span),
        sourceEvidenceIds=[f"{page.id}:overall-eps-switchgear:{eps_switchgear['index']}"],
        confidence=0.96,
        metadata={
            "sourcePath": source_paths.get(page.sourceFileId),
            "source": "overall_oneline_eps_switchgear",
            "equipmentClass": "switchgear",
            "discipline": "Electrical",
            "ruleset": ELECTRICAL_RULESET,
        },
    )
    nodes.append(eps_node)
    edges.append(
        ElectricalGraphEdge(
            id=_edge_id("attached_to_line", eps_node.id, generator_node.id),
            kind="attached_to_line",
            sourceId=eps_node.id,
            targetId=generator_node.id,
            label=generator_node.tag,
            lineTag=generator_node.tag,
            system="ELEC",
            sourceEvidenceIds=[*eps_node.sourceEvidenceIds, *generator_node.sourceEvidenceIds],
            confidence=0.94,
            status="confirmed",
            metadata={"source": "overall_oneline_generator_feed", "discipline": "Electrical", "ruleset": ELECTRICAL_RULESET},
        )
    )
    return nodes, edges


def _is_overall_oneline_page(page: PageEvidence) -> bool:
    text = " ".join(span_text(span).upper() for span in page.textSpans[:500])
    return "OVERALL" in text and re.search(r"\bONE[- ]?LINE|ONELINE\b", text) is not None


def _overall_hv_yard_source(page: PageEvidence) -> dict[str, Any] | None:
    for index, span in enumerate(page.textSpans):
        text = span_text(span).upper()
        if "HV" not in text or "YARD" not in text or "SWG" not in text:
            continue
        nearby = [
            candidate
            for candidate in page.textSpans
            if abs(_center_of_span(candidate)["x"] - _center_of_span(span)["x"]) <= 160.0
            and -80.0 <= candidate.y - span.y <= 90.0
        ]
        nearby_text = " ".join(span_text(candidate).upper() for candidate in nearby)
        return {
            "tag": "HV YARD SWG",
            "span": span,
            "index": index,
            "sheetRef": _first_match(EXTERNAL_DRAWING_REF_RE, nearby_text),
        }
    return None


def _overall_switchgear_candidates(page: PageEvidence) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, span in enumerate(page.textSpans):
        for match in SWITCHGEAR_RE.finditer(span_text(span).upper()):
            tag = _normalize_tag(match.group(0))
            if tag in seen:
                continue
            seen.add(tag)
            candidates.append({"tag": tag, "span": span, "index": index})
    return sorted(candidates, key=lambda item: (_center_of_span(item["span"])["y"], _center_of_span(item["span"])["x"], item["tag"]))


def _generator_feeder_tree(
    page: PageEvidence,
    source_paths: dict[str, str],
) -> tuple[list[ElectricalGraphNode], list[ElectricalGraphEdge]] | None:
    all_incoming_refs = _incoming_power_references(page, max_y_ratio=0.45)
    generators = _generator_feeder_equipment(page)
    if len(generators) < 1:
        return None
    first_generator_y = min((_center_of_span(generator["span"])["y"] for generator in generators), default=0.0)
    incoming_refs = [
        ref
        for ref in all_incoming_refs
        if _center_of_span(ref["span"])["y"] < first_generator_y + page.height * 0.2
    ]
    last_incoming_y = max((_center_of_span(ref["span"])["y"] for ref in incoming_refs), default=first_generator_y)
    owner_min_y = max(first_generator_y + 90.0, last_incoming_y + 120.0)
    owner_candidates = [
        owner
        for owner in _switchgear_feeder_owners(page, max_y_ratio=0.58, require_ofci=False, min_center_y=owner_min_y)
        if ("SWG" in owner["tag"] or "SS" in owner["tag"])
        and "MDP" not in owner["tag"]
    ]
    owners = [owner for owner in owner_candidates if "SWG" in owner["tag"]] or owner_candidates
    outbound_targets = _bottom_arrow_targets(page, min_y_ratio=0.32)
    if len(incoming_refs) < 1 or len(owners) < 1 or len(outbound_targets) < 1:
        return None

    nodes: list[ElectricalGraphNode] = []
    edges: list[ElectricalGraphEdge] = []
    parent_nodes: list[tuple[dict[str, Any], ElectricalGraphNode]] = []
    generator_nodes: list[tuple[dict[str, Any], ElectricalGraphNode]] = []
    owner_nodes: list[ElectricalGraphNode] = []

    for index, ref in enumerate(_dedupe_incoming_references(incoming_refs)):
        span = ref["span"]
        upstream_tag = _normalize_tag(str(ref.get("upstreamTag") or ""))
        display_tag = upstream_tag or ref["sheetRef"]
        node = ElectricalGraphNode(
            id=_node_id("line_tag", page.id, f"generator_incoming_{index}_{display_tag}_{int(span.x)}"),
            kind="line_tag",
            tag=display_tag,
            system="ELEC",
            sourceFileId=page.sourceFileId,
            sourcePageId=page.id,
            page=page.page,
            bounds=span_bounds(span),
            sourceEvidenceIds=[f"{page.id}:generator-incoming-reference:{item_index}" for item_index in ref.get("sourceIndexes", [index])],
            confidence=0.94,
            metadata={
                "sourcePath": source_paths.get(page.sourceFileId),
                "source": "incoming_sheet_reference",
                "upstreamTag": ref.get("upstreamTag", ""),
                "sheetRef": ref.get("sheetRef", ""),
                "discipline": "Electrical",
                "ruleset": ELECTRICAL_RULESET,
            },
        )
        nodes.append(node)
        parent_nodes.append((ref, node))

    for index, generator in enumerate(generators):
        span = generator["span"]
        node = ElectricalGraphNode(
            id=_node_id("equipment", page.id, f"generator_{index}_{generator['tag']}_{int(span.x)}"),
            kind="equipment",
            tag=generator["tag"],
            system="ELEC",
            sourceFileId=page.sourceFileId,
            sourcePageId=page.id,
            page=page.page,
            bounds=span_bounds(span),
            sourceEvidenceIds=[f"{page.id}:generator-feeder-equipment:{index}"],
            confidence=0.94,
            metadata={
                "sourcePath": source_paths.get(page.sourceFileId),
                "source": "generator_feeder_equipment",
                "equipmentClass": "generator",
                "discipline": "Electrical",
                "ruleset": ELECTRICAL_RULESET,
            },
        )
        nodes.append(node)
        generator_nodes.append((generator, node))
        parent = _nearest_reference_for_owner(generator, parent_nodes)
        if parent is not None:
            edges.append(
                ElectricalGraphEdge(
                    id=_edge_id("power_source", node.id, parent.id),
                    kind="power_source",
                    sourceId=node.id,
                    targetId=parent.id,
                    label=parent.tag,
                    lineTag=parent.tag,
                    system="ELEC",
                    sourceEvidenceIds=[*node.sourceEvidenceIds, *parent.sourceEvidenceIds],
                    confidence=0.94,
                    status="confirmed",
                    metadata={"source": "incoming_reference_feeds_generator_component", "discipline": "Electrical", "ruleset": ELECTRICAL_RULESET},
                )
            )

    for index, owner in enumerate(owners):
        span = owner["span"]
        node = ElectricalGraphNode(
            id=_node_id("line_tag", page.id, f"generator_switchgear_owner_{index}_{owner['tag']}_{int(span.x)}"),
            kind="line_tag",
            tag=owner["tag"],
            system="ELEC",
            sourceFileId=page.sourceFileId,
            sourcePageId=page.id,
            page=page.page,
            bounds=span_bounds(span),
            sourceEvidenceIds=[f"{page.id}:generator-switchgear-owner:{index}"],
            confidence=0.96,
            metadata={
                "sourcePath": source_paths.get(page.sourceFileId),
                "source": "switchgear_ofci_owner_tag",
                "discipline": "Electrical",
                "ruleset": ELECTRICAL_RULESET,
            },
        )
        nodes.append(node)
        owner_nodes.append(node)
        generator = _nearest_reference_for_owner(owner, generator_nodes)
        if generator is not None:
            edges.append(
                ElectricalGraphEdge(
                    id=_edge_id("attached_to_line", node.id, generator.id),
                    kind="attached_to_line",
                    sourceId=node.id,
                    targetId=generator.id,
                    label=generator.tag,
                    lineTag=generator.tag,
                    system="ELEC",
                    sourceEvidenceIds=[*node.sourceEvidenceIds, *generator.sourceEvidenceIds],
                    confidence=0.94,
                    status="confirmed",
                    metadata={"source": "generator_feeds_switchgear_owner", "discipline": "Electrical", "ruleset": ELECTRICAL_RULESET},
                )
            )

    seen_targets: set[tuple[str, int]] = set()
    for index, target in enumerate(outbound_targets):
        span = target["span"]
        owner = _nearest_owner_for_target(target, owner_nodes)
        if owner is None:
            continue
        dedupe_key = (target["tag"], int(_center_of_span(span)["x"] // 20))
        if dedupe_key in seen_targets:
            continue
        seen_targets.add(dedupe_key)
        node = ElectricalGraphNode(
            id=_node_id("line_tag", page.id, f"generator_outbound_{index}_{target['tag']}_{int(span.x)}"),
            kind="line_tag",
            tag=target["tag"],
            system="ELEC",
            sourceFileId=page.sourceFileId,
            sourcePageId=page.id,
            page=page.page,
            bounds=span_bounds(span),
            sourceEvidenceIds=[f"{page.id}:generator-bottom-arrow-target:{index}"],
            confidence=0.92,
            metadata={
                "sourcePath": source_paths.get(page.sourceFileId),
                "source": "bottom_arrow_target",
                "discipline": "Electrical",
                "ruleset": ELECTRICAL_RULESET,
            },
        )
        nodes.append(node)
        edges.append(
            ElectricalGraphEdge(
                id=_edge_id("attached_to_line", node.id, owner.id),
                kind="attached_to_line",
                sourceId=node.id,
                targetId=owner.id,
                label=owner.tag,
                lineTag=owner.tag,
                system="ELEC",
                sourceEvidenceIds=[*node.sourceEvidenceIds, *owner.sourceEvidenceIds],
                confidence=0.92,
                status="confirmed",
                metadata={"source": "bottom_arrow_target_under_switchgear_owner", "discipline": "Electrical", "ruleset": ELECTRICAL_RULESET},
            )
        )

    if not any(edge.metadata.get("source") == "generator_feeds_switchgear_owner" for edge in edges):
        return None
    if not any(edge.metadata.get("source") == "bottom_arrow_target_under_switchgear_owner" for edge in edges):
        return None
    return nodes, edges


def _switchgear_feeder_tree(
    page: PageEvidence,
    source_paths: dict[str, str],
) -> tuple[list[ElectricalGraphNode], list[ElectricalGraphEdge]] | None:
    incoming_refs = _incoming_switchgear_references(page)
    owners = _switchgear_feeder_owners(page)
    outbound_targets = _bottom_arrow_targets(page)
    if len(incoming_refs) < 1 or len(owners) < 1 or len(outbound_targets) < 1:
        return None

    nodes: list[ElectricalGraphNode] = []
    edges: list[ElectricalGraphEdge] = []
    parent_nodes: list[tuple[dict[str, Any], ElectricalGraphNode]] = []
    owner_nodes: list[ElectricalGraphNode] = []

    for index, ref in enumerate(_dedupe_incoming_references(incoming_refs)):
        span = ref["span"]
        upstream_tag = _normalize_tag(str(ref.get("upstreamTag") or ""))
        display_tag = upstream_tag or ref["sheetRef"]
        node = ElectricalGraphNode(
            id=_node_id("line_tag", page.id, f"incoming_{index}_{display_tag}_{int(span.x)}"),
            kind="line_tag",
            tag=display_tag,
            system="ELEC",
            sourceFileId=page.sourceFileId,
            sourcePageId=page.id,
            page=page.page,
            bounds=span_bounds(span),
            sourceEvidenceIds=[f"{page.id}:incoming-reference:{item_index}" for item_index in ref.get("sourceIndexes", [index])],
            confidence=0.94,
            metadata={
                "sourcePath": source_paths.get(page.sourceFileId),
                "source": "incoming_sheet_reference",
                "upstreamTag": ref.get("upstreamTag", ""),
                "sheetRef": ref.get("sheetRef", ""),
                "discipline": "Electrical",
                "ruleset": ELECTRICAL_RULESET,
            },
        )
        nodes.append(node)
        parent_nodes.append((ref, node))

    for index, owner in enumerate(owners):
        span = owner["span"]
        node = ElectricalGraphNode(
            id=_node_id("line_tag", page.id, f"switchgear_owner_{index}_{owner['tag']}_{int(span.x)}"),
            kind="line_tag",
            tag=owner["tag"],
            system="ELEC",
            sourceFileId=page.sourceFileId,
            sourcePageId=page.id,
            page=page.page,
            bounds=span_bounds(span),
            sourceEvidenceIds=[f"{page.id}:switchgear-feeder-owner:{index}"],
            confidence=0.96,
            metadata={
                "sourcePath": source_paths.get(page.sourceFileId),
                "source": "switchgear_ofci_owner_tag",
                "discipline": "Electrical",
                "ruleset": ELECTRICAL_RULESET,
            },
        )
        nodes.append(node)
        owner_nodes.append(node)
        parent = _nearest_reference_for_owner(owner, parent_nodes)
        if parent is not None:
            edges.append(
                ElectricalGraphEdge(
                    id=_edge_id("attached_to_line", node.id, parent.id),
                    kind="attached_to_line",
                    sourceId=node.id,
                    targetId=parent.id,
                    label=parent.tag,
                    lineTag=parent.tag,
                    system="ELEC",
                    sourceEvidenceIds=[*node.sourceEvidenceIds, *parent.sourceEvidenceIds],
                    confidence=0.94,
                    status="confirmed",
                    metadata={"source": "incoming_reference_feeds_switchgear_owner", "discipline": "Electrical", "ruleset": ELECTRICAL_RULESET},
                )
            )

    seen_targets: set[tuple[str, int]] = set()
    for index, target in enumerate(outbound_targets):
        span = target["span"]
        owner = _nearest_owner_for_target(target, owner_nodes)
        if owner is None:
            continue
        dedupe_key = (target["tag"], int(_center_of_span(span)["x"] // 20))
        if dedupe_key in seen_targets:
            continue
        seen_targets.add(dedupe_key)
        node = ElectricalGraphNode(
            id=_node_id("line_tag", page.id, f"outbound_{index}_{target['tag']}_{int(span.x)}"),
            kind="line_tag",
            tag=target["tag"],
            system="ELEC",
            sourceFileId=page.sourceFileId,
            sourcePageId=page.id,
            page=page.page,
            bounds=span_bounds(span),
            sourceEvidenceIds=[f"{page.id}:bottom-arrow-target:{index}"],
            confidence=0.92,
            metadata={
                "sourcePath": source_paths.get(page.sourceFileId),
                "source": "bottom_arrow_target",
                "discipline": "Electrical",
                "ruleset": ELECTRICAL_RULESET,
            },
        )
        nodes.append(node)
        edges.append(
            ElectricalGraphEdge(
                id=_edge_id("attached_to_line", node.id, owner.id),
                kind="attached_to_line",
                sourceId=node.id,
                targetId=owner.id,
                label=owner.tag,
                lineTag=owner.tag,
                system="ELEC",
                sourceEvidenceIds=[*node.sourceEvidenceIds, *owner.sourceEvidenceIds],
                confidence=0.92,
                status="confirmed",
                metadata={"source": "bottom_arrow_target_under_switchgear_owner", "discipline": "Electrical", "ruleset": ELECTRICAL_RULESET},
            )
        )

    child_edges = [edge for edge in edges if edge.metadata.get("source") == "bottom_arrow_target_under_switchgear_owner"]
    if len(child_edges) < 1:
        return None
    connected_node_ids = {edge.sourceId for edge in edges} | {edge.targetId for edge in edges}
    nodes = [node for node in nodes if node.metadata.get("source") != "incoming_sheet_reference" or node.id in connected_node_ids]
    return nodes, edges


def _dedupe_incoming_references(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[tuple[int, dict[str, Any]]]] = {}
    for index, ref in enumerate(refs):
        key = (str(ref.get("sheetRef") or ""), str(ref.get("upstreamTag") or ""))
        grouped.setdefault(key, []).append((index, ref))

    merged: list[dict[str, Any]] = []
    for (_sheet_ref, _upstream_tag), items in grouped.items():
        first = items[0][1]
        if len(items) == 1:
            merged.append({**first, "sourceIndexes": [items[0][0]]})
            continue
        bounds = _union_bounds([item["span"] for _index, item in items])
        merged.append(
            {
                **first,
                "span": TextSpan(
                    str(first.get("sheetRef") or ""),
                    bounds["x"],
                    bounds["y"],
                    bounds["width"],
                    bounds["height"],
                ),
                "sourceIndexes": [index for index, _item in items],
            }
        )
    return sorted(merged, key=lambda item: (_center_of_span(item["span"])["x"], item["sheetRef"]))


def _incoming_switchgear_references(page: PageEvidence) -> list[dict[str, Any]]:
    return _incoming_power_references(page, max_y_ratio=0.18)


def _incoming_power_references(page: PageEvidence, *, max_y_ratio: float) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for span in page.textSpans:
        text = span_text(span).upper()
        if not SHEET_REF_RE.fullmatch(text):
            continue
        if span.y > page.height * max_y_ratio:
            continue
        nearby = [
            candidate
            for candidate in page.textSpans
            if abs(_center_of_span(candidate)["x"] - _center_of_span(span)["x"]) <= 150.0
            and -96.0 <= candidate.y - span.y <= 24.0
        ]
        nearby_text = " ".join(span_text(candidate).upper() for candidate in nearby)
        if "FROM" not in nearby_text or ("SEE DRAWING" not in nearby_text and "VIA" not in nearby_text):
            continue
        refs.append({"sheetRef": text, "upstreamTag": _first_match(SWITCHGEAR_RE, nearby_text), "span": span})
    return sorted(refs, key=lambda item: (_center_of_span(item["span"])["x"], item["sheetRef"]))


def _generator_feeder_equipment(page: PageEvidence) -> list[dict[str, Any]]:
    generators: list[dict[str, Any]] = []
    used: set[str] = set()
    for span in page.textSpans:
        text = span_text(span).upper()
        if not GENERATOR_TAG_RE.fullmatch(text):
            continue
        if span.y > page.height * 0.4:
            continue
        if text in used:
            continue
        used.add(text)
        generators.append({"tag": _normalize_tag(text), "span": span})
    return sorted(generators, key=lambda item: (_center_of_span(item["span"])["x"], item["tag"]))


def _switchgear_feeder_owners(
    page: PageEvidence,
    *,
    max_y_ratio: float = 0.25,
    require_ofci: bool = True,
    min_center_y: float | None = None,
) -> list[dict[str, Any]]:
    owners: list[dict[str, Any]] = []
    used: set[str] = set()
    for span in page.textSpans:
        text = span_text(span).upper()
        if not SWITCHGEAR_RE.fullmatch(text):
            continue
        if span.y > page.height * max_y_ratio:
            continue
        if min_center_y is not None and _center_of_span(span)["y"] < min_center_y:
            continue
        if text in used:
            continue
        if require_ofci and _nearest_text_span(page.textSpans, span, "(OFCI)", max_dx=140.0, max_dy=48.0) is None:
            continue
        used.add(text)
        owners.append({"tag": text, "span": span})
    return sorted(owners, key=lambda item: (_center_of_span(item["span"])["x"], item["tag"]))


def _bottom_arrow_targets(page: PageEvidence, *, min_y_ratio: float = 0.42) -> list[dict[str, Any]]:
    targets_by_tag: dict[str, dict[str, Any]] = {}
    hyphen_target_re = re.compile(r"\bR-[A-Z0-9]+(?:-[A-Z0-9]+)+\b(?:\s+\([A-Z0-9 ]+\))?", re.IGNORECASE)
    feeder_target_re = re.compile(r"\b" + BUILDING_CODE_PATTERN + r"[A-Z0-9]*(?:MDP|SS|SWG)[A-Z0-9-]*(?:\s*&\s*[A-Z0-9-]+)?\b", re.IGNORECASE)
    for span in page.textSpans:
        text = span_text(span).upper()
        if span.y < page.height * min_y_ratio or span.y > page.height * 0.82:
            continue
        has_to_marker = _has_to_marker_above(page, span)
        hyphen_match = hyphen_target_re.search(text)
        feeder_match = feeder_target_re.search(text)
        if not hyphen_match and not feeder_match:
            continue
        if hyphen_match and not has_to_marker:
            continue
        tag = _normalize_tag((hyphen_match or feeder_match).group(0))
        existing = targets_by_tag.get(tag)
        if existing is None or _target_span_rank(span, has_to_marker) < _target_span_rank(existing["span"], bool(existing.get("hasToMarker"))):
            targets_by_tag[tag] = {"tag": tag, "span": span, "hasToMarker": has_to_marker}
    return sorted(targets_by_tag.values(), key=lambda item: (_center_of_span(item["span"])["x"], _center_of_span(item["span"])["y"], item["tag"]))


def _target_span_rank(span: TextSpan, has_to_marker: bool) -> tuple[int, float]:
    return (0 if has_to_marker else 1, -span.y)


def _has_to_marker_above(page: PageEvidence, span: TextSpan) -> bool:
    center = _center_of_span(span)
    return any(
        span_text(candidate).upper() == "TO"
        and abs(_center_of_span(candidate)["x"] - center["x"]) <= 72.0
        and -34.0 <= candidate.y - span.y <= 4.0
        for candidate in page.textSpans
    )


def _nearest_reference_for_owner(owner: dict[str, Any], parent_nodes: list[tuple[dict[str, Any], ElectricalGraphNode]]) -> ElectricalGraphNode | None:
    if not parent_nodes:
        return None
    owner_x = _center_of_span(owner["span"])["x"]
    return min(parent_nodes, key=lambda item: abs(_center_of_span(item[0]["span"])["x"] - owner_x))[1]


def _nearest_owner_for_target(target: dict[str, Any], owner_nodes: list[ElectricalGraphNode]) -> ElectricalGraphNode | None:
    if not owner_nodes:
        return None
    target_x = _center_of_span(target["span"])["x"]
    return min(owner_nodes, key=lambda node: abs(_center_of_bounds(node.bounds)["x"] - target_x))


def _switchgear_owner_nodes(page: PageEvidence, source_paths: dict[str, str]) -> list[ElectricalGraphNode]:
    nodes: list[ElectricalGraphNode] = []
    used: set[str] = set()
    for index, span in enumerate(page.textSpans):
        text = span_text(span).upper()
        match = SWITCHGEAR_RE.search(text)
        if not match:
            continue
        tag = _normalize_tag(match.group(0))
        owner_class = _switchgear_owner_class(tag)
        if tag in used or not owner_class:
            continue
        if span.y > page.height * 0.42:
            continue
        nearby_ofci = _nearest_text_span(page.textSpans, span, "(OFCI)", max_dx=240.0, max_dy=72.0)
        title_mentions_tag = any(tag in span_text(candidate).upper() for candidate in page.textSpans if candidate.y < page.height * 0.18 and "/" in span_text(candidate))
        if nearby_ofci is None and not title_mentions_tag:
            continue
        evidence = [span]
        if nearby_ofci is not None:
            evidence.append(nearby_ofci)
        label = f"{tag} (OFCI)" if nearby_ofci is not None else tag
        used.add(tag)
        nodes.append(
            ElectricalGraphNode(
                id=_node_id("section", page.id, f"{label}_{index}"),
                kind="section",
                tag=label,
                system="ELEC",
                sourceFileId=page.sourceFileId,
                sourcePageId=page.id,
                page=page.page,
                bounds=_union_bounds(evidence),
                sourceEvidenceIds=[f"{page.id}:switchgear-owner:{index}"],
                confidence=0.92 if nearby_ofci is not None else 0.78,
                metadata={
                    "sourcePath": source_paths.get(page.sourceFileId),
                    "sourceText": " ".join(span.text for span in evidence),
                    "procurement": "OFCI" if nearby_ofci is not None else "",
                    "equipmentClass": owner_class,
                    "source": "switchgear_corner_label",
                },
            )
        )
    return nodes


def _switchgear_section_nodes(page: PageEvidence, source_paths: dict[str, str]) -> list[ElectricalGraphNode]:
    nodes: list[ElectricalGraphNode] = []
    switch_spans = [
        span
        for span in page.textSpans
        if _is_switch_section_label(span_text(span)) and span.y >= page.height * 0.18
    ]
    section_spans = [
        span
        for span in page.textSpans
        if re.fullmatch(r"\(SECTION\s+\d+\)", span_text(span).upper()) and span.y >= page.height * 0.18
    ]
    for index, switch_span in enumerate(switch_spans):
        section_span = min(section_spans, key=lambda span: abs(_center_of_span(span)["x"] - _center_of_span(switch_span)["x"]) + abs(span.y - switch_span.y), default=None)
        if section_span is not None and _span_distance(switch_span, section_span) > 260.0:
            section_span = None
        if section_span is None:
            continue
        section_text = span_text(section_span).upper() if section_span else "SECTION"
        tag = f"{span_text(switch_span).upper()} {section_text}"
        evidence = [switch_span]
        if section_span is not None:
            evidence.append(section_span)
        nodes.append(
            ElectricalGraphNode(
                id=_node_id("section", page.id, f"{tag}_{index}"),
                kind="section",
                tag=tag,
                system="ELEC",
                sourceFileId=page.sourceFileId,
                sourcePageId=page.id,
                page=page.page,
                bounds=_union_bounds(evidence),
                sourceEvidenceIds=[f"{page.id}:switchgear-section:{index}"],
                confidence=0.88 if section_span is not None else 0.68,
                metadata={"sourcePath": source_paths.get(page.sourceFileId), "switch": span_text(switch_span).upper(), "section": section_text},
            )
        )
    return nodes


def _switchgear_transformer_nodes(page: PageEvidence, source_paths: dict[str, str], sections: list[ElectricalGraphNode]) -> list[ElectricalGraphNode]:
    nodes: list[ElectricalGraphNode] = []
    for index, span in enumerate(page.textSpans):
        if span_text(span).upper() != "TRANSFORMER":
            continue
        section = _nearest_bounds(span_bounds(span), sections)
        if section is None or _bounds_distance(span_bounds(span), section) > 420.0:
            continue
        side = str(section.metadata.get("switch") if section else "SW").upper()
        tag = f"{side} TRANSFORMER"
        nodes.append(
            ElectricalGraphNode(
                id=_node_id("equipment", page.id, f"{tag}_{index}"),
                kind="equipment",
                tag=tag,
                system="ELEC",
                sourceFileId=page.sourceFileId,
                sourcePageId=page.id,
                page=page.page,
                bounds=span_bounds(span),
                sourceEvidenceIds=[f"{page.id}:transformer:{index}"],
                confidence=0.82,
                metadata={"sourcePath": source_paths.get(page.sourceFileId), "sourceText": span.text},
            )
        )
    return nodes


def _switchgear_breaker_nodes(
    page: PageEvidence,
    source_paths: dict[str, str],
    sections: list[ElectricalGraphNode],
    transformers: list[ElectricalGraphNode],
) -> list[ElectricalGraphNode]:
    nodes: list[ElectricalGraphNode] = []
    used: set[tuple[int, str]] = set()
    for index, span in enumerate(page.textSpans):
        text = span_text(span).upper()
        if text not in {"BREAKER", "MAIN", "TIE", "GEN"}:
            continue
        cell_spans = [span]
        if text == "MAIN":
            nearby_breaker = _nearest_text_span(page.textSpans, span, "BREAKER", max_dx=80.0, max_dy=32.0)
            if nearby_breaker is not None:
                cell_spans.append(nearby_breaker)
                text = "MAIN BREAKER"
        section_span = _nearest_matching_span(page.textSpans, span, r"\(SECTION\s+\d+\)", max_dx=140.0, max_dy=48.0)
        if section_span is not None:
            cell_spans.append(section_span)
            text = f"{text} {span_text(section_span).upper()}"
        parent_probe_bounds = _union_bounds(cell_spans)
        parent_probe = _nearest_bounds(parent_probe_bounds, transformers) or _nearest_bounds(parent_probe_bounds, sections)
        if parent_probe is None or _bounds_distance(parent_probe_bounds, parent_probe) > 520.0:
            continue
        key = (int(_center_of_span(span)["x"] // 30), text)
        if key in used:
            continue
        used.add(key)
        parent = parent_probe
        if parent is not None and _center_of_bounds(parent.bounds)["x"] < _center_of_bounds(_union_bounds(cell_spans))["x"] - 900:
            parent = _nearest_bounds(_union_bounds(cell_spans), sections)
        nodes.append(
            ElectricalGraphNode(
                id=_node_id("device", page.id, f"{text}_{index}"),
                kind="device",
                tag=text,
                system="ELEC",
                sourceFileId=page.sourceFileId,
                sourcePageId=page.id,
                page=page.page,
                bounds=_union_bounds(cell_spans),
                sourceEvidenceIds=[f"{page.id}:switchgear-device:{index}"],
                confidence=0.78,
                metadata={"sourcePath": source_paths.get(page.sourceFileId), "sourceText": " ".join(span.text for span in cell_spans)},
            )
        )
    return nodes


def _is_electrical_page(page: PageEvidence, source_paths: dict[str, str]) -> bool:
    return _electrical_page_profile(page, source_paths) is not None


def _is_electrical_hierarchy_page(page: PageEvidence, source_paths: dict[str, str]) -> bool:
    profile = _electrical_page_profile(page, source_paths)
    return profile is not None and profile.get("drawingType") == "one_line"


def _electrical_page_profile(page: PageEvidence, source_paths: dict[str, str]) -> dict[str, Any] | None:
    source_name = Path(source_paths.get(page.sourceFileId, page.sourceFileId)).stem.upper()
    text = " ".join(span.text for span in page.textSpans[:500]).upper()
    reasons: list[str] = []
    if re.search(r"\b(ELEC|ELECTRICAL|POWER|ONE[- ]?LINE|SINGLE[- ]?LINE|EPMS|SWITCHGEAR)\b", source_name):
        reasons.append("source_name")
    if re.search(r"\b(480Y/277V|13\.8KV|4160V|SWITCHGEAR|SWGR|SWBD|EPMS|FEEDER|CIRCUIT|ONE[- ]?LINE|SINGLE[- ]?LINE|ONELINE)\b", text):
        reasons.append("electrical_keywords")
    if SWITCHGEAR_RE.search(text) or BUS_RE.search(text):
        reasons.append("electrical_tags")
    if not reasons:
        return None
    confidence = min(0.96, 0.58 + 0.14 * len(set(reasons)))
    return {
        "pageId": page.id,
        "sourceFileId": page.sourceFileId,
        "page": page.page,
        "discipline": "Electrical",
        "ruleset": ELECTRICAL_RULESET,
        "drawingType": _classify_electrical_page(page),
        "confidence": round(confidence, 2),
        "reasons": sorted(set(reasons)),
    }


def _classify_electrical_page(page: PageEvidence) -> str:
    text = " ".join(span.text for span in page.textSpans[:500]).upper()
    if _is_electrical_guide_page_text(text):
        return "guide"
    if re.search(r"\b(PANEL\s+SCHEDULE|LOAD\s+SCHEDULE|CIRCUIT\s+SCHEDULE|FEEDER\s+SCHEDULES?|SCHEDULES?)\b", text):
        return "panel_schedule"
    if re.search(r"\b(TEMP\s+POWER\s+PLAN|POWER\s+PLAN|LIGHTING\s+PLAN|SITE\s*-\s*OVERALL|FLOOR\s+PLAN)\b", text):
        return "power_plan"
    if re.search(r"\b(ONE[- ]?LINE|SINGLE[- ]?LINE|ONELINE)\b", text):
        return "one_line"
    if re.search(r"\b(RISER|FEEDER\s+RISER)\b", text):
        return "riser"
    if re.search(r"\b(CONTROL|SCHEMATIC|LADDER)\b", text):
        return "control_schematic"
    if _looks_like_one_line_content(text):
        return "one_line"
    return "electrical"


def _looks_like_one_line_content(text: str) -> bool:
    return any(node in text for node in ("SWITCHGEAR", "SWG", "MDP", "TRANSFORMER", "FEEDER"))


def _is_electrical_guide_page_text(text: str) -> bool:
    guide_markers = [
        "ABBREVIATIONS",
        "EQUIPMENT TAGGING LEGEND",
        "POWER ONE-LINE LEGEND",
        "WIRING DEVICES LEGEND",
        "BUILDING GROUNDING GRID LEGEND",
        "DETAIL INDICATOR LEGEND",
        "GENERAL NOTES",
        "SCOPE",
    ]
    hits = sum(marker in text for marker in guide_markers)
    return "ABBREVIATIONS" in text and hits >= 3


def _primary_line_node(nodes: list[ElectricalGraphNode]) -> ElectricalGraphNode | None:
    line_nodes = [node for node in nodes if node.kind == "line_tag"]
    if not line_nodes:
        return None
    return min(line_nodes, key=lambda node: (_primary_rank(node.tag), node.bounds["y"], node.bounds["x"]))


def _primary_rank(tag: str) -> int:
    upper = tag.upper()
    if "MSWG" in upper or "SWG" in upper:
        return 0
    if "SS" in upper:
        return 1
    if "MDP" in upper:
        return 2
    if "BUS" in upper:
        return 3
    return 4


def _target_after_to(window: list[TextSpan]) -> str:
    for span in window[1:]:
        text = span_text(span).upper()
        if text in {"SEE", "DRAWING", "OS-OPTIONAL", "LR-LEGALLY", "REQUIRED", "STANDBY"}:
            continue
        if SHEET_REF_RE.search(text):
            continue
        match = TARGET_EQUIPMENT_RE.search(text)
        if match:
            return _normalize_tag(match.group(0))
    return ""


def _metrics(
    nodes: list[ElectricalGraphNode],
    edges: list[ElectricalGraphEdge],
    pages: list[PageEvidence],
    source_paths: dict[str, str],
    document_profile: dict[str, Any],
    cross_page_dedupe: dict[str, Any] | None = None,
) -> dict[str, Any]:
    page_classifications: dict[str, int] = {}
    page_profiles: list[dict[str, Any]] = []
    for page in pages:
        profile = _electrical_page_profile(page, source_paths)
        if profile is None:
            continue
        page_profiles.append(profile)
        page_class = str(profile["drawingType"])
        page_classifications[page_class] = page_classifications.get(page_class, 0) + 1
    active_rulesets = sorted({str(profile["ruleset"]) for profile in page_profiles})
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "discipline": "Electrical" if active_rulesets else "",
        "activeRulesets": active_rulesets,
        "pageProfiles": page_profiles,
        "equipmentNodes": sum(node.kind == "equipment" for node in nodes),
        "instrumentNodes": 0,
        "deviceNodes": sum(node.kind == "device" for node in nodes),
        "sectionNodes": sum(node.kind == "section" for node in nodes),
        "lineTagNodes": sum(node.kind == "line_tag" for node in nodes),
        "continuationNodes": sum(node.kind == "continuation" for node in nodes),
        "circuitNodes": sum(node.kind == "circuit" for node in nodes),
        "attachmentEdges": sum(edge.kind == "attached_to_line" for edge in edges),
        "deviceEdges": sum(edge.kind in {"device_on_line", "device_on_equipment"} for edge in edges),
        "switchgearHierarchyEdges": sum(edge.kind in {"equipment_on_section", "feeds_panel"} for edge in edges),
        "panelScheduleEdges": sum(edge.kind in {"panel_schedule_feeds", "panel_circuit"} for edge in edges),
        "continuationEdges": sum(edge.kind == "continues_to" for edge in edges),
        "lineworkBackedRelationships": sum(edge.metadata.get("source") == "linework_geometry" for edge in edges),
        "enclosureBackedRelationships": sum(edge.metadata.get("source") == "enclosure_containment" for edge in edges),
        "pageClassifications": page_classifications,
        "documentGuide": document_profile["guide"],
        "documentProfile": {key: value for key, value in document_profile.items() if key != "guide"},
        "crossPageDedupe": cross_page_dedupe
        or {"mergedDuplicateTags": 0, "mergedDuplicateNodes": 0, "resolvedCompoundTargets": 0, "compoundTargets": 0},
    }


def _document_profile(pages: list[PageEvidence], source_paths: dict[str, str]) -> dict[str, Any]:
    guide = _document_guide(pages, source_paths)
    guide_abbreviations = guide.get("abbreviations") if isinstance(guide.get("abbreviations"), dict) else {}
    component_codes = {
        code: str(guide_abbreviations.get(code) or _default_component_description(code))
        for code in GUIDE_ABBREVIATION_CODES
        if code in guide_abbreviations or _default_component_description(code)
    }
    return {
        "guide": guide,
        "sourcePageIds": guide["sourcePageIds"],
        "equipmentTagSchema": guide["equipmentTagSchema"] or EQUIPMENT_TAG_SCHEMA_FIELDS.copy(),
        "equipmentComponentCodes": dict(sorted(component_codes.items())),
        "oneLineLegendTerms": guide["oneLineLegendTerms"],
    }


def _default_component_description(code: str) -> str:
    return {
        "ATS": "AUTOMATIC TRANSFER SWITCH",
        "GEN": "GENERATOR",
        "LCP": "LIGHTING CONTROL PANEL",
        "MCC": "MOTOR CONTROL CENTER",
        "MDP": "MAIN DISTRIBUTION PANEL",
        "MSWG": "MAIN SWITCHGEAR",
        "PNL": "PANEL",
        "PP": "POWER PANEL",
        "SS": "SUBSTATION",
        "SWBD": "SWITCHBOARD",
        "SWG": "SWITCHGEAR",
        "SWGR": "SWITCHGEAR",
        "TR": "TRANSFORMER",
        "TX": "TRANSFORMER",
        "UPS": "UNINTERRUPTIBLE POWER SUPPLY",
        "VFD": "VARIABLE FREQUENCY DRIVE",
        "XFMR": "TRANSFORMER",
    }.get(code, "")


def _document_guide(pages: list[PageEvidence], source_paths: dict[str, str]) -> dict[str, Any]:
    guide_pages = [
        page
        for page in sorted(pages, key=lambda item: (item.sourceFileId, item.page, item.id))
        if (_electrical_page_profile(page, source_paths) or {}).get("drawingType") == "guide"
    ]
    abbreviations: dict[str, str] = {}
    equipment_schema: list[str] = []
    one_line_terms: set[str] = set()
    for page in guide_pages:
        abbreviations.update(_guide_abbreviations(page))
        for field_name in _guide_equipment_tag_schema(page):
            if field_name not in equipment_schema:
                equipment_schema.append(field_name)
        one_line_terms.update(_guide_one_line_terms(page))
    return {
        "sourcePageIds": [page.id for page in guide_pages],
        "sourcePages": [{"sourceFileId": page.sourceFileId, "page": page.page, "pageId": page.id} for page in guide_pages],
        "abbreviations": dict(sorted(abbreviations.items())),
        "equipmentTagSchema": equipment_schema,
        "oneLineLegendTerms": sorted(one_line_terms),
    }


def _guide_abbreviations(page: PageEvidence) -> dict[str, str]:
    abbreviations: dict[str, str] = {}
    for span in page.textSpans:
        code = span_text(span).upper().strip(" .")
        if code not in GUIDE_ABBREVIATION_CODES:
            continue
        phrase = _guide_abbreviation_phrase_for_code_span(page, span)
        if phrase:
            abbreviations[code] = phrase

    rows = _guide_text_rows(page)
    for row in rows:
        text = re.sub(r"\s+", " ", row).strip().upper()
        match = re.match(r"^([A-Z][A-Z0-9/.-]{1,8})\s+(.{3,})$", text)
        if not match:
            continue
        code, phrase = match.groups()
        if code not in GUIDE_ABBREVIATION_CODES or code in abbreviations:
            continue
        phrase = _clean_guide_abbreviation_phrase(phrase)
        if not phrase:
            continue
        abbreviations[code] = phrase
    return abbreviations


def _guide_abbreviation_phrase_for_code_span(page: PageEvidence, code_span: TextSpan) -> str:
    code_center_y = _center_of_span(code_span)["y"]
    same_row = [
        span
        for span in page.textSpans
        if span is not code_span
        and abs(_center_of_span(span)["y"] - code_center_y) <= max(6.0, code_span.height * 0.75)
        and 0.0 < span.x - code_span.x <= 340.0
    ]
    for candidate in sorted(same_row, key=lambda item: item.x):
        text = span_text(candidate).upper()
        if not text:
            continue
        if text.strip(" .") in GUIDE_ABBREVIATION_CODES:
            continue
        phrase = _clean_guide_abbreviation_phrase(text)
        if phrase:
            return phrase
    return ""


def _clean_guide_abbreviation_phrase(phrase: str) -> str:
    cleaned = re.sub(r"\s+", " ", phrase).strip(" -").upper()
    if not cleaned:
        return ""
    if not re.search(r"[A-Z]", cleaned):
        return ""
    if "LEGEND" in cleaned or "NOTES" in cleaned:
        return ""
    if re.fullmatch(r"[A-Z0-9/().#\"' -]{1,5}", cleaned):
        return ""
    return cleaned


def _guide_text_rows(page: PageEvidence) -> list[str]:
    row_buckets: dict[int, list[TextSpan]] = {}
    for span in page.textSpans:
        row_buckets.setdefault(int(span.y // 8.0), []).append(span)
    rows: list[str] = []
    for _bucket, spans in sorted(row_buckets.items()):
        row_text = " ".join(span_text(span) for span in sorted(spans, key=lambda item: item.x) if span_text(span))
        if row_text:
            rows.append(row_text)
    return rows


def _guide_equipment_tag_schema(page: PageEvidence) -> list[str]:
    text = " ".join(_guide_text_rows(page)).upper()
    if "EQUIPMENT TAGGING LEGEND" not in text:
        return []
    fields = [field_name for field_name in EQUIPMENT_TAG_SCHEMA_FIELDS if field_name in text]
    return fields or EQUIPMENT_TAG_SCHEMA_FIELDS.copy()


def _guide_one_line_terms(page: PageEvidence) -> set[str]:
    text = " ".join(_guide_text_rows(page)).upper()
    if "POWER ONE-LINE LEGEND" not in text:
        return set()
    terms = {
        "AC CIRCUIT BREAKER",
        "CIRCUIT BREAKER",
        "CURRENT TRANSFORMER",
        "DIFFERENTIAL RELAY",
        "GENERATOR",
        "GROUND FAULT SENSOR",
        "PROTECTIVE RELAY",
        "SWITCH",
        "TRANSFORMER",
        "VOLTAGE TRANSFORMER",
    }
    return {term for term in terms if term in text}


def _qa(nodes: list[ElectricalGraphNode], edges: list[ElectricalGraphEdge]) -> dict[str, list[str]]:
    attached = {edge.sourceId for edge in edges} | {edge.targetId for edge in edges}
    return {
        "isolatedEquipmentNodes": [node.id for node in nodes if node.kind == "equipment" and node.id not in attached],
        "isolatedInstrumentNodes": [node.id for node in nodes if node.kind == "device" and node.id not in attached],
        "lineTagsWithoutGeometryRelationships": [node.id for node in nodes if node.kind == "line_tag" and node.id not in attached],
        "unresolvedContinuationNodes": [node.id for node in nodes if node.kind == "continuation" and node.id not in attached],
        "proximityOnlyRelationships": [edge.id for edge in edges if str(edge.metadata.get("source") or "").startswith("nearest_")],
    }


def _match_bounds(span: TextSpan, match_index: int) -> BoundsDict:
    return {
        "x": span.x + min(match_index * 20.0, max(span.width - 12.0, 0.0)),
        "y": span.y,
        "width": max(58.0, min(span.width, 210.0)),
        "height": max(span.height, 14.0),
    }


def _union_bounds(spans: list[TextSpan]) -> BoundsDict:
    if not spans:
        return {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    min_x = min(span.x for span in spans)
    min_y = min(span.y for span in spans)
    max_x = max(span.x + span.width for span in spans)
    max_y = max(span.y + span.height for span in spans)
    return {"x": min_x, "y": min_y, "width": max_x - min_x, "height": max_y - min_y}


def span_bounds(span: TextSpan) -> BoundsDict:
    return {"x": span.x, "y": span.y, "width": span.width, "height": span.height}


def _node_metadata(kind: str, tag: str, span: TextSpan, source_path: str | None) -> dict[str, Any]:
    metadata: dict[str, Any] = {"sourceText": span.text, "sourcePath": source_path, "discipline": "Electrical", "ruleset": ELECTRICAL_RULESET}
    equipment_class = _equipment_class(tag)
    device_class = _device_class(tag)
    if kind == "equipment" and equipment_class:
        metadata["equipmentClass"] = equipment_class
    if kind == "device" and device_class:
        metadata["deviceClass"] = device_class
    return metadata


def _equipment_class(tag: str) -> str:
    upper = tag.upper()
    if upper.startswith("VFD"):
        return "vfd"
    if upper.startswith("MCC"):
        return "motor_control_center"
    if upper.startswith(("PANEL", "PNL")):
        return "panel"
    if upper.startswith(("SWBD", "SWGR")) or "SWG" in upper:
        return "switchgear"
    if upper.startswith(("XFMR", "TR", "TX")):
        return "transformer"
    if "KVA" in upper:
        return "transformer"
    return ""


def _device_class(tag: str) -> str:
    upper = tag.upper()
    if re.fullmatch(r"\d{2,5}A", upper):
        return "current_rating"
    if re.fullmatch(r"\d{2,5}AF", upper):
        return "frame_rating"
    if re.fullmatch(r"\d{2,5}AT", upper):
        return "trip_rating"
    if upper.startswith("52"):
        return "circuit_breaker"
    if upper.startswith("87T"):
        return "transformer_differential_relay"
    if upper.startswith("87"):
        return "differential_relay"
    if upper.startswith(("50", "51")):
        return "overcurrent_relay"
    if upper.startswith("86"):
        return "lockout_relay"
    if upper.startswith(("27", "59")):
        return "voltage_relay"
    if upper.startswith("CT"):
        return "current_transformer"
    if upper.startswith(("PT", "VT")):
        return "voltage_transformer"
    if upper.startswith("METER"):
        return "meter"
    return ""


def _switchgear_owner_class(tag: str) -> str:
    upper = tag.upper()
    if "MSWG" in upper:
        return "main_switchgear"
    if "SWG" in upper:
        return "switchgear"
    if "SS" in upper:
        return "substation"
    return ""


def _owner_base_tag(tag: str) -> str:
    return re.sub(r"\s+\(OFCI\)$", "", tag.upper()).strip()


def _is_bus_tag(tag: str) -> bool:
    return "BUS" in tag.upper()


def _is_feeder_line_tag(tag: str, primary_tag: str) -> bool:
    upper = tag.upper()
    if upper == primary_tag.upper() or _is_bus_tag(upper):
        return False
    if any(token in upper for token in ("MDP", "MSWG", "SWG", "SS", "SWBD", "SWGR")):
        return True
    return bool(re.search(r"\b" + BUILDING_CODE_PATTERN + r"[A-Z0-9-]{5,}\b", upper))


def _is_electrical_line_annotation(tag: str) -> bool:
    upper = tag.upper()
    if re.fullmatch(r"\d{2,5}A(?:F|T)?", upper):
        return True
    if re.fullmatch(r"(?:27|32|46|47|49|50|51|52|59|81|86|87)[A-Z]{0,2}(?:-[A-Z0-9]+)?", upper):
        return True
    return upper.startswith(("CT", "PT", "VT", "METER", "BKR", "CB"))


def _center_of_span(span: TextSpan) -> dict[str, float]:
    return {"x": span.x + span.width / 2.0, "y": span.y + span.height / 2.0}


def _span_distance(left: TextSpan, right: TextSpan) -> float:
    return abs(_center_of_span(left)["x"] - _center_of_span(right)["x"]) + abs(_center_of_span(left)["y"] - _center_of_span(right)["y"])


def _center_of_bounds(bounds: BoundsDict) -> dict[str, float]:
    return {"x": bounds["x"] + bounds["width"] / 2.0, "y": bounds["y"] + bounds["height"] / 2.0}


def _same_page_distance(left: ElectricalGraphNode, right: ElectricalGraphNode) -> float:
    return abs((left.bounds["x"] + left.bounds["width"] / 2.0) - (right.bounds["x"] + right.bounds["width"] / 2.0)) + abs((left.bounds["y"] + left.bounds["height"] / 2.0) - (right.bounds["y"] + right.bounds["height"] / 2.0))


def _bounds_distance(bounds: BoundsDict, node: ElectricalGraphNode) -> float:
    left = _center_of_bounds(bounds)
    right = _center_of_bounds(node.bounds)
    return abs(left["x"] - right["x"]) + abs(left["y"] - right["y"])


def _nearest_node(node: ElectricalGraphNode, candidates: list[ElectricalGraphNode]) -> ElectricalGraphNode | None:
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: _same_page_distance(node, candidate))


def _nearest_bounds(bounds: BoundsDict, candidates: list[ElectricalGraphNode]) -> ElectricalGraphNode | None:
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: _bounds_distance(bounds, candidate))


def _nearest_text_span(
    spans: list[TextSpan],
    anchor: TextSpan,
    text: str,
    *,
    max_dx: float,
    max_dy: float,
) -> TextSpan | None:
    matches = [
        span
        for span in spans
        if span is not anchor
        and span_text(span).upper() == text
        and abs(_center_of_span(span)["x"] - _center_of_span(anchor)["x"]) <= max_dx
        and abs(span.y - anchor.y) <= max_dy
    ]
    return min(matches, key=lambda span: abs(span.y - anchor.y) + abs(_center_of_span(span)["x"] - _center_of_span(anchor)["x"]), default=None)


def _nearest_matching_span(
    spans: list[TextSpan],
    anchor: TextSpan,
    pattern: str,
    *,
    max_dx: float,
    max_dy: float,
) -> TextSpan | None:
    regex = re.compile(pattern, re.IGNORECASE)
    matches = [
        span
        for span in spans
        if regex.fullmatch(span_text(span))
        and abs(_center_of_span(span)["x"] - _center_of_span(anchor)["x"]) <= max_dx
        and abs(span.y - anchor.y) <= max_dy
    ]
    return min(matches, key=lambda span: abs(span.y - anchor.y) + abs(_center_of_span(span)["x"] - _center_of_span(anchor)["x"]), default=None)


def _nearest_line_node(node: ElectricalGraphNode, page_nodes: list[ElectricalGraphNode]) -> ElectricalGraphNode | None:
    line_nodes = [candidate for candidate in page_nodes if candidate.kind == "line_tag" and candidate.id != node.id]
    if not line_nodes:
        return None
    return min(line_nodes, key=lambda candidate: _same_page_distance(node, candidate))


def _best_line_node(node: ElectricalGraphNode, page_nodes: list[ElectricalGraphNode], page: PageEvidence | None) -> tuple[ElectricalGraphNode | None, str]:
    line_nodes = [candidate for candidate in page_nodes if candidate.kind == "line_tag" and candidate.id != node.id]
    if not line_nodes:
        return None, "nearest_electrical_line"
    if page is not None:
        geometry_candidates: list[tuple[float, ElectricalGraphNode]] = []
        for candidate in line_nodes:
            score = _linework_score(node, candidate, page)
            if score is not None:
                geometry_candidates.append((score, candidate))
        if geometry_candidates:
            return min(geometry_candidates, key=lambda item: item[0])[1], "linework_geometry"
    return min(line_nodes, key=lambda candidate: _same_page_distance(node, candidate)), "nearest_electrical_line"


def _nearest_equipment_node(node: ElectricalGraphNode, page_nodes: list[ElectricalGraphNode]) -> ElectricalGraphNode | None:
    equipment_nodes = [candidate for candidate in page_nodes if candidate.kind == "equipment" and candidate.id != node.id]
    if not equipment_nodes:
        return None
    return min(equipment_nodes, key=lambda candidate: _same_page_distance(node, candidate))


def _containing_equipment_node(node: ElectricalGraphNode, page_nodes: list[ElectricalGraphNode], page: PageEvidence | None) -> ElectricalGraphNode | None:
    if page is None:
        return None
    equipment_nodes = [candidate for candidate in page_nodes if candidate.kind == "equipment" and candidate.id != node.id]
    containing = [candidate for candidate in equipment_nodes if _share_enclosure(node, candidate, page)]
    if not containing:
        return None
    return min(containing, key=lambda candidate: _same_page_distance(node, candidate))


def _share_enclosure(left: ElectricalGraphNode, right: ElectricalGraphNode, page: PageEvidence) -> bool:
    left_center = _center_of_bounds(left.bounds)
    right_center = _center_of_bounds(right.bounds)
    for segment in page.vectorSegments:
        if segment.kind != "rect":
            continue
        bounds = segment.bounds
        if bounds["width"] < 40.0 or bounds["height"] < 40.0:
            continue
        if _point_in_bounds(left_center, bounds) and _point_in_bounds(right_center, bounds):
            return True
    return False


def _linework_score(node: ElectricalGraphNode, line: ElectricalGraphNode, page: PageEvidence) -> float | None:
    node_center = _center_of_bounds(node.bounds)
    line_center = _center_of_bounds(line.bounds)
    best: float | None = None
    for segment in page.vectorSegments:
        if segment.kind not in {"line", "polyline"} or len(segment.points) < 2:
            continue
        distances = _point_distances_to_polyline([node_center, line_center], segment.points)
        if distances[0] <= 34.0 and distances[1] <= 48.0:
            score = distances[0] + distances[1]
            best = score if best is None else min(best, score)
    return best


def _point_distances_to_polyline(points: list[dict[str, float]], polyline: list[dict[str, float]]) -> list[float]:
    distances: list[float] = []
    for point in points:
        segment_distances = [
            _point_segment_distance(point, start, end)
            for start, end in zip(polyline, polyline[1:])
        ]
        distances.append(min(segment_distances) if segment_distances else float("inf"))
    return distances


def _point_segment_distance(point: dict[str, float], start: dict[str, float], end: dict[str, float]) -> float:
    dx = end["x"] - start["x"]
    dy = end["y"] - start["y"]
    if dx == 0 and dy == 0:
        return ((point["x"] - start["x"]) ** 2 + (point["y"] - start["y"]) ** 2) ** 0.5
    t = ((point["x"] - start["x"]) * dx + (point["y"] - start["y"]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    nearest = {"x": start["x"] + t * dx, "y": start["y"] + t * dy}
    return ((point["x"] - nearest["x"]) ** 2 + (point["y"] - nearest["y"]) ** 2) ** 0.5


def _point_in_bounds(point: dict[str, float], bounds: BoundsDict) -> bool:
    return bounds["x"] <= point["x"] <= bounds["x"] + bounds["width"] and bounds["y"] <= point["y"] <= bounds["y"] + bounds["height"]


def _page_for_node(node: ElectricalGraphNode, pages: list[PageEvidence]) -> PageEvidence | None:
    return next((page for page in pages if page.sourceFileId == node.sourceFileId and page.page == node.page), None)


def _device_is_redundant(tag: str, node_by_key: dict[tuple[str, int, str, str], ElectricalGraphNode], page: PageEvidence) -> bool:
    if (page.sourceFileId, page.page, "line_tag", tag) in node_by_key:
        return True
    if (page.sourceFileId, page.page, "equipment", tag) in node_by_key:
        return True
    return tag.upper() in {"MAIN", "MAINS", "MAX", "MAKE", "TRANSFORMER"}


def _useful_tag(tag: str) -> bool:
    upper = tag.upper()
    if re.fullmatch(r"M\d+", upper):
        return True
    if re.fullmatch(r"(?:27|32|46|47|49|50|51|52|59|81|86|87)[A-Z]{0,2}", upper):
        return True
    if upper in {"SPARE", "DRAWING", "STANDBY", "FUTURE", "EPMS", "FMCS", "REFERENCE", "REQUEST", "REQUIRED", "RESEARCH", "RETURNED", "REPRODUCED", "REDISTRIBUTED"}:
        return False
    if upper.startswith(("RE", *BUILDING_CODES)) and not any(char.isdigit() for char in upper):
        return False
    if upper == "TRANSFORMER":
        return False
    if upper in {"800N", "1200N", "N.C.", "N.O."}:
        return False
    return len(upper) >= 4


def _is_actual_equipment_tag(tag: str) -> bool:
    upper = _normalize_tag(tag)
    if _is_electrical_rating_or_annotation(upper):
        return False
    if upper == "HV YARD SWG":
        return True
    if SWITCHGEAR_RE.fullmatch(upper) or TARGET_EQUIPMENT_RE.fullmatch(upper):
        return True
    if re.fullmatch(BUILDING_CODE_PATTERN + r"[A-Z0-9]*(?:MDP|SS|SWG)[A-Z0-9-]*(?:\s*&\s*[A-Z0-9-]+)+", upper):
        return True
    if GENERATOR_TAG_RE.fullmatch(upper):
        return True
    if re.fullmatch(r"R-[A-Z0-9]+(?:-[A-Z0-9]+)+(?:\s+\([A-Z0-9 ]+\))?", upper):
        return True
    if re.fullmatch(r"(?:ATS|UPS|MCC|VFD|PANEL|PNL|SWBD|SWGR|XFMR)(?:-[A-Z0-9][A-Z0-9-]*|\d[A-Z0-9-]*)", upper):
        return True
    if re.fullmatch(r"(?:TR|TX)(?:-[A-Z0-9][A-Z0-9-]*|\d[A-Z0-9-]*)", upper):
        return True
    return False


def is_user_facing_equipment_tag(tag: str) -> bool:
    return _is_actual_equipment_tag(tag)


def _is_electrical_rating_or_annotation(tag: str) -> bool:
    upper = _normalize_tag(tag)
    if "BUS" in upper:
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?\s*(?:KV|V|OHM|Ω)(?:[-/]\d+(?:\.\d+)?\s*(?:KV|V|OHM|Ω)?)*", upper):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?KV[-/]\d+(?:\.\d+)?V", upper):
        return True
    if re.fullmatch(r"\d+(?:\.\d+)?[A-Z]?(?:AF|AT|A|KVA|KW|PF|N)?", upper):
        return True
    if re.fullmatch(r"(?:AA|FA)\s+\d{3,5}KVA", upper):
        return True
    if re.fullmatch(r"M\d+", upper):
        return True
    if re.fullmatch(r"(?:27|32|46|47|49|50|51|52|59|81|86|87)[A-Z]{0,2}(?:-[A-Z0-9]+)?", upper):
        return True
    return False


def _is_to_reference_target(page: PageEvidence, span: TextSpan) -> bool:
    target_text = span_text(span)
    if not TARGET_EQUIPMENT_RE.fullmatch(target_text.upper()):
        return False
    for other in page.textSpans:
        if span_text(other).upper() != "TO":
            continue
        same_row = abs(other.y - span.y) <= max(16.0, span.height * 1.6)
        to_left = 0.0 <= span.x - other.x <= 260.0
        stacked_above = 0.0 <= span.y - other.y <= 38.0 and abs(other.x - span.x) <= 80.0
        if same_row and to_left or stacked_above:
            return True
    return False


def _is_switch_section_label(value: str) -> bool:
    text = _normalize_tag(value)
    return bool(SWITCH_SECTION_LABEL_RE.fullmatch(text))


def _normalize_tag(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().upper())


def span_text(span: TextSpan) -> str:
    return (span.text or "").strip()


def _first_match(regex: re.Pattern[str], text: str) -> str:
    match = regex.search(text or "")
    return match.group(0).upper() if match else ""


def _node_id(kind: str, page_id: str, tag: str) -> str:
    return f"elecnode_{kind}_{_slug(page_id)}_{_slug(tag)}"


def _edge_id(kind: str, *parts: str) -> str:
    return f"elecedge_{kind}_{'_'.join(_slug(part) for part in parts if part)}"


def _slug(value: str) -> str:
    text = str(value).lower()
    text = re.sub(r'["]+', "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "item"
