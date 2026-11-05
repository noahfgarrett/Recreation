from __future__ import annotations

import re
from pathlib import Path

from recreation_extractor.conventions import PROJECT_CODE, PROJECT_CODE_PATTERN
from recreation_extractor.pid_stitch.models import ContinuationCandidate, ContinuationMatch


OPPOSITE_EDGES = {("left", "right"), ("right", "left"), ("top", "bottom"), ("bottom", "top")}
SHEET_REF_RE = re.compile(r"(?<![A-Z0-9]-)\b" + PROJECT_CODE_PATTERN + r"-[A-Z0-9]+-[A-Z0-9][A-Z0-9.-]*[A-Z0-9](?=\b|_)", re.IGNORECASE)
STATUS_PRIORITY = {"confirmed": 0, "needs_review": 1, "rejected": 2}


def rank_continuation_matches(
    candidates: list[ContinuationCandidate],
    source_paths: dict[str, str] | None = None,
) -> list[ContinuationMatch]:
    scored_matches: list[ContinuationMatch] = []
    source_paths = source_paths or {}

    for source in candidates:
        if source.direction == "from":
            continue

        for target in candidates:
            if source.id == target.id or _same_source_page(source, target):
                continue

            score, reasons = _score_pair(source, target, source_paths)
            if score < 35:
                continue

            scored_matches.append(
                ContinuationMatch(
                    id=f"match_{source.id.replace(':', '_')}__{target.id.replace(':', '_')}",
                    sourceCandidateId=source.id,
                    targetCandidateId=target.id,
                    score=score,
                    reasons=reasons,
                    status=_status_for_pair(source, target, score),
                )
            )

    selected_matches: list[ContinuationMatch] = []
    used_candidate_ids: set[str] = set()
    for match in sorted(scored_matches, key=_match_sort_key):
        if match.sourceCandidateId in used_candidate_ids or match.targetCandidateId in used_candidate_ids:
            continue

        selected_matches.append(match)
        used_candidate_ids.add(match.sourceCandidateId)
        used_candidate_ids.add(match.targetCandidateId)

    return selected_matches


def _score_pair(
    source: ContinuationCandidate,
    target: ContinuationCandidate,
    source_paths: dict[str, str] | None = None,
) -> tuple[float, list[str]]:
    if not _directions_compatible(source, target):
        return 0.0, []

    source_paths = source_paths or {}
    score = 0.0
    reasons: list[str] = []
    source_sheet = _source_sheet_ref(source, source_paths)
    target_sheet = _source_sheet_ref(target, source_paths)
    if source.sourceFileId != target.sourceFileId and source_sheet and source_sheet == target_sheet:
        return 0.0, []
    if _is_non_process_reference(source, source_sheet) or _is_non_process_reference(target, target_sheet):
        return 0.0, []

    if source.direction == "to" and target.direction == "from":
        score += 25
        reasons.append("to/from")
    elif source.direction != "unknown" and target.direction != "unknown" and source.direction != target.direction:
        score += 14
        reasons.append("direction")

    if _casefold_equal(source.lineTag, target.lineTag):
        score += 35
        reasons.append("line tag")

    if _casefold_equal(source.system, target.system):
        score += 15
        reasons.append("system")

    if _canonical_sheet_ref(source.sheetRef) in _sheet_refs_from_text(target.evidenceText):
        score += 10
        reasons.append("sheet reference")

    if _canonical_sheet_ref(target.sheetRef) in _sheet_refs_from_text(source.evidenceText):
        score += 10
        reasons.append("reverse sheet reference")

    source_points_to_target = _candidate_points_to_sheet(source, target_sheet, source_sheet)
    target_points_to_source = _candidate_points_to_sheet(target, source_sheet, target_sheet)
    if source_points_to_target and not target_points_to_source and not target.lineTag:
        source_points_to_target = False
    if target_points_to_source and not source_points_to_target and not source.lineTag:
        target_points_to_source = False

    if source_points_to_target:
        score += 18
        reasons.append("target sheet")

    if target_points_to_source:
        score += 18
        reasons.append("source sheet")

    if source_points_to_target and target_points_to_source:
        score += 16
        reasons.append("reciprocal sheet")

    if (source.edge, target.edge) in OPPOSITE_EDGES:
        score += 8
        reasons.append("edge direction")

    if not any(
        reason in {"line tag", "sheet reference", "reverse sheet reference", "target sheet", "source sheet"}
        for reason in reasons
    ):
        return 0.0, []

    score += min(source.confidence, target.confidence) * 7
    return min(score, 100.0), reasons


def _same_source_page(source: ContinuationCandidate, target: ContinuationCandidate) -> bool:
    return source.sourceFileId == target.sourceFileId and source.page == target.page


def _casefold_equal(left: str, right: str) -> bool:
    return bool(left and right and left.casefold() == right.casefold())


def _directions_compatible(source: ContinuationCandidate, target: ContinuationCandidate) -> bool:
    if source.direction == "unknown" or target.direction == "unknown":
        return True
    return source.direction != target.direction


def _status_for_pair(source: ContinuationCandidate, target: ContinuationCandidate, score: float) -> str:
    if source.direction == "unknown" or target.direction == "unknown":
        return "needs_review"
    return "confirmed" if score >= 80 else "needs_review"


def _match_sort_key(match: ContinuationMatch) -> tuple[float, int, str, str]:
    return (
        -match.score,
        STATUS_PRIORITY[match.status],
        match.sourceCandidateId,
        match.targetCandidateId,
    )


def _canonical_sheet_ref(text: str) -> str:
    match = SHEET_REF_RE.search(text)
    return match.group(0).upper() if match else ""


def _sheet_refs_from_text(text: str) -> set[str]:
    return {match.group(0).upper() for match in SHEET_REF_RE.finditer(text)}


def _source_sheet_ref(candidate: ContinuationCandidate, source_paths: dict[str, str]) -> str:
    path = source_paths.get(candidate.sourceFileId)
    if path:
        ref = _canonical_sheet_ref(Path(path).stem)
        if ref:
            return ref
    return _canonical_sheet_ref(candidate.sourceFileId)


def _candidate_points_to_sheet(candidate: ContinuationCandidate, sheet_ref: str, own_sheet_ref: str) -> bool:
    candidate_ref = _canonical_sheet_ref(candidate.sheetRef)
    if not candidate_ref or not sheet_ref:
        return False
    if own_sheet_ref and candidate_ref == own_sheet_ref:
        return False
    return candidate_ref == sheet_ref


def _is_non_process_reference(candidate: ContinuationCandidate, own_sheet_ref: str) -> bool:
    candidate_ref = _canonical_sheet_ref(candidate.sheetRef or candidate.evidenceText)
    if not candidate_ref or candidate.lineTag:
        return False
    if not candidate_ref.startswith(f"{PROJECT_CODE}-ME-"):
        return True
    return bool(own_sheet_ref and candidate_ref == own_sheet_ref)
