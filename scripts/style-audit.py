#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from recreation_extractor.models import to_dict
from recreation_extractor.pid_stitch.evidence import extract_pid_evidence, find_continuation_candidates
from recreation_extractor.pid_stitch.export import export_drawing_svg
from recreation_extractor.pid_stitch.layout import (
    EQUIPMENT_TAG_RE,
    INSTRUMENT_TAG_RE,
    LINE_TAG_TOKEN_RE,
    _clean_source_token,
    generate_layout_options,
)
from recreation_extractor.pid_stitch.matching import rank_continuation_matches
from recreation_extractor.pid_stitch.visio_template import load_visio_template_objects, style_profile_from_objects


DEFAULT_GROUPS_DIR = Path("data/pid-groups")
DEFAULT_VISIO_DIR = Path("data/visio-templates")
DEFAULT_OUTPUT = Path("data/style-audit.json")
TAG_REGEXES = (LINE_TAG_TOKEN_RE, EQUIPMENT_TAG_RE, INSTRUMENT_TAG_RE)


class AuditFailure(RuntimeError):
    pass


def run_audit(groups_dir: Path, visio_dir: Path, svg_output_dir: Path | None = None) -> dict[str, Any]:
    groups = _group_directories(groups_dir)
    reference_profiles = _load_reference_profiles(visio_dir)
    svg_output_dir = svg_output_dir or _svg_output_dir_for(DEFAULT_OUTPUT)
    group_summaries: list[dict[str, Any]] = []

    for group_dir in groups:
        group_summary = _audit_group(group_dir, reference_profiles, svg_output_dir)
        group_summaries.append(group_summary)

    totals = _aggregate_totals(group_summaries)
    return {
        "groups": len(group_summaries),
        "groupsDir": str(groups_dir),
        "visioDir": str(visio_dir),
        "svgOutputDir": str(svg_output_dir),
        "referenceProfiles": [_profile_to_dict(profile) for profile in reference_profiles],
        "totals": totals,
        "groupSummaries": group_summaries,
    }


def summarize_drawing(name: str, drawing: dict[str, Any], reference_profiles: list[Any]) -> dict[str, Any]:
    drawing = _to_plain_dict(drawing)
    objects = [obj for obj in drawing.get("objects", []) if isinstance(obj, dict)]
    source_tags = _source_tags(drawing.get("sourcePages", []))
    represented = _represented_tags(objects)
    hidden_inventory = _hidden_inventory_tags(objects)
    missing = [tag for tag in source_tags if _norm_token(tag) not in represented]
    source_vector_coverage = _source_vector_color_coverage(objects)
    line_weight_metrics = _line_weight_metrics(objects)
    visible_coverage = _visible_coverage_metrics(source_tags, represented, hidden_inventory)

    detected_systems = sorted(
        {
            str(metadata.get("system")).upper()
            for obj in objects
            for metadata in [_metadata(obj)]
            if isinstance(metadata.get("system"), str) and str(metadata.get("system")).upper() != "DEFAULT"
        }
    )
    line_colors = _line_colors(objects)
    legend_entries = _legend_entry_count(objects)
    profile_matches = _style_profile_matches(line_colors, reference_profiles)

    return {
        "name": name,
        "objects": len(objects),
        "sourcePages": len([page for page in drawing.get("sourcePages", []) if isinstance(page, dict)]),
        "detectedSystems": detected_systems,
        "lineColors": line_colors,
        "legendEntries": legend_entries,
        "hiddenFrames": _hidden_frame_count(objects),
        "hiddenInventoryTags": len(hidden_inventory),
        "hiddenInventorySample": hidden_inventory[:25],
        "missingTags": len(missing),
        "missingSample": missing[:25],
        "sourceVectorColorCoverage": source_vector_coverage,
        "sourceDerivedPipeVectors": source_vector_coverage["total"],
        "sourceDerivedPipeVectorsRecoloredBySystem": source_vector_coverage["colored"],
        "sourceDerivedPipeVectorsRecoloredBySystemPercent": _ratio(source_vector_coverage["colored"] * 100.0, source_vector_coverage["total"]),
        "dominantConnectorLineWeight": line_weight_metrics["dominantConnectorLineWeight"],
        "dominantSourceLineWeight": line_weight_metrics["dominantSourceLineWeight"],
        "connectorLineObjects": line_weight_metrics["connectorLineObjects"],
        "sourceLineObjects": line_weight_metrics["sourceLineObjects"],
        "connectorToSourceRatio": line_weight_metrics["connectorToSourceRatio"],
        "hiddenVsVisibleCoverage": visible_coverage,
        "paletteOverlap": _best_palette_overlap(line_colors, reference_profiles),
        "styleProfileMatches": profile_matches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit source-driven layout output against Visio style profiles.")
    parser.add_argument("--groups-dir", type=Path, default=DEFAULT_GROUPS_DIR)
    parser.add_argument("--visio-dir", type=Path, default=DEFAULT_VISIO_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    output_path = args.output.expanduser()
    result = run_audit(args.groups_dir.expanduser(), args.visio_dir.expanduser(), _svg_output_dir_for(output_path))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def _audit_group(group_dir: Path, reference_profiles: list[Any], svg_output_dir: Path) -> dict[str, Any]:
    pdfs = sorted(path for path in group_dir.iterdir() if path.is_file() and path.suffix.lower() == ".pdf")
    if not pdfs:
        raise AuditFailure(f"No PDFs found for group: {group_dir}")

    project_id = f"style_audit_{_slug(group_dir.name)}"
    pages = []
    candidates = []
    source_paths: dict[str, str] = {}
    for index, pdf in enumerate(pdfs, start=1):
        source_file_id = f"source_{index}_{_slug(pdf.stem)}"
        source_paths[source_file_id] = str(pdf)
        extracted_pages = extract_pid_evidence(project_id, source_file_id, str(pdf))
        pages.extend(extracted_pages)
        candidates.extend(find_continuation_candidates(extracted_pages))

    matches = rank_continuation_matches(candidates, source_paths=source_paths)
    options = generate_layout_options(project_id, pages, candidates, matches, source_paths=source_paths)
    option, document = _primary_semantic_or_source_option(options)
    drawing = to_dict(document)
    svg_path = svg_output_dir / f"{_slug(group_dir.name)}.svg"
    export_drawing_svg(drawing, svg_path)

    summary = summarize_drawing(group_dir.name, drawing, reference_profiles)
    summary.update(
        {
            "group": group_dir.name,
            "pdfs": len(pdfs),
            "candidates": len(candidates),
            "matches": len([match for match in matches if match.status != "rejected"]),
            "layoutOption": option.id,
            "drawingId": document.id,
            "svgPath": str(svg_path),
            "sourceFiles": [str(path) for path in pdfs],
        }
    )
    return summary


def _primary_semantic_or_source_option(options: list[tuple[Any, Any]]) -> tuple[Any, Any]:
    for option, document in options:
        metrics = getattr(option, "metrics", {}) or {}
        if metrics.get("semanticOverlay") and metrics.get("primaryOutput"):
            return option, document
    return _source_driven_option(options)


def _source_driven_option(options: list[tuple[Any, Any]]) -> tuple[Any, Any]:
    for option, document in options:
        metrics = getattr(option, "metrics", {}) or {}
        if metrics.get("sourceDriven") and metrics.get("primaryOutput"):
            return option, document
    for option, document in options:
        if "source_driven" in getattr(option, "id", "") or "source_driven" in getattr(document, "id", ""):
            return option, document
    raise AuditFailure("No source-driven drawing option was generated")


def _group_directories(groups_dir: Path) -> list[Path]:
    if not groups_dir.exists():
        raise AuditFailure(f"Groups directory does not exist: {groups_dir}")
    groups = [
        path
        for path in sorted(groups_dir.iterdir())
        if path.is_dir() and any(child.is_file() and child.suffix.lower() == ".pdf" for child in path.iterdir())
    ]
    if groups:
        return groups
    if any(path.is_file() and path.suffix.lower() == ".pdf" for path in groups_dir.iterdir()):
        return [groups_dir]
    raise AuditFailure(f"No PDF groups found in: {groups_dir}")


def _load_reference_profiles(visio_dir: Path) -> list[Any]:
    old_template_dir = os.environ.get("RECREATION_VISIO_TEMPLATE_DIR")
    os.environ["RECREATION_VISIO_TEMPLATE_DIR"] = str(visio_dir)
    try:
        references = [
            ("CHW / CW", "compiled_chw_cw_reference"),
            ("CHW / CW", "compiled_chw_ctw_baseline"),
            ("HHW / HRW", "compiled_hhw_hrw_reference"),
        ]
        profiles = []
        seen_paths: set[str] = set()
        for group_name, slug in references:
            objects, stats = load_visio_template_objects(group_name, slug, [])
            if not objects:
                continue
            path = stats.path if stats is not None else f"{group_name}:{slug}"
            if path in seen_paths:
                continue
            seen_paths.add(path)
            profiles.append(style_profile_from_objects(path, objects))
        return profiles
    finally:
        if old_template_dir is None:
            os.environ.pop("RECREATION_VISIO_TEMPLATE_DIR", None)
        else:
            os.environ["RECREATION_VISIO_TEMPLATE_DIR"] = old_template_dir


def _aggregate_totals(group_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    source_vectors = sum(int(group.get("sourceDerivedPipeVectors", 0)) for group in group_summaries)
    recolored_vectors = sum(int(group.get("sourceDerivedPipeVectorsRecoloredBySystem", 0)) for group in group_summaries)
    connector_lines = sum(int(group.get("connectorLineObjects", 0)) for group in group_summaries)
    source_lines = sum(int(group.get("sourceLineObjects", 0)) for group in group_summaries)

    hidden_visible = [group.get("hiddenVsVisibleCoverage", {}) for group in group_summaries]
    source_tags = sum(int(metrics.get("sourceTags", 0)) for metrics in hidden_visible if isinstance(metrics, dict))
    visible_tags = sum(int(metrics.get("visibleCoveredTags", 0)) for metrics in hidden_visible if isinstance(metrics, dict))
    hidden_tags = sum(int(metrics.get("hiddenInventoryTags", 0)) for metrics in hidden_visible if isinstance(metrics, dict))

    palette_overlaps = [group.get("paletteOverlap", {}) for group in group_summaries]
    overlap_ratios = [
        float(overlap.get("overlapRatio", 0.0))
        for overlap in palette_overlaps
        if isinstance(overlap, dict)
    ]
    return {
        "pdfs": sum(int(group.get("pdfs", 0)) for group in group_summaries),
        "missingTags": sum(int(group.get("missingTags", 0)) for group in group_summaries),
        "legendEntries": sum(int(group.get("legendEntries", 0)) for group in group_summaries),
        "sourceDerivedPipeVectors": source_vectors,
        "sourceDerivedPipeVectorsRecoloredBySystem": recolored_vectors,
        "sourceDerivedPipeVectorsRecoloredBySystemPercent": _ratio(recolored_vectors * 100.0, source_vectors),
        "connectorLineObjects": connector_lines,
        "sourceLineObjects": source_lines,
        "connectorToSourceRatio": _ratio(connector_lines, source_lines),
        "hiddenVsVisibleCoverage": {
            "sourceTags": source_tags,
            "visibleCoveredTags": visible_tags,
            "hiddenInventoryTags": hidden_tags,
            "visibleCoverageRatio": _ratio(visible_tags, source_tags),
            "hiddenToVisibleRatio": _ratio(hidden_tags, visible_tags),
        },
        "averagePaletteOverlapRatio": round(sum(overlap_ratios) / len(overlap_ratios), 3) if overlap_ratios else 0.0,
        "bestPaletteOverlapRatio": max(overlap_ratios, default=0.0),
    }


def _source_tags(source_pages: Iterable[Any]) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for page in source_pages:
        page_dict = _to_plain_dict(page)
        for span in page_dict.get("textSpans", []):
            text = _text_from_span(span)
            for tag in _tags_in_text(text):
                key = _norm_token(tag)
                if key in seen:
                    continue
                seen.add(key)
                tags.append(tag)
    return tags


def _represented_tags(objects: Iterable[dict[str, Any]]) -> set[str]:
    represented: set[str] = set()
    for obj in objects:
        if _is_hidden_inventory(obj):
            continue
        for value in _object_strings(obj):
            for tag in _tags_in_text(value):
                represented.add(_norm_token(tag))
    return represented


def _hidden_inventory_tags(objects: Iterable[dict[str, Any]]) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for obj in objects:
        if not _is_hidden_inventory(obj):
            continue
        for value in _object_strings(obj):
            for tag in _tags_in_text(value):
                key = _norm_token(tag)
                if key in seen:
                    continue
                seen.add(key)
                tags.append(tag)
    return tags


def _is_hidden_inventory(obj: dict[str, Any]) -> bool:
    metadata = _metadata(obj)
    if metadata.get("sourceCoverageRole") == "instrumentInventory":
        return True
    style = obj.get("style") if isinstance(obj.get("style"), dict) else {}
    bounds = obj.get("bounds") if isinstance(obj.get("bounds"), dict) else {}
    return (
        metadata.get("sourceCoverage") is True
        and float(style.get("opacity") or 1.0) <= 0.0
        and float(bounds.get("width") or 0.0) <= 1.0
        and float(bounds.get("height") or 0.0) <= 1.0
    )


def _tags_in_text(text: str) -> list[str]:
    tags: list[str] = []
    for regex in TAG_REGEXES:
        tags.extend(_clean_source_token(match.group(0)) for match in regex.finditer(text or ""))
    return list(dict.fromkeys(tags))


def _object_strings(obj: dict[str, Any]) -> Iterable[str]:
    label = obj.get("label")
    if isinstance(label, str):
        yield label
    yield from _string_values(obj.get("metadata", {}))


def _string_values(value: Any) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for child in value.values():
            yield from _string_values(child)
    elif isinstance(value, list):
        for child in value:
            yield from _string_values(child)


def _text_from_span(span: Any) -> str:
    span_dict = _to_plain_dict(span)
    return str(span_dict.get("text") or "")


def _metadata(obj: dict[str, Any]) -> dict[str, Any]:
    metadata = obj.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _line_colors(objects: Iterable[dict[str, Any]]) -> list[str]:
    colors: dict[str, int] = {}
    for obj in objects:
        if obj.get("kind") not in {"pipe", "connector"}:
            continue
        style = obj.get("style") if isinstance(obj.get("style"), dict) else {}
        stroke = str(style.get("stroke") or "").lower()
        if re.fullmatch(r"#[0-9a-f]{6}", stroke):
            colors[stroke] = colors.get(stroke, 0) + 1
    return [color for color, _count in sorted(colors.items(), key=lambda item: (-item[1], item[0]))]


def _source_vector_color_coverage(objects: Iterable[dict[str, Any]]) -> dict[str, Any]:
    total = 0
    colored = 0
    by_system: dict[str, int] = {}
    for obj in objects:
        if not _is_source_derived_pipe_vector(obj):
            continue
        total += 1
        metadata = _metadata(obj)
        system = str(metadata.get("system") or "DEFAULT").upper()
        if metadata.get("systemColorApplied") is True and system != "DEFAULT":
            colored += 1
            by_system[system] = by_system.get(system, 0) + 1
    return {
        "colored": colored,
        "total": total,
        "ratio": _ratio(colored, total),
        "bySystem": dict(sorted(by_system.items())),
    }


def _line_weight_metrics(objects: Iterable[dict[str, Any]]) -> dict[str, Any]:
    connector_weights: list[float] = []
    source_weights: list[float] = []
    for obj in objects:
        if obj.get("kind") not in {"pipe", "connector"}:
            continue
        weight = _line_weight(obj)
        if weight is None:
            continue
        if _is_source_derived_pipe_vector(obj):
            source_weights.append(weight)
        else:
            connector_weights.append(weight)

    connector_count = len(connector_weights)
    source_count = len(source_weights)
    return {
        "connectorLineObjects": connector_count,
        "sourceLineObjects": source_count,
        "dominantConnectorLineWeight": _dominant_number(connector_weights),
        "dominantSourceLineWeight": _dominant_number(source_weights),
        "connectorToSourceRatio": _ratio(connector_count, source_count),
    }


def _visible_coverage_metrics(source_tags: list[str], represented: set[str], hidden_inventory: list[str]) -> dict[str, Any]:
    source_keys = {_norm_token(tag) for tag in source_tags}
    hidden_keys = {_norm_token(tag) for tag in hidden_inventory}
    visible_keys = source_keys & represented
    visible_not_hidden = visible_keys - hidden_keys
    return {
        "sourceTags": len(source_keys),
        "visibleCoveredTags": len(visible_keys),
        "visibleNonInventoryTags": len(visible_not_hidden),
        "hiddenInventoryTags": len(hidden_keys),
        "hiddenToVisibleRatio": _ratio(len(hidden_keys), len(visible_keys)),
        "visibleCoverageRatio": _ratio(len(visible_keys), len(source_keys)),
    }


def _best_palette_overlap(line_colors: list[str], reference_profiles: list[Any]) -> dict[str, Any]:
    drawing_colors = {color.lower() for color in line_colors}
    best: dict[str, Any] = {
        "path": None,
        "drawingColorCount": len(drawing_colors),
        "referenceColorCount": 0,
        "overlapCount": 0,
        "overlapRatio": 0.0,
        "matchedLineColors": [],
        "missingReferenceColors": [],
    }
    for profile in reference_profiles:
        profile_dict = _profile_to_dict(profile)
        reference_colors = {str(color).lower() for color in profile_dict.get("dominantLineColors", [])}
        matched_colors = sorted(drawing_colors & reference_colors)
        overlap = {
            "path": profile_dict.get("path"),
            "drawingColorCount": len(drawing_colors),
            "referenceColorCount": len(reference_colors),
            "overlapCount": len(matched_colors),
            "overlapRatio": _ratio(len(matched_colors), len(reference_colors)),
            "matchedLineColors": matched_colors,
            "missingReferenceColors": sorted(reference_colors - drawing_colors),
        }
        if (overlap["overlapRatio"], overlap["overlapCount"]) > (best["overlapRatio"], best["overlapCount"]):
            best = overlap
    return best


def _is_source_derived_pipe_vector(obj: dict[str, Any]) -> bool:
    if obj.get("kind") != "pipe":
        return False
    metadata = _metadata(obj)
    return metadata.get("sourceDerived") is True or (
        isinstance(metadata.get("sourceVectorId"), str) and metadata.get("singleSheetReconstructionVector") is True
    )


def _line_weight(obj: dict[str, Any]) -> float | None:
    style = obj.get("style") if isinstance(obj.get("style"), dict) else {}
    try:
        value = float(style.get("strokeWidth"))
    except (TypeError, ValueError):
        return None
    if value <= 0:
        return None
    return round(value, 3)


def _dominant_number(values: list[float]) -> float | None:
    counts: dict[float, int] = {}
    for value in values:
        counts[value] = counts.get(value, 0) + 1
    if not counts:
        return None
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))[0][0]


def _ratio(numerator: int | float, denominator: int | float) -> float:
    return round(float(numerator) / float(denominator), 3) if denominator else 0.0


def _legend_entry_count(objects: Iterable[dict[str, Any]]) -> int:
    return sum(
        1
        for obj in objects
        if obj.get("kind") == "label"
        and _metadata(obj).get("sourceDrivenLegend") is True
        and isinstance(_metadata(obj).get("system"), str)
    )


def _hidden_frame_count(objects: Iterable[dict[str, Any]]) -> int:
    return sum(1 for obj in objects if obj.get("kind") == "region" and _metadata(obj).get("stitchedSourcePageTile") is True)


def _style_profile_matches(line_colors: list[str], reference_profiles: list[Any]) -> list[dict[str, Any]]:
    color_set = set(line_colors)
    matches = []
    for profile in reference_profiles:
        profile_dict = _profile_to_dict(profile)
        reference_colors = {str(color).lower() for color in profile_dict.get("dominantLineColors", [])}
        matched_colors = sorted(color_set & reference_colors)
        missing_reference_colors = sorted(reference_colors - color_set)
        matches.append(
            {
                "path": profile_dict.get("path"),
                "lineColorOverlap": len(matched_colors),
                "lineColorOverlapRatio": round(len(matched_colors) / max(1, len(reference_colors)), 3),
                "matchedLineColors": matched_colors,
                "missingReferenceColors": missing_reference_colors,
                "legendSystems": profile_dict.get("legendSystems", []),
                "pointerLikeObjects": profile_dict.get("pointerLikeObjects", 0),
                "zoneLikeObjects": profile_dict.get("zoneLikeObjects", 0),
            }
        )
    return matches


def _profile_to_dict(profile: Any) -> dict[str, Any]:
    if is_dataclass(profile):
        return asdict(profile)
    if isinstance(profile, dict):
        return profile
    return {
        "path": getattr(profile, "path", ""),
        "dominantLineColors": list(getattr(profile, "dominantLineColors", [])),
        "legendSystems": list(getattr(profile, "legendSystems", [])),
        "lineWeights": list(getattr(profile, "lineWeights", [])),
        "pointerLikeObjects": getattr(profile, "pointerLikeObjects", 0),
        "zoneLikeObjects": getattr(profile, "zoneLikeObjects", 0),
        "objectCount": getattr(profile, "objectCount", 0),
    }


def _to_plain_dict(value: Any) -> Any:
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, dict):
        return {key: _to_plain_dict(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_plain_dict(item) for item in value]
    return value


def _norm_token(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "", value.upper())


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "group"


def _svg_output_dir_for(output_path: Path) -> Path:
    return output_path.with_suffix("")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AuditFailure as exc:
        raise SystemExit(str(exc)) from exc
