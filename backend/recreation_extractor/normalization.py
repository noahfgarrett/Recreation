from __future__ import annotations

import re


WHITESPACE_RE = re.compile(r"\s+")
TAG_CLEAN_RE = re.compile(r"[^A-Z0-9\-_/]")


def normalize_ocr_text(value: str) -> str:
    cleaned = value.upper().replace("–", "-").replace("—", "-")
    if looks_numeric_tag(cleaned):
        cleaned = _replace_o_in_numeric_portion(cleaned)
    cleaned = WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def _replace_o_in_numeric_portion(value: str) -> str:
    """Replace 'O' with '0' only in the numeric portion of a tag.

    The numeric portion starts after the first hyphen, slash, or space
    separator. Alphabetic prefixes like 'FO' in 'FO-101' are preserved.
    """
    separators = ("-", "/", " ")
    for sep in separators:
        idx = value.find(sep)
        if idx != -1:
            prefix = value[:idx + 1]
            suffix = value[idx + 1:].replace("O", "0")
            return prefix + suffix
    # No separator found — apply globally as before (pure numeric string)
    return value.replace("O", "0")


def normalize_tag(value: str) -> str:
    value = normalize_ocr_text(value)
    value = TAG_CLEAN_RE.sub("", value)
    value = re.sub(r"([A-Z]+)\s*(\d)", r"\1-\2", value)
    value = re.sub(r"-+", "-", value)
    return value.strip("-")


def looks_numeric_tag(value: str) -> bool:
    letters = sum(1 for char in value.upper() if char.isalpha())
    digits = sum(1 for char in value if char.isdigit())
    return digits >= 2 and letters <= 4


def score_text_similarity(left: str, right: str) -> float:
    left_set = set(normalize_tag(left))
    right_set = set(normalize_tag(right))
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)
