from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Iterable

from ..conventions import BUILDING_CODES
from .models import (
    Discipline,
    PageRole,
    PageRoleAssignment,
    PreflightReview,
    TemplateSummary,
    discipline_from_text,
    page_role_from_text,
)


@dataclass(frozen=True)
class PreflightPageSummary:
    sourceFileId: str
    page: int
    text: str


TABLE_FAMILY_BY_ROLE: dict[str, str] = {
    "panel_schedule": "panel_schedule",
    "equipment_schedule": "equipment_schedule",
    "line_list": "line_list",
    "instrument_index": "instrument_index",
    "loop_sheet": "loop_sheet",
    "cable_schedule": "cable_schedule",
    "io_schedule": "io_schedule",
    "mechanical_schedule": "mechanical_schedule",
}


def build_preflight_review(
    project_id: str,
    pages: Iterable[PreflightPageSummary],
    templates: list[TemplateSummary],
) -> PreflightReview:
    page_list = list(pages)
    role_assignments: list[PageRoleAssignment] = []
    discipline_counts: Counter[Discipline] = Counter()
    table_families: set[str] = set()
    legend_pages: list[int] = []

    for page in page_list:
        text = " ".join(page.text.split())
        role = _page_role_for_preflight(text)
        discipline = _discipline_for_preflight(text, role)
        confidence = _role_confidence(role, text)
        reason = _role_reason(role, text)
        role_assignments.append(
            PageRoleAssignment(
                sourceFileId=page.sourceFileId,
                page=page.page,
                role=role,
                confidence=confidence,
                reason=reason,
            )
        )
        if role in {"legend_reference", "abbreviations", "general_notes"}:
            legend_pages.append(page.page)
        if role in TABLE_FAMILY_BY_ROLE:
            table_families.add(TABLE_FAMILY_BY_ROLE[role])
        if discipline != "Unknown":
            discipline_counts[discipline] += 1

    disciplines = _rank_disciplines(discipline_counts)
    legend_confidence = 0.0 if not legend_pages else min(0.95, 0.72 + len(legend_pages) * 0.04)
    warnings: list[str] = []
    if not legend_pages:
        warnings.append("No likely legend/reference page found.")
    if disciplines == ["Unknown"]:
        warnings.append("No strong discipline signal found.")

    return PreflightReview(
        projectId=project_id,
        status="draft",
        disciplines=disciplines,
        disciplineConfidence=_discipline_confidence(discipline_counts, len(page_list)),
        legendPages=sorted(set(legend_pages)),
        legendConfidence=legend_confidence,
        pageRoles=role_assignments,
        tableFamilies=sorted(table_families),
        suggestedTemplateIds=[template.id for template in templates[:3]],
        warnings=warnings,
    )


def _rank_disciplines(counts: Counter[Discipline]) -> list[Discipline]:
    if not counts:
        return ["Unknown"]
    ranked = [discipline for discipline, _count in counts.most_common()]
    if len(ranked) > 1:
        return ranked[:4]
    return ranked


def _discipline_confidence(counts: Counter[Discipline], page_count: int) -> float:
    if not counts or page_count <= 0:
        return 0.0
    top = counts.most_common(1)[0][1]
    return min(0.96, 0.52 + top / max(page_count, 1) * 0.44)


def _page_role_for_preflight(text: str) -> PageRole:
    upper = text.upper()
    if _electrical_one_line_signal(upper):
        return "one_line"
    if _strong_legend_reference(upper):
        return "legend_reference"
    if "PANEL SCHEDULE" in upper:
        return "panel_schedule"
    role = page_role_from_text(text)
    if role == "legend_reference":
        return "unknown"
    return role


def _strong_legend_reference(upper_text: str) -> bool:
    if "LEGEND" not in upper_text:
        return False
    if "P&ID LEGEND" in upper_text or "PIPING AND INSTRUMENTATION" in upper_text:
        return True
    if "LINE DESIGNATION" in upper_text:
        return True
    if "TAGGING LEGEND" in upper_text or "SYMBOLS LEGEND" in upper_text:
        return True
    if "ABBREVIATION" in upper_text and upper_text.count("LEGEND") >= 2:
        return True
    return upper_text.count("LEGEND") >= 3


def _electrical_one_line_signal(upper_text: str) -> bool:
    if "OVERALL ONE LINE" in upper_text or "ONE-LINE DIAGRAM" in upper_text or "SINGLE-LINE DIAGRAM" in upper_text:
        return True
    if "HV YARD SWG" in upper_text or any(f"{code}MSWG" in upper_text for code in BUILDING_CODES):
        return True
    drawing_refs = len(re.findall(r"\bSEE DRAWING\b", upper_text))
    electrical_tokens = sum(
        1
        for token in ("SWG", "SWITCHGEAR", "13.8KV", "4160V", "480Y/277", "FEEDER", " BUS", "GEN-")
        if token in upper_text
    )
    if drawing_refs >= 2 and electrical_tokens >= 2:
        return True
    return "GEN-" in upper_text and "SWG" in upper_text


def _discipline_for_preflight(text: str, role: PageRole) -> Discipline:
    if role in {"instrument_index", "loop_sheet", "io_schedule"}:
        return "Instrumentation & Control"
    return discipline_from_text(text)


def _role_confidence(role: PageRole, text: str) -> float:
    if role == "unknown":
        return 0.25
    if role == "legend_reference" and "ABBREVIATION" in text.upper():
        return 0.9
    if role.endswith("schedule") or role in {"line_list", "instrument_index", "loop_sheet"}:
        return 0.88
    return 0.78


def _role_reason(role: PageRole, text: str) -> str:
    if role == "unknown":
        return "No strong page role keyword detected."
    upper = text.upper()
    if "LEGEND" in upper:
        return "Legend/reference heading detected."
    if "SCHEDULE" in upper:
        return "Schedule heading detected."
    if "ONE LINE" in upper or "ONE-LINE" in upper:
        return "One-line heading detected."
    if "INDEX" in upper:
        return "Index heading detected."
    return f"{role.replace('_', ' ')} keyword detected."
