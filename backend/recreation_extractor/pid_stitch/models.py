from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict


class Point(TypedDict):
    x: float
    y: float


class BoundsDict(TypedDict):
    x: float
    y: float
    width: float
    height: float


@dataclass
class TextSpan:
    text: str
    x: float
    y: float
    width: float
    height: float
    rotation: float = 0.0
    color: str | None = None


@dataclass
class VectorSegment:
    id: str
    kind: Literal["line", "polyline", "curve", "rect", "unknown"]
    points: list[Point]
    bounds: BoundsDict
    stroke: str | None = None
    strokeWidth: float | None = None
    dashed: bool = False


@dataclass
class PageEvidence:
    id: str
    sourceFileId: str
    page: int
    width: float
    height: float
    rotation: int
    cropBounds: BoundsDict
    textSpans: list[TextSpan]
    vectorCount: int
    vectorSegments: list[VectorSegment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContinuationCandidate:
    id: str
    sourceFileId: str
    page: int
    sheetRef: str
    direction: Literal["to", "from", "unknown"]
    label: str
    lineTag: str
    system: str
    edge: Literal["left", "right", "top", "bottom", "inside"]
    position: Point
    bounds: BoundsDict
    confidence: float
    evidenceText: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ContinuationMatch:
    id: str
    sourceCandidateId: str
    targetCandidateId: str
    score: float
    reasons: list[str]
    status: Literal["confirmed", "needs_review", "rejected"] = "needs_review"


@dataclass
class DrawingStyle:
    stroke: str = "#111827"
    fill: str = "none"
    strokeWidth: float = 1.0
    opacity: float = 1.0
    dash: list[float] | None = None
    fontSize: float | None = None
    fontFamily: str = "Arial"


@dataclass
class DrawingObject:
    id: str
    kind: Literal["pipe", "label", "symbol", "region", "source_fragment", "connector"]
    label: str
    points: list[Point]
    bounds: BoundsDict
    style: DrawingStyle
    sourceEvidenceIds: list[str]
    locked: bool = False
    groupId: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DrawingDocument:
    id: str
    projectId: str
    name: str
    width: float
    height: float
    objects: list[DrawingObject]
    sourcePages: list[PageEvidence]
    styles: dict[str, DrawingStyle]
    visualQa: dict[str, Any]


@dataclass
class LayoutOption:
    id: str
    projectId: str
    drawingId: str
    name: str
    description: str
    score: float
    metrics: dict[str, Any]
