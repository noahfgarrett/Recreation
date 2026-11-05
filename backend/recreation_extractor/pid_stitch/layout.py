from __future__ import annotations

import copy
import hashlib
import re
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Literal

from recreation_extractor.conventions import PROJECT_CODE, PROJECT_CODE_PATTERN
from recreation_extractor.hierarchy.dependency_rules import build_dependency_graph
from recreation_extractor.hierarchy.models import to_plain_dict
from recreation_extractor.hierarchy.relationship_graph import attach_hierarchy_views
from recreation_extractor.hierarchy.rulebook import build_rulebook
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
    TextSpan,
    VectorSegment,
)
from recreation_extractor.pid_stitch.electrical_graph import build_electrical_relationship_graph
from recreation_extractor.pid_stitch.semantic_overlay import build_semantic_drawing_option, build_semantic_overlay_option
from recreation_extractor.pid_stitch.semantic_graph import build_pid_relationship_graph
from recreation_extractor.pid_stitch.source_graph import PidSourceGraph, build_source_graph
from recreation_extractor.pid_stitch.system_colors import SystemColorMap, canonical_system, discover_system_color_map, style_for_system, system_for_text
from recreation_extractor.pid_stitch.visio_template import load_visio_template_objects


SYSTEM_COLORS: dict[str, str] = {
    "CHWS": "#0070c0",
    "CHWR": "#0070c0",
    "CWS": "#7030a0",
    "CWR": "#7030a0",
    "HHWS": "#ff0000",
    "HHWR": "#ff0000",
    "HRW": "#ea700d",
    "CDA": "#4bacc6",
    "PW": "#00b050",
    "DOMW": "#00b050",
    "SSW": "#0c1c54",
}
SYSTEM_COLOR_REFERENCE_COLORS: dict[str, str] = {
    "CHW": SYSTEM_COLORS["CHWS"],
    "CW": SYSTEM_COLORS["CWS"],
    "HHW": SYSTEM_COLORS["HHWS"],
    "HRW": SYSTEM_COLORS["HRW"],
    "CDA": SYSTEM_COLORS["CDA"],
    "PW": SYSTEM_COLORS["PW"],
    "DOMW": SYSTEM_COLORS["DOMW"],
    "SSW": SYSTEM_COLORS["SSW"],
}
GROUP_COLORS: dict[str, str] = {
    "CDA": "#f3e8ff",
    "PLUMBING WATER": "#ecfdf5",
    "CHW / CW": "#e0f2fe",
    "HHW / HRW": "#fee2e2",
    "OTHER": "#f8fafc",
}
GROUP_ORDER = ("CDA", "PLUMBING WATER", "CHW / CW", "HHW / HRW", "OTHER")
EQUIPMENT_TAG_RE = re.compile(
    r"\b(?:R-[A-Z0-9]+-[A-Z0-9]+-[A-Z0-9_-]+|[A-Z]{2,5}-\d{2,4}-(?:AHU|MAU|FCU|DUH|FTR|CAVR|CVR|VAR)[- ]?\d+[A-Z0-9-]*|(?:AHU|MAU|FCU|DUH|FTR|CAVR|CVR|VAR)[- ]?\d+[A-Z0-9-]*|P-(?:\d{1,3}|XX)(?:-[A-Z0-9]+)?|HX-(?:\d{1,3}|XX)(?:-[A-Z0-9]+)?)\b",
    re.IGNORECASE,
)
LINE_TAG_TOKEN_RE = re.compile(r'\b\d{1,3}"-[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b', re.IGNORECASE)
SHEET_REF_TOKEN_RE = re.compile(r"\b" + PROJECT_CODE_PATTERN + r"-[A-Z0-9]+-[A-Z0-9][A-Z0-9.-]*[A-Z0-9](?=\b|_)", re.IGNORECASE)
INSTRUMENT_TAG_RE = re.compile(
    r"\b(?:(?:PDIT|PDT|PIT|FIT|TIT|LIT|AIT|PT|FT|TT|LT|TE|FE|PE|PI|FI|TI|LI|LV|XV|HV|FCV|PCV|TCV|SV|PSV|PRV|ST|BA|IE)[- ]?\d{2,4}[A-Z]?|AT-?\d{2,4}[A-Z]?)\b",
    re.IGNORECASE,
)
ADMIN_TEXT_RE = re.compile(
    r"\b(?:CXA\s+COMMENT|FIELD\s+REVIEW|GENERAL\s+NOTES?|REVISION|ISSUED\s+FOR|RECOMMEND(?:ED|ATION)?|COMMENT)\b",
    re.IGNORECASE,
)

_PAGE_MARGIN = 160.0
_SOURCE_FAITHFUL_GAP = 120.0
_RECOMMENDED_GAP = 80.0
_OVERVIEW_WIDTH = 3456.0
_OVERVIEW_HEIGHT = 2592.0
_OVERVIEW_COLUMNS = 3
_OVERVIEW_MARGIN_X = 120.0
_OVERVIEW_MARGIN_TOP = 180.0
_OVERVIEW_MARGIN_BOTTOM = 120.0
_SOURCE_VECTOR_SYSTEM_MAX_DISTANCE = 30.0
_SOURCE_VECTOR_CONNECT_TOLERANCE = 10.0
_PIPE_PADDING = 18.0
_STITCHED_TILE_MAX_WIDTH = 1240.0
_STITCHED_TILE_MAX_HEIGHT = 900.0
_STITCHED_TILE_GAP_X = 96.0
_STITCHED_TILE_GAP_Y = 112.0
_STITCHED_CONTINUATION_GAP = 144.0

PageTransform = dict[str, float]


def generate_layout_options(
    project_id: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str] | None = None,
    preflight_review: dict[str, Any] | None = None,
) -> list[tuple[LayoutOption, DrawingDocument]]:
    """Generate deterministic editable drawing options for stitched P&IDs."""
    _validate_unique_candidate_ids(candidates)
    selected_matches = [match for match in matches if match.status != "rejected"]
    source_paths = source_paths or {}
    system_color_map = discover_system_color_map(pages, candidates, source_paths, SYSTEM_COLOR_REFERENCE_COLORS)
    sorted_pages = _sorted_pages(pages)
    relationship_graph = build_pid_relationship_graph(project_id, sorted_pages, candidates, selected_matches, source_paths, system_color_map)
    electrical_relationship_graph = build_electrical_relationship_graph(project_id, sorted_pages, source_paths)
    document_rulebook = to_plain_dict(build_rulebook(project_id, sorted_pages, preflight_review))
    source_bounds_by_source = {page.sourceFileId: _stitched_page_display_content_bounds(page) for page in sorted_pages}
    candidate_by_id = {candidate.id: candidate for candidate in candidates}
    tile_by_source = _stitched_source_tiles(sorted_pages, selected_matches, candidate_by_id, source_bounds_by_source) if len(pages) > 1 else {
        page.sourceFileId: {
            "x": 120.0,
            "y": 178.0,
            "width": source_bounds_by_source[page.sourceFileId]["width"] * min(
                _STITCHED_TILE_MAX_WIDTH / max(1.0, source_bounds_by_source[page.sourceFileId]["width"]),
                _STITCHED_TILE_MAX_HEIGHT / max(1.0, source_bounds_by_source[page.sourceFileId]["height"]),
            ),
            "height": source_bounds_by_source[page.sourceFileId]["height"] * min(
                _STITCHED_TILE_MAX_WIDTH / max(1.0, source_bounds_by_source[page.sourceFileId]["width"]),
                _STITCHED_TILE_MAX_HEIGHT / max(1.0, source_bounds_by_source[page.sourceFileId]["height"]),
            ),
        }
        for page in sorted_pages
    }
    options = [
        build_semantic_drawing_option(project_id, pages, candidates, selected_matches, source_paths, system_color_map, tile_by_source, source_bounds_by_source, relationship_graph),
        build_semantic_overlay_option(project_id, pages, candidates, selected_matches, source_paths, system_color_map, tile_by_source, source_bounds_by_source, relationship_graph),
        _build_source_driven_combined_option(project_id, pages, candidates, selected_matches, source_paths),
        _build_clean_overview_option(project_id, pages, candidates, selected_matches, source_paths),
        _build_recommended_combined_option(project_id, pages, candidates, selected_matches, source_paths),
    ]
    source_generated = _build_source_generated_chw_cw_option(project_id, pages, candidates, selected_matches, source_paths)
    if source_generated is not None:
        options.append(source_generated)
    source_generated_hhw = _build_source_generated_hhw_hrw_option(project_id, pages, candidates, selected_matches, source_paths)
    if source_generated_hhw is not None:
        options.append(source_generated_hhw)
    full_combined_hhw = _build_full_combined_hhw_hrw_option(project_id, pages, candidates, selected_matches, source_paths)
    if full_combined_hhw is not None:
        options.append(full_combined_hhw)
    presentation_clean_hhw = _build_presentation_clean_hhw_hrw_option(project_id, pages, candidates, selected_matches, source_paths)
    if presentation_clean_hhw is not None:
        options.append(presentation_clean_hhw)
    options.extend(_build_template_compiled_options(project_id, pages, candidates, selected_matches, source_paths))
    options.append(
        _build_option(
            "source_faithful",
            "Source-faithful",
            "Preserves source page order and spacing while showing continuation links.",
            project_id,
            pages,
            candidates,
            selected_matches,
            _SOURCE_FAITHFUL_GAP,
            1.0,
            "source_faithful",
            source_paths,
        )
    )
    electrical_visual_qa = electrical_relationship_graph.to_visual_qa()
    dependency_visual_qa = build_dependency_graph(project_id, relationship_graph, electrical_relationship_graph).to_visual_qa()
    for _option, document in options:
        document.visualQa["electricalRelationshipGraph"] = electrical_visual_qa
        document.visualQa["dependencyGraph"] = copy.deepcopy(dependency_visual_qa)
        document.visualQa["preflightReview"] = copy.deepcopy(preflight_review or {})
        document.visualQa["documentRulebook"] = copy.deepcopy(document_rulebook)
        attach_hierarchy_views(document.visualQa)
    return options


def _build_source_driven_combined_option(
    project_id: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
) -> tuple[LayoutOption, DrawingDocument]:
    system_color_map = discover_system_color_map(pages, candidates, source_paths, SYSTEM_COLOR_REFERENCE_COLORS)
    styles = _styles(system_color_map)
    groups = _overview_groups(pages, source_paths)
    detected_groups = [name for name, _group_pages in groups] or ["OTHER"]
    objects = _source_driven_combined_objects(pages, candidates, matches, source_paths, styles, groups, system_color_map)
    _mark_layout_mode(objects, "source_driven_combined")
    _mark_source_generated(objects)
    _polish_compiled_objects(objects)
    document_width, document_height = _source_driven_document_size(objects)
    qa_pipes = _source_driven_qa_pipes(objects)
    qa_labels = _source_driven_qa_labels(objects)
    visual_qa = {
        "crossings": _count_crossings(qa_pipes),
        "labelOverlaps": _count_label_overlaps(qa_labels),
        "disconnectedContinuations": _count_disconnected(candidates, matches),
        "detectedGroups": detected_groups,
        "sourcePages": len(pages),
        "sourceContinuations": len(candidates),
        "sourceVectorObjects": _source_vector_object_count(objects),
        "editableObjects": len(objects),
        "stitchedSourcePages": len(pages) > 1,
        "stitchedPageTiles": len(pages) if len(pages) > 1 else 0,
        "canvasWidth": document_width,
        "canvasHeight": document_height,
        "canvasExpanded": document_width > _OVERVIEW_WIDTH or document_height > _OVERVIEW_HEIGHT,
    }
    project_namespace = _stable_hash(project_id)
    drawing_id = f"drawing_{project_namespace}_source_driven_combined"
    document = DrawingDocument(
        id=drawing_id,
        projectId=project_id,
        name="Source-driven Combined P&ID",
        width=document_width,
        height=document_height,
        objects=objects,
        sourcePages=pages,
        styles=styles,
        visualQa=visual_qa,
    )
    option = LayoutOption(
        id=f"layout_{project_namespace}_source_driven_combined",
        projectId=project_id,
        drawingId=drawing_id,
        name="Source-driven Combined P&ID",
        description="Primary editable combined P&ID inferred from the uploaded source drawings, systems, tags, and off-sheet continuations.",
        score=_clamp_score(92.0 - min(visual_qa["labelOverlaps"], 24) * 0.24 - visual_qa["crossings"] * 0.045),
        metrics={
            "sourceDriven": True,
            "sourceAudit": True,
            "primaryOutput": False,
            "detectedGroups": detected_groups,
            "sourcePages": len(pages),
            "sourceContinuations": len(candidates),
            "sourceVectorObjects": visual_qa["sourceVectorObjects"],
            "editableObjects": len(objects),
            "stitchedSourcePages": visual_qa["stitchedSourcePages"],
            "stitchedPageTiles": visual_qa["stitchedPageTiles"],
            "canvasExpanded": visual_qa["canvasExpanded"],
        },
    )
    return option, document


def _source_driven_document_size(objects: list[DrawingObject]) -> tuple[float, float]:
    if not objects:
        return _OVERVIEW_WIDTH, _OVERVIEW_HEIGHT
    max_x = max(obj.bounds["x"] + obj.bounds["width"] for obj in objects)
    max_y = max(obj.bounds["y"] + obj.bounds["height"] for obj in objects)
    width = max(_OVERVIEW_WIDTH, min(14000.0, max_x + 180.0))
    height = max(_OVERVIEW_HEIGHT, min(10000.0, max_y + 180.0))
    return width, height


def _source_driven_qa_pipes(objects: list[DrawingObject]) -> list[DrawingObject]:
    return [
        obj
        for obj in objects
        if obj.kind == "pipe"
        and obj.metadata.get("singleSheetReconstructionVector") is not True
        and obj.metadata.get("sourceDerived") is not True
    ]


def _source_driven_qa_labels(objects: list[DrawingObject]) -> list[DrawingObject]:
    return [
        obj
        for obj in objects
        if obj.kind == "label"
        and obj.metadata.get("singleSheetReconstructionText") is not True
        and obj.metadata.get("sourceCoverage") is not True
    ]


def _build_clean_overview_option(
    project_id: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
) -> tuple[LayoutOption, DrawingDocument]:
    styles = _styles()
    objects = _overview_objects(pages, candidates, matches, source_paths, styles)
    _mark_layout_mode(objects, "clean_overview")
    visual_qa = {
        "crossings": _count_crossings([obj for obj in objects if obj.kind == "pipe"]),
        "labelOverlaps": _count_label_overlaps([obj for obj in objects if obj.kind == "label"]),
        "disconnectedContinuations": _count_disconnected(candidates, matches),
    }
    project_namespace = _stable_hash(project_id)
    drawing_id = f"drawing_{project_namespace}_clean_overview"
    document = DrawingDocument(
        id=drawing_id,
        projectId=project_id,
        name="Clean overview P&ID Stitch",
        width=_OVERVIEW_WIDTH,
        height=_OVERVIEW_HEIGHT,
        objects=objects,
        sourcePages=pages,
        styles=styles,
        visualQa=visual_qa,
    )
    option = LayoutOption(
        id=f"layout_{project_namespace}_clean_overview",
        projectId=project_id,
        drawingId=drawing_id,
        name="Clean overview",
        description="Editable Visio-style system overview generated from extracted equipment, line, and continuation tags.",
        score=_clamp_score(82.0 - visual_qa["crossings"] * 0.75 - visual_qa["labelOverlaps"] * 0.5),
        metrics={
            "crossings": visual_qa["crossings"],
            "labelOverlaps": visual_qa["labelOverlaps"],
            "sourceFaithfulness": 0.64,
            "matchedContinuations": len(matches),
        },
    )
    return option, document


def _build_recommended_combined_option(
    project_id: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
) -> tuple[LayoutOption, DrawingDocument]:
    styles = _styles()
    objects = _combined_pid_objects(pages, candidates, matches, source_paths, styles)
    _mark_layout_mode(objects, "combined_pid")
    visual_qa = {
        "crossings": _count_crossings([obj for obj in objects if obj.kind == "pipe"]),
        "labelOverlaps": _count_label_overlaps([obj for obj in objects if obj.kind == "label"]),
        "disconnectedContinuations": _count_disconnected(candidates, matches),
    }
    project_namespace = _stable_hash(project_id)
    drawing_id = f"drawing_{project_namespace}_recommended"
    document = DrawingDocument(
        id=drawing_id,
        projectId=project_id,
        name="Recommended Combined P&ID",
        width=_OVERVIEW_WIDTH,
        height=_OVERVIEW_HEIGHT,
        objects=objects,
        sourcePages=pages,
        styles=styles,
        visualQa=visual_qa,
    )
    option = LayoutOption(
        id=f"layout_{project_namespace}_recommended",
        projectId=project_id,
        drawingId=drawing_id,
        name="Recommended",
        description="Editable combined P&ID-style drawing generated from extracted equipment, line tags, and off-sheet continuations.",
        score=_clamp_score(92.0 - min(visual_qa["labelOverlaps"], 12) * 0.45 - _count_disconnected(candidates, matches) * 0.03),
        metrics={
            "sourceFaithfulness": 0.72,
            "matchedContinuations": len(matches),
            "systemZones": len(_overview_groups(pages, source_paths)),
            "editableObjects": len(objects),
        },
    )
    return option, document


def _build_source_generated_chw_cw_option(
    project_id: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
) -> tuple[LayoutOption, DrawingDocument] | None:
    group_pages = dict(_overview_groups(pages, source_paths)).get("CHW / CW", [])
    if not group_pages:
        return None

    styles = _styles()
    source_ids = _page_ids(group_pages)
    source_graph = build_source_graph(group_pages, candidates, source_paths, "CHW / CW")
    objects: list[DrawingObject] = []
    plant_bounds = {"x": 100.0, "y": 160.0, "width": 2365.0, "height": 1980.0}
    distribution_bounds = {"x": 2525.0, "y": 380.0, "width": 650.0, "height": 1545.0}

    objects.append(
        _overview_label(
            "source_generated_chw_cw_title",
            f"{PROJECT_CODE} CHILLED WATER / COOLING WATER SYSTEM OVERVIEW",
            {"x": 980.0, "y": 54.0, "width": 1500.0, "height": 30.0},
            "#0f172a",
            22.0,
            source_ids,
        )
    )
    objects.append(
        _overview_label(
            "source_generated_chw_cw_subtitle",
            "Generated from uploaded source P&IDs; editable house-style layout",
            {"x": 1040.0, "y": 92.0, "width": 1280.0, "height": 20.0},
            "#475569",
            10.5,
            source_ids,
        )
    )
    objects.append(_overview_region("source_generated_chw_cw_plant_zone", "", plant_bounds, "#7c3aed", "#f7f3ff", 0.08, source_ids, {"hideCenterLabel": True}))
    objects.append(_overview_region("source_generated_chw_cw_distribution_zone", "", distribution_bounds, "#0284c7", "#ffffff", 0.1, source_ids, {"hideCenterLabel": True}))
    _add_zone_label(objects, "source_generated_chw_cw_plant_zone_label", "CHILLED WATER / COOLING WATER", plant_bounds, "#4c1d95", source_ids)
    _add_zone_label(objects, "source_generated_chw_cw_distribution_zone_label", "BUILDING / SITE DISTRIBUTION", distribution_bounds, "#075985", source_ids)
    _add_source_generated_chw_cw_detail_boxes(objects, "source_generated_chw_cw", source_graph, plant_bounds, distribution_bounds)
    _combined_chw_cw_system(objects, group_pages, candidates, source_paths, styles, plant_bounds, distribution_bounds, source_graph)
    _add_source_derived_linework(objects, "source_generated_chw_cw", "CHW / CW", group_pages, plant_bounds, distribution_bounds, source_ids)
    _add_source_generated_distribution_ladder(objects, "source_generated_chw_cw", group_pages, candidates, source_paths, styles, distribution_bounds)
    _add_source_graph_assembly_badges(objects, "source_generated_chw_cw", source_graph, plant_bounds, distribution_bounds)
    _add_source_generated_line_tag_rack(objects, "source_generated_chw_cw", source_graph, styles, plant_bounds)
    _add_source_generated_evidence_tags(objects, "source_generated_chw_cw", group_pages, candidates, source_paths, "CHW / CW")
    _add_reference_title_block(objects, group_pages, source_paths)

    _mark_layout_mode(objects, "source_generated_chw_cw")
    _mark_source_generated(objects)
    visual_qa = {
        "crossings": _count_crossings([obj for obj in objects if obj.kind == "pipe"]),
        "labelOverlaps": _count_label_overlaps([obj for obj in objects if obj.kind == "label"]),
        "disconnectedContinuations": _count_disconnected(candidates, matches),
    }
    project_namespace = _stable_hash(project_id)
    drawing_id = f"drawing_{project_namespace}_source_generated_chw_cw"
    document = DrawingDocument(
        id=drawing_id,
        projectId=project_id,
        name="Source-generated CHW/CW P&ID",
        width=_OVERVIEW_WIDTH,
        height=_OVERVIEW_HEIGHT,
        objects=objects,
        sourcePages=pages,
        styles=styles,
        visualQa=visual_qa,
    )
    option = LayoutOption(
        id=f"layout_{project_namespace}_source_generated_chw_cw",
        projectId=project_id,
        drawingId=drawing_id,
        name="Source-generated CHW/CW",
        description="First source-driven CHW/CW compiler output: source P&ID evidence redrafted into a house-style editable overview without copying the combined Visio template.",
        score=_clamp_score(88.0 - min(visual_qa["labelOverlaps"], 16) * 0.35 - visual_qa["crossings"] * 0.08),
        metrics={
            "sourceGenerated": True,
            "sourceFaithfulness": 0.79,
            "sourcePages": len(group_pages),
            "sourceContinuations": source_graph.metrics["continuations"],
            "extractedEquipment": source_graph.metrics["equipmentTags"],
            "sourceAssemblies": source_graph.metrics["assemblies"],
            "sourceLineTags": source_graph.metrics["lineTags"],
            "sourceVectorObjects": _source_vector_object_count(objects),
            "editableObjects": len(objects),
        },
    )
    return option, document


def _build_source_generated_hhw_hrw_option(
    project_id: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
) -> tuple[LayoutOption, DrawingDocument] | None:
    group_pages = dict(_overview_groups(pages, source_paths)).get("HHW / HRW", [])
    if not group_pages:
        return None

    styles = _styles()
    source_ids = _page_ids(group_pages)
    source_graph = build_source_graph(group_pages, candidates, source_paths, "HHW / HRW")
    objects: list[DrawingObject] = []
    plant_bounds = {"x": 110.0, "y": 160.0, "width": 2385.0, "height": 2055.0}
    distribution_bounds = {"x": 2560.0, "y": 380.0, "width": 620.0, "height": 1545.0}

    objects.append(
        _overview_label(
            "source_generated_hhw_hrw_title",
            f"{PROJECT_CODE} HEATED HOT WATER / HEAT RECOVERY WATER SYSTEM OVERVIEW",
            {"x": 760.0, "y": 54.0, "width": 1800.0, "height": 30.0},
            "#0f172a",
            22.0,
            source_ids,
        )
    )
    objects.append(
        _overview_label(
            "source_generated_hhw_hrw_subtitle",
            "Generated from uploaded HHW / HRW source P&IDs; editable house-style layout",
            {"x": 840.0, "y": 92.0, "width": 1580.0, "height": 20.0},
            "#475569",
            10.5,
            source_ids,
        )
    )
    objects.append(_overview_region("source_generated_hhw_hrw_plant_zone", "", plant_bounds, "#ef4444", "#fff7ed", 0.055, source_ids, {"hideCenterLabel": True}))
    objects.append(_overview_region("source_generated_hhw_hrw_distribution_zone", "", distribution_bounds, "#f97316", "#ffffff", 0.07, source_ids, {"hideCenterLabel": True}))
    _add_zone_label(objects, "source_generated_hhw_hrw_plant_zone_label", "HHW / HRW PLANT AND HEAT RECOVERY", plant_bounds, "#991b1b", source_ids)
    _add_zone_label(objects, "source_generated_hhw_hrw_distribution_zone_label", "BUILDING / SITE DISTRIBUTION", distribution_bounds, "#9a3412", source_ids)
    _add_source_generated_hhw_hrw_detail_boxes(objects, "source_generated_hhw_hrw", source_graph, plant_bounds, distribution_bounds)
    _combined_hhw_hrw_system(objects, group_pages, candidates, source_paths, styles, plant_bounds, distribution_bounds)
    _add_source_derived_linework(objects, "source_generated_hhw_hrw", "HHW / HRW", group_pages, plant_bounds, distribution_bounds, source_ids)
    _add_source_graph_assembly_badges(objects, "source_generated_hhw_hrw", source_graph, plant_bounds, distribution_bounds)
    _add_source_generated_line_tag_rack(objects, "source_generated_hhw_hrw", source_graph, styles, plant_bounds)
    _add_source_generated_coverage_index(objects, "source_generated_hhw_hrw", source_graph, plant_bounds, candidates, group_pages, source_paths)
    _add_reference_title_block(objects, group_pages, source_paths)

    _mark_layout_mode(objects, "source_generated_hhw_hrw")
    _mark_source_generated(objects)
    _polish_compiled_objects(objects)
    visual_qa = {
        "crossings": _count_crossings([obj for obj in objects if obj.kind == "pipe"]),
        "labelOverlaps": _count_label_overlaps([obj for obj in objects if obj.kind == "label"]),
        "disconnectedContinuations": _count_disconnected(candidates, matches),
    }
    project_namespace = _stable_hash(project_id)
    drawing_id = f"drawing_{project_namespace}_source_generated_hhw_hrw"
    document = DrawingDocument(
        id=drawing_id,
        projectId=project_id,
        name="Source-generated HHW/HRW P&ID",
        width=_OVERVIEW_WIDTH,
        height=_OVERVIEW_HEIGHT,
        objects=objects,
        sourcePages=pages,
        styles=styles,
        visualQa=visual_qa,
    )
    option = LayoutOption(
        id=f"layout_{project_namespace}_source_generated_hhw_hrw",
        projectId=project_id,
        drawingId=drawing_id,
        name="Source-generated HHW/HRW",
        description="Source-first HHW/HRW compiler output: uploaded P&ID evidence redrafted into an editable house-style overview without copying a combined Visio template.",
        score=_clamp_score(87.5 - min(visual_qa["labelOverlaps"], 16) * 0.35 - visual_qa["crossings"] * 0.08),
        metrics={
            "sourceGenerated": True,
            "sourceFaithfulness": 0.8,
            "sourcePages": len(group_pages),
            "sourceContinuations": source_graph.metrics["continuations"],
            "extractedEquipment": source_graph.metrics["equipmentTags"],
            "sourceAssemblies": source_graph.metrics["assemblies"],
            "sourceLineTags": source_graph.metrics["lineTags"],
            "sourceVectorObjects": _source_vector_object_count(objects),
            "editableObjects": len(objects),
        },
    )
    return option, document


def _build_presentation_clean_hhw_hrw_option(
    project_id: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
) -> tuple[LayoutOption, DrawingDocument] | None:
    group_pages = dict(_overview_groups(pages, source_paths)).get("HHW / HRW", [])
    if not group_pages:
        return None

    styles = _styles()
    source_ids = _page_ids(group_pages)
    source_graph = build_source_graph(group_pages, candidates, source_paths, "HHW / HRW")
    objects: list[DrawingObject] = []
    plant_bounds = {"x": 112.0, "y": 160.0, "width": 2220.0, "height": 1875.0}
    distribution_bounds = {"x": 2420.0, "y": 420.0, "width": 610.0, "height": 1325.0}

    objects.append(
        _overview_label(
            "presentation_clean_hhw_hrw_title",
            f"{PROJECT_CODE} HEATED HOT WATER / HEAT RECOVERY WATER SYSTEM OVERVIEW",
            {"x": 760.0, "y": 54.0, "width": 1800.0, "height": 30.0},
            "#0f172a",
            22.0,
            source_ids,
        )
    )
    objects.append(
        _overview_label(
            "presentation_clean_hhw_hrw_subtitle",
            "Source-first combined P&ID with full coverage proof kept in the QA band",
            {"x": 940.0, "y": 92.0, "width": 1380.0, "height": 20.0},
            "#475569",
            10.5,
            source_ids,
        )
    )
    objects.append(_overview_region("presentation_clean_hhw_hrw_plant_zone", "", plant_bounds, "#ef4444", "#fff7ed", 0.045, source_ids, {"hideCenterLabel": True}))
    objects.append(_overview_region("presentation_clean_hhw_hrw_distribution_zone", "", distribution_bounds, "#f97316", "#ffffff", 0.06, source_ids, {"hideCenterLabel": True}))
    _add_zone_label(objects, "presentation_clean_hhw_hrw_plant_zone_label", "HHW / HRW PLANT AND HEAT RECOVERY", plant_bounds, "#991b1b", source_ids)
    _add_zone_label(objects, "presentation_clean_hhw_hrw_distribution_zone_label", "BUILDING / SITE DISTRIBUTION", distribution_bounds, "#9a3412", source_ids)
    _add_source_generated_hhw_hrw_detail_boxes(objects, "presentation_clean_hhw_hrw", source_graph, plant_bounds, distribution_bounds)
    _combined_hhw_hrw_system(objects, group_pages, candidates, source_paths, styles, plant_bounds, distribution_bounds)
    _add_presentation_hhw_hrw_route_bundle(objects, "presentation_clean_hhw_hrw", group_pages, candidates, source_paths, source_graph, styles, plant_bounds, distribution_bounds)
    _add_source_derived_linework(objects, "presentation_clean_hhw_hrw", "HHW / HRW", group_pages, plant_bounds, distribution_bounds, source_ids, limit_per_page=14, opacity=0.18)
    _add_source_graph_assembly_badges(objects, "presentation_clean_hhw_hrw", source_graph, plant_bounds, distribution_bounds)
    _add_source_generated_coverage_index(objects, "presentation_clean_hhw_hrw", source_graph, plant_bounds, candidates, group_pages, source_paths)
    _add_reference_title_block(objects, group_pages, source_paths)

    _mark_layout_mode(objects, "presentation_clean_hhw_hrw")
    _mark_source_generated(objects)
    for obj in objects:
        obj.metadata["presentationClean"] = True
    _polish_compiled_objects(objects)
    visual_qa = {
        "crossings": _count_crossings([obj for obj in objects if obj.kind == "pipe"]),
        "labelOverlaps": _count_label_overlaps([obj for obj in objects if obj.kind == "label"]),
        "disconnectedContinuations": _count_disconnected(candidates, matches),
    }
    project_namespace = _stable_hash(project_id)
    drawing_id = f"drawing_{project_namespace}_presentation_clean_hhw_hrw"
    document = DrawingDocument(
        id=drawing_id,
        projectId=project_id,
        name="Presentation-clean HHW/HRW P&ID",
        width=_OVERVIEW_WIDTH,
        height=_OVERVIEW_HEIGHT,
        objects=objects,
        sourcePages=pages,
        styles=styles,
        visualQa=visual_qa,
    )
    option = LayoutOption(
        id=f"layout_{project_namespace}_presentation_clean_hhw_hrw",
        projectId=project_id,
        drawingId=drawing_id,
        name="Presentation-clean HHW/HRW",
        description="Cleaner source-first HHW/HRW combined P&ID that keeps full source coverage in a compact QA band while reducing visual noise in the main drawing.",
        score=_clamp_score(90.0 - min(visual_qa["labelOverlaps"], 16) * 0.3 - visual_qa["crossings"] * 0.06),
        metrics={
            "sourceGenerated": True,
            "presentationClean": True,
            "sourceFaithfulness": 0.78,
            "sourcePages": len(group_pages),
            "sourceContinuations": source_graph.metrics["continuations"],
            "extractedEquipment": source_graph.metrics["equipmentTags"],
            "sourceAssemblies": source_graph.metrics["assemblies"],
            "sourceLineTags": source_graph.metrics["lineTags"],
            "sourceVectorObjects": _source_vector_object_count(objects),
            "editableObjects": len(objects),
        },
    )
    return option, document


def _build_full_combined_hhw_hrw_option(
    project_id: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
) -> tuple[LayoutOption, DrawingDocument] | None:
    group_pages = dict(_overview_groups(pages, source_paths)).get("HHW / HRW", [])
    if not group_pages:
        return None

    styles = _styles()
    source_ids = _page_ids(group_pages)
    source_graph = build_source_graph(group_pages, candidates, source_paths, "HHW / HRW")
    objects: list[DrawingObject] = []
    full_width = 4300.0
    full_height = 3800.0
    plant_bounds = {"x": 120.0, "y": 170.0, "width": 3000.0, "height": 3350.0}
    distribution_bounds = {"x": 3260.0, "y": 430.0, "width": 900.0, "height": 2760.0}

    objects.append(
        _overview_label(
            "full_combined_hhw_hrw_title",
            f"{PROJECT_CODE} HEATED HOT WATER / HEAT RECOVERY WATER FULL COMBINED P&ID",
            {"x": 760.0, "y": 54.0, "width": 2200.0, "height": 30.0},
            "#0f172a",
            22.0,
            source_ids,
        )
    )
    objects.append(
        _overview_label(
            "full_combined_hhw_hrw_subtitle",
            "Strict source reconstruction: required equipment remains visible; extracted line tags are preserved in the register",
            {"x": 900.0, "y": 92.0, "width": 1900.0, "height": 20.0},
            "#475569",
            10.5,
            source_ids,
        )
    )
    objects.append(_overview_region("full_combined_hhw_hrw_plant_zone", "", plant_bounds, "#ef4444", "#fff7ed", 0.05, source_ids, {"hideCenterLabel": True}))
    objects.append(_overview_region("full_combined_hhw_hrw_distribution_zone", "", distribution_bounds, "#f97316", "#ffffff", 0.08, source_ids, {"hideCenterLabel": True}))
    _add_zone_label(objects, "full_combined_hhw_hrw_plant_zone_label", "HHW / HRW PLANT AND HEAT RECOVERY", plant_bounds, "#991b1b", source_ids)
    _add_zone_label(objects, "full_combined_hhw_hrw_distribution_zone_label", "BUILDING / SITE DISTRIBUTION", distribution_bounds, "#9a3412", source_ids)
    _add_source_generated_hhw_hrw_detail_boxes(objects, "full_combined_hhw_hrw", source_graph, plant_bounds, distribution_bounds)
    _combined_hhw_hrw_system(objects, group_pages, candidates, source_paths, styles, plant_bounds, distribution_bounds)
    staged_equipment_register = _add_full_source_equipment_body(
        objects,
        "full_combined_hhw_hrw",
        source_graph,
        plant_bounds,
        distribution_bounds,
        styles,
        hidden_buckets={"pumps"},
    )
    line_tag_register = _line_tag_register(source_graph)
    _add_presentation_hhw_hrw_route_bundle(objects, "full_combined_hhw_hrw", group_pages, candidates, source_paths, source_graph, styles, plant_bounds, distribution_bounds)
    _add_source_derived_linework(objects, "full_combined_hhw_hrw", "HHW / HRW", group_pages, plant_bounds, distribution_bounds, source_ids, limit_per_page=28, opacity=0.24)
    _add_source_graph_assembly_badges(objects, "full_combined_hhw_hrw", source_graph, plant_bounds, distribution_bounds)
    _add_strict_coverage_gate(objects, "full_combined_hhw_hrw", source_graph, plant_bounds, distribution_bounds, staged_equipment_register)
    _add_reference_title_block(objects, group_pages, source_paths, full_width)

    _mark_layout_mode(objects, "full_combined_hhw_hrw")
    _mark_source_generated(objects)
    for obj in objects:
        obj.metadata["fullCombined"] = True
    _polish_compiled_objects(objects)
    connectivity_qa = _annotate_connector_connectivity(objects)
    required_equipment = set(source_graph.equipmentTags)
    visible_equipment = _visible_required_metadata_values(objects, "equipmentTag", "sourceRequiredEquipment")
    registered_equipment = visible_equipment | {str(item["tag"]) for item in staged_equipment_register}
    required_lines = {str(item["tag"]) for item in line_tag_register}
    registered_lines = {str(item["tag"]) for item in line_tag_register}
    visual_qa = {
        "crossings": _count_crossings([obj for obj in objects if obj.kind == "pipe"]),
        "labelOverlaps": _count_label_overlaps([obj for obj in objects if obj.kind == "label"]),
        "disconnectedContinuations": _count_disconnected(candidates, matches),
        "requiredEquipmentTags": len(required_equipment),
        "visibleEquipmentTags": len(visible_equipment),
        "missingVisibleEquipmentTags": len(required_equipment - visible_equipment),
        "registeredEquipmentTags": len(registered_equipment),
        "missingRegisteredEquipmentTags": len(required_equipment - registered_equipment),
        "equipmentRegister": staged_equipment_register,
        "requiredLineTags": len(required_lines),
        "registeredLineTags": len(registered_lines),
        "missingRegisteredLineTags": len(required_lines - registered_lines),
        "lineTagRegister": line_tag_register,
        "connectivity": connectivity_qa,
    }
    project_namespace = _stable_hash(project_id)
    drawing_id = f"drawing_{project_namespace}_full_combined_hhw_hrw"
    document = DrawingDocument(
        id=drawing_id,
        projectId=project_id,
        name="Full Combined HHW/HRW P&ID",
        width=full_width,
        height=full_height,
        objects=objects,
        sourcePages=pages,
        styles=styles,
        visualQa=visual_qa,
    )
    missing_penalty = visual_qa["missingRegisteredEquipmentTags"] * 4.0 + visual_qa["missingRegisteredLineTags"] * 1.25
    option = LayoutOption(
        id=f"layout_{project_namespace}_full_combined_hhw_hrw",
        projectId=project_id,
        drawingId=drawing_id,
        name="Full Combined HHW/HRW",
        description="Coverage-complete HHW/HRW combined P&ID: extracted equipment is emitted as editable drawing-body objects, with source line tags preserved in the line tag register.",
        score=_clamp_score(94.0 - missing_penalty - min(visual_qa["labelOverlaps"], 24) * 0.22 - visual_qa["crossings"] * 0.025),
        metrics={
            "sourceGenerated": True,
            "fullCombined": True,
            "sourceFaithfulness": 0.9,
            "sourcePages": len(group_pages),
            "sourceContinuations": source_graph.metrics["continuations"],
            "sourceAssemblies": source_graph.metrics["assemblies"],
            "requiredEquipmentTags": len(required_equipment),
            "visibleEquipmentTags": len(visible_equipment),
            "missingVisibleEquipmentTags": visual_qa["missingVisibleEquipmentTags"],
            "registeredEquipmentTags": len(registered_equipment),
            "hiddenEquipmentTags": len(staged_equipment_register),
            "missingRegisteredEquipmentTags": visual_qa["missingRegisteredEquipmentTags"],
            "requiredLineTags": len(required_lines),
            "registeredLineTags": len(registered_lines),
            "missingRegisteredLineTags": visual_qa["missingRegisteredLineTags"],
            "connectivityConnectablePipes": connectivity_qa["connectablePipes"],
            "connectivityConnectedEndpoints": connectivity_qa["connectedEndpoints"],
            "connectivityDanglingEndpoints": connectivity_qa["danglingEndpoints"],
            "connectivityNodeToNodePipes": connectivity_qa["nodeToNodePipes"],
            "sourceVectorObjects": _source_vector_object_count(objects),
            "editableObjects": len(objects),
        },
    )
    return option, document


def _build_template_compiled_options(
    project_id: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
) -> list[tuple[LayoutOption, DrawingDocument]]:
    group_map = dict(_overview_groups(pages, source_paths))
    options: list[tuple[LayoutOption, DrawingDocument]] = []
    for group_name, slug, title in [
        ("CHW / CW", "compiled_chw_cw", "Compiled CHW/CW"),
        ("CHW / CW", "compiled_chw_ctw_baseline", "Compiled CHW/CTW Baseline"),
        ("HHW / HRW", "compiled_hhw_hrw", "Compiled HHW/HRW"),
    ]:
        group_pages = group_map.get(group_name, [])
        if not group_pages:
            continue
        options.append(
            _build_template_compiled_option(
                project_id,
                group_name,
                slug,
                title,
                group_pages,
                pages,
                candidates,
                matches,
                source_paths,
            )
        )
    trace_group = "CHW / CW" if group_map.get("CHW / CW") else "HHW / HRW"
    trace_pages = group_map.get(trace_group, [])
    if trace_pages:
        options.append(
            _build_template_compiled_option(
                project_id,
                trace_group,
                "compiled_trace_overlay",
                "Source Trace Overlay",
                trace_pages,
                pages,
                candidates,
                matches,
                source_paths,
                trace_overlay=True,
            )
        )
    return options


def _build_template_compiled_option(
    project_id: str,
    group_name: str,
    slug: str,
    option_name: str,
    group_pages: list[PageEvidence],
    all_pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
    trace_overlay: bool = False,
) -> tuple[LayoutOption, DrawingDocument]:
    styles = _styles()
    source_ids = _page_ids(group_pages)
    objects: list[DrawingObject] = []
    template_objects, template_stats = load_visio_template_objects(group_name, slug, source_ids)
    if template_objects:
        objects.extend(template_objects)
        if trace_overlay:
            _add_source_to_template_trace_overlay(
                objects,
                slug,
                group_name,
                group_pages,
                candidates,
                source_paths,
                template_stats.width,
                template_stats.height,
            )
    else:
        title = f"{PROJECT_CODE} CHILLED WATER / COOLING WATER SYSTEM OVERVIEW" if group_name == "CHW / CW" else f"{PROJECT_CODE} HEATED HOT WATER / HEAT RECOVERY WATER SYSTEM OVERVIEW"
        objects.append(
            _overview_label(
                f"{slug}_title",
                title,
                {"x": 960.0, "y": 54.0, "width": 1500.0, "height": 28.0},
                "#0f172a",
                22.0,
                source_ids,
            )
        )

        if group_name == "CHW / CW":
            plant_bounds = {"x": 105.0, "y": 170.0, "width": 2360.0, "height": 2215.0}
            distribution_bounds = {"x": 2545.0, "y": 425.0, "width": 610.0, "height": 1560.0}
            objects.append(_overview_region(f"{slug}_plant_zone", "CHILLED WATER / COOLING WATER", plant_bounds, "#7c3aed", "#f5f3ff", 0.045, source_ids, {"hideCenterLabel": True}))
            objects.append(_overview_region(f"{slug}_distribution_zone", "BUILDING / SITE DISTRIBUTION", distribution_bounds, "#0284c7", "#eff6ff", 0.06, source_ids, {"hideCenterLabel": True}))
            _add_zone_label(objects, f"{slug}_plant_zone_label", "CHW / CW PLANT", plant_bounds, "#4c1d95", source_ids)
            _add_zone_label(objects, f"{slug}_distribution_zone_label", "BUILDING TIE-INS", distribution_bounds, "#075985", source_ids)
            _add_system_compiled_detail_boxes(objects, slug, group_name, plant_bounds, distribution_bounds, source_ids)
            _combined_chw_cw_system(objects, group_pages, candidates, source_paths, styles, plant_bounds, distribution_bounds)
            _combined_distribution(objects, group_pages, styles, distribution_bounds)
            _add_source_derived_linework(objects, slug, group_name, group_pages, plant_bounds, distribution_bounds, source_ids)
            _add_overview_review_notes(objects, slug, group_name, plant_bounds, distribution_bounds, source_ids)
        else:
            plant_bounds = {"x": 115.0, "y": 170.0, "width": 2360.0, "height": 2215.0}
            distribution_bounds = {"x": 2525.0, "y": 425.0, "width": 610.0, "height": 1560.0}
            objects.append(_overview_region(f"{slug}_plant_zone", "HEATED HOT WATER / HRW", plant_bounds, "#ef4444", "#fff1f2", 0.04, source_ids, {"hideCenterLabel": True}))
            objects.append(_overview_region(f"{slug}_distribution_zone", "BUILDING / SITE DISTRIBUTION", distribution_bounds, "#f97316", "#fff7ed", 0.055, source_ids, {"hideCenterLabel": True}))
            _add_zone_label(objects, f"{slug}_plant_zone_label", "HHW / HRW PLANT", plant_bounds, "#991b1b", source_ids)
            _add_zone_label(objects, f"{slug}_distribution_zone_label", "BUILDING TIE-INS", distribution_bounds, "#9a3412", source_ids)
            _add_system_compiled_detail_boxes(objects, slug, group_name, plant_bounds, distribution_bounds, source_ids)
            _combined_hhw_hrw_system(objects, group_pages, candidates, source_paths, styles, plant_bounds, distribution_bounds)
            _combined_distribution(objects, group_pages, styles, distribution_bounds)
            _add_source_derived_linework(objects, slug, group_name, group_pages, plant_bounds, distribution_bounds, source_ids)
            _add_overview_review_notes(objects, slug, group_name, plant_bounds, distribution_bounds, source_ids)

        _add_reference_title_block(objects, all_pages, source_paths)
    _polish_compiled_objects(objects)
    _mark_layout_mode(objects, slug)
    visual_qa = {
        "crossings": _count_crossings([obj for obj in objects if obj.kind == "pipe"]),
        "labelOverlaps": _count_label_overlaps([obj for obj in objects if obj.kind == "label"]),
        "disconnectedContinuations": _count_disconnected(candidates, matches),
    }
    project_namespace = _stable_hash(project_id)
    drawing_id = f"drawing_{project_namespace}_{slug}"
    document = DrawingDocument(
        id=drawing_id,
        projectId=project_id,
        name=f"{option_name} P&ID",
        width=template_stats.width if template_stats else _OVERVIEW_WIDTH,
        height=template_stats.height if template_stats else _OVERVIEW_HEIGHT,
        objects=objects,
        sourcePages=all_pages,
        styles=styles,
        visualQa=visual_qa,
    )
    option = LayoutOption(
        id=f"layout_{project_namespace}_{slug}",
        projectId=project_id,
        drawingId=drawing_id,
        name=option_name,
        description=f"house-style editable {group_name} compiled P&ID focused on one system sheet.",
        score=_clamp_score(93.0 - min(visual_qa["labelOverlaps"], 12) * 0.35 - _count_disconnected(candidates, matches) * 0.02),
        metrics={
            "sourceFaithfulness": 0.94 if template_stats else (0.82 if _source_vector_object_count(objects) else 0.76),
            "matchedContinuations": len(matches),
            "editableObjects": len(objects),
            "systemPages": len(group_pages),
            "sourceVectorObjects": _source_vector_object_count(objects),
            "visioTemplateObjects": _template_object_count(objects),
            "visioTemplatePath": template_stats.path if template_stats else "",
            "visioTemplateConnectors": template_stats.connectors if template_stats else 0,
            "visioTemplateTexts": template_stats.texts if template_stats else 0,
            "sourceTraceObjects": _source_trace_object_count(objects),
        },
    )
    return option, document


def _build_option(
    slug: str,
    name: str,
    description: str,
    project_id: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    page_gap: float,
    source_faithfulness: float,
    layout_mode: Literal["recommended", "source_faithful"],
    source_paths: dict[str, str],
) -> tuple[LayoutOption, DrawingDocument]:
    page_transforms = _page_transforms(pages, page_gap, layout_mode)
    page_by_source = {(page.sourceFileId, page.page): page for page in pages}
    candidate_by_id = {candidate.id: candidate for candidate in candidates}
    renderable_matches = _renderable_matches(matches, candidate_by_id)
    styles = _styles()

    objects: list[DrawingObject] = []
    objects.extend(_source_fragment_objects(pages, page_transforms, source_paths))
    objects.extend(_label_objects(candidates, page_transforms, page_by_source, styles))
    objects.extend(_pipe_objects(renderable_matches, candidate_by_id, page_transforms, page_by_source, styles))

    visual_qa = {
        "crossings": _count_crossings([obj for obj in objects if obj.kind == "pipe"]),
        "labelOverlaps": _count_label_overlaps([obj for obj in objects if obj.kind == "label"]),
        "disconnectedContinuations": _count_disconnected(candidates, renderable_matches),
    }
    width, height = _document_size(objects)
    project_namespace = _stable_hash(project_id)
    drawing_id = f"drawing_{project_namespace}_{slug}"
    document = DrawingDocument(
        id=drawing_id,
        projectId=project_id,
        name=f"{name} P&ID Stitch",
        width=width,
        height=height,
        objects=objects,
        sourcePages=pages,
        styles=styles,
        visualQa=visual_qa,
    )
    option = LayoutOption(
        id=f"layout_{project_namespace}_{slug}",
        projectId=project_id,
        drawingId=drawing_id,
        name=name,
        description=description,
        score=_clamp_score(
            100.0
            - visual_qa["disconnectedContinuations"] * 0.35
            - visual_qa["crossings"] * 1.5
            - visual_qa["labelOverlaps"] * 1.0
        ),
        metrics={
            "crossings": visual_qa["crossings"],
            "labelOverlaps": visual_qa["labelOverlaps"],
            "sourceFaithfulness": source_faithfulness,
        },
    )
    return option, document


def _page_transforms(
    pages: list[PageEvidence],
    page_gap: float,
    layout_mode: Literal["recommended", "source_faithful"],
) -> dict[tuple[str, int], PageTransform]:
    if layout_mode == "recommended":
        return _overview_page_transforms(pages, page_gap)
    return _source_faithful_page_transforms(pages, page_gap)


def _source_faithful_page_transforms(pages: list[PageEvidence], page_gap: float) -> dict[tuple[str, int], PageTransform]:
    transforms: dict[tuple[str, int], PageTransform] = {}
    cursor_x = _PAGE_MARGIN
    for page in _sorted_pages(pages):
        transforms[(page.sourceFileId, page.page)] = {
            "x": cursor_x,
            "y": _PAGE_MARGIN,
            "scale": 1.0,
            "cropX": page.cropBounds["x"],
            "cropY": page.cropBounds["y"],
        }
        cursor_x += page.cropBounds["width"] + page_gap
    return transforms


def _overview_page_transforms(pages: list[PageEvidence], page_gap: float) -> dict[tuple[str, int], PageTransform]:
    ordered_pages = _sorted_pages(pages)
    if not ordered_pages:
        return {}

    columns = min(_OVERVIEW_COLUMNS, max(1, len(ordered_pages)))
    rows = (len(ordered_pages) + columns - 1) // columns
    slot_gap = page_gap
    usable_width = _OVERVIEW_WIDTH - (_OVERVIEW_MARGIN_X * 2.0) - slot_gap * (columns - 1)
    usable_height = _OVERVIEW_HEIGHT - _OVERVIEW_MARGIN_TOP - _OVERVIEW_MARGIN_BOTTOM - slot_gap * (rows - 1)
    slot_width = max(1.0, usable_width / columns)
    slot_height = max(1.0, usable_height / rows)

    transforms: dict[tuple[str, int], PageTransform] = {}
    for index, page in enumerate(ordered_pages):
        row = index // columns
        column = index % columns
        scale = min(slot_width / max(1.0, page.cropBounds["width"]), slot_height / max(1.0, page.cropBounds["height"]))
        scaled_width = page.cropBounds["width"] * scale
        scaled_height = page.cropBounds["height"] * scale
        slot_x = _OVERVIEW_MARGIN_X + column * (slot_width + slot_gap)
        slot_y = _OVERVIEW_MARGIN_TOP + row * (slot_height + slot_gap)
        transforms[(page.sourceFileId, page.page)] = {
            "x": slot_x + (slot_width - scaled_width) / 2.0,
            "y": slot_y + (slot_height - scaled_height) / 2.0,
            "scale": scale,
            "cropX": page.cropBounds["x"],
            "cropY": page.cropBounds["y"],
        }
    return transforms


def _sorted_pages(pages: list[PageEvidence]) -> list[PageEvidence]:
    return sorted(pages, key=lambda item: (item.sourceFileId, item.page, item.id))


def _validate_unique_candidate_ids(candidates: list[ContinuationCandidate]) -> None:
    seen_ids: set[str] = set()
    for candidate in candidates:
        if candidate.id in seen_ids:
            raise ValueError(f"Duplicate continuation candidate id: {candidate.id}")
        seen_ids.add(candidate.id)


def _renderable_matches(
    matches: list[ContinuationMatch],
    candidate_by_id: dict[str, ContinuationCandidate],
) -> list[ContinuationMatch]:
    return [
        match
        for match in matches
        if match.sourceCandidateId in candidate_by_id and match.targetCandidateId in candidate_by_id
    ]


def _source_fragment_objects(
    pages: list[PageEvidence],
    page_transforms: dict[tuple[str, int], PageTransform],
    source_paths: dict[str, str],
) -> list[DrawingObject]:
    style = DrawingStyle(stroke="#94a3b8", fill="none", strokeWidth=1.0, opacity=1.0)
    objects: list[DrawingObject] = []
    for page in _sorted_pages(pages):
        transform = page_transforms[(page.sourceFileId, page.page)]
        bounds = {
            "x": transform["x"],
            "y": transform["y"],
            "width": page.cropBounds["width"] * transform["scale"],
            "height": page.cropBounds["height"] * transform["scale"],
        }
        metadata: dict[str, Any] = {
            "sourceFileId": page.sourceFileId,
            "page": page.page,
            "scale": transform["scale"],
            "cropBounds": dict(page.cropBounds),
        }
        if page.sourceFileId in source_paths:
            metadata["sourcePath"] = source_paths[page.sourceFileId]
        objects.append(
            DrawingObject(
                id=_object_id("source_fragment", page.id),
                kind="source_fragment",
                label=f"{page.sourceFileId} p{page.page}",
                points=_rect_points(bounds),
                bounds=bounds,
                style=style,
                sourceEvidenceIds=[page.id],
                locked=True,
                metadata=metadata,
            )
        )
    return objects


def _label_objects(
    candidates: list[ContinuationCandidate],
    page_transforms: dict[tuple[str, int], PageTransform],
    page_by_source: dict[tuple[str, int], PageEvidence],
    styles: dict[str, DrawingStyle],
) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    for candidate in sorted(candidates, key=lambda item: item.id):
        transform = _candidate_transform(candidate, page_transforms, page_by_source)
        bounds = _offset_bounds(candidate.bounds, transform)
        objects.append(
            DrawingObject(
                id=_object_id("label", candidate.id),
                kind="label",
                label=candidate.label,
                points=[_center(bounds)],
                bounds=bounds,
                style=_label_style(candidate.system, styles, transform["scale"]),
                sourceEvidenceIds=[candidate.id],
                locked=False,
                metadata={
                    "candidateId": candidate.id,
                    "direction": candidate.direction,
                    "lineTag": candidate.lineTag,
                    "system": candidate.system,
                    "edge": candidate.edge,
                    "evidenceText": candidate.evidenceText,
                },
            )
        )
    return objects


def _pipe_objects(
    matches: list[ContinuationMatch],
    candidate_by_id: dict[str, ContinuationCandidate],
    page_transforms: dict[tuple[str, int], PageTransform],
    page_by_source: dict[tuple[str, int], PageEvidence],
    styles: dict[str, DrawingStyle],
) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    for match in sorted(matches, key=lambda item: item.id):
        source = candidate_by_id.get(match.sourceCandidateId)
        target = candidate_by_id.get(match.targetCandidateId)
        if source is None or target is None:
            continue
        source_transform = _candidate_transform(source, page_transforms, page_by_source)
        target_transform = _candidate_transform(target, page_transforms, page_by_source)
        source_bounds = _offset_bounds(source.bounds, source_transform)
        target_bounds = _offset_bounds(target.bounds, target_transform)
        start = _anchor(source_bounds, source.edge)
        end = _anchor(target_bounds, target.edge)
        points = _orthogonal_points(start, end)
        bounds = _points_bounds(points, _PIPE_PADDING)
        system = source.system or target.system
        objects.append(
            DrawingObject(
                id=_object_id("pipe", match.id, source.id, target.id),
                kind="pipe",
                label=source.lineTag or target.lineTag,
                points=points,
                bounds=bounds,
                style=replace(styles.get(system, styles["DEFAULT"])),
                sourceEvidenceIds=[source.id, target.id, match.id],
                locked=False,
                groupId=_object_id("match", match.id, source.id, target.id),
                metadata={
                    "matchId": match.id,
                    "sourceCandidateId": source.id,
                    "targetCandidateId": target.id,
                    "score": match.score,
                    "status": match.status,
                    "reasons": match.reasons,
                    "system": system,
                },
            )
        )
    return objects


def _overview_objects(
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
    styles: dict[str, DrawingStyle],
) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    source_ids = [page.id for page in pages]
    objects.append(
        _overview_label(
            "overview_title",
            "RECREATED P&ID OVERVIEW",
            {"x": 120.0, "y": 52.0, "width": 1800.0, "height": 42.0},
            "#0f172a",
            34.0,
            source_ids,
        )
    )
    objects.append(
        _overview_label(
            "overview_subtitle",
            f"Editable symbols, tags, and matched off-sheet continuations from {len(pages)} uploaded sheets",
            {"x": 124.0, "y": 102.0, "width": 980.0, "height": 24.0},
            "#475569",
            16.0,
            source_ids,
        )
    )
    objects.extend(_overview_legend(styles))

    groups = _overview_groups(pages, source_paths)
    if not groups:
        return objects

    top = 170.0
    bottom = 120.0
    gap = 54.0
    band_height = (_OVERVIEW_HEIGHT - top - bottom - gap * (len(groups) - 1)) / len(groups)
    for index, (group_name, group_pages) in enumerate(groups):
        band_y = top + index * (band_height + gap)
        objects.extend(_overview_group_objects(group_name, group_pages, candidates, source_paths, styles, band_y, band_height))
    return objects


def _source_driven_combined_objects(
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
    styles: dict[str, DrawingStyle],
    groups: list[tuple[str, list[PageEvidence]]],
    system_color_map: SystemColorMap,
) -> list[DrawingObject]:
    if len(pages) == 1:
        objects = _source_driven_single_sheet_objects(pages[0])
        objects.extend(_source_driven_legend(system_color_map))
        return objects

    return _source_driven_stitched_page_objects(pages, candidates, matches, source_paths, styles, groups, system_color_map)


def _source_driven_overview_objects(
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    source_paths: dict[str, str],
    styles: dict[str, DrawingStyle],
    groups: list[tuple[str, list[PageEvidence]]],
    system_color_map: SystemColorMap,
) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    source_ids = [page.id for page in pages]
    objects.append(
        _overview_label(
            "source_driven_title",
            "SOURCE-DRIVEN COMBINED P&ID",
            {"x": 1040.0, "y": 52.0, "width": 1380.0, "height": 38.0},
            "#0f172a",
            26.0,
            source_ids,
        )
    )
    objects.append(
        _overview_label(
            "source_driven_subtitle",
            f"{len(pages)} source sheet{'s' if len(pages) != 1 else ''} redrafted into editable systems, equipment, lines, instruments, and continuation banks",
            {"x": 920.0, "y": 98.0, "width": 1620.0, "height": 22.0},
            "#475569",
            12.5,
            source_ids,
        )
    )
    objects.extend(_source_driven_legend(system_color_map))

    if not groups:
        return objects

    top = 176.0
    bottom = 132.0
    gap = 62.0 if len(groups) <= 3 else 48.0
    band_height = (_OVERVIEW_HEIGHT - top - bottom - gap * (len(groups) - 1)) / len(groups)
    for index, (group_name, group_pages) in enumerate(groups):
        band_y = top + index * (band_height + gap)
        objects.extend(_overview_group_objects(group_name, group_pages, candidates, source_paths, styles, band_y, band_height))
        band_bounds = {"x": 120.0, "y": band_y, "width": _OVERVIEW_WIDTH - 240.0, "height": band_height}
        distribution_bounds = {
            "x": band_bounds["x"] + band_bounds["width"] - 560.0,
            "y": band_y + 74.0,
            "width": 430.0,
            "height": max(240.0, band_height - 160.0),
        }
        _add_source_derived_linework(
            objects,
            f"source_driven_{_slug(group_name)}_{index}",
            group_name,
            group_pages,
            band_bounds,
            distribution_bounds,
            _page_ids(group_pages),
            limit_per_page=22,
            opacity=0.16,
        )
        source_graph = build_source_graph(group_pages, candidates, source_paths, group_name)
        _add_source_driven_full_coverage(
            objects,
            f"source_driven_{_slug(group_name)}_{index}",
            source_graph,
            group_pages,
            band_bounds,
            styles,
        )
        _add_source_driven_group_summary(objects, f"source_driven_{_slug(group_name)}_{index}", source_graph, band_y, band_height)
    _add_reference_title_block(objects, pages, source_paths)
    return objects


def _source_driven_stitched_page_objects(
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
    styles: dict[str, DrawingStyle],
    groups: list[tuple[str, list[PageEvidence]]],
    system_color_map: SystemColorMap,
) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    sorted_pages = _sorted_pages(pages)
    page_by_source = {page.sourceFileId: page for page in sorted_pages}
    candidate_by_id = {candidate.id: candidate for candidate in candidates}
    source_bounds_by_source = {page.sourceFileId: _stitched_page_display_content_bounds(page) for page in sorted_pages}
    tile_by_source = _stitched_source_tiles(sorted_pages, matches, candidate_by_id, source_bounds_by_source)
    suppressed_bounds_by_source = _matched_continuation_display_bounds_by_source(sorted_pages, matches, candidate_by_id)
    page_source_ids = [page.id for page in sorted_pages]

    objects.append(
        _overview_label(
            "source_stitched_title",
            "SOURCE-STITCHED P&ID",
            {"x": 120.0, "y": 58.0, "width": 520.0, "height": 22.0},
            "#0f172a",
            15.5,
            page_source_ids,
        )
    )
    objects.append(
        _overview_label(
            "source_stitched_subtitle",
            f"{len(sorted_pages)} source sheet{'s' if len(sorted_pages) != 1 else ''} stitched by matched continuations",
            {"x": 122.0, "y": 84.0, "width": 520.0, "height": 14.0},
            "#475569",
            8.0,
            page_source_ids,
        )
    )
    for index, (group_name, group_pages) in enumerate(groups[:8]):
        label = _overview_label(
            f"source_stitched_group_label_{group_name}",
            f"{group_name} SYSTEM",
            {"x": 132.0 + index * 238.0, "y": 126.0, "width": 210.0, "height": 18.0},
            GROUP_COLORS.get(group_name, "#334155"),
            9.0,
            _page_ids(group_pages),
        )
        label.metadata.update({"stitchedSourceGroupLabel": True, "groupName": group_name})
        objects.append(label)
    objects.extend(_source_driven_legend(system_color_map))

    for index, page in enumerate(sorted_pages):
        tile = tile_by_source[page.sourceFileId]
        _append_single_page_reconstruction(
            objects,
            page,
            tile,
            f"source_stitched_{index}_{page.sourceFileId}",
            {
                "stitchedSourcePage": True,
                "sourceDisplayName": _source_display_name(page, source_paths),
            },
            source_bounds=source_bounds_by_source[page.sourceFileId],
            clean_for_combined=True,
            suppressed_display_bounds=suppressed_bounds_by_source.get(page.sourceFileId, []),
            draw_frame=False,
            system_color_map=system_color_map,
        )
        label = _overview_label(
            f"source_stitched_page_label_{page.id}",
            _source_display_name(page, source_paths),
            {"x": tile["x"], "y": tile["y"] - 28.0, "width": min(tile["width"], 760.0), "height": 18.0},
            "#334155",
            10.0,
            [page.id],
        )
        label.metadata.update({"stitchedSourcePageLabel": True, "sourcePageId": page.id, "sourceFileId": page.sourceFileId})
        objects.append(label)

    _add_stitched_continuation_connectors(
        objects,
        matches,
        candidate_by_id,
        page_by_source,
        tile_by_source,
        source_bounds_by_source,
        source_paths,
        styles,
        system_color_map,
    )
    for group_name, group_pages in _overview_groups(sorted_pages, source_paths):
        source_graph = build_source_graph(group_pages, candidates, source_paths, group_name)
        coverage_band = _stitched_group_coverage_band(group_pages, tile_by_source)
        _add_source_driven_full_coverage(objects, f"source_stitched_{_slug(group_name)}", source_graph, group_pages, coverage_band, styles)
    return objects


def _stitched_source_tiles(
    pages: list[PageEvidence],
    matches: list[ContinuationMatch],
    candidate_by_id: dict[str, ContinuationCandidate],
    source_bounds_by_source: dict[str, BoundsDict],
) -> dict[str, BoundsDict]:
    positions = _stitched_page_grid_positions(pages, matches, candidate_by_id)
    margin_x = 120.0
    margin_y = 178.0
    tiles: dict[str, BoundsDict] = {}
    for page in pages:
        source_bounds = source_bounds_by_source[page.sourceFileId]
        scale = min(_STITCHED_TILE_MAX_WIDTH / max(1.0, source_bounds["width"]), _STITCHED_TILE_MAX_HEIGHT / max(1.0, source_bounds["height"]))
        width = source_bounds["width"] * scale
        height = source_bounds["height"] * scale
        tiles[page.sourceFileId] = {
            "x": 0.0,
            "y": 0.0,
            "width": width,
            "height": height,
        }
    _place_stitched_tiles_on_compact_tracks(tiles, positions, margin_x, margin_y)
    if len(pages) <= 6:
        for _ in range(3):
            _align_stitched_tiles_to_matched_ports(tiles, pages, matches, candidate_by_id, source_bounds_by_source)
    _compact_stitched_tile_gaps(tiles, "x", _STITCHED_TILE_GAP_X * 1.65)
    _compact_stitched_tile_gaps(tiles, "y", _STITCHED_TILE_GAP_Y * 1.55)
    _normalize_stitched_tiles(tiles, margin_x, margin_y)
    return tiles


def _place_stitched_tiles_on_compact_tracks(
    tiles: dict[str, BoundsDict],
    positions: dict[str, tuple[int, int]],
    margin_x: float,
    margin_y: float,
) -> None:
    if not tiles:
        return
    columns = sorted({col for col, _row in positions.values()})
    rows = sorted({row for _col, row in positions.values()})
    column_widths = {
        col: max((tiles[source_id]["width"] for source_id, position in positions.items() if position[0] == col and source_id in tiles), default=0.0)
        for col in columns
    }
    row_heights = {
        row: max((tiles[source_id]["height"] for source_id, position in positions.items() if position[1] == row and source_id in tiles), default=0.0)
        for row in rows
    }
    column_x: dict[int, float] = {}
    current_x = margin_x
    for col in columns:
        column_x[col] = current_x
        current_x += column_widths[col] + _STITCHED_TILE_GAP_X
    row_y: dict[int, float] = {}
    current_y = margin_y
    for row in rows:
        row_y[row] = current_y
        current_y += row_heights[row] + _STITCHED_TILE_GAP_Y

    for source_id, tile in tiles.items():
        col, row = positions[source_id]
        track_width = column_widths[col]
        track_height = row_heights[row]
        tile["x"] = column_x[col] + (track_width - tile["width"]) / 2.0
        tile["y"] = row_y[row] + (track_height - tile["height"]) / 2.0


def _align_stitched_tiles_to_matched_ports(
    tiles: dict[str, BoundsDict],
    pages: list[PageEvidence],
    matches: list[ContinuationMatch],
    candidate_by_id: dict[str, ContinuationCandidate],
    source_bounds_by_source: dict[str, BoundsDict],
) -> None:
    if not tiles or not pages:
        return
    page_by_source = {page.sourceFileId: page for page in pages}
    pinned_source_id = pages[0].sourceFileId
    ordered_matches = sorted(matches, key=lambda item: (-item.score, item.id))
    for _iteration in range(min(4, max(1, len(pages)))):
        offsets: dict[str, dict[str, list[float]]] = {source_id: {"x": [], "y": []} for source_id in tiles}

        for match in ordered_matches:
            if match.status == "rejected":
                continue
            source_candidate = candidate_by_id.get(match.sourceCandidateId)
            target_candidate = candidate_by_id.get(match.targetCandidateId)
            if not source_candidate or not target_candidate:
                continue
            if source_candidate.sourceFileId == target_candidate.sourceFileId:
                continue
            source_page = page_by_source.get(source_candidate.sourceFileId)
            target_page = page_by_source.get(target_candidate.sourceFileId)
            source_tile = tiles.get(source_candidate.sourceFileId)
            target_tile = tiles.get(target_candidate.sourceFileId)
            if not source_page or not target_page or not source_tile or not target_tile:
                continue
            source_bounds = source_bounds_by_source.get(source_candidate.sourceFileId, {"x": 0.0, "y": 0.0, "width": source_page.width, "height": source_page.height})
            target_bounds = source_bounds_by_source.get(target_candidate.sourceFileId, {"x": 0.0, "y": 0.0, "width": target_page.width, "height": target_page.height})
            source_anchor = _map_single_sheet_point(source_candidate.position, source_page, source_bounds, source_tile)
            target_anchor = _map_single_sheet_point(target_candidate.position, target_page, target_bounds, target_tile)

            move_id = target_candidate.sourceFileId
            reference_anchor = source_anchor
            movable_anchor = target_anchor
            source_edges_pinned = source_candidate.sourceFileId == pinned_source_id
            target_edges_pinned = target_candidate.sourceFileId == pinned_source_id
            if target_edges_pinned and not source_edges_pinned:
                move_id = source_candidate.sourceFileId
                reference_anchor = target_anchor
                movable_anchor = source_anchor
            if move_id == pinned_source_id:
                continue

            delta = _stitched_match_delta(source_candidate, target_candidate)
            if _stitched_match_is_horizontal(source_candidate, target_candidate):
                offsets[move_id]["y"].append(reference_anchor["y"] - movable_anchor["y"])
                horizontal_sign = delta[0] or (1 if target_anchor["x"] >= source_anchor["x"] else -1)
                if move_id == target_candidate.sourceFileId:
                    offsets[move_id]["x"].append(source_anchor["x"] + horizontal_sign * _STITCHED_CONTINUATION_GAP - target_anchor["x"])
                else:
                    offsets[move_id]["x"].append(target_anchor["x"] - horizontal_sign * _STITCHED_CONTINUATION_GAP - source_anchor["x"])
            else:
                offsets[move_id]["x"].append(reference_anchor["x"] - movable_anchor["x"])
                vertical_sign = delta[1] or (1 if target_anchor["y"] >= source_anchor["y"] else -1)
                if move_id == target_candidate.sourceFileId:
                    offsets[move_id]["y"].append(source_anchor["y"] + vertical_sign * _STITCHED_CONTINUATION_GAP - target_anchor["y"])
                else:
                    offsets[move_id]["y"].append(target_anchor["y"] - vertical_sign * _STITCHED_CONTINUATION_GAP - source_anchor["y"])

        max_offset = 0.0
        for source_id, axis_offsets in offsets.items():
            if source_id == pinned_source_id:
                continue
            dx_values = axis_offsets["x"]
            dy_values = axis_offsets["y"]
            if dx_values:
                dx = sum(dx_values) / len(dx_values)
                tiles[source_id]["x"] += dx
                max_offset = max(max_offset, abs(dx))
            if dy_values:
                dy = sum(dy_values) / len(dy_values)
                tiles[source_id]["y"] += dy
                max_offset = max(max_offset, abs(dy))
        if max_offset < 0.5:
            break


def _stitched_match_is_horizontal(source_candidate: ContinuationCandidate, target_candidate: ContinuationCandidate) -> bool:
    return source_candidate.edge in {"left", "right"} or target_candidate.edge in {"left", "right"}


def _normalize_stitched_tiles(tiles: dict[str, BoundsDict], margin_x: float, margin_y: float) -> None:
    if not tiles:
        return
    min_x = min(tile["x"] for tile in tiles.values())
    min_y = min(tile["y"] for tile in tiles.values())
    dx = margin_x - min_x
    dy = margin_y - min_y
    if dx == 0.0 and dy == 0.0:
        return
    for tile in tiles.values():
        tile["x"] += dx
        tile["y"] += dy


def _compact_stitched_tile_gaps(tiles: dict[str, BoundsDict], axis: Literal["x", "y"], max_gap: float) -> None:
    if len(tiles) < 2:
        return
    size_key = "width" if axis == "x" else "height"
    ordered = sorted(tiles.values(), key=lambda tile: (tile[axis], tile[axis] + tile[size_key]))
    previous_end = ordered[0][axis] + ordered[0][size_key]
    total_shift = 0.0
    for tile in ordered[1:]:
        original_start = tile[axis]
        shifted_start = original_start - total_shift
        gap = shifted_start - previous_end
        if gap > max_gap:
            total_shift += gap - max_gap
            shifted_start = original_start - total_shift
        if total_shift:
            tile[axis] = shifted_start
        previous_end = max(previous_end, tile[axis] + tile[size_key])


def _matched_continuation_display_bounds_by_source(
    pages: list[PageEvidence],
    matches: list[ContinuationMatch],
    candidate_by_id: dict[str, ContinuationCandidate],
) -> dict[str, list[BoundsDict]]:
    page_by_source = {page.sourceFileId: page for page in pages}
    bounds_by_source: dict[str, list[BoundsDict]] = {}
    for match in matches:
        if match.status == "rejected":
            continue
        for candidate_id in (match.sourceCandidateId, match.targetCandidateId):
            candidate = candidate_by_id.get(candidate_id)
            if not candidate:
                continue
            page = page_by_source.get(candidate.sourceFileId)
            if not page:
                continue
            display_bounds = _candidate_display_bounds(candidate, page)
            bounds_by_source.setdefault(candidate.sourceFileId, []).append(_expand_display_bounds(display_bounds, 42.0, 28.0, page))
    return bounds_by_source


def _candidate_display_bounds(candidate: ContinuationCandidate, page: PageEvidence) -> BoundsDict:
    bounds = candidate.bounds
    corners = [
        _rotate_source_point_for_page({"x": bounds["x"], "y": bounds["y"]}, page),
        _rotate_source_point_for_page({"x": bounds["x"] + bounds["width"], "y": bounds["y"]}, page),
        _rotate_source_point_for_page({"x": bounds["x"], "y": bounds["y"] + bounds["height"]}, page),
        _rotate_source_point_for_page({"x": bounds["x"] + bounds["width"], "y": bounds["y"] + bounds["height"]}, page),
    ]
    return _points_bounds(corners)


def _expand_display_bounds(bounds: BoundsDict, pad_x: float, pad_y: float, page: PageEvidence) -> BoundsDict:
    x0 = max(0.0, bounds["x"] - pad_x)
    y0 = max(0.0, bounds["y"] - pad_y)
    x1 = min(page.width, bounds["x"] + bounds["width"] + pad_x)
    y1 = min(page.height, bounds["y"] + bounds["height"] + pad_y)
    return {"x": x0, "y": y0, "width": max(0.0, x1 - x0), "height": max(0.0, y1 - y0)}


def _is_suppressed_continuation_marker(display_bounds: BoundsDict, suppressed_bounds: list[BoundsDict]) -> bool:
    if not _display_bounds_intersects_any(display_bounds, suppressed_bounds):
        return False
    # Keep the real process line running into the port. Only remove the small
    # off-sheet pointer glyphs and local marker strokes around matched ports.
    return display_bounds["width"] <= 340.0 and display_bounds["height"] <= 170.0


def _display_bounds_intersects_any(bounds: BoundsDict, candidates: list[BoundsDict]) -> bool:
    return any(_display_bounds_intersect(bounds, candidate) for candidate in candidates)


def _stitched_page_grid_positions(
    pages: list[PageEvidence],
    matches: list[ContinuationMatch],
    candidate_by_id: dict[str, ContinuationCandidate],
) -> dict[str, tuple[int, int]]:
    source_ids = [page.sourceFileId for page in pages]
    positions: dict[str, tuple[int, int]] = {}
    if source_ids:
        positions[source_ids[0]] = (0, 0)

    for match in sorted(matches, key=lambda item: (-item.score, item.id)):
        if match.status == "rejected":
            continue
        source_candidate = candidate_by_id.get(match.sourceCandidateId)
        target_candidate = candidate_by_id.get(match.targetCandidateId)
        if not source_candidate or not target_candidate:
            continue
        source_id = source_candidate.sourceFileId
        target_id = target_candidate.sourceFileId
        if source_id == target_id:
            continue
        delta = _stitched_match_delta(source_candidate, target_candidate)
        if source_id in positions and target_id not in positions:
            sx, sy = positions[source_id]
            positions[target_id] = (sx + delta[0], sy + delta[1])
        elif target_id in positions and source_id not in positions:
            tx, ty = positions[target_id]
            positions[source_id] = (tx - delta[0], ty - delta[1])

    next_col = 0
    next_row = max([row for _col, row in positions.values()], default=0) + 1
    for source_id in source_ids:
        if source_id in positions:
            continue
        positions[source_id] = (next_col, next_row)
        next_col += 1
        if next_col >= 3:
            next_col = 0
            next_row += 1
    return _pack_grid_positions(positions)


def _stitched_match_delta(source_candidate: ContinuationCandidate, target_candidate: ContinuationCandidate) -> tuple[int, int]:
    if source_candidate.edge == "right" or target_candidate.edge == "left":
        return (1, 0)
    if source_candidate.edge == "left" or target_candidate.edge == "right":
        return (-1, 0)
    if source_candidate.edge == "bottom" or target_candidate.edge == "top":
        return (0, 1)
    if source_candidate.edge == "top" or target_candidate.edge == "bottom":
        return (0, -1)
    return (1, 0)


def _pack_grid_positions(positions: dict[str, tuple[int, int]]) -> dict[str, tuple[int, int]]:
    used: set[tuple[int, int]] = set()
    packed: dict[str, tuple[int, int]] = {}
    min_col = min([col for col, _row in positions.values()], default=0)
    min_row = min([row for _col, row in positions.values()], default=0)
    for source_id, (col, row) in sorted(positions.items(), key=lambda item: (item[1][1], item[1][0], item[0])):
        candidate = (col - min_col, row - min_row)
        while candidate in used:
            candidate = (candidate[0] + 1, candidate[1])
        used.add(candidate)
        packed[source_id] = candidate
    return packed


def _append_single_page_reconstruction(
    objects: list[DrawingObject],
    page: PageEvidence,
    tile: BoundsDict,
    id_seed: str,
    metadata: dict[str, Any] | None = None,
    source_bounds: BoundsDict | None = None,
    clean_for_combined: bool = False,
    suppressed_display_bounds: list[BoundsDict] | None = None,
    draw_frame: bool = True,
    system_color_map: SystemColorMap | None = None,
) -> None:
    source_ids = [page.id]
    source_bounds = source_bounds or {"x": 0.0, "y": 0.0, "width": page.width, "height": page.height}
    suppressed_display_bounds = suppressed_display_bounds or []
    source_system_text = _source_system_text_bounds(page, system_color_map)
    source_vectors: list[tuple[int, VectorSegment, BoundsDict]] = []
    for index, vector in enumerate(_single_sheet_vectors(page)):
        display_bounds = _vector_display_bounds(vector, page)
        if clean_for_combined and not _display_bounds_intersect(display_bounds, source_bounds):
            continue
        if clean_for_combined and _display_bounds_is_sheet_noise(display_bounds, page):
            continue
        if clean_for_combined and _is_source_region_border_vector(display_bounds, page, source_bounds):
            continue
        if clean_for_combined and _is_suppressed_continuation_marker(display_bounds, suppressed_display_bounds):
            continue
        source_vectors.append((index, vector, display_bounds))
    vector_systems = (
        _source_vector_systems([vector for _index, vector, _bounds in source_vectors], page, system_color_map, source_system_text)
        if clean_for_combined
        else {}
    )
    if draw_frame:
        frame = _overview_region(
            f"{id_seed}_page_frame",
            "",
            tile,
            "#94a3b8",
            "#ffffff",
            0.18,
            source_ids,
            {
                "singleSheetPageFrame": True,
                "stitchedSourcePageTile": True,
                "sourcePageId": page.id,
                "sourceFileId": page.sourceFileId,
                "hideCenterLabel": True,
                **(metadata or {}),
            },
        )
        objects.append(frame)
    for index, vector, _display_bounds in source_vectors:
        points = [_map_single_sheet_point(point, page, source_bounds, tile) for point in vector.points]
        if len(points) < 2:
            continue
        vector_system = vector_systems.get(vector.id) or _source_vector_system(vector, page, system_color_map, source_system_text)
        objects.append(
            DrawingObject(
                id=_object_id("stitched_page_vector", id_seed, page.id, vector.id, index),
                kind="pipe",
                label="",
                points=points,
                bounds=_points_bounds(points, 2.0),
                style=DrawingStyle(
                    stroke=system_color_map.color_for(vector_system) if system_color_map and vector_system != "DEFAULT" else _single_sheet_vector_stroke(vector),
                    fill="none",
                    strokeWidth=_source_vector_stroke_width(vector, vector_system),
                    opacity=_source_vector_opacity(vector, vector_system),
                    dash=_source_vector_dash(vector),
                ),
                sourceEvidenceIds=[page.id, vector.id] if vector.id else source_ids,
                locked=False,
                metadata={
                    "overview": True,
                    "sourceDerived": True,
                    "singleSheetReconstructionVector": True,
                    "sourceVectorId": vector.id,
                    "sourcePageId": page.id,
                    "sourceFileId": page.sourceFileId,
                    "system": vector_system,
                    "systemColorApplied": vector_system != "DEFAULT",
                    "futureLine": vector.dashed,
                    **(metadata or {}),
                },
            )
        )

    for index, span in enumerate(page.textSpans):
        label_text = _stitched_sheet_text(span) if clean_for_combined else (_reconstructable_text(span.text) if _source_text_is_red_markup(span) else _single_sheet_text(span.text))
        if not label_text:
            continue
        display_bounds = _text_span_display_bounds(span, page)
        if clean_for_combined and not _display_bounds_intersect(display_bounds, source_bounds):
            continue
        bounds = _map_single_sheet_bounds(span.x, span.y, span.width, span.height, page, source_bounds, tile)
        font_size = _stitched_sheet_label_font_size(label_text, bounds)
        label = _overview_label(
            f"{id_seed}_text_{index}_{label_text}",
            label_text,
            bounds,
            _single_sheet_text_color(span.color),
            font_size,
            source_ids,
        )
        label.style.opacity = 0.84 if clean_for_combined else 0.74
        label.metadata.update(
            {
                "singleSheetReconstructionText": True,
                "sourceCoverage": True,
                "sourcePageId": page.id,
                "sourceFileId": page.sourceFileId,
                "fontWeight": "400",
                "rotationDegrees": _single_sheet_label_rotation(span.rotation, page.rotation),
                **(metadata or {}),
            }
        )
        objects.append(label)


def _add_stitched_continuation_connectors(
    objects: list[DrawingObject],
    matches: list[ContinuationMatch],
    candidate_by_id: dict[str, ContinuationCandidate],
    page_by_source: dict[str, PageEvidence],
    tile_by_source: dict[str, BoundsDict],
    source_bounds_by_source: dict[str, BoundsDict],
    source_paths: dict[str, str],
    styles: dict[str, DrawingStyle],
    system_color_map: SystemColorMap,
) -> None:
    for match in sorted(matches, key=lambda item: (-item.score, item.id)):
        if match.status == "rejected":
            continue
        source_candidate = candidate_by_id.get(match.sourceCandidateId)
        target_candidate = candidate_by_id.get(match.targetCandidateId)
        if not source_candidate or not target_candidate:
            continue
        source_page = page_by_source.get(source_candidate.sourceFileId)
        target_page = page_by_source.get(target_candidate.sourceFileId)
        source_tile = tile_by_source.get(source_candidate.sourceFileId)
        target_tile = tile_by_source.get(target_candidate.sourceFileId)
        if not source_page or not target_page or not source_tile or not target_tile:
            continue
        source_bounds = source_bounds_by_source.get(source_page.sourceFileId, {"x": 0.0, "y": 0.0, "width": source_page.width, "height": source_page.height})
        target_bounds = source_bounds_by_source.get(target_page.sourceFileId, {"x": 0.0, "y": 0.0, "width": target_page.width, "height": target_page.height})
        start = _map_single_sheet_point(source_candidate.position, source_page, source_bounds, source_tile)
        end = _map_single_sheet_point(target_candidate.position, target_page, target_bounds, target_tile)
        line_tag = source_candidate.lineTag or target_candidate.lineTag
        system = _stitched_connector_dynamic_system(
            source_candidate,
            target_candidate,
            source_page,
            target_page,
            source_paths,
            line_tag,
            system_color_map,
        )
        connector = _overview_pipe(
            f"source_stitched_connector_{match.id}",
            line_tag,
            _stitched_connector_points(start, end, source_candidate, target_candidate),
            system,
            styles,
            [source_candidate.id, target_candidate.id],
            0.95,
        )
        connector.style = _stitched_connector_style(system, styles, system_color_map, 0.82)
        connector.style.opacity = 0.56
        entry = system_color_map.entries.get(system)
        system_color_source = entry.source if entry is not None else "reference" if system in SYSTEM_COLORS else "fallback"
        connector.metadata.update(
            {
                "stitchedContinuationMatchId": match.id,
                "sourceCandidateId": source_candidate.id,
                "targetCandidateId": target_candidate.id,
                "lineTag": line_tag,
                "arrowEnd": False,
                "connectorRole": "matchedOffPageContinuation",
                "system": system,
                "systemAccent": connector.style.stroke,
                "systemColorSource": system_color_source,
                "sourceGenerated": True,
            }
        )
        objects.append(connector)
        mid = _midpoint(start, end)
        label = _overview_label(
            f"source_stitched_connector_label_{match.id}",
            line_tag or f"{source_candidate.sheetRef or ''} {target_candidate.sheetRef or ''}".strip(),
            {"x": mid["x"] - 80.0, "y": mid["y"] - 15.0, "width": 160.0, "height": 12.0},
            "#111827",
            5.6,
            [source_candidate.id, target_candidate.id],
        )
        label.style.opacity = 0.66
        label.metadata.update({"stitchedContinuationMatchId": match.id, "lineTag": line_tag, "fontWeight": "400", "connectorRole": "matchedOffPageContinuationLabel"})
        objects.append(label)


def _stitched_connector_system(
    source_candidate: ContinuationCandidate,
    target_candidate: ContinuationCandidate,
    source_page: PageEvidence,
    target_page: PageEvidence,
    source_paths: dict[str, str],
    line_tag: str,
) -> str:
    explicit = (source_candidate.system or target_candidate.system or "").upper()
    if explicit and explicit != "DEFAULT":
        return explicit
    for page in (source_page, target_page):
        group_name = _page_group(page, source_paths)
        inferred = _system_for_tag(line_tag or source_candidate.label or target_candidate.label, group_name)
        if inferred != "DEFAULT":
            return inferred
        systems = _overview_systems_for_group(group_name, [page])
        if systems and systems[0] != "DEFAULT":
            return systems[0]
    return "DEFAULT"


def _stitched_connector_dynamic_system(
    source_candidate: ContinuationCandidate,
    target_candidate: ContinuationCandidate,
    source_page: PageEvidence,
    target_page: PageEvidence,
    source_paths: dict[str, str],
    line_tag: str,
    system_color_map: SystemColorMap,
) -> str:
    legacy_system = _stitched_connector_system(source_candidate, target_candidate, source_page, target_page, source_paths, line_tag)
    if legacy_system in SYSTEM_COLORS:
        return legacy_system

    dynamic_system = system_for_text(
        " ".join([line_tag or "", source_candidate.system, target_candidate.system, source_candidate.label, target_candidate.label]),
        system_color_map,
    )
    if dynamic_system != "DEFAULT":
        return dynamic_system
    return legacy_system


def _stitched_connector_style(
    system: str,
    styles: dict[str, DrawingStyle],
    system_color_map: SystemColorMap,
    stroke_width: float,
) -> DrawingStyle:
    if system in SYSTEM_COLORS:
        style = replace(styles.get(system, styles["DEFAULT"]))
        style.strokeWidth = stroke_width
        return style
    return style_for_system(system, system_color_map, stroke_width)


def _stitched_connector_points(
    start: Point,
    end: Point,
    source_candidate: ContinuationCandidate,
    target_candidate: ContinuationCandidate,
) -> list[Point]:
    if _stitched_match_is_horizontal(source_candidate, target_candidate) and abs(start["y"] - end["y"]) <= 4.0:
        return [start, end]
    if not _stitched_match_is_horizontal(source_candidate, target_candidate) and abs(start["x"] - end["x"]) <= 4.0:
        return [start, end]
    return _orthogonal_points(start, end)


def _stitched_group_coverage_band(group_pages: list[PageEvidence], tile_by_source: dict[str, BoundsDict]) -> BoundsDict:
    tiles = [tile_by_source[page.sourceFileId] for page in group_pages if page.sourceFileId in tile_by_source]
    if not tiles:
        return {"x": 120.0, "y": 180.0, "width": _OVERVIEW_WIDTH - 240.0, "height": 820.0}
    x0 = min(tile["x"] for tile in tiles)
    y0 = min(tile["y"] for tile in tiles)
    x1 = max(tile["x"] + tile["width"] for tile in tiles)
    y1 = max(tile["y"] + tile["height"] for tile in tiles)
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def _midpoint(start: Point, end: Point) -> Point:
    return {"x": (start["x"] + end["x"]) / 2.0, "y": (start["y"] + end["y"]) / 2.0}


def _stitched_page_display_content_bounds(page: PageEvidence) -> BoundsDict:
    bounds: list[BoundsDict] = []
    for vector in _single_sheet_vectors(page):
        display_bounds = _vector_display_bounds(vector, page)
        if _display_bounds_is_sheet_noise(display_bounds, page):
            continue
        bounds.append(display_bounds)
    for span in page.textSpans:
        useful_text = _stitched_sheet_text(span)
        if not useful_text:
            continue
        display_bounds = _text_span_display_bounds(span, page)
        if _display_bounds_is_sheet_noise(display_bounds, page) and not _reconstructable_text(span.text):
            continue
        bounds.append(display_bounds)
    if not bounds:
        return {"x": 0.0, "y": 0.0, "width": page.width, "height": page.height}
    if len(bounds) >= 32:
        x0, y0, x1, y1 = _trimmed_display_extents(bounds)
    else:
        x0 = min(item["x"] for item in bounds)
        y0 = min(item["y"] for item in bounds)
        x1 = max(item["x"] + item["width"] for item in bounds)
        y1 = max(item["y"] + item["height"] for item in bounds)
    pad_x = max(36.0, (x1 - x0) * 0.035)
    pad_y = max(28.0, (y1 - y0) * 0.035)
    return {
        "x": max(0.0, x0 - pad_x),
        "y": max(0.0, y0 - pad_y),
        "width": min(page.width, x1 + pad_x) - max(0.0, x0 - pad_x),
        "height": min(page.height, y1 + pad_y) - max(0.0, y0 - pad_y),
    }


def _trimmed_display_extents(bounds: list[BoundsDict]) -> tuple[float, float, float, float]:
    starts_x = sorted(item["x"] for item in bounds)
    starts_y = sorted(item["y"] for item in bounds)
    ends_x = sorted(item["x"] + item["width"] for item in bounds)
    ends_y = sorted(item["y"] + item["height"] for item in bounds)
    trim = max(1, int(len(bounds) * 0.005))
    x0 = starts_x[min(trim, len(starts_x) - 1)]
    y0 = starts_y[min(trim, len(starts_y) - 1)]
    x1 = ends_x[max(0, len(ends_x) - trim - 1)]
    y1 = ends_y[max(0, len(ends_y) - trim - 1)]
    if x1 <= x0 or y1 <= y0:
        return starts_x[0], starts_y[0], ends_x[-1], ends_y[-1]
    return x0, y0, x1, y1


def _vector_display_bounds(vector: VectorSegment, page: PageEvidence) -> BoundsDict:
    points = [_rotate_source_point_for_page(point, page) for point in vector.points]
    return _points_bounds(points)


def _text_span_display_bounds(span: TextSpan, page: PageEvidence) -> BoundsDict:
    corners = [
        _rotate_source_point_for_page({"x": span.x, "y": span.y}, page),
        _rotate_source_point_for_page({"x": span.x + span.width, "y": span.y}, page),
        _rotate_source_point_for_page({"x": span.x, "y": span.y + span.height}, page),
        _rotate_source_point_for_page({"x": span.x + span.width, "y": span.y + span.height}, page),
    ]
    return _points_bounds(corners)


def _display_bounds_is_sheet_noise(bounds: BoundsDict, page: PageEvidence) -> bool:
    center_x = bounds["x"] + bounds["width"] / 2.0
    center_y = bounds["y"] + bounds["height"] / 2.0
    if center_y > page.height * 0.80:
        return True
    if center_x > page.width * 0.92 and center_y > page.height * 0.68:
        return True
    if bounds["width"] > page.width * 0.94 or bounds["height"] > page.height * 0.94:
        return True
    return False


def _is_sheet_border_vector(bounds: BoundsDict, page: PageEvidence) -> bool:
    edge_x = max(18.0, page.width * 0.018)
    edge_y = max(18.0, page.height * 0.018)
    thin = max(8.0, min(page.width, page.height) * 0.006)
    long_horizontal = bounds["width"] > page.width * 0.20 and bounds["height"] <= thin
    long_vertical = bounds["height"] > page.height * 0.20 and bounds["width"] <= thin
    near_top = bounds["y"] <= edge_y
    near_bottom = bounds["y"] + bounds["height"] >= page.height - edge_y
    near_left = bounds["x"] <= edge_x
    near_right = bounds["x"] + bounds["width"] >= page.width - edge_x
    return (long_horizontal and (near_top or near_bottom)) or (long_vertical and (near_left or near_right))


def _is_source_region_border_vector(bounds: BoundsDict, page: PageEvidence, source_bounds: BoundsDict) -> bool:
    return _is_sheet_border_vector(bounds, page) or _is_bounds_border_vector(bounds, source_bounds)


def _is_bounds_border_vector(bounds: BoundsDict, frame: BoundsDict) -> bool:
    edge_x = max(14.0, frame["width"] * 0.018)
    edge_y = max(14.0, frame["height"] * 0.018)
    thin = max(6.0, min(frame["width"], frame["height"]) * 0.006)
    long_horizontal = bounds["width"] > frame["width"] * 0.24 and bounds["height"] <= thin
    long_vertical = bounds["height"] > frame["height"] * 0.24 and bounds["width"] <= thin
    near_top = abs(bounds["y"] - frame["y"]) <= edge_y
    near_bottom = abs((bounds["y"] + bounds["height"]) - (frame["y"] + frame["height"])) <= edge_y
    near_left = abs(bounds["x"] - frame["x"]) <= edge_x
    near_right = abs((bounds["x"] + bounds["width"]) - (frame["x"] + frame["width"])) <= edge_x
    return (long_horizontal and (near_top or near_bottom)) or (long_vertical and (near_left or near_right))


def _display_bounds_intersect(bounds: BoundsDict, source_bounds: BoundsDict) -> bool:
    return (
        bounds["x"] < source_bounds["x"] + source_bounds["width"]
        and bounds["x"] + bounds["width"] > source_bounds["x"]
        and bounds["y"] < source_bounds["y"] + source_bounds["height"]
        and bounds["y"] + bounds["height"] > source_bounds["y"]
    )


def _stitched_sheet_text(span: TextSpan) -> str:
    text = re.sub(r"\s+", " ", span.text.strip())
    if not text:
        return ""
    return _reconstructable_text(text)


def _stitched_sheet_label_font_size(label: str, bounds: BoundsDict) -> float:
    if not label:
        return 3.8
    base = max(2.6, min(6.2, bounds["height"] * 0.52))
    if LINE_TAG_TOKEN_RE.fullmatch(label) or EQUIPMENT_TAG_RE.fullmatch(label) or INSTRUMENT_TAG_RE.fullmatch(label):
        return max(2.4, min(base, 4.8))
    if len(label) > 28:
        return max(2.4, min(base, 3.8))
    return base


def _source_system_text_bounds(page: PageEvidence, system_color_map: SystemColorMap | None) -> list[tuple[BoundsDict, str]]:
    if system_color_map is None:
        return []
    eligible: list[tuple[BoundsDict, str]] = []
    process_sheet = any(LINE_TAG_TOKEN_RE.search(span.text or "") for span in page.textSpans)
    for span in page.textSpans:
        system = system_for_text(span.text, system_color_map)
        if system == "DEFAULT" and not LINE_TAG_TOKEN_RE.search(span.text or ""):
            continue
        if process_sheet and not LINE_TAG_TOKEN_RE.search(span.text or "") and _system_is_electrical_annotation(system):
            continue
        eligible.append((_text_span_display_bounds(span, page), system))
    return eligible


def _system_is_electrical_annotation(system: str) -> bool:
    return canonical_system(system) in {"480V", "208V", "120V", "MCC", "UPS", "PDU", "SWGR", "XFMR", "FEEDER", "PANEL", "ELEC"}


def _source_vector_system(
    vector: VectorSegment,
    page: PageEvidence,
    system_color_map: SystemColorMap | None,
    source_system_text: list[tuple[BoundsDict, str]] | None = None,
) -> str:
    if system_color_map is None:
        return "DEFAULT"
    candidates = source_system_text if source_system_text is not None else _source_system_text_bounds(page, system_color_map)
    vector_points = [_rotate_source_point_for_page(point, page) for point in vector.points]
    if len(vector_points) < 2:
        return "DEFAULT"

    closest_system = "DEFAULT"
    closest_distance = float("inf")
    for text_bounds, system in candidates:
        if system == "DEFAULT":
            continue
        distance = _bounds_to_polyline_distance(text_bounds, vector_points)
        if distance < closest_distance:
            closest_distance = distance
            closest_system = system

    if closest_distance <= _SOURCE_VECTOR_SYSTEM_MAX_DISTANCE:
        return closest_system
    return "DEFAULT"


def _source_vector_systems(
    vectors: list[VectorSegment],
    page: PageEvidence,
    system_color_map: SystemColorMap | None,
    source_system_text: list[tuple[BoundsDict, str]],
) -> dict[str, str]:
    if system_color_map is None:
        return {}
    direct: dict[str, str] = {
        vector.id: _source_vector_system(vector, page, system_color_map, source_system_text)
        for vector in vectors
    }
    adjacency = _source_vector_adjacency(vectors, page)
    systems: dict[str, str] = {}
    visited: set[str] = set()

    for vector in vectors:
        if vector.id in visited:
            continue
        stack = [vector.id]
        component: list[str] = []
        visited.add(vector.id)
        while stack:
            current = stack.pop()
            component.append(current)
            for neighbor in adjacency.get(current, []):
                if neighbor in visited:
                    continue
                visited.add(neighbor)
                stack.append(neighbor)

        votes: dict[str, int] = {}
        for vector_id in component:
            system = direct.get(vector_id, "DEFAULT")
            if system == "DEFAULT":
                continue
            votes[system] = votes.get(system, 0) + 1
        if not votes:
            continue
        winner, winner_count = max(votes.items(), key=lambda item: (item[1], item[0]))
        total_votes = sum(votes.values())
        if winner_count / max(1, total_votes) < 0.58:
            continue
        for vector_id in component:
            systems[vector_id] = winner

    return systems


def _source_vector_adjacency(vectors: list[VectorSegment], page: PageEvidence) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = {vector.id: set() for vector in vectors}
    points_by_id: dict[str, list[Point]] = {}
    endpoint_buckets: dict[tuple[int, int], list[str]] = {}
    segment_buckets: dict[tuple[int, int], list[tuple[str, Point, Point]]] = {}
    for vector in vectors:
        points = [_rotate_source_point_for_page(point, page) for point in vector.points]
        if len(points) < 2:
            continue
        points_by_id[vector.id] = points
        for point in (points[0], points[-1]):
            bucket = _source_vector_point_bucket(point)
            endpoint_buckets.setdefault(bucket, []).append(vector.id)
        for start, end in zip(points, points[1:]):
            for bucket in _source_vector_segment_buckets(start, end):
                segment_buckets.setdefault(bucket, []).append((vector.id, start, end))

    for bucket, ids in endpoint_buckets.items():
        neighbor_ids = set(ids)
        bx, by = bucket
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                neighbor_ids.update(endpoint_buckets.get((bx + dx, by + dy), []))
        for vector_id in ids:
            adjacency[vector_id].update(neighbor for neighbor in neighbor_ids if neighbor != vector_id)

    tolerance = _SOURCE_VECTOR_CONNECT_TOLERANCE
    for vector_id, points in points_by_id.items():
        for endpoint in (points[0], points[-1]):
            bx, by = _source_vector_point_bucket(endpoint)
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    for neighbor_id, start, end in segment_buckets.get((bx + dx, by + dy), []):
                        if neighbor_id == vector_id:
                            continue
                        if _point_to_segment_distance(endpoint, start, end) <= tolerance:
                            adjacency[vector_id].add(neighbor_id)
                            adjacency[neighbor_id].add(vector_id)
    return adjacency


def _source_vector_point_bucket(point: Point) -> tuple[int, int]:
    tolerance = _SOURCE_VECTOR_CONNECT_TOLERANCE
    return (round(point["x"] / tolerance), round(point["y"] / tolerance))


def _source_vector_segment_buckets(start: Point, end: Point) -> list[tuple[int, int]]:
    tolerance = _SOURCE_VECTOR_CONNECT_TOLERANCE
    x0 = min(start["x"], end["x"]) - tolerance
    x1 = max(start["x"], end["x"]) + tolerance
    y0 = min(start["y"], end["y"]) - tolerance
    y1 = max(start["y"], end["y"]) + tolerance
    min_bucket_x = int(x0 // tolerance)
    max_bucket_x = int(x1 // tolerance)
    min_bucket_y = int(y0 // tolerance)
    max_bucket_y = int(y1 // tolerance)
    return [
        (bucket_x, bucket_y)
        for bucket_x in range(min_bucket_x, max_bucket_x + 1)
        for bucket_y in range(min_bucket_y, max_bucket_y + 1)
    ]


def _source_vector_stroke_width(vector: VectorSegment, system: str) -> float:
    base = vector.strokeWidth or 0.7
    if system != "DEFAULT":
        return max(0.62, min(0.98, base * 0.86))
    return max(0.24, min(0.65, base * 0.55))


def _source_vector_opacity(vector: VectorSegment, system: str) -> float:
    if vector.dashed:
        return 0.68 if system != "DEFAULT" else 0.48
    return 0.96 if system != "DEFAULT" else 0.68


def _source_vector_dash(vector: VectorSegment) -> list[float] | None:
    return [9.0, 5.0] if vector.dashed else None


def _bounds_to_polyline_distance(bounds: BoundsDict, points: list[Point]) -> float:
    corners = _bounds_corners(bounds)
    distances: list[float] = []
    for start, end in zip(points, points[1:]):
        if _point_in_bounds(start, bounds) or _point_in_bounds(end, bounds) or _segment_intersects_bounds(start, end, bounds):
            return 0.0
        distances.extend(_point_to_segment_distance(corner, start, end) for corner in corners)
        distances.append(_point_to_bounds_distance(start, bounds))
        distances.append(_point_to_bounds_distance(end, bounds))
    return min(distances, default=float("inf"))


def _bounds_corners(bounds: BoundsDict) -> list[Point]:
    x0 = bounds["x"]
    y0 = bounds["y"]
    x1 = bounds["x"] + bounds["width"]
    y1 = bounds["y"] + bounds["height"]
    return [
        {"x": x0, "y": y0},
        {"x": x1, "y": y0},
        {"x": x1, "y": y1},
        {"x": x0, "y": y1},
    ]


def _point_in_bounds(point: Point, bounds: BoundsDict) -> bool:
    return (
        bounds["x"] <= point["x"] <= bounds["x"] + bounds["width"]
        and bounds["y"] <= point["y"] <= bounds["y"] + bounds["height"]
    )


def _segment_intersects_bounds(start: Point, end: Point, bounds: BoundsDict) -> bool:
    corners = _bounds_corners(bounds)
    edges = list(zip(corners, corners[1:] + corners[:1]))
    return any(_segments_intersect(start, end, edge_start, edge_end) for edge_start, edge_end in edges)


def _segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    o1 = _segment_orientation(a, b, c)
    o2 = _segment_orientation(a, b, d)
    o3 = _segment_orientation(c, d, a)
    o4 = _segment_orientation(c, d, b)
    if o1 == 0 and _point_on_segment(c, a, b):
        return True
    if o2 == 0 and _point_on_segment(d, a, b):
        return True
    if o3 == 0 and _point_on_segment(a, c, d):
        return True
    if o4 == 0 and _point_on_segment(b, c, d):
        return True
    return o1 != o2 and o3 != o4


def _segment_orientation(a: Point, b: Point, c: Point) -> int:
    value = (b["y"] - a["y"]) * (c["x"] - b["x"]) - (b["x"] - a["x"]) * (c["y"] - b["y"])
    if abs(value) < 1e-9:
        return 0
    return 1 if value > 0 else 2


def _point_on_segment(point: Point, start: Point, end: Point) -> bool:
    return (
        min(start["x"], end["x"]) <= point["x"] <= max(start["x"], end["x"])
        and min(start["y"], end["y"]) <= point["y"] <= max(start["y"], end["y"])
    )


def _point_to_segment_distance(point: Point, start: Point, end: Point) -> float:
    dx = end["x"] - start["x"]
    dy = end["y"] - start["y"]
    length_squared = dx * dx + dy * dy
    if length_squared == 0:
        return _point_distance(point, start)
    t = ((point["x"] - start["x"]) * dx + (point["y"] - start["y"]) * dy) / length_squared
    t = max(0.0, min(1.0, t))
    projection = {"x": start["x"] + t * dx, "y": start["y"] + t * dy}
    return _point_distance(point, projection)


def _point_distance(a: Point, b: Point) -> float:
    dx = a["x"] - b["x"]
    dy = a["y"] - b["y"]
    return (dx * dx + dy * dy) ** 0.5


def _point_to_bounds_distance(point: Point, bounds: BoundsDict) -> float:
    x0 = bounds["x"]
    y0 = bounds["y"]
    x1 = bounds["x"] + bounds["width"]
    y1 = bounds["y"] + bounds["height"]
    dx = max(x0 - point["x"], 0.0, point["x"] - x1)
    dy = max(y0 - point["y"], 0.0, point["y"] - y1)
    return (dx * dx + dy * dy) ** 0.5


def _source_driven_single_sheet_objects(page: PageEvidence) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    source_ids = [page.id]
    tile = _single_sheet_canvas_tile(page)
    source_bounds = {"x": 0.0, "y": 0.0, "width": page.width, "height": page.height}
    objects.append(_overview_region("single_sheet_page_frame", "", tile, "#94a3b8", "#ffffff", 0.18, source_ids, {"singleSheetPageFrame": True, "hideCenterLabel": True}))

    for index, vector in enumerate(_single_sheet_vectors(page)):
        points = [_map_single_sheet_point(point, page, source_bounds, tile) for point in vector.points]
        if len(points) < 2:
            continue
        objects.append(
            DrawingObject(
                id=_object_id("single_sheet_reconstruction_vector", page.id, vector.id, index),
                kind="pipe",
                label="",
                points=points,
                bounds=_points_bounds(points, 2.0),
                style=DrawingStyle(
                    stroke=_single_sheet_vector_stroke(vector),
                    fill="none",
                    strokeWidth=max(0.35, min(1.25, vector.strokeWidth or 0.7)),
                    opacity=0.64,
                    dash=[4.0, 3.0] if vector.dashed else None,
                ),
                sourceEvidenceIds=[page.id, vector.id] if vector.id else source_ids,
                locked=False,
                metadata={
                    "overview": True,
                    "sourceDerived": True,
                    "singleSheetReconstructionVector": True,
                    "sourceVectorId": vector.id,
                    "sourcePageId": page.id,
                },
            )
        )

    for index, span in enumerate(page.textSpans):
        label_text = _reconstructable_text(span.text) if _source_text_is_red_markup(span) else _single_sheet_text(span.text)
        if not label_text:
            continue
        bounds = _map_single_sheet_bounds(span.x, span.y, span.width, span.height, page, source_bounds, tile)
        label = _overview_label(
            f"single_sheet_text_{page.id}_{index}_{label_text}",
            label_text,
            bounds,
            _single_sheet_text_color(span.color),
            max(3.8, min(9.5, bounds["height"] * 0.76)),
            source_ids,
        )
        label.style.opacity = 0.74
        label.metadata.update(
            {
                "singleSheetReconstructionText": True,
                "sourceCoverage": True,
                "sourcePageId": page.id,
                "fontWeight": "400",
                "rotationDegrees": _single_sheet_label_rotation(span.rotation, page.rotation),
            }
        )
        objects.append(label)

    return objects


def _single_sheet_canvas_tile(page: PageEvidence) -> BoundsDict:
    margin_x = 84.0
    margin_y = 84.0
    usable_width = _OVERVIEW_WIDTH - margin_x * 2.0
    usable_height = _OVERVIEW_HEIGHT - margin_y * 2.0
    scale = min(usable_width / max(1.0, page.width), usable_height / max(1.0, page.height))
    width = page.width * scale
    height = page.height * scale
    return {
        "x": (_OVERVIEW_WIDTH - width) / 2.0,
        "y": (_OVERVIEW_HEIGHT - height) / 2.0,
        "width": width,
        "height": height,
    }


def _map_single_sheet_point(point: Point, page: PageEvidence, source_bounds: BoundsDict, tile: BoundsDict) -> Point:
    display_point = _rotate_source_point_for_page(point, page)
    return _map_source_point(display_point, source_bounds, tile)


def _map_single_sheet_bounds(x: float, y: float, width: float, height: float, page: PageEvidence, source_bounds: BoundsDict, tile: BoundsDict) -> BoundsDict:
    corners = [
        _rotate_source_point_for_page({"x": x, "y": y}, page),
        _rotate_source_point_for_page({"x": x + width, "y": y}, page),
        _rotate_source_point_for_page({"x": x, "y": y + height}, page),
        _rotate_source_point_for_page({"x": x + width, "y": y + height}, page),
    ]
    x0 = min(point["x"] for point in corners)
    y0 = min(point["y"] for point in corners)
    x1 = max(point["x"] for point in corners)
    y1 = max(point["y"] for point in corners)
    return _map_source_bounds(x0, y0, x1 - x0, y1 - y0, source_bounds, tile)


def _rotate_source_point_for_page(point: Point, page: PageEvidence) -> Point:
    crop = page.cropBounds
    x = point["x"] - crop["x"]
    y = point["y"] - crop["y"]
    rotation = page.rotation % 360
    if rotation == 90:
        return {"x": crop["height"] - y, "y": x}
    if rotation == 180:
        return {"x": crop["width"] - x, "y": crop["height"] - y}
    if rotation == 270:
        return {"x": y, "y": crop["width"] - x}
    return {"x": x, "y": y}


def _single_sheet_vectors(page: PageEvidence) -> list[VectorSegment]:
    vectors: list[VectorSegment] = []
    for vector in page.vectorSegments:
        if _single_sheet_vector_is_usable(vector, page.cropBounds):
            vectors.append(vector)
    return sorted(vectors, key=lambda vector: (vector.bounds["y"], vector.bounds["x"], vector.id))


def _single_sheet_vector_is_usable(vector: VectorSegment, crop: BoundsDict) -> bool:
    if vector.kind not in {"line", "polyline", "rect", "curve"}:
        return False
    if len(vector.points) < 2 or len(vector.points) > 30:
        return False
    if _source_vector_is_red_markup(vector):
        return False
    bounds = vector.bounds
    if bounds["width"] <= 0.5 and bounds["height"] <= 0.5:
        return False
    length = _polyline_length(vector.points)
    if length < max(3.0, min(crop["width"], crop["height"]) * 0.0015):
        return False
    return True


def _source_vector_is_red_markup(vector: VectorSegment) -> bool:
    stroke = (vector.stroke or "").lower()
    return stroke in {"#ef4444", "#dc2626", "#b91c1c", "#ff0000", "red"}


def _source_text_is_red_markup(span: TextSpan) -> bool:
    color = (span.color or "").lower()
    return color in {"#ef4444", "#dc2626", "#b91c1c", "#ff0000", "red"}


def _single_sheet_vector_stroke(vector: VectorSegment) -> str:
    stroke = (vector.stroke or "").lower()
    if stroke.startswith("#") and stroke not in {"#ffffff", "#fefefe", "#fff"}:
        return stroke
    return "#111827"


def _single_sheet_text(text: str) -> str:
    if _is_admin_text(text):
        return _reconstructable_text(text)
    cleaned = re.sub(r"\s+", " ", text.strip())
    if not cleaned:
        return ""
    if len(cleaned) > 180:
        return cleaned[:177] + "..."
    return cleaned


def _single_sheet_text_color(color: str | None) -> str:
    if color and color.startswith("#") and color.lower() not in {"#ffffff", "#fefefe", "#fff"}:
        if color.lower() in {"#ef4444", "#dc2626", "#b91c1c", "#ff0000"}:
            return "#991b1b"
        return color
    return "#111827"


def _single_sheet_label_rotation(span_rotation: float, page_rotation: int) -> float:
    rotation = (span_rotation + page_rotation) % 360
    if rotation > 180:
        rotation -= 360
    if abs(rotation) < 0.5:
        return 0.0
    return rotation


def _source_driven_legend(system_color_map: SystemColorMap) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    entries = list(system_color_map.entries.values())[:12]
    legend_x = 2460.0
    legend_y = 42.0
    legend_w = 420.0
    row_h = 22.0
    bounds = {"x": legend_x - 18.0, "y": legend_y - 18.0, "width": legend_w, "height": 38.0 + len(entries) * row_h}
    frame = _overview_region("source_driven_system_legend_frame", "", bounds, "#64748b", "#ffffff", 0.68, [], {"hideCenterLabel": True})
    frame.style.strokeWidth = 0.7
    frame.style.dash = None
    frame.metadata.update({"sourceDrivenLegend": True})
    objects.append(frame)
    title = _overview_label(
        "source_driven_system_legend_title",
        "SYSTEM LEGEND",
        {"x": legend_x, "y": legend_y - 8.0, "width": 180.0, "height": 14.0},
        "#334155",
        7.0,
        [],
    )
    title.metadata.update({"sourceDrivenLegend": True})
    objects.append(title)
    for index, entry in enumerate(entries):
        y = legend_y + 18.0 + index * row_h
        sample = DrawingObject(
            id=_object_id("source_driven_system_legend_sample", entry.key),
            kind="pipe",
            label="",
            points=[{"x": legend_x, "y": y + 6.0}, {"x": legend_x + 58.0, "y": y + 6.0}],
            bounds={"x": legend_x, "y": y + 3.0, "width": 58.0, "height": 6.0},
            style=DrawingStyle(stroke=entry.color, fill="none", strokeWidth=2.2, opacity=0.95, dash=entry.dash),
            sourceEvidenceIds=[],
            locked=False,
            metadata={"overview": True, "sourceDrivenLegend": True, "sourceDrivenLegendSample": True, "system": entry.key},
        )
        objects.append(sample)
        label = _overview_label(
            f"source_driven_system_legend_label_{entry.key}",
            entry.label,
            {"x": legend_x + 70.0, "y": y - 2.0, "width": 180.0, "height": 14.0},
            "#334155",
            6.4,
            [],
        )
        label.metadata.update({"sourceDrivenLegend": True, "system": entry.key, "systemColorSource": entry.source})
        objects.append(label)
    return objects


def _add_source_driven_group_summary(
    objects: list[DrawingObject],
    slug: str,
    source_graph: PidSourceGraph,
    band_y: float,
    band_height: float,
) -> None:
    bounds = {"x": _OVERVIEW_WIDTH - 560.0, "y": band_y + band_height - 94.0, "width": 350.0, "height": 58.0}
    objects.append(_overview_region(f"{slug}_summary", "", bounds, "#0f766e", "#ffffff", 0.58, source_graph.sourcePageIds, {"hideCenterLabel": True}))
    objects.append(
        _overview_label(
            f"{slug}_summary_label",
            f"{source_graph.metrics['equipmentTags']} EQUIP / {source_graph.metrics['lineTags']} LINES / {source_graph.metrics['continuations']} CONT.",
            {"x": bounds["x"] + 12.0, "y": bounds["y"] + 19.0, "width": bounds["width"] - 24.0, "height": 16.0},
            "#0f766e",
            7.8,
            source_graph.sourcePageIds,
        )
    )


def _add_source_driven_full_coverage(
    objects: list[DrawingObject],
    slug: str,
    source_graph: PidSourceGraph,
    pages: list[PageEvidence],
    band: BoundsDict,
    styles: dict[str, DrawingStyle],
) -> None:
    represented = _represented_source_tokens(objects)
    line_tags = _flatten_line_tags(source_graph.lineTagsBySystem)
    equipment_tags = source_graph.equipmentTags
    instrument_tags = _instrument_tags_for_pages(pages)

    missing_lines = [tag for tag in line_tags if _norm_token(tag) not in represented]
    missing_equipment = [tag for tag in equipment_tags if _norm_token(tag) not in represented]
    missing_instruments = [tag for tag in instrument_tags if _norm_token(tag) not in represented]

    _add_missing_line_tag_rack(objects, slug, source_graph, missing_lines, band, styles)
    _add_missing_equipment_grid(objects, slug, source_graph, missing_equipment, band, styles)
    _add_missing_instrument_grid(objects, slug, source_graph, instrument_tags, band)


def _represented_source_tokens(objects: list[DrawingObject]) -> set[str]:
    tokens: set[str] = set()
    for obj in objects:
        for value in [obj.label, *[metadata_value for metadata_value in obj.metadata.values() if isinstance(metadata_value, str)]]:
            for match in LINE_TAG_TOKEN_RE.finditer(value):
                tokens.add(_norm_token(match.group(0)))
            for match in EQUIPMENT_TAG_RE.finditer(value):
                tokens.add(_norm_token(match.group(0)))
            for match in INSTRUMENT_TAG_RE.finditer(value):
                tokens.add(_norm_token(match.group(0)))
    return tokens


def _flatten_line_tags(tags_by_system: dict[str, list[str]]) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for system_tags in tags_by_system.values():
        for tag in system_tags:
            key = _norm_token(tag)
            if key in seen:
                continue
            seen.add(key)
            tags.append(tag)
    return tags


def _instrument_tags_for_pages(pages: list[PageEvidence]) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for page in pages:
        for match in INSTRUMENT_TAG_RE.finditer(_page_text(page)):
            tag = _clean_source_token(match.group(0))
            key = _norm_token(tag)
            if key in seen:
                continue
            seen.add(key)
            tags.append(tag)
    return sorted(tags, key=_natural_token_key)


def _add_missing_line_tag_rack(
    objects: list[DrawingObject],
    slug: str,
    source_graph: PidSourceGraph,
    line_tags: list[str],
    band: BoundsDict,
    styles: dict[str, DrawingStyle],
) -> None:
    if not line_tags:
        return
    cols = max(2, min(6, int(band["width"] // 430.0)))
    row_gap = 34.0
    col_gap = min(460.0, (band["width"] - 360.0) / cols)
    start_x = band["x"] + 170.0
    start_y = band["y"] + max(104.0, band["height"] - 128.0)
    for index, tag in enumerate(line_tags):
        col = index % cols
        row = index // cols
        x = start_x + col * col_gap
        y = start_y + row * row_gap
        system = _system_for_tag(tag, source_graph.groupName)
        pipe = _overview_pipe(f"{slug}_coverage_line_{tag}", tag, [{"x": x, "y": y}, {"x": x + 142.0, "y": y}], system, styles, source_graph.sourcePageIds, 1.55)
        pipe.metadata.update({"sourceCoverage": True, "sourceCoverageRole": "line", "lineTag": tag})
        objects.append(pipe)
        label = _overview_label(f"{slug}_coverage_line_label_{tag}", tag, {"x": x + 154.0, "y": y - 8.0, "width": 170.0, "height": 16.0}, "#111827", 7.0, source_graph.sourcePageIds)
        label.metadata.update({"sourceCoverage": True, "sourceCoverageRole": "line", "lineTag": tag})
        objects.append(label)


def _add_missing_equipment_grid(
    objects: list[DrawingObject],
    slug: str,
    source_graph: PidSourceGraph,
    equipment_tags: list[str],
    band: BoundsDict,
    styles: dict[str, DrawingStyle],
) -> None:
    if not equipment_tags:
        return
    columns = max(4, min(12, int(band["width"] // 230.0)))
    gap_x = min(230.0, (band["width"] - 260.0) / columns)
    gap_y = 58.0
    start_x = band["x"] + 168.0
    start_y = band["y"] + 84.0
    for index, tag in enumerate(equipment_tags):
        col = index % columns
        row = index // columns
        x = start_x + col * gap_x
        y = start_y + row * gap_y
        if y > band["y"] + band["height"] - 178.0:
            y = band["y"] + 84.0 + (row % max(1, int((band["height"] - 260.0) // gap_y))) * gap_y
            x = start_x + (columns + col) * min(126.0, gap_x * 0.56)
        system = _system_for_tag(tag, source_graph.groupName)
        stroke = SYSTEM_COLORS.get(system, "#334155")
        symbol = _overview_symbol(
            f"{slug}_coverage_equipment_{tag}_{index}",
            tag,
            {"x": x, "y": y, "width": 104.0, "height": 38.0},
            stroke,
            source_graph.sourcePageIds,
            _symbol_type_for_tag(tag),
            metadata={"sourceCoverage": True, "sourceCoverageRole": "equipment", "equipmentTag": tag},
        )
        objects.append(symbol)
        tap = _overview_pipe(f"{slug}_coverage_equipment_tap_{tag}_{index}", "", [{"x": x + 52.0, "y": y - 18.0}, {"x": x + 52.0, "y": y}], system, styles, source_graph.sourcePageIds, 1.05)
        tap.metadata.update({"sourceCoverage": True, "sourceCoverageRole": "equipmentTap", "equipmentTag": tag})
        objects.append(tap)


def _add_missing_instrument_grid(
    objects: list[DrawingObject],
    slug: str,
    source_graph: PidSourceGraph,
    instrument_tags: list[str],
    band: BoundsDict,
) -> None:
    if not instrument_tags:
        return
    # Keep OCR-only instrument coverage available to QA/inspection without
    # drawing an orphan register across the bottom of a house-style sheet.
    inventory = _overview_region(
        f"{slug}_coverage_instrument_inventory",
        "",
        {"x": band["x"], "y": band["y"], "width": 1.0, "height": 1.0},
        "#ffffff",
        "#ffffff",
        0.0,
        source_graph.sourcePageIds,
        {"hideCenterLabel": True},
    )
    inventory.metadata.update(
        {
            "sourceCoverage": True,
            "sourceCoverageRole": "instrumentInventory",
            "instrumentTags": " ".join(instrument_tags),
            "instrumentTagCount": len(instrument_tags),
        }
    )
    objects.append(inventory)


def _add_single_sheet_reconstruction(
    objects: list[DrawingObject],
    slug: str,
    page: PageEvidence,
    band: BoundsDict,
) -> None:
    tile = {"x": band["x"] + 80.0, "y": band["y"] + 78.0, "width": band["width"] - 160.0, "height": band["height"] - 170.0}
    vectors = _select_source_vectors(page, limit=900)
    source_bounds = _single_sheet_source_bounds(page, vectors)
    for index, vector in enumerate(vectors):
        points = _map_source_vector_points(vector, source_bounds, tile)
        if len(points) < 2:
            continue
        obj = DrawingObject(
            id=_object_id("single_sheet_reconstruction_vector", slug, page.id, vector.id, index),
            kind="pipe",
            label="",
            points=points,
            bounds=_points_bounds(points, 2.0),
            style=DrawingStyle(
                stroke=_source_vector_stroke(vector),
                fill="none",
                strokeWidth=max(0.55, min(1.25, vector.strokeWidth or 0.9)),
                opacity=0.62,
                dash=[4.0, 3.0] if vector.dashed else None,
            ),
            sourceEvidenceIds=[page.id, vector.id] if vector.id else [page.id],
            locked=False,
            metadata={"overview": True, "sourceDerived": True, "singleSheetReconstructionVector": True, "sourceVectorId": vector.id, "sourcePageId": page.id},
        )
        objects.append(obj)

    for index, span in enumerate(page.textSpans):
        if _is_admin_text(span.text):
            continue
        text = _reconstructable_text(span.text)
        if not text:
            continue
        bounds = _map_source_bounds(span.x, span.y, span.width, span.height, source_bounds, tile)
        label = _overview_label(
            f"{slug}_single_sheet_text_{index}_{text}",
            text,
            bounds,
            "#111827",
            max(4.8, min(8.8, bounds["height"] * 0.78)),
            [page.id],
        )
        label.metadata.update({"singleSheetReconstructionText": True, "sourceCoverage": True, "sourcePageId": page.id})
        objects.append(label)


def _single_sheet_source_bounds(page: PageEvidence, vectors: list[VectorSegment]) -> BoundsDict:
    bounds: list[BoundsDict] = [vector.bounds for vector in vectors]
    for span in page.textSpans:
        if _is_admin_text(span.text):
            continue
        if _reconstructable_text(span.text):
            bounds.append({"x": span.x, "y": span.y, "width": span.width, "height": span.height})
    if not bounds:
        return page.cropBounds
    x0 = min(item["x"] for item in bounds)
    y0 = min(item["y"] for item in bounds)
    x1 = max(item["x"] + item["width"] for item in bounds)
    y1 = max(item["y"] + item["height"] for item in bounds)
    pad_x = max(30.0, (x1 - x0) * 0.035)
    pad_y = max(30.0, (y1 - y0) * 0.035)
    return {"x": x0 - pad_x, "y": y0 - pad_y, "width": x1 - x0 + pad_x * 2.0, "height": y1 - y0 + pad_y * 2.0}


def _map_source_bounds(x: float, y: float, width: float, height: float, source_bounds: BoundsDict, tile: BoundsDict) -> BoundsDict:
    top_left = _map_source_point({"x": x, "y": y}, source_bounds, tile)
    bottom_right = _map_source_point({"x": x + width, "y": y + height}, source_bounds, tile)
    return {
        "x": top_left["x"],
        "y": top_left["y"],
        "width": max(8.0, bottom_right["x"] - top_left["x"]),
        "height": max(8.0, bottom_right["y"] - top_left["y"]),
    }


def _map_source_point(point: Point, source_bounds: BoundsDict, tile: BoundsDict) -> Point:
    padding = 18.0
    usable_width = max(1.0, tile["width"] - padding * 2.0)
    usable_height = max(1.0, tile["height"] - padding * 2.0)
    scale = min(usable_width / max(1.0, source_bounds["width"]), usable_height / max(1.0, source_bounds["height"]))
    scaled_width = source_bounds["width"] * scale
    scaled_height = source_bounds["height"] * scale
    offset_x = tile["x"] + (tile["width"] - scaled_width) / 2.0
    offset_y = tile["y"] + (tile["height"] - scaled_height) / 2.0
    return {
        "x": offset_x + (point["x"] - source_bounds["x"]) * scale,
        "y": offset_y + (point["y"] - source_bounds["y"]) * scale,
    }


def _reconstructable_text(text: str) -> str:
    useful: list[str] = []
    for regex in (LINE_TAG_TOKEN_RE, EQUIPMENT_TAG_RE, INSTRUMENT_TAG_RE):
        useful.extend(_clean_source_token(match.group(0)) for match in regex.finditer(text))
    return " ".join(dict.fromkeys(useful))


def _is_admin_text(text: str) -> bool:
    return bool(ADMIN_TEXT_RE.search(text or ""))


def _clean_source_token(value: str) -> str:
    return re.sub(r"\s+", "-", value.strip().upper())


def _norm_token(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", value.upper())


def _natural_token_key(value: str) -> tuple[str, int, str]:
    match = re.search(r"(\d+)", value)
    return (re.sub(r"\d+", "", value), int(match.group(1)) if match else 9999, value)


def _combined_pid_objects(
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
    styles: dict[str, DrawingStyle],
) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    source_ids = [page.id for page in pages]
    objects.append(
        _overview_label(
            "combined_title",
            f"{PROJECT_CODE} COMBINED P&ID SYSTEM OVERVIEW",
            {"x": 1120.0, "y": 54.0, "width": 1220.0, "height": 38.0},
            "#0f172a",
            28.0,
            source_ids,
        )
    )
    objects.append(
        _overview_label(
            "combined_subtitle",
            f"Editable recreated P&ID assembled from {len(pages)} source sheets, extracted equipment tags, and off-sheet continuations",
            {"x": 1040.0, "y": 100.0, "width": 1380.0, "height": 22.0},
            "#475569",
            14.0,
            source_ids,
        )
    )
    group_map = dict(_overview_groups(pages, source_paths))
    cda_bounds = {"x": 140.0, "y": 245.0, "width": 1320.0, "height": 610.0}
    chw_bounds = {"x": 120.0, "y": 875.0, "width": 2050.0, "height": 1450.0}
    hhw_bounds = {"x": 1810.0, "y": 245.0, "width": 1500.0, "height": 2050.0}
    dist_bounds = {"x": 2860.0, "y": 650.0, "width": 390.0, "height": 1210.0}

    objects.append(_overview_region("combined_cda_zone", "CDA / IA", cda_bounds, "#7c3aed", GROUP_COLORS["CDA"], 0.16, _page_ids(group_map.get("CDA", [])), {"hideCenterLabel": True}))
    objects.append(_overview_region("combined_chw_zone", "CHILLED WATER / COOLING WATER", chw_bounds, "#0284c7", GROUP_COLORS["CHW / CW"], 0.13, _page_ids(group_map.get("CHW / CW", [])), {"hideCenterLabel": True}))
    objects.append(_overview_region("combined_hhw_zone", "HEATED HOT WATER / HRW", hhw_bounds, "#ef4444", GROUP_COLORS["HHW / HRW"], 0.12, _page_ids(group_map.get("HHW / HRW", [])), {"hideCenterLabel": True}))
    objects.append(_overview_region("combined_distribution_zone", "BUILDING / SITE DISTRIBUTION", dist_bounds, "#64748b", "#f8fafc", 0.16, source_ids, {"hideCenterLabel": True}))

    _add_zone_label(objects, "combined_cda_zone_label", "CDA / IA GENERATION", cda_bounds, "#581c87", _page_ids(group_map.get("CDA", [])))
    _add_zone_label(objects, "combined_chw_zone_label", "CHW / CW PLANT AND DISTRIBUTION", chw_bounds, "#075985", _page_ids(group_map.get("CHW / CW", [])))
    _add_zone_label(objects, "combined_hhw_zone_label", "HHW / HRW PLANT", hhw_bounds, "#991b1b", _page_ids(group_map.get("HHW / HRW", [])))
    _add_zone_label(objects, "combined_distribution_zone_label", "SITE DISTRIBUTION", dist_bounds, "#334155", source_ids)
    _add_overview_detail_boxes(objects, cda_bounds, chw_bounds, hhw_bounds, dist_bounds, group_map, source_ids)

    _combined_cda_system(objects, group_map.get("CDA", []), candidates, source_paths, styles, cda_bounds)
    _combined_chw_cw_system(objects, group_map.get("CHW / CW", []), candidates, source_paths, styles, chw_bounds, dist_bounds)
    _combined_hhw_hrw_system(objects, group_map.get("HHW / HRW", []), candidates, source_paths, styles, hhw_bounds, dist_bounds)
    _combined_distribution(objects, pages, styles, dist_bounds)
    _add_reference_title_block(objects, pages, source_paths)
    return objects


def _mark_layout_mode(objects: list[DrawingObject], layout_mode: str) -> None:
    for obj in objects:
        obj.metadata = {**obj.metadata, "layoutMode": layout_mode}


def _mark_source_generated(objects: list[DrawingObject]) -> None:
    for obj in objects:
        obj.metadata = {**obj.metadata, "sourceGenerated": True}


def _page_ids(pages: list[PageEvidence]) -> list[str]:
    return [page.id for page in pages]


def _add_zone_label(
    objects: list[DrawingObject],
    id_seed: str,
    label: str,
    bounds: BoundsDict,
    color: str,
    evidence_ids: list[str],
) -> None:
    objects.append(
        _overview_label(
            id_seed,
            label,
            {"x": bounds["x"] + 24.0, "y": bounds["y"] + 20.0, "width": min(620.0, bounds["width"] - 48.0), "height": 20.0},
            color,
            15.0,
            evidence_ids,
        )
    )


def _combined_cda_system(
    objects: list[DrawingObject],
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    source_paths: dict[str, str],
    styles: dict[str, DrawingStyle],
    bounds: BoundsDict,
) -> None:
    page_ids = _page_ids(pages)
    equipment = _equipment_tags_for_pages(pages)
    line_tags = _line_tags_for_pages(pages, "CDA")
    group_candidates = _meaningful_continuation_candidates(candidates, pages, source_paths, "CDA")
    x0, y0, w, h = bounds["x"], bounds["y"], bounds["width"], bounds["height"]
    header_y = y0 + 150.0
    process_y = y0 + 330.0
    lower_y = y0 + 485.0
    left_x = x0 + 120.0
    right_x = x0 + w - 110.0
    cda_tag = _first_tag(line_tags, "CDA", '6"-CDA-SS01')

    objects.append(_overview_pipe("combined_cda_top_header", cda_tag, [{"x": left_x, "y": header_y}, {"x": right_x, "y": header_y}], "CDA", styles, page_ids, 3.2))
    objects.append(_overview_pipe("combined_cda_returned_loop", "", [{"x": left_x, "y": header_y}, {"x": left_x, "y": lower_y}, {"x": x0 + 540.0, "y": lower_y}, {"x": x0 + 540.0, "y": process_y}, {"x": x0 + 970.0, "y": process_y}, {"x": x0 + 970.0, "y": header_y}], "CDA", styles, page_ids, 2.2))
    objects.append(_overview_pipe("combined_cda_dryer_bypass", "", [{"x": x0 + 430.0, "y": header_y}, {"x": x0 + 430.0, "y": process_y - 82.0}, {"x": x0 + 920.0, "y": process_y - 82.0}, {"x": x0 + 920.0, "y": header_y}], "CDA", styles, page_ids, 1.7))
    _add_line_tag(objects, "combined_cda_tag", cda_tag, x0 + 735.0, header_y - 26.0, "CDA", page_ids)
    _add_flow_arrow(objects, "combined_cda_flow", right_x, header_y, "CDA", page_ids)

    compressors = _pick_equipment(equipment, ["-C-"], [f"R-{PROJECT_CODE}-CDA-C-01", f"R-{PROJECT_CODE}-CDA-C-02", f"R-{PROJECT_CODE}-CDA-C-03"], 3)
    dryers = _pick_equipment(equipment, ["-AD-"], [f"R-{PROJECT_CODE}-CDA-AD-01", f"R-{PROJECT_CODE}-CDA-AD-02"], 2)
    filters = _pick_equipment(equipment, ["-FLTR-"], [f"R-{PROJECT_CODE}-CDA-FLTR-01", f"R-{PROJECT_CODE}-CDA-FLTR-02"], 2)
    tanks = _pick_equipment(equipment, ["-ST-", "-ET-"], [f"R-{PROJECT_CODE}-CDA-ST-01", f"R-{PROJECT_CODE}-CDA-ST-02"], 2)
    _place_symbol_row(objects, "combined_cda_compressors", compressors, x0 + 230.0, process_y + 54.0, 150.0, "CDA", page_ids, header_y)
    _place_symbol_row(objects, "combined_cda_dryers", dryers, x0 + 610.0, process_y + 44.0, 170.0, "CDA", page_ids, header_y)
    _place_symbol_row(objects, "combined_cda_filters", filters, x0 + 910.0, process_y + 44.0, 145.0, "CDA", page_ids, header_y)
    _place_symbol_row(objects, "combined_cda_receivers", tanks, x0 + 1110.0, process_y + 32.0, 150.0, "CDA", page_ids, header_y)
    _add_valve_station(objects, "combined_cda_valves", x0 + 1025.0, header_y, "CDA", styles, page_ids, 4, 42.0)
    _add_edge_continuation_stack(objects, "combined_cda", group_candidates, styles, "CDA", page_ids, right_x + 16.0, header_y + 82.0, 48.0, 4, "right")


def _combined_chw_cw_system(
    objects: list[DrawingObject],
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    source_paths: dict[str, str],
    styles: dict[str, DrawingStyle],
    bounds: BoundsDict,
    distribution_bounds: BoundsDict,
    source_graph: PidSourceGraph | None = None,
) -> None:
    page_ids = _page_ids(pages)
    equipment = _equipment_tags_for_pages(pages)
    line_tags = _line_tags_for_pages(pages, "CHW / CW")
    group_candidates = _meaningful_continuation_candidates(candidates, pages, source_paths, "CHW / CW")
    x0, y0, w, h = bounds["x"], bounds["y"], bounds["width"], bounds["height"]
    chws = _first_tag(line_tags, "CHWS", '24"-CHWS-CS01')
    chwr = _first_tag(line_tags, "CHWR", '24"-CHWR-CS01')
    cws = _first_tag(line_tags, "CWS", '18"-CWS-CS01')
    cwr = _first_tag(line_tags, "CWR", '18"-CWR-CS01')

    plant_left = x0 + 140.0
    plant_right = x0 + 1110.0
    riser_x = x0 + 1410.0
    tower_x = x0 + 1770.0
    source_generated = source_graph is not None
    top_y = y0 + 165.0
    return_y = y0 + 390.0
    condenser_y = y0 + 655.0
    basin_y = y0 + 1090.0
    bottom_y = y0 + (1260.0 if source_generated else h - 150.0)
    dist_x = distribution_bounds["x"] + 40.0

    supply_header = _overview_pipe("combined_chw_supply_header", chws, [{"x": plant_left, "y": top_y}, {"x": riser_x, "y": top_y}, {"x": riser_x, "y": bottom_y}, {"x": dist_x, "y": bottom_y}], "CHWS", styles, page_ids, 3.4)
    return_header = _overview_pipe("combined_chw_return_header", chwr, [{"x": dist_x, "y": return_y}, {"x": riser_x - 120.0, "y": return_y}, {"x": riser_x - 120.0, "y": y0 + 250.0}, {"x": plant_left + 120.0, "y": y0 + 250.0}, {"x": plant_left + 120.0, "y": return_y}], "CHWR", styles, page_ids, 2.8)
    cw_supply_loop = _overview_pipe("combined_cw_supply_loop", cws, [{"x": plant_left + 50.0, "y": condenser_y}, {"x": tower_x, "y": condenser_y}, {"x": tower_x, "y": y0 + 260.0}, {"x": dist_x + 100.0, "y": y0 + 260.0}], "CWS", styles, page_ids, 2.7)
    cw_return_loop = _overview_pipe("combined_cw_return_loop", cwr, [{"x": dist_x + 100.0, "y": y0 + 470.0}, {"x": tower_x + 120.0, "y": y0 + 470.0}, {"x": tower_x + 120.0, "y": basin_y}, {"x": plant_left + 90.0, "y": basin_y}, {"x": plant_left + 90.0, "y": condenser_y}], "CWR", styles, page_ids, 2.7)
    low_bridge = _overview_pipe("combined_chw_low_bridge", "", [{"x": x0 + 500.0, "y": y0 + 980.0}, {"x": x0 + 500.0, "y": bottom_y - 160.0}, {"x": riser_x + 170.0, "y": bottom_y - 160.0}, {"x": riser_x + 170.0, "y": return_y}], "CHWR", styles, page_ids, 1.8)
    if source_generated:
        _mark_route_polish(supply_header, "primary_chws")
        _mark_route_polish(return_header, "primary_chwr")
        _mark_route_polish(cw_supply_loop, "primary_cws")
        _mark_route_polish(cw_return_loop, "primary_cwr")
        _mark_route_polish(low_bridge, "compact_return_bridge")
    objects.extend([supply_header, return_header, cw_supply_loop, cw_return_loop, low_bridge])

    _add_line_tag(objects, "combined_chws_tag", chws, x0 + 760.0, top_y - 28.0, "CHWS", page_ids)
    _add_line_tag(objects, "combined_chwr_tag", chwr, x0 + 770.0, return_y - 26.0, "CHWR", page_ids)
    _add_line_tag(objects, "combined_cws_tag", cws, x0 + 910.0, condenser_y - 26.0, "CWS", page_ids)
    _add_line_tag(objects, "combined_cwr_tag", cwr, x0 + 950.0, basin_y - 26.0, "CWR", page_ids)
    _add_flow_arrow(objects, "combined_chws_flow", riser_x, top_y, "CHWS", page_ids)
    _add_flow_arrow(objects, "combined_chwr_flow", plant_left + 120.0, return_y, "CHWR", page_ids, "left")
    _add_flow_arrow(objects, "combined_cwr_flow", plant_left + 90.0, basin_y, "CWR", page_ids, "left")

    chillers = _source_graph_equipment(source_graph, "chiller_bank") or _pick_equipment(equipment, ["-CH-"], [f"R-{PROJECT_CODE}-CHW-CH-01", f"R-{PROJECT_CODE}-CHW-CH-02", f"R-{PROJECT_CODE}-CHW-CH-03", f"R-{PROJECT_CODE}-CHW-CH-04", f"R-{PROJECT_CODE}-CHW-CH-05", f"R-{PROJECT_CODE}-CHW-CH-06", f"R-{PROJECT_CODE}-CHW-CH-07"], 7)
    pumps = (
        _source_graph_equipment(source_graph, "chw_pumps")
        + _source_graph_equipment(source_graph, "cw_pumps")
        or _pick_equipment(equipment, ["-P-"], [f"R-{PROJECT_CODE}-CHW-P-01", f"R-{PROJECT_CODE}-CHW-P-02", f"R-{PROJECT_CODE}-CHW-P-03", f"R-{PROJECT_CODE}-CHW-P-04", f"R-{PROJECT_CODE}-CW-P-01", f"R-{PROJECT_CODE}-CW-P-02"], 6)
    )
    towers = _source_graph_equipment(source_graph, "cooling_water") or _pick_equipment(equipment, ["-CT-"], [f"R-{PROJECT_CODE}-CW-CT-01", f"R-{PROJECT_CODE}-CW-CT-02", f"R-{PROJECT_CODE}-CW-CT-03", f"R-{PROJECT_CODE}-CW-CT-04"], 4)
    _place_symbol_grid(objects, "combined_chw_chillers", chillers, plant_left + 170.0, y0 + 330.0, 4, 215.0, 155.0, "CHWS", page_ids, [top_y, return_y])
    _place_symbol_row(objects, "combined_chw_pumps", pumps, plant_left + 185.0, y0 + 900.0, 138.0, "CHWS", page_ids, basin_y)
    _place_symbol_grid(objects, "combined_chw_towers", towers, tower_x - 35.0, y0 + 520.0, 2, 175.0, 150.0, "CWS", page_ids, [condenser_y])
    _add_chw_detail_density(objects, plant_left, riser_x, tower_x, top_y, return_y, condenser_y, basin_y, y0, styles, page_ids)
    _add_valve_station(objects, "combined_chw_riser_valves", riser_x, top_y + 150.0, "CHWS", styles, page_ids, 8, 92.0)
    _add_valve_station(objects, "combined_cw_tower_valves", tower_x + 120.0, y0 + 560.0, "CWR", styles, page_ids, 5, 76.0)
    _add_edge_continuation_stack(objects, "combined_chw_right", group_candidates, styles, "CHWS", page_ids, x0 + w - 120.0, y0 + 930.0, 58.0, 4, "right")
    _add_edge_continuation_stack(objects, "combined_chw_left", group_candidates, styles, "CHWR", page_ids, x0 + 72.0, y0 + 1070.0, 42.0, 4, "left")


def _combined_hhw_hrw_system(
    objects: list[DrawingObject],
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    source_paths: dict[str, str],
    styles: dict[str, DrawingStyle],
    bounds: BoundsDict,
    distribution_bounds: BoundsDict,
) -> None:
    page_ids = _page_ids(pages)
    equipment = _equipment_tags_for_pages(pages)
    line_tags = _line_tags_for_pages(pages, "HHW / HRW")
    group_candidates = _meaningful_continuation_candidates(candidates, pages, source_paths, "HHW / HRW")
    x0, y0, w, h = bounds["x"], bounds["y"], bounds["width"], bounds["height"]
    hhw_supply = _first_tag(line_tags, "HHWS", '12"-HHWS-CS01')
    hhw_return = _first_tag(line_tags, "HHWR", '12"-HHWR-CS01')
    hrw_tag = _first_tag(line_tags, "HRW", '8"-HRW-CS01')
    future = {"x": x0 + 70.0, "y": y0 + 130.0, "width": 360.0, "height": 1510.0}
    objects.append(_overview_region("combined_hhw_future", "FUTURE", future, "#ef4444", "#ffffff", 0.48, page_ids))
    objects.append(_overview_label("combined_hhw_future_vertical", "FUTURE EXPANSION", {"x": future["x"] + 92.0, "y": future["y"] + 34.0, "width": 180.0, "height": 20.0}, "#991b1b", 13.0, page_ids))

    supply_y = y0 + 260.0
    return_y = y0 + 590.0
    recovery_y = y0 + 1020.0
    lower_y = y0 + 1665.0
    boiler_x = x0 + 560.0
    pump_x = x0 + 940.0
    hx_x = x0 + 1160.0
    dist_x = distribution_bounds["x"] + 260.0

    objects.append(_overview_pipe("combined_hhw_supply_header", hhw_supply, [{"x": future["x"] + 40.0, "y": supply_y}, {"x": boiler_x + 380.0, "y": supply_y}, {"x": boiler_x + 380.0, "y": y0 + 760.0}, {"x": dist_x, "y": y0 + 760.0}], "HHWS", styles, page_ids, 3.1))
    objects.append(_overview_pipe("combined_hhw_return_header", hhw_return, [{"x": dist_x, "y": return_y}, {"x": pump_x - 210.0, "y": return_y}, {"x": pump_x - 210.0, "y": lower_y}, {"x": future["x"] + 80.0, "y": lower_y}, {"x": future["x"] + 80.0, "y": supply_y}], "HHWR", styles, page_ids, 2.6))
    objects.append(_overview_pipe("combined_hrw_recovery_network", hrw_tag, [{"x": x0 + 620.0, "y": recovery_y}, {"x": hx_x + 210.0, "y": recovery_y}, {"x": hx_x + 210.0, "y": y0 + 1430.0}, {"x": pump_x - 10.0, "y": y0 + 1430.0}, {"x": pump_x - 10.0, "y": return_y}], "HRW", styles, page_ids, 2.4))
    objects.append(_overview_pipe("combined_hhw_future_ladder", "", [{"x": future["x"] + 130.0, "y": future["y"] + 110.0}, {"x": future["x"] + 130.0, "y": future["y"] + future["height"] - 120.0}], "HHWS", styles, page_ids, 1.7))

    _add_line_tag(objects, "combined_hhws_tag", hhw_supply, boiler_x + 120.0, supply_y - 28.0, "HHWS", page_ids)
    _add_line_tag(objects, "combined_hhwr_tag", hhw_return, pump_x - 10.0, return_y - 28.0, "HHWR", page_ids)
    _add_line_tag(objects, "combined_hrw_tag", hrw_tag, hx_x + 40.0, recovery_y - 26.0, "HRW", page_ids)
    _add_flow_arrow(objects, "combined_hhws_flow", dist_x, y0 + 760.0, "HHWS", page_ids)
    _add_flow_arrow(objects, "combined_hhwr_flow", dist_x, return_y, "HHWR", page_ids, "left")

    boilers = _pick_equipment(equipment, ["-HWB-", "-BLR-"], [f"R-{PROJECT_CODE}-HHW-HWB-01", f"R-{PROJECT_CODE}-HHW-HWB-02", f"R-{PROJECT_CODE}-HHW-HWB-03", f"R-{PROJECT_CODE}-HHW-HWB-04"], 4)
    future_boilers = _pick_equipment(equipment, ["-HWB-", "-BLR-"], [f"R-{PROJECT_CODE}-HHW-HWB-01", f"R-{PROJECT_CODE}-HHW-HWB-02", f"R-{PROJECT_CODE}-HHW-HWB-03", f"R-{PROJECT_CODE}-HHW-HWB-04", f"R-{PROJECT_CODE}-HHW-HWB-05", f"R-{PROJECT_CODE}-HHW-HWB-06", f"R-{PROJECT_CODE}-HHW-HWB-07", f"R-{PROJECT_CODE}-HHW-HWB-08"], 8)
    pumps = _pick_equipment(equipment, ["-P-"], [f"R-{PROJECT_CODE}-HHW-P-01", f"R-{PROJECT_CODE}-HHW-P-02", f"R-{PROJECT_CODE}-HHW-P-03", f"R-{PROJECT_CODE}-HHW-P-04", f"R-{PROJECT_CODE}-HRW-P-01", f"R-{PROJECT_CODE}-HRW-P-02"], 6)
    exchangers = _pick_equipment(equipment, ["-HX-", "-AS-"], [f"R-{PROJECT_CODE}-HRW-HX-01", f"R-{PROJECT_CODE}-HRW-HX-02", f"R-{PROJECT_CODE}-HRW-HX-03", f"R-{PROJECT_CODE}-HRW-HX-04"], 4)
    _place_symbol_grid(objects, "combined_hhw_future_boilers", future_boilers, future["x"] + 230.0, future["y"] + 145.0, 1, 0.0, 145.0, "HHWS", page_ids, [supply_y, return_y])
    _place_symbol_grid(objects, "combined_hhw_boilers", boilers, boiler_x, y0 + 365.0, 2, 190.0, 190.0, "HHWS", page_ids, [supply_y, return_y])
    _place_symbol_grid(objects, "combined_hhw_pumps", pumps, pump_x - 120.0, y0 + 1290.0, 3, 145.0, 142.0, "HHWR", page_ids, [return_y])
    _place_symbol_grid(objects, "combined_hhw_exchangers", exchangers, hx_x - 20.0, recovery_y + 72.0, 2, 165.0, 142.0, "HRW", page_ids, [recovery_y])
    _add_hhw_detail_density(objects, future, boiler_x, pump_x, hx_x, supply_y, return_y, recovery_y, lower_y, y0, styles, page_ids)
    _add_valve_station(objects, "combined_hhw_distribution_valves", dist_x - 30.0, y0 + 760.0, "HHWS", styles, page_ids, 6, 80.0)
    _add_edge_continuation_stack(objects, "combined_hhw_right", group_candidates, styles, "HHWS", page_ids, distribution_bounds["x"] + 312.0, y0 + 380.0, 72.0, 5, "right")


def _add_presentation_hhw_hrw_route_bundle(
    objects: list[DrawingObject],
    slug: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    source_paths: dict[str, str],
    source_graph: PidSourceGraph,
    styles: dict[str, DrawingStyle],
    plant_bounds: BoundsDict,
    distribution_bounds: BoundsDict,
) -> None:
    page_ids = _page_ids(pages)
    bus_x = distribution_bounds["x"] - 82.0
    branch_end_x = distribution_bounds["x"] - 16.0
    lanes = [
        ("HHWS", _first_tag(source_graph.lineTagsBySystem, "HHWS", '12"-HHWS-CS02'), plant_bounds["y"] + 760.0),
        ("HHWR", _first_tag(source_graph.lineTagsBySystem, "HHWR", '12"-HHWR-CS02'), plant_bounds["y"] + 980.0),
        ("HRW", _first_tag(source_graph.lineTagsBySystem, "HRW", '24"-HRW-CS02'), plant_bounds["y"] + 1160.0),
    ]
    vertical = _overview_pipe(
        f"{slug}_route_bundle_manifold",
        "",
        [{"x": bus_x, "y": lanes[0][2] - 70.0}, {"x": bus_x, "y": lanes[-1][2] + 120.0}],
        "DEFAULT",
        styles,
        page_ids,
        1.25,
    )
    vertical.style.dash = [10.0, 8.0]
    vertical.metadata.update({"presentationRouteBundle": True, "routeRole": "manifold", "sourceGenerated": True, "system": "DEFAULT"})
    objects.append(vertical)

    for index, (system, tag, y) in enumerate(lanes):
        pipe = _overview_pipe(
            f"{slug}_route_bundle_lane_{system.lower()}",
            tag,
            [{"x": bus_x - 34.0, "y": y}, {"x": bus_x, "y": y}, {"x": branch_end_x, "y": y}],
            system,
            styles,
            page_ids,
            2.2 if system != "HRW" else 1.9,
        )
        pipe.metadata.update({"presentationRouteBundle": True, "routeRole": "handoff_lane", "sourceGenerated": True, "system": system, "lineTag": tag})
        objects.append(pipe)
        _add_flow_arrow(objects, f"{slug}_route_bundle_arrow_{system.lower()}", branch_end_x, y, system, page_ids)
        objects[-1].metadata.update({"presentationRouteBundle": True, "routeRole": "handoff_flow", "sourceGenerated": True, "system": system, "lineTag": tag})
        label = _overview_label(
            f"{slug}_route_bundle_label_{system.lower()}",
            _compact_line_tag_label(tag, system),
            {"x": bus_x + 18.0, "y": y - 24.0, "width": 172.0, "height": 14.0},
            SYSTEM_COLORS.get(system, "#334155"),
            7.0,
            page_ids,
        )
        label.metadata.update({"presentationRouteBundle": True, "routeRole": "handoff_label", "sourceGenerated": True, "system": system, "lineTag": tag})
        objects.append(label)
        if index:
            tie = _overview_pipe(
                f"{slug}_route_bundle_tie_{system.lower()}",
                "",
                [{"x": bus_x, "y": lanes[index - 1][2]}, {"x": bus_x, "y": y}],
                system,
                styles,
                page_ids,
                0.85,
            )
            tie.style.dash = [8.0, 7.0]
            tie.metadata.update({"presentationRouteBundle": True, "routeRole": "system_tie", "sourceGenerated": True, "system": system})
            objects.append(tie)

    continuations = _meaningful_continuation_candidates(candidates, pages, source_paths, "HHW / HRW")
    for index, candidate in enumerate(continuations[:6]):
        y = distribution_bounds["y"] + 112.0 + index * 88.0
        system = candidate.system or _system_for_tag(candidate.lineTag or candidate.label, "HHW / HRW") or "HHWS"
        evidence_ids = [candidate.id] if candidate.id else page_ids
        rack = _overview_pipe(
            f"{slug}_continuation_rack_{index}",
            "",
            [{"x": branch_end_x + 52.0, "y": y}, {"x": distribution_bounds["x"] + distribution_bounds["width"] - 152.0, "y": y}],
            system,
            styles,
            evidence_ids,
            1.15,
        )
        rack.metadata.update(
            {
                "presentationContinuationRack": True,
                "sourceGenerated": True,
                "sourceCandidateId": candidate.id,
                "lineTag": candidate.lineTag,
                "sheetRef": candidate.sheetRef,
                "system": system,
            }
        )
        objects.append(rack)


def _compact_line_tag_label(tag: str, fallback: str) -> str:
    if not tag:
        return fallback
    match = LINE_TAG_TOKEN_RE.search(tag)
    return match.group(0).upper() if match else tag.upper()


def _combined_distribution(
    objects: list[DrawingObject],
    pages: list[PageEvidence],
    styles: dict[str, DrawingStyle],
    bounds: BoundsDict,
) -> None:
    page_ids = _page_ids(pages)
    x0, y0, w, h = bounds["x"], bounds["y"], bounds["width"], bounds["height"]
    rail_x = x0 + 120.0
    objects.append(_overview_pipe("combined_distribution_vertical_rail", "", [{"x": rail_x, "y": y0 + 70.0}, {"x": rail_x, "y": y0 + h - 90.0}], "DEFAULT", styles, page_ids, 2.2))
    rows = [
        ("PROCESS CONDENSATE", "CDA", y0 + 140.0),
        ("CHW SUPPLY / RETURN", "CHWS", y0 + 320.0),
        ("CONDENSER WATER", "CWS", y0 + 500.0),
        ("HHW SUPPLY / RETURN", "HHWS", y0 + 720.0),
        ("HRW RECOVERY", "HRW", y0 + 900.0),
        ("FUTURE CONNECTIONS", "DEFAULT", y0 + 1080.0),
    ]
    for index, (label, system, y) in enumerate(rows):
        objects.append(_overview_pipe(f"combined_distribution_branch_{index}", "", [{"x": rail_x, "y": y}, {"x": x0 + w - 90.0, "y": y}], system, styles, page_ids, 1.9))
        _add_flow_arrow(objects, f"combined_distribution_arrow_{index}", x0 + w - 90.0, y, system, page_ids)
        objects.append(_overview_label(f"combined_distribution_label_{index}", label, {"x": x0 + 150.0, "y": y - 28.0, "width": 188.0, "height": 18.0}, "#111827", 9.0, page_ids))


def _add_chw_detail_density(
    objects: list[DrawingObject],
    plant_left: float,
    riser_x: float,
    tower_x: float,
    top_y: float,
    return_y: float,
    condenser_y: float,
    basin_y: float,
    y0: float,
    styles: dict[str, DrawingStyle],
    page_ids: list[str],
) -> None:
    chiller_xs = [plant_left + 170.0 + (index % 4) * 215.0 for index in range(7)]
    chiller_ys = [y0 + 330.0 + (index // 4) * 155.0 for index in range(7)]
    for index, (x, y) in enumerate(zip(chiller_xs, chiller_ys), start=1):
        _add_equipment_detail_train(objects, f"combined_chw_chiller_detail_{index}", x, top_y, return_y, y, "CHWS", "PDIT" if index % 2 else "TIT", styles, page_ids)
        objects.append(_overview_label(f"combined_chw_chiller_service_{index}", "HR Chiller" if index <= 3 else "Standard Chiller", {"x": x - 48.0, "y": y - 34.0, "width": 96.0, "height": 14.0}, "#4c1d95", 7.4, page_ids))

    pump_xs = [plant_left + 185.0 + index * 138.0 for index in range(6)]
    for index, x in enumerate(pump_xs, start=1):
        _add_equipment_detail_train(objects, f"combined_chw_pump_detail_{index}", x, condenser_y, basin_y, y0 + 900.0, "CWR" if index > 3 else "CHWS", "P", styles, page_ids)
        objects.append(_overview_label(f"combined_chw_pump_tag_{index}", f"R-CHW-P-{index:02d}", {"x": x - 44.0, "y": y0 + 982.0, "width": 88.0, "height": 13.0}, "#075985", 7.0, page_ids))

    tower_xs = [tower_x - 35.0 + (index % 2) * 175.0 for index in range(4)]
    tower_ys = [y0 + 520.0 + (index // 2) * 150.0 for index in range(4)]
    for index, (x, y) in enumerate(zip(tower_xs, tower_ys), start=1):
        _add_equipment_detail_train(objects, f"combined_cw_tower_detail_{index}", x, condenser_y, basin_y, y, "CWS", "FIT", styles, page_ids)
        objects.append(_overview_label(f"combined_cw_tower_basin_{index}", "COOLING TOWER BASINS", {"x": x - 78.0, "y": y + 66.0, "width": 156.0, "height": 13.0}, "#0f766e", 6.8, page_ids))

    _add_vertical_instrument_ladder(objects, "combined_chw_riser_detail", riser_x + 44.0, top_y + 55.0, 9, 82.0, "CHWS", styles, page_ids, ["PDIT", "TIT", "FIT"])
    _add_offpage_callout_bank(objects, "combined_chw_building_callouts", riser_x + 1210.0, y0 + 380.0, 7, 86.0, "CHWS", "TO EQUIPMENT HVAC CHW COILS", styles, page_ids, "right")


def _add_hhw_detail_density(
    objects: list[DrawingObject],
    future: BoundsDict,
    boiler_x: float,
    pump_x: float,
    hx_x: float,
    supply_y: float,
    return_y: float,
    recovery_y: float,
    lower_y: float,
    y0: float,
    styles: dict[str, DrawingStyle],
    page_ids: list[str],
) -> None:
    for index in range(8):
        y = future["y"] + 145.0 + index * 145.0
        branch_x = future["x"] + 84.0
        objects.append(_overview_pipe(f"combined_hhw_future_branch_{index}", "", [{"x": branch_x, "y": y + 30.0}, {"x": future["x"] + future["width"] - 54.0, "y": y + 30.0}], "HHWS", styles, page_ids, 1.45))
        _add_valve_and_instrument_pair(objects, f"combined_hhw_future_pair_{index}", branch_x + 36.0, y + 30.0, "HHWS", styles, page_ids, "TIT" if index % 2 else "P")
        objects.append(_overview_label(f"combined_hhw_future_tag_{index}", f"R-HHW-HWB-{index + 1:02d}", {"x": future["x"] + 158.0, "y": y + 18.0, "width": 112.0, "height": 13.0}, "#991b1b", 7.0, page_ids))

    boiler_xs = [boiler_x + (index % 2) * 190.0 for index in range(4)]
    boiler_ys = [y0 + 365.0 + (index // 2) * 190.0 for index in range(4)]
    for index, (x, y) in enumerate(zip(boiler_xs, boiler_ys), start=1):
        _add_equipment_detail_train(objects, f"combined_hhw_boiler_detail_{index}", x, supply_y, return_y, y, "HHWS", "TIT", styles, page_ids)

    pump_xs = [pump_x - 120.0 + (index % 3) * 145.0 for index in range(6)]
    pump_ys = [y0 + 1290.0 + (index // 3) * 142.0 for index in range(6)]
    for index, (x, y) in enumerate(zip(pump_xs, pump_ys), start=1):
        _add_equipment_detail_train(objects, f"combined_hhw_pump_detail_{index}", x, return_y, lower_y, y, "HHWR", "P", styles, page_ids)
        objects.append(_overview_label(f"combined_hhw_pump_tag_{index}", f"R-HHW-P-{index:02d}", {"x": x - 44.0, "y": y + 72.0, "width": 88.0, "height": 13.0}, "#991b1b", 7.0, page_ids))

    for index in range(4):
        x = hx_x - 20.0 + (index % 2) * 165.0
        y = recovery_y + 72.0 + (index // 2) * 142.0
        _add_equipment_detail_train(objects, f"combined_hrw_hx_detail_{index}", x, recovery_y, lower_y - 235.0, y, "HRW", "FIT", styles, page_ids)

    objects.append(_overview_pipe("combined_hhw_natural_gas_header", "NATURAL GAS", [{"x": boiler_x - 95.0, "y": y0 + 205.0}, {"x": boiler_x + 565.0, "y": y0 + 205.0}], "GAS", styles, page_ids, 1.8))
    _add_offpage_callout_bank(objects, "combined_hhw_building_callouts", hx_x + 1090.0, y0 + 520.0, 6, 98.0, "HHWS", "FROM / TO ANNEX HHW DISTRIBUTION", styles, page_ids, "right")


def _add_equipment_detail_train(
    objects: list[DrawingObject],
    id_seed: str,
    x: float,
    upper_y: float,
    lower_y: float,
    equipment_y: float,
    system: str,
    instrument_label: str,
    styles: dict[str, DrawingStyle],
    page_ids: list[str],
) -> None:
    objects.append(_overview_pipe(f"{id_seed}_upper_drop", "", [{"x": x, "y": upper_y}, {"x": x, "y": equipment_y - 8.0}], system, styles, page_ids, 1.1))
    objects.append(_overview_pipe(f"{id_seed}_lower_return", "", [{"x": x + 34.0, "y": equipment_y + 68.0}, {"x": x + 34.0, "y": lower_y}], system, styles, page_ids, 1.1))
    _add_valve_and_instrument_pair(objects, f"{id_seed}_upper", x, upper_y + (equipment_y - upper_y) * 0.45, system, styles, page_ids, instrument_label)
    _add_valve_and_instrument_pair(objects, f"{id_seed}_lower", x + 34.0, equipment_y + (lower_y - equipment_y) * 0.42, system, styles, page_ids, "P")


def _add_valve_and_instrument_pair(
    objects: list[DrawingObject],
    id_seed: str,
    x: float,
    y: float,
    system: str,
    styles: dict[str, DrawingStyle],
    page_ids: list[str],
    label: str,
) -> None:
    stroke = SYSTEM_COLORS.get(system, "#334155")
    objects.append(_overview_symbol(f"{id_seed}_valve", "", {"x": x - 9.0, "y": y - 9.0, "width": 18.0, "height": 18.0}, stroke, page_ids, "valve", metadata={"orientation": "vertical"}))
    objects.append(_overview_symbol(f"{id_seed}_instrument", "", {"x": x + 18.0, "y": y - 13.0, "width": 26.0, "height": 26.0}, stroke, page_ids, "instrument"))
    objects.append(_overview_label(f"{id_seed}_instrument_label", label, {"x": x + 23.0, "y": y - 6.0, "width": 26.0, "height": 11.0}, stroke, 5.8, page_ids))


def _add_vertical_instrument_ladder(
    objects: list[DrawingObject],
    id_seed: str,
    x: float,
    start_y: float,
    count: int,
    gap: float,
    system: str,
    styles: dict[str, DrawingStyle],
    page_ids: list[str],
    labels: list[str],
) -> None:
    for index in range(count):
        _add_valve_and_instrument_pair(objects, f"{id_seed}_{index}", x, start_y + index * gap, system, styles, page_ids, labels[index % len(labels)])


def _add_offpage_callout_bank(
    objects: list[DrawingObject],
    id_seed: str,
    x: float,
    y: float,
    count: int,
    gap: float,
    system: str,
    label: str,
    styles: dict[str, DrawingStyle],
    page_ids: list[str],
    orientation: Literal["left", "right"],
) -> None:
    for index in range(count):
        target_y = y + index * gap
        if orientation == "right":
            objects.append(_overview_pipe(f"{id_seed}_lead_{index}", "", [{"x": x - 190.0, "y": target_y}, {"x": x - 34.0, "y": target_y}], system, styles, page_ids, 1.25))
            symbol_bounds = {"x": x - 42.0, "y": target_y - 14.0, "width": 58.0, "height": 28.0}
            label_bounds = {"x": x + 24.0, "y": target_y - 8.0, "width": 250.0, "height": 18.0}
            symbol_orientation = "right"
        else:
            objects.append(_overview_pipe(f"{id_seed}_lead_{index}", "", [{"x": x + 34.0, "y": target_y}, {"x": x + 190.0, "y": target_y}], system, styles, page_ids, 1.25))
            symbol_bounds = {"x": x - 16.0, "y": target_y - 14.0, "width": 58.0, "height": 28.0}
            label_bounds = {"x": x - 274.0, "y": target_y - 8.0, "width": 250.0, "height": 18.0}
            symbol_orientation = "left"
        objects.append(_overview_symbol(f"{id_seed}_offpage_{index}", "", symbol_bounds, "#111827", page_ids, "offpage", metadata={"orientation": symbol_orientation}))
        objects.append(_overview_label(f"{id_seed}_label_{index}", f"{label} {index + 1}", label_bounds, "#111827", 7.4, page_ids))


def _pick_equipment(equipment: list[str], keywords: list[str], fallbacks: list[str], limit: int) -> list[str]:
    picked = _equipment_by_keywords(equipment, keywords)
    if not picked and keywords:
        picked = equipment[:limit]
    for fallback in fallbacks:
        if fallback not in picked:
            picked.append(fallback)
        if len(picked) >= limit:
            break
    return picked[:limit]


def _source_graph_equipment(source_graph: PidSourceGraph | None, assembly_kind: str) -> list[str]:
    if source_graph is None:
        return []
    for assembly in source_graph.assemblies:
        if assembly.kind == assembly_kind:
            return assembly.equipmentTags
    return []


def _mark_route_polish(obj: DrawingObject, role: str) -> None:
    obj.metadata.update({"sourceGeneratedRoutingPolish": True, "routeRole": role, "sourceGenerated": True})


def _add_valve_station(
    objects: list[DrawingObject],
    id_seed: str,
    x: float,
    y: float,
    system: str,
    styles: dict[str, DrawingStyle],
    evidence_ids: list[str],
    count: int,
    gap: float,
) -> None:
    stroke = SYSTEM_COLORS.get(system, "#334155")
    for index in range(count):
        target_y = y + index * gap
        objects.append(
            _overview_symbol(
                f"{id_seed}_valve_{index}",
                "",
                {"x": x - 11.0, "y": target_y - 11.0, "width": 22.0, "height": 22.0},
                stroke,
                evidence_ids,
                "valve",
                metadata={"orientation": "vertical"},
            )
        )
        if index % 2 == 0:
            objects.append(
                _overview_symbol(
                    f"{id_seed}_instrument_{index}",
                    "",
                    {"x": x + 24.0, "y": target_y - 15.0, "width": 30.0, "height": 30.0},
                    stroke,
                    evidence_ids,
                    "instrument",
                )
            )
        if index < count - 1:
            objects.append(
                _overview_pipe(
                    f"{id_seed}_spool_{index}",
                    "",
                    [{"x": x, "y": target_y + 14.0}, {"x": x, "y": target_y + gap - 14.0}],
                    system,
                    styles,
                    evidence_ids,
                    1.2,
                )
            )


def _add_edge_continuation_stack(
    objects: list[DrawingObject],
    id_seed: str,
    candidates: list[ContinuationCandidate],
    styles: dict[str, DrawingStyle],
    fallback_system: str,
    page_ids: list[str],
    x: float,
    y: float,
    row_gap: float,
    limit: int,
    orientation: Literal["left", "right"],
    legacy_label_prefix: bool = True,
) -> None:
    continuations = _overview_continuations_for_group(candidates, _group_for_system(fallback_system))
    if not continuations:
        continuations = candidates
    for index, candidate in enumerate(continuations[:limit]):
        target_y = y + index * row_gap
        system = candidate.system or _system_for_tag(candidate.lineTag or candidate.label, _group_for_system(fallback_system)) or fallback_system
        evidence_ids = [candidate.id] if candidate.id else page_ids
        if orientation == "left":
            pipe_points = [{"x": x + 28.0, "y": target_y}, {"x": x + 170.0, "y": target_y}]
            symbol_bounds = {"x": x - 14.0, "y": target_y - 15.0, "width": 56.0, "height": 30.0}
            label_bounds = {"x": max(20.0, x + 184.0), "y": target_y - 9.0, "width": 230.0, "height": 20.0}
            symbol_orientation = "left"
        else:
            pipe_points = [{"x": x - 170.0, "y": target_y}, {"x": x - 28.0, "y": target_y}]
            symbol_bounds = {"x": x - 42.0, "y": target_y - 15.0, "width": 56.0, "height": 30.0}
            label_width = min(245.0, max(120.0, x - 206.0))
            label_bounds = {"x": x - label_width - 56.0, "y": target_y - 27.0, "width": label_width, "height": 18.0}
            symbol_orientation = "right"
        pipe = _overview_pipe(f"{id_seed}_continuation_pipe_{index}", "", pipe_points, system, styles, evidence_ids, 1.7)
        pipe.metadata.update({"sourceCandidateId": candidate.id, "lineTag": candidate.lineTag, "sheetRef": candidate.sheetRef, "edgeContinuation": True})
        objects.append(pipe)
        symbol = _overview_symbol(
            f"{id_seed}_continuation_offpage_{index}",
            "",
            symbol_bounds,
            "#111827",
            evidence_ids,
            "offpage",
            metadata={
                "orientation": symbol_orientation,
                "sourceCandidateId": candidate.id,
                "lineTag": candidate.lineTag,
                "sheetRef": candidate.sheetRef,
                "edgeContinuation": True,
            },
        )
        objects.append(symbol)
        label_seed = f"continuation_label_{id_seed}_{index}" if legacy_label_prefix else f"{id_seed}_label_{index}"
        label = _overview_label(label_seed, _continuation_label(candidate), label_bounds, "#111827", 8.8, evidence_ids)
        label.metadata.update({"sourceCandidateId": candidate.id, "lineTag": candidate.lineTag, "sheetRef": candidate.sheetRef, "edgeContinuation": True})
        objects.append(label)


def _group_for_system(system: str) -> str:
    system = system.upper()
    if "CDA" in system:
        return "CDA"
    if "HHW" in system or "HRW" in system or system in {"HWS", "HWR"}:
        return "HHW / HRW"
    if "CHW" in system or system in {"CWS", "CWR"}:
        return "CHW / CW"
    return "OTHER"


def _add_reference_title_block(
    objects: list[DrawingObject],
    pages: list[PageEvidence],
    source_paths: dict[str, str],
    document_width: float = _OVERVIEW_WIDTH,
) -> None:
    source_ids = [page.id for page in pages]
    bounds = {"x": document_width - 620.0, "y": 48.0, "width": 410.0, "height": 116.0}
    objects.append(_overview_region("combined_title_block", "", bounds, "#475569", "#ffffff", 0.82, source_ids))
    row_ys = [bounds["y"] + 28.0, bounds["y"] + 56.0, bounds["y"] + 84.0]
    for index, y in enumerate(row_ys):
        objects.append(
            _overview_pipe(
                f"combined_title_block_row_{index}",
                "",
                [{"x": bounds["x"], "y": y}, {"x": bounds["x"] + bounds["width"], "y": y}],
                "DEFAULT",
                _styles(),
                source_ids,
                0.7,
            )
        )
    for index, x in enumerate([bounds["x"] + 78.0, bounds["x"] + 242.0, bounds["x"] + 330.0]):
        objects.append(
            _overview_pipe(
                f"combined_title_block_col_{index}",
                "",
                [{"x": x, "y": bounds["y"]}, {"x": x, "y": bounds["y"] + bounds["height"]}],
                "DEFAULT",
                _styles(),
                source_ids,
                0.7,
            )
        )
    objects.append(_overview_label("combined_title_block_name", "RECREATION", {"x": bounds["x"] + 254.0, "y": bounds["y"] + 18.0, "width": 145.0, "height": 18.0}, "#0f172a", 12.0, source_ids))
    objects.append(_overview_label("combined_title_block_drawing", "COMBINED P&ID SYSTEM OVERVIEW", {"x": bounds["x"] + 12.0, "y": bounds["y"] + 38.0, "width": 220.0, "height": 16.0}, "#0f172a", 8.5, source_ids))
    objects.append(_overview_label("combined_title_block_sources", f"{len(source_paths) or len(pages)} SOURCE SHEETS", {"x": bounds["x"] + 12.0, "y": bounds["y"] + 66.0, "width": 190.0, "height": 16.0}, "#475569", 8.5, source_ids))
    objects.append(_overview_label("combined_title_block_rev", "REV A", {"x": bounds["x"] + 342.0, "y": bounds["y"] + 68.0, "width": 58.0, "height": 16.0}, "#0f172a", 9.5, source_ids))
    objects.append(_overview_label("combined_title_block_status", "DRAFT", {"x": bounds["x"] + 342.0, "y": bounds["y"] + 96.0, "width": 58.0, "height": 16.0}, "#0f172a", 9.5, source_ids))
    for index, (system, color) in enumerate([("CHW", "#2563eb"), ("CW", "#16a34a"), ("HHW", "#dc2626"), ("HRW", "#334155")]):
        swatch = {"x": bounds["x"] + 88.0 + index * 36.0, "y": bounds["y"] + 92.0, "width": 28.0, "height": 10.0}
        objects.append(_overview_region(f"combined_title_block_swatch_{system}", "", swatch, color, color, 0.95, source_ids))
        objects.append(_overview_label(f"combined_title_block_swatch_label_{system}", system, {"x": swatch["x"], "y": swatch["y"] + 12.0, "width": 32.0, "height": 10.0}, "#334155", 6.5, source_ids))


def _add_overview_detail_boxes(
    objects: list[DrawingObject],
    cda_bounds: BoundsDict,
    chw_bounds: BoundsDict,
    hhw_bounds: BoundsDict,
    dist_bounds: BoundsDict,
    group_map: dict[str, list[PageEvidence]],
    source_ids: list[str],
) -> None:
    detail_boxes: list[tuple[str, str, BoundsDict, str, str, list[str]]] = [
        (
            "cda_generation",
            "COMPRESSORS / DRYERS",
            {"x": cda_bounds["x"] + 84.0, "y": cda_bounds["y"] + 112.0, "width": 520.0, "height": 286.0},
            "#7c3aed",
            "#ffffff",
            _page_ids(group_map.get("CDA", [])),
        ),
        (
            "cda_receivers",
            "RECEIVERS / FILTRATION",
            {"x": cda_bounds["x"] + 650.0, "y": cda_bounds["y"] + 132.0, "width": 530.0, "height": 250.0},
            "#7c3aed",
            "#ffffff",
            _page_ids(group_map.get("CDA", [])),
        ),
        (
            "chw_chiller_bank",
            "CHILLER BANK",
            {"x": chw_bounds["x"] + 170.0, "y": chw_bounds["y"] + 105.0, "width": 920.0, "height": 410.0},
            "#7c3aed",
            "#f5f3ff",
            _page_ids(group_map.get("CHW / CW", [])),
        ),
        (
            "chw_pump_bank",
            "PUMP / HX SKIDS",
            {"x": chw_bounds["x"] + 165.0, "y": chw_bounds["y"] + 790.0, "width": 850.0, "height": 310.0},
            "#2563eb",
            "#eff6ff",
            _page_ids(group_map.get("CHW / CW", [])),
        ),
        (
            "cw_towers",
            "COOLING WATER",
            {"x": chw_bounds["x"] + 1415.0, "y": chw_bounds["y"] + 285.0, "width": 475.0, "height": 410.0},
            "#0284c7",
            "#ecfeff",
            _page_ids(group_map.get("CHW / CW", [])),
        ),
        (
            "hhw_future",
            "FUTURE",
            {"x": hhw_bounds["x"] + 58.0, "y": hhw_bounds["y"] + 95.0, "width": 382.0, "height": 1565.0},
            "#ef4444",
            "#fff7ed",
            _page_ids(group_map.get("HHW / HRW", [])),
        ),
        (
            "hhw_boiler_bank",
            "BOILER PLANT",
            {"x": hhw_bounds["x"] + 520.0, "y": hhw_bounds["y"] + 245.0, "width": 520.0, "height": 590.0},
            "#ef4444",
            "#fff1f2",
            _page_ids(group_map.get("HHW / HRW", [])),
        ),
        (
            "hrw_recovery",
            "HEAT RECOVERY",
            {"x": hhw_bounds["x"] + 835.0, "y": hhw_bounds["y"] + 905.0, "width": 500.0, "height": 540.0},
            "#334155",
            "#f8fafc",
            _page_ids(group_map.get("HHW / HRW", [])),
        ),
        (
            "site_tie_ins",
            "TO / FROM BUILDING",
            {"x": dist_bounds["x"] + 58.0, "y": dist_bounds["y"] + 58.0, "width": 280.0, "height": 1050.0},
            "#64748b",
            "#ffffff",
            source_ids,
        ),
    ]
    for id_seed, label, bounds, stroke, fill, evidence_ids in detail_boxes:
        objects.append(_overview_region(f"combined_detail_{id_seed}", "", bounds, stroke, fill, 0.28, evidence_ids or source_ids))
        objects.append(
            _overview_label(
                f"combined_detail_label_{id_seed}",
                label,
                {"x": bounds["x"] + 14.0, "y": bounds["y"] + 12.0, "width": min(230.0, bounds["width"] - 28.0), "height": 16.0},
                stroke,
                8.6,
                evidence_ids or source_ids,
            )
        )


def _add_system_compiled_detail_boxes(
    objects: list[DrawingObject],
    slug: str,
    group_name: str,
    plant_bounds: BoundsDict,
    distribution_bounds: BoundsDict,
    source_ids: list[str],
) -> None:
    if group_name == "CHW / CW":
        boxes: list[tuple[str, str, BoundsDict, str, str]] = [
            ("chiller_bank", "CHILLER BANK", {"x": plant_bounds["x"] + 145.0, "y": plant_bounds["y"] + 95.0, "width": 1040.0, "height": 430.0}, "#7c3aed", "#f5f3ff"),
            ("chw_pumps", "CHW PUMPS", {"x": plant_bounds["x"] + 125.0, "y": plant_bounds["y"] + 760.0, "width": 940.0, "height": 360.0}, "#2563eb", "#eff6ff"),
            ("cw_towers", "COOLING WATER", {"x": plant_bounds["x"] + 1410.0, "y": plant_bounds["y"] + 245.0, "width": 560.0, "height": 520.0}, "#0284c7", "#ecfeff"),
            ("controls", "CONTROL / METERING", {"x": plant_bounds["x"] + 110.0, "y": plant_bounds["y"] + 1220.0, "width": 1040.0, "height": 360.0}, "#64748b", "#ffffff"),
            ("distribution", "TO / FROM BUILDING", {"x": distribution_bounds["x"] + 55.0, "y": distribution_bounds["y"] + 70.0, "width": 405.0, "height": 1260.0}, "#0284c7", "#ffffff"),
        ]
    else:
        boxes = [
            ("future", "FUTURE", {"x": plant_bounds["x"] + 65.0, "y": plant_bounds["y"] + 100.0, "width": 410.0, "height": 1645.0}, "#ef4444", "#fff7ed"),
            ("boilers", "BOILER PLANT", {"x": plant_bounds["x"] + 565.0, "y": plant_bounds["y"] + 220.0, "width": 620.0, "height": 650.0}, "#ef4444", "#fff1f2"),
            ("hrw", "HEAT RECOVERY", {"x": plant_bounds["x"] + 920.0, "y": plant_bounds["y"] + 910.0, "width": 610.0, "height": 590.0}, "#334155", "#f8fafc"),
            ("pumps", "PUMP SKIDS", {"x": plant_bounds["x"] + 560.0, "y": plant_bounds["y"] + 1450.0, "width": 780.0, "height": 360.0}, "#f97316", "#fff7ed"),
            ("distribution", "TO / FROM BUILDING", {"x": distribution_bounds["x"] + 55.0, "y": distribution_bounds["y"] + 70.0, "width": 405.0, "height": 1260.0}, "#f97316", "#ffffff"),
        ]

    for id_seed, label, bounds, stroke, fill in boxes:
        objects.append(_overview_region(f"{slug}_detail_{id_seed}", "", bounds, stroke, fill, 0.16, source_ids))
        objects.append(
            _overview_label(
                f"{slug}_detail_label_{id_seed}",
                label,
                {"x": bounds["x"] + 14.0, "y": bounds["y"] + 12.0, "width": min(235.0, bounds["width"] - 28.0), "height": 16.0},
                stroke,
                8.6,
                source_ids,
            )
        )


def _add_source_generated_chw_cw_detail_boxes(
    objects: list[DrawingObject],
    slug: str,
    source_graph: PidSourceGraph,
    plant_bounds: BoundsDict,
    distribution_bounds: BoundsDict,
) -> None:
    assembly_by_kind = {assembly.kind: assembly for assembly in source_graph.assemblies}

    def assembly_size(kind: str, fallback: int) -> int:
        assembly = assembly_by_kind.get(kind)
        return max(fallback, len(assembly.equipmentTags) if assembly else 0)

    boxes: list[tuple[str, str, BoundsDict, str, str]] = [
        (
            "chiller_bank",
            "CHILLER BANK",
            {
                "x": plant_bounds["x"] + 145.0,
                "y": plant_bounds["y"] + 92.0,
                "width": min(1080.0, 260.0 + assembly_size("chiller_bank", 3) * 172.0),
                "height": 410.0,
            },
            "#7c3aed",
            "#f5f3ff",
        ),
        (
            "chw_pumps",
            "CHW PUMPS",
            {
                "x": plant_bounds["x"] + 130.0,
                "y": plant_bounds["y"] + 735.0,
                "width": min(920.0, 255.0 + assembly_size("chw_pumps", 3) * 118.0),
                "height": 325.0,
            },
            "#2563eb",
            "#eff6ff",
        ),
        (
            "cw_pumps",
            "CW PUMPS",
            {
                "x": plant_bounds["x"] + 540.0,
                "y": plant_bounds["y"] + 735.0,
                "width": min(800.0, 245.0 + assembly_size("cw_pumps", 2) * 120.0),
                "height": 325.0,
            },
            "#0f766e",
            "#ecfdf5",
        ),
        (
            "cooling_water",
            "COOLING WATER",
            {
                "x": plant_bounds["x"] + 1420.0,
                "y": plant_bounds["y"] + 225.0,
                "width": min(640.0, 285.0 + assembly_size("cooling_water", 2) * 124.0),
                "height": 560.0,
            },
            "#0284c7",
            "#ecfeff",
        ),
        (
            "distribution",
            "TO / FROM BUILDING",
            {
                "x": distribution_bounds["x"] + 55.0,
                "y": distribution_bounds["y"] + 66.0,
                "width": 438.0,
                "height": 1320.0,
            },
            "#0284c7",
            "#ffffff",
        ),
    ]
    for id_seed, label, bounds, stroke, fill in boxes:
        region = _overview_region(f"{slug}_detail_{id_seed}", "", bounds, stroke, fill, 0.18, source_graph.sourcePageIds)
        region.metadata.update({"sourceGeneratedDetailBox": id_seed, "sourceGenerated": True, "hideCenterLabel": True})
        objects.append(region)
        text = _overview_label(
            f"{slug}_detail_label_{id_seed}",
            label,
            {"x": bounds["x"] + 14.0, "y": bounds["y"] + 12.0, "width": min(235.0, bounds["width"] - 28.0), "height": 16.0},
            stroke,
            8.6,
            source_graph.sourcePageIds,
        )
        text.metadata.update({"sourceGeneratedDetailBox": id_seed, "sourceGenerated": True})
        objects.append(text)


def _add_source_generated_hhw_hrw_detail_boxes(
    objects: list[DrawingObject],
    slug: str,
    source_graph: PidSourceGraph,
    plant_bounds: BoundsDict,
    distribution_bounds: BoundsDict,
) -> None:
    assembly_by_kind = {assembly.kind: assembly for assembly in source_graph.assemblies}

    def assembly_size(kind: str, fallback: int) -> int:
        assembly = assembly_by_kind.get(kind)
        return max(fallback, len(assembly.equipmentTags) if assembly else 0)

    boxes: list[tuple[str, str, BoundsDict, str, str]] = [
        (
            "hhw_boilers",
            "HHW BOILER PLANT",
            {
                "x": plant_bounds["x"] + 515.0,
                "y": plant_bounds["y"] + 210.0,
                "width": min(760.0, 340.0 + assembly_size("hhw_boilers", 2) * 115.0),
                "height": 650.0,
            },
            "#ef4444",
            "#fff1f2",
        ),
        (
            "hhw_pumps",
            "HHW PUMP SKIDS",
            {
                "x": plant_bounds["x"] + 520.0,
                "y": plant_bounds["y"] + 1380.0,
                "width": min(820.0, 320.0 + assembly_size("hhw_pumps", 2) * 118.0),
                "height": 380.0,
            },
            "#f97316",
            "#fff7ed",
        ),
        (
            "hrw_recovery",
            "HEAT RECOVERY",
            {
                "x": plant_bounds["x"] + 920.0,
                "y": plant_bounds["y"] + 880.0,
                "width": min(680.0, 320.0 + assembly_size("hrw_recovery", 2) * 124.0),
                "height": 590.0,
            },
            "#334155",
            "#f8fafc",
        ),
        (
            "future_capacity",
            "FUTURE / BYPASS",
            {
                "x": plant_bounds["x"] + 65.0,
                "y": plant_bounds["y"] + 96.0,
                "width": 430.0,
                "height": 1645.0,
            },
            "#dc2626",
            "#fff7ed",
        ),
        (
            "distribution",
            "TO / FROM BUILDING",
            {
                "x": distribution_bounds["x"] + 55.0,
                "y": distribution_bounds["y"] + 66.0,
                "width": 450.0,
                "height": 1320.0,
            },
            "#f97316",
            "#ffffff",
        ),
    ]
    for id_seed, label, bounds, stroke, fill in boxes:
        region = _overview_region(f"{slug}_detail_{id_seed}", "", bounds, stroke, fill, 0.18, source_graph.sourcePageIds)
        region.metadata.update({"sourceGeneratedDetailBox": id_seed, "sourceGenerated": True, "hideCenterLabel": True})
        objects.append(region)
        text = _overview_label(
            f"{slug}_detail_label_{id_seed}",
            label,
            {"x": bounds["x"] + 14.0, "y": bounds["y"] + 12.0, "width": min(250.0, bounds["width"] - 28.0), "height": 16.0},
            stroke,
            8.6,
            source_graph.sourcePageIds,
        )
        text.metadata.update({"sourceGeneratedDetailBox": id_seed, "sourceGenerated": True})
        objects.append(text)


def _add_source_derived_linework(
    objects: list[DrawingObject],
    slug: str,
    group_name: str,
    pages: list[PageEvidence],
    plant_bounds: BoundsDict,
    distribution_bounds: BoundsDict,
    source_ids: list[str],
    limit_per_page: int = 112,
    opacity: float = 0.42,
) -> None:
    tiles = _compiled_source_vector_tiles(group_name, plant_bounds, distribution_bounds)
    if not tiles:
        return

    for page_index, page in enumerate(_sorted_pages(pages)):
        vectors = _select_source_vectors(page, limit=limit_per_page)
        if not vectors:
            continue
        source_bounds = _union_vector_bounds(vectors)
        tile_name, tile_bounds = tiles[page_index % len(tiles)]
        for vector_index, vector in enumerate(vectors):
            points = _map_source_vector_points(vector, source_bounds, tile_bounds)
            if len(points) < 2:
                continue
            stroke = _source_vector_stroke(vector)
            stroke_width = max(0.48, min(1.15, (vector.strokeWidth or 0.85) * 0.76))
            objects.append(
                DrawingObject(
                    id=_object_id("source_vector_pipe", slug, tile_name, page.id, vector.id, vector_index),
                    kind="pipe",
                    label="",
                    points=points,
                    bounds=_points_bounds(points, 3.0),
                    style=DrawingStyle(
                        stroke=stroke,
                        fill="none",
                        strokeWidth=stroke_width,
                        opacity=opacity,
                        dash=[4.0, 3.0] if vector.dashed else None,
                    ),
                    sourceEvidenceIds=[page.id, vector.id] if vector.id else source_ids,
                    locked=False,
                    groupId=_object_id("source_vector_group", slug, tile_name, page.id),
                    metadata={
                        "overview": True,
                        "sourceDerived": True,
                        "sourceVectorId": vector.id,
                        "sourcePageId": page.id,
                        "sourceTile": tile_name,
                    },
                )
            )


def _compiled_source_vector_tiles(
    group_name: str,
    plant_bounds: BoundsDict,
    distribution_bounds: BoundsDict,
) -> list[tuple[str, BoundsDict]]:
    if group_name == "CHW / CW":
        return [
            ("chiller_bank", {"x": plant_bounds["x"] + 170.0, "y": plant_bounds["y"] + 128.0, "width": 980.0, "height": 365.0}),
            ("chw_pumps", {"x": plant_bounds["x"] + 152.0, "y": plant_bounds["y"] + 790.0, "width": 880.0, "height": 292.0}),
            ("cw_towers", {"x": plant_bounds["x"] + 1438.0, "y": plant_bounds["y"] + 282.0, "width": 502.0, "height": 442.0}),
            ("controls", {"x": plant_bounds["x"] + 144.0, "y": plant_bounds["y"] + 1258.0, "width": 970.0, "height": 292.0}),
            ("distribution", {"x": distribution_bounds["x"] + 76.0, "y": distribution_bounds["y"] + 112.0, "width": 356.0, "height": 1160.0}),
        ]
    return [
        ("future", {"x": plant_bounds["x"] + 92.0, "y": plant_bounds["y"] + 138.0, "width": 354.0, "height": 1542.0}),
        ("boilers", {"x": plant_bounds["x"] + 600.0, "y": plant_bounds["y"] + 258.0, "width": 552.0, "height": 570.0}),
        ("hrw", {"x": plant_bounds["x"] + 958.0, "y": plant_bounds["y"] + 948.0, "width": 536.0, "height": 510.0}),
        ("pumps", {"x": plant_bounds["x"] + 594.0, "y": plant_bounds["y"] + 1484.0, "width": 712.0, "height": 292.0}),
        ("distribution", {"x": distribution_bounds["x"] + 76.0, "y": distribution_bounds["y"] + 112.0, "width": 356.0, "height": 1160.0}),
    ]


def _select_source_vectors(page: PageEvidence, limit: int) -> list[VectorSegment]:
    crop = page.cropBounds
    candidates: list[tuple[float, VectorSegment]] = []
    for vector in page.vectorSegments:
        if not _source_vector_is_usable(vector, crop):
            continue
        length = _polyline_length(vector.points)
        candidates.append((length, vector))

    candidates.sort(key=lambda item: (-item[0], item[1].id))
    large = [vector for _length, vector in candidates[: max(16, limit // 2)]]
    medium = [vector for _length, vector in candidates[max(16, limit // 2) : limit]]
    return large + medium


def _source_vector_is_usable(vector: VectorSegment, crop: BoundsDict) -> bool:
    if vector.kind not in {"line", "polyline", "rect", "curve"}:
        return False
    if len(vector.points) > 8:
        return False

    bounds = vector.bounds
    crop_width = max(1.0, crop["width"])
    crop_height = max(1.0, crop["height"])
    if bounds["width"] > crop_width * 0.78 or bounds["height"] > crop_height * 0.78:
        return False
    if _inside_likely_title_block(bounds, crop):
        return False

    length = _polyline_length(vector.points)
    min_length = max(10.0, min(crop_width, crop_height) * 0.006)
    max_length = max(crop_width, crop_height) * 0.42
    if length < min_length or length > max_length:
        return False
    if _source_vector_is_hairline_artifact(vector, crop):
        return False
    return _mostly_orthogonal(vector.points) or vector.kind in {"rect", "curve"}


def _inside_likely_title_block(bounds: BoundsDict, crop: BoundsDict) -> bool:
    return (
        bounds["x"] > crop["x"] + crop["width"] * 0.64
        and bounds["y"] > crop["y"] + crop["height"] * 0.68
        and bounds["width"] < crop["width"] * 0.34
        and bounds["height"] < crop["height"] * 0.28
    )


def _source_vector_is_hairline_artifact(vector: VectorSegment, crop: BoundsDict) -> bool:
    if vector.kind != "line" or len(vector.points) != 2:
        return False
    bounds = vector.bounds
    length = _polyline_length(vector.points)
    short_length = max(32.0, min(crop["width"], crop["height"]) * 0.018)
    if length >= short_length:
        return False
    return min(bounds["width"], bounds["height"]) <= 1.0


def _union_vector_bounds(vectors: list[VectorSegment]) -> BoundsDict:
    x0 = min(vector.bounds["x"] for vector in vectors)
    y0 = min(vector.bounds["y"] for vector in vectors)
    x1 = max(vector.bounds["x"] + vector.bounds["width"] for vector in vectors)
    y1 = max(vector.bounds["y"] + vector.bounds["height"] for vector in vectors)
    pad_x = max(20.0, (x1 - x0) * 0.04)
    pad_y = max(20.0, (y1 - y0) * 0.04)
    return {"x": x0 - pad_x, "y": y0 - pad_y, "width": x1 - x0 + pad_x * 2.0, "height": y1 - y0 + pad_y * 2.0}


def _map_source_vector_points(vector: VectorSegment, source_bounds: BoundsDict, tile: BoundsDict) -> list[Point]:
    padding = 18.0
    usable_width = max(1.0, tile["width"] - padding * 2.0)
    usable_height = max(1.0, tile["height"] - padding * 2.0)
    scale = min(usable_width / max(1.0, source_bounds["width"]), usable_height / max(1.0, source_bounds["height"]))
    scaled_width = source_bounds["width"] * scale
    scaled_height = source_bounds["height"] * scale
    offset_x = tile["x"] + (tile["width"] - scaled_width) / 2.0
    offset_y = tile["y"] + (tile["height"] - scaled_height) / 2.0
    return [
        {
            "x": offset_x + (point["x"] - source_bounds["x"]) * scale,
            "y": offset_y + (point["y"] - source_bounds["y"]) * scale,
        }
        for point in vector.points
    ]


def _source_vector_stroke(vector: VectorSegment) -> str:
    stroke = (vector.stroke or "").lower()
    if stroke in {"#ef4444", "#dc2626", "#ff0000"}:
        return "#b91c1c"
    if stroke.startswith("#") and stroke not in {"#000000", "#111827", "#ffffff", "#fefefe", "#fff"}:
        return stroke
    return "#64748b"


def _polyline_length(points: list[Point]) -> float:
    return sum(((b["x"] - a["x"]) ** 2 + (b["y"] - a["y"]) ** 2) ** 0.5 for a, b in zip(points, points[1:]))


def _mostly_orthogonal(points: list[Point]) -> bool:
    segments = list(zip(points, points[1:]))
    if not segments:
        return False
    orthogonal = 0
    for start, end in segments:
        dx = abs(end["x"] - start["x"])
        dy = abs(end["y"] - start["y"])
        if dx < 1.0 or dy < 1.0 or min(dx, dy) / max(dx, dy) <= 0.08:
            orthogonal += 1
    return orthogonal / len(segments) >= 0.72


def _source_vector_object_count(objects: list[DrawingObject]) -> int:
    return sum(1 for obj in objects if obj.metadata.get("sourceDerived") is True)


def _template_object_count(objects: list[DrawingObject]) -> int:
    return sum(1 for obj in objects if obj.metadata.get("templateDerived") is True)


def _source_trace_object_count(objects: list[DrawingObject]) -> int:
    return sum(1 for obj in objects if obj.metadata.get("traceOverlay") is True)


def _add_source_to_template_trace_overlay(
    objects: list[DrawingObject],
    slug: str,
    group_name: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    source_paths: dict[str, str],
    document_width: float,
    document_height: float,
) -> None:
    page_by_key = {(page.sourceFileId, page.page): page for page in pages}
    trace_candidates = [
        candidate
        for candidate in _meaningful_continuation_candidates(candidates, pages, source_paths, group_name)
        if (candidate.sourceFileId, candidate.page) in page_by_key
    ][:6]
    if not trace_candidates:
        return

    source_ids = _page_ids(pages)
    strip_x = max(42.0, min(132.0, document_width * 0.04))
    strip_top = max(250.0, document_height * 0.15)
    card_width = min(430.0, max(300.0, document_width * 0.12))
    card_height = min(185.0, max(126.0, document_height * 0.068))
    row_gap = max(card_height + 42.0, document_height * 0.09)
    target_x = min(document_width - 520.0, max(strip_x + card_width + 620.0, document_width * 0.62))
    trace_color = "#0f766e"

    header = _overview_label(
        f"{slug}_trace_header",
        "SOURCE CALLOUT TRACE",
        {"x": strip_x, "y": strip_top - 58.0, "width": 410.0, "height": 22.0},
        trace_color,
        13.0,
        source_ids,
    )
    header.metadata.update({"traceOverlay": True, "explainability": True})
    objects.append(header)

    target_header = _overview_label(
        f"{slug}_trace_target_header",
        "GENERATED TEMPLATE CONNECTIONS",
        {"x": target_x - 18.0, "y": strip_top - 58.0, "width": 430.0, "height": 22.0},
        trace_color,
        13.0,
        source_ids,
    )
    target_header.metadata.update({"traceOverlay": True, "explainability": True})
    objects.append(target_header)

    for index, candidate in enumerate(trace_candidates):
        page = page_by_key[(candidate.sourceFileId, candidate.page)]
        row_y = strip_top + index * row_gap
        if row_y + card_height > document_height - 120.0:
            break

        crop_bounds = _trace_crop_bounds(candidate, page)
        source_bounds = {"x": strip_x, "y": row_y, "width": card_width, "height": card_height}
        source_metadata: dict[str, Any] = {
            "sourceFileId": page.sourceFileId,
            "page": page.page,
            "cropBounds": crop_bounds,
            "traceOverlay": True,
            "traceRole": "source_callout",
            "sourceCandidateId": candidate.id,
            "edge": candidate.edge,
            "lineTag": candidate.lineTag,
            "sheetRef": candidate.sheetRef,
        }
        if page.sourceFileId in source_paths:
            source_metadata["sourcePath"] = source_paths[page.sourceFileId]
        objects.append(
            DrawingObject(
                id=_object_id("source_trace_fragment", slug, candidate.id, index),
                kind="source_fragment",
                label=_continuation_label(candidate),
                points=_rect_points(source_bounds),
                bounds=source_bounds,
                style=DrawingStyle(stroke=trace_color, fill="none", strokeWidth=1.2, opacity=1.0, dash=[8.0, 4.0]),
                sourceEvidenceIds=[page.id, candidate.id],
                locked=False,
                metadata=source_metadata,
            )
        )

        source_label = _overview_label(
            f"{slug}_trace_source_label_{index}",
            f"{_source_sheet_ref_for_page(page, source_paths)} / {_continuation_label(candidate)}",
            {"x": strip_x, "y": row_y + card_height + 6.0, "width": card_width + 80.0, "height": 18.0},
            "#334155",
            8.8,
            [page.id, candidate.id],
        )
        source_label.metadata.update({"traceOverlay": True, "sourceCandidateId": candidate.id})
        objects.append(source_label)

        target_y = row_y + card_height * 0.5
        system = candidate.system or _system_for_tag(candidate.lineTag or candidate.label, group_name) or "DEFAULT"
        line_start = {"x": strip_x + card_width, "y": target_y}
        line_mid = {"x": strip_x + card_width + 115.0, "y": target_y}
        line_end = {"x": target_x, "y": target_y}
        trace_line = _overview_pipe(
            f"{slug}_trace_line_{index}",
            "",
            [line_start, line_mid, line_end],
            system,
            _styles(),
            [page.id, candidate.id],
            1.4,
        )
        trace_line.style.stroke = trace_color
        trace_line.style.opacity = 0.72
        trace_line.style.dash = [11.0, 7.0]
        trace_line.metadata.update(
            {
                "traceOverlay": True,
                "sourceCandidateId": candidate.id,
                "traceRole": "source_to_template",
                "lineTag": candidate.lineTag,
                "sheetRef": candidate.sheetRef,
            }
        )
        objects.append(trace_line)

        target_symbol = _overview_symbol(
            f"{slug}_trace_target_{index}",
            "",
            {"x": target_x - 18.0, "y": target_y - 15.0, "width": 56.0, "height": 30.0},
            "#111827",
            [page.id, candidate.id],
            "offpage",
            metadata={"orientation": "right"},
        )
        target_symbol.metadata.update({"traceOverlay": True, "sourceCandidateId": candidate.id, "traceRole": "generated_target"})
        objects.append(target_symbol)

        target_label = _overview_label(
            f"{slug}_trace_target_label_{index}",
            _continuation_label(candidate),
            {"x": target_x + 48.0, "y": target_y - 10.0, "width": 360.0, "height": 20.0},
            "#111827",
            9.0,
            [page.id, candidate.id],
        )
        target_label.metadata.update({"traceOverlay": True, "sourceCandidateId": candidate.id, "traceRole": "generated_label"})
        objects.append(target_label)


def _trace_crop_bounds(candidate: ContinuationCandidate, page: PageEvidence) -> BoundsDict:
    crop = page.cropBounds
    pad_x = 235.0 if candidate.edge in {"left", "right"} else 130.0
    pad_y = 120.0 if candidate.edge in {"top", "bottom"} else 72.0
    x0 = max(crop["x"], candidate.bounds["x"] - pad_x)
    y0 = max(crop["y"], candidate.bounds["y"] - pad_y)
    x1 = min(crop["x"] + crop["width"], candidate.bounds["x"] + candidate.bounds["width"] + pad_x)
    y1 = min(crop["y"] + crop["height"], candidate.bounds["y"] + candidate.bounds["height"] + pad_y)
    return {"x": x0, "y": y0, "width": max(1.0, x1 - x0), "height": max(1.0, y1 - y0)}


def _add_overview_review_notes(
    objects: list[DrawingObject],
    slug: str,
    group_name: str,
    plant_bounds: BoundsDict,
    distribution_bounds: BoundsDict,
    source_ids: list[str],
) -> None:
    if group_name == "CHW / CW":
        notes: list[tuple[str, str, BoundsDict, Point]] = [
            ("chiller_tie", "VERIFY COMMON CHWS / CHWR HEADER ROUTING", {"x": plant_bounds["x"] + 1250.0, "y": plant_bounds["y"] + 318.0, "width": 250.0, "height": 62.0}, {"x": plant_bounds["x"] + 1120.0, "y": plant_bounds["y"] + 355.0}),
            ("pump_controls", "PUMP SKID CONTROLS TO BE CONFIRMED", {"x": plant_bounds["x"] + 520.0, "y": plant_bounds["y"] + 1150.0, "width": 260.0, "height": 70.0}, {"x": plant_bounds["x"] + 505.0, "y": plant_bounds["y"] + 940.0}),
            ("tower_bypass", "CW BYPASS / TOWER ISOLATION", {"x": plant_bounds["x"] + 1760.0, "y": plant_bounds["y"] + 800.0, "width": 235.0, "height": 62.0}, {"x": plant_bounds["x"] + 1775.0, "y": plant_bounds["y"] + 610.0}),
            ("building_ties", "OFF-SHEET REFERENCES REQUIRE FIELD REVIEW", {"x": distribution_bounds["x"] + 75.0, "y": distribution_bounds["y"] + 1380.0, "width": 330.0, "height": 68.0}, {"x": distribution_bounds["x"] + 255.0, "y": distribution_bounds["y"] + 1120.0}),
        ]
    else:
        notes = [
            ("future_capacity", "FUTURE BOILER BRANCHES SHOWN FOR COORDINATION", {"x": plant_bounds["x"] + 500.0, "y": plant_bounds["y"] + 330.0, "width": 285.0, "height": 68.0}, {"x": plant_bounds["x"] + 330.0, "y": plant_bounds["y"] + 620.0}),
            ("hrw_controls", "HRW CONTROLS / HEAT RECOVERY TIE-IN", {"x": plant_bounds["x"] + 1250.0, "y": plant_bounds["y"] + 1015.0, "width": 270.0, "height": 70.0}, {"x": plant_bounds["x"] + 1180.0, "y": plant_bounds["y"] + 1150.0}),
            ("pump_review", "PUMP DUTY / STANDBY ORDER TO REVIEW", {"x": plant_bounds["x"] + 760.0, "y": plant_bounds["y"] + 1820.0, "width": 265.0, "height": 64.0}, {"x": plant_bounds["x"] + 890.0, "y": plant_bounds["y"] + 1620.0}),
            ("building_ties", "OFF-SHEET REFERENCES REQUIRE FIELD REVIEW", {"x": distribution_bounds["x"] + 75.0, "y": distribution_bounds["y"] + 1380.0, "width": 330.0, "height": 68.0}, {"x": distribution_bounds["x"] + 255.0, "y": distribution_bounds["y"] + 1120.0}),
        ]

    for id_seed, label, bounds, leader_end in notes:
        objects.append(_overview_region(f"{slug}_review_note_{id_seed}", "", bounds, "#ef4444", "#ffffff", 0.72, source_ids))
        objects.append(
            _overview_label(
                f"{slug}_review_note_label_{id_seed}",
                label,
                {"x": bounds["x"] + 10.0, "y": bounds["y"] + 15.0, "width": bounds["width"] - 20.0, "height": bounds["height"] - 20.0},
                "#dc2626",
                8.2,
                source_ids,
            )
        )
        leader_start = {"x": bounds["x"], "y": bounds["y"] + bounds["height"] / 2.0}
        objects.append(
            _overview_pipe(
                f"{slug}_review_note_leader_{id_seed}",
                "",
                [leader_start, {"x": (leader_start["x"] + leader_end["x"]) / 2.0, "y": leader_start["y"]}, leader_end],
                "REVIEW",
                _styles(),
                source_ids,
                1.1,
            )
        )


def _polish_compiled_objects(objects: list[DrawingObject]) -> None:
    """Apply final house-style cleanup to imported/generated overview objects."""
    for obj in objects:
        if obj.kind == "label":
            _mark_wrappable_label(obj)
            _soften_review_label(obj)
        elif obj.kind in {"pipe", "connector"}:
            _normalize_endpoint_metadata(obj)


def _mark_wrappable_label(obj: DrawingObject) -> None:
    label = " ".join(obj.label.split())
    if not label:
        return
    font_size = obj.style.fontSize or 8.0
    available_width = max(1.0, obj.bounds["width"] - 4.0)
    estimated_width = len(label) * font_size * 0.54
    if estimated_width <= available_width:
        return
    obj.metadata["textWrap"] = True
    obj.metadata.setdefault("textAlign", "left")


def _soften_review_label(obj: DrawingObject) -> None:
    label = obj.label.casefold()
    if "cxa comment" not in label and "recommend" not in label:
        return
    obj.metadata.update({"qaAnnotation": True, "textWrap": True, "textBox": True, "boxStroke": "#fecaca"})
    obj.style.stroke = "#b91c1c"
    obj.style.fill = "#fffafa"
    obj.style.opacity = min(obj.style.opacity, 0.82)
    obj.style.fontSize = min(obj.style.fontSize or 7.0, 6.6)
    obj.style.strokeWidth = 0.8
    obj.bounds["width"] = min(max(obj.bounds["width"], 190.0), 260.0)
    obj.bounds["height"] = max(obj.bounds["height"], 42.0)


def _normalize_endpoint_metadata(obj: DrawingObject) -> None:
    if len(obj.points) < 2:
        return
    if obj.metadata.get("arrowStart") or obj.metadata.get("arrowEnd"):
        obj.metadata["trimLineForArrowheads"] = True


def _add_source_generated_evidence_tags(
    objects: list[DrawingObject],
    slug: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    source_paths: dict[str, str],
    group_name: str,
) -> None:
    page_ids = _page_ids(pages)
    meaningful = _meaningful_continuation_candidates(candidates, pages, source_paths, group_name)
    source_names = [_source_sheet_ref_for_page(page, source_paths) for page in pages]
    summary_bounds = {"x": 116.0, "y": 2398.0, "width": 1160.0, "height": 104.0}
    objects.append(_overview_region(f"{slug}_source_summary", "", summary_bounds, "#0f766e", "#ffffff", 0.78, page_ids))
    objects.append(
        _overview_label(
            f"{slug}_source_summary_title",
            "SOURCE-DRIVEN BUILD",
            {"x": summary_bounds["x"] + 14.0, "y": summary_bounds["y"] + 16.0, "width": 240.0, "height": 16.0},
            "#0f766e",
            8.6,
            page_ids,
        )
    )
    objects.append(
        _overview_label(
            f"{slug}_source_summary_sources",
            f"{len(pages)} source sheets: {', '.join(source_names[:4])}",
            {"x": summary_bounds["x"] + 14.0, "y": summary_bounds["y"] + 42.0, "width": 760.0, "height": 16.0},
            "#334155",
            8.0,
            page_ids,
        )
    )
    objects.append(
        _overview_label(
            f"{slug}_source_summary_continuations",
            f"{len(meaningful)} off-sheet continuation callouts extracted and redrafted into editable targets",
            {"x": summary_bounds["x"] + 14.0, "y": summary_bounds["y"] + 66.0, "width": 820.0, "height": 16.0},
            "#334155",
            8.0,
            page_ids,
        )
    )
    for index, candidate in enumerate(meaningful[:5]):
        y = summary_bounds["y"] + 20.0 + index * 16.0
        objects.append(
            _overview_label(
                f"{slug}_source_summary_callout_{index}",
                _continuation_label(candidate),
                {"x": summary_bounds["x"] + 792.0, "y": y, "width": 340.0, "height": 14.0},
                SYSTEM_COLORS.get(candidate.system or _system_for_tag(candidate.lineTag, group_name), "#334155"),
                7.2,
                [candidate.id],
            )
        )


def _add_source_graph_assembly_badges(
    objects: list[DrawingObject],
    slug: str,
    source_graph: PidSourceGraph,
    plant_bounds: BoundsDict,
    distribution_bounds: BoundsDict,
) -> None:
    positions = {
        "chiller_bank": {"x": plant_bounds["x"] + 185.0, "y": plant_bounds["y"] + 74.0, "width": 360.0, "height": 42.0},
        "chw_pumps": {"x": plant_bounds["x"] + 170.0, "y": plant_bounds["y"] + 732.0, "width": 340.0, "height": 42.0},
        "cw_pumps": {"x": plant_bounds["x"] + 600.0, "y": plant_bounds["y"] + 732.0, "width": 320.0, "height": 42.0},
        "cooling_water": {"x": plant_bounds["x"] + 1438.0, "y": plant_bounds["y"] + 218.0, "width": 380.0, "height": 42.0},
        "hhw_boilers": {"x": plant_bounds["x"] + 540.0, "y": plant_bounds["y"] + 190.0, "width": 360.0, "height": 42.0},
        "hhw_pumps": {"x": plant_bounds["x"] + 550.0, "y": plant_bounds["y"] + 1360.0, "width": 340.0, "height": 42.0},
        "hrw_pumps": {"x": plant_bounds["x"] + 910.0, "y": plant_bounds["y"] + 1360.0, "width": 320.0, "height": 42.0},
        "hrw_recovery": {"x": plant_bounds["x"] + 955.0, "y": plant_bounds["y"] + 860.0, "width": 380.0, "height": 42.0},
    }
    for assembly in source_graph.assemblies:
        bounds = positions.get(assembly.kind)
        if bounds is None:
            continue
        label = f"{assembly.label}: {len(assembly.equipmentTags)} EQUIP / {len(assembly.lineTags)} LINES"
        badge = _overview_region(f"{slug}_assembly_badge_{assembly.kind}", "", bounds, "#0f766e", "#ffffff", 0.82, assembly.sourcePageIds)
        badge.metadata.update({"sourceAssembly": assembly.kind, "sourceGenerated": True, "hideCenterLabel": True})
        objects.append(badge)
        text = _overview_label(
            f"{slug}_assembly_badge_label_{assembly.kind}",
            label,
            {"x": bounds["x"] + 10.0, "y": bounds["y"] + 15.0, "width": bounds["width"] - 20.0, "height": 14.0},
            "#0f766e",
            7.6,
            assembly.sourcePageIds,
        )
        text.metadata.update({"sourceAssembly": assembly.kind, "sourceGenerated": True})
        objects.append(text)

    summary_bounds = {"x": distribution_bounds["x"] + 58.0, "y": distribution_bounds["y"] + distribution_bounds["height"] - 150.0, "width": 470.0, "height": 72.0}
    objects.append(_overview_region(f"{slug}_source_graph_summary", "", summary_bounds, "#0f766e", "#ffffff", 0.72, source_graph.sourcePageIds))
    objects.append(
        _overview_label(
            f"{slug}_source_graph_summary_label",
            f"SOURCE GRAPH: {source_graph.metrics['assemblies']} assemblies / {source_graph.metrics['continuations']} continuations",
            {"x": summary_bounds["x"] + 12.0, "y": summary_bounds["y"] + 18.0, "width": 430.0, "height": 16.0},
            "#0f766e",
            8.0,
            source_graph.sourcePageIds,
        )
    )
    objects.append(
        _overview_label(
            f"{slug}_source_graph_summary_detail",
            f"{source_graph.metrics['equipmentTags']} equipment tags and {source_graph.metrics['lineTags']} line tags extracted",
            {"x": summary_bounds["x"] + 12.0, "y": summary_bounds["y"] + 42.0, "width": 430.0, "height": 16.0},
            "#334155",
            7.6,
            source_graph.sourcePageIds,
        )
    )


def _add_source_generated_line_tag_rack(
    objects: list[DrawingObject],
    slug: str,
    source_graph: PidSourceGraph,
    styles: dict[str, DrawingStyle],
    plant_bounds: BoundsDict,
) -> None:
    line_rows: list[tuple[str, str]] = []
    systems = ("HHWS", "HHWR", "HRW") if source_graph.groupName == "HHW / HRW" else ("CHWS", "CHWR", "CWS", "CWR")
    for system in systems:
        for tag in source_graph.lineTagsBySystem.get(system, []):
            line_rows.append((system, tag))
    if not line_rows:
        return

    rack_bounds = {
        "x": plant_bounds["x"] + 145.0,
        "y": plant_bounds["y"] + 1195.0,
        "width": 1055.0,
        "height": min(560.0, 105.0 + min(8, len(line_rows)) * 54.0),
    }
    region = _overview_region(f"{slug}_line_tag_rack", "", rack_bounds, "#64748b", "#ffffff", 0.2, source_graph.sourcePageIds)
    region.metadata.update({"sourceGeneratedLineRack": True, "sourceGenerated": True, "hideCenterLabel": True})
    objects.append(region)
    label = _overview_label(
        f"{slug}_line_tag_rack_label",
        "SOURCE LINE TAG RACK",
        {"x": rack_bounds["x"] + 14.0, "y": rack_bounds["y"] + 14.0, "width": 240.0, "height": 16.0},
        "#475569",
        8.4,
        source_graph.sourcePageIds,
    )
    label.metadata.update({"sourceGeneratedLineRack": True, "sourceGenerated": True})
    objects.append(label)

    start_x = rack_bounds["x"] + 46.0
    end_x = rack_bounds["x"] + rack_bounds["width"] - 68.0
    for index, (system, tag) in enumerate(line_rows[:8]):
        y = rack_bounds["y"] + 62.0 + index * 54.0
        pipe = _overview_pipe(
            f"{slug}_line_tag_rack_pipe_{index}",
            tag,
            [{"x": start_x, "y": y}, {"x": end_x, "y": y}],
            system,
            styles,
            source_graph.sourcePageIds,
            1.45,
        )
        pipe.metadata.update({"sourceGeneratedLineRack": True, "sourceGenerated": True, "lineTag": tag})
        objects.append(pipe)
        _add_valve_and_instrument_pair(objects, f"{slug}_line_tag_rack_pair_{index}", start_x + 118.0 + (index % 4) * 142.0, y, system, styles, source_graph.sourcePageIds, "FIT" if index % 2 else "PIT")
        objects.append(
            _overview_symbol(
                f"{slug}_line_tag_rack_offpage_{index}",
                "",
                {"x": end_x - 10.0, "y": y - 12.0, "width": 46.0, "height": 24.0},
                "#111827",
                source_graph.sourcePageIds,
                "offpage",
                metadata={"orientation": "right", "sourceGeneratedLineRack": True, "sourceGenerated": True, "lineTag": tag},
            )
        )
        tag_label = _overview_label(
            f"{slug}_line_tag_rack_tag_{index}",
            tag,
            {"x": start_x + 10.0, "y": y - 25.0, "width": 180.0, "height": 14.0},
            SYSTEM_COLORS.get(system, "#334155"),
            7.2,
            source_graph.sourcePageIds,
        )
        tag_label.metadata.update({"sourceGeneratedLineRack": True, "sourceGenerated": True, "lineTag": tag})
        objects.append(tag_label)


def _add_full_source_equipment_body(
    objects: list[DrawingObject],
    slug: str,
    source_graph: PidSourceGraph,
    plant_bounds: BoundsDict,
    distribution_bounds: BoundsDict,
    styles: dict[str, DrawingStyle],
    hidden_buckets: set[str] | None = None,
) -> list[dict[str, Any]]:
    hidden_buckets = hidden_buckets or set()
    staged_register: list[dict[str, Any]] = []
    buckets: dict[str, list[str]] = {
        "future": [],
        "boilers": [],
        "pumps": [],
        "hrw": [],
        "distribution": [],
        "auxiliary": [],
    }
    for tag in source_graph.equipmentTags:
        buckets[_full_equipment_bucket(tag)].append(tag)

    sections: dict[str, tuple[str, BoundsDict, str]] = {
        "future": (
            "FUTURE / STANDBY EQUIPMENT",
            {"x": plant_bounds["x"] + 110.0, "y": plant_bounds["y"] + 360.0, "width": 500.0, "height": 2130.0},
            "HHWS",
        ),
        "boilers": (
            "BOILER PLANT EQUIPMENT",
            {"x": plant_bounds["x"] + 720.0, "y": plant_bounds["y"] + 380.0, "width": 930.0, "height": 760.0},
            "HHWS",
        ),
        "hrw": (
            "HEAT RECOVERY EQUIPMENT",
            {"x": plant_bounds["x"] + 1220.0, "y": plant_bounds["y"] + 1460.0, "width": 950.0, "height": 720.0},
            "HRW",
        ),
        "pumps": (
            "PUMP AND SKID EQUIPMENT",
            {"x": plant_bounds["x"] + 690.0, "y": plant_bounds["y"] + 2330.0, "width": 1260.0, "height": 610.0},
            "HHWR",
        ),
        "distribution": (
            "BUILDING LOAD EQUIPMENT",
            {"x": distribution_bounds["x"] + 118.0, "y": distribution_bounds["y"] + 430.0, "width": 680.0, "height": 2200.0},
            "HRW",
        ),
        "auxiliary": (
            "AUXILIARY EQUIPMENT",
            {"x": plant_bounds["x"] + 1850.0, "y": plant_bounds["y"] + 440.0, "width": 900.0, "height": 840.0},
            "DEFAULT",
        ),
    }
    for bucket, tags in buckets.items():
        if not tags:
            continue
        title, bounds, fallback_system = sections[bucket]
        if bucket in hidden_buckets:
            for tag in tags:
                system = _system_for_tag(tag, "HHW / HRW")
                if system == "DEFAULT":
                    system = fallback_system
                staged_register.append(
                    {
                        "tag": tag,
                        "system": system,
                        "section": title,
                        "status": "staged",
                        "sourcePages": len(source_graph.sourcePageIds),
                    }
                )
            continue
        _add_full_section_title(objects, slug, f"equipment_{bucket}", title, bounds, fallback_system, source_graph.sourcePageIds)
        columns = _full_equipment_columns(bucket, bounds)
        gap_x = bounds["width"] / columns
        gap_y = _full_equipment_row_gap(bucket)
        for index, tag in enumerate(tags):
            column = index % columns
            row = index // columns
            x = bounds["x"] + gap_x * column + gap_x * 0.5
            y = bounds["y"] + 58.0 + row * gap_y
            if y > bounds["y"] + bounds["height"] - 58.0:
                y = bounds["y"] + bounds["height"] - 58.0
                x += (row - int((bounds["height"] - 116.0) // gap_y)) * 8.0
            _add_required_equipment_symbol(objects, slug, tag, x, y, fallback_system, styles, source_graph.sourcePageIds)
    return staged_register


def _add_full_source_line_body(
    objects: list[DrawingObject],
    slug: str,
    source_graph: PidSourceGraph,
    plant_bounds: BoundsDict,
    distribution_bounds: BoundsDict,
    styles: dict[str, DrawingStyle],
) -> None:
    rows: list[tuple[str, str]] = []
    for system in ("HHWS", "HHWR", "HRW", "DEFAULT"):
        rows.extend((system, tag) for tag in source_graph.lineTagsBySystem.get(system, []))
    for system, tags in source_graph.lineTagsBySystem.items():
        if system not in {"HHWS", "HHWR", "HRW", "DEFAULT"}:
            rows.extend((system, tag) for tag in tags)
    if not rows:
        return

    bounds = {
        "x": plant_bounds["x"] + 180.0,
        "y": plant_bounds["y"] + plant_bounds["height"] - 500.0,
        "width": distribution_bounds["x"] + distribution_bounds["width"] - plant_bounds["x"] - 360.0,
        "height": 430.0,
    }
    _add_full_section_title(objects, slug, "line_body", "VISIBLE SOURCE LINE TAG ROUTING", bounds, "DEFAULT", source_graph.sourcePageIds)
    row_gap = 20.0
    max_rows = max(1, int((bounds["height"] - 70.0) // row_gap))
    columns = min(8, max(3, (len(rows) + max_rows - 1) // max_rows))
    col_width = bounds["width"] / columns
    for index, (system, tag) in enumerate(rows):
        col = index % columns
        row = index // columns
        x = bounds["x"] + col * col_width + 22.0
        y = bounds["y"] + 52.0 + row * row_gap
        if y > bounds["y"] + bounds["height"] - 18.0:
            break
        color_system = system if system in styles else _system_for_tag(tag, source_graph.groupName)
        pipe = _overview_pipe(
            f"{slug}_required_line_{index}",
            tag,
            [{"x": x, "y": y}, {"x": x + col_width - 68.0, "y": y}],
            color_system,
            styles,
            source_graph.sourcePageIds,
            1.05,
        )
        pipe.metadata.update({"sourceRequiredLineTag": True, "sourceGenerated": True, "lineTag": tag, "system": color_system})
        objects.append(pipe)
        label = _overview_label(
            f"{slug}_required_line_label_{index}",
            tag,
            {"x": x + 6.0, "y": y - 13.0, "width": col_width - 82.0, "height": 10.0},
            SYSTEM_COLORS.get(color_system, "#334155"),
            5.8,
            source_graph.sourcePageIds,
        )
        label.metadata.update({"sourceRequiredLineTag": True, "sourceGenerated": True, "lineTag": tag, "system": color_system})
        objects.append(label)


def _line_tag_register(source_graph: PidSourceGraph) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    ordered_systems = ["HHWS", "HHWR", "HRW", "CHWS", "CHWR", "CWS", "CWR", "CDA", "DEFAULT"]
    for system in ordered_systems:
        for tag in source_graph.lineTagsBySystem.get(system, []):
            if tag in seen:
                continue
            seen.add(tag)
            rows.append({"tag": tag, "system": system, "status": "registered", "sourcePages": len(source_graph.sourcePageIds)})
    for system, tags in source_graph.lineTagsBySystem.items():
        if system in ordered_systems:
            continue
        for tag in tags:
            if tag in seen:
                continue
            seen.add(tag)
            rows.append({"tag": tag, "system": system, "status": "registered", "sourcePages": len(source_graph.sourcePageIds)})
    return rows


def _add_strict_coverage_gate(
    objects: list[DrawingObject],
    slug: str,
    source_graph: PidSourceGraph,
    plant_bounds: BoundsDict,
    distribution_bounds: BoundsDict,
    staged_equipment_register: list[dict[str, Any]] | None = None,
) -> None:
    staged_equipment_register = staged_equipment_register or []
    required_equipment = set(source_graph.equipmentTags)
    visible_equipment = _visible_required_metadata_values(objects, "equipmentTag", "sourceRequiredEquipment")
    registered_equipment = visible_equipment | {str(item["tag"]) for item in staged_equipment_register}
    required_lines = {tag for tags in source_graph.lineTagsBySystem.values() for tag in tags}
    missing_equipment = len(required_equipment - registered_equipment)
    registered_lines = required_lines
    missing_lines = len(required_lines - registered_lines)
    color = "#0f766e" if not missing_equipment and not missing_lines else "#dc2626"
    bounds = {"x": distribution_bounds["x"] + 68.0, "y": plant_bounds["y"] + 62.0, "width": 520.0, "height": 104.0}
    gate = _overview_region(f"{slug}_strict_coverage_gate", "", bounds, color, "#ffffff", 0.82, source_graph.sourcePageIds, {"hideCenterLabel": True})
    gate.metadata.update({"strictCoverageGate": True, "sourceGenerated": True})
    objects.append(gate)
    lines = [
        "STRICT COVERAGE GATE",
        f"EQUIPMENT: {len(visible_equipment)} VISIBLE / {len(staged_equipment_register)} IN REGISTER",
        f"LINE TAGS: {len(registered_lines)} / {len(required_lines)} IN REGISTER",
    ]
    for index, line in enumerate(lines):
        label = _overview_label(
            f"{slug}_strict_coverage_gate_label_{index}",
            line,
            {"x": bounds["x"] + 14.0, "y": bounds["y"] + 16.0 + index * 25.0, "width": bounds["width"] - 28.0, "height": 14.0},
            color if index == 0 else "#334155",
            8.4 if index == 0 else 7.4,
            source_graph.sourcePageIds,
        )
        label.metadata.update({"strictCoverageGate": True, "sourceGenerated": True})
        objects.append(label)


def _add_full_section_title(
    objects: list[DrawingObject],
    slug: str,
    id_seed: str,
    title: str,
    bounds: BoundsDict,
    system: str,
    source_ids: list[str],
) -> None:
    label = _overview_label(
        f"{slug}_{id_seed}_title",
        title,
        {"x": bounds["x"] + 8.0, "y": bounds["y"] + 12.0, "width": bounds["width"] - 16.0, "height": 13.0},
        SYSTEM_COLORS.get(system, "#334155"),
        7.4,
        source_ids,
    )
    label.metadata.update({"sourceRequiredSection": id_seed, "sourceGenerated": True})
    objects.append(label)


def _add_required_equipment_symbol(
    objects: list[DrawingObject],
    slug: str,
    tag: str,
    x: float,
    y: float,
    fallback_system: str,
    styles: dict[str, DrawingStyle],
    source_ids: list[str],
) -> None:
    system = _system_for_tag(tag, "HHW / HRW")
    if system == "DEFAULT":
        system = fallback_system
    stroke = SYSTEM_COLORS.get(system, styles.get(fallback_system, styles["DEFAULT"]).stroke)
    center_y = y + 24.0
    branch = _overview_pipe(
        f"{slug}_required_equipment_branch_{tag}_{x:.1f}_{y:.1f}",
        "",
        [{"x": x - 68.0, "y": center_y}, {"x": x + 68.0, "y": center_y}],
        system,
        styles,
        source_ids,
        1.0,
    )
    branch.metadata.update({"sourceRequiredEquipment": True, "sourceGenerated": True, "equipmentTag": tag, "system": system})
    objects.append(branch)
    symbol = _overview_symbol(
        f"{slug}_required_equipment_{tag}_{x:.1f}_{y:.1f}",
        "",
        {"x": x - 44.0, "y": y, "width": 88.0, "height": 48.0},
        stroke,
        source_ids,
        _symbol_type_for_tag(tag),
        metadata={"sourceRequiredEquipment": True, "sourceGenerated": True, "equipmentTag": tag, "system": system},
    )
    objects.append(symbol)
    _add_valve_and_instrument_pair(objects, f"{slug}_required_equipment_pair_{tag}_{x:.1f}_{y:.1f}", x - 58.0, center_y, system, styles, source_ids, "PIT")
    for obj in objects[-3:]:
        obj.metadata.setdefault("sourceGenerated", True)
        obj.metadata.setdefault("equipmentTag", tag)
    label = _overview_label(
        f"{slug}_required_equipment_label_{tag}_{x:.1f}_{y:.1f}",
        tag,
        {"x": x - 66.0, "y": y + 54.0, "width": 132.0, "height": 14.0},
        stroke,
        6.3,
        source_ids,
    )
    label.metadata.update({"sourceRequiredEquipment": True, "sourceGenerated": True, "equipmentTag": tag, "system": system, "textWrap": True, "textAlign": "center"})
    objects.append(label)


def _full_equipment_bucket(tag: str) -> str:
    text = tag.upper()
    if text.startswith("AHU-") or text.startswith("MAU-"):
        return "distribution"
    if "-HWB-" in text or "-BLR-" in text:
        return "future" if re.search(r"(?:0[5-9]|1[0-9])$", text) else "boilers"
    if "HRW" in text and ("-HX-" in text or "-AS-" in text or "-P-" in text):
        return "hrw"
    if text.startswith("HX-") or "-HX-" in text:
        return "hrw"
    if "-P-" in text or re.match(r"P-(?:\d{1,3}|XX)", text):
        return "pumps"
    return "auxiliary"


def _full_equipment_columns(bucket: str, bounds: BoundsDict) -> int:
    if bucket == "future":
        return 1
    if bucket == "distribution":
        return 3
    if bucket in {"pumps", "auxiliary"}:
        return 4
    return max(2, min(4, int(bounds["width"] // 170.0)))


def _full_equipment_row_gap(bucket: str) -> float:
    if bucket == "future":
        return 170.0
    if bucket == "distribution":
        return 105.0
    if bucket == "pumps":
        return 145.0
    if bucket == "auxiliary":
        return 135.0
    return 125.0


def _visible_required_metadata_values(objects: list[DrawingObject], value_key: str, required_key: str) -> set[str]:
    return {
        str(obj.metadata[value_key])
        for obj in objects
        if obj.metadata.get(required_key) is True
        and obj.metadata.get("sourceGeneratedCoverageIndex") is not True
        and obj.metadata.get(value_key)
    }


def _annotate_connector_connectivity(objects: list[DrawingObject]) -> dict[str, int]:
    """Attach editable generated line endpoints to nearby symbols/labels and QA the rest."""
    connectors = [
        obj
        for obj in objects
        if obj.kind in {"pipe", "connector"}
        and len(obj.points) >= 2
        and obj.metadata.get("sourceDerived") is not True
        and obj.metadata.get("sourceVector") is not True
    ]
    hosts = [
        obj
        for obj in objects
        if obj.kind in {"symbol", "label"}
        and obj.metadata.get("sourceGeneratedCoverageIndex") is not True
        and obj.metadata.get("strictCoverageGate") is not True
    ]
    segments: list[tuple[str, Point, Point]] = []
    for connector in connectors:
        for index in range(len(connector.points) - 1):
            start = connector.points[index]
            end = connector.points[index + 1]
            if _point_distance(start, end) >= 0.5:
                segments.append((connector.id, start, end))

    stats = {
        "connectablePipes": len(connectors),
        "totalEndpoints": len(connectors) * 2,
        "connectedEndpoints": 0,
        "explicitObjectEndpoints": 0,
        "pipeJunctionEndpoints": 0,
        "danglingEndpoints": 0,
        "nodeToNodePipes": 0,
        "partialPipes": 0,
        "regionEndpointAttachments": 0,
    }
    for connector in connectors:
        connector.metadata["connectable"] = True
        connected_for_pipe = 0
        for endpoint_name, point in (("start", connector.points[0]), ("end", connector.points[-1])):
            host, host_distance = _nearest_connectable_host(point, hosts)
            prefix = endpoint_name
            if host is not None and host_distance <= 30.0:
                connector.metadata[f"{prefix}ObjectId"] = host.id
                connector.metadata[f"{prefix}ObjectKind"] = host.kind
                connector.metadata[f"{prefix}ConnectionType"] = host.kind
                connector.metadata[f"{prefix}ConnectionDistance"] = round(host_distance, 2)
                stats["connectedEndpoints"] += 1
                stats["explicitObjectEndpoints"] += 1
                if host.kind == "region":
                    stats["regionEndpointAttachments"] += 1
                connected_for_pipe += 1
                continue

            junction_id, junction_distance = _nearest_connector_segment(point, segments, connector.id)
            if junction_id is not None and junction_distance <= 8.0:
                connector.metadata[f"{prefix}ConnectedObjectId"] = junction_id
                connector.metadata[f"{prefix}ConnectionType"] = "pipe-junction"
                connector.metadata[f"{prefix}ConnectionDistance"] = round(junction_distance, 2)
                stats["connectedEndpoints"] += 1
                stats["pipeJunctionEndpoints"] += 1
                connected_for_pipe += 1
                continue

            connector.metadata[f"{prefix}ConnectionType"] = "dangling"
            stats["danglingEndpoints"] += 1

        if connected_for_pipe == 2:
            stats["nodeToNodePipes"] += 1
            connector.metadata["connectivityStatus"] = "node-to-node"
        elif connected_for_pipe == 1:
            stats["partialPipes"] += 1
            connector.metadata["connectivityStatus"] = "partial"
        else:
            connector.metadata["connectivityStatus"] = "dangling"

    return stats


def _nearest_connectable_host(point: Point, hosts: list[DrawingObject]) -> tuple[DrawingObject | None, float]:
    nearest: DrawingObject | None = None
    nearest_distance = float("inf")
    for host in hosts:
        distance = _point_distance_to_bounds(point, host.bounds)
        if distance < nearest_distance:
            nearest = host
            nearest_distance = distance
    return nearest, nearest_distance


def _nearest_connector_segment(
    point: Point,
    segments: list[tuple[str, Point, Point]],
    connector_id: str,
) -> tuple[str | None, float]:
    nearest_id: str | None = None
    nearest_distance = float("inf")
    for segment_connector_id, start, end in segments:
        if segment_connector_id == connector_id:
            continue
        distance = _point_distance_to_segment(point, start, end)
        if distance < nearest_distance:
            nearest_id = segment_connector_id
            nearest_distance = distance
    return nearest_id, nearest_distance


def _point_distance_to_bounds(point: Point, bounds: BoundsDict) -> float:
    x = point["x"]
    y = point["y"]
    dx = max(bounds["x"] - x, 0.0, x - (bounds["x"] + bounds["width"]))
    dy = max(bounds["y"] - y, 0.0, y - (bounds["y"] + bounds["height"]))
    return (dx * dx + dy * dy) ** 0.5


def _point_distance_to_segment(point: Point, start: Point, end: Point) -> float:
    vx = end["x"] - start["x"]
    vy = end["y"] - start["y"]
    wx = point["x"] - start["x"]
    wy = point["y"] - start["y"]
    length_squared = vx * vx + vy * vy
    if length_squared <= 0.0:
        return _point_distance(point, start)
    t = max(0.0, min(1.0, (wx * vx + wy * vy) / length_squared))
    projection = {"x": start["x"] + t * vx, "y": start["y"] + t * vy}
    return _point_distance(point, projection)


def _point_distance(a: Point, b: Point) -> float:
    return ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5


def _add_source_generated_inventory(
    objects: list[DrawingObject],
    slug: str,
    source_graph: PidSourceGraph,
    plant_bounds: BoundsDict,
) -> None:
    equipment_tags = source_graph.equipmentTags[:16]
    if not equipment_tags:
        return
    bounds = {
        "x": plant_bounds["x"] + 1415.0,
        "y": plant_bounds["y"] + 1540.0,
        "width": 760.0,
        "height": min(360.0, 68.0 + ((len(equipment_tags) + 1) // 2) * 32.0),
    }
    region = _overview_region(f"{slug}_source_inventory", "", bounds, "#64748b", "#ffffff", 0.22, source_graph.sourcePageIds)
    region.metadata.update({"sourceGeneratedInventory": True, "sourceGenerated": True, "hideCenterLabel": True})
    objects.append(region)
    title = _overview_label(
        f"{slug}_source_inventory_title",
        "SOURCE EQUIPMENT INVENTORY",
        {"x": bounds["x"] + 14.0, "y": bounds["y"] + 14.0, "width": 260.0, "height": 16.0},
        "#475569",
        8.4,
        source_graph.sourcePageIds,
    )
    title.metadata.update({"sourceGeneratedInventory": True, "sourceGenerated": True})
    objects.append(title)
    for index, tag in enumerate(equipment_tags):
        col = index % 2
        row = index // 2
        label = _overview_label(
            f"{slug}_source_inventory_tag_{index}",
            tag,
            {"x": bounds["x"] + 28.0 + col * 360.0, "y": bounds["y"] + 48.0 + row * 32.0, "width": 320.0, "height": 14.0},
            SYSTEM_COLORS.get(_system_for_tag(tag, source_graph.groupName), "#334155"),
            7.2,
            source_graph.sourcePageIds,
        )
        label.metadata.update({"sourceGeneratedInventory": True, "sourceGenerated": True, "equipmentTag": tag})
        objects.append(label)


def _add_source_generated_coverage_index(
    objects: list[DrawingObject],
    slug: str,
    source_graph: PidSourceGraph,
    plant_bounds: BoundsDict,
    candidates: list[ContinuationCandidate],
    pages: list[PageEvidence],
    source_paths: dict[str, str],
) -> None:
    line_tags = [tag for system in sorted(source_graph.lineTagsBySystem) for tag in source_graph.lineTagsBySystem[system]]
    continuations = _meaningful_continuation_candidates(candidates, pages, source_paths, source_graph.groupName)
    sheet_refs = _source_sheet_refs_for_pages(pages, source_paths)
    sheet_refs.extend(candidate.sheetRef for candidate in continuations if candidate.sheetRef)
    sheet_refs = sorted(set(ref for ref in sheet_refs if ref))
    if not source_graph.equipmentTags and not line_tags and not sheet_refs:
        return

    bounds = {"x": plant_bounds["x"] + 42.0, "y": 2228.0, "width": 3120.0, "height": 292.0}
    region = _overview_region(f"{slug}_coverage_index", "", bounds, "#64748b", "#ffffff", 0.2, source_graph.sourcePageIds)
    region.metadata.update({"sourceGeneratedCoverageIndex": True, "sourceGenerated": True, "hideCenterLabel": True})
    objects.append(region)
    title = _overview_label(
        f"{slug}_coverage_index_title",
        "SOURCE COVERAGE INDEX",
        {"x": bounds["x"] + 16.0, "y": bounds["y"] + 16.0, "width": 280.0, "height": 16.0},
        "#475569",
        8.6,
        source_graph.sourcePageIds,
    )
    title.metadata.update({"sourceGeneratedCoverageIndex": True, "sourceGenerated": True})
    objects.append(title)
    _add_coverage_index_column(
        objects,
        slug,
        "equipment",
        "EQUIPMENT TAGS",
        source_graph.equipmentTags,
        bounds["x"] + 22.0,
        bounds["y"] + 48.0,
        1040.0,
        4,
        "equipmentTag",
        source_graph.sourcePageIds,
        source_graph.groupName,
    )
    _add_coverage_index_column(
        objects,
        slug,
        "line",
        "LINE TAGS",
        line_tags,
        bounds["x"] + 1110.0,
        bounds["y"] + 48.0,
        880.0,
        3,
        "lineTag",
        source_graph.sourcePageIds,
        source_graph.groupName,
    )
    _add_coverage_index_column(
        objects,
        slug,
        "ref",
        "SHEET REFS",
        sheet_refs,
        bounds["x"] + 2040.0,
        bounds["y"] + 48.0,
        1000.0,
        3,
        "sheetRef",
        source_graph.sourcePageIds,
        source_graph.groupName,
    )


def _source_sheet_refs_for_pages(pages: list[PageEvidence], source_paths: dict[str, str]) -> list[str]:
    refs: set[str] = set()
    for page in pages:
        own_ref = _source_sheet_ref_for_page(page, source_paths)
        if own_ref:
            refs.add(own_ref)
        for match in SHEET_REF_TOKEN_RE.finditer(_page_text(page)):
            ref = match.group(0).replace("_", "-").upper()
            if ref.startswith(f"{PROJECT_CODE}-ME-"):
                refs.add(ref)
    return sorted(refs)


def _add_coverage_index_column(
    objects: list[DrawingObject],
    slug: str,
    section: str,
    title: str,
    values: list[str],
    x: float,
    y: float,
    width: float,
    columns: int,
    metadata_key: str,
    source_ids: list[str],
    group_name: str,
) -> None:
    header = _overview_label(
        f"{slug}_coverage_{section}_header",
        f"{title} ({len(values)})",
        {"x": x, "y": y, "width": width, "height": 14.0},
        "#334155",
        7.8,
        source_ids,
    )
    header.metadata.update({"sourceGeneratedCoverageIndex": True, "sourceGenerated": True, "coverageSection": section})
    objects.append(header)
    col_width = width / max(1, columns)
    for index, value in enumerate(values):
        col = index % max(1, columns)
        row = index // max(1, columns)
        if row >= 21:
            break
        label = _overview_label(
            f"{slug}_coverage_{section}_{index}",
            value,
            {"x": x + col * col_width, "y": y + 23.0 + row * 11.2, "width": col_width - 12.0, "height": 9.0},
            SYSTEM_COLORS.get(_system_for_tag(value, group_name), "#334155"),
            5.2,
            source_ids,
        )
        label.metadata.update({"sourceGeneratedCoverageIndex": True, "sourceGenerated": True, "coverageSection": section, metadata_key: value})
        objects.append(label)


def _add_source_generated_distribution_ladder(
    objects: list[DrawingObject],
    slug: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    source_paths: dict[str, str],
    styles: dict[str, DrawingStyle],
    bounds: BoundsDict,
) -> None:
    page_ids = _page_ids(pages)
    continuations = _meaningful_continuation_candidates(candidates, pages, source_paths, "CHW / CW")
    if not continuations:
        return

    rail_x = bounds["x"] + 118.0
    top_y = bounds["y"] + 210.0
    row_gap = 70.0
    max_rows = min(12, len(continuations))
    bottom_y = top_y + (max_rows - 1) * row_gap + 44.0
    objects.append(
        _overview_pipe(
            f"{slug}_distribution_rail",
            "",
            [{"x": rail_x, "y": top_y - 42.0}, {"x": rail_x, "y": bottom_y}],
            "DEFAULT",
            styles,
            page_ids,
            1.65,
        )
    )

    for index, candidate in enumerate(continuations[:max_rows]):
        y = top_y + index * row_gap
        system = candidate.system or _system_for_tag(candidate.lineTag or candidate.label, "CHW / CW") or "CHWS"
        evidence_ids = [candidate.id]
        branch_end_x = bounds["x"] + bounds["width"] - 72.0
        objects.append(
            _overview_pipe(
                f"{slug}_distribution_branch_{index}",
                "",
                [{"x": rail_x, "y": y}, {"x": branch_end_x - 58.0, "y": y}],
                system,
                styles,
                evidence_ids,
                1.35,
            )
        )
        objects.append(
            _overview_symbol(
                f"{slug}_distribution_offpage_{index}",
                "",
                {"x": branch_end_x - 62.0, "y": y - 13.0, "width": 48.0, "height": 26.0},
                "#111827",
                evidence_ids,
                "offpage",
                metadata={
                    "orientation": "right",
                    "sourceCandidateId": candidate.id,
                    "lineTag": candidate.lineTag,
                    "sheetRef": candidate.sheetRef,
                    "sourceGeneratedDistribution": True,
                },
            )
        )
        line_label = _overview_label(
            f"{slug}_distribution_line_label_{index}",
            _continuation_line_label(candidate),
            {"x": rail_x + 16.0, "y": y - 24.0, "width": 212.0, "height": 16.0},
            "#111827",
            7.2,
            evidence_ids,
        )
        line_label.metadata.update(
            {
                "sourceGeneratedDistribution": True,
                "sourceGeneratedDistributionLabel": True,
                "distributionLabelRole": "line",
                "sourceCandidateId": candidate.id,
                "lineTag": candidate.lineTag,
                "sheetRef": candidate.sheetRef,
            }
        )
        objects.append(line_label)
        if candidate.sheetRef:
            target_label = _overview_label(
                f"{slug}_distribution_target_label_{index}",
                candidate.sheetRef,
                {"x": branch_end_x - 298.0, "y": y + 12.0, "width": 220.0, "height": 16.0},
                "#334155",
                6.8,
                evidence_ids,
            )
            target_label.metadata.update(
                {
                    "sourceGeneratedDistribution": True,
                    "sourceGeneratedDistributionLabel": True,
                    "distributionLabelRole": "target",
                    "sourceCandidateId": candidate.id,
                    "lineTag": candidate.lineTag,
                    "sheetRef": candidate.sheetRef,
                }
            )
            objects.append(target_label)
        if index % 2 == 0:
            _add_valve_and_instrument_pair(objects, f"{slug}_distribution_pair_{index}", rail_x + 55.0, y, system, styles, evidence_ids, "FIT")


def _overview_legend(styles: dict[str, DrawingStyle]) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    legend_x = 2500.0
    legend_y = 44.0
    swatch_w = 88.0
    row_h = 24.0
    systems = ["CHWS", "CHWR", "CWS", "CWR", "HHWS", "HHWR", "HRW", "CDA"]
    for index, system in enumerate(systems):
        row = index // 2
        col = index % 2
        x = legend_x + col * 270.0
        y = legend_y + row * row_h
        objects.append(
            _overview_pipe(
                f"legend_{system}",
                "",
                [{"x": x, "y": y + 10.0}, {"x": x + swatch_w, "y": y + 10.0}],
                system,
                styles,
                [],
                stroke_width=4.0,
            )
        )
        objects.append(
            _overview_label(
                f"legend_label_{system}",
                system,
                {"x": x + swatch_w + 12.0, "y": y, "width": 120.0, "height": 18.0},
                "#334155",
                12.0,
                [],
            )
        )
    return objects


def _overview_group_objects(
    group_name: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    source_paths: dict[str, str],
    styles: dict[str, DrawingStyle],
    y: float,
    height: float,
) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    page_ids = [page.id for page in pages]
    band = {"x": 120.0, "y": y, "width": _OVERVIEW_WIDTH - 240.0, "height": height}
    systems = _overview_systems_for_group(group_name, pages)
    equipment = _equipment_tags_for_pages(pages)
    line_tags_by_system = _line_tags_for_pages(pages, group_name)
    group_candidates = _meaningful_continuation_candidates(candidates, pages, source_paths, group_name)

    objects.extend(_overview_group_shell(group_name, band, page_ids))
    if group_name == "CDA":
        objects.extend(_overview_cda_network(group_name, band, equipment, line_tags_by_system, group_candidates, styles, page_ids))
    elif group_name == "CHW / CW":
        objects.extend(_overview_chw_cw_network(group_name, band, equipment, line_tags_by_system, group_candidates, styles, page_ids))
    elif group_name == "HHW / HRW":
        objects.extend(_overview_hhw_hrw_network(group_name, band, equipment, line_tags_by_system, group_candidates, styles, page_ids))
    else:
        objects.extend(_overview_generic_network(group_name, band, systems, equipment, line_tags_by_system, group_candidates, styles, page_ids))
    return objects


def _meaningful_continuation_candidates(
    candidates: list[ContinuationCandidate],
    pages: list[PageEvidence],
    source_paths: dict[str, str],
    group_name: str,
) -> list[ContinuationCandidate]:
    page_source_ids = {page.sourceFileId for page in pages}
    source_refs = {page.sourceFileId: _source_sheet_ref_for_page(page, source_paths) for page in pages}
    meaningful: list[ContinuationCandidate] = []
    for candidate in candidates:
        if candidate.sourceFileId not in page_source_ids:
            continue
        if _is_title_block_self_reference(candidate, source_refs.get(candidate.sourceFileId, "")):
            continue
        if _is_general_notes_reference(candidate):
            continue

        system = candidate.system or _system_for_tag(candidate.lineTag or candidate.label, group_name)
        if not _system_belongs_to_group(system, group_name):
            continue
        if candidate.lineTag or _is_mechanical_sheet_ref(candidate.sheetRef):
            meaningful.append(candidate)
    return meaningful


def _source_sheet_ref_for_page(page: PageEvidence, source_paths: dict[str, str]) -> str:
    source_path = source_paths.get(page.sourceFileId)
    if source_path:
        ref = _canonical_sheet_ref(Path(source_path).stem)
        if ref:
            return ref
    return _canonical_sheet_ref(page.sourceFileId)


def _is_title_block_self_reference(candidate: ContinuationCandidate, own_sheet_ref: str) -> bool:
    candidate_ref = _canonical_sheet_ref(candidate.sheetRef or candidate.evidenceText)
    return bool(candidate_ref and own_sheet_ref and candidate_ref == own_sheet_ref and not candidate.lineTag)


def _is_general_notes_reference(candidate: ContinuationCandidate) -> bool:
    candidate_ref = _canonical_sheet_ref(candidate.sheetRef or candidate.evidenceText)
    return bool(candidate_ref and not _is_mechanical_sheet_ref(candidate_ref) and not candidate.lineTag)


def _is_mechanical_sheet_ref(sheet_ref: str) -> bool:
    return bool(sheet_ref and sheet_ref.upper().startswith(f"{PROJECT_CODE}-ME-"))


def _canonical_sheet_ref(text: str) -> str:
    match = SHEET_REF_TOKEN_RE.search(text or "")
    return match.group(0).upper() if match else ""


def _overview_group_shell(group_name: str, band: BoundsDict, page_ids: list[str]) -> list[DrawingObject]:
    return [
        _overview_region(
            f"group_{group_name}",
            group_name,
            band,
            "#64748b",
            GROUP_COLORS.get(group_name, GROUP_COLORS["OTHER"]),
            0.58,
            page_ids,
        ),
        _overview_label(
            f"group_title_{group_name}",
            f"{group_name} SYSTEM",
            {"x": band["x"] + 28.0, "y": band["y"] + 28.0, "width": 520.0, "height": 28.0},
            "#0f172a",
            21.0,
            page_ids,
        ),
    ]


def _overview_cda_network(
    group_name: str,
    band: BoundsDict,
    equipment: list[str],
    line_tags_by_system: dict[str, list[str]],
    candidates: list[ContinuationCandidate],
    styles: dict[str, DrawingStyle],
    page_ids: list[str],
) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    x0 = band["x"]
    y0 = band["y"]
    w = band["width"]
    h = band["height"]
    header_y = y0 + h * 0.32
    lower_y = y0 + h * 0.66
    train_y = y0 + h * 0.52
    left_x = x0 + 210.0
    compressor_x = x0 + w * 0.18
    dryer_x = x0 + w * 0.34
    filter_x = x0 + w * 0.55
    tank_x = x0 + w * 0.76
    right_x = x0 + w - 280.0
    line_tag = _first_tag(line_tags_by_system, "CDA", "6\"-CA-CS01")

    objects.append(_overview_label(f"{group_name}_process_label", "COMPRESSORS / DRYERS / RECEIVERS", {"x": left_x, "y": y0 + 62.0, "width": 480.0, "height": 22.0}, "#4c1d95", 13.0, page_ids))
    objects.append(_overview_pipe(f"{group_name}_cda_upper_header", line_tag, [{"x": left_x, "y": header_y}, {"x": right_x, "y": header_y}], "CDA", styles, page_ids, 3.2))
    objects.append(_overview_pipe(f"{group_name}_cda_train_loop", "", [{"x": left_x, "y": header_y}, {"x": left_x, "y": lower_y}, {"x": compressor_x, "y": lower_y}, {"x": compressor_x, "y": train_y}, {"x": dryer_x, "y": train_y}, {"x": dryer_x, "y": lower_y}, {"x": filter_x, "y": lower_y}, {"x": filter_x, "y": train_y}, {"x": tank_x, "y": train_y}, {"x": tank_x, "y": header_y}], "CDA", styles, page_ids, 2.2))
    _add_line_tag(objects, f"{group_name}_cda_tag", line_tag, (left_x + right_x) / 2.0, header_y - 28.0, "CDA", page_ids)
    _add_flow_arrow(objects, f"{group_name}_cda_arrow", right_x, header_y, "CDA", page_ids)

    compressors = _equipment_by_keywords(equipment, ["-C-"])[:4] or equipment[:4]
    dryers = _equipment_by_keywords(equipment, ["-AD-"])[:2]
    filters = _equipment_by_keywords(equipment, ["-FLTR-"])[:6]
    tanks = _equipment_by_keywords(equipment, ["-ST-"])[:2]
    _place_symbol_row(objects, group_name, compressors, compressor_x - 185.0, lower_y + 28.0, 150.0, "CDA", page_ids, header_y)
    _place_symbol_row(objects, group_name, dryers, dryer_x - 90.0, train_y + 44.0, 150.0, "CDA", page_ids, train_y)
    _place_symbol_row(objects, group_name, filters, filter_x - 220.0, train_y + 44.0, 126.0, "CDA", page_ids, train_y)
    _place_symbol_row(objects, group_name, tanks, tank_x - 86.0, train_y + 38.0, 154.0, "CDA", page_ids, train_y)
    _add_continuation_stack(objects, group_name, band, candidates, styles, "CDA", page_ids, right_x + 4.0, y0 + 86.0, 36.0, 7)
    return objects


def _overview_chw_cw_network(
    group_name: str,
    band: BoundsDict,
    equipment: list[str],
    line_tags_by_system: dict[str, list[str]],
    candidates: list[ContinuationCandidate],
    styles: dict[str, DrawingStyle],
    page_ids: list[str],
) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    x0 = band["x"]
    y0 = band["y"]
    w = band["width"]
    h = band["height"]
    chiller_y = y0 + h * 0.28
    header_top_y = y0 + h * 0.18
    header_mid_y = y0 + h * 0.46
    pump_y = y0 + h * 0.62
    lower_loop_y = y0 + h * 0.78
    left_x = x0 + 250.0
    chiller_start_x = x0 + w * 0.24
    chiller_gap = 175.0
    pump_start_x = x0 + w * 0.46
    pump_gap = 130.0
    right_x = x0 + w - 280.0

    chws = _first_tag(line_tags_by_system, "CHWS", "20\"-CHWS-CS02")
    chwr = _first_tag(line_tags_by_system, "CHWR", "20\"-CHWR-CS02")
    cwr = _first_tag(line_tags_by_system, "CWR", "20\"-CWR-CS02")
    objects.append(_overview_pipe(f"{group_name}_chws_supply_manifold", chws, [{"x": left_x, "y": header_top_y}, {"x": right_x, "y": header_top_y}, {"x": right_x, "y": header_mid_y}], "CHWS", styles, page_ids, 3.2))
    objects.append(_overview_pipe(f"{group_name}_chwr_return_loop", chwr, [{"x": right_x, "y": header_mid_y}, {"x": left_x + 110.0, "y": header_mid_y}, {"x": left_x + 110.0, "y": chiller_y}, {"x": chiller_start_x - 120.0, "y": chiller_y}], "CHWR", styles, page_ids, 2.6))
    objects.append(_overview_pipe(f"{group_name}_cw_condenser_loop", cwr, [{"x": left_x + 20.0, "y": lower_loop_y}, {"x": x0 + w * 0.70, "y": lower_loop_y}, {"x": x0 + w * 0.70, "y": pump_y - 28.0}, {"x": right_x + 42.0, "y": pump_y - 28.0}, {"x": right_x + 42.0, "y": header_mid_y}], "CWR", styles, page_ids, 2.6))
    _add_line_tag(objects, f"{group_name}_chws_tag", chws, left_x + 500.0, header_top_y - 26.0, "CHWS", page_ids)
    _add_line_tag(objects, f"{group_name}_chwr_tag", chwr, left_x + 440.0, header_mid_y - 26.0, "CHWR", page_ids)
    _add_line_tag(objects, f"{group_name}_cwr_tag", cwr, left_x + 380.0, lower_loop_y - 24.0, "CWR", page_ids)
    _add_flow_arrow(objects, f"{group_name}_chws_arrow", right_x, header_top_y, "CHWS", page_ids)
    _add_flow_arrow(objects, f"{group_name}_chwr_arrow", left_x + 110.0, header_mid_y, "CHWR", page_ids, "left")
    _add_flow_arrow(objects, f"{group_name}_cwr_arrow", right_x + 42.0, pump_y - 28.0, "CWR", page_ids)

    chillers = _equipment_by_keywords(equipment, ["-CH-"])[:6]
    pumps = _equipment_by_keywords(equipment, ["-P-"])[:7]
    support = _equipment_by_keywords(equipment, ["-ET-", "-CFS-"])[:2]
    for index, tag in enumerate(chillers):
        x = chiller_start_x + index * chiller_gap
        _add_equipment_with_taps(objects, group_name, tag, x, chiller_y + 48.0, 150.0, 66.0, "CHWS", page_ids, [header_top_y, header_mid_y])
    for index, tag in enumerate(pumps):
        x = pump_start_x + index * pump_gap
        _add_equipment_with_taps(objects, group_name, tag, x, pump_y + 56.0, 82.0, 64.0, "CHWS", page_ids, [header_mid_y, lower_loop_y])
    _place_symbol_row(objects, group_name, support, left_x - 40.0, lower_loop_y + 34.0, 145.0, "CWR", page_ids, lower_loop_y)
    _add_continuation_stack(objects, group_name, band, candidates, styles, "CHWS", page_ids, right_x + 4.0, y0 + 74.0, 34.0, 8)
    return objects


def _overview_hhw_hrw_network(
    group_name: str,
    band: BoundsDict,
    equipment: list[str],
    line_tags_by_system: dict[str, list[str]],
    candidates: list[ContinuationCandidate],
    styles: dict[str, DrawingStyle],
    page_ids: list[str],
) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    x0 = band["x"]
    y0 = band["y"]
    w = band["width"]
    h = band["height"]
    boiler_x = x0 + w * 0.22
    pump_x = x0 + w * 0.54
    hx_x = x0 + w * 0.74
    supply_y = y0 + h * 0.20
    return_y = y0 + h * 0.43
    hrw_y = y0 + h * 0.62
    lower_y = y0 + h * 0.78
    right_x = x0 + w - 275.0
    hhw_supply = _first_tag(line_tags_by_system, "HHWS", "12\"-HHWS-CS02")
    hhw_return = _first_tag(line_tags_by_system, "HHWR", "12\"-HHWR-CS02")

    future_bounds = {"x": x0 + 68.0, "y": y0 + h * 0.15, "width": 300.0, "height": h * 0.68}
    objects.append(_overview_region(f"{group_name}_future", "FUTURE", future_bounds, "#94a3b8", "#ffffff", 0.48, page_ids))
    objects.append(_overview_label(f"{group_name}_future_label", "FUTURE", {"x": future_bounds["x"] + 90.0, "y": future_bounds["y"] + 20.0, "width": 120.0, "height": 20.0}, "#334155", 15.0, page_ids))
    objects.append(_overview_pipe(f"{group_name}_hhws_manifold", hhw_supply, [{"x": boiler_x - 60.0, "y": supply_y}, {"x": right_x, "y": supply_y}, {"x": right_x, "y": return_y}], "HHWS", styles, page_ids, 3.0))
    objects.append(_overview_pipe(f"{group_name}_hhwr_return", hhw_return, [{"x": right_x, "y": return_y}, {"x": pump_x - 220.0, "y": return_y}, {"x": pump_x - 220.0, "y": lower_y}, {"x": boiler_x - 80.0, "y": lower_y}, {"x": boiler_x - 80.0, "y": supply_y}], "HHWR", styles, page_ids, 2.6))
    objects.append(_overview_pipe(f"{group_name}_hrw_recovery_loop", "HRW", [{"x": hx_x - 160.0, "y": hrw_y}, {"x": hx_x + 240.0, "y": hrw_y}, {"x": hx_x + 240.0, "y": lower_y}, {"x": pump_x + 60.0, "y": lower_y}, {"x": pump_x + 60.0, "y": return_y}], "HRW", styles, page_ids, 2.4))
    _add_line_tag(objects, f"{group_name}_hhws_tag", hhw_supply, boiler_x + 350.0, supply_y - 28.0, "HHWS", page_ids)
    _add_line_tag(objects, f"{group_name}_hhwr_tag", hhw_return, boiler_x + 300.0, return_y - 28.0, "HHWR", page_ids)
    _add_line_tag(objects, f"{group_name}_hrw_tag", "HRW", hx_x + 40.0, hrw_y - 26.0, "HRW", page_ids)
    _add_flow_arrow(objects, f"{group_name}_hhws_arrow", right_x, supply_y, "HHWS", page_ids)
    _add_flow_arrow(objects, f"{group_name}_hhwr_arrow", right_x, return_y, "HHWR", page_ids, "left")
    _add_flow_arrow(objects, f"{group_name}_hrw_arrow", hx_x + 240.0, hrw_y, "HRW", page_ids)

    boilers = _equipment_by_keywords(equipment, ["-HWB-", "-BLR-"])[:8]
    pumps = _equipment_by_keywords(equipment, ["-P-"])[:6]
    exchangers = _equipment_by_keywords(equipment, ["-HX-", "-AS-"])[:3]
    _place_symbol_grid(objects, group_name, boilers, boiler_x - 130.0, supply_y + 54.0, 2, 150.0, 88.0, "HHWS", page_ids, [supply_y, return_y])
    _place_symbol_row(objects, group_name, pumps, pump_x - 120.0, lower_y + 28.0, 124.0, "HHWR", page_ids, return_y)
    _place_symbol_row(objects, group_name, exchangers, hx_x - 110.0, hrw_y + 46.0, 150.0, "HRW", page_ids, hrw_y)
    _add_continuation_stack(objects, group_name, band, candidates, styles, "HHWS", page_ids, right_x + 8.0, y0 + 78.0, 34.0, 8)
    return objects


def _overview_generic_network(
    group_name: str,
    band: BoundsDict,
    systems: list[str],
    equipment: list[str],
    line_tags_by_system: dict[str, list[str]],
    candidates: list[ContinuationCandidate],
    styles: dict[str, DrawingStyle],
    page_ids: list[str],
) -> list[DrawingObject]:
    objects: list[DrawingObject] = []
    system_area_x = band["x"] + 260.0
    system_area_right = band["x"] + band["width"] - 260.0
    first_row_y = band["y"] + 118.0
    row_gap = min(80.0, max(58.0, (band["height"] - 250.0) / max(1, len(systems))))
    for row_index, system in enumerate(systems):
        pipe_y = first_row_y + row_index * row_gap
        objects.append(_overview_pipe(f"{group_name}_{system}_generic_main", _first_tag(line_tags_by_system, system, system), [{"x": system_area_x, "y": pipe_y}, {"x": system_area_right, "y": pipe_y}, {"x": system_area_right, "y": pipe_y + 44.0}, {"x": system_area_x + 120.0, "y": pipe_y + 44.0}], system, styles, page_ids, 2.8))
        _add_flow_arrow(objects, f"{group_name}_{system}_generic_arrow", system_area_right, pipe_y, system, page_ids)
    _place_symbol_row(objects, group_name, equipment[:8], system_area_x, band["y"] + band["height"] * 0.56, 160.0, systems[0] if systems else "DEFAULT", page_ids, first_row_y)
    _add_continuation_stack(objects, group_name, band, candidates, styles, systems[0] if systems else "DEFAULT", page_ids, system_area_right + 8.0, band["y"] + 88.0, 36.0, 6)
    return objects


def _first_tag(tags_by_system: dict[str, list[str]], system: str, fallback: str) -> str:
    tags = tags_by_system.get(system, [])
    return tags[0] if tags else fallback


def _equipment_by_keywords(equipment: list[str], keywords: list[str]) -> list[str]:
    return [tag for tag in equipment if any(keyword in tag for keyword in keywords)]


def _add_line_tag(
    objects: list[DrawingObject],
    id_seed: str,
    label: str,
    x: float,
    y: float,
    system: str,
    evidence_ids: list[str],
) -> None:
    objects.append(
        _overview_label(
            id_seed,
            label,
            {"x": x - 78.0, "y": y, "width": 156.0, "height": 16.0},
            SYSTEM_COLORS.get(system, "#111827"),
            9.2,
            evidence_ids,
        )
    )


def _add_flow_arrow(
    objects: list[DrawingObject],
    id_seed: str,
    tip_x: float,
    center_y: float,
    system: str,
    evidence_ids: list[str],
    orientation: str = "right",
) -> None:
    width = 34.0
    height = 24.0
    x = tip_x - width if orientation == "right" else tip_x
    y = center_y - height / 2.0
    objects.append(
        _overview_symbol(
            id_seed,
            "",
            {"x": x, "y": y, "width": width, "height": height},
            SYSTEM_COLORS.get(system, "#334155"),
            evidence_ids,
            "flow_arrow",
            metadata={"orientation": orientation, "tip": {"x": tip_x, "y": center_y}},
        )
    )


def _place_symbol_row(
    objects: list[DrawingObject],
    group_name: str,
    tags: list[str],
    start_x: float,
    y: float,
    gap: float,
    system: str,
    evidence_ids: list[str],
    tap_y: float | None = None,
) -> None:
    for index, tag in enumerate(tags):
        x = start_x + index * gap
        _add_equipment_with_taps(objects, group_name, tag, x, y, 118.0, 60.0, system, evidence_ids, [tap_y] if tap_y is not None else [])


def _place_symbol_grid(
    objects: list[DrawingObject],
    group_name: str,
    tags: list[str],
    start_x: float,
    start_y: float,
    columns: int,
    gap_x: float,
    gap_y: float,
    system: str,
    evidence_ids: list[str],
    tap_ys: list[float],
) -> None:
    for index, tag in enumerate(tags):
        column = index % max(1, columns)
        row = index // max(1, columns)
        x = start_x + column * gap_x
        y = start_y + row * gap_y
        _add_equipment_with_taps(objects, group_name, tag, x, y, 118.0, 60.0, system, evidence_ids, tap_ys)


def _add_equipment_with_taps(
    objects: list[DrawingObject],
    group_name: str,
    tag: str,
    x: float,
    y: float,
    width: float,
    height: float,
    system: str,
    evidence_ids: list[str],
    tap_ys: list[float | None],
) -> None:
    symbol_system = _system_for_tag(tag, group_name) if tag else system
    stroke = SYSTEM_COLORS.get(symbol_system, SYSTEM_COLORS.get(system, "#334155"))
    bounds = {"x": x - width / 2.0, "y": y, "width": width, "height": height}
    objects.append(_overview_symbol(f"equipment_{group_name}_{tag}_{x:.1f}_{y:.1f}", tag, bounds, stroke, evidence_ids))
    center_x = bounds["x"] + bounds["width"] / 2.0
    for index, tap_y in enumerate(tap_ys):
        if tap_y is None:
            continue
        objects.append(
            _overview_pipe(
                f"equipment_tap_{group_name}_{tag}_{index}_{x:.1f}_{y:.1f}",
                "",
                [{"x": center_x, "y": tap_y}, {"x": center_x, "y": y}],
                symbol_system,
                _styles(),
                evidence_ids,
                1.45,
            )
        )
        valve_y = tap_y + (y - tap_y) * 0.34
        objects.append(
            _overview_symbol(
                f"equipment_valve_{group_name}_{tag}_{index}_{x:.1f}_{y:.1f}",
                "",
                {"x": center_x - 11.0, "y": valve_y - 11.0, "width": 22.0, "height": 22.0},
                stroke,
                evidence_ids,
                "valve",
                metadata={"orientation": "vertical"},
            )
        )
        if index == 0:
            objects.append(
                _overview_symbol(
                    f"equipment_instrument_{group_name}_{tag}_{index}_{x:.1f}_{y:.1f}",
                    "",
                    {"x": center_x + 20.0, "y": valve_y - 16.0, "width": 28.0, "height": 28.0},
                    stroke,
                    evidence_ids,
                    "instrument",
                )
            )


def _add_continuation_stack(
    objects: list[DrawingObject],
    group_name: str,
    band: BoundsDict,
    candidates: list[ContinuationCandidate],
    styles: dict[str, DrawingStyle],
    fallback_system: str,
    page_ids: list[str],
    x: float,
    y: float,
    row_gap: float,
    limit: int,
) -> None:
    continuations = _overview_continuations_for_group(candidates, group_name)
    for index, candidate in enumerate(continuations[:limit]):
        target_y = y + index * row_gap
        system = candidate.system or _system_for_tag(candidate.lineTag or candidate.label, group_name) or fallback_system
        evidence_ids = [candidate.id] if candidate.id else page_ids
        objects.append(
            _overview_pipe(
                f"continuation_{group_name}_{index}_{target_y:.1f}",
                "",
                [{"x": x - 160.0, "y": target_y}, {"x": x - 26.0, "y": target_y}],
                system,
                styles,
                evidence_ids,
                1.8,
            )
        )
        objects.append(
            _overview_symbol(
                f"continuation_offpage_{group_name}_{index}_{target_y:.1f}",
                "",
                {"x": x - 42.0, "y": target_y - 15.0, "width": 56.0, "height": 30.0},
                "#111827",
                evidence_ids,
                "offpage",
                metadata={"orientation": "right"},
            )
        )
        objects.append(
            _overview_label(
                f"continuation_label_{group_name}_{index}_{target_y:.1f}",
                _continuation_label(candidate),
                {"x": x + 20.0, "y": target_y - 9.0, "width": min(220.0, band["x"] + band["width"] - x - 24.0), "height": 20.0},
                "#111827",
                9.2,
                evidence_ids,
            )
        )


def _overview_groups(
    pages: list[PageEvidence],
    source_paths: dict[str, str],
) -> list[tuple[str, list[PageEvidence]]]:
    grouped: dict[str, list[PageEvidence]] = {name: [] for name in GROUP_ORDER}
    for page in _sorted_pages(pages):
        grouped[_page_group(page, source_paths)].append(page)
    return [(name, group_pages) for name in GROUP_ORDER if (group_pages := grouped[name])]


def _page_group(page: PageEvidence, source_paths: dict[str, str]) -> str:
    text = _page_search_text(page, source_paths)
    if f"{PROJECT_CODE}-PB" in text or "PLUMBING" in text or "DOMESTIC WATER" in text or "SAFETY SHOWER" in text:
        return "PLUMBING WATER"
    if "CDA" in text:
        return "CDA"
    if "HHW" in text or "HRW" in text:
        return "HHW / HRW"
    if "CHW" in text or "CWS" in text or "CWR" in text or "CW " in text:
        return "CHW / CW"
    return "OTHER"


def _overview_systems_for_group(group_name: str, pages: list[PageEvidence]) -> list[str]:
    text = " ".join(_page_text(page) for page in pages).upper()
    if group_name == "CDA":
        return ["CDA"]
    if group_name == "PLUMBING WATER":
        systems = []
        if "DOMESTIC" in text or "EWH" in text or "TMV" in text:
            systems.append("DOMW")
        if "SAFETY" in text or "SHOWER" in text:
            systems.append("SSW")
        return systems or ["PW"]
    if group_name == "CHW / CW":
        systems = [system for system in ("CHWS", "CHWR", "CWS", "CWR") if system in text]
        return systems or ["CHWS", "CHWR"]
    if group_name == "HHW / HRW":
        systems = [system for system in ("HHWS", "HHWR", "HRW") if system in text]
        return systems or ["HHWS", "HHWR"]
    return ["DEFAULT"]


def _equipment_tags_for_pages(pages: list[PageEvidence]) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for page in pages:
        for span in page.textSpans:
            for match in EQUIPMENT_TAG_RE.finditer(span.text):
                tag = match.group(0).upper()
                if tag not in seen:
                    seen.add(tag)
                    tags.append(tag)
    return sorted(tags, key=_equipment_sort_key)


def _line_tags_for_pages(pages: list[PageEvidence], group_name: str) -> dict[str, list[str]]:
    tags_by_system: dict[str, list[str]] = {}
    seen: set[str] = set()
    for page in pages:
        for span in page.textSpans:
            for match in LINE_TAG_TOKEN_RE.finditer(span.text):
                tag = match.group(0).upper()
                if tag in seen:
                    continue
                seen.add(tag)
                system = _system_for_tag(tag, group_name)
                tags_by_system.setdefault(system, []).append(tag)
    for system, tags in tags_by_system.items():
        tags_by_system[system] = sorted(tags, key=_line_tag_sort_key)
    return tags_by_system


def _line_tag_sort_key(tag: str) -> tuple[int, str]:
    size_match = re.match(r'(\d{1,3})"', tag)
    size = int(size_match.group(1)) if size_match else 999
    return (-size, tag)


def _equipment_sort_key(tag: str) -> tuple[int, str]:
    if "-CH-" in tag:
        return (0, tag)
    if "-HWB-" in tag or "-BLR-" in tag:
        return (0, tag)
    if "-AD-" in tag:
        return (0, tag)
    if "-P-" in tag:
        return (1, tag)
    if "-FLTR-" in tag or "-ST-" in tag or "-ET-" in tag:
        return (2, tag)
    return (3, tag)


def _symbol_type_for_tag(tag: str) -> str:
    text = tag.upper()
    if "-P-" in text or re.match(r"P-(?:\d{1,3}|XX)", text) or "PUMP" in text:
        return "pump"
    if "-CH-" in text or "CHILLER" in text:
        return "chiller"
    if "-HWB-" in text or "BOILER" in text:
        return "boiler"
    if text.startswith("AHU-") or text.startswith("MAU-"):
        return "filter"
    if "-HX-" in text or text.startswith("HX-"):
        return "chiller"
    if "-AD-" in text or "DRYER" in text:
        return "dryer"
    if "-FLTR-" in text:
        return "filter"
    if "-ST-" in text or "-ET-" in text or "TANK" in text:
        return "tank"
    return "equipment"


def _overview_continuations_for_group(candidates: list[ContinuationCandidate], group_name: str) -> list[ContinuationCandidate]:
    seen: set[str] = set()
    items: list[ContinuationCandidate] = []
    for candidate in sorted(candidates, key=lambda item: (item.system, item.lineTag, item.id)):
        system = candidate.system or _system_for_tag(candidate.lineTag or candidate.label, group_name)
        if not _system_belongs_to_group(system, group_name):
            continue
        key = candidate.lineTag or candidate.sheetRef or candidate.evidenceText
        if not key or key in seen:
            continue
        seen.add(key)
        items.append(candidate)
    return items


def _system_belongs_to_group(system: str, group_name: str) -> bool:
    system = system.upper()
    if group_name == "CDA":
        return "CDA" in system
    if group_name == "PLUMBING WATER":
        return system in {"PW", "DOMW", "SSW", "DEFAULT"} or "W" in system
    if group_name == "CHW / CW":
        return "CHW" in system or system in {"CWS", "CWR"}
    if group_name == "HHW / HRW":
        return "HHW" in system or "HRW" in system or system in {"HWS", "HWR"}
    return True


def _system_for_tag(tag: str, group_name: str) -> str:
    text = tag.upper()
    if "CDA" in text:
        return "CDA"
    if "DOMESTIC" in text or "EWH" in text or "TMV" in text:
        return "DOMW"
    if "SAFETY" in text or "SHOWER" in text:
        return "SSW"
    if group_name == "PLUMBING WATER":
        return "PW"
    if "CHWS" in text or "SCHW" in text:
        return "CHWS"
    if "CHWR" in text:
        return "CHWR"
    if "CWS" in text:
        return "CWS"
    if "CWR" in text:
        return "CWR"
    if "HHWS" in text or "HWS" in text:
        return "HHWS"
    if "HHWR" in text or "HWR" in text:
        return "HHWR"
    if "HRW" in text:
        return "HRW"
    if group_name == "HHW / HRW":
        return "HHWS"
    if group_name == "CHW / CW":
        return "CHWS"
    return "CDA" if group_name == "CDA" else "DEFAULT"


def _source_display_name(page: PageEvidence, source_paths: dict[str, str]) -> str:
    source_path = source_paths.get(page.sourceFileId)
    if source_path:
        match = re.search(r"\b" + PROJECT_CODE_PATTERN + r"-[A-Z0-9_.-]+", Path(source_path).stem, re.IGNORECASE)
        if match:
            return match.group(0).upper()
    for span in page.textSpans:
        match = re.search(r"\b" + PROJECT_CODE_PATTERN + r"-[A-Z0-9_.-]+", span.text, re.IGNORECASE)
        if match:
            return match.group(0).upper()
    return f"{page.sourceFileId} p{page.page}"


def _page_search_text(page: PageEvidence, source_paths: dict[str, str]) -> str:
    path_text = Path(source_paths.get(page.sourceFileId, "")).stem
    return f"{path_text} {_page_text(page)}".upper()


def _page_text(page: PageEvidence) -> str:
    return " ".join(span.text for span in page.textSpans)


def _continuation_label(candidate: ContinuationCandidate) -> str:
    target = candidate.sheetRef
    line = candidate.lineTag or _first_line_tag(candidate.evidenceText)
    direction = candidate.direction.upper() if candidate.direction != "unknown" else "REF"
    if line and target:
        return f"{direction} {line} / {target}"
    if line:
        return f"{direction} {line}"
    if target:
        return f"{direction} {target}"
    return direction


def _continuation_line_label(candidate: ContinuationCandidate) -> str:
    line = candidate.lineTag or _first_line_tag(candidate.evidenceText)
    direction = candidate.direction.upper() if candidate.direction != "unknown" else "REF"
    if line:
        return f"{direction} {line}"
    phrase = _continuation_phrase_without_sheet(candidate)
    if phrase and phrase not in {"TO", "FROM", "REF"}:
        return phrase
    return direction


def _continuation_phrase_without_sheet(candidate: ContinuationCandidate) -> str:
    phrase = candidate.label or candidate.evidenceText
    if candidate.sheetRef:
        phrase = re.sub(re.escape(candidate.sheetRef), "", phrase, flags=re.IGNORECASE)
    phrase = LINE_TAG_TOKEN_RE.sub("", phrase)
    phrase = re.sub(r"\s+", " ", phrase).strip(" -_/")
    return phrase[:38].rstrip()


def _first_line_tag(text: str) -> str:
    match = LINE_TAG_TOKEN_RE.search(text)
    return match.group(0).upper() if match else ""


def _overview_region(
    id_seed: str,
    label: str,
    bounds: BoundsDict,
    stroke: str,
    fill: str,
    opacity: float,
    evidence_ids: list[str],
    metadata: dict[str, Any] | None = None,
) -> DrawingObject:
    return DrawingObject(
        id=_object_id("overview_region", id_seed),
        kind="region",
        label=label,
        points=_rect_points(bounds),
        bounds=bounds,
        style=DrawingStyle(stroke=stroke, fill=fill, strokeWidth=1.2, opacity=opacity, dash=[8.0, 5.0]),
        sourceEvidenceIds=evidence_ids,
        locked=False,
        metadata={"overview": True, **(metadata or {})},
    )


def _overview_symbol(
    id_seed: str,
    label: str,
    bounds: BoundsDict,
    stroke: str,
    evidence_ids: list[str],
    symbol_type: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> DrawingObject:
    symbol_metadata: dict[str, Any] = {"overview": True, "symbolType": symbol_type or _symbol_type_for_tag(label)}
    if metadata:
        symbol_metadata.update(metadata)
    return DrawingObject(
        id=_object_id("overview_symbol", id_seed),
        kind="symbol",
        label=label,
        points=_rect_points(bounds),
        bounds=bounds,
        style=DrawingStyle(stroke=stroke, fill="#ffffff", strokeWidth=1.4, opacity=1.0, fontSize=9.0),
        sourceEvidenceIds=evidence_ids,
        locked=False,
        metadata=symbol_metadata,
    )


def _overview_label(
    id_seed: str,
    label: str,
    bounds: BoundsDict,
    color: str,
    font_size: float,
    evidence_ids: list[str],
) -> DrawingObject:
    return DrawingObject(
        id=_object_id("overview_label", id_seed),
        kind="label",
        label=label,
        points=[{"x": bounds["x"], "y": bounds["y"]}],
        bounds=bounds,
        style=DrawingStyle(stroke=color, fill="#ffffff", strokeWidth=0.0, opacity=1.0, fontSize=font_size),
        sourceEvidenceIds=evidence_ids,
        locked=False,
        metadata={"overview": True},
    )


def _overview_pipe(
    id_seed: str,
    label: str,
    points: list[Point],
    system: str,
    styles: dict[str, DrawingStyle],
    evidence_ids: list[str],
    stroke_width: float,
) -> DrawingObject:
    bounds = _points_bounds(points, _PIPE_PADDING)
    style = replace(styles.get(system, styles["DEFAULT"]))
    style.strokeWidth = stroke_width
    return DrawingObject(
        id=_object_id("overview_pipe", id_seed),
        kind="pipe",
        label=label,
        points=points,
        bounds=bounds,
        style=style,
        sourceEvidenceIds=evidence_ids,
        locked=False,
        metadata={"overview": True, "system": system},
    )


def _styles(system_color_map: SystemColorMap | None = None) -> dict[str, DrawingStyle]:
    styles = {
        system: DrawingStyle(stroke=color, fill="none", strokeWidth=2.0, opacity=1.0)
        for system, color in sorted(SYSTEM_COLORS.items())
    }
    if system_color_map is not None:
        for system, entry in system_color_map.entries.items():
            styles[system] = DrawingStyle(stroke=entry.color, fill="none", strokeWidth=2.0, opacity=1.0, dash=entry.dash)
    styles["DEFAULT"] = styles.get("DEFAULT", DrawingStyle(stroke="#111827", fill="none", strokeWidth=2.0, opacity=1.0))
    styles["GAS"] = DrawingStyle(stroke="#111827", fill="none", strokeWidth=1.6, opacity=1.0)
    styles["REVIEW"] = DrawingStyle(stroke="#dc2626", fill="none", strokeWidth=1.0, opacity=1.0, dash=[6.0, 4.0])
    styles["LABEL"] = DrawingStyle(stroke="#334155", fill="#ffffff", strokeWidth=0.8, opacity=1.0, fontSize=12.0)
    styles["SOURCE_FRAGMENT"] = DrawingStyle(stroke="#94a3b8", fill="none", strokeWidth=1.0, opacity=1.0)
    return styles


def _label_style(system: str, styles: dict[str, DrawingStyle], scale: float = 1.0) -> DrawingStyle:
    style = replace(styles["LABEL"])
    style.stroke = styles.get(system, styles["DEFAULT"]).stroke
    style.fontSize = max(5.0, min(12.0, 12.0 * scale))
    return style


def _candidate_transform(
    candidate: ContinuationCandidate,
    page_transforms: dict[tuple[str, int], PageTransform],
    page_by_source: dict[tuple[str, int], PageEvidence],
) -> PageTransform:
    key = (candidate.sourceFileId, candidate.page)
    if key in page_transforms:
        return page_transforms[key]
    page = page_by_source.get(key)
    return {
        "x": _PAGE_MARGIN,
        "y": _PAGE_MARGIN,
        "scale": 1.0,
        "cropX": page.cropBounds["x"] if page else 0.0,
        "cropY": page.cropBounds["y"] if page else 0.0,
    }


def _offset_bounds(bounds: BoundsDict, transform: PageTransform) -> BoundsDict:
    scale = transform["scale"]
    return {
        "x": transform["x"] + (bounds["x"] - transform["cropX"]) * scale,
        "y": transform["y"] + (bounds["y"] - transform["cropY"]) * scale,
        "width": bounds["width"] * scale,
        "height": bounds["height"] * scale,
    }


def _center(bounds: BoundsDict) -> Point:
    return {"x": bounds["x"] + bounds["width"] / 2.0, "y": bounds["y"] + bounds["height"] / 2.0}


def _anchor(bounds: BoundsDict, edge: Literal["left", "right", "top", "bottom", "inside"]) -> Point:
    center = _center(bounds)
    if edge == "left":
        return {"x": bounds["x"], "y": center["y"]}
    if edge == "right":
        return {"x": bounds["x"] + bounds["width"], "y": center["y"]}
    if edge == "top":
        return {"x": center["x"], "y": bounds["y"]}
    if edge == "bottom":
        return {"x": center["x"], "y": bounds["y"] + bounds["height"]}
    return center


def _orthogonal_points(start: Point, end: Point) -> list[Point]:
    midpoint_x = (start["x"] + end["x"]) / 2.0
    points = [start, {"x": midpoint_x, "y": start["y"]}, {"x": midpoint_x, "y": end["y"]}, end]
    return _dedupe_adjacent_points(points)


def _dedupe_adjacent_points(points: list[Point]) -> list[Point]:
    deduped: list[Point] = []
    for point in points:
        if not deduped or point != deduped[-1]:
            deduped.append(point)
    return deduped


def _points_bounds(points: list[Point], padding: float = 0.0) -> BoundsDict:
    min_x = min(point["x"] for point in points) - padding
    min_y = min(point["y"] for point in points) - padding
    max_x = max(point["x"] for point in points) + padding
    max_y = max(point["y"] for point in points) + padding
    return {"x": min_x, "y": min_y, "width": max_x - min_x, "height": max_y - min_y}


def _rect_points(bounds: BoundsDict) -> list[Point]:
    x = bounds["x"]
    y = bounds["y"]
    right = x + bounds["width"]
    bottom = y + bounds["height"]
    return [{"x": x, "y": y}, {"x": right, "y": y}, {"x": right, "y": bottom}, {"x": x, "y": bottom}]


def _document_size(objects: list[DrawingObject]) -> tuple[float, float]:
    if not objects:
        return _PAGE_MARGIN * 2.0, _PAGE_MARGIN * 2.0
    max_x = max(obj.bounds["x"] + obj.bounds["width"] for obj in objects)
    max_y = max(obj.bounds["y"] + obj.bounds["height"] for obj in objects)
    return max_x + _PAGE_MARGIN, max_y + _PAGE_MARGIN


def _clamp_score(score: float) -> float:
    return max(0.0, min(100.0, score))


def _count_disconnected(candidates: list[ContinuationCandidate], matches: list[ContinuationMatch]) -> int:
    connected_ids = set()
    for match in matches:
        connected_ids.add(match.sourceCandidateId)
        connected_ids.add(match.targetCandidateId)
    return sum(1 for candidate in candidates if candidate.id not in connected_ids)


def _count_label_overlaps(labels: list[DrawingObject]) -> int:
    overlaps = 0
    for index, label in enumerate(labels):
        for other in labels[index + 1 :]:
            if _bounds_overlap(label.bounds, other.bounds):
                overlaps += 1
    return overlaps


def _count_crossings(pipes: list[DrawingObject]) -> int:
    crossings = 0
    for index, pipe in enumerate(pipes):
        for other in pipes[index + 1 :]:
            crossings += _segment_crossings(_segments(pipe.points), _segments(other.points))
    return crossings


def _segments(points: list[Point]) -> list[tuple[Point, Point]]:
    return list(zip(points, points[1:]))


def _segment_crossings(
    segments: Iterable[tuple[Point, Point]],
    other_segments: Iterable[tuple[Point, Point]],
) -> int:
    crossings = 0
    for first_start, first_end in segments:
        for second_start, second_end in other_segments:
            if _segments_intersect(first_start, first_end, second_start, second_end):
                crossings += 1
    return crossings


def _segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    if a in (c, d) or b in (c, d):
        return False
    if _is_vertical(a, b) and _is_horizontal(c, d):
        return _between(a["x"], c["x"], d["x"]) and _between(c["y"], a["y"], b["y"])
    if _is_horizontal(a, b) and _is_vertical(c, d):
        return _between(c["x"], a["x"], b["x"]) and _between(a["y"], c["y"], d["y"])
    return False


def _is_vertical(a: Point, b: Point) -> bool:
    return a["x"] == b["x"] and a["y"] != b["y"]


def _is_horizontal(a: Point, b: Point) -> bool:
    return a["y"] == b["y"] and a["x"] != b["x"]


def _between(value: float, start: float, end: float) -> bool:
    return min(start, end) < value < max(start, end)


def _bounds_overlap(first: BoundsDict, second: BoundsDict) -> bool:
    return (
        first["x"] < second["x"] + second["width"]
        and first["x"] + first["width"] > second["x"]
        and first["y"] < second["y"] + second["height"]
        and first["y"] + first["height"] > second["y"]
    )


def _object_id(prefix: str, *parts: Any) -> str:
    slug = _slug("_".join(str(part) for part in parts))
    return f"{prefix}_{slug}_{_stable_hash(*parts)}"


def _stable_hash(*parts: Any) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()[:10]


def _slug(value: Any) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")
    return slug or "item"
