from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from recreation_extractor.conventions import PROJECT_CODE_PATTERN
from recreation_extractor.pid_stitch.models import ContinuationCandidate, DrawingStyle, PageEvidence


FALLBACK_PALETTE = [
    "#0070c0",
    "#7030a0",
    "#ea700d",
    "#ff0000",
    "#4bacc6",
    "#00b050",
    "#923931",
    "#0c1c54",
    "#3f3f3f",
    "#f59d56",
]

_LINE_TAG_RE = re.compile(r'\b(?:\d{1,3}(?:\s+\d/\d)?|\d/\d)"-([A-Z][A-Z0-9]{1,8})(?:-[A-Z0-9]+)+\b', re.IGNORECASE)
_PIPE_SIZE_SYSTEM_RE = re.compile(r'\b(?:\d{1,3}(?:\s+\d/\d)?|\d/\d)"\s+([A-Z][A-Z0-9]{1,8})\b', re.IGNORECASE)
_DISCIPLINE_PREFIX_SYSTEM_RE = re.compile(r"\b\d{2}-([A-Z][A-Z0-9]{1,8})(?:-[A-Z0-9]+)+\b", re.IGNORECASE)
_TAG_PREFIX_SYSTEM_RE = re.compile(r"\b(?:R|" + PROJECT_CODE_PATTERN + r")-([A-Z][A-Z0-9]{1,8})-[A-Z0-9]+(?:-[A-Z0-9_]+)+\b", re.IGNORECASE)
_ELECTRICAL_RE = re.compile(r"\b(\d{3,4}V|MCC|UPS|PDU|SWGR|XFMR|FEEDER|PANEL|ELEC)\b", re.IGNORECASE)
_FUTURE_RE = re.compile(r"\b(FUTURE)\b", re.IGNORECASE)
_SOURCE_SYSTEM_RE = re.compile(r"\b(CHW|CW|HRW|HHW|CDA|DOMW|SSW|PW|CTW|TCHW|POTCW|ICW)\b", re.IGNORECASE)
_SOURCE_EMBEDDED_SYSTEM_RE = re.compile(r"(TCHW|POTCW|CHW|CTW|ICW|CW|HRW|HHW|CDA|DOMW|SSW|PW)", re.IGNORECASE)
_HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{6}\Z")
_NON_SYSTEM_TOKENS = {
    "ABOVE",
    "BELOW",
    "BFP",
    "CEILING",
    "COUPLING",
    "CROSS",
    "DCVA",
    "DRAIN",
    "GATE",
    "HDPE",
    "INLET",
    "LIT",
    "LSHH",
    "MANUAL",
    "OF",
    "OR",
    "OUTL",
    "OVERFL",
    "PER",
    "PRESSURE",
    "PRV",
    "RPZ",
    "SIDE",
    "STRAINER",
    "SYSTEM",
    "TALL",
    "TANK",
    "TEMP",
    "THICK",
    "THROUGH",
    "TO",
    "VALVE",
    "WIDE",
}


@dataclass(frozen=True)
class SystemColorEntry:
    key: str
    label: str
    color: str
    source: str
    evidenceCount: int
    confidence: float
    dash: list[float] | None = None


@dataclass(frozen=True)
class SystemColorMap:
    entries: dict[str, SystemColorEntry]
    tokenToSystem: dict[str, str]

    def color_for(self, system: str | None) -> str:
        key = canonical_system(system or "")
        entry = self.entries.get(key)
        return entry.color if entry else "#111827"


def discover_system_color_map(
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    source_paths: dict[str, str],
    reference_colors: dict[str, str] | None = None,
) -> SystemColorMap:
    counts: dict[str, int] = {}
    first_seen: dict[str, int] = {}
    token_to_system: dict[str, str] = {}

    for ordinal, token in enumerate(_tokens_from_pages(pages, source_paths) + _tokens_from_candidates(candidates)):
        system = canonical_system(token)
        if not system:
            continue
        counts[system] = counts.get(system, 0) + 1
        first_seen.setdefault(system, ordinal)
        token_to_system[token.upper()] = system

    normalized_reference_colors = {
        canonical_system(key): value
        for key, value in (reference_colors or {}).items()
        if canonical_system(key) and _is_hex_color(value)
    }

    entries: dict[str, SystemColorEntry] = {}
    systems = sorted(counts, key=lambda system: (first_seen[system], system))
    for index, system in enumerate(systems):
        has_reference = system in normalized_reference_colors
        entries[system] = SystemColorEntry(
            key=system,
            label=display_system_label(system),
            color=normalized_reference_colors.get(system) or FALLBACK_PALETTE[index % len(FALLBACK_PALETTE)],
            source="reference" if has_reference else "inferred",
            evidenceCount=counts[system],
            confidence=0.92 if has_reference else _confidence_for_system(system, counts[system]),
            dash=[8.0, 4.0] if index >= len(FALLBACK_PALETTE) else None,
        )

    if not entries:
        entries["DEFAULT"] = SystemColorEntry("DEFAULT", "DEFAULT", "#111827", "fallback", 0, 0.3)

    return SystemColorMap(entries=entries, tokenToSystem=token_to_system)


def system_for_text(text: str, color_map: SystemColorMap) -> str:
    direct_system = canonical_system(text)
    if direct_system in color_map.entries:
        return direct_system

    for token in extract_system_tokens(text):
        system = canonical_system(token)
        if system in color_map.entries:
            return system
    return "DEFAULT"


def style_for_system(system: str | None, color_map: SystemColorMap, stroke_width: float = 2.0) -> DrawingStyle:
    entry = color_map.entries.get(canonical_system(system or ""), color_map.entries.get("DEFAULT"))
    return DrawingStyle(
        stroke=entry.color if entry else "#111827",
        fill="none",
        strokeWidth=stroke_width,
        opacity=1.0,
        dash=entry.dash if entry else None,
    )


def extract_system_tokens(text: str) -> list[str]:
    found: list[tuple[int, str]] = []
    for regex in (_LINE_TAG_RE, _PIPE_SIZE_SYSTEM_RE, _DISCIPLINE_PREFIX_SYSTEM_RE, _TAG_PREFIX_SYSTEM_RE, _ELECTRICAL_RE, _FUTURE_RE):
        for match in regex.finditer(text or ""):
            found.append((match.start(1), match.group(1).upper()))

    tokens: list[str] = []
    for _, token in sorted(found, key=lambda item: item[0]):
        if token not in tokens:
            tokens.append(token)
    return tokens


def canonical_system(token: str) -> str:
    text = re.sub(r"[^A-Z0-9]", "", (token or "").upper())
    if text in _NON_SYSTEM_TOKENS:
        return ""
    if text in {"CHW", "CHWS", "CHWR", "TCHW", "TCHWS", "TCHWR", "SCHW", "SCHWS", "SCHWR"}:
        return "CHW"
    if text in {"CW", "CWS", "CWR", "CTW", "CTWS", "CTWR"}:
        return "CW"
    if text in {"HRW", "HRWS", "HRWR", "HRS", "HRR"}:
        return "HRW"
    if text in {"HHW", "HHWS", "HHWR", "HWS", "HWR", "SHHW", "SHHWS", "SHHWR"}:
        return "HHW"
    if text in {"CDA", "IA", "CA"}:
        return "CDA"
    if text in {"DOMW", "PW", "SSW", "POTCW", "ICW"}:
        return text
    if text in {"480V", "208V", "120V", "MCC", "UPS", "PDU", "SWGR", "XFMR", "FEEDER", "PANEL", "ELEC"}:
        return text
    if text == "FUTURE":
        return "FUTURE"
    if re.fullmatch(r"[A-Z][A-Z0-9]{1,8}", text):
        return text
    return ""


def display_system_label(system: str) -> str:
    return {
        "CHW": "CHW / TCHW",
        "CW": "CW",
        "HRW": "HRW",
        "HHW": "HHW",
        "CDA": "COMPRESSED AIR",
        "DOMW": "DOMESTIC WATER",
        "POTCW": "POTABLE COLD WATER",
        "ICW": "INDUSTRIAL COLD WATER",
        "SSW": "SAFETY SHOWER",
    }.get(canonical_system(system) or system, system)


def _tokens_from_pages(pages: list[PageEvidence], source_paths: dict[str, str]) -> list[str]:
    tokens: list[str] = []
    for page in pages:
        source_name = Path(source_paths.get(page.sourceFileId, page.sourceFileId)).stem
        electrical_source = bool(re.search(r"\b(ELEC|ELECTRICAL|POWER|MCC|PANEL|FEEDER)\b", source_name, re.IGNORECASE))
        process_sheet = any(
            _LINE_TAG_RE.search(span.text or "")
            or _PIPE_SIZE_SYSTEM_RE.search(span.text or "")
            or _DISCIPLINE_PREFIX_SYSTEM_RE.search(span.text or "")
            for span in page.textSpans
        )
        for span in page.textSpans:
            span_tokens = extract_system_tokens(span.text)
            if process_sheet and not electrical_source:
                span_tokens = [
                    token
                    for token in span_tokens
                    if canonical_system(token) not in {"480V", "208V", "120V", "MCC", "UPS", "PDU", "SWGR", "XFMR", "FEEDER", "PANEL", "ELEC"}
                ]
            tokens.extend(span_tokens)

        tokens.extend(_tokens_from_source_name(source_name))
    return tokens


def _tokens_from_candidates(candidates: list[ContinuationCandidate]) -> list[str]:
    tokens: list[str] = []
    for candidate in candidates:
        if canonical_system(candidate.system):
            tokens.append(candidate.system)
        tokens.extend(extract_system_tokens(candidate.system))
        tokens.extend(extract_system_tokens(candidate.lineTag))
        tokens.extend(extract_system_tokens(candidate.label))
        tokens.extend(extract_system_tokens(candidate.evidenceText))
    return tokens


def _tokens_from_source_name(source_name: str) -> list[str]:
    tokens = [match.group(1).upper() for match in _SOURCE_SYSTEM_RE.finditer(source_name)]
    for match in _SOURCE_EMBEDDED_SYSTEM_RE.finditer(source_name):
        token = match.group(1).upper()
        if token not in tokens:
            tokens.append(token)
    return tokens


def _confidence_for_system(system: str, evidence_count: int) -> float:
    if system in {"CHW", "CW", "HRW", "HHW", "CDA", "DOMW", "SSW"}:
        return 0.82
    if evidence_count > 1:
        return 0.78
    return 0.68


def _is_hex_color(value: str) -> bool:
    return bool(_HEX_COLOR_RE.fullmatch(value or ""))
