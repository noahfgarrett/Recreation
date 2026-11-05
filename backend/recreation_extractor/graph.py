from __future__ import annotations

from collections import defaultdict
from hashlib import sha1
import math
import re

from .extraction import Detection, LineSegment
from .models import DrawingGraph, GraphEdge, GraphNode, Layout, Port, ReviewItem
from .normalization import score_text_similarity


DRAWING_RE = re.compile(r"PID-(\d{3,5})")
CONTINUED_ON_RE = re.compile(r"(?:CONTINUED\s+ON|SEE\s+SHEET|REF[:\s])\s*([A-Z0-9\-_.]+)", re.IGNORECASE)
LINE_ID_RE = re.compile(
    r"^(?:(\d{1,3}\"?)-)?"       # optional size, e.g. 2" or 10
    r"([A-Z]{1,4})-"             # service code, e.g. PW
    r"(\d{3,6})"                 # sequence number, e.g. 1001
    r"(?:-(.+))?$",              # optional spec/class, e.g. A3B or A3B-H
)


def parse_line_id(line_id: str) -> dict[str, str | None]:
    """Parse a line ID into components.

    Returns dict with keys: size, service, sequence, spec
    Any component not found returns None.
    """
    result: dict[str, str | None] = {"size": None, "service": None, "sequence": None, "spec": None}
    cleaned = line_id.strip()
    match = LINE_ID_RE.match(cleaned)
    if not match:
        return result
    result["size"] = match.group(1) if match.group(1) else None
    result["service"] = match.group(2) if match.group(2) else None
    result["sequence"] = match.group(3) if match.group(3) else None
    result["spec"] = match.group(4) if match.group(4) else None
    return result


def build_graph(
    project_id: str,
    detections: list[Detection],
    line_segments: tuple[LineSegment, ...] | None = None,
) -> DrawingGraph:
    tag_detections = [item for item in detections if item.kind == "tag"]
    line_detections = [item for item in detections if item.kind in {"line_id", "cable_id"}]
    continuation_detections = [item for item in detections if item.kind == "continuation_ref"]
    legend_detections = [item for item in detections if item.kind == "legend_candidate"]

    nodes = [_node_from_detection(project_id, index, detection) for index, detection in enumerate(tag_detections)]
    nodes = _merge_duplicate_nodes(nodes)
    edges = infer_edges(project_id, nodes, line_detections, continuation_detections, line_segments or ())
    review_items = build_review_items(nodes, edges, legend_detections, continuation_detections)
    return DrawingGraph(projectId=project_id, nodes=nodes, edges=edges, reviewItems=review_items)


def _node_from_detection(project_id: str, index: int, detection: Detection) -> GraphNode:
    kind, symbol_id = infer_node_kind(detection.label)
    x = 120 + (index % 5) * 260
    y = 120 + (index // 5) * 170
    if detection.bounds:
        # PDF coordinates are in points (1/72 inch). Letter-size is 612x792 pts.
        # Scale to a canvas width of ~800px so nodes spread across a usable range.
        _PDF_SCALE = 800 / 612  # ~1.31
        x = detection.bounds.x * _PDF_SCALE + (detection.page - 1) * 80
        y = detection.bounds.y * _PDF_SCALE + (detection.page - 1) * 48
    node_fingerprint = f"{project_id}:{detection.sourceFileId}:{detection.page}:{detection.label}:{detection.evidence.id}"
    node_id = f"node_{sha1(node_fingerprint.encode()).hexdigest()[:14]}"
    ports = [
        Port(id=f"{node_id}:left", label="in", side="left"),
        Port(id=f"{node_id}:right", label="out", side="right"),
        Port(id=f"{node_id}:top", label="signal", side="top"),
        Port(id=f"{node_id}:bottom", label="drain", side="bottom"),
    ]
    return GraphNode(
        id=node_id,
        kind=kind,
        tag=detection.label,
        symbolId=symbol_id,
        ports=ports,
        sourceEvidence=[detection.evidence],
        confidence=detection.confidence,
        locked=False,
        layout=Layout(x=x, y=y),
    )


def _merge_duplicate_nodes(nodes: list[GraphNode]) -> list[GraphNode]:
    """Merge nodes that share the same normalized tag (case-insensitive).

    The node with the highest confidence becomes the primary.  Source evidence
    from all duplicates is merged into it and confidence is averaged.
    """
    groups: dict[str, list[GraphNode]] = defaultdict(list)
    for node in nodes:
        key = node.tag.upper()
        groups[key].append(node)

    merged: list[GraphNode] = []
    for group in groups.values():
        if len(group) == 1:
            merged.append(group[0])
            continue

        # Primary = highest confidence
        group.sort(key=lambda n: n.confidence, reverse=True)
        primary = group[0]

        # Combine evidence from all duplicates
        all_evidence = list(primary.sourceEvidence)
        seen_evidence_ids: set[str] = {ev.id for ev in all_evidence}
        for duplicate in group[1:]:
            for ev in duplicate.sourceEvidence:
                if ev.id not in seen_evidence_ids:
                    all_evidence.append(ev)
                    seen_evidence_ids.add(ev.id)

        # Average confidence
        avg_confidence = sum(n.confidence for n in group) / len(group)

        merged.append(
            GraphNode(
                id=primary.id,
                kind=primary.kind,
                tag=primary.tag,
                symbolId=primary.symbolId,
                ports=primary.ports,
                sourceEvidence=all_evidence,
                confidence=round(avg_confidence, 4),
                locked=primary.locked,
                layout=primary.layout,
            )
        )
    return merged


def infer_node_kind(label: str) -> tuple[str, str]:
    if label.startswith(("P-", "PU-")):
        return "equipment", "pump"
    if label.startswith(("HX-",)):
        return "equipment", "heat-exchanger"
    if label.startswith(("TK-", "VSL-", "E-")):
        return "equipment", "vessel"
    if label.startswith(("XV-", "CV-", "HV-", "V-")):
        return "valve", "valve"
    if label.startswith(("JB-",)):
        return "junction_box", "junction-box"
    if label.startswith(("PNL-",)):
        return "panel", "panel"
    if label.startswith(("PT-", "TT-", "FT-", "LT-", "FIT-", "TIC-", "PIC-", "LIC-")):
        return "instrument", "instrument-bubble"
    if label.startswith(("MOT-", "MTR-")):
        return "motor", "motor"
    if label.startswith(("BKR-", "CB-")):
        return "breaker", "breaker"
    if label.startswith(("XFMR-", "TR-")):
        return "transformer", "transformer"
    if label.startswith(("VFD-", "ASD-")):
        return "vfd", "vfd"
    if label.startswith(("MCC-",)):
        return "mcc", "mcc"
    if label.startswith(("SWG-", "SWGR-")):
        return "switchgear", "switchgear"
    return "unknown", "unknown"


def infer_edges(
    project_id: str,
    nodes: list[GraphNode],
    line_detections: list[Detection],
    continuation_detections: list[Detection],
    line_segments: tuple[LineSegment, ...] = (),
) -> list[GraphEdge]:
    edges: list[GraphEdge] = []
    seen_edges: set[str] = set()
    by_page: dict[int, list[GraphNode]] = defaultdict(list)
    for node in nodes:
        page = node.sourceEvidence[0].page if node.sourceEvidence else 1
        by_page[page].append(node)

    segments_by_page: dict[int, list[LineSegment]] = defaultdict(list)
    for seg in line_segments:
        segments_by_page[seg.page].append(seg)

    line_labels_by_page: dict[int, list[str]] = defaultdict(list)
    for detection in line_detections:
        if detection.label not in line_labels_by_page[detection.page]:
            line_labels_by_page[detection.page].append(detection.label)

    off_page_nodes = _build_off_page_nodes(project_id, continuation_detections)
    nodes.extend(off_page_nodes)
    for node in off_page_nodes:
        by_page[_node_page(node)].append(node)

    for page, page_nodes in by_page.items():
        line_labels = line_labels_by_page.get(page, [])
        process_nodes = sorted(
            [node for node in page_nodes if node.kind in {
                "equipment", "valve", "junction_box", "panel",
                "motor", "breaker", "transformer", "vfd", "mcc", "switchgear",
            }],
            key=lambda node: (node.layout.x, node.layout.y),
        )
        instruments = [node for node in page_nodes if node.kind == "instrument"]
        page_continuations = [node for node in page_nodes if node.kind == "off_page_connector"]

        for index, (left, right) in enumerate(zip(process_nodes, process_nodes[1:])):
            label = _line_label(line_labels, index)
            _add_edge(
                edges,
                seen_edges,
                source=left,
                target=right,
                source_side="right" if left.layout.x <= right.layout.x else "bottom",
                label=label,
                kind=_edge_kind(label),
                confidence=0.72 if label else 0.46,
            )

        for index in range(0, max(0, len(process_nodes) - 3), 3):
            source = process_nodes[index]
            target = process_nodes[index + 3]
            label = _line_label(line_labels, index + len(process_nodes))
            _add_edge(
                edges,
                seen_edges,
                source=source,
                target=target,
                source_side="bottom",
                label=label,
                kind="pipe",
                confidence=0.58,
                status="needs_review",
            )

        for instrument in instruments:
            if not process_nodes:
                continue
            anchor = min(process_nodes, key=lambda node: _distance(node, instrument))
            _add_edge(
                edges,
                seen_edges,
                source=anchor,
                target=instrument,
                source_side="top" if instrument.layout.y < anchor.layout.y else "bottom",
                label="instrument signal",
                kind="instrument_signal",
                confidence=0.66,
                status="needs_review",
            )

        for continuation in page_continuations:
            if not process_nodes:
                continue
            anchor = min(process_nodes, key=lambda node: _distance(node, continuation))
            if continuation.tag.startswith("FROM"):
                _add_edge(
                    edges,
                    seen_edges,
                    source=continuation,
                    target=anchor,
                    source_side="right",
                    label=continuation.tag,
                    kind="continuation",
                    confidence=0.62,
                    status="needs_review",
                )
            else:
                _add_edge(
                    edges,
                    seen_edges,
                    source=anchor,
                    target=continuation,
                    source_side="right",
                    label=continuation.tag,
                    kind="continuation",
                    confidence=0.62,
                    status="needs_review",
                )

        page_segments = segments_by_page.get(page, [])
        if page_segments:
            all_page_nodes = process_nodes + instruments + page_continuations
            _add_segment_traced_edges(edges, seen_edges, all_page_nodes, page_segments)

    _add_cross_sheet_continuations(edges, seen_edges, off_page_nodes)
    return edges


def _segment_touches_node(segment: LineSegment, node: GraphNode, tolerance: float = 8.0) -> bool:
    """Check if either endpoint of a line segment falls within a node's bounding box (with tolerance)."""
    layout = node.layout
    x_min = layout.x - tolerance
    y_min = layout.y - tolerance
    x_max = layout.x + layout.width + tolerance
    y_max = layout.y + layout.height + tolerance
    p0_inside = x_min <= segment.x0 <= x_max and y_min <= segment.y0 <= y_max
    p1_inside = x_min <= segment.x1 <= x_max and y_min <= segment.y1 <= y_max
    return p0_inside or p1_inside


def _add_segment_traced_edges(
    edges: list[GraphEdge],
    seen_edges: set[str],
    nodes: list[GraphNode],
    segments: list[LineSegment],
) -> None:
    """Add edges between nodes that are physically connected by drawing line segments."""
    for segment in segments:
        touching: list[GraphNode] = []
        for node in nodes:
            if _segment_touches_node(segment, node):
                touching.append(node)
            if len(touching) >= 2:
                break
        if len(touching) == 2:
            source, target = touching[0], touching[1]
            if source.layout.x > target.layout.x:
                source, target = target, source
            _add_edge(
                edges,
                seen_edges,
                source=source,
                target=target,
                source_side="right",
                label="traced connection",
                kind="pipe",
                confidence=0.82,
            )


def _build_off_page_nodes(project_id: str, continuation_detections: list[Detection]) -> list[GraphNode]:
    off_page_nodes: list[GraphNode] = []
    for ref in continuation_detections:
        label = ref.label
        node_id = f"opc_{sha1((project_id + ref.sourceFileId + label + str(ref.page)).encode()).hexdigest()[:14]}"
        x = 70 if label.startswith("FROM") else 850
        y = 100 + (ref.page % 6) * 105
        off_page_nodes.append(
            GraphNode(
                id=node_id,
                kind="off_page_connector",
                tag=label,
                symbolId="off-page-connector",
                ports=[
                    Port(id=f"{node_id}:left", label="in", side="left"),
                    Port(id=f"{node_id}:right", label="out", side="right"),
                ],
                sourceEvidence=[ref.evidence],
                confidence=ref.confidence,
                locked=False,
                layout=Layout(x=x + (ref.page - 1) * 70, y=y, width=190, height=64),
            )
        )
    return off_page_nodes


def _add_cross_sheet_continuations(
    edges: list[GraphEdge],
    seen_edges: set[str],
    off_page_nodes: list[GraphNode],
) -> None:
    by_page: dict[int, list[GraphNode]] = defaultdict(list)
    for node in off_page_nodes:
        by_page[_node_page(node)].append(node)

    for source in off_page_nodes:
        if not source.tag.startswith("TO"):
            continue
        target_page = _target_page(source.tag)
        if target_page is None:
            # Try extracting a drawing number from alternative patterns
            target_page = _target_page_extended(source.tag)
        if target_page is None:
            continue
        source_page = _node_page(source)
        expected_from = f"FROM PID-{source_page:03d}"
        candidates = [node for node in by_page.get(target_page, []) if node.tag.startswith(expected_from)]
        if not candidates:
            candidates = [node for node in by_page.get(target_page, []) if node.tag.startswith("FROM")]
        # Fuzzy match: if exact matching found nothing, score all FROM nodes
        # on the target page by text similarity
        if not candidates:
            from_nodes = [node for node in by_page.get(target_page, []) if "FROM" in node.tag.upper()]
            if from_nodes:
                scored = sorted(
                    from_nodes,
                    key=lambda node: score_text_similarity(source.tag, node.tag),
                    reverse=True,
                )
                if score_text_similarity(source.tag, scored[0].tag) > 0.6:
                    candidates = [scored[0]]
        if not candidates:
            continue
        target = candidates[0]
        _add_edge(
            edges,
            seen_edges,
            source=source,
            target=target,
            source_side="right",
            label=f"{source.tag} / {target.tag}",
            kind="continuation",
            confidence=0.68,
            status="needs_review",
            continuation_refs=[evidence.id for evidence in source.sourceEvidence + target.sourceEvidence],
        )


def _add_edge(
    edges: list[GraphEdge],
    seen_edges: set[str],
    *,
    source: GraphNode,
    target: GraphNode,
    source_side: str,
    label: str,
    kind: str,
    confidence: float,
    status: str | None = None,
    continuation_refs: list[str] | None = None,
) -> None:
    if source.id == target.id:
        return
    label = label or "unlabeled connection"
    source_port = f"{source.id}:{source_side}"
    target_port = f"{target.id}:left"
    fingerprint = f"{source_port}:{target_port}:{kind}:{label}"
    if fingerprint in seen_edges:
        return
    seen_edges.add(fingerprint)
    edge_id = f"edge_{sha1(fingerprint.encode()).hexdigest()[:14]}"
    line_or_cable_id = label if kind in {"pipe", "cable", "conduit"} and label != "unlabeled connection" else None
    parsed = parse_line_id(line_or_cable_id) if line_or_cable_id else None
    edges.append(
        GraphEdge(
            id=edge_id,
            kind=kind,  # type: ignore[arg-type]
            sourcePort=source_port,
            targetPort=target_port,
            label=label,
            lineOrCableId=line_or_cable_id,
            waypoints=[],
            continuationRefs=continuation_refs or [],
            sourceEvidence=source.sourceEvidence[:1] + target.sourceEvidence[:1],
            confidence=confidence,
            status=(status or ("needs_review" if confidence < 0.7 else "inferred")),  # type: ignore[arg-type]
            parsedLineId=parsed,
        )
    )


def _edge_kind(label: str) -> str:
    if label.startswith(("C-", "CBL-", "W-")):
        return "cable"
    if label.startswith(("COND-", "CNDT-")):
        return "conduit"
    return "pipe"


def _line_label(line_labels: list[str], index: int) -> str:
    return line_labels[index % len(line_labels)] if line_labels else ""


def _node_page(node: GraphNode) -> int:
    return node.sourceEvidence[0].page if node.sourceEvidence else 1


def _distance(left: GraphNode, right: GraphNode) -> float:
    return math.hypot(left.layout.x - right.layout.x, left.layout.y - right.layout.y)


def _target_page(label: str) -> int | None:
    match = DRAWING_RE.search(label)
    if not match:
        return None
    return int(match.group(1))


def _target_page_extended(label: str) -> int | None:
    """Extract a target page from alternative continuation patterns.

    Handles 'CONTINUED ON <ref>', 'SEE SHEET <ref>', 'REF: <ref>' and
    then tries to find a PID number within the extracted reference.
    """
    match = CONTINUED_ON_RE.search(label)
    if match:
        ref = match.group(1)
        pid_match = DRAWING_RE.search(ref)
        if pid_match:
            return int(pid_match.group(1))
        # Try bare numeric reference (e.g. "SEE SHEET 003")
        digits = re.search(r"(\d{2,5})", ref)
        if digits:
            return int(digits.group(1))
    return None


def build_review_items(
    nodes: list[GraphNode],
    edges: list[GraphEdge],
    legend_detections: list[Detection],
    continuation_detections: list[Detection],
) -> list[ReviewItem]:
    review: list[ReviewItem] = []
    for detection in legend_detections:
        review.append(
            ReviewItem(
                id=f"review_{detection.id}",
                type="symbol_confirmation",
                candidates=[{"symbolId": "project-legend", "label": detection.label}],
                recommendedAction="Confirm project legend symbols before running high-confidence symbol classification.",
                evidence=[detection.evidence],
                resolvedBy=None,
                resolution=None,
            )
        )

    for edge in edges:
        if edge.status == "needs_review":
            review.append(
                ReviewItem(
                    id=f"review_{edge.id}",
                    type="continuation_match" if edge.kind in {"continuation", "cable"} else "unconnected_item",
                    candidates=[{"edgeId": edge.id, "label": edge.label}],
                    recommendedAction="Review this inferred connection before locking the combined drawing.",
                    evidence=edge.sourceEvidence,
                    resolvedBy=None,
                    resolution=None,
                )
            )

    for node in nodes:
        if node.confidence < 0.7:
            review.append(
                ReviewItem(
                    id=f"review_{node.id}",
                    type="low_confidence_tag",
                    candidates=[{"nodeId": node.id, "tag": node.tag}],
                    recommendedAction="Confirm or correct this detected tag.",
                    evidence=node.sourceEvidence,
                    resolvedBy=None,
                    resolution=None,
                )
            )

    for detection in continuation_detections:
        review.append(
            ReviewItem(
                id=f"review_{detection.id}",
                type="continuation_match",
                candidates=[{"label": detection.label, "sourceFileId": detection.sourceFileId, "page": detection.page}],
                recommendedAction="Match this off-page continuation to its destination drawing or mark it unresolved.",
                evidence=[detection.evidence],
                resolvedBy=None,
                resolution=None,
            )
        )

    return _dedupe_review(review)


def _dedupe_review(items: list[ReviewItem]) -> list[ReviewItem]:
    seen: set[str] = set()
    result: list[ReviewItem] = []
    for item in items:
        if item.id in seen:
            continue
        seen.add(item.id)
        result.append(item)
    return result
