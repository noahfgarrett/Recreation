from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

from recreation_extractor.pid_stitch.models import BoundsDict


DependencyEdgeKind = Literal[
    "requires_drive",
    "requires_power",
    "requires_upstream_distribution",
    "requires_feeder",
    "requires_transformer",
    "requires_backup_power",
    "requires_driven_equipment",
    "requires_motor",
    "requires_control_panel",
    "requires_control_signal",
    "requires_feedback_signal",
    "requires_safety_device",
    "requires_instrument",
    "requires_process_line",
    "requires_source_equipment",
]
DependencyStatus = Literal["confirmed", "inferred", "needs_review"]

DEPENDENCY_EXPORT_COLUMNS = [
    "Target Equipment Tag",
    "Target Equipment Description",
    "Target Discipline",
    "Depends On Equipment Tag",
    "Depends On Description",
    "Dependency Discipline",
    "Dependency Type",
    "Status",
    "Confidence",
    "Dependency Path",
    "Commissioning Use",
    "Rule ID",
    "Source Discipline",
    "Source File",
    "Source Page",
    "Evidence Text",
    "Notes",
]
DEPENDENCY_KIND_EXPORT_ORDER = {
    "requires_drive": 10,
    "requires_power": 20,
    "requires_upstream_distribution": 30,
    "requires_feeder": 40,
    "requires_transformer": 50,
    "requires_backup_power": 60,
    "requires_motor": 70,
    "requires_control_panel": 80,
    "requires_control_signal": 90,
    "requires_feedback_signal": 100,
    "requires_safety_device": 110,
    "requires_instrument": 120,
    "requires_process_line": 130,
    "requires_source_equipment": 140,
}


@dataclass(frozen=True)
class DependencyGraphNode:
    id: str
    tag: str
    kind: str
    discipline: str
    description: str
    sourceFileId: str
    sourcePageId: str
    page: int | None
    bounds: BoundsDict | None
    sourceEvidenceIds: list[str]
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DependencyGraphEdge:
    id: str
    sourceId: str
    targetId: str
    sourceTag: str
    targetTag: str
    kind: DependencyEdgeKind
    label: str
    status: DependencyStatus
    confidence: float
    ruleId: str
    sourceEvidenceIds: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DependencyGraph:
    projectId: str
    nodes: list[DependencyGraphNode]
    edges: list[DependencyGraphEdge]
    metrics: dict[str, Any]
    qa: dict[str, Any]

    def to_visual_qa(self) -> dict[str, Any]:
        return {
            "metrics": dict(self.metrics),
            "qa": dict(self.qa),
            "nodes": [asdict(node) for node in self.nodes],
            "edges": [asdict(edge) for edge in self.edges],
            "exportColumns": list(DEPENDENCY_EXPORT_COLUMNS),
            "exportRows": self.to_export_rows(),
        }

    def to_export_rows(self) -> list[dict[str, Any]]:
        node_by_id = {node.id: node for node in self.nodes}
        rows: list[dict[str, Any]] = []
        for edge in sorted(self.edges, key=lambda item: (item.targetTag, DEPENDENCY_KIND_EXPORT_ORDER.get(item.kind, 999), item.sourceTag)):
            source = node_by_id.get(edge.sourceId)
            target = node_by_id.get(edge.targetId)
            if source is None or target is None:
                continue
            rows.append(
                {
                    "Target Equipment Tag": target.tag,
                    "Target Equipment Description": target.description,
                    "Target Discipline": target.discipline,
                    "Depends On Equipment Tag": source.tag,
                    "Depends On Description": source.description,
                    "Dependency Discipline": source.discipline,
                    "Dependency Type": edge.kind,
                    "Status": edge.status,
                    "Confidence": round(edge.confidence, 3),
                    "Dependency Path": str(edge.metadata.get("dependencyPath") or f"{target.tag} <- {source.tag}"),
                    "Commissioning Use": str(edge.metadata.get("commissioningUse") or ""),
                    "Rule ID": edge.ruleId,
                    "Source Discipline": str(edge.metadata.get("sourceDiscipline") or source.discipline or target.discipline),
                    "Source File": str(edge.metadata.get("sourcePath") or source.metadata.get("sourcePath") or target.metadata.get("sourcePath") or source.sourceFileId),
                    "Source Page": edge.metadata.get("sourcePage") or source.page or target.page or "",
                    "Evidence Text": _evidence_text(edge, source, target),
                    "Notes": str(edge.metadata.get("notes") or ""),
                }
            )
        return rows


def dependency_metrics(nodes: list[DependencyGraphNode], edges: list[DependencyGraphEdge]) -> dict[str, Any]:
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "targets": len({edge.targetId for edge in edges}),
        "dependencySources": len({edge.sourceId for edge in edges}),
        "byKind": _count_by(edge.kind for edge in edges),
        "byStatus": _count_by(edge.status for edge in edges),
        "realEquipmentOnly": True,
    }


def dependency_edge_id(kind: str, source_tag: str, target_tag: str) -> str:
    return f"depedge_{kind}_{_slug(source_tag)}_{_slug(target_tag)}"


def dependency_node_id(tag: str) -> str:
    return f"depnode_{_slug(tag)}"


def _evidence_text(edge: DependencyGraphEdge, source: DependencyGraphNode, target: DependencyGraphNode) -> str:
    explicit = str(edge.metadata.get("evidenceText") or "").strip()
    if explicit:
        return explicit
    source_text = str(source.metadata.get("sourceText") or "").strip()
    target_text = str(target.metadata.get("sourceText") or "").strip()
    evidence = " | ".join(item for item in [source_text, target_text] if item)
    if evidence:
        return evidence
    return ", ".join(edge.sourceEvidenceIds)


def _count_by(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _slug(value: str) -> str:
    text = str(value).lower()
    text = re.sub(r'["]+', "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "item"
