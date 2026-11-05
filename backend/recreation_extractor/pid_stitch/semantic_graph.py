from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal

from recreation_extractor.conventions import PROJECT_CODE, PROJECT_CODE_PATTERN
from recreation_extractor.pid_stitch.models import BoundsDict, ContinuationCandidate, ContinuationMatch, PageEvidence, Point, TextSpan, VectorSegment
from recreation_extractor.pid_stitch.source_graph import LINE_TAG_RE
from recreation_extractor.pid_stitch.system_colors import SystemColorMap, canonical_system, system_for_text


EQUIPMENT_TAG_RE = re.compile(
    r"\b(?:R-[A-Z0-9]+-[A-Z0-9]+-[A-Z0-9_-]+|(?:AHU|MAU|FCU|DUH|FTR|CAVR|CVR|VAR|SHW|ST|BA|IE)-\d+[A-Z0-9-]*(?:-[A-Z0-9]+)?|P-(?:\d{1,3}|XX)(?:-[A-Z0-9]+)?|HX-(?:\d{1,3}|XX)(?:-[A-Z0-9]+)?)\b",
    re.IGNORECASE,
)
INSTRUMENT_TAG_RE = re.compile(
    r"\b" + PROJECT_CODE_PATTERN + r"-[A-Z0-9]+(?:-[A-Z0-9]+){1,4}-(?:PDIT|PDT|PIT|FIT|TIT|LIT|AIT|PT|FT|TT|LT|PI|FI|TI|FE|TE|AT)-\d+[A-Z0-9]*\b"
    r"|(?<![A-Z0-9]-)\b(?:PDIT|PDT|PIT|FIT|TIT|LIT|AIT|PT|FT|TT|LT|PI|FI|TI|FE|TE|AT)-?\d+[A-Z0-9-]*\b",
    re.IGNORECASE,
)
DEVICE_TAG_RE = re.compile(
    r"\b(?:XV|HV|MOV|FCV|PRV|PSV|SSV|SDV|BDV|LV|PV|TV|FV|V[A-Z]?)-?\d+[A-Z0-9-]*\b",
    re.IGNORECASE,
)
SPLIT_INSTRUMENT_CODE_RE = re.compile(
    r"^(?:PDIT|PDT|PIT|FIT|TIT|LIT|AIT|TIC|PIC|FIC|LIC|PDI|PT|FT|TT|LT|PI|FI|TI|FE|TE|LSHH|LSLL|LSH|LSL|PSH|PSL|TSH|TSL|HSI|HS|ZS|ZI)$",
    re.IGNORECASE,
)
SPLIT_DEVICE_CODE_RE = re.compile(
    r"^(?:XV|HV|MOV|FCV|PRV|PSV|SSV|SDV|BDV|LV|PV|TV|FV|TCV|VFCI|ZSC|ZSO)$",
    re.IGNORECASE,
)
SPLIT_TAG_SUFFIX_RE = re.compile(
    r"^(?:\d{1,3}[A-Z]?(?:-[A-Z0-9]+){1,4}|[A-Z]-?[A-Z0-9]{1,8}-[A-Z0-9-]+|REF-[A-Z0-9-]+|CHW-DELTA)$",
    re.IGNORECASE,
)
SPLIT_TAG_SKIP_RE = re.compile(
    r'^(?:-|AUTO|CLOSE|FAULT|MANUAL|OPEN|START|STATUS|STOP|\(N\+1\)|\(\d+\)|\d+|0-\d+\s*(?:PSI|°?F|GPM|%|"?))$',
    re.IGNORECASE,
)
MAX_TOPOLOGY_VECTOR_COMPONENT_SCAN = 700

CONTROL_POINT_TAG_RE = re.compile(r"\b(?:\d{2}[A-Z]?-[A-Z0-9]+-[A-Z0-9]+|REF-[A-Z0-9-]+|CHW-DELTA)\b", re.IGNORECASE)
CONTROL_FUNCTION_RE = re.compile(
    r"\b(?:AI|AO|DI|DO|ES|FC|FCV|FS|FSL|HS|HSI|IT|P|PDI|PDIT|PI|PSV|QL|QS|RD|SC|TIC|TI|TIT|TT|ZI)\b",
    re.IGNORECASE,
)
STANDARD_DETAIL_LABEL_RE = re.compile(r"\bSTANDARD\s+(?:CHILLER|PUMP|AIR\s+HANDLER|AHU|FCU)\b", re.IGNORECASE)
MECHANICAL_SHEET_RE = re.compile(r"\b" + PROJECT_CODE_PATTERN + r"\s*-\s*MECHANICAL\b|\b" + PROJECT_CODE_PATTERN + r"-ME-\d{3,}\b", re.IGNORECASE)
MECHANICAL_SCHEDULE_TITLE_RE = re.compile(r"\b[A-Z0-9][A-Z0-9 /&().,+-]{3,}\s+SCHEDULE\b", re.IGNORECASE)
MECHANICAL_SCHEDULE_KEYWORDS_RE = re.compile(
    r"\b(?:PUMP|FAN|UNIT|HEATER|FILTER|FEEDER|COMPRESSOR|DRYER|TANK|SEPARATOR|HEAT\s+EXCHANGER|LOUVER|CURTAIN|SKID|SCRUBBER|CHILLER|BOILER)\b",
    re.IGNORECASE,
)
NON_HIERARCHY_MECHANICAL_ROLE_RE = re.compile(
    r"\b(?:PLAN|PLANS|PRESSURIZATION|CLASSIFICATION|ZONING|DETAILS?|AIRFLOW\s+DIAGRAM|SECTION|ELEVATION)\b",
    re.IGNORECASE,
)

PidNodeKind = Literal["equipment", "instrument", "device", "line_tag", "continuation", "section"]
PidEdgeKind = Literal[
    "attached_to_line",
    "instrument_on_line",
    "device_on_line",
    "equipment_on_section",
    "equipment_component",
    "continuation_on_line",
    "continues_to",
    "represents_instance",
    "control_panel_for",
    "control_point_on_panel",
    "instrument_on_equipment",
]


@dataclass(frozen=True)
class PidGraphNode:
    id: str
    kind: PidNodeKind
    tag: str
    system: str
    sourceFileId: str
    sourcePageId: str
    page: int
    bounds: BoundsDict
    sourceEvidenceIds: list[str]
    confidence: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PidGraphEdge:
    id: str
    kind: PidEdgeKind
    sourceId: str
    targetId: str
    label: str
    lineTag: str
    system: str
    sourceEvidenceIds: list[str]
    confidence: float
    status: Literal["confirmed", "inferred", "needs_review"]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PidRelationshipGraph:
    projectId: str
    nodes: list[PidGraphNode]
    edges: list[PidGraphEdge]
    metrics: dict[str, Any]
    qa: dict[str, Any]

    def to_visual_qa(self) -> dict[str, Any]:
        return {
            "metrics": dict(self.metrics),
            "qa": dict(self.qa),
            "nodes": [asdict(node) for node in self.nodes],
            "edges": [asdict(edge) for edge in self.edges],
        }

    def edge_for_match(self, match_id: str) -> PidGraphEdge | None:
        for edge in self.edges:
            if edge.kind == "continues_to" and edge.metadata.get("matchId") == match_id:
                return edge
        return None


def build_pid_relationship_graph(
    project_id: str,
    pages: list[PageEvidence],
    candidates: list[ContinuationCandidate],
    matches: list[ContinuationMatch],
    source_paths: dict[str, str],
    system_color_map: SystemColorMap,
) -> PidRelationshipGraph:
    nodes: list[PidGraphNode] = []
    node_by_key: dict[tuple[str, int, str, str], PidGraphNode] = {}
    page_roles = {(page.sourceFileId, page.page): _mechanical_page_role(page) for page in pages}
    for page in sorted(pages, key=lambda item: (item.sourceFileId, item.page, item.id)):
        if page_roles.get((page.sourceFileId, page.page)) in {"equipment_schedule", "mechanical_schedule", "non_hierarchy"}:
            continue
        for span_index, span in enumerate(page.textSpans):
            for kind, regex in (("line_tag", LINE_TAG_RE), ("equipment", EQUIPMENT_TAG_RE), ("instrument", INSTRUMENT_TAG_RE), ("device", DEVICE_TAG_RE)):
                for match_index, match in enumerate(regex.finditer(span.text or "")):
                    tag = match.group(0).upper()
                    key = (page.sourceFileId, page.page, kind, tag)
                    if key in node_by_key:
                        continue
                    bounds = _match_bounds(span, match_index)
                    metadata = {"sourceText": span.text, "sourcePath": source_paths.get(page.sourceFileId)}
                    if kind == "instrument" and _is_qualified_instrument_reference(tag):
                        metadata["source"] = "qualified_instrument_reference"
                        metadata["suppressLineAttachment"] = True
                    node = PidGraphNode(
                        id=_node_id(kind, page.id, tag),
                        kind=kind,  # type: ignore[arg-type]
                        tag=tag,
                        system=_system_for_tag(tag, system_color_map),
                        sourceFileId=page.sourceFileId,
                        sourcePageId=page.id,
                        page=page.page,
                        bounds=bounds,
                        sourceEvidenceIds=[f"{page.id}:span:{span_index}"],
                        confidence=0.9,
                        metadata=metadata,
                    )
                    node_by_key[key] = node
                    nodes.append(node)
        split_nodes = _split_tag_nodes_for_page(page, node_by_key, source_paths, system_color_map)
        nodes.extend(split_nodes)

    candidate_nodes: dict[str, PidGraphNode] = {}
    for candidate in candidates:
        tag = _continuation_node_tag(candidate)
        node = PidGraphNode(
            id=_node_id("continuation", f"{candidate.sourceFileId}_p{candidate.page}", f"{candidate.id}_{tag}"),
            kind="continuation",
            tag=tag,
            system=_system_for_tag(candidate.system or tag, system_color_map),
            sourceFileId=candidate.sourceFileId,
            sourcePageId=f"{candidate.sourceFileId}_p{candidate.page}",
            page=candidate.page,
            bounds=dict(candidate.bounds),
            sourceEvidenceIds=[candidate.id],
            confidence=candidate.confidence,
            metadata={
                "candidateId": candidate.id,
                "sheetRef": candidate.sheetRef,
                "direction": candidate.direction,
                "edge": candidate.edge,
                "evidenceText": candidate.evidenceText,
                **candidate.metadata,
            },
        )
        candidate_nodes[candidate.id] = node
        nodes.append(node)

    standard_detail_nodes, standard_detail_edges = _standard_detail_control_hierarchy(
        pages,
        nodes,
        source_paths,
        system_color_map,
    )
    nodes.extend(standard_detail_nodes)
    schedule_nodes, schedule_edges = _mechanical_schedule_tree(pages, source_paths, system_color_map, page_roles, nodes)
    nodes.extend(schedule_nodes)

    edges: list[PidGraphEdge] = [*standard_detail_edges, *schedule_edges]
    line_nodes_by_source_tag = {
        (node.sourceFileId, node.page, node.tag): node
        for node in nodes
        if node.kind == "line_tag"
    }
    edges.extend(_attachment_edges(nodes, pages))
    edges.extend(_equipment_component_edges(nodes))
    for candidate in candidates:
        line_node = line_nodes_by_source_tag.get((candidate.sourceFileId, candidate.page, (candidate.lineTag or "").upper()))
        continuation_node = candidate_nodes.get(candidate.id)
        if line_node is None or continuation_node is None:
            continue
        edges.append(
            PidGraphEdge(
                id=_edge_id("continuation_on_line", continuation_node.id, line_node.id),
                kind="continuation_on_line",
                sourceId=continuation_node.id,
                targetId=line_node.id,
                label=line_node.tag,
                lineTag=line_node.tag,
                system=line_node.system,
                sourceEvidenceIds=[candidate.id, *line_node.sourceEvidenceIds],
                confidence=min(candidate.confidence, 0.9),
                status="confirmed" if candidate.lineTag else "needs_review",
                metadata={"candidateId": candidate.id, **candidate.metadata},
            )
        )

    candidate_by_id = {candidate.id: candidate for candidate in candidates}
    for match in matches:
        if match.status == "rejected":
            continue
        source = candidate_by_id.get(match.sourceCandidateId)
        target = candidate_by_id.get(match.targetCandidateId)
        if source is None or target is None:
            continue
        source_line = line_nodes_by_source_tag.get((source.sourceFileId, source.page, (source.lineTag or target.lineTag or "").upper()))
        target_line = line_nodes_by_source_tag.get((target.sourceFileId, target.page, (target.lineTag or source.lineTag or "").upper()))
        if source_line is None or target_line is None:
            continue
        line_tag = source_line.tag or target_line.tag
        edges.append(
            PidGraphEdge(
                id=_edge_id("continues_to", match.id, source_line.id, target_line.id),
                kind="continues_to",
                sourceId=source_line.id,
                targetId=target_line.id,
                label=line_tag,
                lineTag=line_tag,
                system=_system_for_tag(source.system or target.system or line_tag, system_color_map),
                sourceEvidenceIds=[source.id, target.id],
                confidence=match.score / 100.0,
                status="confirmed" if match.status == "confirmed" else "needs_review",
                metadata={
                    "matchId": match.id,
                    "sourceCandidateId": source.id,
                    "targetCandidateId": target.id,
                    "sourceContinuationNodeId": candidate_nodes[source.id].id,
                    "targetContinuationNodeId": candidate_nodes[target.id].id,
                    "reasons": list(match.reasons),
                },
            )
        )

    return PidRelationshipGraph(
        projectId=project_id,
        nodes=nodes,
        edges=edges,
        metrics=_graph_metrics(nodes, edges, pages, page_roles),
        qa=_graph_qa(nodes, edges),
    )


def _continuation_node_tag(candidate: ContinuationCandidate) -> str:
    external_label = str(candidate.metadata.get("externalFlowLabel") or "").strip()
    if external_label:
        role = str(candidate.metadata.get("externalFlowRole") or "").strip().lower()
        role_label = "Source" if role == "source" else "Destination" if role == "destination" else "Flow"
        return f"External {role_label}: {external_label}"
    return (candidate.lineTag or candidate.label or candidate.id).upper()


def _mechanical_schedule_tree(
    pages: list[PageEvidence],
    source_paths: dict[str, str],
    system_color_map: SystemColorMap,
    page_roles: dict[tuple[str, int], str],
    existing_nodes: list[PidGraphNode] | None = None,
) -> tuple[list[PidGraphNode], list[PidGraphEdge]]:
    nodes: list[PidGraphNode] = []
    edges: list[PidGraphEdge] = []
    node_by_key: dict[tuple[str, int, str, str], PidGraphNode] = {}
    existing_equipment = _equipment_match_index(existing_nodes or [])

    for page in sorted(pages, key=lambda item: (item.sourceFileId, item.page, item.id)):
        role = page_roles.get((page.sourceFileId, page.page), "unknown")
        if role not in {"equipment_schedule", "mechanical_schedule"}:
            continue
        for block_index, block in enumerate(_mechanical_schedule_blocks(page)):
            tag_entries = block["tagEntries"]
            if not tag_entries:
                continue
            title = str(block["title"])
            title_spans = block.get("titleSpans") if isinstance(block.get("titleSpans"), list) else []
            tag_spans = [entry["span"] for entry in tag_entries if isinstance(entry.get("span"), TextSpan)]
            bounds = _union_text_bounds([*title_spans, *tag_spans])
            section = PidGraphNode(
                id=_node_id("section", page.id, f"mechanical_schedule_{block_index}_{title}"),
                kind="section",
                tag=title,
                system=_schedule_system_for(title, title, system_color_map),
                sourceFileId=page.sourceFileId,
                sourcePageId=page.id,
                page=page.page,
                bounds=bounds,
                sourceEvidenceIds=[f"{page.id}:mechanical-schedule:{block_index}"],
                confidence=0.9,
                metadata={
                    "source": "mechanical_schedule",
                    "sourcePath": source_paths.get(page.sourceFileId),
                    "scheduleTitle": title,
                    "equipmentDescription": _schedule_equipment_description(title),
                    "pageRole": role,
                },
            )
            nodes.append(section)

            for entry_index, entry in enumerate(tag_entries):
                tag = str(entry["tag"]).upper()
                span = entry["span"]
                span_index = int(entry["spanIndex"])
                row_text = _schedule_row_text(block["spans"], span, span_index)
                evidence_id = f"{page.id}:span:{span_index}"
                matched_node, match_strategy = _existing_equipment_for_schedule_tag(tag, page, existing_equipment)
                if matched_node is not None:
                    node = matched_node
                else:
                    match_strategy = "schedule_only"
                    node = _ensure_mechanical_schedule_node(
                        nodes,
                        node_by_key,
                        page,
                        source_paths,
                        system_color_map,
                        tag=tag,
                        bounds=entry["bounds"] if isinstance(entry.get("bounds"), dict) else span_bounds(span),
                        evidence_id=evidence_id,
                        confidence=0.9,
                        metadata={
                            "source": "mechanical_schedule_row",
                            "scheduleTitle": title,
                            "scheduleDescription": _schedule_equipment_description(title),
                            "equipmentDescription": _schedule_equipment_description(title),
                            "rowText": row_text,
                            "pageRole": role,
                        },
                    )
                edges.append(
                    PidGraphEdge(
                        id=_edge_id("equipment_on_section", node.id, section.id, str(entry_index)),
                        kind="equipment_on_section",
                        sourceId=node.id,
                        targetId=section.id,
                        label=section.tag,
                        lineTag="",
                        system=node.system if node.system != "DEFAULT" else section.system,
                        sourceEvidenceIds=_unique_strings([evidence_id, *node.sourceEvidenceIds, *section.sourceEvidenceIds]),
                        confidence=0.95 if match_strategy != "schedule_only" else 0.9,
                        status="confirmed",
                        metadata={
                            "source": "mechanical_schedule",
                            "scheduleTitle": title,
                            "scheduleDescription": _schedule_equipment_description(title),
                            "scheduleTag": tag,
                            "rowText": row_text,
                            "pageRole": role,
                            "matchStrategy": match_strategy,
                        },
                    )
                )
    return nodes, edges


def _equipment_match_index(nodes: list[PidGraphNode]) -> dict[str, list[PidGraphNode]]:
    index: dict[str, list[PidGraphNode]] = {}
    for node in nodes:
        if node.kind != "equipment":
            continue
        if str(node.metadata.get("source") or "").startswith("mechanical_schedule"):
            continue
        for key in _schedule_tag_match_keys(node.tag):
            index.setdefault(key, []).append(node)
    return index


def _existing_equipment_for_schedule_tag(
    tag: str,
    page: PageEvidence,
    index: dict[str, list[PidGraphNode]],
) -> tuple[PidGraphNode | None, str]:
    exact_key = _canonical_schedule_match_tag(tag)
    exact_candidates = _unique_nodes(index.get(exact_key, []))
    exact = _single_best_equipment_match(exact_candidates, page)
    if exact is not None:
        return exact, "exact_tag"

    normalized_candidates = _unique_nodes(
        [candidate for key in _schedule_tag_match_keys(tag) if key != exact_key for candidate in index.get(key, [])]
    )
    normalized = _single_best_equipment_match(normalized_candidates, page)
    if normalized is not None:
        return normalized, "normalized_tag"
    return None, ""


def _single_best_equipment_match(candidates: list[PidGraphNode], page: PageEvidence) -> PidGraphNode | None:
    same_source = [candidate for candidate in candidates if candidate.sourceFileId == page.sourceFileId]
    if len(same_source) == 1:
        return same_source[0]
    if not same_source and len(candidates) == 1:
        return candidates[0]
    return None


def _schedule_tag_match_keys(tag: str) -> list[str]:
    exact = _canonical_schedule_match_tag(tag)
    keys = [exact]
    normalized = exact.replace("_", "-")
    compact = re.sub(r"[^A-Z0-9]+", "", exact)
    for key in (normalized, compact):
        if key and key not in keys:
            keys.append(key)
    return keys


def _canonical_schedule_match_tag(tag: str) -> str:
    return re.sub(r"\s+", " ", (tag or "").replace("\u200b", "").upper()).strip()


def _unique_nodes(nodes: list[PidGraphNode]) -> list[PidGraphNode]:
    seen: set[str] = set()
    unique: list[PidGraphNode] = []
    for node in nodes:
        if node.id in seen:
            continue
        seen.add(node.id)
        unique.append(node)
    return unique


def _ensure_mechanical_schedule_node(
    nodes: list[PidGraphNode],
    node_by_key: dict[tuple[str, int, str, str], PidGraphNode],
    page: PageEvidence,
    source_paths: dict[str, str],
    system_color_map: SystemColorMap,
    *,
    tag: str,
    bounds: BoundsDict,
    evidence_id: str,
    confidence: float,
    metadata: dict[str, Any],
) -> PidGraphNode:
    key = (page.sourceFileId, page.page, "equipment", tag)
    existing = node_by_key.get(key)
    if existing is not None:
        return existing
    node = PidGraphNode(
        id=_node_id("equipment", page.id, f"mechanical_schedule_{tag}"),
        kind="equipment",
        tag=tag,
        system=_schedule_system_for(tag, str(metadata.get("scheduleTitle") or ""), system_color_map),
        sourceFileId=page.sourceFileId,
        sourcePageId=page.id,
        page=page.page,
        bounds=bounds,
        sourceEvidenceIds=[evidence_id],
        confidence=confidence,
        metadata={
            "sourcePath": source_paths.get(page.sourceFileId),
            **metadata,
        },
    )
    node_by_key[key] = node
    nodes.append(node)
    return node


def _mechanical_schedule_blocks(page: PageEvidence) -> list[dict[str, Any]]:
    spans = list(enumerate(page.textSpans))
    title_indices = [
        index
        for index, span in spans
        if _is_mechanical_schedule_title(span.text)
    ]
    if not title_indices and _mechanical_page_role(page) in {"equipment_schedule", "mechanical_schedule"}:
        title_indices = [0]

    blocks: list[dict[str, Any]] = []
    for title_order, title_index in enumerate(title_indices):
        next_title_index = title_indices[title_order + 1] if title_order + 1 < len(title_indices) else len(page.textSpans)
        block_spans = spans[title_index:next_title_index]
        title_span = page.textSpans[title_index]
        title = _schedule_title_text(title_span.text)
        if not _is_mechanical_schedule_title(title) and _generic_equipment_schedule_text(title):
            title = "MECHANICAL EQUIPMENT SCHEDULE"
        tag_header_position = _tag_header_position(block_spans)
        if tag_header_position is None:
            continue
        tag_column = _tag_column_bounds(block_spans, tag_header_position)
        tag_entries: list[dict[str, Any]] = []
        seen_tags: set[str] = set()
        for span_index, span in block_spans:
            if span_index <= tag_header_position:
                continue
            for match_index, match in enumerate(EQUIPMENT_TAG_RE.finditer(span.text or "")):
                bounds = _match_bounds(span, match_index)
                if not _bounds_in_schedule_tag_column(bounds, tag_column):
                    continue
                tag = match.group(0).upper()
                if tag in seen_tags:
                    continue
                seen_tags.add(tag)
                tag_entries.append({"spanIndex": span_index, "span": span, "tag": tag, "matchIndex": match_index, "bounds": bounds})
        if tag_entries:
            blocks.append({"title": title, "titleSpans": [title_span], "spans": block_spans, "tagEntries": tag_entries})
    return blocks


def _mechanical_page_role(page: PageEvidence) -> str:
    text = _page_text(page)
    upper = text.upper()
    if _is_mechanical_schedule_page_text(upper):
        return "equipment_schedule" if "EQUIPMENT SCHEDULE" in upper else "mechanical_schedule"
    if re.search(r"\b(P\s*&\s*ID|PIPING\s+AND\s+INSTRUMENTATION)\b", upper):
        return "pid"
    if MECHANICAL_SHEET_RE.search(upper) and NON_HIERARCHY_MECHANICAL_ROLE_RE.search(upper):
        return "non_hierarchy"
    return "unknown"


def _is_mechanical_schedule_page_text(upper_text: str) -> bool:
    if "TAG" not in upper_text:
        return False
    if "EQUIPMENT SCHEDULE" in upper_text:
        return True
    return bool(MECHANICAL_SCHEDULE_TITLE_RE.search(upper_text) and MECHANICAL_SCHEDULE_KEYWORDS_RE.search(upper_text))


def _is_mechanical_schedule_title(text: str) -> bool:
    title = _schedule_title_text(text)
    if not title or _generic_equipment_schedule_text(title):
        return False
    if MECHANICAL_SCHEDULE_TITLE_RE.fullmatch(title) and MECHANICAL_SCHEDULE_KEYWORDS_RE.search(title):
        return True
    if len(title) <= 90 and MECHANICAL_SCHEDULE_KEYWORDS_RE.search(title) and re.search(r"\b(?:UNIT SYSTEMS|AIR-RETURN)\b", title):
        return True
    return False


def _generic_equipment_schedule_text(text: str) -> bool:
    return _schedule_title_text(text) in {"EQUIPMENT SCHEDULE", "EQUIPMENT SCHEDULES", "MECHANICAL EQUIPMENT SCHEDULE", "MECHANICAL EQUIPMENT SCHEDULES"}


def _tag_header_position(spans: list[tuple[int, TextSpan]]) -> int | None:
    for span_index, span in spans:
        text = _schedule_title_text(span.text)
        if text == "TAG" or re.search(r"\bTAG\b", text):
            return span_index
    return None


def _tag_column_bounds(spans: list[tuple[int, TextSpan]], tag_header_position: int) -> BoundsDict:
    tag_header = next((span for span_index, span in spans if span_index == tag_header_position), None)
    if tag_header is None:
        return {"x": 0.0, "y": 0.0, "width": 260.0, "height": 99999.0}
    header_bounds = span_bounds(tag_header)
    header_center_y = _center(header_bounds)["y"]
    if abs(float(tag_header.rotation or 0.0)) >= 45.0:
        return {"x": header_bounds["x"] - 32.0, "y": header_center_y - 96.0, "width": 99999.0, "height": 192.0}
    next_header_x: float | None = None
    for span_index, span in spans:
        if span_index == tag_header_position:
            continue
        if span_index <= tag_header_position or span_index - tag_header_position > 20:
            continue
        bounds = span_bounds(span)
        if abs(_center(bounds)["y"] - header_center_y) > max(10.0, tag_header.height * 0.9):
            continue
        if bounds["x"] <= header_bounds["x"] + 6.0:
            continue
        if next_header_x is None or bounds["x"] < next_header_x:
            next_header_x = bounds["x"]
    right = (next_header_x - 4.0) if next_header_x is not None else header_bounds["x"] + 240.0
    return {"x": header_bounds["x"] - 16.0, "y": 0.0, "width": max(64.0, right - (header_bounds["x"] - 16.0)), "height": 99999.0}


def _bounds_in_schedule_tag_column(bounds: BoundsDict, column: BoundsDict) -> bool:
    center_x = _center(bounds)["x"]
    left = column["x"]
    right = column["x"] + column["width"]
    return center_x >= left and center_x <= right and bounds["x"] <= right + 8.0


def _schedule_row_text(spans: list[tuple[int, TextSpan]], tag_span: TextSpan, tag_span_index: int) -> str:
    row_y = _center(span_bounds(tag_span))["y"]
    same_row = [
        span
        for span_index, span in spans
        if span_index >= tag_span_index
        and abs(_center(span_bounds(span))["y"] - row_y) <= max(8.0, tag_span.height)
    ]
    if len(same_row) > 1:
        return _schedule_title_text(" ".join(span.text for span in sorted(same_row, key=lambda item: item.x)))
    following: list[str] = []
    for span_index, span in spans:
        if span_index < tag_span_index:
            continue
        if span_index > tag_span_index and EQUIPMENT_TAG_RE.search(span.text or ""):
            break
        following.append(span.text)
        if len(following) >= 6:
            break
    return _schedule_title_text(" ".join(following))


def _schedule_system_for(tag: str, title: str, system_color_map: SystemColorMap) -> str:
    tag_system = _system_for_tag(tag, system_color_map)
    if tag_system != "DEFAULT":
        return tag_system
    title_system = _system_for_tag(title, system_color_map)
    return title_system if title_system != "DEFAULT" else tag_system


def _schedule_equipment_description(title: str) -> str:
    clean = re.sub(r"\bSCHEDULES?\b", "", _schedule_title_text(title)).strip()
    return clean.title()


def _schedule_title_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u200b", "").strip().upper()).strip(" :-")


def _page_text(page: PageEvidence) -> str:
    return " ".join(_schedule_title_text(span.text) for span in page.textSpans if span.text)


def _unique_strings(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _split_tag_nodes_for_page(
    page: PageEvidence,
    node_by_key: dict[tuple[str, int, str, str], PidGraphNode],
    source_paths: dict[str, str],
    system_color_map: SystemColorMap,
) -> list[PidGraphNode]:
    if any(STANDARD_DETAIL_LABEL_RE.search(span.text or "") for span in page.textSpans):
        return []

    nodes: list[PidGraphNode] = []
    for span_index, span in enumerate(page.textSpans):
        code = _normalized_split_tag_text(span.text)
        kind = _split_tag_kind_for_code(code)
        if kind is None:
            continue
        suffix_index, suffix_span, suffix = _nearby_split_tag_suffix(page.textSpans, span_index)
        if suffix_span is None:
            continue
        tag = f"{code} {suffix}"
        if _split_tag_already_seen(node_by_key, page, kind, tag):
            continue
        node = PidGraphNode(
            id=_node_id(kind, page.id, tag),
            kind=kind,
            tag=tag,
            system=_system_for_tag(tag, system_color_map),
            sourceFileId=page.sourceFileId,
            sourcePageId=page.id,
            page=page.page,
            bounds=_union_text_bounds([span, suffix_span]),
            sourceEvidenceIds=[f"{page.id}:span:{span_index}", f"{page.id}:span:{suffix_index}"],
            confidence=0.86,
            metadata={
                "source": "split_text_tag",
                "sourceText": f"{span.text} {suffix_span.text}",
                "sourcePath": source_paths.get(page.sourceFileId),
                "splitCode": code,
                "splitSuffix": suffix,
            },
        )
        node_by_key[(page.sourceFileId, page.page, kind, tag)] = node
        nodes.append(node)
    return nodes


def _split_tag_kind_for_code(code: str) -> PidNodeKind | None:
    if SPLIT_DEVICE_CODE_RE.fullmatch(code):
        return "device"
    if SPLIT_INSTRUMENT_CODE_RE.fullmatch(code):
        return "instrument"
    return None


def _nearby_split_tag_suffix(spans: list[TextSpan], code_index: int) -> tuple[int, TextSpan | None, str]:
    code_span = spans[code_index]
    for offset in range(1, 5):
        suffix_index = code_index + offset
        if suffix_index >= len(spans):
            break
        suffix_span = spans[suffix_index]
        suffix = _normalized_split_tag_text(suffix_span.text)
        if _is_split_tag_skip_text(suffix):
            continue
        if not SPLIT_TAG_SUFFIX_RE.fullmatch(suffix):
            continue
        if suffix.startswith(f"{PROJECT_CODE}-") or '"' in suffix:
            continue
        if not _split_tag_spans_are_near(code_span, suffix_span):
            continue
        return suffix_index, suffix_span, suffix
    return -1, None, ""


def _normalized_split_tag_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").replace("\u200b", "").strip().upper())


def _is_split_tag_skip_text(text: str) -> bool:
    return not text or bool(SPLIT_TAG_SKIP_RE.fullmatch(text))


def _split_tag_spans_are_near(code_span: TextSpan, suffix_span: TextSpan) -> bool:
    code_center = _center(span_bounds(code_span))
    suffix_center = _center(span_bounds(suffix_span))
    dx = abs(code_center["x"] - suffix_center["x"])
    dy = abs(code_center["y"] - suffix_center["y"])
    return (dx <= 120.0 and dy <= 110.0) or (dy <= 32.0 and dx <= 180.0)


def _split_tag_already_seen(
    node_by_key: dict[tuple[str, int, str, str], PidGraphNode],
    page: PageEvidence,
    kind: str,
    tag: str,
) -> bool:
    variants = {tag, tag.replace(" ", "-")}
    return any((page.sourceFileId, page.page, kind, variant) in node_by_key for variant in variants)


def _attachment_edges(nodes: list[PidGraphNode], pages: list[PageEvidence]) -> list[PidGraphEdge]:
    line_nodes = [node for node in nodes if node.kind == "line_tag"]
    topology = _vector_topology_by_page(pages, line_nodes)
    attached_edges: list[PidGraphEdge] = []
    for node in nodes:
        if node.kind not in {"equipment", "instrument", "device"}:
            continue
        if node.metadata.get("suppressLineAttachment"):
            continue
        nearest, metadata, confidence = _line_node_from_vector_topology(node, topology)
        if nearest is None:
            nearest = _nearest_line_node(node, line_nodes)
            metadata = {"source": "nearest_line_tag"}
            confidence = 0.74
        if nearest is None:
            nearest = _contextual_system_line_node(node, line_nodes)
            metadata = {"source": "system_context_fallback"}
            confidence = 0.62
        if nearest is None:
            continue
        if node.kind == "instrument":
            kind = "instrument_on_line"
        elif node.kind == "device":
            kind = "device_on_line"
        else:
            kind = "attached_to_line"
        attached_edges.append(
            PidGraphEdge(
                id=_edge_id(kind, node.id, nearest.id),
                kind=kind,
                sourceId=node.id,
                targetId=nearest.id,
                label=nearest.tag,
                lineTag=nearest.tag,
                system=nearest.system,
                sourceEvidenceIds=[*node.sourceEvidenceIds, *nearest.sourceEvidenceIds],
                confidence=confidence,
                status="needs_review" if metadata.get("source") == "system_context_fallback" else "inferred",
                metadata=metadata,
            )
        )
    return attached_edges


def _equipment_component_edges(nodes: list[PidGraphNode]) -> list[PidGraphEdge]:
    equipment_nodes = [node for node in nodes if node.kind == "equipment"]
    attachable_nodes = [node for node in nodes if node.kind == "equipment"]
    edges: list[PidGraphEdge] = []
    for child in attachable_nodes:
        parent = _component_parent(child, equipment_nodes)
        if parent is None:
            continue
        edges.append(
            PidGraphEdge(
                id=_edge_id("equipment_component", child.id, parent.id),
                kind="equipment_component",
                sourceId=child.id,
                targetId=parent.id,
                label=parent.tag,
                lineTag="",
                system=parent.system if parent.system != "DEFAULT" else child.system,
                sourceEvidenceIds=[*child.sourceEvidenceIds, *parent.sourceEvidenceIds],
                confidence=0.82,
                status="inferred",
                metadata={"source": "tag_component_prefix"},
            )
        )
    return edges


def _standard_detail_control_hierarchy(
    pages: list[PageEvidence],
    existing_nodes: list[PidGraphNode],
    source_paths: dict[str, str],
    system_color_map: SystemColorMap,
) -> tuple[list[PidGraphNode], list[PidGraphEdge]]:
    nodes: list[PidGraphNode] = []
    edges: list[PidGraphEdge] = []
    existing_by_page: dict[tuple[str, int], list[PidGraphNode]] = {}
    for node in existing_nodes:
        existing_by_page.setdefault((node.sourceFileId, node.page), []).append(node)

    seen_node_ids = {node.id for node in existing_nodes}
    for page in pages:
        page_nodes = existing_by_page.get((page.sourceFileId, page.page), [])
        represented = _standard_detail_represented_nodes(page, page_nodes)
        if len(represented) < 2:
            continue
        root = _standard_detail_root_node(page, represented, source_paths, system_color_map)
        if root.id not in seen_node_ids:
            nodes.append(root)
            seen_node_ids.add(root.id)
        for instance in represented:
            edges.append(
                PidGraphEdge(
                    id=_edge_id("represents_instance", instance.id, root.id),
                    kind="represents_instance",
                    sourceId=instance.id,
                    targetId=root.id,
                    label=root.tag,
                    lineTag="",
                    system=root.system,
                    sourceEvidenceIds=[*instance.sourceEvidenceIds, *root.sourceEvidenceIds],
                    confidence=0.94,
                    status="confirmed",
                    metadata={"source": "standard_detail_equipment_index"},
                )
            )

        panels = [node for node in page_nodes if node.kind == "equipment" and _is_control_panel_tag(node.tag)]
        for panel in panels:
            panel_owners = _represented_equipment_for_panel(page, panel, represented) or [root]
            for owner in panel_owners:
                edges.append(
                    PidGraphEdge(
                        id=_edge_id("control_panel_for", panel.id, owner.id),
                        kind="control_panel_for",
                        sourceId=panel.id,
                        targetId=owner.id,
                        label=owner.tag,
                        lineTag="",
                        system=panel.system if panel.system != "DEFAULT" else owner.system,
                        sourceEvidenceIds=[*panel.sourceEvidenceIds, *owner.sourceEvidenceIds],
                        confidence=0.92 if owner.kind == "equipment" else 0.78,
                        status="confirmed" if owner.kind == "equipment" else "needs_review",
                        metadata={
                            "source": "standard_detail_panel_zone",
                            "standardDetailRootId": root.id,
                            "representedInstanceTags": [node.tag for node in panel_owners if node.kind == "equipment"],
                        },
                    )
                )
            control_nodes, control_edges = _control_point_nodes_for_panel(page, panel, source_paths, system_color_map, seen_node_ids)
            nodes.extend(control_nodes)
            edges.extend(control_edges)
        field_nodes, field_edges = _field_instrument_nodes_for_standard_detail(page, represented, panels, source_paths, system_color_map, seen_node_ids)
        nodes.extend(field_nodes)
        edges.extend(field_edges)
    return nodes, edges


def _standard_detail_represented_nodes(page: PageEvidence, page_nodes: list[PidGraphNode]) -> list[PidGraphNode]:
    if not any(STANDARD_DETAIL_LABEL_RE.search(span.text or "") for span in page.textSpans):
        return []
    represented: list[PidGraphNode] = []
    for node in page_nodes:
        if node.kind != "equipment" or "XX" in node.tag or _is_control_panel_tag(node.tag):
            continue
        bounds = node.bounds
        if bounds["y"] <= page.height * 0.25 and bounds["x"] >= page.width * 0.55:
            represented.append(node)
    return sorted(represented, key=lambda item: (item.bounds["y"], item.bounds["x"], item.tag))


def _standard_detail_root_node(
    page: PageEvidence,
    represented: list[PidGraphNode],
    source_paths: dict[str, str],
    system_color_map: SystemColorMap,
) -> PidGraphNode:
    labels = [span for span in page.textSpans if STANDARD_DETAIL_LABEL_RE.search(span.text or "")]
    bounds = _union_text_bounds(labels) if labels else _union_node_bounds(represented)
    title = _standard_detail_title(labels) or "Standard Detail P&ID"
    system = _dominant_system([node.system for node in represented], system_color_map)
    return PidGraphNode(
        id=_node_id("section", page.id, title),
        kind="section",
        tag=title,
        system=system,
        sourceFileId=page.sourceFileId,
        sourcePageId=page.id,
        page=page.page,
        bounds=bounds,
        sourceEvidenceIds=[page.id],
        confidence=0.94,
        metadata={
            "source": "standard_detail_equipment_index",
            "sourcePath": source_paths.get(page.sourceFileId),
            "representedInstanceTags": [node.tag for node in represented],
        },
    )


def _standard_detail_title(labels: list[TextSpan]) -> str:
    if not labels:
        return ""
    text = max((span.text.strip() for span in labels), key=len).upper()
    return f"{text} P&ID" if "P&ID" not in text else text


def _dominant_system(systems: list[str], system_color_map: SystemColorMap) -> str:
    counts: dict[str, int] = {}
    for system in systems:
        canonical = canonical_system(system)
        if canonical and canonical != "DEFAULT":
            counts[canonical] = counts.get(canonical, 0) + 1
    if counts:
        return max(counts.items(), key=lambda item: item[1])[0]
    if "CHW" in system_color_map.entries:
        return "CHW"
    return "DEFAULT"


def _is_control_panel_tag(tag: str) -> bool:
    upper = tag.upper()
    return "_CP" in upper or "-CP" in upper or "_VFD" in upper or "-VFD" in upper or "PANEL" in upper


def _represented_equipment_for_panel(page: PageEvidence, panel: PidGraphNode, represented: list[PidGraphNode]) -> list[PidGraphNode]:
    explicit_owners: dict[str, tuple[int, PidGraphNode]] = {}
    for _, _, tag in _control_point_tag_spans(page, panel):
        owner = _represented_equipment_for_control_tag(tag, represented)
        if owner is None:
            continue
        count = explicit_owners.get(owner.id, (0, owner))[0] + 1
        explicit_owners[owner.id] = (count, owner)
    if explicit_owners:
        max_count = max(count for count, _ in explicit_owners.values())
        return sorted((owner for count, owner in explicit_owners.values() if count == max_count), key=lambda node: (node.bounds["y"], node.bounds["x"], node.tag))

    family = _panel_equipment_family(panel.tag)
    if family:
        matches = [node for node in represented if re.search(rf"(?:^|-){re.escape(family)}-\d{{2}}\b", node.tag.upper())]
        if matches:
            return sorted(matches, key=lambda node: (node.bounds["y"], node.bounds["x"], node.tag))
    return []


def _panel_equipment_family(tag: str) -> str:
    upper = tag.upper()
    for family in ("CH", "P", "HX"):
        if re.search(rf"(?:^|-){family}-(?:XX|\d{{2}})\b", upper):
            return family
    if "_VFD" in upper or "-VFD" in upper:
        return "P"
    if "_CP" in upper or "-CP" in upper:
        return "CH"
    return ""


def _control_point_nodes_for_panel(
    page: PageEvidence,
    panel: PidGraphNode,
    source_paths: dict[str, str],
    system_color_map: SystemColorMap,
    seen_node_ids: set[str],
) -> tuple[list[PidGraphNode], list[PidGraphEdge]]:
    nodes: list[PidGraphNode] = []
    edges: list[PidGraphEdge] = []
    control_spans = list(_control_point_tag_spans(page, panel))
    for span_index, span, tag in control_spans:
        function_span = _nearest_control_function_span(page.textSpans, span)
        function = function_span.text.strip().upper() if function_span else ""
        descriptor = _nearest_control_descriptor(page.textSpans, function_span, span)
        node_tag = " ".join(part for part in (function, descriptor, tag) if part)
        node_id = _node_id("instrument", page.id, f"{node_tag}_{round(span.x)}_{round(span.y)}")
        if node_id in seen_node_ids:
            continue
        confidence = 0.88 if function else 0.74
        node = PidGraphNode(
            id=node_id,
            kind="instrument",
            tag=node_tag,
            system=_system_for_tag(tag, system_color_map),
            sourceFileId=page.sourceFileId,
            sourcePageId=page.id,
            page=page.page,
            bounds=span_bounds(span),
            sourceEvidenceIds=[f"{page.id}:span:{span_index}"],
            confidence=confidence,
            metadata={
                "source": "standard_detail_panel_control_point",
                "sourcePath": source_paths.get(page.sourceFileId),
                "controlFunction": function,
                "controlDescriptor": descriptor,
                "controlTag": tag,
                "panelTag": panel.tag,
            },
        )
        nodes.append(node)
        seen_node_ids.add(node_id)
        evidence_ids = [*node.sourceEvidenceIds, *panel.sourceEvidenceIds]
        if function_span is not None:
            evidence_ids.append(f"{page.id}:span:{page.textSpans.index(function_span)}")
        edges.append(
            PidGraphEdge(
                id=_edge_id("control_point_on_panel", node.id, panel.id),
                kind="control_point_on_panel",
                sourceId=node.id,
                targetId=panel.id,
                label=panel.tag,
                lineTag="",
                system=node.system if node.system != "DEFAULT" else panel.system,
                sourceEvidenceIds=evidence_ids,
                confidence=confidence,
                status="confirmed" if function else "needs_review",
                metadata={"source": "standard_detail_panel_zone", "controlFunction": function, "controlDescriptor": descriptor},
            )
        )
    return nodes, edges


def _field_instrument_nodes_for_standard_detail(
    page: PageEvidence,
    represented: list[PidGraphNode],
    panels: list[PidGraphNode],
    source_paths: dict[str, str],
    system_color_map: SystemColorMap,
    seen_node_ids: set[str],
) -> tuple[list[PidGraphNode], list[PidGraphEdge]]:
    nodes: list[PidGraphNode] = []
    edges: list[PidGraphEdge] = []
    panel_windows = [_panel_child_window(panel) for panel in panels]
    for span_index, span in enumerate(page.textSpans):
        if any(_point_in_bounds({"x": span.x, "y": span.y}, window) for window in panel_windows):
            continue
        text = span.text.strip().upper()
        for match in CONTROL_POINT_TAG_RE.finditer(text):
            tag = match.group(0).upper()
            function_span = _nearest_control_function_span(page.textSpans, span)
            if function_span is None:
                continue
            function = function_span.text.strip().upper()
            owner = _represented_equipment_for_control_tag(tag, represented)
            if owner is None:
                continue
            node_tag = f"{function} {tag}"
            node_id = _node_id("instrument", page.id, f"{node_tag}_{round(span.x)}_{round(span.y)}")
            if node_id in seen_node_ids:
                continue
            confidence = 0.9 if _instrument_code_matches_owner(tag, owner.tag) else 0.78
            node = PidGraphNode(
                id=node_id,
                kind="instrument",
                tag=node_tag,
                system=_system_for_tag(tag, system_color_map),
                sourceFileId=page.sourceFileId,
                sourcePageId=page.id,
                page=page.page,
                bounds=span_bounds(span),
                sourceEvidenceIds=[f"{page.id}:span:{span_index}"],
                confidence=confidence,
                metadata={
                    "source": "standard_detail_field_instrument",
                    "sourcePath": source_paths.get(page.sourceFileId),
                    "controlFunction": function,
                    "controlTag": tag,
                    "representedEquipmentTag": owner.tag,
                },
            )
            nodes.append(node)
            seen_node_ids.add(node_id)
            edges.append(
                PidGraphEdge(
                    id=_edge_id("instrument_on_equipment", node.id, owner.id),
                    kind="instrument_on_equipment",
                    sourceId=node.id,
                    targetId=owner.id,
                    label=owner.tag,
                    lineTag="",
                    system=owner.system if owner.system != "DEFAULT" else node.system,
                    sourceEvidenceIds=[*node.sourceEvidenceIds, *owner.sourceEvidenceIds, f"{page.id}:span:{page.textSpans.index(function_span)}"],
                    confidence=confidence,
                    status="confirmed" if confidence >= 0.86 else "inferred",
                    metadata={"source": "standard_detail_tag_suffix", "controlFunction": function},
                )
            )
    return nodes, edges


def _represented_equipment_for_control_tag(tag: str, represented: list[PidGraphNode]) -> PidGraphNode | None:
    tag_upper = tag.upper()
    chiller_match = re.search(r"(?:^|-|_)CH-?0*(\d{1,2})\b", tag_upper)
    if chiller_match:
        number = int(chiller_match.group(1))
        return _represented_equipment_by_family_number(represented, "CH", number)
    pump_match = re.search(r"(?:^|-|_)P-?0*(\d{1,2})\b", tag_upper)
    if pump_match:
        number = int(pump_match.group(1))
        return _represented_equipment_by_family_number(represented, "P", number)
    return None


def _represented_equipment_by_family_number(represented: list[PidGraphNode], family: str, number: int) -> PidGraphNode | None:
    expected = f"{family}-{number:02d}"
    for node in represented:
        if expected in node.tag.upper():
            return node
    expected_loose = f"{family}{number:02d}"
    for node in represented:
        if expected_loose in node.tag.upper().replace("-", ""):
            return node
    return None


def _instrument_code_matches_owner(tag: str, owner_tag: str) -> bool:
    return _represented_equipment_for_control_tag(tag, [owner_tag_node(owner_tag)]) is not None


def owner_tag_node(tag: str) -> PidGraphNode:
    return PidGraphNode(
        id="owner_tag_check",
        kind="equipment",
        tag=tag,
        system="DEFAULT",
        sourceFileId="",
        sourcePageId="",
        page=0,
        bounds={"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0},
        sourceEvidenceIds=[],
        confidence=0.0,
        metadata={},
    )


def _control_point_tag_spans(page: PageEvidence, panel: PidGraphNode) -> Iterable[tuple[int, TextSpan, str]]:
    window = _panel_child_window(panel)
    for span_index, span in enumerate(page.textSpans):
        text = span.text.strip().upper()
        if not _point_in_bounds({"x": span.x, "y": span.y}, window):
            continue
        for match in CONTROL_POINT_TAG_RE.finditer(text):
            yield span_index, span, match.group(0).upper()


def _panel_child_window(panel: PidGraphNode) -> BoundsDict:
    bounds = panel.bounds
    upper = panel.tag.upper()
    if "_VFD" in upper or "-VFD" in upper:
        return {
            "x": bounds["x"] + 20.0,
            "y": bounds["y"] - 40.0,
            "width": 240.0,
            "height": 380.0,
        }
    if "_CP" in upper or "-CP" in upper:
        return {
            "x": bounds["x"] - 180.0,
            "y": bounds["y"] - 30.0,
            "width": 280.0,
            "height": 740.0,
        }
    return _expand_bounds(bounds, 220.0, 420.0)


def _nearest_control_function_span(spans: list[TextSpan], tag_span: TextSpan) -> TextSpan | None:
    candidates: list[tuple[float, TextSpan]] = []
    for span in spans:
        text = span.text.strip().upper()
        if not CONTROL_FUNCTION_RE.fullmatch(text):
            continue
        dx = abs(span.x - tag_span.x)
        dy = span.y - tag_span.y
        if dx <= 48.0 and -14.0 <= dy <= 48.0:
            candidates.append((dx + abs(dy) * 0.6, span))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def _nearest_control_descriptor(spans: list[TextSpan], function_span: TextSpan | None, tag_span: TextSpan) -> str:
    if function_span is None:
        return ""
    candidates: list[tuple[float, TextSpan]] = []
    for span in spans:
        text = span.text.strip().upper()
        if not _is_control_descriptor_text(text):
            continue
        dx = abs(span.x - function_span.x)
        dy = abs(span.y - function_span.y)
        if dx <= 34.0 and dy <= 46.0:
            tag_distance = abs(span.x - tag_span.x) + abs(span.y - tag_span.y) * 0.4
            candidates.append((dx + dy * 0.7 + tag_distance * 0.05, span))
    if not candidates:
        return ""
    return min(candidates, key=lambda item: item[0])[1].text.strip().upper()


def _is_control_descriptor_text(text: str) -> bool:
    if not text or len(text) > 28:
        return False
    if CONTROL_FUNCTION_RE.fullmatch(text) or CONTROL_POINT_TAG_RE.search(text):
        return False
    if re.fullmatch(r"\(?\d+\)?", text):
        return False
    return bool(re.fullmatch(r"[A-Z][A-Z0-9 /_-]*", text))


def _point_in_bounds(point: Point, bounds: BoundsDict) -> bool:
    return (
        bounds["x"] <= point["x"] <= bounds["x"] + bounds["width"]
        and bounds["y"] <= point["y"] <= bounds["y"] + bounds["height"]
    )


def _union_text_bounds(spans: list[TextSpan]) -> BoundsDict:
    return _union_bounds([span_bounds(span) for span in spans])


def _union_node_bounds(nodes: list[PidGraphNode]) -> BoundsDict:
    return _union_bounds([node.bounds for node in nodes])


def _union_bounds(bounds_list: list[BoundsDict]) -> BoundsDict:
    if not bounds_list:
        return {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}
    x0 = min(bounds["x"] for bounds in bounds_list)
    y0 = min(bounds["y"] for bounds in bounds_list)
    x1 = max(bounds["x"] + bounds["width"] for bounds in bounds_list)
    y1 = max(bounds["y"] + bounds["height"] for bounds in bounds_list)
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def _component_parent(child: PidGraphNode, equipment_nodes: list[PidGraphNode]) -> PidGraphNode | None:
    child_core = _equipment_core(child.tag)
    if not child_core:
        return None
    candidates: list[tuple[int, PidGraphNode]] = []
    for parent in equipment_nodes:
        if parent.id == child.id or parent.sourceFileId != child.sourceFileId or parent.page != child.page:
            continue
        parent_core = _equipment_core(parent.tag)
        if not parent_core or parent_core == child_core:
            continue
        if child_core.startswith(f"{parent_core}-") or child_core.startswith(f"{parent_core}_"):
            candidates.append((len(parent_core), parent))
            continue
        if _shared_equipment_identity(parent_core, child_core):
            candidates.append((len(parent_core), parent))
    if not candidates:
        return None
    return max(candidates, key=lambda item: item[0])[1]


def _equipment_core(tag: str) -> str:
    core = tag.upper()
    core = re.sub(r"^" + PROJECT_CODE_PATTERN + r"-", "", core)
    core = re.sub(r"^R-", "", core)
    core = re.sub(r"^[A-Z0-9]+-", "", core) if core.startswith(("FR-", "NR-")) else core
    return core.strip("-_")


def _shared_equipment_identity(parent_core: str, child_core: str) -> bool:
    parent_parts = [part for part in re.split(r"[-_]+", parent_core) if part]
    if len(parent_parts) < 2:
        return False
    identity = "-".join(parent_parts[-2:])
    return identity in child_core


def _vector_topology_by_page(
    pages: list[PageEvidence],
    line_nodes: list[PidGraphNode],
) -> dict[tuple[str, int], dict[str, Any]]:
    topology: dict[tuple[str, int], dict[str, Any]] = {}
    line_nodes_by_page: dict[tuple[str, int], list[PidGraphNode]] = {}
    for line in line_nodes:
        line_nodes_by_page.setdefault((line.sourceFileId, line.page), []).append(line)

    for page in pages:
        usable_vectors = [vector for vector in page.vectorSegments if _is_topology_vector(vector, page)]
        if not usable_vectors or len(usable_vectors) > MAX_TOPOLOGY_VECTOR_COMPONENT_SCAN:
            continue
        component_by_vector = _component_by_vector_id(usable_vectors)
        line_nodes_by_component: dict[int, list[PidGraphNode]] = {}
        for line in line_nodes_by_page.get((page.sourceFileId, page.page), []):
            nearest_vector, distance = _nearest_vector_to_bounds(line.bounds, usable_vectors)
            if nearest_vector is None or distance > 96.0:
                continue
            component = component_by_vector.get(nearest_vector.id)
            if component is None:
                continue
            line_nodes_by_component.setdefault(component, []).append(line)
        topology[(page.sourceFileId, page.page)] = {
            "vectors": usable_vectors,
            "componentByVectorId": component_by_vector,
            "lineNodesByComponent": line_nodes_by_component,
        }
    return topology


def _line_node_from_vector_topology(
    node: PidGraphNode,
    topology: dict[tuple[str, int], dict[str, Any]],
) -> tuple[PidGraphNode | None, dict[str, Any], float]:
    page_topology = topology.get((node.sourceFileId, node.page))
    if not page_topology:
        return None, {}, 0.0
    vectors: list[VectorSegment] = page_topology["vectors"]
    nearest_vector, distance = _nearest_vector_to_bounds(node.bounds, vectors)
    if nearest_vector is None or distance > 170.0:
        return None, {}, 0.0
    component = page_topology["componentByVectorId"].get(nearest_vector.id)
    if component is None:
        return None, {}, 0.0
    line_nodes = page_topology["lineNodesByComponent"].get(component, [])
    if not line_nodes:
        return None, {}, 0.0
    if node.system != "DEFAULT":
        same_system_line_nodes = [line for line in line_nodes if line.system == node.system]
        if same_system_line_nodes:
            line_nodes = same_system_line_nodes
    node_center = _center(node.bounds)
    best = min(line_nodes, key=lambda line: _manhattan(_center(line.bounds), node_center))
    return (
        best,
        {
            "source": "connected_vector_geometry",
            "nearestVectorId": nearest_vector.id,
            "vectorComponent": component,
            "vectorDistance": round(distance, 2),
        },
        0.84,
    )


def _is_topology_vector(vector: VectorSegment, page: PageEvidence) -> bool:
    if len(vector.points) < 2:
        return False
    bounds = vector.bounds
    if bounds["width"] <= 1.0 and bounds["height"] <= 1.0:
        return False
    if bounds["width"] < 18.0 and bounds["height"] < 18.0:
        return False
    near_page_edge = bounds["x"] <= 4.0 or bounds["y"] <= 4.0
    long_border = bounds["width"] > page.width * 0.55 or bounds["height"] > page.height * 0.55
    return not (near_page_edge and long_border)


def _component_by_vector_id(vectors: list[VectorSegment]) -> dict[str, int]:
    parent = {vector.id: vector.id for vector in vectors}

    def find(vector_id: str) -> str:
        while parent[vector_id] != vector_id:
            parent[vector_id] = parent[parent[vector_id]]
            vector_id = parent[vector_id]
        return vector_id

    def union(left: str, right: str) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for index, vector in enumerate(vectors):
        for other in vectors[index + 1 :]:
            if _vectors_touch(vector, other):
                union(vector.id, other.id)

    component_index_by_root: dict[str, int] = {}
    component_by_vector: dict[str, int] = {}
    for vector in vectors:
        root = find(vector.id)
        component_index_by_root.setdefault(root, len(component_index_by_root))
        component_by_vector[vector.id] = component_index_by_root[root]
    return component_by_vector


def _vectors_touch(left: VectorSegment, right: VectorSegment) -> bool:
    for left_point in _vector_touch_points(left):
        for right_point in _vector_touch_points(right):
            if _distance(left_point, right_point) <= 14.0:
                return True
    return _bounds_overlap(_expand_bounds(left.bounds, 7.0, 7.0), right.bounds, padding=0.0) and (
        _point_to_vector_distance(_center(left.bounds), right) <= 14.0
        or _point_to_vector_distance(_center(right.bounds), left) <= 14.0
    )


def _vector_touch_points(vector: VectorSegment) -> list[Point]:
    if len(vector.points) <= 2:
        return list(vector.points)
    return [vector.points[0], *vector.points[1:-1], vector.points[-1]]


def _nearest_vector_to_bounds(bounds: BoundsDict, vectors: list[VectorSegment]) -> tuple[VectorSegment | None, float]:
    center = _center(bounds)
    nearest: tuple[float, VectorSegment] | None = None
    for vector in vectors:
        distance = _point_to_vector_distance(center, vector)
        if nearest is None or distance < nearest[0]:
            nearest = (distance, vector)
    if nearest is None:
        return None, 0.0
    return nearest[1], nearest[0]


def _point_to_vector_distance(point: Point, vector: VectorSegment) -> float:
    distances: list[float] = []
    for index in range(len(vector.points) - 1):
        distances.append(_point_to_segment_distance(point, vector.points[index], vector.points[index + 1]))
    return min(distances) if distances else _distance(point, _center(vector.bounds))


def _point_to_segment_distance(point: Point, start: Point, end: Point) -> float:
    dx = end["x"] - start["x"]
    dy = end["y"] - start["y"]
    if dx == 0 and dy == 0:
        return _distance(point, start)
    t = ((point["x"] - start["x"]) * dx + (point["y"] - start["y"]) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    projected = {"x": start["x"] + t * dx, "y": start["y"] + t * dy}
    return _distance(point, projected)


def _distance(left: Point, right: Point) -> float:
    return ((left["x"] - right["x"]) ** 2 + (left["y"] - right["y"]) ** 2) ** 0.5


def _manhattan(left: Point, right: Point) -> float:
    return abs(left["x"] - right["x"]) + abs(left["y"] - right["y"])


def _expand_bounds(bounds: BoundsDict, dx: float, dy: float) -> BoundsDict:
    return {
        "x": bounds["x"] - dx,
        "y": bounds["y"] - dy,
        "width": bounds["width"] + dx * 2.0,
        "height": bounds["height"] + dy * 2.0,
    }


def _bounds_overlap(a: BoundsDict, b: BoundsDict, padding: float = 0.0) -> bool:
    return not (
        a["x"] + a["width"] + padding < b["x"]
        or b["x"] + b["width"] + padding < a["x"]
        or a["y"] + a["height"] + padding < b["y"]
        or b["y"] + b["height"] + padding < a["y"]
    )


def _nearest_line_node(node: PidGraphNode, line_nodes: list[PidGraphNode]) -> PidGraphNode | None:
    same_page_lines = [
        line
        for line in line_nodes
        if line.sourceFileId == node.sourceFileId and line.page == node.page
    ]
    if node.system != "DEFAULT":
        same_system_lines = [line for line in same_page_lines if line.system == node.system]
        if same_system_lines:
            same_page_lines = same_system_lines
    nearest: tuple[float, PidGraphNode] | None = None
    center = _center(node.bounds)
    for line in same_page_lines:
        line_center = _center(line.bounds)
        distance = abs(line_center["y"] - center["y"]) + abs(line_center["x"] - center["x"]) * 0.2
        if nearest is None or distance < nearest[0]:
            nearest = (distance, line)
    if nearest and nearest[0] <= 220.0:
        return nearest[1]
    return None


def _contextual_system_line_node(node: PidGraphNode, line_nodes: list[PidGraphNode]) -> PidGraphNode | None:
    same_page_lines = [
        line
        for line in line_nodes
        if line.sourceFileId == node.sourceFileId and line.page == node.page and line.system != "DEFAULT"
    ]
    using_same_system_context = False
    same_system_line_count = 0
    if node.system != "DEFAULT":
        same_system = [line for line in same_page_lines if line.system == node.system]
        if same_system:
            same_page_lines = same_system
            using_same_system_context = True
            same_system_line_count = len(same_system)
    nearest: tuple[float, PidGraphNode] | None = None
    center = _center(node.bounds)
    for line in same_page_lines:
        line_center = _center(line.bounds)
        distance = abs(line_center["y"] - center["y"]) + abs(line_center["x"] - center["x"]) * 0.18
        if nearest is None or distance < nearest[0]:
            nearest = (distance, line)
    max_distance = 1800.0 if same_system_line_count == 1 else 980.0 if using_same_system_context else 520.0
    if nearest and nearest[0] <= max_distance:
        return nearest[1]
    return None


def _graph_metrics(
    nodes: list[PidGraphNode],
    edges: list[PidGraphEdge],
    pages: list[PageEvidence],
    page_roles: dict[tuple[str, int], str],
) -> dict[str, Any]:
    page_classifications: dict[str, int] = {}
    for page in pages:
        role = page_roles.get((page.sourceFileId, page.page), "unknown")
        page_classifications[role] = page_classifications.get(role, 0) + 1
    return {
        "nodes": len(nodes),
        "edges": len(edges),
        "equipmentNodes": sum(node.kind == "equipment" for node in nodes),
        "instrumentNodes": sum(node.kind == "instrument" for node in nodes),
        "deviceNodes": sum(node.kind == "device" for node in nodes),
        "lineTagNodes": sum(node.kind == "line_tag" for node in nodes),
        "continuationNodes": sum(node.kind == "continuation" for node in nodes),
        "attachmentEdges": sum(edge.kind in {"attached_to_line", "instrument_on_line", "device_on_line"} for edge in edges),
        "deviceEdges": sum(edge.kind == "device_on_line" for edge in edges),
        "scheduleEdges": sum(edge.kind == "equipment_on_section" and edge.metadata.get("source") == "mechanical_schedule" for edge in edges),
        "scheduleMatchedNodes": sum(
            edge.kind == "equipment_on_section"
            and edge.metadata.get("source") == "mechanical_schedule"
            and edge.metadata.get("matchStrategy") in {"exact_tag", "normalized_tag"}
            for edge in edges
        ),
        "mechanicalScheduleNodes": sum(node.kind == "equipment" and node.metadata.get("source") == "mechanical_schedule_row" for node in nodes),
        "componentEdges": sum(edge.kind == "equipment_component" for edge in edges),
        "continuationEdges": sum(edge.kind == "continues_to" for edge in edges),
        "pageClassifications": page_classifications,
    }


def _graph_qa(nodes: list[PidGraphNode], edges: list[PidGraphEdge]) -> dict[str, list[str]]:
    edge_source_ids = {edge.sourceId for edge in edges}
    edge_target_ids = {edge.targetId for edge in edges}
    attached_ids = edge_source_ids | edge_target_ids
    matched_candidate_ids = {
        str(edge.metadata.get("sourceCandidateId"))
        for edge in edges
        if edge.kind == "continues_to"
    } | {
        str(edge.metadata.get("targetCandidateId"))
        for edge in edges
        if edge.kind == "continues_to"
    }
    return {
        "isolatedEquipmentNodes": [node.id for node in nodes if node.kind == "equipment" and node.id not in attached_ids],
        "isolatedInstrumentNodes": [node.id for node in nodes if node.kind == "instrument" and node.id not in attached_ids],
        "isolatedDeviceNodes": [node.id for node in nodes if node.kind == "device" and node.id not in attached_ids],
        "lineTagsWithoutGeometryRelationships": [node.id for node in nodes if node.kind == "line_tag" and node.id not in attached_ids],
        "unresolvedContinuationNodes": [
            node.id
            for node in nodes
            if node.kind == "continuation"
            and node.metadata.get("sheetRef")
            and node.metadata.get("candidateId") not in matched_candidate_ids
        ],
    }


def _match_bounds(span: TextSpan, match_index: int) -> BoundsDict:
    return {
        "x": span.x + min(match_index * 18.0, max(span.width - 12.0, 0.0)),
        "y": span.y,
        "width": max(48.0, min(span.width, 160.0)),
        "height": max(span.height, 14.0),
    }


def span_bounds(span: TextSpan) -> BoundsDict:
    return {"x": span.x, "y": span.y, "width": span.width, "height": span.height}


def _system_for_tag(tag: str, system_color_map: SystemColorMap) -> str:
    inferred = canonical_system(system_for_text(tag, system_color_map)) or canonical_system(tag)
    if inferred in system_color_map.entries:
        return inferred
    for token in re.split(r"[-_\\s]+", tag or ""):
        token_system = canonical_system(token)
        if token_system in system_color_map.entries:
            return token_system
    return inferred or "DEFAULT"


def _is_qualified_instrument_reference(tag: str) -> bool:
    return bool(re.fullmatch(PROJECT_CODE_PATTERN + r"-[A-Z0-9]+(?:-[A-Z0-9]+){1,4}-(?:PDIT|PDT|PIT|FIT|TIT|LIT|AIT|PT|FT|TT|LT|PI|FI|TI|FE|TE|AT)-\d+[A-Z0-9]*", tag or "", re.IGNORECASE))


def _center(bounds: BoundsDict) -> dict[str, float]:
    return {"x": bounds["x"] + bounds["width"] / 2.0, "y": bounds["y"] + bounds["height"] / 2.0}


def _node_id(kind: str, page_id: str, tag: str) -> str:
    return f"pidnode_{kind}_{_id_slug(page_id)}_{_slug(tag)}"


def _edge_id(kind: str, *parts: str) -> str:
    return f"pidedge_{kind}_{'_'.join(_slug(part) for part in parts if part)}"


def _slug(value: str) -> str:
    text = Path(str(value)).stem.lower()
    text = re.sub(r'["]+', "", text)
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "item"


def _id_slug(value: str) -> str:
    text = Path(str(value)).stem.lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text).strip("_")
    return text or "item"
