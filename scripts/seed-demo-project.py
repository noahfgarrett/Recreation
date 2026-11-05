#!/usr/bin/env python3
"""Seed a realistic demo project directly into the running backend's SQLite database.

Usage:
    python3 scripts/seed-demo-project.py

Creates a "Demo — Cooling Water Unit" project with a realistic P&ID layout:
  - Pumps, vessels, heat exchangers
  - Instruments (PT, TT, FT, LT)
  - Valves (XV, CV, HV)
  - Electrical (motor, VFD, breaker, MCC, transformer, switchgear)
  - Junction boxes, panels, off-page connectors
  - Pipe edges, instrument signal edges, cable edges
"""

from __future__ import annotations

import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from recreation_extractor.models import (
    Bounds,
    DrawingGraph,
    GraphEdge,
    GraphNode,
    Layout,
    Port,
    Project,
    ReviewItem,
    SourceEvidence,
)
from recreation_extractor.storage import ProjectStore

DATA_DIR = Path(__file__).resolve().parent.parent / "backend" / ".recreation-data"
PROJECT_ID = "project_demo_cw_unit"
PROJECT_NAME = "Demo — Cooling Water Unit"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sha(text: str) -> str:
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def _node_id(tag: str) -> str:
    return f"node_{_sha(tag)}"


def _edge_id(src: str, tgt: str, label: str) -> str:
    return f"edge_{_sha(f'{src}:{tgt}:{label}')}"


def _ports(node_id: str) -> list[Port]:
    return [
        Port(id=f"{node_id}:left", label="in", side="left"),
        Port(id=f"{node_id}:right", label="out", side="right"),
        Port(id=f"{node_id}:top", label="signal", side="top"),
        Port(id=f"{node_id}:bottom", label="drain", side="bottom"),
    ]


def _evidence(tag: str, page: int = 1, confidence: float = 0.92) -> list[SourceEvidence]:
    ev_id = f"ev_demo_{_sha(tag)}"
    return [
        SourceEvidence(
            id=ev_id,
            sourceFileId="src_demo_file",
            page=page,
            bounds=Bounds(page=page, x=100, y=100, width=40, height=14),
            text=tag,
            confidence=confidence,
        )
    ]


KIND_MAP: dict[str, tuple[str, str]] = {
    # Process equipment
    "P": ("equipment", "pump"),
    "PU": ("equipment", "pump"),
    "TK": ("equipment", "vessel"),
    "VSL": ("equipment", "vessel"),
    "HX": ("equipment", "heat-exchanger"),
    "E": ("equipment", "vessel"),
    # Instruments
    "PT": ("instrument", "instrument-bubble"),
    "TT": ("instrument", "instrument-bubble"),
    "FT": ("instrument", "instrument-bubble"),
    "LT": ("instrument", "instrument-bubble"),
    "FIT": ("instrument", "instrument-bubble"),
    "TIC": ("instrument", "instrument-bubble"),
    "PIC": ("instrument", "instrument-bubble"),
    "LIC": ("instrument", "instrument-bubble"),
    # Valves
    "XV": ("valve", "valve"),
    "CV": ("valve", "valve"),
    "HV": ("valve", "valve"),
    "V": ("valve", "valve"),
    # Electrical
    "MOT": ("equipment", "motor"),
    "MTR": ("equipment", "motor"),
    "BKR": ("equipment", "breaker"),
    "CB": ("equipment", "breaker"),
    "VFD": ("equipment", "vfd"),
    "ASD": ("equipment", "vfd"),
    "XFMR": ("equipment", "transformer"),
    "TR": ("equipment", "transformer"),
    "MCC": ("equipment", "mcc"),
    "SWG": ("equipment", "switchgear"),
    "SWGR": ("equipment", "switchgear"),
    # Infrastructure
    "JB": ("junction_box", "junction-box"),
    "PNL": ("panel", "panel"),
}


def _make_node(tag: str, x: float, y: float, page: int = 1, confidence: float = 0.92) -> GraphNode:
    nid = _node_id(tag)
    prefix = tag.split("-")[0]
    kind, symbol = KIND_MAP.get(prefix, ("unknown", "unknown"))
    return GraphNode(
        id=nid,
        kind=kind,
        tag=tag,
        symbolId=symbol,
        ports=_ports(nid),
        sourceEvidence=_evidence(tag, page, confidence),
        confidence=confidence,
        locked=False,
        layout=Layout(x=x, y=y),
    )


def _make_opc(tag: str, x: float, y: float, page: int = 1) -> GraphNode:
    nid = _node_id(tag)
    return GraphNode(
        id=nid,
        kind="off_page_connector",
        tag=tag,
        symbolId="off-page-connector",
        ports=_ports(nid),
        sourceEvidence=_evidence(tag, page, 0.88),
        confidence=0.88,
        locked=False,
        layout=Layout(x=x, y=y),
    )


def _make_edge(
    src_tag: str,
    src_side: str,
    tgt_tag: str,
    tgt_side: str,
    label: str,
    kind: str = "pipe",
    line_id: str | None = None,
    confidence: float = 0.85,
    status: str = "confirmed",
) -> GraphEdge:
    src_port = f"{_node_id(src_tag)}:{src_side}"
    tgt_port = f"{_node_id(tgt_tag)}:{tgt_side}"
    eid = _edge_id(src_tag, tgt_tag, label)
    return GraphEdge(
        id=eid,
        kind=kind,
        sourcePort=src_port,
        targetPort=tgt_port,
        label=label,
        lineOrCableId=line_id,
        waypoints=[],
        continuationRefs=[],
        sourceEvidence=_evidence(label, confidence=confidence),
        confidence=confidence,
        status=status,
    )


# ---------------------------------------------------------------------------
# Build the demo graph
# ---------------------------------------------------------------------------

def build_demo_graph() -> tuple[list[GraphNode], list[GraphEdge], list[ReviewItem]]:
    nodes: list[GraphNode] = []
    edges: list[GraphEdge] = []

    # -----------------------------------------------------------------------
    # Page 1: Cooling Water Supply — Tank → Pumps → HX → Return
    # -----------------------------------------------------------------------
    # Cooling water tank
    nodes.append(_make_node("TK-101", 0, 200, page=1))
    # Level transmitter on tank
    nodes.append(_make_node("LT-101", 0, 50, page=1))
    # Level controller
    nodes.append(_make_node("LIC-101", 200, 50, page=1))

    # Pump A (duty)
    nodes.append(_make_node("P-101A", 400, 120, page=1))
    # Pump B (standby)
    nodes.append(_make_node("P-101B", 400, 280, page=1))

    # Pressure transmitter after pumps
    nodes.append(_make_node("PT-102", 600, 50, page=1))
    # Flow transmitter
    nodes.append(_make_node("FT-103", 800, 50, page=1))

    # Isolation valve before HX
    nodes.append(_make_node("XV-101", 700, 200, page=1))

    # Heat exchanger
    nodes.append(_make_node("HX-101", 1000, 200, page=1))

    # Temperature transmitters on HX
    nodes.append(_make_node("TT-101", 900, 50, page=1))   # inlet
    nodes.append(_make_node("TT-102", 1100, 50, page=1))  # outlet

    # Temperature controller
    nodes.append(_make_node("TIC-101", 1100, 350, page=1))

    # Control valve on CW return
    nodes.append(_make_node("CV-101", 1300, 200, page=1))

    # Return to cooling tower (OPC)
    nodes.append(_make_node("HV-102", 1500, 200, page=1))
    nodes.append(_make_opc("OPC-CW-RET", 1700, 200, page=1))

    # Supply OPC
    nodes.append(_make_opc("OPC-CW-SUP", -200, 200, page=1))

    # Piping: supply path
    edges.append(_make_edge("OPC-CW-SUP", "right", "TK-101", "left", "CW Supply", line_id="6-CW-1001"))
    edges.append(_make_edge("TK-101", "right", "P-101A", "left", "6-CW-1002", line_id="6-CW-1002"))
    edges.append(_make_edge("TK-101", "right", "P-101B", "left", "6-CW-1002B", line_id="6-CW-1002"))
    edges.append(_make_edge("P-101A", "right", "XV-101", "left", "4-CW-1003", line_id="4-CW-1003"))
    edges.append(_make_edge("P-101B", "right", "XV-101", "left", "4-CW-1003B", line_id="4-CW-1003"))
    edges.append(_make_edge("XV-101", "right", "HX-101", "left", "4-CW-1004", line_id="4-CW-1004"))
    edges.append(_make_edge("HX-101", "right", "CV-101", "left", "4-CW-1005", line_id="4-CW-1005"))
    edges.append(_make_edge("CV-101", "right", "HV-102", "left", "4-CW-1006", line_id="4-CW-1006"))
    edges.append(_make_edge("HV-102", "right", "OPC-CW-RET", "left", "CW Return", line_id="4-CW-1006"))

    # Instrument signals
    edges.append(_make_edge("LT-101", "bottom", "TK-101", "top", "LT-101 sig", kind="instrument_signal"))
    edges.append(_make_edge("LT-101", "right", "LIC-101", "left", "LIC loop", kind="instrument_signal"))
    edges.append(_make_edge("PT-102", "bottom", "P-101A", "top", "PT-102 sig", kind="instrument_signal"))
    edges.append(_make_edge("FT-103", "bottom", "XV-101", "top", "FT-103 sig", kind="instrument_signal"))
    edges.append(_make_edge("TT-101", "bottom", "HX-101", "top", "TT-101 sig", kind="instrument_signal"))
    edges.append(_make_edge("TT-102", "right", "TIC-101", "top", "TIC loop", kind="instrument_signal"))
    edges.append(_make_edge("TIC-101", "left", "CV-101", "bottom", "CV ctrl", kind="instrument_signal"))

    # -----------------------------------------------------------------------
    # Page 2: Process Side — Vessel + second HX loop
    # -----------------------------------------------------------------------
    nodes.append(_make_node("VSL-201", 0, 600, page=2))
    nodes.append(_make_node("PT-201", 0, 450, page=2))
    nodes.append(_make_node("PIC-201", 200, 450, page=2))
    nodes.append(_make_node("HX-201", 600, 600, page=2))
    nodes.append(_make_node("TT-201", 600, 450, page=2))
    nodes.append(_make_node("P-201", 400, 600, page=2))
    nodes.append(_make_node("FT-201", 400, 450, page=2))
    nodes.append(_make_node("FIT-201", 800, 450, page=2))
    nodes.append(_make_node("CV-201", 800, 600, page=2))
    nodes.append(_make_node("XV-201", 1000, 600, page=2))
    nodes.append(_make_node("E-201", 1200, 600, page=2))
    nodes.append(_make_node("TT-202", 1200, 450, page=2))
    nodes.append(_make_opc("OPC-PROC-IN", -200, 600, page=2))
    nodes.append(_make_opc("OPC-PROC-OUT", 1400, 600, page=2))

    edges.append(_make_edge("OPC-PROC-IN", "right", "VSL-201", "left", "Proc Feed", line_id="8-PR-2001"))
    edges.append(_make_edge("VSL-201", "right", "P-201", "left", "8-PR-2002", line_id="8-PR-2002"))
    edges.append(_make_edge("P-201", "right", "HX-201", "left", "6-PR-2003", line_id="6-PR-2003"))
    edges.append(_make_edge("HX-201", "right", "CV-201", "left", "6-PR-2004", line_id="6-PR-2004"))
    edges.append(_make_edge("CV-201", "right", "XV-201", "left", "6-PR-2005", line_id="6-PR-2005"))
    edges.append(_make_edge("XV-201", "right", "E-201", "left", "4-PR-2006", line_id="4-PR-2006"))
    edges.append(_make_edge("E-201", "right", "OPC-PROC-OUT", "left", "Proc Out", line_id="4-PR-2006"))

    edges.append(_make_edge("PT-201", "bottom", "VSL-201", "top", "PT-201 sig", kind="instrument_signal"))
    edges.append(_make_edge("PT-201", "right", "PIC-201", "left", "PIC-201 loop", kind="instrument_signal"))
    edges.append(_make_edge("FT-201", "bottom", "P-201", "top", "FT-201 sig", kind="instrument_signal"))
    edges.append(_make_edge("TT-201", "bottom", "HX-201", "top", "TT-201 sig", kind="instrument_signal"))
    edges.append(_make_edge("FIT-201", "bottom", "CV-201", "top", "FIT-201 sig", kind="instrument_signal"))
    edges.append(_make_edge("TT-202", "bottom", "E-201", "top", "TT-202 sig", kind="instrument_signal"))

    # -----------------------------------------------------------------------
    # Page 3: Electrical — MCC → VFDs → Motors → Pumps
    # -----------------------------------------------------------------------
    nodes.append(_make_node("SWGR-001", 0, 1000, page=3))
    nodes.append(_make_node("XFMR-001", 300, 1000, page=3))
    nodes.append(_make_node("MCC-001", 600, 1000, page=3))
    nodes.append(_make_node("BKR-101", 900, 900, page=3))
    nodes.append(_make_node("BKR-102", 900, 1100, page=3))
    nodes.append(_make_node("VFD-101", 1100, 900, page=3))
    nodes.append(_make_node("VFD-102", 1100, 1100, page=3))
    nodes.append(_make_node("MOT-101A", 1300, 900, page=3))
    nodes.append(_make_node("MOT-101B", 1300, 1100, page=3))
    nodes.append(_make_node("BKR-201", 900, 1300, page=3))
    nodes.append(_make_node("MOT-201", 1100, 1300, page=3))

    # Power path
    edges.append(_make_edge("SWGR-001", "right", "XFMR-001", "left", "HV Feed", kind="cable", line_id="PWR-001"))
    edges.append(_make_edge("XFMR-001", "right", "MCC-001", "left", "LV Bus", kind="cable", line_id="PWR-002"))
    edges.append(_make_edge("MCC-001", "right", "BKR-101", "left", "Fdr 1", kind="cable", line_id="PWR-003"))
    edges.append(_make_edge("MCC-001", "right", "BKR-102", "left", "Fdr 2", kind="cable", line_id="PWR-004"))
    edges.append(_make_edge("MCC-001", "right", "BKR-201", "left", "Fdr 3", kind="cable", line_id="PWR-005"))
    edges.append(_make_edge("BKR-101", "right", "VFD-101", "left", "VFD-101 pwr", kind="cable"))
    edges.append(_make_edge("BKR-102", "right", "VFD-102", "left", "VFD-102 pwr", kind="cable"))
    edges.append(_make_edge("VFD-101", "right", "MOT-101A", "left", "MOT-101A pwr", kind="cable"))
    edges.append(_make_edge("VFD-102", "right", "MOT-101B", "left", "MOT-101B pwr", kind="cable"))
    edges.append(_make_edge("BKR-201", "right", "MOT-201", "left", "MOT-201 pwr", kind="cable"))

    # -----------------------------------------------------------------------
    # Page 4: Marshalling — JBs + Panel
    # -----------------------------------------------------------------------
    nodes.append(_make_node("JB-001", 0, 1500, page=4))
    nodes.append(_make_node("JB-002", 300, 1500, page=4))
    nodes.append(_make_node("JB-003", 600, 1500, page=4))
    nodes.append(_make_node("PNL-001", 900, 1500, page=4))
    nodes.append(_make_node("PNL-002", 1200, 1500, page=4))
    nodes.append(_make_opc("OPC-DCS-A", 1500, 1500, page=4))

    edges.append(_make_edge("JB-001", "right", "JB-002", "left", "CBL-1001", kind="cable", line_id="CBL-1001"))
    edges.append(_make_edge("JB-002", "right", "JB-003", "left", "CBL-1002", kind="cable", line_id="CBL-1002"))
    edges.append(_make_edge("JB-003", "right", "PNL-001", "left", "CBL-1003", kind="cable", line_id="CBL-1003"))
    edges.append(_make_edge("PNL-001", "right", "PNL-002", "left", "CBL-1004", kind="cable", line_id="CBL-1004"))
    edges.append(_make_edge("PNL-002", "right", "OPC-DCS-A", "left", "To DCS", kind="cable", line_id="CBL-1005"))

    # Instrument-to-JB signal cables
    edges.append(_make_edge("LT-101", "bottom", "JB-001", "top", "LT-101 cable", kind="cable", confidence=0.72, status="needs_review"))
    edges.append(_make_edge("PT-102", "bottom", "JB-001", "top", "PT-102 cable", kind="cable", confidence=0.72, status="needs_review"))
    edges.append(_make_edge("FT-103", "bottom", "JB-002", "top", "FT-103 cable", kind="cable", confidence=0.68, status="needs_review"))
    edges.append(_make_edge("TT-101", "bottom", "JB-002", "top", "TT-101 cable", kind="cable", confidence=0.70, status="needs_review"))
    edges.append(_make_edge("TT-102", "bottom", "JB-003", "top", "TT-102 cable", kind="cable", confidence=0.70, status="needs_review"))

    # -----------------------------------------------------------------------
    # Review items
    # -----------------------------------------------------------------------
    reviews: list[ReviewItem] = []

    # Low confidence instrument-JB connections
    low_conf_pairs = [
        ("FT-103", "JB-002", 0.68),
        ("TT-101", "JB-002", 0.70),
        ("TT-102", "JB-003", 0.70),
    ]
    for src, tgt, conf in low_conf_pairs:
        eid = _edge_id(src, tgt, f"{src} cable")
        reviews.append(
            ReviewItem(
                id=f"rev_{_sha(eid)}",
                type="unconnected_item",
                candidates=[{"edgeId": eid, "source": src, "target": tgt}],
                recommendedAction="Review this inferred cable connection before locking the combined drawing.",
                evidence=_evidence(src, confidence=conf),
                resolvedBy=None,
                resolution=None,
                status="open",
            )
        )

    # Low confidence tag
    reviews.append(
        ReviewItem(
            id=f"rev_{_sha('low_e201')}",
            type="low_confidence_tag",
            candidates=[{"nodeId": _node_id("E-201"), "tag": "E-201", "confidence": 0.72}],
            recommendedAction="Verify this tag — matched with lower confidence from a split word pair.",
            evidence=_evidence("E-201", confidence=0.72),
            resolvedBy=None,
            resolution=None,
            status="open",
        )
    )

    return nodes, edges, reviews


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    store = ProjectStore(DATA_DIR)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    project = Project(id=PROJECT_ID, name=PROJECT_NAME, createdAt=now, updatedAt=now)
    store.upsert_project(project)

    nodes, edges, reviews = build_demo_graph()
    graph = DrawingGraph(projectId=PROJECT_ID, nodes=nodes, edges=edges, reviewItems=reviews)
    store.replace_graph(graph)

    print(f"Seeded project: {PROJECT_NAME}")
    print(f"  ID:      {PROJECT_ID}")
    print(f"  Nodes:   {len(nodes)}")
    print(f"  Edges:   {len(edges)}")
    print(f"  Reviews: {len(reviews)}")
    print()
    print("Node kinds:")
    kinds: dict[str, int] = {}
    for n in nodes:
        kinds[n.kind] = kinds.get(n.kind, 0) + 1
    for k, c in sorted(kinds.items(), key=lambda x: -x[1]):
        print(f"  {k}: {c}")
    print()
    print("Edge kinds:")
    ekinds: dict[str, int] = {}
    for e in edges:
        ekinds[e.kind] = ekinds.get(e.kind, 0) + 1
    for k, c in sorted(ekinds.items(), key=lambda x: -x[1]):
        print(f"  {k}: {c}")


if __name__ == "__main__":
    main()
