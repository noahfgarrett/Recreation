from __future__ import annotations

import html
import json
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape


def _stroke_for_edge_kind(kind: str) -> tuple[str, str]:
    """Return (stroke_color, dash_array) for an edge kind."""
    styles: dict[str, tuple[str, str]] = {
        "pipe": ("#334155", ""),
        "instrument_signal": ("#2563EB", "6,3"),
        "cable": ("#B45309", "6,3"),
        "continuation": ("#0F766E", ""),
    }
    return styles.get(kind, ("#334155", ""))


def _edge_path_d(
    edge: dict[str, Any],
    sx: float,
    sy: float,
    tx: float,
    ty: float,
) -> str:
    """Build an SVG path 'd' attribute, routing through waypoints when present."""
    waypoints: list[dict[str, Any]] = edge.get("waypoints") or []
    if waypoints:
        segments = [f"M {sx:.1f} {sy:.1f}"]
        for wp in waypoints:
            wx = float(wp.get("x", 0))
            wy = float(wp.get("y", 0))
            segments.append(f"L {wx:.1f} {wy:.1f}")
        segments.append(f"L {tx:.1f} {ty:.1f}")
        return " ".join(segments)
    mid = (sx + tx) / 2
    return f"M {sx:.1f} {sy:.1f} L {mid:.1f} {sy:.1f} L {mid:.1f} {ty:.1f} L {tx:.1f} {ty:.1f}"


def export_svg(graph: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    width = max([node.get("layout", {}).get("x", 0) + 280 for node in nodes] + [1200])
    height = max([node.get("layout", {}).get("y", 0) + 180 for node in nodes] + [800])
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} {height:.0f}">',
        "<defs>",
        '<marker id="arrow" markerWidth="12" markerHeight="12" refX="10" refY="6" orient="auto" markerUnits="strokeWidth"><path d="M2,2 L10,6 L2,10 z" fill="#25313f"/></marker>',
        "</defs>",
        '<rect width="100%" height="100%" fill="#f7f8fb"/>',
    ]
    node_by_id = {node["id"]: node for node in nodes}
    for edge in edges:
        source_id = edge.get("sourcePort", "").split(":")[0]
        target_id = edge.get("targetPort", "").split(":")[0]
        source = node_by_id.get(source_id)
        target = node_by_id.get(target_id)
        if not source or not target:
            continue
        sx, sy = _node_anchor(source, "right")
        tx, ty = _node_anchor(target, "left")
        d = _edge_path_d(edge, sx, sy, tx, ty)
        stroke_color, dash = _stroke_for_edge_kind(edge.get("kind", ""))
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        parts.append(f'<path d="{d}" fill="none" stroke="{stroke_color}" stroke-width="2"{dash_attr} marker-end="url(#arrow)"/>')
        label_text = edge.get("lineOrCableId") or edge.get("label") or ""
        label = escape(label_text)
        if label:
            mid_x = (sx + tx) / 2
            mid_y = ((sy + ty) / 2) - 6
            parts.append(f'<text x="{mid_x:.1f}" y="{mid_y:.1f}" font-size="12" fill="{stroke_color}">{label}</text>')

    for node in nodes:
        layout = node.get("layout", {})
        x = float(layout.get("x", 0))
        y = float(layout.get("y", 0))
        w = float(layout.get("width", 160))
        h = float(layout.get("height", 88))
        tag = escape(node.get("tag", ""))
        kind = escape(node.get("kind", "unknown"))
        fill = _fill_for_kind(kind)
        parts.append(f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" rx="6" fill="{fill}" stroke="#25313f" stroke-width="1.5"/>')
        parts.append(f'<text x="{x + 14:.1f}" y="{y + 32:.1f}" font-size="15" font-weight="700" fill="#17202b">{tag}</text>')
        parts.append(f'<text x="{x + 14:.1f}" y="{y + 54:.1f}" font-size="11" fill="#4b5b6b">{kind}</text>')
    parts.append("</svg>")
    output_path.write_text("\n".join(parts), encoding="utf-8")
    return output_path


def export_pdf(graph: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.pdfgen import canvas

        page_width, page_height = landscape(letter)
        c = canvas.Canvas(str(output_path), pagesize=landscape(letter))
        c.setTitle("Recreation Combined Drawing")

        nodes_per_page = 30
        all_nodes = graph.get("nodes", [])
        all_edges = graph.get("edges", [])

        # --- Node pages ---
        for page_start in range(0, max(len(all_nodes), 1), nodes_per_page):
            page_nodes = all_nodes[page_start : page_start + nodes_per_page]
            c.drawString(36, page_height - 36, "Recreation Combined Drawing")
            c.drawString(36, page_height - 54, f"Project: {graph.get('projectId')}")
            page_label = f"Nodes {page_start + 1}–{page_start + len(page_nodes)} of {len(all_nodes)}"
            c.drawString(36, page_height - 72, page_label)
            y = page_height - 100
            for node in page_nodes:
                c.drawString(36, y, f"{node.get('tag')}  {node.get('kind')}  confidence={node.get('confidence')}")
                y -= 18
                if y < 36:
                    break
            c.showPage()

        # --- Edge pages ---
        edges_per_page = 30
        if all_edges:
            for page_start in range(0, len(all_edges), edges_per_page):
                page_edges = all_edges[page_start : page_start + edges_per_page]
                c.drawString(36, page_height - 36, "Recreation Combined Drawing — Connections")
                edge_label = f"Edges {page_start + 1}–{page_start + len(page_edges)} of {len(all_edges)}"
                c.drawString(36, page_height - 54, edge_label)
                y = page_height - 82
                for edge in page_edges:
                    line_id = edge.get("lineOrCableId") or edge.get("label") or ""
                    kind = edge.get("kind", "")
                    src = edge.get("sourcePort", "")
                    tgt = edge.get("targetPort", "")
                    conf = edge.get("confidence", "")
                    c.drawString(36, y, f"{line_id}  [{kind}]  {src} -> {tgt}  confidence={conf}")
                    y -= 18
                    if y < 36:
                        break
                c.showPage()

        c.save()
    except Exception:
        output_path.write_bytes(_minimal_pdf_bytes(graph))
    return output_path


def export_xlsx(graph: dict[str, Any], output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill

        wb = Workbook()
        ws = wb.active
        ws.title = "Tags"
        headers = ["Tag", "Kind", "Symbol", "Confidence", "Locked", "Source Evidence"]
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="25313F")
        for node in graph.get("nodes", []):
            ws.append(
                [
                    node.get("tag"),
                    node.get("kind"),
                    node.get("symbolId"),
                    node.get("confidence"),
                    node.get("locked"),
                    ", ".join(ev.get("id", "") for ev in node.get("sourceEvidence", [])),
                ]
            )

        ws_edges = wb.create_sheet("Connections")
        ws_edges.append(["Label", "Kind", "Source Port", "Target Port", "Line/Cable ID", "Confidence", "Status"])
        for edge in graph.get("edges", []):
            ws_edges.append(
                [
                    edge.get("label"),
                    edge.get("kind"),
                    edge.get("sourcePort"),
                    edge.get("targetPort"),
                    edge.get("lineOrCableId"),
                    edge.get("confidence"),
                    edge.get("status"),
                ]
            )

        ws_review = wb.create_sheet("Review Queue")
        ws_review.append(["ID", "Type", "Status", "Recommended Action", "Candidates"])
        for item in graph.get("reviewItems", []):
            ws_review.append(
                [
                    item.get("id"),
                    item.get("type"),
                    item.get("status"),
                    item.get("recommendedAction"),
                    json.dumps(item.get("candidates", [])),
                ]
            )
        wb.save(output_path)
    except Exception:
        _write_minimal_xlsx(graph, output_path)
    return output_path


def export_line_list_xlsx(graph: dict[str, Any], output_path: Path) -> Path:
    """Export a construction line list as XLSX.

    Only edges with a ``lineOrCableId`` are included.  Rows are deduplicated
    by line ID — when the same line appears on multiple edges the from/to
    information is combined.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    node_by_id: dict[str, dict[str, Any]] = {node["id"]: node for node in graph.get("nodes", [])}

    # Collect line rows, deduplicating by lineOrCableId
    line_rows: dict[str, dict[str, Any]] = {}
    for edge in graph.get("edges", []):
        line_id = edge.get("lineOrCableId")
        if not line_id:
            continue
        parsed = edge.get("parsedLineId") or {}
        source_node_id = edge.get("sourcePort", "").split(":")[0]
        target_node_id = edge.get("targetPort", "").split(":")[0]
        source_tag = node_by_id.get(source_node_id, {}).get("tag", "")
        target_tag = node_by_id.get(target_node_id, {}).get("tag", "")

        # Gather sheet numbers from source evidence
        sheets: set[str] = set()
        for ev in edge.get("sourceEvidence", []):
            page = ev.get("page")
            if page is not None:
                sheets.add(str(page))

        if line_id in line_rows:
            existing = line_rows[line_id]
            # Combine from/to tags
            if source_tag and source_tag not in existing["from"]:
                existing["from"] += f", {source_tag}" if existing["from"] else source_tag
            if target_tag and target_tag not in existing["to"]:
                existing["to"] += f", {target_tag}" if existing["to"] else target_tag
            existing["sheets"].update(sheets)
            # Keep higher confidence
            existing["confidence"] = max(existing["confidence"], edge.get("confidence", 0))
        else:
            line_rows[line_id] = {
                "lineNumber": line_id,
                "size": parsed.get("size") or "",
                "service": parsed.get("service") or "",
                "spec": parsed.get("spec") or "",
                "from": source_tag,
                "to": target_tag,
                "sheets": sheets,
                "status": edge.get("status", ""),
                "confidence": edge.get("confidence", 0),
            }

    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill

        wb = Workbook()
        ws = wb.active
        ws.title = "Line List"
        headers = [
            "Line Number",
            "Size",
            "Service",
            "Spec / Class",
            "From",
            "To",
            "P&ID Reference",
            "Status",
            "Confidence (%)",
        ]
        ws.append(headers)
        for cell in ws[1]:
            cell.font = Font(bold=True, color="FFFFFF")
            cell.fill = PatternFill("solid", fgColor="25313F")
        for row_data in line_rows.values():
            ws.append([
                row_data["lineNumber"],
                row_data["size"],
                row_data["service"],
                row_data["spec"],
                row_data["from"],
                row_data["to"],
                ", ".join(sorted(row_data["sheets"])),
                row_data["status"],
                round(row_data["confidence"] * 100, 1),
            ])
        wb.save(output_path)
    except Exception:
        _write_minimal_line_list_xlsx(line_rows, output_path)
    return output_path


def _write_minimal_line_list_xlsx(line_rows: dict[str, dict[str, Any]], output_path: Path) -> None:
    """Minimal XLSX fallback when openpyxl is not available."""
    headers = ["Line Number", "Size", "Service", "Spec / Class", "From", "To", "P&ID Reference", "Status", "Confidence (%)"]
    all_rows: list[list[str]] = [headers]
    for row_data in line_rows.values():
        all_rows.append([
            html.escape(str(row_data["lineNumber"])),
            html.escape(str(row_data["size"])),
            html.escape(str(row_data["service"])),
            html.escape(str(row_data["spec"])),
            html.escape(str(row_data["from"])),
            html.escape(str(row_data["to"])),
            html.escape(", ".join(sorted(row_data["sheets"]))),
            html.escape(str(row_data["status"])),
            html.escape(str(round(row_data["confidence"] * 100, 1))),
        ])
    sheet_rows = []
    for index, row in enumerate(all_rows, start=1):
        cells = []
        for col, value in enumerate(row, start=1):
            ref = f"{chr(64 + col)}{index}"
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        sheet_rows.append(f'<row r="{index}">{"".join(cells)}</row>')
    sheet = f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        zf.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        zf.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Line List" sheetId="1" r:id="rId1"/></sheets></workbook>')
        zf.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        zf.writestr("xl/worksheets/sheet1.xml", sheet)


def _node_anchor(node: dict[str, Any], side: str) -> tuple[float, float]:
    layout = node.get("layout", {})
    x = float(layout.get("x", 0))
    y = float(layout.get("y", 0))
    w = float(layout.get("width", 160))
    h = float(layout.get("height", 88))
    if side == "right":
        return x + w, y + h / 2
    return x, y + h / 2


def _fill_for_kind(kind: str) -> str:
    return {
        "equipment": "#e8f2ff",
        "instrument": "#f7f0ff",
        "valve": "#fff2d8",
        "panel": "#e8f8ef",
        "junction_box": "#eaf7f7",
        "off_page_connector": "#ffeceb",
        "cable_endpoint": "#eef2ff",
    }.get(kind, "#ffffff")


def _minimal_pdf_bytes(graph: dict[str, Any]) -> bytes:
    text = f"Recreation export for {graph.get('projectId')} with {len(graph.get('nodes', []))} nodes"
    stream = f"BT /F1 18 Tf 72 720 Td ({_pdf_escape(text)}) Tj ET"
    objects = [
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj",
        "4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
        f"5 0 obj << /Length {len(stream)} >> stream\n{stream}\nendstream endobj",
    ]
    body = "%PDF-1.4\n" + "\n".join(objects) + "\n"
    offsets = [0]
    current = len("%PDF-1.4\n")
    for obj in objects:
        offsets.append(current)
        current += len(obj) + 1
    xref_start = len(body)
    xref = ["xref", "0 6", "0000000000 65535 f "]
    xref.extend(f"{offset:010d} 00000 n " for offset in offsets[1:])
    trailer = f"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n"
    return (body + "\n".join(xref) + "\n" + trailer).encode("latin-1")


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _write_minimal_xlsx(graph: dict[str, Any], output_path: Path) -> None:
    # NOTE: This fallback only writes a Tags sheet. Install openpyxl for full
    # export with Connections and Review sheets.
    rows: list[list[str]] = [["Tag", "Kind", "Symbol", "Confidence", "Install openpyxl for full export"]]
    rows.extend(
        [
            [
                html.escape(str(node.get("tag", ""))),
                html.escape(str(node.get("kind", ""))),
                html.escape(str(node.get("symbolId", ""))),
                html.escape(str(node.get("confidence", ""))),
            ]
            for node in graph.get("nodes", [])
        ]
    )
    sheet_rows = []
    for index, row in enumerate(rows, start=1):
        cells = []
        for col, value in enumerate(row, start=1):
            ref = f"{chr(64 + col)}{index}"
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        sheet_rows.append(f'<row r="{index}">{"".join(cells)}</row>')
    sheet = f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>')
        zf.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
        zf.writestr("xl/workbook.xml", '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Tags" sheetId="1" r:id="rId1"/></sheets></workbook>')
        zf.writestr("xl/_rels/workbook.xml.rels", '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>')
        zf.writestr("xl/worksheets/sheet1.xml", sheet)
