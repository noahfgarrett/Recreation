from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal


NodeKind = Literal[
    "equipment",
    "instrument",
    "valve",
    "panel",
    "junction_box",
    "off_page_connector",
    "cable_endpoint",
    "unknown",
]

EdgeKind = Literal["pipe", "instrument_signal", "cable", "conduit", "continuation", "unknown"]
ReviewStatus = Literal["open", "resolved", "ignored"]


def to_dict(value: Any) -> Any:
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    if isinstance(value, list):
        return [to_dict(item) for item in value]
    if isinstance(value, dict):
        return {key: to_dict(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class Bounds:
    page: int
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class SourceEvidence:
    id: str
    sourceFileId: str
    page: int
    bounds: Bounds | None
    text: str
    confidence: float


@dataclass(frozen=True)
class Port:
    id: str
    label: str
    side: Literal["top", "right", "bottom", "left"]


@dataclass
class Layout:
    x: float
    y: float
    width: float = 160
    height: float = 88
    groupId: str | None = None
    waypoints: list[dict[str, float]] = field(default_factory=list)


@dataclass
class GraphNode:
    id: str
    kind: NodeKind
    tag: str
    symbolId: str | None
    ports: list[Port]
    sourceEvidence: list[SourceEvidence]
    confidence: float
    locked: bool
    layout: Layout


@dataclass
class GraphEdge:
    id: str
    kind: EdgeKind
    sourcePort: str
    targetPort: str
    label: str
    lineOrCableId: str | None
    waypoints: list[dict[str, float]]
    continuationRefs: list[str]
    sourceEvidence: list[SourceEvidence]
    confidence: float
    status: Literal["confirmed", "needs_review", "inferred"]
    parsedLineId: dict[str, str | None] | None = None


@dataclass
class ReviewItem:
    id: str
    type: Literal[
        "symbol_confirmation",
        "continuation_match",
        "low_confidence_tag",
        "unconnected_item",
        "export_warning",
    ]
    candidates: list[dict[str, Any]]
    recommendedAction: str
    evidence: list[SourceEvidence]
    resolvedBy: str | None
    resolution: dict[str, Any] | None
    status: ReviewStatus = "open"


@dataclass
class DrawingGraph:
    projectId: str
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    reviewItems: list[ReviewItem]


@dataclass
class SourceFile:
    id: str
    projectId: str
    path: str
    name: str
    sha256: str
    pageCount: int = 0


@dataclass
class Project:
    id: str
    name: str
    createdAt: str
    updatedAt: str
