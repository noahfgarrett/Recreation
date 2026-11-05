from __future__ import annotations

from typing import Any


def build_template_payload(template_id: str, name: str, review: dict[str, Any]) -> dict[str, Any]:
    disciplines = _string_list(review.get("disciplines"))
    payload = {
        "legendPages": _positive_int_list(review.get("legendPages")),
        "pageRoles": list(review.get("pageRoles", [])) if isinstance(review.get("pageRoles"), list) else [],
        "tableFamilies": _string_list(review.get("tableFamilies")),
        "disciplines": disciplines,
    }
    return {
        "id": template_id,
        "name": name,
        "description": _description_for(disciplines, payload["tableFamilies"]),
        "disciplines": disciplines,
        "payload": payload,
    }


def score_template_match(template: dict[str, Any], review: dict[str, Any]) -> float:
    payload = template.get("payload") if isinstance(template.get("payload"), dict) else {}
    template_disciplines = _string_list(payload.get("disciplines") or template.get("disciplines"))
    template_tables = _string_list(payload.get("tableFamilies") or template.get("tableFamilies"))
    template_legends = _positive_int_list(payload.get("legendPages") or template.get("legendPages"))

    review_disciplines = _string_list(review.get("disciplines"))
    review_tables = _string_list(review.get("tableFamilies"))
    review_legends = _positive_int_list(review.get("legendPages"))

    score = (
        0.45 * _overlap_score(template_disciplines, review_disciplines)
        + 0.35 * _overlap_score(template_tables, review_tables)
        + 0.20 * _overlap_score(template_legends, review_legends)
    )
    return min(round(score, 4), 0.95)


def _description_for(disciplines: list[str], table_families: list[str]) -> str:
    parts = []
    if disciplines:
        parts.append(", ".join(disciplines))
    if table_families:
        parts.append(", ".join(table_families))
    return "Saved hierarchy template" if not parts else f"Saved hierarchy template for {'; '.join(parts)}"


def _overlap_score(left: list[Any], right: list[Any]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / min(len(left_set), len(right_set))


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _positive_int_list(value: Any) -> list[int]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, int) and not isinstance(item, bool) and item > 0]
