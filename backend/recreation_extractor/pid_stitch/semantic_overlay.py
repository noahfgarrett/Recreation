from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

from recreation_extractor.conventions import PROJECT_CODE_PATTERN
from recreation_extractor.pid_stitch.models import (
    BoundsDict,
    ContinuationCandidate,
    ContinuationMatch,
    DrawingDocument,
    DrawingObject,
    DrawingStyle,
    LayoutOption,
    PageEvidence,
    Point,
    VectorSegment,
)
from recreation_extractor.pid_stitch.semantic_graph import PidRelationshipGraph
from recreation_extractor.pid_stitch.source_graph import LINE_TAG_RE
from recreation_extractor.pid_stitch.system_colors import SystemColorMap, canonical_system, display_system_label, style_for_system, system_for_text

# Plumbing sheets often label a pipe with size and system only, e.g. 10" POTCW.
PIPE_SIZE_SYSTEM_LABEL_RE = re.compile(r'\b(?:\d{1,3}(?:\s+\d/\d)?|\d/\d)"\s+[A-Z][A-Z0-9]{1,8}\b', re.IGNORECASE)
# Inline plumbing devices carry the system in the tag, e.g. 01-ICW-BFP-01 (backflow
# preventer on the ICW line). They only seed pipe colors; they are not drawn as line tags.
INLINE_DEVICE_TAG_RE = re.compile(r"\b\d{2}-[A-Z]{2,6}-[A-Z]{2,5}-\d{2,3}\b", re.IGNORECASE)


INSTRUMENT_TAG_RE = re.compile(r"\b(?:PDIT|PDT|PIT|FIT|TIT|LIT|AIT|PT|FT|TT|LT|PI|FI|TI|FE|TE|AT)-?\d+[A-Z0-9-]*\b", re.IGNORECASE)
SEMANTIC_EQUIPMENT_TAG_RE = re.compile(
    r"\b(?:R-[A-Z0-9]+-[A-Z0-9]+-[A-Z0-9_-]+|(?:AHU|MAU|FCU|DUH|FTR|CAVR|CVR|VAR|SHW|ST|BA|IE)-\d+[A-Z0-9-]*(?:-[A-Z0-9]+)?|P-(?:\d{1,3}|XX)(?:-[A-Z0-9]+)?|HX-(?:\d{1,3}|XX)(?:-[A-Z0-9]+)?)\b",
    re.IGNORECASE,
)
SHEET_REF_RE = re.compile(r"\b[A-Z]{2,8}-[A-Z]{1,5}-[0-9][A-Z0-9_.-]*\b", re.IGNORECASE)


def build_semantic_drawing_option(
    project_id: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
    system_color_map: SystemColorMap,
    tile_by_source: dict[str, BoundsDict],
    source_bounds_by_source: dict[str, BoundsDict],
    relationship_graph: PidRelationshipGraph | None = None,
) -> tuple[LayoutOption, DrawingDocument]:
    """Build a compact semantic-only P&ID drawing for overview review."""
    sorted_pages = sorted(pages, key=lambda page: (page.sourceFileId, page.page, page.id))
    single_source_page = len(sorted_pages) == 1
    option, document = _build_semantic_option(
        project_id,
        sorted_pages,
        candidates,
        matches,
        source_paths,
        system_color_map,
        tile_by_source,
        source_bounds_by_source,
        option_suffix="semantic_drawing",
        drawing_name="Semantic Drawing",
        title="SEMANTIC DRAWING",
        description="Primary overview semantic-only P&ID using source-stitched page placement, colored system routes, and editable snap connectors.",
        primary_output=True,
        include_source_map=False,
        include_source_traces=single_source_page,
        compose_inventory=False,
        source_trace_opacity=0.96 if single_source_page else 0.9,
        source_trace_stroke_width=0.62 if single_source_page else 0.78,
        include_default_source_vectors=single_source_page,
        generate_backbones=not single_source_page,
        include_graph_attachments=False,
        relationship_graph=relationship_graph,
    )
    option.metrics["semanticDrawing"] = True
    option.metrics["singleSourceFaithful"] = single_source_page
    document.visualQa["singleSourceFaithful"] = single_source_page
    return option, document


def build_semantic_overlay_option(
    project_id: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
    system_color_map: SystemColorMap,
    tile_by_source: dict[str, BoundsDict],
    source_bounds_by_source: dict[str, BoundsDict],
    relationship_graph: PidRelationshipGraph | None = None,
) -> tuple[LayoutOption, DrawingDocument]:
    """Build a source-coordinate semantic overlay that remains fully editable."""
    return _build_semantic_option(
        project_id,
        sorted(pages, key=lambda page: (page.sourceFileId, page.page, page.id)),
        candidates,
        matches,
        source_paths,
        system_color_map,
        tile_by_source,
        source_bounds_by_source,
        option_suffix="semantic_overlay",
        drawing_name="Semantic Overlay",
        title="SEMANTIC OVERLAY",
        description="Auditable semantic P&ID: source-coordinate map plus editable house-style equipment, colored systems, and continuation links.",
        primary_output=False,
        include_source_map=True,
        include_source_traces=True,
        compose_inventory=False,
        source_trace_opacity=0.18,
        source_trace_stroke_width=0.82,
        include_default_source_vectors=False,
        generate_backbones=True,
        include_graph_attachments=True,
        relationship_graph=relationship_graph,
    )


def _build_semantic_option(
    project_id: str,
    sorted_pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
    system_color_map: SystemColorMap,
    tile_by_source: dict[str, BoundsDict],
    source_bounds_by_source: dict[str, BoundsDict],
    *,
    option_suffix: str,
    drawing_name: str,
    title: str,
    description: str,
    primary_output: bool,
    include_source_map: bool,
    include_source_traces: bool,
    compose_inventory: bool,
    source_trace_opacity: float,
    source_trace_stroke_width: float,
    include_default_source_vectors: bool,
    generate_backbones: bool,
    include_graph_attachments: bool,
    relationship_graph: PidRelationshipGraph | None,
) -> tuple[LayoutOption, DrawingDocument]:
    candidate_by_id = {candidate.id: candidate for candidate in candidates}
    objects: list[DrawingObject] = []

    page_source_ids = [page.id for page in sorted_pages]
    display_title = _semantic_output_title(title, system_color_map)
    objects.append(
        _label(
            "semantic_title",
            display_title,
            {"x": 120.0, "y": 54.0, "width": 720.0, "height": 26.0},
            "#0f172a",
            17.0,
            page_source_ids,
            {"semanticOverlay": True, "semanticTitle": True},
        )
    )
    objects.append(
        _label(
            "semantic_subtitle",
            f"{len(sorted_pages)} source sheet{'s' if len(sorted_pages) != 1 else ''} redrawn as editable equipment, instruments, system pipes, and continuation links",
            {"x": 122.0, "y": 86.0, "width": 820.0, "height": 16.0},
            "#475569",
            8.2,
            page_source_ids,
            {"semanticOverlay": True, "semanticTitle": True},
        )
    )
    objects.extend(_legend(system_color_map, page_source_ids))
    if include_source_map:
        objects.extend(_source_map_fragments(sorted_pages, source_paths, tile_by_source, source_bounds_by_source))

    inventory = _semantic_inventory(sorted_pages, candidates, system_color_map, tile_by_source, source_bounds_by_source)
    _assign_nearby_systems(inventory)
    placed_inventory = _placed_semantic_inventory(inventory, compose=compose_inventory)
    if include_source_traces:
        objects.extend(_semantic_vector_lines(sorted_pages, placed_inventory, matches, candidate_by_id, system_color_map, tile_by_source, source_bounds_by_source, opacity=source_trace_opacity, stroke_width=source_trace_stroke_width, include_default_vectors=include_default_source_vectors))
    if compose_inventory:
        objects.extend(_semantic_system_regions(placed_inventory, system_color_map, page_source_ids))
    if generate_backbones:
        objects.extend(_semantic_system_backbones(placed_inventory, system_color_map))
    if include_graph_attachments:
        objects.extend(_semantic_graph_attachment_connectors(placed_inventory, system_color_map, relationship_graph))
    objects.extend(_semantic_tags(placed_inventory, system_color_map, relationship_graph))
    objects.extend(_semantic_continuations(sorted_pages, candidates, matches, candidate_by_id, placed_inventory, system_color_map, tile_by_source, source_bounds_by_source, source_paths, use_semantic_anchors=compose_inventory, relationship_graph=relationship_graph))
    _deconflict_semantic_labels(objects)
    _route_semantic_lines_around_dense_pockets(objects)
    objects = _merge_nearby_same_system_routes(objects)
    _snap_attached_connector_endpoints(objects)
    if not include_source_map:
        _normalize_semantic_body_position(objects)

    semantic_objects = [obj for obj in objects if obj.metadata.get("semanticOverlay") is True]
    semantic_searchable = " ".join(obj.label.upper() for obj in semantic_objects)
    equipment_tags = sorted({item["tag"] for item in inventory if item["kind"] == "equipment"})
    line_tags = sorted({item["tag"] for item in inventory if item["kind"] == "line"} | {candidate.lineTag.upper() for candidate in candidates if candidate.lineTag})
    missing_equipment = [tag for tag in equipment_tags if tag.upper() not in semantic_searchable]
    missing_lines = [tag for tag in line_tags if tag.upper() not in semantic_searchable]

    width, height = _document_size(objects, compact=not include_source_map)
    namespace = _stable_hash(f"{project_id}:{option_suffix}")
    drawing_id = f"drawing_{namespace}_{option_suffix}"
    document = DrawingDocument(
        id=drawing_id,
        projectId=project_id,
        name=drawing_name,
        width=width,
        height=height,
        objects=objects,
        sourcePages=sorted_pages,
        styles=_styles_from_color_map(system_color_map),
        visualQa={
            "semanticOverlay": True,
            "semanticObjects": len(semantic_objects),
            "sourceMapObjects": len([obj for obj in objects if obj.metadata.get("semanticSourceMap") is True]),
            "semanticEquipmentTags": len(equipment_tags),
            "semanticLineTags": len(line_tags),
            "semanticMissingEquipmentTags": missing_equipment,
            "semanticMissingLineTags": missing_lines,
            "semanticMatchedContinuations": len([obj for obj in semantic_objects if obj.metadata.get("semanticConnectorRole") == "matchedContinuation"]),
            "semanticUnresolvedContinuations": len([obj for obj in semantic_objects if obj.metadata.get("semanticConnectorRole") == "unresolvedContinuation"]),
            "semanticGraphAttachmentConnectors": len([obj for obj in semantic_objects if obj.metadata.get("semanticConnectorRole") == "graphAttachment"]),
            "semanticGeneratedRouteObjects": len([obj for obj in semantic_objects if obj.metadata.get("semanticGeneratedRoute") is True]),
            "semanticTracePipeObjects": len([obj for obj in semantic_objects if obj.metadata.get("semanticTracePipe") is True]),
            "semanticRelationshipGraph": relationship_graph.to_visual_qa() if relationship_graph is not None else {"metrics": {}, "qa": {}, "nodes": [], "edges": []},
        },
    )
    option = LayoutOption(
        id=f"layout_{namespace}_{option_suffix}",
        projectId=project_id,
        drawingId=drawing_id,
        name=drawing_name,
        description=description,
        score=max(30.0, 94.0 - len(missing_equipment) * 1.2 - len(missing_lines) * 0.8),
        metrics={
            "primaryOutput": primary_output,
            "semanticOverlay": True,
            "sourceMapObjects": document.visualQa["sourceMapObjects"],
            "semanticObjects": document.visualQa["semanticObjects"],
            "equipmentCoverage": _coverage(len(equipment_tags), len(missing_equipment)),
            "lineCoverage": _coverage(len(line_tags), len(missing_lines)),
            "matchedContinuations": document.visualQa["semanticMatchedContinuations"],
            "unresolvedContinuations": document.visualQa["semanticUnresolvedContinuations"],
            "graphAttachmentConnectors": document.visualQa["semanticGraphAttachmentConnectors"],
            "semanticTracePipeObjects": document.visualQa["semanticTracePipeObjects"],
        },
    )
    return option, document


def _semantic_output_title(default_title: str, system_color_map: SystemColorMap) -> str:
    if default_title != "SEMANTIC DRAWING":
        return default_title
    systems = [key for key in system_color_map.entries if key not in {"DEFAULT", "FUTURE"}]
    canonical_systems = {canonical_system(system) or system for system in systems}
    if {"CHW", "CW"}.issubset(canonical_systems):
        return "CHILLED WATER / COOLING WATER SYSTEM OVERVIEW"
    if "CHW" in canonical_systems:
        return "CHILLED WATER SYSTEM OVERVIEW"
    if {"HHW", "HRW"}.issubset(canonical_systems):
        return "HEATED HOT WATER / HEAT RECOVERY WATER SYSTEM OVERVIEW"
    if "HHW" in canonical_systems:
        return "HEATED HOT WATER SYSTEM OVERVIEW"
    if "HRW" in canonical_systems:
        return "HEAT RECOVERY WATER SYSTEM OVERVIEW"
    if "CDA" in canonical_systems:
        return "COMPRESSED AIR SYSTEM OVERVIEW"
    if canonical_systems & {"DOMW", "SSW", "PW"}:
        return "PLUMBING WATER SYSTEM OVERVIEW"
    if canonical_systems & {"480V", "208V", "120V", "MCC", "UPS", "PDU", "SWGR", "XFMR", "FEEDER", "PANEL", "ELEC"}:
        return "ELECTRICAL SYSTEM OVERVIEW"
    if systems:
        labels = [display_system_label(system).upper() for system in systems[:3]]
        return f"{' / '.join(labels)} SYSTEM OVERVIEW"
    return "SYSTEM OVERVIEW"


def _semantic_inventory(
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    system_color_map: SystemColorMap,
    tile_by_source: dict[str, BoundsDict],
    source_bounds_by_source: dict[str, BoundsDict],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for page in pages:
        tile = tile_by_source.get(page.sourceFileId)
        source_bounds = source_bounds_by_source.get(page.sourceFileId)
        if not tile or not source_bounds:
            continue
        for span_index, span in enumerate(page.textSpans):
            text = span.text or ""
            for kind, regex in (
                ("equipment", SEMANTIC_EQUIPMENT_TAG_RE),
                ("line", LINE_TAG_RE),
                ("line", PIPE_SIZE_SYSTEM_LABEL_RE),
                ("instrument", INSTRUMENT_TAG_RE),
            ):
                for match_index, match in enumerate(regex.finditer(text)):
                    tag = match.group(0).upper()
                    key = (page.id, kind, tag)
                    if key in seen:
                        continue
                    system = _semantic_system_for_tag(kind, tag, system_color_map)
                    if regex is PIPE_SIZE_SYSTEM_LABEL_RE and system == "DEFAULT":
                        # A bare size label like 10" PIPE says nothing about the system.
                        continue
                    seen.add(key)
                    bounds = _map_bounds(
                        {
                            "x": span.x + min(match_index * 18.0, max(span.width - 12.0, 0.0)),
                            "y": span.y,
                            "width": max(48.0, min(span.width, 160.0)),
                            "height": max(span.height, 14.0),
                        },
                        source_bounds,
                        tile,
                    )
                    items.append(
                        {
                            "id": _slug_id(kind, page.id, tag, str(span_index)),
                            "kind": kind,
                            "tag": tag,
                            "system": system,
                            "page": page,
                            "bounds": bounds,
                            "sourceBounds": {
                                "x": span.x + min(match_index * 18.0, max(span.width - 12.0, 0.0)),
                                "y": span.y,
                                "width": max(48.0, min(span.width, 160.0)),
                                "height": max(span.height, 14.0),
                            },
                            "sourceEvidenceIds": [page.id],
                        }
                    )
    for candidate in candidates:
        if not candidate.lineTag:
            continue
        page = next((item for item in pages if item.sourceFileId == candidate.sourceFileId and item.page == candidate.page), None)
        tile = tile_by_source.get(candidate.sourceFileId)
        source_bounds = source_bounds_by_source.get(candidate.sourceFileId)
        if not page or not tile or not source_bounds:
            continue
        tag = candidate.lineTag.upper()
        key = (candidate.id, "line", tag)
        if key in seen:
            continue
        bounds = _map_bounds(candidate.bounds, source_bounds, tile)
        items.append(
            {
                "id": _slug_id("candidate_line", candidate.id, tag),
                "kind": "line",
                "tag": tag,
                "system": _normalize_semantic_system(system_for_text(candidate.system or tag, system_color_map), system_color_map),
                "page": page,
                "bounds": bounds,
                "sourceBounds": dict(candidate.bounds),
                "sourceEvidenceIds": [candidate.id],
            }
        )
    return items


def _semantic_drawing_tiles(pages: list[PageEvidence], source_bounds_by_source: dict[str, BoundsDict]) -> dict[str, BoundsDict]:
    if not pages:
        return {}
    columns = 1 if len(pages) == 1 else min(3, len(pages))
    tile_width = 760.0 if len(pages) <= 2 else 700.0
    tile_height = 500.0 if len(pages) <= 2 else 460.0
    gap_x = 96.0
    gap_y = 88.0
    origin_x = 120.0
    origin_y = 178.0
    tiles: dict[str, BoundsDict] = {}
    for index, page in enumerate(pages):
        source_bounds = source_bounds_by_source.get(page.sourceFileId, {"x": 0.0, "y": 0.0, "width": page.width, "height": page.height})
        scale = min(tile_width / max(source_bounds["width"], 1.0), tile_height / max(source_bounds["height"], 1.0))
        col = index % columns
        row = index // columns
        tiles[page.sourceFileId] = {
            "x": origin_x + col * (tile_width + gap_x),
            "y": origin_y + row * (tile_height + gap_y),
            "width": source_bounds["width"] * scale,
            "height": source_bounds["height"] * scale,
        }
    return tiles


def _semantic_vector_lines(
    pages: list[PageEvidence],
    inventory: list[dict[str, Any]],
    matches: list[ContinuationMatch],
    candidate_by_id: dict[str, ContinuationCandidate],
    system_color_map: SystemColorMap,
    tile_by_source: dict[str, BoundsDict],
    source_bounds_by_source: dict[str, BoundsDict],
    *,
    opacity: float,
    stroke_width: float,
    include_default_vectors: bool,
) -> list[DrawingObject]:
    line_items = [item for item in inventory if item["kind"] == "line"] + _inline_device_seeds(pages, system_color_map)
    context_bounds_by_source = _semantic_context_bounds_by_source(inventory)
    detail_context_bounds_by_source = _semantic_detail_context_bounds_by_source(inventory)
    matched_bounds_by_source = _matched_candidate_bounds_by_source(matches, candidate_by_id)
    objects: list[DrawingObject] = []
    for page in pages:
        tile = tile_by_source.get(page.sourceFileId)
        source_bounds = source_bounds_by_source.get(page.sourceFileId)
        if not tile or not source_bounds:
            continue
        vector_records: list[tuple[int, VectorSegment]] = []
        for index, vector in enumerate(page.vectorSegments):
            if len(vector.points) < 2 or _is_noise_vector(vector, page):
                continue
            if _is_page_edge_frame_vector(vector.bounds, page) or _is_title_block_band_vector(vector.bounds, page):
                continue
            if _is_matched_offpage_marker_vector(vector, matched_bounds_by_source.get(page.sourceFileId, [])):
                continue
            vector_records.append((index, vector))
        propagated_systems = _propagated_vector_systems(page, vector_records, line_items, system_color_map)
        colored_segments = [
            segment
            for record_index, vector in vector_records
            if propagated_systems.get(record_index, "DEFAULT") != "DEFAULT"
            for segment in _vector_line_segments(vector)
        ]
        for index, vector in vector_records:
            system = propagated_systems.get(index, "DEFAULT")
            if system == "DEFAULT" and not include_default_vectors:
                continue
            if system == "DEFAULT" and not _is_default_detail_trace_vector(
                vector,
                page,
                detail_context_bounds_by_source.get(page.sourceFileId, []),
                colored_segments,
            ):
                continue
            if system == "DEFAULT" and _is_default_context_vector_noise(vector, page, context_bounds_by_source.get(page.sourceFileId, [])):
                continue
            points = [_map_point(point, source_bounds, tile) for point in vector.points]
            if len(points) < 2:
                continue
            if system == "DEFAULT":
                style = DrawingStyle(stroke="#334155", fill="none", strokeWidth=max(0.44, stroke_width * 0.62), opacity=min(opacity, 0.24), dash=[4.0, 4.0] if vector.dashed else None)
                system_color_applied = False
            else:
                style = style_for_system(system, system_color_map, stroke_width=stroke_width)
                style.opacity = opacity
                system_color_applied = True
            objects.append(
                DrawingObject(
                    id=_object_id("semantic_source_trace_pipe", page.id, vector.id or str(index)),
                    kind="pipe",
                    label="",
                    points=points,
                    bounds=_points_bounds(points, 2.0),
                    style=style,
                    sourceEvidenceIds=[page.id, vector.id] if vector.id else [page.id],
                    locked=False,
                    metadata={
                        "semanticOverlay": True,
                        "semanticPipe": True,
                        "semanticTracePipe": True,
                        "sourceDerived": True,
                        "sourceVectorId": vector.id,
                        "sourcePageId": page.id,
                        "sourceFileId": page.sourceFileId,
                        "system": system,
                        "systemColor": style.stroke,
                        "systemColorApplied": system_color_applied,
                        "futureLine": vector.dashed,
                    },
                )
            )
    return objects


def _semantic_context_bounds_by_source(inventory: list[dict[str, Any]]) -> dict[str, list[BoundsDict]]:
    bounds_by_source: dict[str, list[BoundsDict]] = {}
    for item in inventory:
        source_bounds = item.get("sourceBounds")
        page = item.get("page")
        if not source_bounds or page is None:
            continue
        pad_x = 180.0 if item["kind"] == "line" else 92.0
        pad_y = 96.0 if item["kind"] == "line" else 72.0
        bounds_by_source.setdefault(page.sourceFileId, []).append(_expand_bounds(source_bounds, pad_x, pad_y))
    return bounds_by_source


def _semantic_detail_context_bounds_by_source(inventory: list[dict[str, Any]]) -> dict[str, list[BoundsDict]]:
    bounds_by_source: dict[str, list[BoundsDict]] = {}
    for item in inventory:
        if item["kind"] not in {"equipment", "instrument"}:
            continue
        source_bounds = item.get("sourceBounds")
        page = item.get("page")
        if not source_bounds or page is None:
            continue
        pad_x = 44.0 if item["kind"] == "equipment" else 32.0
        pad_y = 32.0 if item["kind"] == "equipment" else 28.0
        bounds_by_source.setdefault(page.sourceFileId, []).append(_expand_bounds(source_bounds, pad_x, pad_y))
    return bounds_by_source


def _semantic_tags(inventory: list[dict[str, Any]], system_color_map: SystemColorMap, relationship_graph: PidRelationshipGraph | None = None) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    for item in inventory:
        bounds = item.get("displayBounds") or item["bounds"]
        tag = item["tag"]
        system = item["system"]
        color = system_color_map.color_for(system)
        graph_node_id = _semantic_graph_node_id_for_item(item, relationship_graph)
        if item["kind"] == "equipment":
            symbol_profile = _symbol_profile_for_tag(tag)
            symbol_bounds = {"x": bounds["x"] - 20.0, "y": bounds["y"] - 10.0, "width": 42.0, "height": 28.0}
            objects.append(
                DrawingObject(
                    id=_semantic_object_id_for_item(item),
                    kind="symbol",
                    label=tag,
                    points=_rect_points(symbol_bounds),
                    bounds=symbol_bounds,
                    style=DrawingStyle(stroke=color, fill="#ffffff", strokeWidth=1.05, opacity=1.0),
                    sourceEvidenceIds=item["sourceEvidenceIds"],
                    locked=False,
                    metadata={
                        "semanticOverlay": True,
                        "semanticObject": True,
                        "symbolType": symbol_profile["symbolType"],
                        "symbolRegistry": symbol_profile["symbolRegistry"],
                        "symbolStandard": symbol_profile["symbolStandard"],
                        "symbolConfidence": symbol_profile["symbolConfidence"],
                        "tag": tag,
                        "system": system,
                        "systemColor": color,
                        "semanticGraphNodeId": graph_node_id,
                        "hideCenterLabel": True,
                        "labelSide": item.get("labelSide", "bottom"),
                        **_placement_metadata_for_item(item),
                    },
                )
            )
            label_bounds = _semantic_item_label_bounds_for_item(item)
            objects.append(_label(_object_id("semantic_equipment_label", item["id"]), tag, label_bounds, "#0f172a", 4.6, item["sourceEvidenceIds"], {"semanticOverlay": True, "semanticObjectLabel": True, "tag": tag, "system": system, "labelSide": item.get("labelSide", "bottom")}))
        elif item["kind"] == "instrument":
            symbol_bounds = {"x": bounds["x"] - 10.0, "y": bounds["y"] - 10.0, "width": 24.0, "height": 24.0}
            objects.append(
                DrawingObject(
                    id=_semantic_object_id_for_item(item),
                    kind="symbol",
                    label=tag,
                    points=_rect_points(symbol_bounds),
                    bounds=symbol_bounds,
                    style=DrawingStyle(stroke=color, fill="#ffffff", strokeWidth=0.95, opacity=1.0),
                    sourceEvidenceIds=item["sourceEvidenceIds"],
                    locked=False,
                    metadata={
                        "semanticOverlay": True,
                        "semanticObject": True,
                        "symbolType": "instrument",
                        "tag": tag,
                        "system": system,
                        "systemColor": color,
                        "semanticGraphNodeId": graph_node_id,
                        "hideCenterLabel": True,
                        "labelSide": item.get("labelSide", "right"),
                        **_placement_metadata_for_item(item),
                    },
                )
            )
            label_bounds = _semantic_item_label_bounds_for_item(item)
            objects.append(_label(_object_id("semantic_instrument_label", item["id"]), tag, label_bounds, "#0f172a", 4.1, item["sourceEvidenceIds"], {"semanticOverlay": True, "semanticObjectLabel": True, "tag": tag, "system": system, "labelSide": item.get("labelSide", "right")}))
        else:
            label_bounds = _semantic_line_label_bounds(item)
            objects.append(_label(_object_id("semantic_line_label", item["id"]), tag, label_bounds, color, 4.2, item["sourceEvidenceIds"], {"semanticOverlay": True, "semanticLineTag": True, "tag": tag, "system": system, "semanticGraphNodeId": graph_node_id}))
    return objects


def _semantic_graph_attachment_connectors(
    inventory: list[dict[str, Any]],
    system_color_map: SystemColorMap,
    relationship_graph: PidRelationshipGraph | None = None,
) -> list[DrawingObject]:
    if relationship_graph is None:
        return []

    item_by_graph_node_id: dict[str, dict[str, Any]] = {}
    for item in inventory:
        graph_node_id = _semantic_graph_node_id_for_item(item, relationship_graph)
        if graph_node_id:
            item_by_graph_node_id.setdefault(graph_node_id, item)

    objects: list[DrawingObject] = []
    emitted: set[str] = set()
    attachment_edges = [edge for edge in relationship_graph.edges if edge.kind in {"attached_to_line", "instrument_on_line"}]
    route_lanes = _route_lanes_for_attachment_edges(attachment_edges, item_by_graph_node_id)
    for edge in attachment_edges:
        source_item = item_by_graph_node_id.get(edge.sourceId)
        line_item = item_by_graph_node_id.get(edge.targetId)
        if source_item is None or line_item is None or line_item["kind"] != "line":
            continue
        object_id = _semantic_object_id_for_item(source_item)
        line_object_id = _semantic_line_label_object_id(line_item)
        if object_id == line_object_id:
            continue
        key = f"{edge.id}:{line_object_id}:{object_id}"
        if key in emitted:
            continue
        emitted.add(key)
        color = system_color_map.color_for(edge.system or source_item["system"] or line_item["system"])
        line_bounds = _semantic_line_label_bounds(line_item)
        symbol_bounds = _semantic_symbol_bounds_for_item(source_item)
        line_center = _bounds_center(line_bounds)
        symbol_center = _bounds_center(symbol_bounds)
        start, start_side = _snap_point_on_bounds_towards(line_bounds, symbol_center)
        end, end_side = _snap_point_on_bounds_towards(symbol_bounds, line_center)
        lane = route_lanes.get(edge.id, {"index": 0, "offset": 0.0, "total": 1, "key": f"{edge.targetId}:0"})
        points = _visio_like_connector_points(start, end, lane_offset=float(lane["offset"]), fanout_total=int(lane["total"]))
        objects.append(
            DrawingObject(
                id=_object_id("semantic_graph_attachment", edge.id, object_id),
                kind="connector",
                label="",
                points=points,
                bounds=_points_bounds(points, 2.0),
                style=DrawingStyle(stroke=color, fill="none", strokeWidth=0.62, opacity=0.84),
                sourceEvidenceIds=list(edge.sourceEvidenceIds),
                locked=False,
                metadata={
                    "semanticOverlay": True,
                    "semanticPipe": True,
                    "semanticGeneratedRoute": True,
                    "semanticConnectorRole": "graphAttachment",
                    "semanticRouteRole": "lineToNodeAttachment",
                    "semanticGraphEdgeId": edge.id,
                    "semanticGraphSourceNodeId": edge.sourceId,
                    "semanticGraphTargetNodeId": edge.targetId,
                    "startObjectId": line_object_id,
                    "endObjectId": object_id,
                    "startSnapSide": start_side,
                    "endSnapSide": end_side,
                    "routeLane": lane["key"],
                    "routeLaneIndex": lane["index"],
                    "routeStrategy": "lineTagFanout",
                    "hideCenterLabel": True,
                    "lineTag": edge.lineTag,
                    "system": edge.system,
                    "systemColor": color,
                    "relationshipConfidence": edge.confidence,
                },
            )
        )
    return objects


def _route_lanes_for_attachment_edges(
    edges: list[Any],
    item_by_graph_node_id: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[Any]] = {}
    for edge in edges:
        if edge.sourceId not in item_by_graph_node_id or edge.targetId not in item_by_graph_node_id:
            continue
        grouped.setdefault(edge.targetId, []).append(edge)

    lanes: dict[str, dict[str, Any]] = {}
    for target_id, target_edges in grouped.items():
        ordered = sorted(
            target_edges,
            key=lambda edge: (
                _bounds_center(_semantic_symbol_bounds_for_item(item_by_graph_node_id[edge.sourceId]))["y"],
                _bounds_center(_semantic_symbol_bounds_for_item(item_by_graph_node_id[edge.sourceId]))["x"],
                edge.id,
            ),
        )
        total = len(ordered)
        midpoint = (total - 1) / 2.0
        for index, edge in enumerate(ordered):
            lanes[edge.id] = {
                "index": index,
                "total": total,
                "offset": (index - midpoint) * 16.0,
                "key": f"{target_id}:{index}",
            }
    return lanes


def _semantic_graph_node_id_for_item(item: dict[str, Any], relationship_graph: PidRelationshipGraph | None) -> str | None:
    if relationship_graph is None:
        return None
    graph_kind = "line_tag" if item["kind"] == "line" else item["kind"]
    source_file_id = item["page"].sourceFileId
    page_number = item["page"].page
    tag = item["tag"]
    for node in relationship_graph.nodes:
        if node.kind == graph_kind and node.sourceFileId == source_file_id and node.page == page_number and node.tag == tag:
            return node.id
    return None


def _semantic_line_label_object_id(item: dict[str, Any]) -> str:
    return _object_id("label", _object_id("semantic_line_label", item["id"]))


def _semantic_line_label_bounds(item: dict[str, Any]) -> BoundsDict:
    bounds = item.get("displayBounds") or item["bounds"]
    return {"x": bounds["x"], "y": bounds["y"] - 8.0, "width": min(max(bounds["width"], 58.0), 132.0), "height": 10.0}


def _snap_point_on_bounds_towards(bounds: BoundsDict, target: Point) -> tuple[Point, str]:
    center = _bounds_center(bounds)
    dx = target["x"] - center["x"]
    dy = target["y"] - center["y"]
    if abs(dx) >= abs(dy):
        if dx >= 0:
            return {"x": bounds["x"] + bounds["width"], "y": center["y"]}, "right"
        return {"x": bounds["x"], "y": center["y"]}, "left"
    if dy >= 0:
        return {"x": center["x"], "y": bounds["y"] + bounds["height"]}, "bottom"
    return {"x": center["x"], "y": bounds["y"]}, "top"


def _visio_like_connector_points(start: Point, end: Point, *, lane_offset: float = 0.0, fanout_total: int = 1) -> list[Point]:
    if fanout_total <= 1 and (abs(start["x"] - end["x"]) < 1.0 or abs(start["y"] - end["y"]) < 1.0):
        return [start, end]
    horizontal_first = abs(end["x"] - start["x"]) >= abs(end["y"] - start["y"])
    if horizontal_first:
        mid_x = start["x"] + (end["x"] - start["x"]) / 2.0 + lane_offset
        return _dedupe_points([start, {"x": mid_x, "y": start["y"]}, {"x": mid_x, "y": end["y"]}, end])
    mid_y = start["y"] + (end["y"] - start["y"]) / 2.0 + lane_offset
    return _dedupe_points([start, {"x": start["x"], "y": mid_y}, {"x": end["x"], "y": mid_y}, end])


def _dedupe_points(points: list[Point]) -> list[Point]:
    deduped: list[Point] = []
    for point in points:
        if deduped and abs(deduped[-1]["x"] - point["x"]) < 0.5 and abs(deduped[-1]["y"] - point["y"]) < 0.5:
            continue
        deduped.append(point)
    return deduped


def _semantic_system_backbones(inventory: list[dict[str, Any]], system_color_map: SystemColorMap) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    by_system: dict[str, list[dict[str, Any]]] = {}
    line_tags_by_system: dict[str, list[str]] = {}
    for item in inventory:
        system = item["system"]
        if system == "DEFAULT":
            continue
        if item["kind"] in {"equipment", "instrument"}:
            by_system.setdefault(system, []).append(item)
        elif item["kind"] == "line":
            line_tags_by_system.setdefault(system, []).append(item["tag"])

    for system, items in sorted(by_system.items(), key=lambda entry: (min(_item_center(item)["y"] for item in entry[1]), entry[0])):
        color = system_color_map.color_for(system)
        cluster_infos: list[dict[str, Any]] = []
        for cluster_index, cluster_items in enumerate(_route_clusters_for_system(items)):
            bus_points, orientation = _system_bus_geometry(cluster_items)
            start, end = bus_points[0], bus_points[-1]
            bus = DrawingObject(
                id=_object_id("semantic_system_backbone", system, str(cluster_index), str(len(cluster_items)), str(round(start["x"])), str(round(start["y"]))),
                kind="pipe",
                label="",
                points=bus_points,
                bounds=_points_bounds(bus_points, 2.0),
                style=DrawingStyle(stroke=color, fill="none", strokeWidth=1.05, opacity=0.98),
                sourceEvidenceIds=_source_ids_for_items(cluster_items),
                locked=False,
                metadata={
                    "semanticOverlay": True,
                    "semanticPipe": True,
                    "semanticGeneratedRoute": True,
                    "semanticRouteRole": "systemBackbone",
                    "semanticRouteCluster": cluster_index,
                    "system": system,
                    "systemColor": color,
                },
            )
            objects.append(bus)
            cluster_infos.append({"bus": bus, "orientation": orientation, "anchor": _midpoint(start, end), "items": cluster_items})

            line_tags = _unique(line_tags_by_system.get(system, []))[: max(2, min(4, len(cluster_items)))]
            for index, tag in enumerate(line_tags):
                if orientation == "horizontal":
                    label_x = start["x"] + 18.0 + index * 108.0
                    label_bounds = {"x": min(label_x, end["x"] - 96.0), "y": start["y"] - 13.0, "width": 104.0, "height": 11.0}
                else:
                    label_bounds = {"x": start["x"] + 8.0, "y": start["y"] + 20.0 + index * 28.0, "width": 108.0, "height": 11.0}
                objects.append(
                    _label(
                        _object_id("semantic_system_line_label", system, tag, str(cluster_index), str(index)),
                        tag,
                        label_bounds,
                        color,
                        4.8,
                        _source_ids_for_items(cluster_items),
                        {"semanticOverlay": True, "semanticLineTag": True, "semanticGeneratedRoute": True, "tag": tag, "system": system, "semanticRouteCluster": cluster_index},
                    )
                )

            for index, item in enumerate(sorted(cluster_items, key=lambda item: (_item_center(item)["x"], _item_center(item)["y"], item["tag"]))):
                center = _item_center(item)
                object_id = _semantic_object_id_for_item(item)
                if orientation == "horizontal":
                    attach = {"x": center["x"], "y": start["y"]}
                    target, snap_side = _snap_attachment_for_bus(item, "horizontal", start["y"])
                else:
                    attach = {"x": start["x"], "y": center["y"]}
                    target, snap_side = _snap_attachment_for_bus(item, "vertical", start["x"])
                points = _branch_points_from_bus(attach, target)
                if abs(points[0]["x"] - points[-1]["x"]) < 1.0 and abs(points[0]["y"] - points[-1]["y"]) < 1.0:
                    continue
                objects.append(
                    DrawingObject(
                        id=_object_id("semantic_system_branch", system, object_id, str(cluster_index), str(index)),
                        kind="connector",
                        label="",
                        points=points,
                        bounds=_points_bounds(points, 2.0),
                        style=DrawingStyle(stroke=color, fill="none", strokeWidth=0.78, opacity=0.94),
                        sourceEvidenceIds=item["sourceEvidenceIds"],
                        locked=False,
                        metadata={
                            "semanticOverlay": True,
                            "semanticPipe": True,
                            "semanticGeneratedRoute": True,
                            "semanticRouteRole": "equipmentBranch" if item["kind"] == "equipment" else "instrumentBranch",
                            "semanticRouteCluster": cluster_index,
                            "endObjectId": object_id,
                            "endSnapSide": snap_side,
                            "system": system,
                            "systemColor": color,
                        },
                    )
                )

        if len(cluster_infos) > 1:
            anchors = [info["anchor"] for info in sorted(cluster_infos, key=lambda info: (info["anchor"]["x"], info["anchor"]["y"]))]
            trunk_points, trunk_orientation = _system_corridor_points(anchors)
            objects.append(
                DrawingObject(
                    id=_object_id("semantic_system_interconnect", system, str(len(cluster_infos))),
                    kind="pipe",
                    label="",
                    points=trunk_points,
                    bounds=_points_bounds(trunk_points, 2.0),
                    style=DrawingStyle(stroke=color, fill="none", strokeWidth=0.95, opacity=0.92),
                    sourceEvidenceIds=_source_ids_for_items(items),
                    locked=False,
                    metadata={
                        "semanticOverlay": True,
                        "semanticPipe": True,
                        "semanticGeneratedRoute": True,
                        "semanticRouteRole": "systemInterconnect",
                        "routeStrategy": "sharedCorridor",
                        "routeOrientation": trunk_orientation,
                        "system": system,
                        "systemColor": color,
                    },
                )
            )
            for branch_index, anchor in enumerate(anchors):
                snap = _corridor_snap_point(anchor, trunk_points, trunk_orientation)
                if _point_distance(anchor, snap) < 1.0:
                    continue
                branch_points = _dedupe_points([anchor, snap])
                objects.append(
                    DrawingObject(
                        id=_object_id("semantic_system_interconnect_branch", system, str(len(cluster_infos)), str(branch_index)),
                        kind="connector",
                        label="",
                        points=branch_points,
                        bounds=_points_bounds(branch_points, 2.0),
                        style=DrawingStyle(stroke=color, fill="none", strokeWidth=0.72, opacity=0.88),
                        sourceEvidenceIds=_source_ids_for_items(items),
                        locked=False,
                        metadata={
                            "semanticOverlay": True,
                            "semanticPipe": True,
                            "semanticGeneratedRoute": True,
                            "semanticRouteRole": "systemInterconnectBranch",
                            "routeStrategy": "sharedCorridorBranch",
                            "routeOrientation": trunk_orientation,
                            "system": system,
                            "systemColor": color,
                        },
                    )
                )
    return objects


def _semantic_system_regions(inventory: list[dict[str, Any]], system_color_map: SystemColorMap, source_ids: list[str]) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    by_system: dict[str, list[dict[str, Any]]] = {}
    for item in inventory:
        if item["kind"] not in {"equipment", "instrument"} or item["system"] == "DEFAULT":
            continue
        by_system.setdefault(item["system"], []).append(item)

    for system, items in sorted(by_system.items(), key=lambda entry: (min(_item_center(item)["y"] for item in entry[1]), entry[0])):
        item_bounds = [_semantic_symbol_bounds_for_item(item) for item in items]
        min_x = min(bounds["x"] for bounds in item_bounds) - 34.0
        min_y = min(bounds["y"] for bounds in item_bounds) - 32.0
        max_x = max(bounds["x"] + bounds["width"] for bounds in item_bounds) + 48.0
        max_y = max(bounds["y"] + bounds["height"] for bounds in item_bounds) + 54.0
        color = system_color_map.color_for(system)
        region_bounds = {"x": min_x, "y": min_y, "width": max_x - min_x, "height": max_y - min_y}
        objects.append(
            DrawingObject(
                id=_object_id("semantic_system_region", system, str(round(min_x)), str(round(min_y))),
                kind="region",
                label="",
                points=_rect_points(region_bounds),
                bounds=region_bounds,
                style=DrawingStyle(stroke=color, fill=color, strokeWidth=0.75, opacity=0.055, dash=[8.0, 5.0]),
                sourceEvidenceIds=source_ids,
                locked=False,
                metadata={
                    "semanticOverlay": True,
                    "semanticSystemRegion": True,
                    "hideCenterLabel": True,
                    "system": system,
                    "systemColor": color,
                },
            )
        )
        objects.append(
            _label(
                _object_id("semantic_system_region_label", system, str(round(min_x)), str(round(min_y))),
                display_system_label(system),
                {"x": min_x + 10.0, "y": min_y + 8.0, "width": 180.0, "height": 14.0},
                color,
                7.2,
                source_ids,
                {"semanticOverlay": True, "semanticSystemRegionLabel": True, "system": system, "systemColor": color},
            )
        )
    return objects


def _route_clusters_for_system(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    clusters_by_source: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        clusters_by_source.setdefault(item["page"].sourceFileId, []).append(item)
    clusters: list[list[dict[str, Any]]] = []
    for source_items in clusters_by_source.values():
        clusters.extend(_spatial_route_clusters(source_items))
    return sorted(clusters, key=lambda cluster: (min(_item_center(item)["x"] for item in cluster), min(_item_center(item)["y"] for item in cluster)))


def _spatial_route_clusters(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if len(items) <= 3:
        return [items]
    remaining = set(range(len(items)))
    centers = [_item_center(item) for item in items]
    clusters: list[list[dict[str, Any]]] = []
    while remaining:
        start_index = min(remaining)
        remaining.remove(start_index)
        queue = [start_index]
        component = [start_index]
        while queue:
            current = queue.pop(0)
            linked = [
                index
                for index in list(remaining)
                if _same_equipment_pocket(centers[current], centers[index])
            ]
            for index in linked:
                remaining.remove(index)
                queue.append(index)
                component.append(index)
        component_items = [items[index] for index in component]
        clusters.extend(_split_large_route_cluster(component_items))
    return clusters


def _same_equipment_pocket(left: Point, right: Point) -> bool:
    dx = abs(left["x"] - right["x"])
    dy = abs(left["y"] - right["y"])
    return dx <= 520.0 and dy <= 440.0 and (dx * dx + dy * dy) ** 0.5 <= 680.0


def _split_large_route_cluster(items: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    if len(items) <= 16:
        return [items]
    centers = [_item_center(item) for item in items]
    min_x = min(point["x"] for point in centers)
    max_x = max(point["x"] for point in centers)
    min_y = min(point["y"] for point in centers)
    max_y = max(point["y"] for point in centers)
    if max(max_x - min_x, max_y - min_y) < 920.0:
        return [items]
    split_horizontal = (max_x - min_x) >= (max_y - min_y)
    ordered = sorted(items, key=lambda item: (_item_center(item)["x" if split_horizontal else "y"], _item_center(item)["y" if split_horizontal else "x"]))
    midpoint = len(ordered) // 2
    return [ordered[:midpoint], ordered[midpoint:]]


def _system_bus_geometry(items: list[dict[str, Any]]) -> tuple[list[Point], str]:
    centers = [_item_center(item) for item in items]
    min_x = min(point["x"] for point in centers)
    max_x = max(point["x"] for point in centers)
    min_y = min(point["y"] for point in centers)
    max_y = max(point["y"] for point in centers)
    horizontal = len(items) == 1 or (max_x - min_x) >= (max_y - min_y) * 0.72
    if horizontal:
        bus_y = _system_bus_lane(items, orientation="horizontal")
        return [{"x": min_x - 38.0, "y": bus_y}, {"x": max_x + 38.0, "y": bus_y}], "horizontal"
    bus_x = _system_bus_lane(items, orientation="vertical")
    return [{"x": bus_x, "y": min_y - 34.0}, {"x": bus_x, "y": max_y + 34.0}], "vertical"


def _system_bus_lane(items: list[dict[str, Any]], *, orientation: str) -> float:
    centers = [_item_center(item) for item in items]
    protected = [_semantic_protected_bounds_for_item(item, item.get("displayBounds") or item["bounds"]) for item in items]
    if orientation == "horizontal":
        median_y = _median([point["y"] for point in centers])
        min_y = min(bounds["y"] for bounds in protected)
        max_y = max(bounds["y"] + bounds["height"] for bounds in protected)
        candidates = [min_y - 18.0, max_y + 18.0, median_y]
        start = {"x": min(point["x"] for point in centers) - 38.0, "y": 0.0}
        end = {"x": max(point["x"] for point in centers) + 38.0, "y": 0.0}
        return min(
            candidates,
            key=lambda y: (
                _bus_lane_crossings({**start, "y": y}, {**end, "y": y}, protected),
                abs(y - median_y) if y not in {min_y - 18.0, max_y + 18.0} else abs(y - median_y) * 0.82,
            ),
        )

    median_x = _median([point["x"] for point in centers])
    min_x = min(bounds["x"] for bounds in protected)
    max_x = max(bounds["x"] + bounds["width"] for bounds in protected)
    candidates = [min_x - 18.0, max_x + 18.0, median_x]
    start = {"x": 0.0, "y": min(point["y"] for point in centers) - 34.0}
    end = {"x": 0.0, "y": max(point["y"] for point in centers) + 34.0}
    return min(
        candidates,
        key=lambda x: (
            _bus_lane_crossings({**start, "x": x}, {**end, "x": x}, protected),
            abs(x - median_x) if x not in {min_x - 18.0, max_x + 18.0} else abs(x - median_x) * 0.82,
        ),
    )


def _bus_lane_crossings(start: Point, end: Point, protected: list[BoundsDict]) -> int:
    return sum(1 for bounds in protected if _segment_intersects_bounds(start, end, bounds))


def _branch_points_from_bus(attach: Point, target: Point) -> list[Point]:
    if abs(attach["x"] - target["x"]) < 1.0 or abs(attach["y"] - target["y"]) < 1.0:
        return [attach, target]
    return [attach, {"x": attach["x"], "y": target["y"]}, target]


def _orthogonal_chain(anchors: list[Point]) -> list[Point]:
    if len(anchors) <= 1:
        return anchors
    points = [anchors[0]]
    current = anchors[0]
    for anchor in anchors[1:]:
        points.extend(_orthogonal_points(current, anchor)[1:])
        current = anchor
    return points


def _system_corridor_points(anchors: list[Point], lane_offset: float = 0.0) -> tuple[list[Point], str]:
    if len(anchors) <= 1:
        return list(anchors), "point"
    min_x = min(point["x"] for point in anchors)
    max_x = max(point["x"] for point in anchors)
    min_y = min(point["y"] for point in anchors)
    max_y = max(point["y"] for point in anchors)
    horizontal = (max_x - min_x) >= (max_y - min_y) * 0.82
    if horizontal:
        ordered = sorted(anchors, key=lambda point: (point["x"], point["y"]))
        corridor_y = _median([point["y"] for point in anchors]) + lane_offset
        points: list[Point] = [ordered[0]]
        if abs(ordered[0]["y"] - corridor_y) >= 1.0:
            points.append({"x": ordered[0]["x"], "y": corridor_y})
        for anchor in ordered[1:-1]:
            points.append({"x": anchor["x"], "y": corridor_y})
        if abs(ordered[-1]["y"] - corridor_y) >= 1.0:
            points.append({"x": ordered[-1]["x"], "y": corridor_y})
        points.append(ordered[-1])
        return _dedupe_points(points), "horizontal"

    ordered = sorted(anchors, key=lambda point: (point["y"], point["x"]))
    corridor_x = _median([point["x"] for point in anchors]) + lane_offset
    points = [ordered[0]]
    if abs(ordered[0]["x"] - corridor_x) >= 1.0:
        points.append({"x": corridor_x, "y": ordered[0]["y"]})
    for anchor in ordered[1:-1]:
        points.append({"x": corridor_x, "y": anchor["y"]})
    if abs(ordered[-1]["x"] - corridor_x) >= 1.0:
        points.append({"x": corridor_x, "y": ordered[-1]["y"]})
    points.append(ordered[-1])
    return _dedupe_points(points), "vertical"


def _corridor_snap_point(anchor: Point, corridor_points: list[Point], orientation: str) -> Point:
    if orientation == "horizontal":
        y_values = [point["y"] for point in corridor_points[1:-1]] or [point["y"] for point in corridor_points]
        return {"x": anchor["x"], "y": _median(y_values)}
    if orientation == "vertical":
        x_values = [point["x"] for point in corridor_points[1:-1]] or [point["x"] for point in corridor_points]
        return {"x": _median(x_values), "y": anchor["y"]}
    return dict(anchor)


def _semantic_continuations(
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    candidate_by_id: dict[str, ContinuationCandidate],
    inventory: list[dict[str, Any]],
    system_color_map: SystemColorMap,
    tile_by_source: dict[str, BoundsDict],
    source_bounds_by_source: dict[str, BoundsDict],
    source_paths: dict[str, str],
    *,
    use_semantic_anchors: bool = False,
    relationship_graph: PidRelationshipGraph | None = None,
) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    page_by_source = {page.sourceFileId: page for page in pages}
    semantic_anchor_by_candidate_id = _semantic_candidate_anchor_map(inventory, candidate_by_id) if use_semantic_anchors else {}
    loaded_sheet_refs_by_source = _loaded_sheet_refs_by_source(pages, source_paths=source_paths)
    loaded_sheet_refs = {ref for refs in loaded_sheet_refs_by_source.values() for ref in refs}
    matched_candidate_ids = {match.sourceCandidateId for match in matches if match.status != "rejected"} | {match.targetCandidateId for match in matches if match.status != "rejected"}
    for match in sorted(matches, key=lambda item: (-item.score, item.id)):
        if match.status == "rejected":
            continue
        source = candidate_by_id.get(match.sourceCandidateId)
        target = candidate_by_id.get(match.targetCandidateId)
        if not source or not target:
            continue
        start = semantic_anchor_by_candidate_id.get(source.id) or _candidate_point(source, page_by_source, tile_by_source, source_bounds_by_source)
        end = semantic_anchor_by_candidate_id.get(target.id) or _candidate_point(target, page_by_source, tile_by_source, source_bounds_by_source)
        if not start or not end:
            continue
        line_tag = (source.lineTag or target.lineTag or "").upper()
        if use_semantic_anchors and not line_tag:
            continue
        graph_edge = relationship_graph.edge_for_match(match.id) if relationship_graph is not None else None
        system = _semantic_system_for_flow_text(source.system or target.system or line_tag, system_color_map)
        color = system_color_map.color_for(system)
        start_id = _object_id("semantic_endpoint", source.id)
        end_id = _object_id("semantic_endpoint", target.id)
        for endpoint_id, candidate, point in ((start_id, source, start), (end_id, target, end)):
            bounds = {"x": point["x"] - 4.0, "y": point["y"] - 4.0, "width": 8.0, "height": 8.0}
            objects.append(
                DrawingObject(
                    id=endpoint_id,
                    kind="symbol",
                    label="",
                    points=_rect_points(bounds),
                    bounds=bounds,
                    style=DrawingStyle(stroke=color, fill=color, strokeWidth=0.6, opacity=0.0),
                    sourceEvidenceIds=[candidate.id],
                    locked=False,
                    metadata={"semanticOverlay": True, "semanticEndpoint": True, "symbolType": "instrument", "system": system, "systemColor": color},
                )
            )
        connector = DrawingObject(
            id=_object_id("semantic_connector", match.id),
            kind="connector",
            label=line_tag,
            points=_orthogonal_points(start, end),
            bounds=_points_bounds(_orthogonal_points(start, end), 2.0),
            style=DrawingStyle(stroke=color, fill="none", strokeWidth=1.05, opacity=0.98),
            sourceEvidenceIds=[source.id, target.id],
            locked=False,
            metadata={
                "semanticOverlay": True,
                "semanticConnectorRole": "matchedContinuation",
                "stitchedContinuationMatchId": match.id,
                "sourceCandidateId": source.id,
                "targetCandidateId": target.id,
                "startObjectId": start_id,
                "endObjectId": end_id,
                "lineTag": line_tag,
                "system": system,
                "systemColor": color,
                "semanticGraphEdgeId": graph_edge.id if graph_edge is not None else None,
                "semanticGraphSourceNodeId": graph_edge.sourceId if graph_edge is not None else None,
                "semanticGraphTargetNodeId": graph_edge.targetId if graph_edge is not None else None,
            },
        )
        objects.append(connector)
        mid = _midpoint(start, end)
        objects.append(_label(_object_id("semantic_connector_label", match.id), line_tag, {"x": mid["x"] - 56.0, "y": mid["y"] - 12.0, "width": 112.0, "height": 12.0}, color, 5.0, [source.id, target.id], {"semanticOverlay": True, "semanticConnectorLabel": True, "lineTag": line_tag, "system": system}))

    for candidate in candidates:
        if candidate.id in matched_candidate_ids:
            continue
        if not _should_render_unresolved_pointer(candidate, loaded_sheet_refs, loaded_sheet_refs_by_source.get(candidate.sourceFileId, set())):
            continue
        point = semantic_anchor_by_candidate_id.get(candidate.id) or _candidate_point(candidate, page_by_source, tile_by_source, source_bounds_by_source)
        if not point:
            continue
        line_tag = candidate.lineTag.upper() if candidate.lineTag else ""
        system = _semantic_system_for_flow_text(candidate.system or line_tag or candidate.label, system_color_map)
        color = system_color_map.color_for(system)
        bounds = {"x": point["x"] - 22.0, "y": point["y"] - 10.0, "width": 58.0, "height": 20.0}
        pointer_id = _object_id("semantic_unresolved_offpage", candidate.id)
        leader_points = _unresolved_pointer_leader_points(candidate, bounds, inventory, system)
        if leader_points:
            objects.append(
                DrawingObject(
                    id=_object_id("semantic_unresolved_leader", candidate.id),
                    kind="connector",
                    label="",
                    points=leader_points,
                    bounds=_points_bounds(leader_points, 2.0),
                    style=DrawingStyle(stroke=color, fill="none", strokeWidth=0.74, opacity=0.9),
                    sourceEvidenceIds=[candidate.id],
                    locked=False,
                    metadata={
                        "semanticOverlay": True,
                        "semanticPipe": True,
                        "semanticGeneratedRoute": True,
                        "semanticConnectorRole": "unresolvedContinuationLeader",
                        "semanticRouteRole": "offpageLeader",
                        "endObjectId": pointer_id,
                        "sourceCandidateId": candidate.id,
                        "lineTag": line_tag,
                        "sheetRef": candidate.sheetRef,
                        "system": system,
                        "systemColor": color,
                    },
                )
            )
        objects.append(
            DrawingObject(
                id=pointer_id,
                kind="symbol",
                label=line_tag or candidate.label,
                points=_rect_points(bounds),
                bounds=bounds,
                style=DrawingStyle(stroke="#111827", fill="#ffffff", strokeWidth=1.0, opacity=1.0),
                sourceEvidenceIds=[candidate.id],
                locked=False,
                metadata={
                    "semanticOverlay": True,
                    "semanticConnectorRole": "unresolvedContinuation",
                    "symbolType": "offpage",
                    "sourceCandidateId": candidate.id,
                    "lineTag": line_tag,
                    "sheetRef": candidate.sheetRef,
                    "system": system,
                    "systemColor": color,
                },
            )
        )
        objects.append(_label(_object_id("semantic_unresolved_label", candidate.id), line_tag or candidate.label, {"x": point["x"] + 40.0, "y": point["y"] - 8.0, "width": 150.0, "height": 12.0}, color, 5.0, [candidate.id], {"semanticOverlay": True, "semanticConnectorLabel": True, "lineTag": line_tag, "system": system}))
    return objects


def _unresolved_pointer_leader_points(
    candidate: ContinuationCandidate,
    pointer_bounds: BoundsDict,
    inventory: list[dict[str, Any]],
    system: str,
) -> list[Point]:
    attach, fallback = _unresolved_pointer_attach_and_fallback(candidate, pointer_bounds)
    nearest = _nearest_unresolved_pointer_anchor(candidate, attach, inventory, system)
    if nearest is None:
        return _dedupe_points([fallback, attach])
    return _visio_like_connector_points(nearest, attach)


def _unresolved_pointer_attach_and_fallback(candidate: ContinuationCandidate, bounds: BoundsDict) -> tuple[Point, Point]:
    center = _bounds_center(bounds)
    edge = candidate.edge or ""
    if edge == "right":
        attach = {"x": bounds["x"], "y": center["y"]}
        fallback = {"x": attach["x"] - 126.0, "y": attach["y"]}
    elif edge == "left":
        attach = {"x": bounds["x"] + bounds["width"], "y": center["y"]}
        fallback = {"x": attach["x"] + 126.0, "y": attach["y"]}
    elif edge == "top":
        attach = {"x": center["x"], "y": bounds["y"] + bounds["height"]}
        fallback = {"x": attach["x"], "y": attach["y"] + 96.0}
    elif edge == "bottom":
        attach = {"x": center["x"], "y": bounds["y"]}
        fallback = {"x": attach["x"], "y": attach["y"] - 96.0}
    else:
        attach = {"x": bounds["x"], "y": center["y"]}
        fallback = {"x": attach["x"] - 96.0, "y": attach["y"]}
    return attach, fallback


def _nearest_unresolved_pointer_anchor(
    candidate: ContinuationCandidate,
    attach: Point,
    inventory: list[dict[str, Any]],
    system: str,
) -> Point | None:
    candidates: list[tuple[float, Point]] = []
    for item in inventory:
        if item["system"] != system:
            continue
        if candidate.id in item.get("sourceEvidenceIds", []):
            continue
        if item["page"].sourceFileId != candidate.sourceFileId and system == "DEFAULT":
            continue
        bounds = item.get("displayBounds") or item["bounds"]
        center = _bounds_center(bounds)
        page_penalty = 0.0 if item["page"].sourceFileId == candidate.sourceFileId else 160.0
        kind_penalty = 0.0 if item["kind"] == "line" else 70.0
        distance = abs(center["x"] - attach["x"]) + abs(center["y"] - attach["y"]) * 0.75 + page_penalty + kind_penalty
        candidates.append((distance, center))
    if not candidates:
        return None
    distance, center = min(candidates, key=lambda item: item[0])
    if distance > 320.0:
        return None
    return center


def _semantic_candidate_anchor_map(inventory: list[dict[str, Any]], candidate_by_id: dict[str, ContinuationCandidate]) -> dict[str, Point]:
    anchors: dict[str, Point] = {}
    for item in inventory:
        if item["kind"] != "line":
            continue
        for evidence_id in item.get("sourceEvidenceIds", []):
            if evidence_id in candidate_by_id:
                anchors[evidence_id] = _bounds_center(item.get("displayBounds") or item["bounds"])
    return anchors


def _semantic_system_for_tag(kind: str, tag: str, system_color_map: SystemColorMap) -> str:
    inferred = system_for_text(tag, system_color_map)
    if inferred != "DEFAULT":
        return _normalize_semantic_system(inferred, system_color_map)
    text = tag.upper()
    for key in system_color_map.entries:
        canonical = canonical_system(key)
        if canonical and canonical != "DEFAULT" and re.search(rf"(^|[^A-Z0-9]){re.escape(canonical)}($|[^A-Z0-9])", text):
            return _normalize_semantic_system(canonical, system_color_map)
    token_map = {
        "CHW": ("CHW", "CHWS", "CHWR", "TCHW", "TCHWS", "TCHWR"),
        "CW": ("CW", "CWS", "CWR", "CTW"),
        "HHW": ("HHW", "HHWS", "HHWR", "HWS", "HWR"),
        "HRW": ("HRW", "HRWS", "HRWR"),
        "CDA": ("CDA", "CA", "IA"),
        "DOMW": ("DOMW", "PW"),
        "SSW": ("SSW", "SHW"),
    }
    for system, tokens in token_map.items():
        if system not in system_color_map.entries:
            continue
        if any(re.search(rf"(^|[^A-Z0-9]){token}($|[^A-Z0-9])", text) for token in tokens):
            return system
    return "DEFAULT"


def _semantic_system_for_flow_text(text: str, system_color_map: SystemColorMap) -> str:
    inferred = _normalize_semantic_system(system_for_text(text, system_color_map), system_color_map)
    if inferred != "DEFAULT":
        return inferred
    return _semantic_system_for_tag("line", text, system_color_map)


def _normalize_semantic_system(system: str, system_color_map: SystemColorMap) -> str:
    normalized = canonical_system(system) or system.upper()
    if normalized == "CA" and "CDA" in system_color_map.entries:
        return "CDA"
    return normalized


def _is_noise_unresolved_candidate(candidate: ContinuationCandidate) -> bool:
    text = f"{candidate.label} {candidate.evidenceText}".upper()
    return any(
        phrase in text
        for phrase in (
            "ARE SUBJECT",
            "LOSS TO PERSON",
            "PROPERTY AS A RESULT",
            "VERIFICATION",
            "WARRANTY",
            "COORDINATION",
            "FIELD VERIFY",
            "GENERAL NOTE",
            "KEYED NOTE",
            "ADD THERMOMETER",
            "ADD PRESSURE",
            "ADD DIFFERENTIAL",
        )
    )


def _should_render_unresolved_pointer(candidate: ContinuationCandidate, loaded_refs: set[str], own_refs: set[str]) -> bool:
    if _is_noise_unresolved_candidate(candidate):
        return False
    refs = _candidate_sheet_refs(candidate)
    if any(ref in loaded_refs for ref in refs):
        return False
    if refs:
        return True
    if candidate.direction not in {"to", "from"} or candidate.edge not in {"left", "right", "top", "bottom"}:
        return False
    text = f"{candidate.label} {candidate.evidenceText}".upper()
    if not re.search(r"\b(?:TO|FROM)\b", text):
        return False
    return bool(candidate.lineTag or re.search(r"\b(?:SYSTEM|BUILDING|DISTRIBUTION|RETURN|SUPPLY|TANK|LOOP|HEADER)\b", text))


def _loaded_sheet_refs_by_source(pages: list[PageEvidence], source_paths: dict[str, str]) -> dict[str, set[str]]:
    refs_by_source: dict[str, set[str]] = {}
    for page in pages:
        refs = refs_by_source.setdefault(page.sourceFileId, set())
        for span in page.textSpans:
            refs.update(_sheet_refs_in_text(span.text))
        source_path = source_paths.get(page.sourceFileId)
        if source_path:
            refs.update(_sheet_refs_in_text(Path(source_path).stem))
    return refs_by_source


def _candidate_sheet_refs(candidate: ContinuationCandidate) -> set[str]:
    refs: set[str] = set()
    for value in (candidate.sheetRef, candidate.label, candidate.evidenceText):
        if value:
            refs.update(_sheet_refs_in_text(value))
    return refs


def _sheet_refs_in_text(text: str) -> set[str]:
    refs: set[str] = set()
    for match in SHEET_REF_RE.finditer(text or ""):
        ref = _normalize_sheet_ref(match.group(0))
        if ref:
            refs.add(ref)
    return refs


def _normalize_sheet_ref(value: str) -> str:
    return re.sub(r"[^A-Z0-9-]+$", "", value.upper().strip())


def _assign_nearby_systems(inventory: list[dict[str, Any]]) -> None:
    non_default = [item for item in inventory if item["system"] != "DEFAULT"]
    if not non_default:
        return
    dominant_by_page: dict[str, str] = {}
    for item in non_default:
        page_id = item["page"].sourceFileId
        dominant_by_page.setdefault(page_id, item["system"])

    for item in inventory:
        if item["system"] != "DEFAULT" or item["kind"] not in {"equipment", "instrument"}:
            continue
        own_center = _bounds_center(item.get("sourceBounds") or item["bounds"])
        candidates = [
            candidate
            for candidate in non_default
            if candidate["page"].sourceFileId == item["page"].sourceFileId
        ] or non_default
        nearest: tuple[float, str] | None = None
        for candidate in candidates:
            candidate_center = _bounds_center(candidate.get("sourceBounds") or candidate["bounds"])
            distance = abs(candidate_center["x"] - own_center["x"]) * 0.45 + abs(candidate_center["y"] - own_center["y"])
            if nearest is None or distance < nearest[0]:
                nearest = (distance, candidate["system"])
        if nearest and nearest[0] <= 520.0:
            item["system"] = nearest[1]
        else:
            item["system"] = dominant_by_page.get(item["page"].sourceFileId, "DEFAULT")


def _placed_semantic_inventory(inventory: list[dict[str, Any]], *, compose: bool = False) -> list[dict[str, Any]]:
    if compose:
        return _composed_semantic_inventory(inventory)

    by_system: dict[str, list[dict[str, Any]]] = {}
    for item in inventory:
        by_system.setdefault(item["system"], []).append(item)

    expanded: dict[int, BoundsDict] = {}
    for system, items in by_system.items():
        if system == "DEFAULT":
            for item in items:
                expanded[id(item)] = dict(item["bounds"])
            continue
        centers = [_bounds_center(item["bounds"]) for item in items if item["kind"] in {"equipment", "instrument"}]
        if not centers:
            for item in items:
                expanded[id(item)] = dict(item["bounds"])
            continue
        centroid = {"x": sum(point["x"] for point in centers) / len(centers), "y": sum(point["y"] for point in centers) / len(centers)}
        for item in items:
            bounds = dict(item["bounds"])
            if item["kind"] in {"equipment", "instrument"}:
                center = _bounds_center(bounds)
                bounds["x"] += (center["x"] - centroid["x"]) * 0.055
                bounds["y"] += (center["y"] - centroid["y"]) * 0.055
            expanded[id(item)] = bounds

    placed: list[dict[str, Any]] = []
    occupied: list[BoundsDict] = []
    for item in sorted(inventory, key=lambda item: (item["page"].sourceFileId, item["system"], item["bounds"]["y"], item["bounds"]["x"], item["kind"])):
        copied = dict(item)
        bounds = expanded.get(id(item), dict(item["bounds"]))
        if item["kind"] in {"equipment", "instrument"}:
            bounds = _deconflict_item_bounds(item, bounds, occupied)
            occupied.append(_semantic_protected_bounds_for_item(item, bounds))
        copied["displayBounds"] = bounds
        placed.append(copied)
    return _apply_source_cluster_breathing(placed)


def _apply_source_cluster_breathing(placed: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Gently separate dense source-derived symbol clusters without losing page geometry."""

    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in placed:
        if item["kind"] not in {"equipment", "instrument"}:
            continue
        groups.setdefault((item["page"].sourceFileId, item["system"]), []).append(item)

    desired_by_id: dict[str, BoundsDict] = {}
    for (_source_id, _system), items in groups.items():
        if len(items) < 3:
            continue
        source_centers = [_bounds_center(item.get("sourceBounds") or item["bounds"]) for item in items]
        dense_indexes = [
            index
            for index, center in enumerate(source_centers)
            if sum(1 for other in source_centers if _point_distance(center, other) <= 130.0) >= 3
        ]
        if not dense_indexes:
            continue
        centroid = {
            "x": sum(source_centers[index]["x"] for index in dense_indexes) / len(dense_indexes),
            "y": sum(source_centers[index]["y"] for index in dense_indexes) / len(dense_indexes),
        }
        for dense_order, item_index in enumerate(dense_indexes):
            item = items[item_index]
            source_center = source_centers[item_index]
            display_bounds = dict(item.get("displayBounds") or item["bounds"])
            dx = source_center["x"] - centroid["x"]
            dy = source_center["y"] - centroid["y"]
            distance = max((dx * dx + dy * dy) ** 0.5, 0.01)
            if distance < 2.0:
                dx, dy = _cluster_breathing_direction(dense_order)
                distance = max((dx * dx + dy * dy) ** 0.5, 0.01)
            close_count = sum(1 for other in source_centers if _point_distance(source_center, other) <= 130.0)
            shift = min(64.0, 18.0 + close_count * 9.0)
            desired_by_id[item["id"]] = {
                **display_bounds,
                "x": display_bounds["x"] + dx / distance * shift,
                "y": display_bounds["y"] + dy / distance * shift,
            }

    if not desired_by_id:
        return placed

    breathed: list[dict[str, Any]] = []
    occupied: list[BoundsDict] = []
    for item in sorted(placed, key=lambda item: (item["page"].sourceFileId, item["system"], item["bounds"]["y"], item["bounds"]["x"], item["kind"])):
        copied = dict(item)
        base_bounds = dict(item.get("displayBounds") or item["bounds"])
        bounds = dict(desired_by_id.get(item["id"], base_bounds))
        if item["id"] in desired_by_id:
            source_center = _bounds_center(item.get("sourceBounds") or item["bounds"])
            group_items = groups.get((item["page"].sourceFileId, item["system"]), [])
            group_centers = [_bounds_center(group_item.get("sourceBounds") or group_item["bounds"]) for group_item in group_items]
            if group_centers:
                centroid = {"x": sum(center["x"] for center in group_centers) / len(group_centers), "y": sum(center["y"] for center in group_centers) / len(group_centers)}
                copied["labelSide"] = _cluster_label_side(source_center, centroid)
        if item["kind"] in {"equipment", "instrument"}:
            bounds = _deconflict_item_bounds(copied, bounds, occupied)
            occupied.append(_semantic_protected_bounds_for_item(copied, bounds))
        if item["id"] in desired_by_id:
            copied["placementStrategy"] = "sourceClusterBreathing"
            copied["placementDx"] = round(bounds["x"] - item["bounds"]["x"], 2)
            copied["placementDy"] = round(bounds["y"] - item["bounds"]["y"], 2)
        copied["displayBounds"] = bounds
        breathed.append(copied)
    return breathed


def _cluster_breathing_direction(index: int) -> tuple[float, float]:
    directions = [
        (1.0, 0.0),
        (-1.0, 0.0),
        (0.0, 1.0),
        (0.0, -1.0),
        (0.85, 0.62),
        (-0.85, 0.62),
        (0.85, -0.62),
        (-0.85, -0.62),
    ]
    return directions[index % len(directions)]


def _point_distance(a: Point, b: Point) -> float:
    return ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5


def _cluster_label_side(center: Point, centroid: Point) -> str:
    dx = center["x"] - centroid["x"]
    dy = center["y"] - centroid["y"]
    if abs(dx) >= abs(dy) * 0.8:
        return "left" if dx < 0 else "right"
    return "top" if dy < 0 else "bottom"


def _placement_metadata_for_item(item: dict[str, Any]) -> dict[str, Any]:
    if not item.get("placementStrategy"):
        return {}
    return {
        "placementStrategy": item["placementStrategy"],
        "placementDx": item.get("placementDx", 0.0),
        "placementDy": item.get("placementDy", 0.0),
    }


def _deconflict_semantic_labels(objects: list[DrawingObject]) -> None:
    protected: list[BoundsDict] = []
    for obj in objects:
        if obj.kind == "symbol" and obj.metadata.get("semanticObject") is True:
            protected.append(_expand_bounds(obj.bounds, 1.0, 1.0))

    labels = [
        obj
        for obj in objects
        if obj.kind == "label" and (obj.metadata.get("semanticObjectLabel") is True or obj.metadata.get("semanticLineTag") is True)
    ]
    for label in sorted(labels, key=lambda obj: (obj.bounds["y"], obj.bounds["x"], obj.id)):
        original = dict(label.bounds)
        adjusted = _first_non_overlapping_label_bounds(original, protected)
        if adjusted != original:
            label.bounds = adjusted
            label.points = _rect_points(adjusted)
            label.metadata["labelDeconflicted"] = True
        protected.append(_expand_bounds(label.bounds, 1.0, 1.0))


def _first_non_overlapping_label_bounds(bounds: BoundsDict, protected: list[BoundsDict]) -> BoundsDict:
    for dx, dy in _label_collision_offsets():
        adjusted = {**bounds, "x": bounds["x"] + dx, "y": bounds["y"] + dy}
        if not any(_bounds_overlap(adjusted, other, padding=1.0) for other in protected):
            return adjusted
    return _least_overlapping_label_bounds(bounds, protected)


def _label_collision_offsets() -> list[tuple[float, float]]:
    offsets = [(0.0, 0.0)]
    for radius in (8.0, 14.0, 22.0, 34.0, 52.0, 76.0):
        offsets.extend(
            [
                (radius, 0.0),
                (-radius, 0.0),
                (0.0, radius),
                (0.0, -radius),
                (radius, radius * 0.5),
                (-radius, radius * 0.5),
                (radius, -radius * 0.5),
                (-radius, -radius * 0.5),
            ]
        )
    return offsets


def _least_overlapping_label_bounds(bounds: BoundsDict, protected: list[BoundsDict]) -> BoundsDict:
    best = bounds
    best_score: tuple[float, float] | None = None
    for dx, dy in _label_collision_offsets():
        adjusted = {**bounds, "x": bounds["x"] + dx, "y": bounds["y"] + dy}
        overlap_area = sum(_overlap_area(adjusted, other, padding=1.0) for other in protected)
        travel = abs(dx) + abs(dy)
        score = (overlap_area, travel)
        if best_score is None or score < best_score:
            best_score = score
            best = adjusted
    return best


def _merge_nearby_same_system_routes(objects: list[DrawingObject]) -> list[DrawingObject]:
    merged: list[DrawingObject] = []
    route_index: dict[tuple[str, str, str], DrawingObject] = {}
    mergeable_roles = {"systemBackbone", "systemInterconnect"}
    for obj in objects:
        role = str(obj.metadata.get("semanticRouteRole") or "")
        system = str(obj.metadata.get("system") or "")
        if (
            obj.kind != "pipe"
            or obj.metadata.get("semanticGeneratedRoute") is not True
            or role not in mergeable_roles
            or not system
            or len(obj.points) != 2
        ):
            merged.append(obj)
            continue
        key = (system, role, _near_route_signature(obj.points))
        existing = route_index.get(key)
        if existing is None:
            route_index[key] = obj
            merged.append(obj)
            continue
        existing.sourceEvidenceIds = _unique([*existing.sourceEvidenceIds, *obj.sourceEvidenceIds])
        existing.metadata["mergedRouteCount"] = int(existing.metadata.get("mergedRouteCount", 1)) + 1
        existing.metadata.setdefault("mergedRouteIds", []).append(obj.id)
    return merged


def _near_route_signature(points: list[Point]) -> str:
    first, last = points[0], points[-1]
    horizontal = abs(last["x"] - first["x"]) >= abs(last["y"] - first["y"])
    if horizontal:
        start = round(min(first["x"], last["x"]) / 16.0)
        end = round(max(first["x"], last["x"]) / 16.0)
        lane = round(((first["y"] + last["y"]) / 2.0) / 12.0)
        return f"h:{lane}:{start}:{end}"
    start = round(min(first["y"], last["y"]) / 16.0)
    end = round(max(first["y"], last["y"]) / 16.0)
    lane = round(((first["x"] + last["x"]) / 2.0) / 12.0)
    return f"v:{lane}:{start}:{end}"


def _snap_attached_connector_endpoints(objects: list[DrawingObject]) -> None:
    object_bounds = {
        obj.id: obj.bounds
        for obj in objects
        if obj.kind in {"symbol", "label", "region"}
        and (obj.metadata.get("semanticOverlay") is True or obj.metadata.get("semanticEndpoint") is True)
    }
    if not object_bounds:
        return

    for obj in objects:
        if obj.kind not in {"connector", "pipe"}:
            continue
        if len(obj.points) < 2:
            continue

        changed = False
        points = [dict(point) for point in obj.points]
        start_object_id = obj.metadata.get("startObjectId")
        if isinstance(start_object_id, str) and start_object_id in object_bounds:
            snapped, side = _snap_point_on_bounds_towards(object_bounds[start_object_id], points[1])
            if _point_distance(snapped, points[0]) > 0.5:
                points[0] = snapped
                points = _repair_start_terminal_orthogonal(points, side)
                obj.metadata["startSnapSide"] = side
                changed = True

        end_object_id = obj.metadata.get("endObjectId")
        if isinstance(end_object_id, str) and end_object_id in object_bounds:
            snapped, side = _snap_point_on_bounds_towards(object_bounds[end_object_id], points[-2])
            if _point_distance(snapped, points[-1]) > 0.5:
                points[-1] = snapped
                points = _repair_end_terminal_orthogonal(points, side)
                obj.metadata["endSnapSide"] = side
                changed = True

        if changed:
            obj.points = _dedupe_points(points)
            obj.bounds = _points_bounds(obj.points, 2.0)
            obj.metadata["endpointSnapRepaired"] = True


def _repair_start_terminal_orthogonal(points: list[Point], side: str) -> list[Point]:
    if len(points) < 2:
        return points
    start = points[0]
    next_point = points[1]
    if abs(start["x"] - next_point["x"]) < 0.5 or abs(start["y"] - next_point["y"]) < 0.5:
        return points
    if side in {"left", "right"}:
        elbow = {"x": next_point["x"], "y": start["y"]}
    else:
        elbow = {"x": start["x"], "y": next_point["y"]}
    return _dedupe_points([start, elbow, *points[1:]])


def _repair_end_terminal_orthogonal(points: list[Point], side: str) -> list[Point]:
    if len(points) < 2:
        return points
    previous = points[-2]
    end = points[-1]
    if abs(previous["x"] - end["x"]) < 0.5 or abs(previous["y"] - end["y"]) < 0.5:
        return points
    if side in {"left", "right"}:
        elbow = {"x": previous["x"], "y": end["y"]}
    else:
        elbow = {"x": end["x"], "y": previous["y"]}
    return _dedupe_points([*points[:-1], elbow, end])


def _route_semantic_lines_around_dense_pockets(objects: list[DrawingObject]) -> None:
    protected = [
        _expand_bounds(obj.bounds, 3.0, 3.0)
        for obj in objects
        if (obj.kind == "symbol" and obj.metadata.get("semanticObject") is True)
        or (obj.kind == "label" and (obj.metadata.get("semanticObjectLabel") is True or obj.metadata.get("semanticLineTag") is True))
    ]
    if not protected:
        return

    for obj in objects:
        if obj.kind != "connector":
            continue
        if obj.metadata.get("semanticGeneratedRoute") is not True:
            continue
        if obj.metadata.get("semanticRouteRole") not in {"equipmentBranch", "instrumentBranch", "lineToNodeAttachment"}:
            continue
        if obj.metadata.get("semanticConnectorRole") in {"matchedContinuation", "unresolvedContinuation"}:
            continue
        routed = _route_points_around_protected_bounds(obj.points, protected)
        if routed == obj.points:
            continue
        obj.points = routed
        obj.bounds = _points_bounds(routed, 2.0)
        obj.metadata["routeAvoidedDensePockets"] = True


def _route_points_around_protected_bounds(points: list[Point], protected: list[BoundsDict]) -> list[Point]:
    routed = list(points)
    for _attempt in range(4):
        changed = False
        next_points: list[Point] = [routed[0]]
        for start, end in zip(routed, routed[1:]):
            segment_points = _route_segment_around_first_obstacle(start, end, protected)
            if segment_points != [start, end]:
                changed = True
            next_points.extend(segment_points[1:])
        routed = _dedupe_points(next_points)
        if not changed:
            break
    return routed


def _route_segment_around_first_obstacle(start: Point, end: Point, protected: list[BoundsDict]) -> list[Point]:
    if abs(start["x"] - end["x"]) < 0.5 and abs(start["y"] - end["y"]) < 0.5:
        return [start, end]
    horizontal = abs(start["y"] - end["y"]) < 0.5
    vertical = abs(start["x"] - end["x"]) < 0.5
    if not horizontal and not vertical:
        return [start, end]
    for bounds in protected:
        if _point_inside_bounds(start, bounds) or _point_inside_bounds(end, bounds):
            continue
        if not _segment_intersects_bounds(start, end, bounds):
            continue
        if horizontal:
            detour_y = _best_horizontal_detour_y(start, end, bounds, protected)
            return _dedupe_points([start, {"x": start["x"], "y": detour_y}, {"x": end["x"], "y": detour_y}, end])
        detour_x = _best_vertical_detour_x(start, end, bounds, protected)
        return _dedupe_points([start, {"x": detour_x, "y": start["y"]}, {"x": detour_x, "y": end["y"]}, end])
    return [start, end]


def _best_horizontal_detour_y(start: Point, end: Point, bounds: BoundsDict, protected: list[BoundsDict]) -> float:
    candidates = [bounds["y"] - 8.0, bounds["y"] + bounds["height"] + 8.0]
    return min(candidates, key=lambda candidate: (_route_detour_crossings([start, {"x": start["x"], "y": candidate}, {"x": end["x"], "y": candidate}, end], protected), abs(candidate - start["y"])))


def _best_vertical_detour_x(start: Point, end: Point, bounds: BoundsDict, protected: list[BoundsDict]) -> float:
    candidates = [bounds["x"] - 8.0, bounds["x"] + bounds["width"] + 8.0]
    return min(candidates, key=lambda candidate: (_route_detour_crossings([start, {"x": candidate, "y": start["y"]}, {"x": candidate, "y": end["y"]}, end], protected), abs(candidate - start["x"])))


def _route_detour_crossings(points: list[Point], protected: list[BoundsDict]) -> int:
    crossings = 0
    for start, end in zip(points, points[1:]):
        for bounds in protected:
            if _point_inside_bounds(start, bounds) or _point_inside_bounds(end, bounds):
                continue
            if _segment_intersects_bounds(start, end, bounds):
                crossings += 1
    return crossings


def _segment_intersects_bounds(start: Point, end: Point, bounds: BoundsDict) -> bool:
    if abs(start["y"] - end["y"]) < 0.5:
        y = start["y"]
        min_x = min(start["x"], end["x"])
        max_x = max(start["x"], end["x"])
        return bounds["y"] <= y <= bounds["y"] + bounds["height"] and max_x >= bounds["x"] and min_x <= bounds["x"] + bounds["width"]
    if abs(start["x"] - end["x"]) < 0.5:
        x = start["x"]
        min_y = min(start["y"], end["y"])
        max_y = max(start["y"], end["y"])
        return bounds["x"] <= x <= bounds["x"] + bounds["width"] and max_y >= bounds["y"] and min_y <= bounds["y"] + bounds["height"]
    return False


def _point_inside_bounds(point: Point, bounds: BoundsDict) -> bool:
    return bounds["x"] <= point["x"] <= bounds["x"] + bounds["width"] and bounds["y"] <= point["y"] <= bounds["y"] + bounds["height"]


def _normalize_semantic_body_position(objects: list[DrawingObject]) -> None:
    body_objects = [
        obj
        for obj in objects
        if obj.metadata.get("semanticOverlay") is True
        and obj.metadata.get("semanticTitle") is not True
        and obj.metadata.get("semanticLegend") is not True
        and obj.metadata.get("semanticSourceMap") is not True
        and obj.kind != "source_fragment"
    ]
    if not body_objects:
        return
    min_y = min(obj.bounds["y"] for obj in body_objects)
    target_y = 186.0
    if min_y <= target_y + 72.0:
        return
    shift_y = min(420.0, min_y - target_y)
    for obj in body_objects:
        obj.bounds = {**obj.bounds, "y": obj.bounds["y"] - shift_y}
        obj.points = [{"x": point["x"], "y": point["y"] - shift_y} for point in obj.points]
        obj.metadata["bodyPositionNormalized"] = True
        obj.metadata["bodyPositionShiftY"] = round(-shift_y, 2)


def _composed_semantic_inventory(inventory: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_system: dict[str, list[dict[str, Any]]] = {}
    for item in inventory:
        by_system.setdefault(item["system"], []).append(item)

    placed: list[dict[str, Any]] = []
    y_cursor = 210.0
    for system, items in sorted(by_system.items(), key=_semantic_system_sort_key):
        semantic_items = [item for item in items if item["kind"] in {"equipment", "instrument"}]
        line_items = [item for item in items if item["kind"] == "line"]
        page_groups = _items_by_source_page(semantic_items)
        if not page_groups and line_items:
            page_groups = [(line_items[0]["page"].sourceFileId, [])]

        max_group_height = 120.0
        for group_index, (_source_id, group_items) in enumerate(page_groups):
            group_x = 150.0 + group_index * 340.0
            equipment = [item for item in group_items if item["kind"] == "equipment"]
            instruments = [item for item in group_items if item["kind"] == "instrument"]
            for index, item in enumerate(sorted(equipment, key=_source_order_key)):
                col = index % 3
                row = index // 3
                _place_item(placed, item, group_x + col * 104.0, y_cursor + 46.0 + row * 76.0)
            equipment_rows = max(1, (len(equipment) + 2) // 3)
            instrument_y = y_cursor + 46.0 + equipment_rows * 76.0
            for index, item in enumerate(sorted(instruments, key=_source_order_key)):
                col = index % 6
                row = index // 6
                _place_item(placed, item, group_x + col * 52.0, instrument_y + row * 42.0)
            group_height = 80.0 + equipment_rows * 76.0 + max(0, (len(instruments) + 5) // 6) * 42.0
            max_group_height = max(max_group_height, group_height)

        line_y = y_cursor + max_group_height + 16.0
        for index, item in enumerate(sorted(line_items, key=_source_order_key)):
            col = index % 10
            row = index // 10
            _place_item(placed, item, 150.0 + col * 110.0, line_y + row * 18.0)
        line_rows = (len(line_items) + 9) // 10
        y_cursor += max_group_height + max(34.0, line_rows * 18.0) + 46.0

    return placed


def _items_by_source_page(items: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        groups.setdefault(item["page"].sourceFileId, []).append(item)
    return sorted(groups.items(), key=lambda entry: (min(_source_order_key(item) for item in entry[1]), entry[0]))


def _place_item(placed: list[dict[str, Any]], item: dict[str, Any], x: float, y: float) -> None:
    copied = dict(item)
    bounds = dict(item["bounds"])
    bounds["x"] = x
    bounds["y"] = y
    bounds["width"] = max(44.0, min(bounds.get("width", 80.0), 112.0))
    bounds["height"] = max(14.0, min(bounds.get("height", 18.0), 24.0))
    copied["displayBounds"] = bounds
    placed.append(copied)


def _semantic_system_sort_key(entry: tuple[str, list[dict[str, Any]]]) -> tuple[int, float, str]:
    system, items = entry
    preferred = {"CHW": 0, "CW": 1, "HHW": 2, "HRW": 3, "CDA": 4, "DOMW": 5, "SSW": 6, "FUTURE": 98, "DEFAULT": 99}
    y = min((_source_order_key(item)[1] for item in items), default=0.0)
    return (preferred.get(system, 50), y, system)


def _source_order_key(item: dict[str, Any]) -> tuple[str, float, float, str]:
    bounds = item.get("sourceBounds") or item["bounds"]
    return (item["page"].sourceFileId, bounds["y"], bounds["x"], item["tag"])


def _semantic_object_id_for_item(item: dict[str, Any]) -> str:
    if item["kind"] == "equipment":
        return _object_id("semantic_equipment", item["id"])
    if item["kind"] == "instrument":
        return _object_id("semantic_instrument", item["id"])
    return _object_id("semantic_item", item["id"])


def _semantic_symbol_bounds_for_item(item: dict[str, Any]) -> BoundsDict:
    bounds = item.get("displayBounds") or item["bounds"]
    if item["kind"] == "instrument":
        return {"x": bounds["x"] - 10.0, "y": bounds["y"] - 10.0, "width": 24.0, "height": 24.0}
    return {"x": bounds["x"] - 20.0, "y": bounds["y"] - 10.0, "width": 42.0, "height": 28.0}


def _semantic_item_label_bounds_for_item(item: dict[str, Any]) -> BoundsDict:
    symbol_bounds = _semantic_symbol_bounds_for_item(item)
    tag = str(item.get("tag") or "")
    side = str(item.get("labelSide") or ("right" if item["kind"] == "instrument" else "bottom"))
    if item["kind"] == "instrument":
        width = min(78.0, max(32.0, len(tag) * 2.65 + 8.0))
        height = 9.0
        return _label_bounds_on_side(symbol_bounds, width, height, side)
    width = min(98.0, max(54.0, len(tag) * 2.85 + 10.0))
    height = 13.0
    return _label_bounds_on_side(symbol_bounds, width, height, side)


def _label_bounds_on_side(symbol_bounds: BoundsDict, width: float, height: float, side: str) -> BoundsDict:
    center = _bounds_center(symbol_bounds)
    if side == "left":
        return {"x": symbol_bounds["x"] - width - 5.0, "y": center["y"] - height / 2.0, "width": width, "height": height}
    if side == "right":
        return {"x": symbol_bounds["x"] + symbol_bounds["width"] + 5.0, "y": center["y"] - height / 2.0, "width": width, "height": height}
    if side == "top":
        return {
            "x": center["x"] - width / 2.0,
            "y": symbol_bounds["y"] - height - 4.0,
            "width": width,
            "height": height,
        }
    return {"x": center["x"] - width / 2.0, "y": symbol_bounds["y"] + symbol_bounds["height"] + 4.0, "width": width, "height": height}


def _item_center(item: dict[str, Any]) -> Point:
    return _bounds_center(_semantic_symbol_bounds_for_item(item))


def _snap_attachment_for_bus(item: dict[str, Any], orientation: str, bus_coord: float) -> tuple[Point, str]:
    bounds = _semantic_symbol_bounds_for_item(item)
    center = _bounds_center(bounds)
    if orientation == "horizontal":
        if bus_coord <= center["y"]:
            return {"x": center["x"], "y": bounds["y"]}, "top"
        return {"x": center["x"], "y": bounds["y"] + bounds["height"]}, "bottom"
    if bus_coord <= center["x"]:
        return {"x": bounds["x"], "y": center["y"]}, "left"
    return {"x": bounds["x"] + bounds["width"], "y": center["y"]}, "right"


def _source_ids_for_items(items: list[dict[str, Any]]) -> list[str]:
    source_ids: list[str] = []
    for item in items:
        for evidence_id in item.get("sourceEvidenceIds", []):
            if evidence_id not in source_ids:
                source_ids.append(evidence_id)
    return source_ids


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


def _median(values: list[float]) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _source_map_fragments(
    pages: list[PageEvidence],
    source_paths: dict[str, str],
    tile_by_source: dict[str, BoundsDict],
    source_bounds_by_source: dict[str, BoundsDict],
) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    for page in pages:
        tile = tile_by_source.get(page.sourceFileId)
        source_bounds = source_bounds_by_source.get(page.sourceFileId, {"x": 0.0, "y": 0.0, "width": page.width, "height": page.height})
        if not tile:
            continue
        metadata: dict[str, Any] = {
            "semanticSourceMap": True,
            "sourceFileId": page.sourceFileId,
            "sourcePageId": page.id,
            "page": page.page,
            "cropBounds": dict(source_bounds),
            "sourceMapOpacity": 0.18,
        }
        if page.sourceFileId in source_paths:
            metadata["sourcePath"] = source_paths[page.sourceFileId]
        objects.append(
            DrawingObject(
                id=_object_id("semantic_source_map", page.id),
                kind="source_fragment",
                label=_source_display_name(page, source_paths),
                points=_rect_points(tile),
                bounds=tile,
                style=DrawingStyle(stroke="#94a3b8", fill="#ffffff", strokeWidth=0.8, opacity=0.18, dash=[8.0, 5.0]),
                sourceEvidenceIds=[page.id],
                locked=True,
                metadata=metadata,
            )
        )
    return objects


def _legend(system_color_map: SystemColorMap, source_ids: list[str]) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    x = 1200.0
    y = 48.0
    objects.append(
        DrawingObject(
            id=_object_id("semantic_legend_frame"),
            kind="region",
            label="",
            points=_rect_points({"x": x - 10.0, "y": y - 12.0, "width": 330.0, "height": 28.0 + len(system_color_map.entries) * 18.0}),
            bounds={"x": x - 10.0, "y": y - 12.0, "width": 330.0, "height": 28.0 + len(system_color_map.entries) * 18.0},
            style=DrawingStyle(stroke="#94a3b8", fill="#ffffff", strokeWidth=0.8, opacity=0.72),
            sourceEvidenceIds=source_ids,
            locked=False,
            metadata={"semanticOverlay": True, "semanticLegend": True, "hideCenterLabel": True},
        )
    )
    objects.append(_label("semantic_legend_title", "SYSTEM LEGEND", {"x": x, "y": y - 4.0, "width": 120.0, "height": 14.0}, "#0f172a", 6.2, source_ids, {"semanticOverlay": True, "semanticLegend": True}))
    for index, entry in enumerate(system_color_map.entries.values()):
        row_y = y + 18.0 + index * 18.0
        objects.append(
            DrawingObject(
                id=_object_id("semantic_legend_sample", entry.key),
                kind="pipe",
                label="",
                points=[{"x": x, "y": row_y}, {"x": x + 54.0, "y": row_y}],
                bounds={"x": x, "y": row_y - 1.0, "width": 54.0, "height": 2.0},
                style=DrawingStyle(stroke=entry.color, fill="none", strokeWidth=1.6, opacity=1.0, dash=entry.dash),
                sourceEvidenceIds=source_ids,
                metadata={"semanticOverlay": True, "semanticLegend": True, "system": entry.key},
            )
        )
        objects.append(_label(_object_id("semantic_legend_label", entry.key), display_system_label(entry.key), {"x": x + 66.0, "y": row_y - 6.0, "width": 220.0, "height": 12.0}, "#111827", 5.6, source_ids, {"semanticOverlay": True, "semanticLegend": True, "system": entry.key}))
    return objects


def _candidate_point(
    candidate: ContinuationCandidate,
    page_by_source: dict[str, PageEvidence],
    tile_by_source: dict[str, BoundsDict],
    source_bounds_by_source: dict[str, BoundsDict],
) -> Point | None:
    if candidate.sourceFileId not in page_by_source or candidate.sourceFileId not in tile_by_source:
        return None
    source_bounds = source_bounds_by_source.get(candidate.sourceFileId)
    if not source_bounds:
        return None
    return _map_point(candidate.position, source_bounds, tile_by_source[candidate.sourceFileId])


def _inline_device_seeds(pages: list[PageEvidence], system_color_map: SystemColorMap) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    for page in pages:
        for span in page.textSpans:
            for match in INLINE_DEVICE_TAG_RE.finditer(span.text or ""):
                system = _semantic_system_for_tag("line", match.group(0).upper(), system_color_map)
                if system == "DEFAULT":
                    continue
                seeds.append(
                    {
                        "page": page,
                        "system": system,
                        "sourceBounds": {"x": span.x, "y": span.y, "width": span.width, "height": span.height},
                    }
                )
    return seeds


def _nearest_line_system(vector: VectorSegment, page: PageEvidence, line_items: list[dict[str, Any]], system_color_map: SystemColorMap) -> str:
    center = _bounds_center(vector.bounds)
    nearest: tuple[float, str] | None = None
    for item in line_items:
        item_page = item["page"]
        if item_page.sourceFileId != page.sourceFileId:
            continue
        item_center = _bounds_center(item.get("sourceBounds") or item["bounds"])
        vertical_gap = abs(item_center["y"] - center["y"])
        horizontal_gap = abs(item_center["x"] - center["x"])
        horizontal_vector = vector.bounds["width"] >= vector.bounds["height"]
        max_vertical_seed_gap = max(34.0, min(page.width, page.height) * 0.045)
        max_horizontal_seed_gap = max(46.0, min(page.width, page.height) * 0.06)
        if horizontal_vector and vertical_gap > max_vertical_seed_gap:
            continue
        if not horizontal_vector and horizontal_gap > max_horizontal_seed_gap:
            continue
        distance = abs(item_center["y"] - center["y"]) + abs(item_center["x"] - center["x"]) * 0.12
        if nearest is None or distance < nearest[0]:
            nearest = (distance, item["system"])
    if nearest and nearest[0] < 140.0:
        return nearest[1]
    return "DEFAULT"


def _propagated_vector_systems(
    page: PageEvidence,
    vector_records: list[tuple[int, VectorSegment]],
    line_items: list[dict[str, Any]],
    system_color_map: SystemColorMap,
) -> dict[int, str]:
    """Color source pipe fragments by walking connected vector geometry from tagged seeds."""

    systems: dict[int, str] = {
        index: _nearest_line_system(vector, page, line_items, system_color_map)
        for index, vector in vector_records
    }
    if not any(system != "DEFAULT" for system in systems.values()):
        return systems

    segments_by_index = {index: _vector_line_segments(vector) for index, vector in vector_records}
    tolerance = max(6.0, min(page.width, page.height) * 0.0045)
    for _pass in range(6):
        changed = False
        colored = [
            (index, systems[index], segments_by_index[index])
            for index, _vector in vector_records
            if systems.get(index) != "DEFAULT"
        ]
        for index, _vector in vector_records:
            if systems.get(index) != "DEFAULT":
                continue
            own_segments = segments_by_index[index]
            matches: list[tuple[float, str]] = []
            for other_index, other_system, other_segments in colored:
                if other_index == index:
                    continue
                distance = _polyline_distance(own_segments, other_segments)
                if distance <= tolerance:
                    matches.append((distance, other_system))
            if not matches:
                continue
            matches.sort(key=lambda item: item[0])
            nearest_distance = matches[0][0]
            nearest_systems = {system for distance, system in matches if distance <= nearest_distance + 1.5}
            if len(nearest_systems) == 1:
                systems[index] = matches[0][1]
                changed = True
        if not changed:
            break
    return systems


def _vector_line_segments(vector: VectorSegment) -> list[tuple[Point, Point]]:
    segments: list[tuple[Point, Point]] = []
    points = [point for point in vector.points if isinstance(point.get("x"), (int, float)) and isinstance(point.get("y"), (int, float))]
    for start, end in zip(points, points[1:]):
        if _point_distance(start, end) <= 0.5:
            continue
        segments.append((start, end))
    return segments


def _polyline_distance(first: list[tuple[Point, Point]], second: list[tuple[Point, Point]]) -> float:
    if not first or not second:
        return float("inf")
    best = float("inf")
    for a_start, a_end in first:
        for b_start, b_end in second:
            best = min(best, _segment_distance(a_start, a_end, b_start, b_end))
            if best <= 0.01:
                return best
    return best


def _segment_distance(a_start: Point, a_end: Point, b_start: Point, b_end: Point) -> float:
    if _segments_intersect(a_start, a_end, b_start, b_end):
        return 0.0
    return min(
        _point_to_segment_distance(a_start, b_start, b_end),
        _point_to_segment_distance(a_end, b_start, b_end),
        _point_to_segment_distance(b_start, a_start, a_end),
        _point_to_segment_distance(b_end, a_start, a_end),
    )


def _segments_intersect(a_start: Point, a_end: Point, b_start: Point, b_end: Point) -> bool:
    def orientation(p: Point, q: Point, r: Point) -> float:
        return (q["y"] - p["y"]) * (r["x"] - q["x"]) - (q["x"] - p["x"]) * (r["y"] - q["y"])

    def on_segment(p: Point, q: Point, r: Point) -> bool:
        return (
            min(p["x"], r["x"]) - 0.01 <= q["x"] <= max(p["x"], r["x"]) + 0.01
            and min(p["y"], r["y"]) - 0.01 <= q["y"] <= max(p["y"], r["y"]) + 0.01
        )

    o1 = orientation(a_start, a_end, b_start)
    o2 = orientation(a_start, a_end, b_end)
    o3 = orientation(b_start, b_end, a_start)
    o4 = orientation(b_start, b_end, a_end)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True
    if abs(o1) <= 0.01 and on_segment(a_start, b_start, a_end):
        return True
    if abs(o2) <= 0.01 and on_segment(a_start, b_end, a_end):
        return True
    if abs(o3) <= 0.01 and on_segment(b_start, a_start, b_end):
        return True
    if abs(o4) <= 0.01 and on_segment(b_start, a_end, b_end):
        return True
    return False


def _point_to_segment_distance(point: Point, start: Point, end: Point) -> float:
    length_sq = (end["x"] - start["x"]) ** 2 + (end["y"] - start["y"]) ** 2
    if length_sq <= 0.01:
        return _point_distance(point, start)
    t = ((point["x"] - start["x"]) * (end["x"] - start["x"]) + (point["y"] - start["y"]) * (end["y"] - start["y"])) / length_sq
    t = max(0.0, min(1.0, t))
    projected = {"x": start["x"] + t * (end["x"] - start["x"]), "y": start["y"] + t * (end["y"] - start["y"])}
    return _point_distance(point, projected)


def _is_noise_vector(vector: VectorSegment, page: PageEvidence) -> bool:
    bounds = vector.bounds
    if bounds["width"] <= 1.0 and bounds["height"] <= 1.0:
        return True
    if bounds["width"] < 18.0 and bounds["height"] < 18.0:
        return True
    near_top_or_left = bounds["x"] <= 4.0 or bounds["y"] <= 4.0
    long_border = bounds["width"] > page.width * 0.55 or bounds["height"] > page.height * 0.55
    return near_top_or_left and long_border


def _is_default_context_vector_noise(vector: VectorSegment, page: PageEvidence, context_bounds: list[BoundsDict]) -> bool:
    """Drop drafting frames/title block fragments from the faint semantic context layer."""
    bounds = vector.bounds
    if _is_page_edge_frame_vector(bounds, page):
        return True
    if _is_title_block_band_vector(bounds, page):
        return True
    if any(_bounds_overlap(bounds, context, padding=0.0) for context in context_bounds):
        return False

    longest_axis = max(bounds["width"], bounds["height"])
    shortest_axis = min(bounds["width"], bounds["height"])
    mostly_linear = shortest_axis <= 8.0
    if vector.dashed and longest_axis < max(page.width, page.height) * 0.36 and not _touches_page_edge(bounds, page, 8.0):
        return False
    if longest_axis <= max(page.width, page.height) * 0.075 and not _touches_page_edge(bounds, page, 12.0):
        return False
    if mostly_linear and longest_axis > max(page.width, page.height) * 0.18:
        return True
    return True


def _is_default_detail_trace_vector(
    vector: VectorSegment,
    page: PageEvidence,
    detail_context_bounds: list[BoundsDict],
    colored_segments: list[tuple[Point, Point]],
) -> bool:
    bounds = vector.bounds
    if any(_bounds_overlap(bounds, context, padding=0.0) for context in detail_context_bounds):
        return True

    segments = _vector_line_segments(vector)
    if not segments or not colored_segments:
        return False
    longest_axis = max(bounds["width"], bounds["height"])
    if longest_axis > max(page.width, page.height) * 0.16:
        return False
    nearest_colored = _polyline_distance(segments, colored_segments)
    return nearest_colored <= max(5.0, min(page.width, page.height) * 0.0035)


def _is_page_edge_frame_vector(bounds: BoundsDict, page: PageEvidence) -> bool:
    margin = max(8.0, min(page.width, page.height) * 0.018)
    inset_margin = max(margin, min(page.width, page.height) * 0.045)
    near_left = bounds["x"] <= margin
    near_top = bounds["y"] <= margin
    near_right = bounds["x"] + bounds["width"] >= page.width - margin
    near_bottom = bounds["y"] + bounds["height"] >= page.height - margin
    near_inset_left = bounds["x"] <= page.width * 0.11
    near_inset_top = bounds["y"] <= inset_margin
    spans_past_bottom = bounds["y"] + bounds["height"] >= page.height * 0.92
    spans_past_right = bounds["x"] + bounds["width"] >= page.width * 0.68
    overlong_vertical_frame = bounds["height"] >= page.height * 1.12 and near_inset_top
    overlong_horizontal_frame = bounds["width"] >= page.width * 0.62 and near_inset_top
    partial_inset_vertical_rail = bounds["height"] >= page.height * 0.2 and near_inset_left
    partial_inset_horizontal_rail = bounds["width"] >= page.width * 0.2 and near_inset_top
    page_wide = bounds["width"] >= page.width * 0.42
    page_tall = bounds["height"] >= page.height * 0.42
    hairline_horizontal = bounds["height"] <= 8.0
    hairline_vertical = bounds["width"] <= 8.0
    if hairline_horizontal and page_wide and (near_top or near_bottom):
        return True
    if hairline_vertical and page_tall and (near_left or near_right):
        return True
    if hairline_horizontal and page_wide and near_inset_top and spans_past_right:
        return True
    if hairline_vertical and page_tall and near_inset_left and (near_inset_top or spans_past_bottom):
        return True
    if hairline_vertical and partial_inset_vertical_rail:
        return True
    if hairline_horizontal and partial_inset_horizontal_rail and (spans_past_right or near_left):
        return True
    if hairline_vertical and overlong_vertical_frame:
        return True
    if hairline_horizontal and overlong_horizontal_frame:
        return True
    if page_wide and page_tall and (near_left or near_top or near_right or near_bottom):
        return True
    return False


def _is_title_block_band_vector(bounds: BoundsDict, page: PageEvidence) -> bool:
    right_band = bounds["x"] > page.width * 0.72
    bottom_band = bounds["y"] > page.height * 0.78
    left_band = bounds["x"] < page.width * 0.08
    long_vertical = bounds["width"] <= 18.0 and bounds["height"] >= page.height * 0.18
    long_horizontal = bounds["height"] <= 18.0 and bounds["width"] >= page.width * 0.18
    if (right_band or left_band) and long_vertical:
        return True
    if bottom_band and long_horizontal:
        return True
    return False


def _touches_page_edge(bounds: BoundsDict, page: PageEvidence, margin: float) -> bool:
    return (
        bounds["x"] <= margin
        or bounds["y"] <= margin
        or bounds["x"] + bounds["width"] >= page.width - margin
        or bounds["y"] + bounds["height"] >= page.height - margin
    )


def _matched_candidate_bounds_by_source(
    matches: list[ContinuationMatch],
    candidate_by_id: dict[str, ContinuationCandidate],
) -> dict[str, list[BoundsDict]]:
    bounds_by_source: dict[str, list[BoundsDict]] = {}
    for match in matches:
        if match.status == "rejected":
            continue
        for candidate_id in (match.sourceCandidateId, match.targetCandidateId):
            candidate = candidate_by_id.get(candidate_id)
            if candidate is None:
                continue
            bounds_by_source.setdefault(candidate.sourceFileId, []).append(_expand_bounds(candidate.bounds, 8.0, 8.0))
    return bounds_by_source


def _is_matched_offpage_marker_vector(vector: VectorSegment, matched_bounds: list[BoundsDict]) -> bool:
    if not matched_bounds:
        return False
    bounds = vector.bounds
    if not any(_bounds_overlap(bounds, candidate_bounds, padding=0.0) for candidate_bounds in matched_bounds):
        return False
    compact_marker = bounds["width"] <= 180.0 and bounds["height"] <= 80.0 and len(vector.points) >= 4
    return compact_marker


def _expand_bounds(bounds: BoundsDict, dx: float, dy: float) -> BoundsDict:
    return {
        "x": bounds["x"] - dx,
        "y": bounds["y"] - dy,
        "width": bounds["width"] + dx * 2.0,
        "height": bounds["height"] + dy * 2.0,
    }


def _symbol_type_for_tag(tag: str) -> str:
    return _symbol_profile_for_tag(tag)["symbolType"]


def _symbol_profile_for_tag(tag: str) -> dict[str, Any]:
    text = tag.upper()
    symbol_type = "equipment"
    if "-CT-" in text or "COOLING-TOWER" in text or "COOLING TOWER" in text:
        symbol_type = "cooling_tower"
    elif "-C-" in text and ("CDA" in text or "-CA-" in text or "COMP" in text):
        symbol_type = "compressor"
    elif "-COMP-" in text or "COMPRESSOR" in text:
        symbol_type = "compressor"
    elif "-FAN-" in text or "-EF-" in text or "-SF-" in text or "-RF-" in text or "BLOWER" in text or "FAN" in text:
        symbol_type = "fan"
    elif "-PNL-" in text or "-PANEL-" in text or "PANEL" in text or "-MCC-" in text or "-SWGR-" in text:
        symbol_type = "panel"
    elif "-SKID-" in text or "SKID" in text:
        symbol_type = "skid"
    elif "-SEP-" in text or "SEPARATOR" in text:
        symbol_type = "separator"
    elif "-COIL-" in text or "COIL" in text:
        symbol_type = "coil"
    elif "-P-" in text or re.match(r"P-(?:\d{1,3}|XX)", text) or "PUMP" in text:
        symbol_type = "pump"
    elif "-HX-" in text or text.startswith("HX-") or "HEAT-EXCHANGER" in text:
        symbol_type = "heat_exchanger"
    elif "-CH-" in text or "CHILLER" in text:
        symbol_type = "chiller"
    if "-HWB-" in text or "-BLR-" in text or "BOILER" in text:
        symbol_type = "boiler"
    elif "-AD-" in text or "DRYER" in text:
        symbol_type = "dryer"
    elif "-VFD-" in text or text.endswith("-VFD") or "DRIVE" in text:
        symbol_type = "drive"
    elif "-FLTR-" in text or "-FILT-" in text or "FILTER" in text:
        symbol_type = "filter"
    elif text.startswith("AHU-") or text.startswith("MAU-") or "-AHU-" in text or "-MAU-" in text:
        symbol_type = "air_handler"
    elif "-FCU-" in text or text.startswith("FCU-") or "-FTR" in text:
        symbol_type = "terminal_unit"
    elif "-ST-" in text or "-ET-" in text or "TANK" in text:
        symbol_type = "tank"
    return {
        "symbolType": symbol_type,
        "symbolRegistry": "iso_primitives",
        "symbolStandard": "ISO-10628-inspired",
        "symbolConfidence": 0.82 if symbol_type != "equipment" else 0.58,
    }


def _deconflict_bounds(bounds: BoundsDict, occupied: list[BoundsDict]) -> BoundsDict:
    offsets = [
        (0.0, 0.0),
        (12.0, -10.0),
        (-12.0, 10.0),
        (18.0, 14.0),
        (-18.0, -14.0),
        (28.0, 0.0),
        (-28.0, 0.0),
        (0.0, 24.0),
        (0.0, -24.0),
        (36.0, 18.0),
        (-36.0, -18.0),
        (48.0, 30.0),
        (-48.0, -30.0),
    ]
    for dx, dy in offsets:
        adjusted = {**bounds, "x": bounds["x"] + dx, "y": bounds["y"] + dy}
        if not any(_bounds_overlap(adjusted, other, padding=5.0) for other in occupied):
            return adjusted
    return {**bounds, "x": bounds["x"] + 56.0, "y": bounds["y"] + 38.0}


def _deconflict_item_bounds(item: dict[str, Any], bounds: BoundsDict, occupied: list[BoundsDict]) -> BoundsDict:
    if not occupied:
        return bounds
    offsets = _local_collision_offsets()
    for dx, dy in offsets:
        adjusted = {**bounds, "x": bounds["x"] + dx, "y": bounds["y"] + dy}
        protected = _semantic_protected_bounds_for_item(item, adjusted)
        if not any(_bounds_overlap(protected, other, padding=4.0) for other in occupied):
            return adjusted
    return _least_overlapping_item_bounds(item, bounds, occupied, offsets)


def _local_collision_offsets() -> list[tuple[float, float]]:
    offsets = [(0.0, 0.0)]
    for radius in (14.0, 24.0, 36.0, 60.0, 78.0, 102.0):
        offsets.extend(
            [
                (radius, 0.0),
                (-radius, 0.0),
                (0.0, radius),
                (0.0, -radius),
                (radius, radius * 0.55),
                (-radius, radius * 0.55),
                (radius, -radius * 0.55),
                (-radius, -radius * 0.55),
            ]
        )
    return offsets


def _least_overlapping_item_bounds(item: dict[str, Any], bounds: BoundsDict, occupied: list[BoundsDict], offsets: list[tuple[float, float]]) -> BoundsDict:
    best_bounds = bounds
    best_score: tuple[float, float] | None = None
    for dx, dy in offsets:
        adjusted = {**bounds, "x": bounds["x"] + dx, "y": bounds["y"] + dy}
        protected = _semantic_protected_bounds_for_item(item, adjusted)
        overlap_area = sum(_overlap_area(protected, other, padding=4.0) for other in occupied)
        travel = abs(dx) + abs(dy)
        score = (overlap_area, travel)
        if best_score is None or score < best_score:
            best_score = score
            best_bounds = adjusted
    return best_bounds


def _semantic_protected_bounds_for_item(item: dict[str, Any], display_bounds: BoundsDict) -> BoundsDict:
    temp = {**item, "displayBounds": display_bounds}
    symbol_bounds = _semantic_symbol_bounds_for_item(temp)
    if item["kind"] not in {"equipment", "instrument"}:
        return _expand_bounds(symbol_bounds, 4.0, 4.0)
    label_bounds = _semantic_item_label_bounds_for_item(temp)
    min_x = min(symbol_bounds["x"], label_bounds["x"])
    min_y = min(symbol_bounds["y"], label_bounds["y"])
    max_x = max(symbol_bounds["x"] + symbol_bounds["width"], label_bounds["x"] + label_bounds["width"])
    max_y = max(symbol_bounds["y"] + symbol_bounds["height"], label_bounds["y"] + label_bounds["height"])
    return _expand_bounds({"x": min_x, "y": min_y, "width": max_x - min_x, "height": max_y - min_y}, 4.0, 4.0)


def _bounds_overlap(a: BoundsDict, b: BoundsDict, padding: float = 0.0) -> bool:
    return not (
        a["x"] + a["width"] + padding < b["x"]
        or b["x"] + b["width"] + padding < a["x"]
        or a["y"] + a["height"] + padding < b["y"]
        or b["y"] + b["height"] + padding < a["y"]
    )


def _overlap_area(a: BoundsDict, b: BoundsDict, padding: float = 0.0) -> float:
    left = max(a["x"] - padding, b["x"] - padding)
    right = min(a["x"] + a["width"] + padding, b["x"] + b["width"] + padding)
    top = max(a["y"] - padding, b["y"] - padding)
    bottom = min(a["y"] + a["height"] + padding, b["y"] + b["height"] + padding)
    if right <= left or bottom <= top:
        return 0.0
    return (right - left) * (bottom - top)


def _map_point(point: Point, source_bounds: BoundsDict, tile: BoundsDict) -> Point:
    return {
        "x": tile["x"] + ((point["x"] - source_bounds["x"]) / max(source_bounds["width"], 1.0)) * tile["width"],
        "y": tile["y"] + ((point["y"] - source_bounds["y"]) / max(source_bounds["height"], 1.0)) * tile["height"],
    }


def _map_bounds(bounds: BoundsDict, source_bounds: BoundsDict, tile: BoundsDict) -> BoundsDict:
    top_left = _map_point({"x": bounds["x"], "y": bounds["y"]}, source_bounds, tile)
    bottom_right = _map_point({"x": bounds["x"] + bounds["width"], "y": bounds["y"] + bounds["height"]}, source_bounds, tile)
    return {
        "x": min(top_left["x"], bottom_right["x"]),
        "y": min(top_left["y"], bottom_right["y"]),
        "width": abs(bottom_right["x"] - top_left["x"]),
        "height": abs(bottom_right["y"] - top_left["y"]),
    }


def _orthogonal_points(start: Point, end: Point) -> list[Point]:
    if abs(start["y"] - end["y"]) < 12.0 or abs(start["x"] - end["x"]) < 12.0:
        return [start, end]
    mid_x = start["x"] + (end["x"] - start["x"]) / 2.0
    return [start, {"x": mid_x, "y": start["y"]}, {"x": mid_x, "y": end["y"]}, end]


def _source_display_name(page: PageEvidence, source_paths: dict[str, str]) -> str:
    source_path = source_paths.get(page.sourceFileId)
    if source_path:
        match = re.search(r"\b" + PROJECT_CODE_PATTERN + r"-[A-Z0-9_.-]+", Path(source_path).stem, re.IGNORECASE)
        if match:
            return match.group(0).upper()
    return f"{page.sourceFileId} p{page.page}"


def _label(id_seed: str, text: str, bounds: BoundsDict, color: str, font_size: float, source_ids: list[str], metadata: dict[str, Any] | None = None) -> DrawingObject:
    return DrawingObject(
        id=_object_id("label", id_seed),
        kind="label",
        label=text,
        points=_rect_points(bounds),
        bounds=bounds,
        style=DrawingStyle(stroke=color, fill="none", strokeWidth=0.0, opacity=1.0, fontSize=font_size),
        sourceEvidenceIds=source_ids,
        locked=False,
        metadata=metadata or {},
    )


def _styles_from_color_map(system_color_map: SystemColorMap) -> dict[str, DrawingStyle]:
    styles = {"default": DrawingStyle()}
    for key, entry in system_color_map.entries.items():
        styles[key] = DrawingStyle(stroke=entry.color, fill="none", strokeWidth=1.0, opacity=1.0, dash=entry.dash)
    return styles


def _points_bounds(points: list[Point], pad: float = 0.0) -> BoundsDict:
    min_x = min(point["x"] for point in points) - pad
    max_x = max(point["x"] for point in points) + pad
    min_y = min(point["y"] for point in points) - pad
    max_y = max(point["y"] for point in points) + pad
    return {"x": min_x, "y": min_y, "width": max_x - min_x, "height": max_y - min_y}


def _rect_points(bounds: BoundsDict) -> list[Point]:
    return [
        {"x": bounds["x"], "y": bounds["y"]},
        {"x": bounds["x"] + bounds["width"], "y": bounds["y"]},
        {"x": bounds["x"] + bounds["width"], "y": bounds["y"] + bounds["height"]},
        {"x": bounds["x"], "y": bounds["y"] + bounds["height"]},
    ]


def _bounds_center(bounds: BoundsDict) -> Point:
    return {"x": bounds["x"] + bounds["width"] / 2.0, "y": bounds["y"] + bounds["height"] / 2.0}


def _midpoint(start: Point, end: Point) -> Point:
    return {"x": (start["x"] + end["x"]) / 2.0, "y": (start["y"] + end["y"]) / 2.0}


def _document_size(objects: list[DrawingObject], *, compact: bool = False) -> tuple[float, float]:
    if not objects:
        return 3200.0, 2200.0
    width = max(obj.bounds["x"] + obj.bounds["width"] for obj in objects) + 180.0
    height = max(obj.bounds["y"] + obj.bounds["height"] for obj in objects) + 180.0
    if compact:
        return max(1700.0, min(14000.0, width)), max(1050.0, min(10000.0, height))
    return max(3200.0, min(14000.0, width)), max(2200.0, min(10000.0, height))


def _coverage(total: int, missing: int) -> float:
    if total <= 0:
        return 1.0
    return round((total - missing) / total, 3)


def _slug_id(*parts: str) -> str:
    raw = "_".join(part for part in parts if part)
    return re.sub(r"[^a-zA-Z0-9_]+", "_", raw).strip("_").lower()[:96]


def _object_id(prefix: str, *parts: str) -> str:
    raw = "|".join([prefix, *[str(part) for part in parts]])
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    slug = _slug_id(prefix, *[str(part) for part in parts])[:64]
    return f"{slug}_{digest}"


def _stable_hash(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:12]
