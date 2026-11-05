from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from recreation_extractor.conventions import PROJECT_CODE, PROJECT_CODE_PATTERN
from recreation_extractor.pid_stitch.models import ContinuationCandidate, PageEvidence


EQUIPMENT_TAG_RE = re.compile(
    r"\b(?:R-[A-Z0-9]+-[A-Z0-9]+-[A-Z0-9_-]+|(?:AHU|MAU|FCU|DUH|FTR|CAVR|CVR|VAR)-\d+[A-Z0-9-]*|P-(?:\d{1,3}|XX)(?:-[A-Z0-9]+)?|HX-(?:\d{1,3}|XX)(?:-[A-Z0-9]+)?)\b",
    re.IGNORECASE,
)
LINE_TAG_RE = re.compile(
    r'\b(?:\d{1,3}(?:\s+\d/\d)?|\d/\d)"-[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b',
    re.IGNORECASE,
)
SHEET_REF_RE = re.compile(r"\b" + PROJECT_CODE_PATTERN + r"-[A-Z0-9][A-Z0-9_.-]*\b", re.IGNORECASE)


@dataclass(frozen=True)
class PidSourceAssembly:
    id: str
    kind: str
    label: str
    equipmentTags: list[str]
    lineTags: list[str]
    sourcePageIds: list[str]


@dataclass(frozen=True)
class PidSourceGraph:
    groupName: str
    sourcePageIds: list[str]
    equipmentTags: list[str]
    lineTagsBySystem: dict[str, list[str]]
    continuations: list[ContinuationCandidate]
    assemblies: list[PidSourceAssembly]
    metrics: dict[str, Any]


def build_source_graph(
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    source_paths: dict[str, str],
    group_name: str,
) -> PidSourceGraph:
    source_page_ids = [page.id for page in _sorted_pages(pages)]
    equipment_tags = _equipment_tags_for_pages(pages)
    line_tags_by_system = _line_tags_for_pages(pages, group_name)
    continuations = _continuations_for_pages(candidates, pages, source_paths, group_name)
    assemblies = _assemblies_for_group(group_name, pages, equipment_tags, line_tags_by_system)
    return PidSourceGraph(
        groupName=group_name,
        sourcePageIds=source_page_ids,
        equipmentTags=equipment_tags,
        lineTagsBySystem=line_tags_by_system,
        continuations=continuations,
        assemblies=assemblies,
        metrics={
            "equipmentTags": len(equipment_tags),
            "lineTags": sum(len(tags) for tags in line_tags_by_system.values()),
            "continuations": len(continuations),
            "assemblies": len(assemblies),
        },
    )


def _assemblies_for_group(
    group_name: str,
    pages: list[PageEvidence],
    equipment_tags: list[str],
    line_tags_by_system: dict[str, list[str]],
) -> list[PidSourceAssembly]:
    page_ids = [page.id for page in _sorted_pages(pages)]
    if group_name == "CHW / CW":
        definitions = [
            ("chiller_bank", "CHILLER BANK", ["-CH-"], ["CHWS", "CHWR"]),
            ("chw_pumps", "CHW PUMPS", ["-CHW-P-"], ["CHWS", "CHWR"]),
            ("cw_pumps", "CW PUMPS", ["-CW-P-"], ["CWS", "CWR"]),
            ("cooling_water", "COOLING WATER", ["-CT-", "-HX-"], ["CWS", "CWR"]),
        ]
    elif group_name == "HHW / HRW":
        definitions = [
            ("hhw_boilers", "HHW BOILERS", ["-HWB-", "-BLR-"], ["HHWS", "HHWR"]),
            ("hhw_pumps", "HHW PUMPS", ["-HHW-P-", "P-"], ["HHWS", "HHWR"]),
            ("hrw_pumps", "HRW PUMPS", ["-HRW-P-"], ["HRW"]),
            ("hrw_recovery", "HEAT RECOVERY", ["-HX-", "-AS-", "HX-"], ["HRW"]),
        ]
    elif group_name == "PLUMBING WATER":
        definitions = [
            ("domestic_water", "DOMESTIC WATER", ["-EWH-", "-TMV-", "-P-"], ["PW", "DOMW"]),
            ("safety_shower", "SAFETY SHOWER", ["-SS-", "-SHW-", "-MV-"], ["PW", "SSW"]),
        ]
    elif group_name == "CDA":
        definitions = [
            ("cda_compressors", "CDA COMPRESSORS", ["-C-"], ["CDA"]),
            ("cda_dryers", "CDA DRYERS", ["-AD-"], ["CDA"]),
            ("cda_filtration", "CDA FILTRATION", ["-FLTR-", "-ST-", "-ET-"], ["CDA"]),
        ]
    else:
        definitions = []
    assemblies: list[PidSourceAssembly] = []
    for kind, label, equipment_tokens, systems in definitions:
        assembly_equipment = [tag for tag in equipment_tags if any(token in tag for token in equipment_tokens)]
        assembly_lines = _line_tags_for_systems(line_tags_by_system, systems)
        if not assembly_equipment and not assembly_lines:
            continue
        assemblies.append(
            PidSourceAssembly(
                id=f"assembly_{kind}",
                kind=kind,
                label=label,
                equipmentTags=assembly_equipment,
                lineTags=assembly_lines,
                sourcePageIds=page_ids,
            )
        )
    return assemblies


def _continuations_for_pages(
    candidates: list[ContinuationCandidate],
    pages: list[PageEvidence],
    source_paths: dict[str, str],
    group_name: str,
) -> list[ContinuationCandidate]:
    page_source_ids = {page.sourceFileId for page in pages}
    own_refs = {page.sourceFileId: _source_sheet_ref_for_page(page, source_paths) for page in pages}
    filtered: list[ContinuationCandidate] = []
    for candidate in candidates:
        if candidate.sourceFileId not in page_source_ids:
            continue
        if _is_title_block_self_reference(candidate, own_refs.get(candidate.sourceFileId, "")):
            continue
        system = candidate.system or _system_for_tag(candidate.lineTag or candidate.label, group_name)
        if not _system_belongs_to_group(system, group_name):
            continue
        if candidate.lineTag or _is_mechanical_sheet_ref(candidate.sheetRef):
            filtered.append(candidate)
    return sorted(filtered, key=lambda item: (item.system, item.lineTag, item.sheetRef, item.id))


def _equipment_tags_for_pages(pages: list[PageEvidence]) -> list[str]:
    seen: set[str] = set()
    tags: list[str] = []
    for page in pages:
        for span in page.textSpans:
            for match in EQUIPMENT_TAG_RE.finditer(span.text):
                tag = match.group(0).upper()
                if tag not in seen:
                    seen.add(tag)
                    tags.append(tag)
    return sorted(tags, key=_equipment_sort_key)


def _line_tags_for_pages(pages: list[PageEvidence], group_name: str) -> dict[str, list[str]]:
    seen: set[str] = set()
    tags_by_system: dict[str, list[str]] = {}
    for page in pages:
        for span in page.textSpans:
            for match in LINE_TAG_RE.finditer(span.text):
                tag = match.group(0).upper()
                if tag in seen:
                    continue
                seen.add(tag)
                tags_by_system.setdefault(_system_for_tag(tag, group_name), []).append(tag)
    return {system: sorted(tags, key=_line_tag_sort_key) for system, tags in sorted(tags_by_system.items())}


def _line_tags_for_systems(line_tags_by_system: dict[str, list[str]], systems: list[str]) -> list[str]:
    tags: list[str] = []
    for system in systems:
        tags.extend(line_tags_by_system.get(system, []))
    return tags


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


def _is_mechanical_sheet_ref(sheet_ref: str) -> bool:
    return bool(sheet_ref and sheet_ref.upper().startswith(f"{PROJECT_CODE}-ME-"))


def _system_belongs_to_group(system: str, group_name: str) -> bool:
    system = system.upper()
    if group_name == "CHW / CW":
        return "CHW" in system or system in {"CWS", "CWR"}
    if group_name == "HHW / HRW":
        return "HHW" in system or "HRW" in system or system in {"HWS", "HWR"}
    if group_name == "CDA":
        return "CDA" in system
    if group_name == "PLUMBING WATER":
        return system in {"PW", "DOMW", "SSW", "DEFAULT"} or "W" in system
    return True


def _system_for_tag(tag: str, group_name: str) -> str:
    text = tag.upper()
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
    if "CDA" in text or "-CA-" in text or "-IA-" in text:
        return "CDA"
    if "ICW" in text:
        return "ICW"
    if "POTCW" in text:
        return "POTCW"
    if "DOMESTIC" in text or "EWH" in text or "TMV" in text:
        return "DOMW"
    if "SAFETY" in text or "SHOWER" in text:
        return "SSW"
    if group_name == "PLUMBING WATER":
        return "PW"
    return "CHWS" if group_name == "CHW / CW" else "DEFAULT"


def _canonical_sheet_ref(text: str) -> str:
    match = SHEET_REF_RE.search(text.upper())
    return match.group(0).replace("_", "-") if match else ""


def _equipment_sort_key(tag: str) -> tuple[int, str]:
    if "-CH-" in tag:
        return (0, tag)
    if "-P-" in tag:
        return (1, tag)
    if "-CT-" in tag or "-HX-" in tag:
        return (2, tag)
    return (3, tag)


def _line_tag_sort_key(tag: str) -> tuple[int, str]:
    size_match = re.match(r'(\d{1,3})"', tag)
    size = int(size_match.group(1)) if size_match else 999
    return (-size, tag)


def _sorted_pages(pages: list[PageEvidence]) -> list[PageEvidence]:
    return sorted(pages, key=lambda page: (page.sourceFileId, page.page, page.id))
