from __future__ import annotations

from typing import Any


def line_mounted_parent_id(
    line: dict[str, Any],
    item: dict[str, Any],
    *,
    hide_line_nodes: bool = False,
) -> str | None:
    line_id = str(line.get("id") or "")
    attached_line_id = str(item.get("attachedLineId") or "")
    if not line_id or attached_line_id != line_id:
        return None

    if hide_line_nodes:
        direction = str(line.get("flowDirection", "source_to_target"))
        if direction == "target_to_source":
            parent_id = line.get("targetEquipmentId")
        else:
            parent_id = line.get("sourceEquipmentId")
    else:
        parent_id = line_id

    return str(parent_id) if parent_id else None


def normalize_hierarchy_views(visual_qa: dict[str, Any]) -> list[dict[str, Any]]:
    existing = visual_qa.get("hierarchyViews")
    if isinstance(existing, list) and existing:
        views = [dict(view) for view in existing if isinstance(view, dict)]
        return _append_dependency_view(views, visual_qa)

    views: list[dict[str, Any]] = []
    electrical = visual_qa.get("electricalRelationshipGraph")
    if isinstance(electrical, dict):
        views.append(
            {
                "id": "electrical_power",
                "label": "Electrical Power Tree",
                "discipline": "Electrical",
                "nodes": list(electrical.get("nodes", [])),
                "edges": list(electrical.get("edges", [])),
                "metrics": dict(electrical.get("metrics", {})),
                "sourceGraph": "electricalRelationshipGraph",
            }
        )
    return _append_dependency_view(views, visual_qa)


def _append_dependency_view(views: list[dict[str, Any]], visual_qa: dict[str, Any]) -> list[dict[str, Any]]:
    if any(view.get("id") == "commissioning_dependencies" for view in views):
        return views
    dependency = visual_qa.get("dependencyGraph")
    if not isinstance(dependency, dict):
        return views
    nodes = list(dependency.get("nodes", []))
    edges = list(dependency.get("edges", []))
    if not nodes or not edges:
        return views
    views.append(
        {
            "id": "commissioning_dependencies",
            "label": "Dependency View",
            "discipline": "Mixed Package",
            "nodes": nodes,
            "edges": edges,
            "metrics": dict(dependency.get("metrics", {})),
            "qa": dict(dependency.get("qa", {})),
            "sourceGraph": "dependencyGraph",
        }
    )
    return views


def attach_hierarchy_views(visual_qa: dict[str, Any]) -> dict[str, Any]:
    visual_qa["hierarchyViews"] = normalize_hierarchy_views(visual_qa)
    return visual_qa
