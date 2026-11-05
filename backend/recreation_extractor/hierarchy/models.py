from __future__ import annotations

import dataclasses
import re
from dataclasses import dataclass, field
from typing import Any, Literal

Discipline = Literal[
    "Electrical",
    "Process / P&ID",
    "Mechanical",
    "Mechanical Dry",
    "Mechanical Wet",
    "Plumbing",
    "Instrumentation & Control",
    "Security",
    "Fire Alarm",
    "Fire Protection",
    "Life Safety Services",
    "Telecom / Low Voltage",
    "Controls / BAS",
    "CSA",
    "General / Reference",
    "Mixed Package",
    "Unknown",
]

PageRole = Literal[
    "legend_reference",
    "abbreviations",
    "general_notes",
    "sheet_index",
    "one_line",
    "riser",
    "pid",
    "plan_view",
    "detail_sheet",
    "panel_schedule",
    "equipment_schedule",
    "line_list",
    "instrument_index",
    "loop_sheet",
    "cable_schedule",
    "io_schedule",
    "control_panel",
    "fire_alarm_riser",
    "security_riser",
    "plumbing_riser",
    "mechanical_schedule",
    "csa_plan_detail",
    "vendor_drawing",
    "unknown",
]

HierarchyViewId = Literal[
    "electrical_power",
    "commissioning_dependencies",
    "process_flow",
    "mechanical_system",
    "ic_loop",
    "security_device",
    "fire_life_safety",
    "plumbing_fire_protection",
    "equipment_asset",
    "location_area",
    "source_document",
    "overview_export",
]

DISCIPLINES: tuple[Discipline, ...] = (
    "Electrical",
    "Process / P&ID",
    "Mechanical",
    "Mechanical Dry",
    "Mechanical Wet",
    "Plumbing",
    "Instrumentation & Control",
    "Security",
    "Fire Alarm",
    "Fire Protection",
    "Life Safety Services",
    "Telecom / Low Voltage",
    "Controls / BAS",
    "CSA",
    "General / Reference",
    "Mixed Package",
    "Unknown",
)

PAGE_ROLES: tuple[PageRole, ...] = (
    "legend_reference",
    "abbreviations",
    "general_notes",
    "sheet_index",
    "one_line",
    "riser",
    "pid",
    "plan_view",
    "detail_sheet",
    "panel_schedule",
    "equipment_schedule",
    "line_list",
    "instrument_index",
    "loop_sheet",
    "cable_schedule",
    "io_schedule",
    "control_panel",
    "fire_alarm_riser",
    "security_riser",
    "plumbing_riser",
    "mechanical_schedule",
    "csa_plan_detail",
    "vendor_drawing",
    "unknown",
)

HIERARCHY_VIEW_IDS: tuple[HierarchyViewId, ...] = (
    "electrical_power",
    "commissioning_dependencies",
    "process_flow",
    "mechanical_system",
    "ic_loop",
    "security_device",
    "fire_life_safety",
    "plumbing_fire_protection",
    "equipment_asset",
    "location_area",
    "source_document",
    "overview_export",
)

DISCIPLINE_PATTERNS: tuple[tuple[Discipline, re.Pattern[str]], ...] = (
    ("Process / P&ID", re.compile(r"\b(P\s*&\s*ID|PIPING\s+AND\s+INSTRUMENTATION|PROCESS\s+FLOW|PROCESS\s+LINE)\b", re.I)),
    ("Instrumentation & Control", re.compile(r"\b(I\s*&\s*C|I/?C|INSTRUMENTATION|CONTROL(?:S)?\s+LOOP|LOOP\s+SHEET)\b", re.I)),
    ("Electrical", re.compile(r"\b(ELECTRICAL|ONE[-\s]?LINE|PANEL\s+SCHEDULE|SWITCHGEAR|GENERATOR|MCC|MDP)\b", re.I)),
    ("Fire Alarm", re.compile(r"\b(FIRE\s+ALARM|FACP|NAC|INITIATING\s+DEVICE)\b", re.I)),
    ("Fire Protection", re.compile(r"\b(FIRE\s+PROTECTION|SPRINKLER|STANDPIPE|FIRE\s+PUMP)\b", re.I)),
    ("Life Safety Services", re.compile(r"\b(LIFE\s+SAFETY|EGRESS|EMERGENCY\s+LIGHTING)\b", re.I)),
    ("Security", re.compile(r"\b(SECURITY|ACCESS\s+CONTROL|CCTV|CARD\s+READER)\b", re.I)),
    ("Telecom / Low Voltage", re.compile(r"\b(TELECOM|LOW\s+VOLTAGE|DATA|COMMUNICATIONS)\b", re.I)),
    ("Controls / BAS", re.compile(r"\b(BAS|BUILDING\s+AUTOMATION|DDC|CONTROL\s+PANEL)\b", re.I)),
    ("Plumbing", re.compile(r"\b(PLUMBING|DOMESTIC\s+WATER|SANITARY|STORM\s+DRAIN)\b", re.I)),
    ("Mechanical Wet", re.compile(r"\b(CHILLED\s+WATER|HOT\s+WATER|HYDRONIC|CONDENSATE|STEAM)\b", re.I)),
    ("Mechanical Dry", re.compile(r"\b(HVAC|DUCT|AIR\s+HANDLING|AHU|EXHAUST\s+FAN)\b", re.I)),
    ("Mechanical", re.compile(r"\b(MECHANICAL|PUMP|CHILLER|BOILER|FAN)\b", re.I)),
    ("CSA", re.compile(r"\b(CIVIL|STRUCTURAL|ARCHITECTURAL|FOUNDATION|FRAMING|SITE\s+PLAN)\b", re.I)),
)

PAGE_ROLE_PATTERNS: tuple[tuple[PageRole, re.Pattern[str]], ...] = (
    ("panel_schedule", re.compile(r"\bPANEL\s+SCHEDULE\b", re.I)),
    ("one_line", re.compile(r"\b(ONE[-\s]?LINE|SINGLE[-\s]?LINE)\b", re.I)),
    ("line_list", re.compile(r"\bLINE\s+LIST\b", re.I)),
    ("instrument_index", re.compile(r"\bINSTRUMENT\s+INDEX\b", re.I)),
    ("loop_sheet", re.compile(r"\bLOOP\s+SHEET\b", re.I)),
    ("equipment_schedule", re.compile(r"\bEQUIPMENT\s+SCHEDULE\b", re.I)),
    ("cable_schedule", re.compile(r"\bCABLE\s+SCHEDULE\b", re.I)),
    ("io_schedule", re.compile(r"\b(I/O|IO)\s+SCHEDULE\b", re.I)),
    ("fire_alarm_riser", re.compile(r"\bFIRE\s+ALARM\s+RISER\b", re.I)),
    ("security_riser", re.compile(r"\bSECURITY\s+RISER\b", re.I)),
    ("plumbing_riser", re.compile(r"\bPLUMBING\s+RISER\b", re.I)),
    ("mechanical_schedule", re.compile(r"\bMECHANICAL\s+SCHEDULE\b", re.I)),
    ("riser", re.compile(r"\bRISER\b", re.I)),
    ("pid", re.compile(r"\b(P\s*&\s*ID|PIPING\s+AND\s+INSTRUMENTATION)\b", re.I)),
    ("legend_reference", re.compile(r"\b(LEGEND|SYMBOLS|ABBREVIATIONS|TAGGING\s+LEGEND)\b", re.I)),
    ("general_notes", re.compile(r"\bGENERAL\s+NOTES\b", re.I)),
    ("sheet_index", re.compile(r"\b(SHEET\s+INDEX|DRAWING\s+LIST)\b", re.I)),
    ("detail_sheet", re.compile(r"\bDETAILS?\b", re.I)),
    ("plan_view", re.compile(r"\bPLAN\b", re.I)),
    ("vendor_drawing", re.compile(r"\b(VENDOR|MANUFACTURER|SHOP\s+DRAWING)\b", re.I)),
)


@dataclass
class PageRoleAssignment:
    sourceFileId: str
    page: int
    role: PageRole
    confidence: float
    reason: str
    title: str = ""
    sheetNumber: str = ""


@dataclass
class PreflightReview:
    projectId: str
    status: Literal["draft", "confirmed"] = "draft"
    disciplines: list[Discipline] = field(default_factory=list)
    disciplineConfidence: float = 0.0
    legendPages: list[int] = field(default_factory=list)
    legendConfidence: float = 0.0
    pageRoles: list[PageRoleAssignment] = field(default_factory=list)
    tableFamilies: list[str] = field(default_factory=list)
    suggestedTemplateIds: list[str] = field(default_factory=list)
    appliedTemplateId: str | None = None
    warnings: list[str] = field(default_factory=list)


@dataclass
class Rulebook:
    projectId: str
    disciplines: list[Discipline]
    legendPages: list[int]
    acronymMap: dict[str, str] = field(default_factory=dict)
    symbolRules: list[dict[str, Any]] = field(default_factory=list)
    tagRules: list[dict[str, Any]] = field(default_factory=list)
    suppressionRules: list[dict[str, Any]] = field(default_factory=list)
    sourceEvidence: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class HierarchyView:
    id: HierarchyViewId
    label: str
    discipline: Discipline
    nodes: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    metrics: dict[str, Any] = field(default_factory=dict)


@dataclass
class TemplateSummary:
    id: str
    name: str
    disciplines: list[Discipline]
    description: str
    confidence: float = 0.0


def discipline_from_text(text: str) -> Discipline:
    for discipline, pattern in DISCIPLINE_PATTERNS:
        if pattern.search(text):
            return discipline
    return "Unknown"


def page_role_from_text(text: str) -> PageRole:
    for role, pattern in PAGE_ROLE_PATTERNS:
        if pattern.search(text):
            return role
    return "unknown"


def to_plain_dict(value: Any) -> Any:
    if dataclasses.is_dataclass(value):
        return {field.name: to_plain_dict(getattr(value, field.name)) for field in dataclasses.fields(value)}
    if isinstance(value, list):
        return [to_plain_dict(item) for item in value]
    if isinstance(value, tuple):
        return [to_plain_dict(item) for item in value]
    if isinstance(value, dict):
        return {str(key): to_plain_dict(item) for key, item in value.items()}
    return value
