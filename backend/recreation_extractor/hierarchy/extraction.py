from __future__ import annotations

import copy
import hashlib
from typing import Any

from recreation_extractor.hierarchy.models import to_plain_dict
from recreation_extractor.hierarchy.dependency_rules import build_dependency_graph
from recreation_extractor.hierarchy.relationship_graph import attach_hierarchy_views
from recreation_extractor.hierarchy.rulebook import build_rulebook
from recreation_extractor.pid_stitch.electrical_graph import build_electrical_relationship_graph
from recreation_extractor.pid_stitch.electrical_graph import is_user_facing_equipment_tag
from recreation_extractor.pid_stitch.models import (
    ContinuationCandidate,
    ContinuationMatch,
    DrawingDocument,
    DrawingStyle,
    PageEvidence,
)
from recreation_extractor.pid_stitch.semantic_graph import build_pid_relationship_graph
from recreation_extractor.pid_stitch.system_colors import discover_system_color_map


HIERARCHY_DOCUMENT_WIDTH = 1440.0
HIERARCHY_DOCUMENT_HEIGHT = 900.0


def slim_source_pages(pages: list[PageEvidence]) -> list[PageEvidence]:
    return [
        PageEvidence(
            id=page.id,
            sourceFileId=page.sourceFileId,
            page=page.page,
            width=page.width,
            height=page.height,
            rotation=page.rotation,
            cropBounds=dict(page.cropBounds),
            textSpans=[],
            vectorCount=page.vectorCount,
            vectorSegments=[],
            metadata=copy.deepcopy(page.metadata),
        )
        for page in pages
    ]


def build_hierarchy_document(
    project_id: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
    *,
    preflight_review: dict[str, Any] | None = None,
) -> DrawingDocument:
    sorted_pages = sorted(pages, key=lambda item: (item.sourceFileId, item.page, item.id))
    selected_matches = [match for match in matches if match.status != "rejected"]
    system_color_map = discover_system_color_map(sorted_pages, candidates, source_paths)
    semantic_graph = build_pid_relationship_graph(project_id, sorted_pages, candidates, selected_matches, source_paths, system_color_map)
    electrical_graph = build_electrical_relationship_graph(project_id, sorted_pages, source_paths)
    dependency_graph = build_dependency_graph(project_id, semantic_graph, electrical_graph)
    rulebook = to_plain_dict(build_rulebook(project_id, sorted_pages, preflight_review))
    visual_qa: dict[str, Any] = {
        "hierarchyOnly": True,
        "sourceGraph": "hierarchy_extraction_job",
        "semanticRelationshipGraph": semantic_graph.to_visual_qa(),
        "electricalRelationshipGraph": electrical_graph.to_visual_qa(),
        "dependencyGraph": dependency_graph.to_visual_qa(),
        "preflightReview": copy.deepcopy(preflight_review or {}),
        "documentRulebook": copy.deepcopy(rulebook),
        "metrics": {
            "sourcePages": len(sorted_pages),
            "sourceContinuations": len(candidates),
            "matchedContinuations": len(selected_matches),
            "semanticNodes": len(semantic_graph.nodes),
            "semanticEdges": len(semantic_graph.edges),
            "electricalNodes": len(electrical_graph.nodes),
            "electricalEdges": len(electrical_graph.edges),
            "dependencyNodes": len(dependency_graph.nodes),
            "dependencyEdges": len(dependency_graph.edges),
            "legendAcronyms": len(rulebook.get("acronymMap", {})),
        },
    }
    attach_hierarchy_views(visual_qa)
    visual_qa["hierarchyViews"] = _filter_hierarchy_views(visual_qa.get("hierarchyViews", []))
    namespace = hashlib.sha1(project_id.encode("utf-8")).hexdigest()[:12]
    return DrawingDocument(
        id=f"hierarchy_{namespace}",
        projectId=project_id,
        name="Hierarchy Tree Extraction",
        width=HIERARCHY_DOCUMENT_WIDTH,
        height=HIERARCHY_DOCUMENT_HEIGHT,
        objects=[],
        sourcePages=slim_source_pages(sorted_pages),
        styles={
            "default": DrawingStyle(
                stroke="#64748b",
                fill="transparent",
                strokeWidth=1.0,
                opacity=1.0,
            )
        },
        visualQa=visual_qa,
    )


def _filter_hierarchy_views(views: object) -> list[dict[str, Any]]:
    if not isinstance(views, list):
        return []
    filtered: list[dict[str, Any]] = []
    for view in views:
        if not isinstance(view, dict):
            continue
        if view.get("id") != "electrical_power":
            filtered.append(dict(view))
            continue
        electrical_view = _equipment_only_electrical_view(view)
        if electrical_view is not None:
            filtered.append(electrical_view)
    return filtered


def _equipment_only_electrical_view(view: dict[str, Any]) -> dict[str, Any] | None:
    nodes = [dict(node) for node in view.get("nodes", []) if isinstance(node, dict)]
    equipment_nodes = [node for node in nodes if _is_user_facing_electrical_node(node)]
    if not equipment_nodes:
        return None

    kept_ids = {str(node.get("id") or "") for node in equipment_nodes if node.get("id")}
    edges = [
        dict(edge)
        for edge in view.get("edges", [])
        if isinstance(edge, dict)
        and _edge_endpoint_id(edge, "source") in kept_ids
        and _edge_endpoint_id(edge, "target") in kept_ids
    ]
    next_view = dict(view)
    next_view["nodes"] = equipment_nodes
    next_view["edges"] = edges
    metrics = dict(next_view.get("metrics", {}))
    metrics["equipmentOnlyNodes"] = len(equipment_nodes)
    metrics["equipmentOnlyEdges"] = len(edges)
    next_view["metrics"] = metrics
    return next_view


def _is_user_facing_electrical_node(node: dict[str, Any]) -> bool:
    metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else {}
    if metadata.get("suppressInEquipmentFlow"):
        return False
    kind = str(node.get("kind") or "")
    if kind not in {"equipment", "line_tag", "section"}:
        return False
    return is_user_facing_equipment_tag(str(node.get("tag") or ""))


def _edge_endpoint_id(edge: dict[str, Any], endpoint: str) -> str:
    camel_key = f"{endpoint}Id"
    return str(edge.get(camel_key) or edge.get(endpoint) or "")
