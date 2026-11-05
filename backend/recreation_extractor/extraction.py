from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import Bounds, SourceEvidence, SourceFile
from .normalization import normalize_ocr_text, normalize_tag

try:
    import fitz  # type: ignore
except Exception:  # pragma: no cover - optional at runtime
    fitz = None


TAG_RE = re.compile(
    r"\b(?:"
    r"(?:P|PU|TK|V|XV|CV|HV|PT|TT|FT|LT|FIT|TIC|PIC|LIC|JB|PNL|MCC|MOT|MTR|BKR|CB|XFMR|TR|VFD|ASD|SWG|SWGR|HX|VSL|E)[-\s]?\d{2,5}[A-Z]?"
    r"|[A-Z]{1,4}-\d{2,5}[A-Z]?"
    r")\b"
)

LINE_RE = re.compile(r"\b(?:\d{1,2}\"[-\s]?)?(?:[A-Z]{1,4})[-\s]?\d{3,6}(?:[-\s]?[A-Z]{1,4})?\b")
CABLE_RE = re.compile(r"\b(?:C|CBL|COND|CNDT|W|WIRE)[-\s]?\d{2,6}[A-Z]?\b")
CONTINUATION_RE = re.compile(r"\b(?:TO|FROM|CONT\.?|CONTINUED|SEE)\s+([A-Z0-9\-_.]+)\b", re.IGNORECASE)
NON_TAG_PREFIXES = {
    "AI",
    "CAB",
    "CBL",
    "COND",
    "CNDT",
    "CW",
    "DR",
    "FW",
    "LINE",
    "OF",
    "PID",
    "PW",
    "REV",
    "VR",
    "W",
    "WIRE",
}
KNOWN_SYMBOL_PREFIXES = {
    "ASD",
    "BKR",
    "CB",
    "CV",
    "E",
    "FIT",
    "FT",
    "HV",
    "HX",
    "JB",
    "LIC",
    "LT",
    "MCC",
    "MOT",
    "MTR",
    "P",
    "PIC",
    "PNL",
    "PT",
    "PU",
    "SWG",
    "SWGR",
    "TK",
    "TIC",
    "TT",
    "TR",
    "V",
    "VFD",
    "VSL",
    "XV",
    "XFMR",
}


@dataclass(frozen=True)
class LineSegment:
    x0: float
    y0: float
    x1: float
    y1: float
    page: int


@dataclass(frozen=True)
class PageExtraction:
    id: str
    sourceFileId: str
    page: int
    width: float
    height: float
    text: str
    words: list[dict[str, Any]]
    vectorCount: int
    rasterized: bool
    paths: tuple[LineSegment, ...] = ()


@dataclass(frozen=True)
class Detection:
    id: str
    sourceFileId: str
    page: int
    kind: str
    label: str
    confidence: float
    bounds: Bounds | None
    evidence: SourceEvidence


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_file_for_path(project_id: str, path: str) -> SourceFile:
    file_path = Path(path)
    digest = sha256_file(file_path)
    source_namespace = hashlib.sha256(f"{project_id}\0{digest}".encode("utf-8")).hexdigest()[:16]
    source_id = f"src_{source_namespace}"
    return SourceFile(
        id=source_id,
        projectId=project_id,
        path=str(file_path),
        name=file_path.name,
        sha256=digest,
    )


def extract_pdf(source: SourceFile) -> tuple[SourceFile, list[PageExtraction], list[Detection]]:
    path = Path(source.path)
    if fitz is None:
        pages = [_fallback_page(source)]
        return SourceFile(**{**source.__dict__, "pageCount": 1}), pages, detect_from_pages(pages)

    doc = fitz.open(path)
    pages: list[PageExtraction] = []
    for page_index, page in enumerate(doc):
        page_no = page_index + 1
        text_words = _extract_words(page)
        text = " ".join(word["text"] for word in text_words)
        drawings = page.get_drawings()
        vector_count = len(drawings)
        line_segments = _extract_line_segments(drawings, page_no)
        pages.append(
            PageExtraction(
                id=f"{source.id}_p{page_no}",
                sourceFileId=source.id,
                page=page_no,
                width=float(page.rect.width),
                height=float(page.rect.height),
                text=text,
                words=text_words,
                vectorCount=vector_count,
                rasterized=not bool(text_words) or vector_count == 0,
                paths=tuple(line_segments),
            )
        )
    source = SourceFile(**{**source.__dict__, "pageCount": len(pages)})
    return source, pages, detect_from_pages(pages)


def _extract_words(page: Any) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for raw in page.get_text("words"):
        x0, y0, x1, y1, text, block, line, word = raw[:8]
        normalized = normalize_ocr_text(str(text))
        if not normalized:
            continue
        words.append(
            {
                "text": normalized,
                "x": float(x0),
                "y": float(y0),
                "width": float(x1 - x0),
                "height": float(y1 - y0),
                "block": int(block),
                "line": int(line),
                "word": int(word),
            }
        )
    return words


def _extract_line_segments(drawings: list[Any], page_no: int) -> list[LineSegment]:
    """Extract line segments from PyMuPDF drawing dicts.

    Each drawing dict has an 'items' list. Items with type 'l' (line)
    contain two points: (x0, y0) and (x1, y1).
    """
    segments: list[LineSegment] = []
    for drawing in drawings:
        for item in drawing.get("items", []):
            if len(item) >= 3 and item[0] == "l":
                p1, p2 = item[1], item[2]
                segments.append(
                    LineSegment(
                        x0=float(p1.x if hasattr(p1, "x") else p1[0]),
                        y0=float(p1.y if hasattr(p1, "y") else p1[1]),
                        x1=float(p2.x if hasattr(p2, "x") else p2[0]),
                        y1=float(p2.y if hasattr(p2, "y") else p2[1]),
                        page=page_no,
                    )
                )
    return segments


def _fallback_page(source: SourceFile) -> PageExtraction:
    text = Path(source.path).name
    return PageExtraction(
        id=f"{source.id}_p1",
        sourceFileId=source.id,
        page=1,
        width=1728,
        height=1118,
        text=text,
        words=[{"text": normalize_ocr_text(text), "x": 72, "y": 72, "width": 240, "height": 24}],
        vectorCount=0,
        rasterized=True,
    )


def detect_from_pages(pages: list[PageExtraction]) -> list[Detection]:
    detections: list[Detection] = []
    for page in pages:
        detections.extend(_detect_tags(page))
        detections.extend(_detect_line_or_cable_ids(page))
        detections.extend(_detect_continuations(page))
        detections.extend(_detect_legend(page))
    return dedupe_detections(detections)


def _detect_tags(page: PageExtraction) -> list[Detection]:
    detections: list[Detection] = []
    seen_labels: set[str] = set()
    for word in page.words:
        for match in TAG_RE.finditer(word["text"]):
            label = normalize_tag(match.group(0))
            if _is_non_equipment_tag(label):
                continue
            seen_labels.add(label)
            detections.append(_detection(page, "tag", label, 0.78, word))

    # Check consecutive word pairs within the same block/line for split tags
    # e.g. "P" "101" or "FT" "201A" appearing as separate words
    for i in range(len(page.words) - 1):
        left = page.words[i]
        right = page.words[i + 1]
        if left.get("block") != right.get("block") or left.get("line") != right.get("line"):
            continue
        combined = f"{left['text']}-{right['text']}"
        for match in TAG_RE.finditer(combined):
            label = normalize_tag(match.group(0))
            if _is_non_equipment_tag(label) or label in seen_labels:
                continue
            seen_labels.add(label)
            merged_word = {
                "text": combined,
                "x": left["x"],
                "y": min(left["y"], right["y"]),
                "width": (right["x"] + right.get("width", 0)) - left["x"],
                "height": max(left.get("height", 12), right.get("height", 12)),
            }
            detections.append(_detection(page, "tag", label, 0.72, merged_word))

    return detections


def _detect_line_or_cable_ids(page: PageExtraction) -> list[Detection]:
    detections: list[Detection] = []
    for word in page.words:
        text = word["text"]
        for match in CABLE_RE.finditer(text):
            detections.append(_detection(page, "cable_id", normalize_tag(match.group(0)), 0.74, word))
        for match in LINE_RE.finditer(text):
            label = normalize_tag(match.group(0))
            if len(label) >= 5 and not label.startswith(("PID-", "CAB-")) and not _is_symbol_tag(label):
                detections.append(_detection(page, "line_id", label, 0.68, word))
    return detections


def _detect_continuations(page: PageExtraction) -> list[Detection]:
    detections: list[Detection] = []
    text = page.text
    for match in CONTINUATION_RE.finditer(text):
        label = normalize_ocr_text(match.group(0))
        detections.append(_detection(page, "continuation_ref", label, 0.62, _nearest_word(page, match.group(1))))
    return detections


def _detect_legend(page: PageExtraction) -> list[Detection]:
    text = page.text.upper()
    if "LEGEND" not in text and "SYMBOL" not in text:
        return []
    evidence_word = page.words[0] if page.words else {"text": "LEGEND", "x": 0, "y": 0, "width": page.width, "height": 80}
    return [_detection(page, "legend_candidate", "PROJECT-LEGEND", 0.82, evidence_word)]


def _nearest_word(page: PageExtraction, text: str) -> dict[str, Any]:
    needle = normalize_ocr_text(text)
    for word in page.words:
        if needle in word["text"]:
            return word
    return page.words[0] if page.words else {"text": needle, "x": 0, "y": 0, "width": 1, "height": 1}


def _is_non_equipment_tag(label: str) -> bool:
    prefix = label.split("-", 1)[0]
    return prefix in NON_TAG_PREFIXES


def _is_symbol_tag(label: str) -> bool:
    prefix = label.split("-", 1)[0]
    return prefix in KNOWN_SYMBOL_PREFIXES


def _detection(page: PageExtraction, kind: str, label: str, confidence: float, word: dict[str, Any]) -> Detection:
    bounds = Bounds(
        page=page.page,
        x=float(word.get("x", 0)),
        y=float(word.get("y", 0)),
        width=float(word.get("width", 1)),
        height=float(word.get("height", 1)),
    )
    evidence_id = f"ev_{page.sourceFileId}_{page.page}_{kind}_{hashlib.sha1((label + str(bounds)).encode()).hexdigest()[:10]}"
    evidence = SourceEvidence(
        id=evidence_id,
        sourceFileId=page.sourceFileId,
        page=page.page,
        bounds=bounds,
        text=label,
        confidence=confidence,
    )
    det_id = f"det_{hashlib.sha1((evidence_id + kind).encode()).hexdigest()[:16]}"
    return Detection(
        id=det_id,
        sourceFileId=page.sourceFileId,
        page=page.page,
        kind=kind,
        label=label,
        confidence=confidence,
        bounds=bounds,
        evidence=evidence,
    )


def dedupe_detections(detections: list[Detection]) -> list[Detection]:
    seen: set[tuple[str, int, str, str]] = set()
    result: list[Detection] = []
    for detection in detections:
        key = (detection.sourceFileId, detection.page, detection.kind, detection.label)
        if key in seen:
            continue
        seen.add(key)
        result.append(detection)
    return result
