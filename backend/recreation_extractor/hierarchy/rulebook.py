from __future__ import annotations

import re
from collections import defaultdict
from typing import Any

from .models import Rulebook
from ..pid_stitch.models import PageEvidence


ACRONYM_RE = re.compile(r"^[A-Z][A-Z0-9/&.-]{1,10}$")
LEGEND_PAGE_ROLES = {"legend_reference", "abbreviations", "general_notes"}


def build_rulebook(project_id: str, pages: list[PageEvidence], preflight: dict[str, Any] | None) -> Rulebook:
    preflight = preflight or {}
    has_confirmed_legend_pages = "legendPages" in preflight
    legend_pages = [int(page) for page in preflight.get("legendPages", []) if isinstance(page, int)]
    legend_page_set = set(legend_pages)
    legend_page_keys = (
        _confirmed_page_keys(preflight, legend_page_set)
        if has_confirmed_legend_pages
        else _legend_page_keys(preflight)
    )
    acronym_map: dict[str, str] = {}
    source_evidence: list[dict[str, Any]] = []

    for page in pages:
        if has_confirmed_legend_pages and legend_page_keys:
            if (page.sourceFileId, page.page) not in legend_page_keys:
                continue
        elif has_confirmed_legend_pages:
            if not legend_page_set or page.page not in legend_page_set:
                continue
        elif legend_page_keys:
            if (page.sourceFileId, page.page) not in legend_page_keys:
                continue
        pairs = _legend_acronym_pairs(page)
        for key, value in pairs.items():
            acronym_map.setdefault(key, value)
            source_evidence.append(
                {
                    "sourceFileId": page.sourceFileId,
                    "pageId": page.id,
                    "page": page.page,
                    "type": "acronym",
                    "key": key,
                    "value": value,
                }
            )

    return Rulebook(
        projectId=project_id,
        disciplines=list(preflight.get("disciplines", ["Unknown"])),
        legendPages=legend_pages,
        acronymMap=acronym_map,
        symbolRules=[],
        tagRules=[],
        suppressionRules=_default_suppression_rules(preflight),
        sourceEvidence=source_evidence,
        warnings=list(preflight.get("warnings", [])),
    )


def _legend_page_keys(preflight: dict[str, Any], allowed_pages: set[int] | None = None) -> set[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    for role in preflight.get("pageRoles", []):
        if not isinstance(role, dict) or role.get("role") not in LEGEND_PAGE_ROLES:
            continue
        source_file_id = role.get("sourceFileId")
        page = role.get("page")
        if allowed_pages is not None and page not in allowed_pages:
            continue
        if isinstance(source_file_id, str) and isinstance(page, int):
            keys.add((source_file_id, page))
    return keys


def _confirmed_page_keys(preflight: dict[str, Any], allowed_pages: set[int]) -> set[tuple[str, int]]:
    keys: set[tuple[str, int]] = set()
    for role in preflight.get("pageRoles", []):
        if not isinstance(role, dict):
            continue
        source_file_id = role.get("sourceFileId")
        page = role.get("page")
        if isinstance(source_file_id, str) and isinstance(page, int) and page in allowed_pages:
            keys.add((source_file_id, page))
    return keys


def _legend_acronym_pairs(page: PageEvidence) -> dict[str, str]:
    by_row: dict[int, list[Any]] = defaultdict(list)
    for span in page.textSpans:
        row_key = round(span.y / 8)
        by_row[row_key].append(span)

    pairs: dict[str, str] = {}
    for spans in by_row.values():
        ordered = sorted(spans, key=lambda span: span.x)
        for left, right in zip(ordered, ordered[1:]):
            key = left.text.strip().upper()
            value = right.text.strip()
            if ACRONYM_RE.match(key) and len(value) > 2 and len(value) > len(key):
                pairs[key] = value.upper()
    return pairs


def _default_suppression_rules(preflight: dict[str, Any]) -> list[dict[str, Any]]:
    disciplines = set(preflight.get("disciplines", []))
    rules = [{"kind": "audit_only", "pattern": r"\b\d+(?:\.\d+)?\s?(?:KV|V|A|AMP|OHM|HZ)\b"}]
    if "Electrical" in disciplines:
        rules.append({"kind": "electrical_tree_noise", "pattern": r"\b(?:BUS|RELAY|TRIP|FRAME|POLE)\b"})
    return rules
