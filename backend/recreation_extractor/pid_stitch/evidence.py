from __future__ import annotations

from math import atan2, degrees, isfinite
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable, Literal

import fitz

from recreation_extractor.conventions import PROJECT_CODE, PROJECT_CODE_PATTERN
from recreation_extractor.pid_stitch.models import BoundsDict, ContinuationCandidate, PageEvidence, Point, TextSpan, VectorSegment


# The lookbehind keeps equipment tags such as R-DEMO-CHW-P-01 from reading as a sheet reference.
SHEET_REF_RE = re.compile(r"(?<![A-Z0-9]-)\b" + PROJECT_CODE_PATTERN + r"-[A-Z0-9][A-Z0-9_.-]*\b", re.IGNORECASE)
LINE_TAG_RE = re.compile(r'\b(?:\d{1,3}(?:\s+\d/\d)?|\d/\d)"-[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b', re.IGNORECASE)
SYSTEM_RE = re.compile(r"\b(?:CHWS|CHWR|SCHWS|SCHWR|TSCHWS|TSCHWR|CWS|CWR|HHWS|HHWR|HRW|CDA|IA|CA|ICW|TCHWS|TCHWR|TCHW|POTCW)\b", re.IGNORECASE)

EDGE_ZONE_RATIO = 0.16
OCR_WEAK_TEXT_SPAN_THRESHOLD = 4
OCR_VECTOR_HEAVY_THRESHOLD = 1000
# A page whose raster images cover at least this share of the page is treated as a scan.
OCR_RASTER_COVERAGE_THRESHOLD = 0.5
OCR_DEFAULT_DPI = 250
OCR_RENDERED_TESSERACT_DPI = 160
Edge = Literal["left", "right", "top", "bottom", "inside"]
Direction = Literal["to", "from", "unknown"]
OcrMode = Literal["auto", "always", "never"]


def extract_pid_evidence(project_id: str, source_file_id: str, pdf_path: str | Path, *, ocr_mode: OcrMode = "auto") -> list[PageEvidence]:
    del project_id
    doc = fitz.open(Path(pdf_path))
    try:
        pages: list[PageEvidence] = []
        for page_index, page in enumerate(doc, start=1):
            text_spans = _extract_text_spans(page)
            drawings = page.get_drawings()
            vector_segments = _extract_vector_segments(drawings, f"{source_file_id}_p{page_index}")
            text_spans, text_extraction = _apply_ocr_fallback(page, text_spans, len(drawings), ocr_mode=ocr_mode)
            crop_box = page.cropbox
            pages.append(
                PageEvidence(
                    id=f"{source_file_id}_p{page_index}",
                    sourceFileId=source_file_id,
                    page=page_index,
                    width=float(page.rect.width),
                    height=float(page.rect.height),
                    rotation=int(page.rotation),
                    cropBounds={
                        "x": float(crop_box.x0),
                        "y": float(crop_box.y0),
                        "width": float(crop_box.width),
                        "height": float(crop_box.height),
                    },
                    textSpans=text_spans,
                    vectorCount=len(drawings),
                    vectorSegments=vector_segments,
                    metadata={"textExtraction": text_extraction},
                )
            )
        return pages
    finally:
        doc.close()


def find_continuation_candidates(pages: list[PageEvidence]) -> list[ContinuationCandidate]:
    candidates: list[ContinuationCandidate] = []
    seen: set[tuple[str, int, str, str, Direction, Edge, str, int, int]] = set()
    external_seen: set[tuple[str, int, str, str, str, str, str, str]] = set()

    for page in pages:
        for span in page.textSpans:
            edge = _span_edge(span, page.width, page.height)
            if edge == "inside":
                continue

            neighborhood = _nearby_spans(page.textSpans, span, page.width, page.height)
            evidence_text = " ".join(item.text.strip() for item in neighborhood if item.text.strip())
            direction = _direction_from_text(evidence_text)
            sheet_ref = _first_match(SHEET_REF_RE, evidence_text)
            line_tag = _first_match(LINE_TAG_RE, evidence_text)
            system = _first_match(SYSTEM_RE, evidence_text)
            metadata = _flow_callout_metadata(page, neighborhood, span, direction, sheet_ref, line_tag, system)
            if metadata:
                direction = metadata.get("direction", direction)
                sheet_ref = metadata.get("sourceDrawingRef", sheet_ref)
                line_tag = metadata.get("lineTag", line_tag)
                system = metadata.get("system", system)
                evidence_text = metadata.get("evidenceText", evidence_text)

            if direction == "unknown" and not sheet_ref and not line_tag:
                continue

            bounds = _union_bounds(neighborhood)
            if _is_red_markup_annotation(neighborhood, direction, sheet_ref, line_tag):
                continue

            if _is_prose_continuation_noise(evidence_text, direction, sheet_ref, line_tag):
                continue

            if _is_edge_title_or_revision_noise(page, edge, bounds, evidence_text, direction, sheet_ref, line_tag):
                continue

            if metadata.get("externalFlowLabel"):
                external_key = (
                    page.sourceFileId,
                    page.page,
                    metadata.get("externalFlowRole", ""),
                    metadata.get("externalFlowLabel", ""),
                    metadata.get("sourceDrawingRef", ""),
                    metadata.get("lineTag", ""),
                    metadata.get("direction", ""),
                    metadata.get("calloutAnchor", ""),
                )
                if external_key in external_seen:
                    continue
                external_seen.add(external_key)

            dedupe_key = (
                page.sourceFileId,
                page.page,
                sheet_ref,
                line_tag,
                direction,
                edge,
                _normalized_local_label(evidence_text),
                int((bounds["x"] + bounds["width"] / 2.0) // _bucket_size(page.width)),
                int((bounds["y"] + bounds["height"] / 2.0) // _bucket_size(page.height)),
            )
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            if _duplicates_existing_callout(candidates, page, sheet_ref, line_tag, direction, bounds):
                continue

            candidates.append(
                ContinuationCandidate(
                    id=f"{page.id}:cont_{len(candidates) + 1}",
                    sourceFileId=page.sourceFileId,
                    page=page.page,
                    sheetRef=sheet_ref,
                    direction=direction,
                    label=evidence_text,
                    lineTag=line_tag,
                    system=system,
                    edge=edge,
                    position=_center_point(span),
                    bounds=bounds,
                    confidence=0.9 if metadata.get("externalFlowLabel") else 0.85 if sheet_ref or line_tag else 0.62,
                    evidenceText=evidence_text,
                    metadata=metadata,
                )
            )

    return candidates


def _extract_text_spans(page: fitz.Page) -> list[TextSpan]:
    return _extract_text_spans_from_dict(page.get_text("dict"))


def _extract_text_spans_from_dict(text_dict: dict) -> list[TextSpan]:
    text_spans: list[TextSpan] = []
    for block in text_dict.get("blocks", []):
        for line in block.get("lines", []):
            rotation = _rotation_from_line(line)
            for span in line.get("spans", []):
                text = str(span.get("text", "")).strip()
                if not text:
                    continue
                x0, y0, x1, y1 = span.get("bbox", (0.0, 0.0, 0.0, 0.0))
                text_spans.append(
                    TextSpan(
                        text=text,
                        x=float(x0),
                        y=float(y0),
                        width=float(x1 - x0),
                        height=float(y1 - y0),
                        rotation=rotation,
                        color=_text_color_to_hex(span.get("color")),
                    )
                )
    return text_spans


def _apply_ocr_fallback(page: fitz.Page, native_spans: list[TextSpan], vector_count: int, *, ocr_mode: OcrMode) -> tuple[list[TextSpan], dict[str, object]]:
    image_coverage = _raster_image_coverage(page) if ocr_mode == "auto" else 0.0
    should_ocr = _should_run_ocr(native_spans, vector_count, ocr_mode=ocr_mode, image_coverage=image_coverage)
    base_metadata: dict[str, object] = {
        "mode": "native",
        "nativeSpanCount": len(native_spans),
        "ocrSpanCount": 0,
        "vectorCount": vector_count,
        "imageCoverage": round(image_coverage, 3),
    }
    if not should_ocr:
        return native_spans, base_metadata

    ocr_spans, status = _extract_ocr_text_spans(page)
    merged = _merge_text_spans(native_spans, ocr_spans)
    mode = "native+ocr" if ocr_spans else status
    return merged, {
        **base_metadata,
        "mode": mode,
        "ocrSpanCount": len(ocr_spans),
        "ocrStatus": status,
    }


def _should_run_ocr(native_spans: list[TextSpan], vector_count: int, *, ocr_mode: OcrMode, image_coverage: float = 0.0) -> bool:
    if ocr_mode == "never":
        return False
    if ocr_mode == "always":
        return True
    useful_text = [span for span in native_spans if _ocr_useful_native_text(span.text)]
    if not useful_text and vector_count >= 40:
        return True
    if len(useful_text) < OCR_WEAK_TEXT_SPAN_THRESHOLD and vector_count >= OCR_VECTOR_HEAVY_THRESHOLD:
        return True
    # Scanned sheets: mostly one big raster image and next to no native text.
    if len(useful_text) < OCR_WEAK_TEXT_SPAN_THRESHOLD and image_coverage >= OCR_RASTER_COVERAGE_THRESHOLD:
        return True
    return False


def _raster_image_coverage(page: fitz.Page) -> float:
    """Share of the page area covered by placed raster images (overlaps counted once per image)."""
    page_rect = page.rect
    page_area = page_rect.width * page_rect.height
    if page_area <= 0:
        return 0.0
    covered = 0.0
    for info in page.get_image_info():
        bbox = fitz.Rect(info.get("bbox", (0, 0, 0, 0))) & page_rect
        if not bbox.is_empty:
            covered += bbox.width * bbox.height
    return min(1.0, covered / page_area)


def _extract_ocr_text_spans(page: fitz.Page, *, dpi: int = OCR_DEFAULT_DPI) -> tuple[list[TextSpan], str]:
    tesseract_path = shutil.which("tesseract")
    if tesseract_path is None:
        return [], "ocr_unavailable"
    native_spans: list[TextSpan] = []
    native_status = "native_ocr_unavailable"
    if hasattr(page, "get_textpage_ocr"):
        try:
            textpage = page.get_textpage_ocr(language="eng", dpi=dpi, full=True)
            text_dict = page.get_text("dict", textpage=textpage)
            native_spans = _extract_text_spans_from_dict(text_dict)
            native_status = "native_ocr_applied" if native_spans else "native_ocr_empty"
        except Exception:
            native_status = "native_ocr_unavailable"

    rendered_spans, rendered_status = _extract_rendered_tesseract_text_spans(page, tesseract_path=tesseract_path)
    spans = _merge_text_spans(native_spans, rendered_spans)
    if spans:
        if native_spans and rendered_spans:
            return spans, "ocr_applied"
        return spans, native_status if native_spans else rendered_status
    if rendered_status == "rendered_ocr_unavailable" and native_status == "native_ocr_unavailable":
        return [], "ocr_unavailable"
    return [], "ocr_empty"


def _extract_rendered_tesseract_text_spans(page: fitz.Page, *, tesseract_path: str) -> tuple[list[TextSpan], str]:
    zoom = OCR_RENDERED_TESSERACT_DPI / 72.0
    try:
        pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        with tempfile.TemporaryDirectory() as tmp:
            image_path = Path(tmp) / "page.png"
            pixmap.save(image_path)
            result = subprocess.run(
                [tesseract_path, str(image_path), "stdout", "--psm", "11", "--oem", "1", "tsv"],
                check=False,
                capture_output=True,
                text=True,
                timeout=45,
            )
    except Exception:
        return [], "rendered_ocr_unavailable"
    if result.returncode != 0:
        return [], "rendered_ocr_unavailable"
    spans = _text_spans_from_tesseract_tsv(result.stdout, zoom=zoom)
    return spans, "rendered_ocr_applied" if spans else "rendered_ocr_empty"


def _text_spans_from_tesseract_tsv(tsv_text: str, *, zoom: float) -> list[TextSpan]:
    spans: list[TextSpan] = []
    lines = [line for line in (tsv_text or "").splitlines() if line.strip()]
    if not lines:
        return spans
    header = lines[0].split("\t")
    required = {"left", "top", "width", "height", "conf", "text"}
    if not required.issubset(set(header)):
        return spans
    index = {name: header.index(name) for name in required}
    for line in lines[1:]:
        columns = line.split("\t")
        if len(columns) <= max(index.values()):
            continue
        text = columns[index["text"]].strip()
        if not text:
            continue
        try:
            confidence = float(columns[index["conf"]])
            left = float(columns[index["left"]])
            top = float(columns[index["top"]])
            width = float(columns[index["width"]])
            height = float(columns[index["height"]])
        except ValueError:
            continue
        if confidence < 0 or width <= 0 or height <= 0:
            continue
        spans.append(
            TextSpan(
                text=text,
                x=left / zoom,
                y=top / zoom,
                width=width / zoom,
                height=height / zoom,
                rotation=0.0,
            )
        )
    return spans


def _merge_text_spans(native_spans: list[TextSpan], ocr_spans: list[TextSpan]) -> list[TextSpan]:
    merged = list(native_spans)
    seen = {(_normalized_ocr_text(span.text), int(span.x), int(span.y)) for span in native_spans}
    for span in ocr_spans:
        key = (_normalized_ocr_text(span.text), int(span.x), int(span.y))
        if not key[0] or key in seen:
            continue
        seen.add(key)
        merged.append(span)
    return merged


def _ocr_useful_native_text(value: str) -> bool:
    text = _normalized_ocr_text(value)
    if not text:
        return False
    if re.fullmatch(r"RFI\s+\d+", text, re.IGNORECASE):
        return False
    return bool(re.search(r"[A-Z0-9]{3,}", text, re.IGNORECASE))


def _normalized_ocr_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip()).upper()


def _extract_vector_segments(drawings: list[dict], page_id: str) -> list[VectorSegment]:
    segments: list[VectorSegment] = []
    for drawing_index, drawing in enumerate(drawings):
        for item_index, item in enumerate(drawing.get("items", [])):
            segment = _vector_segment_from_item(page_id, drawing_index, item_index, drawing, item)
            if segment is not None:
                segments.append(segment)
    return segments


def _vector_segment_from_item(
    page_id: str,
    drawing_index: int,
    item_index: int,
    drawing: dict,
    item: tuple,
) -> VectorSegment | None:
    if not item:
        return None

    operator = str(item[0])
    if operator == "l":
        points = [_fitz_point_to_point(value) for value in item[1:3]]
        kind = "line"
    elif operator == "re":
        points = _rect_item_points(item)
        kind = "rect"
    elif operator == "qu":
        points = [_fitz_point_to_point(value) for value in item[1:5]]
        kind = "polyline"
    elif operator == "c":
        points = [_fitz_point_to_point(value) for value in item[1:] if _fitz_point_to_point(value) is not None]
        kind = "curve"
    else:
        raw_points = [_fitz_point_to_point(value) for value in item[1:] if _fitz_point_to_point(value) is not None]
        points = raw_points
        kind = "unknown"

    clean_points = [point for point in points if point is not None and _point_is_finite(point)]
    if len(clean_points) < 2:
        return None

    bounds = _point_bounds(clean_points)
    if bounds["width"] < 0.5 and bounds["height"] < 0.5:
        return None

    return VectorSegment(
        id=f"{page_id}:vector_{drawing_index + 1}_{item_index + 1}",
        kind=kind,
        points=clean_points,
        bounds=bounds,
        stroke=_color_to_hex(drawing.get("color")),
        strokeWidth=_positive_float(drawing.get("width")),
        dashed=_drawing_is_dashed(drawing.get("dashes")),
    )


def _fitz_point_to_point(value: object) -> Point | None:
    if hasattr(value, "x") and hasattr(value, "y"):
        return {"x": float(value.x), "y": float(value.y)}
    if isinstance(value, (tuple, list)) and len(value) >= 2:
        return {"x": float(value[0]), "y": float(value[1])}
    return None


def _rect_item_points(item: tuple) -> list[Point | None]:
    rect = item[1] if len(item) > 1 else None
    if rect is None:
        return []
    if all(hasattr(rect, attr) for attr in ("x0", "y0", "x1", "y1")):
        x0, y0, x1, y1 = float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)
    elif isinstance(rect, (tuple, list)) and len(rect) >= 4:
        x0, y0, x1, y1 = (float(rect[0]), float(rect[1]), float(rect[2]), float(rect[3]))
    else:
        return []
    return [
        {"x": x0, "y": y0},
        {"x": x1, "y": y0},
        {"x": x1, "y": y1},
        {"x": x0, "y": y1},
        {"x": x0, "y": y0},
    ]


def _point_bounds(points: list[Point]) -> BoundsDict:
    min_x = min(point["x"] for point in points)
    min_y = min(point["y"] for point in points)
    max_x = max(point["x"] for point in points)
    max_y = max(point["y"] for point in points)
    return {"x": min_x, "y": min_y, "width": max_x - min_x, "height": max_y - min_y}


def _point_is_finite(point: Point) -> bool:
    return isfinite(point["x"]) and isfinite(point["y"])


def _positive_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _color_to_hex(color: object) -> str | None:
    if not isinstance(color, (tuple, list)) or len(color) < 3:
        return None
    channels: list[int] = []
    for component in color[:3]:
        try:
            value = float(component)
        except (TypeError, ValueError):
            return None
        channels.append(round(max(0.0, min(1.0, value)) * 255.0))
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def _text_color_to_hex(color: object) -> str | None:
    if isinstance(color, int):
        value = max(0, min(0xFFFFFF, color))
        return f"#{value:06x}"
    return _color_to_hex(color)


def _drawing_is_dashed(dashes: object) -> bool:
    if dashes in (None, "", (), [], "[] 0", "[] 0.0"):
        return False
    return True


def _rotation_from_line(line: dict) -> float:
    direction = line.get("dir")
    if not direction or len(direction) < 2:
        return 0.0
    return float(degrees(atan2(float(direction[1]), float(direction[0]))))


def _span_edge(span: TextSpan, page_width: float, page_height: float) -> Edge:
    left_distance = span.x
    right_distance = page_width - (span.x + span.width)
    top_distance = span.y
    bottom_distance = page_height - (span.y + span.height)
    zone_x = page_width * EDGE_ZONE_RATIO
    zone_y = page_height * EDGE_ZONE_RATIO

    distances: dict[Edge, float] = {
        "left": left_distance if left_distance <= zone_x else float("inf"),
        "right": right_distance if right_distance <= zone_x else float("inf"),
        "top": top_distance if top_distance <= zone_y else float("inf"),
        "bottom": bottom_distance if bottom_distance <= zone_y else float("inf"),
    }
    edge, distance = min(distances.items(), key=lambda item: item[1])
    return edge if distance != float("inf") else "inside"


def _nearby_spans(spans: list[TextSpan], seed: TextSpan, page_width: float, page_height: float) -> list[TextSpan]:
    seed_center_x = seed.x + seed.width / 2.0
    seed_center_y = seed.y + seed.height / 2.0
    median_height = _median_span_height(spans)
    if _span_reads_rotated(seed):
        x_limit = max(160.0, min(320.0, page_width * 0.26))
        initial_y_limit = max(median_height * 8.0, min(110.0, page_height * 0.12))
    else:
        x_limit = max(120.0, min(220.0, page_width * 0.18))
        initial_y_limit = max(median_height * 6.0, min(75.0, page_height * 0.08))
    line_gap_limit = max(median_height * 2.4, min(34.0, page_height * 0.04))
    nearby = [
        span
        for span in spans
        if abs((span.x + span.width / 2.0) - seed_center_x) <= x_limit
        and abs((span.y + span.height / 2.0) - seed_center_y) <= initial_y_limit
    ]
    if seed not in nearby:
        nearby.append(seed)

    cluster = _semantic_cluster_for_seed(seed, nearby, line_gap_limit)
    return sorted(cluster, key=lambda span: (span.y, span.x))


def _span_reads_rotated(span: TextSpan) -> bool:
    return abs(span.rotation) > 45.0 or span.height > max(1.0, span.width) * 2.2


def _direction_from_text(text: str) -> Direction:
    if re.search(r"\bTO\b", text, re.IGNORECASE):
        return "to"
    if re.search(r"\bFROM\b", text, re.IGNORECASE):
        return "from"
    return "unknown"


def _first_match(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    return match.group(0).upper() if match else ""


def _flow_callout_metadata(
    page: PageEvidence,
    spans: list[TextSpan],
    seed: TextSpan,
    direction: Direction,
    sheet_ref: str,
    line_tag: str,
    system: str,
) -> dict[str, str]:
    direction_span = _nearest_direction_span(spans, seed)
    if direction_span is None or direction == "unknown":
        return {}

    external_label = _external_flow_label(direction_span, direction, page.textSpans)
    if not external_label:
        return {}

    source_ref_span = _nearest_pattern_span(page.textSpans, direction_span, SHEET_REF_RE, max_distance=260.0)
    line_tag_span = _nearest_pattern_span(page.textSpans, direction_span, LINE_TAG_RE, max_distance=280.0)
    source_ref = _first_match(SHEET_REF_RE, source_ref_span.text) if source_ref_span is not None else sheet_ref
    connected_line = _first_match(LINE_TAG_RE, line_tag_span.text) if line_tag_span is not None else line_tag
    if not connected_line:
        return {}
    connected_system = _first_match(SYSTEM_RE, connected_line or system or direction_span.text)

    evidence_spans = _unique_text_spans([direction_span, source_ref_span, line_tag_span])
    evidence_text = " ".join(span.text.strip() for span in sorted(evidence_spans, key=lambda item: (item.y, item.x)) if span.text.strip())
    callout_bounds = _union_bounds([direction_span, source_ref_span] if source_ref_span is not None else [direction_span])
    return {
        "calloutType": _flow_callout_type(page, callout_bounds),
        "direction": direction,
        "directionEvidence": "explicit_text",
        "externalFlowRole": "source" if direction == "from" else "destination",
        "externalFlowLabel": external_label,
        "sourceDrawingRef": source_ref,
        "lineTag": connected_line,
        "system": connected_system,
        "evidenceText": evidence_text,
        "calloutAnchor": f"{int(direction_span.x)}:{int(direction_span.y)}",
    }


def _unique_text_spans(spans: Iterable[TextSpan | None]) -> list[TextSpan]:
    unique: list[TextSpan] = []
    seen: set[tuple[str, int, int, int, int]] = set()
    for span in spans:
        if span is None:
            continue
        key = (span.text, int(span.x), int(span.y), int(span.width), int(span.height))
        if key in seen:
            continue
        seen.add(key)
        unique.append(span)
    return unique


def _nearest_direction_span(spans: list[TextSpan], seed: TextSpan) -> TextSpan | None:
    direction_spans = [span for span in spans if _direction_from_text(span.text) != "unknown"]
    if seed in direction_spans:
        return seed
    return min(direction_spans, key=lambda span: _span_distance(seed, span), default=None)


def _external_flow_label(direction_span: TextSpan, direction: Direction, spans: list[TextSpan]) -> str:
    direction_word = "FROM" if direction == "from" else "TO"
    text = direction_span.text or ""
    match = re.search(rf"\b{direction_word}\b\s*(.*)", text or "", re.IGNORECASE)
    if match:
        label = _clean_external_flow_label(match.group(1))
        if label:
            return label
    return _split_external_flow_label(direction_span, spans)


def _split_external_flow_label(direction_span: TextSpan, spans: list[TextSpan]) -> str:
    label_spans: list[TextSpan] = []
    for span in spans:
        if span is direction_span:
            continue
        text = (span.text or "").strip()
        if not text or _span_distance(direction_span, span) > 180.0:
            continue
        if SHEET_REF_RE.search(text) or LINE_TAG_RE.search(text) or _direction_from_text(text) != "unknown":
            continue
        if not re.search(r"[A-Z]{2}", text, re.IGNORECASE):
            continue
        label_spans.append(span)
    label = " ".join(span.text.strip() for span in sorted(label_spans, key=lambda item: (item.y, item.x)))
    return _clean_external_flow_label(label)


def _clean_external_flow_label(label: str) -> str:
    label = SHEET_REF_RE.sub(" ", label)
    label = LINE_TAG_RE.sub(" ", label)
    label = re.sub(r"\s+", " ", label).strip(" :-").upper()
    return label


def _nearest_pattern_span(
    spans: list[TextSpan],
    anchor: TextSpan,
    pattern: re.Pattern[str],
    *,
    max_distance: float,
) -> TextSpan | None:
    candidates = [span for span in spans if pattern.search(span.text or "")]
    return min(
        (span for span in candidates if _span_distance(anchor, span) <= max_distance),
        key=lambda span: (_span_distance(anchor, span), span.y, span.x),
        default=None,
    )


def _span_distance(first: TextSpan, second: TextSpan) -> float:
    first_center = _center_point(first)
    second_center = _center_point(second)
    return abs(first_center["x"] - second_center["x"]) + abs(first_center["y"] - second_center["y"])


def _flow_callout_type(page: PageEvidence, bounds: BoundsDict) -> str:
    padded = {
        "x": bounds["x"] - 24.0,
        "y": bounds["y"] - 24.0,
        "width": bounds["width"] + 48.0,
        "height": bounds["height"] + 48.0,
    }
    for segment in page.vectorSegments:
        if segment.bounds["width"] < 30.0 or segment.bounds["height"] < 18.0:
            continue
        if _bounds_overlap(segment.bounds, padded, padding=12.0):
            return "rectangular_flow_callout"
    return "flow_callout_text"


def _bounds_overlap(a: BoundsDict, b: BoundsDict, padding: float = 0.0) -> bool:
    return not (
        a["x"] + a["width"] + padding < b["x"]
        or b["x"] + b["width"] + padding < a["x"]
        or a["y"] + a["height"] + padding < b["y"]
        or b["y"] + b["height"] + padding < a["y"]
    )


def _union_bounds(spans: Iterable[TextSpan]) -> BoundsDict:
    spans = list(spans)
    if not spans:
        return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}

    x0 = min(span.x for span in spans)
    y0 = min(span.y for span in spans)
    x1 = max(span.x + span.width for span in spans)
    y1 = max(span.y + span.height for span in spans)
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


TITLE_REVISION_NOISE_RE = re.compile(
    r"\b(?:PROJECT|KEYPLAN|DRAWING|DRAWINGS|REVISION|DESCRIPTION|DESR|CHKD|APPR|STATUS|FAULT|"
    r"PURPOSE|REPRODUC(?:E|ED)|FURNISHED|DOCUMENT|ARCHITECT|ENGINEER|CONSULTANT|CLIENT|"
    r"PROJECT\s+NORTH|CATEGORY|ADDRESS|COPYRIGHT|GENERAL\s+NOTES|LEGEND|ABBREVIATIONS|"
    r"NAMING\s+CONVENTION)\b",
    re.IGNORECASE,
)

RED_MARKUP_TEXT_RE = re.compile(
    r"\b(?:REVIEW|COMMENT|NOTE|CHECK|VERIFY|TBD|REMOVE|ADD|MOVE|KEYED|OFFSET|CLOUD|"
    r"REVISION|DELTA|UPDATE|DRAFT)\b",
    re.IGNORECASE,
)

PROSE_CONTINUATION_NOISE_RE = re.compile(
    r"\b(?:"
    r"ARE\s+SUBJECT|SUBJECT\s+TO\s+VERIFICATION|MAKE\s+ANY\s+WARRANTY|LOSS\s+TO\s+PERSON|"
    r"PROPERTY\s+AS\s+A\s+RESULT|TO\s+ALLOW\s+FUTURE\s+ACCESS|TO\s+FACILITATE|TO\s+PROVIDE|"
    r"TO\s+BE\s+PROVIDED|TO\s+BE\s+INSTALLED|INSTALLED\s+TO\s+A\s+COMMON|"
    r"CONSTRUCTED\s+TO\s+ALLOW|PENETRATIONS\s+PENETRATING|WATERSTOP\s+TO\s+BE|"
    r"LOCATE\s+.+\s+TO\s+BE|SIZES\s+.+\s+TO\s+BE|COMPONENTS\s+BY|"
    r"ELEVATOR\s+DISCONNECT|GENERAL\s+NOTES|KEYED\s+NOTES"
    r")\b",
    re.IGNORECASE,
)

FLOW_CONTINUATION_CONTEXT_RE = re.compile(
    r"\b(?:SYSTEM|BUILDING|DISTRIBUTION|RETURN|SUPPLY|TANK|LOOP|HEADER|CONNECTION|"
    r"FUTURE\s+CONNECTION|EXISTING\s+CONNECTION|PROCESS|CONDENSATE|WATER|AIR|STEAM)\b",
    re.IGNORECASE,
)


def _duplicates_existing_callout(
    candidates: list[ContinuationCandidate],
    page: PageEvidence,
    sheet_ref: str,
    line_tag: str,
    direction: Direction,
    bounds: BoundsDict,
) -> bool:
    """One callout can be reached from several seed spans (the arrow text, a nearby line tag,
    a corner that sits in two edge bands). Keep the first candidate for each callout."""
    if not sheet_ref and not line_tag:
        return False
    for existing in candidates:
        if existing.sourceFileId != page.sourceFileId or existing.page != page.page:
            continue
        if (existing.sheetRef, existing.lineTag, existing.direction) != (sheet_ref, line_tag, direction):
            continue
        if _bounds_overlap(existing.bounds, bounds):
            return True
    return False


def _is_prose_continuation_noise(
    evidence_text: str,
    direction: Direction,
    sheet_ref: str,
    line_tag: str,
) -> bool:
    if line_tag:
        return False
    if PROSE_CONTINUATION_NOISE_RE.search(evidence_text):
        return True
    if direction == "unknown" or sheet_ref:
        return False
    return not bool(FLOW_CONTINUATION_CONTEXT_RE.search(evidence_text))


def _is_edge_title_or_revision_noise(
    page: PageEvidence,
    edge: Edge,
    bounds: BoundsDict,
    evidence_text: str,
    direction: Direction,
    sheet_ref: str,
    line_tag: str,
) -> bool:
    if TITLE_REVISION_NOISE_RE.search(evidence_text) and not line_tag and not _is_mechanical_sheet_ref(sheet_ref):
        return True

    if direction != "unknown" or sheet_ref:
        return False

    if not line_tag:
        return False

    # A bare line tag near the sheet edge is only useful if it is attached to
    # actual edge geometry. Revision/title blocks contain many tag-like tokens
    # but usually do not have a nearby leader terminating at the sheet edge.
    if page.vectorSegments and not _has_nearby_edge_leader(page, bounds, edge):
        return True
    return False


def _is_mechanical_sheet_ref(sheet_ref: str) -> bool:
    return bool(sheet_ref and sheet_ref.upper().startswith(f"{PROJECT_CODE}-ME-"))


def _is_red_markup_annotation(
    spans: list[TextSpan],
    direction: Direction,
    sheet_ref: str,
    line_tag: str,
) -> bool:
    if line_tag or _is_mechanical_sheet_ref(sheet_ref):
        return False

    colored_spans = [span for span in spans if span.color]
    if not colored_spans:
        return False

    red_count = sum(1 for span in colored_spans if _is_red_markup_color(span.color))
    if red_count == 0 or red_count / max(1, len(colored_spans)) < 0.6:
        return False

    evidence_text = " ".join(span.text for span in spans)
    return direction != "unknown" or bool(RED_MARKUP_TEXT_RE.search(evidence_text))


def _is_red_markup_color(color: str | None) -> bool:
    if not color:
        return False
    match = re.fullmatch(r"#([0-9a-fA-F]{6})", color.strip())
    if not match:
        return False
    red = int(match.group(1)[0:2], 16)
    green = int(match.group(1)[2:4], 16)
    blue = int(match.group(1)[4:6], 16)
    return red >= 150 and red >= green * 1.6 and red >= blue * 1.4


def _has_nearby_edge_leader(page: PageEvidence, bounds: BoundsDict, edge: Edge) -> bool:
    center = {"x": bounds["x"] + bounds["width"] / 2.0, "y": bounds["y"] + bounds["height"] / 2.0}
    edge_band_x = page.width * EDGE_ZONE_RATIO
    edge_band_y = page.height * EDGE_ZONE_RATIO
    proximity = max(42.0, min(page.width, page.height) * 0.045)

    for segment in page.vectorSegments:
        points = segment.points
        if len(points) < 2:
            continue
        for start, end in zip(points, points[1:]):
            if _segment_touches_candidate_edge(start, end, center, edge, page.width, page.height, edge_band_x, edge_band_y, proximity):
                return True
    return False


def _segment_touches_candidate_edge(
    start: Point,
    end: Point,
    center: Point,
    edge: Edge,
    page_width: float,
    page_height: float,
    edge_band_x: float,
    edge_band_y: float,
    proximity: float,
) -> bool:
    dx = abs(end["x"] - start["x"])
    dy = abs(end["y"] - start["y"])
    if edge == "right":
        return (
            dx >= dy
            and dx > 4.0
            and
            max(start["x"], end["x"]) >= page_width - edge_band_x
            and _range_near_value(start["y"], end["y"], center["y"], proximity)
        )
    if edge == "left":
        return (
            dx >= dy
            and dx > 4.0
            and min(start["x"], end["x"]) <= edge_band_x
            and _range_near_value(start["y"], end["y"], center["y"], proximity)
        )
    if edge == "bottom":
        return (
            dy >= dx
            and dy > 4.0
            and
            max(start["y"], end["y"]) >= page_height - edge_band_y
            and _range_near_value(start["x"], end["x"], center["x"], proximity)
        )
    if edge == "top":
        return (
            dy >= dx
            and dy > 4.0
            and min(start["y"], end["y"]) <= edge_band_y
            and _range_near_value(start["x"], end["x"], center["x"], proximity)
        )
    return False


def _range_near_value(first: float, second: float, value: float, proximity: float) -> bool:
    low = min(first, second) - proximity
    high = max(first, second) + proximity
    return low <= value <= high


def _center_point(span: TextSpan) -> Point:
    return {"x": span.x + span.width / 2.0, "y": span.y + span.height / 2.0}


def _median_span_height(spans: list[TextSpan]) -> float:
    heights = sorted(span.height for span in spans if span.height > 0)
    if not heights:
        return 12.0
    midpoint = len(heights) // 2
    if len(heights) % 2:
        return heights[midpoint]
    return (heights[midpoint - 1] + heights[midpoint]) / 2.0


def _vertical_gap(first: TextSpan, second: TextSpan) -> float:
    first_center_y = _center_point(first)["y"]
    second_center_y = _center_point(second)["y"]
    return abs(second_center_y - first_center_y)


def _semantic_cluster_for_seed(seed: TextSpan, nearby: list[TextSpan], line_gap_limit: float) -> list[TextSpan]:
    seed_types = _semantic_types(seed.text)
    if not seed_types:
        return [seed]

    cluster = [seed]
    limit = line_gap_limit * 2.0
    if "direction" in seed_types:
        _append_nearest_type(cluster, nearby, seed, "line_tag", limit)
        _append_nearest_type(cluster, nearby, seed, "sheet_ref", limit)
        return cluster

    direction_span = _nearest_span_with_type(nearby, seed, "direction", limit)
    if direction_span is None:
        return cluster
    cluster.append(direction_span)

    if "sheet_ref" in seed_types:
        _append_nearest_type(cluster, nearby, seed, "line_tag", limit, same_side_as=direction_span)
    elif "line_tag" in seed_types:
        _append_nearest_type(cluster, nearby, seed, "sheet_ref", limit, same_side_as=direction_span)
    return cluster


def _append_nearest_type(
    cluster: list[TextSpan],
    nearby: list[TextSpan],
    seed: TextSpan,
    semantic_type: str,
    limit: float,
    same_side_as: TextSpan | None = None,
) -> None:
    span = _nearest_span_with_type(nearby, seed, semantic_type, limit, same_side_as=same_side_as)
    if span is not None and span not in cluster:
        cluster.append(span)


def _nearest_span_with_type(
    spans: list[TextSpan],
    seed: TextSpan,
    semantic_type: str,
    limit: float,
    same_side_as: TextSpan | None = None,
) -> TextSpan | None:
    candidates = [
        span
        for span in spans
        if span != seed
        and semantic_type in _semantic_types(span.text)
        and _vertical_gap(seed, span) <= limit
        and (same_side_as is None or _same_vertical_side(seed, same_side_as, span))
    ]
    if not candidates and same_side_as is not None:
        return _nearest_span_with_type(spans, seed, semantic_type, limit)
    return min(candidates, key=lambda span: (_vertical_gap(seed, span), span.y, span.x), default=None)


def _same_vertical_side(seed: TextSpan, reference: TextSpan, candidate: TextSpan) -> bool:
    seed_y = _center_point(seed)["y"]
    reference_delta = _center_point(reference)["y"] - seed_y
    candidate_delta = _center_point(candidate)["y"] - seed_y
    return reference_delta == 0 or candidate_delta == 0 or (reference_delta > 0) == (candidate_delta > 0)


def _semantic_types(text: str) -> set[str]:
    semantic_types: set[str] = set()
    if _first_match(SHEET_REF_RE, text):
        semantic_types.add("sheet_ref")
    if _first_match(LINE_TAG_RE, text):
        semantic_types.add("line_tag")
    if _direction_from_text(text) != "unknown":
        semantic_types.add("direction")
    return semantic_types


def _normalized_local_label(text: str) -> str:
    return re.sub(r"\s+", " ", text.upper()).strip()


def _bucket_size(page_size: float) -> float:
    return max(48.0, page_size * 0.08)
