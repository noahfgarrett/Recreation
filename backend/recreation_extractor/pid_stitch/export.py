from __future__ import annotations

import base64
import html
import io
import math
import re
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

from recreation_extractor.models import to_dict


_PIPE_KINDS = {"pipe", "connector"}
_RECT_KINDS = {"region", "source_fragment", "symbol"}
_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")
_MAX_DIMENSION = 20000.0


def export_drawing_svg(document: dict[str, Any], path: Path) -> Path:
    """Export a stitched drawing document as simple structured SVG."""
    path.parent.mkdir(parents=True, exist_ok=True)
    drawing = _as_dict(document)
    width, height = _document_size(drawing)
    parts = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{_num(width)}" height="{_num(height)}" '
            f'viewBox="0 0 {_num(width)} {_num(height)}">'
        ),
        f'<rect x="0" y="0" width="{_num(width)}" height="{_num(height)}" fill="#ffffff"/>',
    ]

    for obj in _objects(drawing):
        kind = str(obj.get("kind", ""))
        if kind in _RECT_KINDS:
            rect = _rect_from_object(obj)
            if rect is not None:
                parts.append(_svg_symbol(obj, rect) if kind == "symbol" else _svg_rect(obj, rect, kind))
                label = _clean_text(str(obj.get("label") or ""))
                if label and not _hide_center_label(obj):
                    if kind == "symbol":
                        parts.append(_svg_symbol_label(obj, label, rect))
                    else:
                        parts.append(_svg_text(obj, label, rect["x"] + 4.0, rect["y"] + _style_font_size(obj, 11.0) + 4.0))

    for obj in _objects(drawing):
        kind = str(obj.get("kind", ""))
        if kind in _PIPE_KINDS:
            points = _points(obj.get("points"))
            if len(points) >= 2:
                parts.append(_svg_polyline(obj, points, kind))
                label = str(obj.get("label") or "")
                if label and not _hide_center_label(obj):
                    label_point = _midpoint(points)
                    parts.append(_svg_text(obj, label, label_point["x"], label_point["y"] - 6.0))

    for obj in _objects(drawing):
        if str(obj.get("kind", "")) == "label":
            label = str(obj.get("label") or "")
            point = _label_point(obj)
            if label and point is not None:
                parts.append(_svg_text(obj, label, point["x"], point["y"]))

    parts.append("</svg>")
    path.write_text("\n".join(parts), encoding="utf-8")
    return path


def export_drawing_pdf(document: dict[str, Any], path: Path) -> Path:
    """Export a stitched drawing document as a PDF using reportlab."""
    try:
        from reportlab.pdfgen import canvas
    except Exception as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("reportlab is required for drawing PDF export") from exc

    path.parent.mkdir(parents=True, exist_ok=True)
    drawing = _as_dict(document)
    width, height = _document_size(drawing)
    c = canvas.Canvas(str(path), pagesize=(width, height))
    c.setTitle(str(drawing.get("name") or "Recreation Drawing"))

    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, width, height, fill=1, stroke=0)

    for obj in _objects(drawing):
        kind = str(obj.get("kind", ""))
        if kind in _RECT_KINDS:
            rect = _rect_from_object(obj)
            if rect is not None:
                if kind == "symbol":
                    _pdf_symbol(c, obj, rect, height)
                else:
                    _pdf_rect(c, obj, rect, kind, height)
                label = _clean_text(str(obj.get("label") or ""))
                if label and not _hide_center_label(obj):
                    if kind == "symbol":
                        _pdf_symbol_label(c, obj, label, rect, height)
                    else:
                        _pdf_text(c, obj, label, rect["x"] + 4.0, rect["y"] + _style_font_size(obj, 11.0) + 4.0, height)

    for obj in _objects(drawing):
        kind = str(obj.get("kind", ""))
        if kind in _PIPE_KINDS:
            points = _points(obj.get("points"))
            if len(points) >= 2:
                _pdf_polyline(c, obj, points, kind, height)
                label = str(obj.get("label") or "")
                if label:
                    label_point = _midpoint(points)
                    _pdf_text(c, obj, label, label_point["x"], label_point["y"] - 6.0, height)

    for obj in _objects(drawing):
        if str(obj.get("kind", "")) == "label":
            label = str(obj.get("label") or "")
            point = _label_point(obj)
            if label and point is not None:
                _pdf_text(c, obj, label, point["x"], point["y"], height)

    c.save()
    return path


def _as_dict(value: Any) -> dict[str, Any]:
    payload = to_dict(value)
    return payload if isinstance(payload, dict) else {}


def _objects(document: dict[str, Any]) -> list[dict[str, Any]]:
    objects = document.get("objects")
    if not isinstance(objects, list):
        return []
    return [obj for obj in objects if isinstance(obj, dict)]


def _hide_center_label(obj: dict[str, Any]) -> bool:
    metadata = obj.get("metadata")
    return isinstance(metadata, dict) and metadata.get("hideCenterLabel") is True


def _document_size(document: dict[str, Any]) -> tuple[float, float]:
    width = _clamp(_float(document.get("width"), 1200.0), 1.0, _MAX_DIMENSION)
    height = _clamp(_float(document.get("height"), 800.0), 1.0, _MAX_DIMENSION)
    return width, height


def _points(value: Any) -> list[dict[str, float]]:
    if not isinstance(value, list):
        return []
    points: list[dict[str, float]] = []
    for point in value:
        if not isinstance(point, dict):
            continue
        x = _finite_float(point.get("x"))
        y = _finite_float(point.get("y"))
        if x is None or y is None:
            continue
        points.append({"x": x, "y": y})
    return points


def _rect_from_object(obj: dict[str, Any]) -> dict[str, float] | None:
    bounds = obj.get("bounds")
    if isinstance(bounds, dict):
        width = _finite_float(bounds.get("width"))
        height = _finite_float(bounds.get("height"))
        if width is None or height is None:
            return None
        return {
            "x": _float(bounds.get("x"), 0.0),
            "y": _float(bounds.get("y"), 0.0),
            "width": _clamp(width, 0.0, _MAX_DIMENSION),
            "height": _clamp(height, 0.0, _MAX_DIMENSION),
        }
    points = _points(obj.get("points"))
    if not points:
        return None
    min_x = min(point["x"] for point in points)
    min_y = min(point["y"] for point in points)
    max_x = max(point["x"] for point in points)
    max_y = max(point["y"] for point in points)
    return {"x": min_x, "y": min_y, "width": max_x - min_x, "height": max_y - min_y}


def _label_point(obj: dict[str, Any]) -> dict[str, float] | None:
    points = _points(obj.get("points"))
    if points:
        return points[0]
    rect = _rect_from_object(obj)
    if rect is None:
        return None
    return {"x": rect["x"], "y": rect["y"] + _style_font_size(obj, 12.0)}


def _svg_rect(obj: dict[str, Any], rect: dict[str, float], kind: str) -> str:
    source_image = _svg_source_image(obj, rect) if kind == "source_fragment" else ""
    opacity = _style_opacity(obj, 0.18 if kind == "source_fragment" else 0.35)
    stroke = _style_color(obj, "stroke", "#94a3b8" if kind == "source_fragment" else "#2563eb")
    fill = "none" if source_image else _style_color(obj, "fill", "#f8fafc" if kind == "source_fragment" else "#dbeafe")
    stroke_width = _style_stroke_width(obj, 1.0)
    dash = _dash_value(obj, "6 4" if kind == "source_fragment" else "")
    dash_attr = f' stroke-dasharray="{_attr(dash)}"' if dash else ""
    rect_markup = (
        f'<rect data-kind="{_attr(kind)}" data-id="{_attr(str(obj.get("id") or ""))}" '
        f'x="{_num(rect["x"])}" y="{_num(rect["y"])}" width="{_num(rect["width"])}" height="{_num(rect["height"])}" '
        f'fill="{_attr(fill)}" stroke="{_attr(stroke)}" stroke-width="{_num(stroke_width)}" '
        f'opacity="{_scalar(opacity)}"{dash_attr}/>'
    )
    if source_image:
        return f"{source_image}\n{rect_markup}"
    return rect_markup


def _svg_symbol(obj: dict[str, Any], rect: dict[str, float]) -> str:
    stroke = _style_color(obj, "stroke", "#334155")
    fill = _style_color(obj, "fill", "#ffffff")
    opacity = _style_opacity(obj, 1.0)
    stroke_width = _style_stroke_width(obj, 1.5)
    symbol_type = _symbol_type(obj)
    orientation = _symbol_orientation(obj)
    cx = rect["x"] + rect["width"] / 2.0
    cy = rect["y"] + rect["height"] / 2.0
    radius = max(8.0, min(rect["width"] * 0.22, rect["height"] * 0.34))
    left = rect["x"]
    right = rect["x"] + rect["width"]
    top = rect["y"]
    bottom = rect["y"] + rect["height"]
    common_base = (
        f'data-kind="symbol" data-id="{_attr(str(obj.get("id") or ""))}" '
        f'data-symbol-registry="recreation-vector-pack" data-symbol-type="{_attr(symbol_type)}" '
        f'stroke="{_attr(stroke)}" stroke-width="{_num(stroke_width)}" '
        f'opacity="{_scalar(opacity)}"'
    )
    common = f'{common_base} fill="{_attr(fill)}"'
    line = lambda x1, y1, x2, y2: (
        f'<line {common_base} x1="{_num(x1)}" y1="{_num(y1)}" x2="{_num(x2)}" y2="{_num(y2)}" '
        f'fill="none"/>'
    )
    polygon = lambda points, shape_fill=fill: (
        f'<polygon data-kind="symbol" data-id="{_attr(str(obj.get("id") or ""))}" '
        f'data-symbol-registry="recreation-vector-pack" data-symbol-type="{_attr(symbol_type)}" '
        f'points="{_attr(" ".join(f"{_num(x)},{_num(y)}" for x, y in points))}" '
        f'fill="{_attr(shape_fill)}" stroke="{_attr(stroke)}" stroke-width="{_num(stroke_width)}" '
        f'opacity="{_scalar(opacity)}"/>'
    )
    path = lambda d, shape_fill="none": (
        f'<path {common_base} d="{_attr(d)}" fill="{_attr(shape_fill)}"/>'
    )
    text = lambda value, x, y, size=10.0: (
        f'<text x="{_num(x)}" y="{_num(y)}" fill="{_attr(stroke)}" stroke="none" '
        f'font-family="Arial, Helvetica, sans-serif" font-size="{_num(size)}" '
        f'font-weight="700" text-anchor="middle">{_text(value)}</text>'
    )
    if symbol_type == "flow_arrow":
        if orientation == "left":
            points = [(right, top), (left, cy), (right, bottom)]
        else:
            points = [(left, top), (right, cy), (left, bottom)]
        return polygon(points, stroke)
    if symbol_type == "offpage":
        if orientation == "left":
            points = [(right, top), (left + rect["width"] * 0.22, top), (left, cy), (left + rect["width"] * 0.22, bottom), (right, bottom)]
        else:
            points = [(left, top), (left + rect["width"] * 0.78, top), (right, cy), (left + rect["width"] * 0.78, bottom), (left, bottom)]
        return polygon(points)
    if symbol_type == "instrument":
        r = min(rect["width"], rect["height"]) * 0.42
        return "\n".join(
            [
                line(cx, cy + r, cx, bottom),
                f'<circle {common} cx="{_num(cx)}" cy="{_num(cy)}" r="{_num(r)}"/>',
                line(cx - r * 0.48, cy, cx + r * 0.48, cy),
                line(cx, cy - r * 0.48, cx, cy + r * 0.48),
            ]
        )
    if symbol_type == "gauge":
        r = min(rect["width"], rect["height"]) * 0.38
        return "\n".join(
            [
                line(cx, cy + r, cx, bottom - rect["height"] * 0.04),
                f'<circle {common} cx="{_num(cx)}" cy="{_num(cy)}" r="{_num(r)}"/>',
                path(f"M {_num(cx - r * 0.66)} {_num(cy + r * 0.3)} A {_num(r * 0.74)} {_num(r * 0.74)} 0 0 1 {_num(cx + r * 0.66)} {_num(cy + r * 0.3)}"),
                line(cx - r * 0.43, cy + r * 0.24, cx - r * 0.3, cy + r * 0.1),
                line(cx + r * 0.43, cy + r * 0.24, cx + r * 0.3, cy + r * 0.1),
                line(cx, cy + r * 0.05, cx + r * 0.53, cy - r * 0.42),
                f'<circle {common_base} cx="{_num(cx)}" cy="{_num(cy + r * 0.05)}" r="{_num(max(1.2, r * 0.08))}" fill="{_attr(stroke)}"/>',
            ]
        )
    if symbol_type == "flow_meter":
        r = min(rect["width"], rect["height"]) * 0.32
        return "\n".join(
            [
                line(left, cy, cx - r, cy),
                line(cx + r, cy, right, cy),
                f'<circle {common} cx="{_num(cx)}" cy="{_num(cy)}" r="{_num(r)}"/>',
                path(f"M {_num(cx - r * 0.55)} {_num(cy + r * 0.32)} L {_num(cx)} {_num(cy - r * 0.7)} L {_num(cx + r * 0.55)} {_num(cy + r * 0.32)}"),
                line(cx - r * 0.42, cy + r * 0.62, cx + r * 0.42, cy + r * 0.62),
            ]
        )
    if symbol_type in {
        "pid_signal",
        "pid_data",
        "pid_pneumatic",
        "pid_pneumatic_binary",
        "pid_electric",
        "pid_electric_binary",
        "pid_electromagnetic",
        "pid_hydraulic",
        "pid_mechanical",
        "pid_capillary",
        "pid_heat_trace",
        "pid_heated_cooled",
    }:
        dash = {
            "pid_capillary": "2 5",
            "pid_data": "9 5",
            "pid_electric": "3 3",
            "pid_electric_binary": "3 3 12 3",
            "pid_electromagnetic": "10 4 2 4 2 4",
            "pid_hydraulic": "14 4 3 4",
            "pid_heated_cooled": "6 3",
            "pid_pneumatic": "1 5",
            "pid_pneumatic_binary": "1 4 10 4",
        }.get(symbol_type)
        dash_attr = f' stroke-dasharray="{_attr(dash)}"' if dash else ""
        marks = [
            f'<line {common_base} x1="{_num(left)}" y1="{_num(cy)}" x2="{_num(right)}" y2="{_num(cy)}" fill="none"{dash_attr}/>'
        ]
        if symbol_type == "pid_mechanical":
            marks.append(path(f"M {_num(left)} {_num(cy + rect['height'] * 0.16)} L {_num(left + rect['width'] * 0.14)} {_num(cy - rect['height'] * 0.16)} L {_num(left + rect['width'] * 0.28)} {_num(cy + rect['height'] * 0.16)} L {_num(left + rect['width'] * 0.42)} {_num(cy - rect['height'] * 0.16)} L {_num(left + rect['width'] * 0.56)} {_num(cy + rect['height'] * 0.16)} L {_num(left + rect['width'] * 0.7)} {_num(cy - rect['height'] * 0.16)} L {_num(left + rect['width'] * 0.84)} {_num(cy + rect['height'] * 0.16)}"))
        elif symbol_type in {"pid_heat_trace", "pid_heated_cooled"}:
            marks.append(path(f"M {_num(left)} {_num(cy + rect['height'] * 0.2)} C {_num(left + rect['width'] * 0.18)} {_num(cy - rect['height'] * 0.25)}, {_num(left + rect['width'] * 0.32)} {_num(cy + rect['height'] * 0.25)}, {_num(left + rect['width'] * 0.5)} {_num(cy - rect['height'] * 0.2)} C {_num(left + rect['width'] * 0.68)} {_num(cy + rect['height'] * 0.25)}, {_num(left + rect['width'] * 0.82)} {_num(cy - rect['height'] * 0.25)}, {_num(right)} {_num(cy + rect['height'] * 0.2)}"))
        elif symbol_type == "pid_electromagnetic":
            marks.append(path(f"M {_num(left + rect['width'] * 0.16)} {_num(cy - rect['height'] * 0.18)} C {_num(left + rect['width'] * 0.26)} {_num(top + rect['height'] * 0.08)}, {_num(left + rect['width'] * 0.38)} {_num(top + rect['height'] * 0.08)}, {_num(left + rect['width'] * 0.48)} {_num(cy - rect['height'] * 0.18)} C {_num(left + rect['width'] * 0.58)} {_num(cy)}, {_num(left + rect['width'] * 0.7)} {_num(cy)}, {_num(left + rect['width'] * 0.8)} {_num(cy - rect['height'] * 0.18)}"))
            marks.append(path(f"M {_num(left + rect['width'] * 0.16)} {_num(cy + rect['height'] * 0.18)} C {_num(left + rect['width'] * 0.26)} {_num(bottom - rect['height'] * 0.08)}, {_num(left + rect['width'] * 0.38)} {_num(bottom - rect['height'] * 0.08)}, {_num(left + rect['width'] * 0.48)} {_num(cy + rect['height'] * 0.18)} C {_num(left + rect['width'] * 0.58)} {_num(cy)}, {_num(left + rect['width'] * 0.7)} {_num(cy)}, {_num(left + rect['width'] * 0.8)} {_num(cy + rect['height'] * 0.18)}"))
        return "\n".join(marks)
    if symbol_type in {
        "pressure_indicator",
        "temperature_indicator",
        "level_indicator",
        "flow_transmitter",
        "pressure_transmitter",
        "temperature_transmitter",
        "level_transmitter",
        "analyzer",
        "controller",
        "fit",
        "tit",
        "flow_element",
        "flow_indicator",
        "flow_controller",
        "pressure_element",
        "pressure_controller",
        "temperature_element",
        "temperature_controller",
        "level_element",
        "level_controller",
        "local_instrument",
        "panel_instrument",
    }:
        code = {
            "analyzer": "A",
            "controller": "C",
            "fit": "FIT",
            "flow_controller": "FIC",
            "flow_element": "FE",
            "flow_indicator": "FI",
            "flow_transmitter": "FT",
            "level_controller": "LIC",
            "level_element": "LE",
            "level_indicator": "LI",
            "level_transmitter": "LT",
            "local_instrument": "L",
            "panel_instrument": "P",
            "pressure_controller": "PIC",
            "pressure_element": "PE",
            "pressure_indicator": "PI",
            "pressure_transmitter": "PT",
            "temperature_controller": "TIC",
            "temperature_element": "TE",
            "temperature_indicator": "TI",
            "temperature_transmitter": "TT",
            "tit": "TIT",
        }.get(symbol_type, "I")
        r = min(rect["width"], rect["height"]) * 0.38
        marks = [
            line(cx, cy + r, cx, bottom),
            f'<circle {common} cx="{_num(cx)}" cy="{_num(cy - rect["height"] * 0.08)}" r="{_num(r)}"/>',
        ]
        if symbol_type.endswith("_transmitter") or symbol_type.endswith("_controller") or symbol_type in {"controller", "panel_instrument"}:
            marks.append(line(cx - r, cy - rect["height"] * 0.08, cx + r, cy - rect["height"] * 0.08))
        if symbol_type == "local_instrument":
            marks.append(path(f"M {_num(cx - r * 0.82)} {_num(cy + r * 0.62)} L {_num(cx + r * 0.82)} {_num(cy + r * 0.62)}"))
        if symbol_type == "analyzer":
            marks.append(path(f"M {_num(cx - r * 0.45)} {_num(cy + r * 0.45)} L {_num(cx)} {_num(cy - r * 0.8)} L {_num(cx + r * 0.45)} {_num(cy + r * 0.45)} Z"))
        marks.append(text(code, cx, cy - rect["height"] * 0.08 + min(12.0, r * 0.35), 9.0 if len(code) > 2 else 11.0))
        return "\n".join(marks)
    if symbol_type in {"pressure_sensor", "reference_circle", "tag_circle", "tag_square"}:
        if symbol_type == "pressure_sensor":
            r = min(rect["width"], rect["height"]) * 0.38
            return "\n".join(
                [
                    line(cx, cy + r, cx, bottom),
                    f'<circle {common} cx="{_num(cx)}" cy="{_num(cy - rect["height"] * 0.08)}" r="{_num(r)}"/>',
                    path(f"M {_num(cx - r * 0.55)} {_num(cy + r * 0.12)} A {_num(r * 0.62)} {_num(r * 0.62)} 0 0 1 {_num(cx + r * 0.55)} {_num(cy + r * 0.12)}"),
                    text("P", cx, cy - rect["height"] * 0.08 + min(12.0, r * 0.35), 11.0),
                ]
            )
        if symbol_type == "tag_square":
            size = min(rect["width"], rect["height"]) * 0.46
            return f'<rect {common} x="{_num(cx - size / 2.0)}" y="{_num(cy - size / 2.0)}" width="{_num(size)}" height="{_num(size)}"/>'
        r = min(rect["width"], rect["height"]) * (0.3 if symbol_type == "tag_circle" else 0.4)
        marks = [f'<circle {common} cx="{_num(cx)}" cy="{_num(cy)}" r="{_num(r)}"/>']
        if symbol_type == "reference_circle":
            marks.append(line(cx - r * 0.58, cy, cx + r * 0.58, cy))
        return "\n".join(marks)
    if symbol_type in {"pneumatic_actuator", "electric_actuator", "handwheel_actuator"}:
        marks = [line(cx, cy + rect["height"] * 0.1, cx, bottom)]
        if symbol_type == "pneumatic_actuator":
            marks.append(path(f"M {_num(cx - rect['width'] * 0.28)} {_num(top + rect['height'] * 0.24)} C {_num(cx - rect['width'] * 0.28)} {_num(top + rect['height'] * 0.04)}, {_num(cx + rect['width'] * 0.28)} {_num(top + rect['height'] * 0.04)}, {_num(cx + rect['width'] * 0.28)} {_num(top + rect['height'] * 0.24)} L {_num(cx + rect['width'] * 0.2)} {_num(cy + rect['height'] * 0.1)} L {_num(cx - rect['width'] * 0.2)} {_num(cy + rect['height'] * 0.1)} Z", fill))
        elif symbol_type == "electric_actuator":
            marks.append(f'<rect {common} x="{_num(cx - rect["width"] * 0.26)}" y="{_num(top + rect["height"] * 0.14)}" width="{_num(rect["width"] * 0.52)}" height="{_num(rect["height"] * 0.36)}" rx="3.0"/>')
        else:
            r = min(rect["width"], rect["height"]) * 0.24
            marks.extend([f'<circle {common} cx="{_num(cx)}" cy="{_num(top + rect["height"] * 0.34)}" r="{_num(r)}"/>', line(cx - r, top + rect["height"] * 0.34, cx + r, top + rect["height"] * 0.34), line(cx, top + rect["height"] * 0.34 - r, cx, top + rect["height"] * 0.34 + r)])
        return "\n".join(marks)
    if symbol_type in {"tee", "elbow", "cross", "union", "pipe_break", "flexible_hose", "expansion_loop", "orifice_plate", "spectacle_blind"}:
        if symbol_type == "tee":
            return "\n".join([line(left, cy, right, cy), line(cx, cy, cx, top)])
        if symbol_type == "elbow":
            return path(f"M {_num(left)} {_num(bottom - rect['height'] * 0.18)} H {_num(cx - rect['width'] * 0.08)} Q {_num(right - rect['width'] * 0.18)} {_num(bottom - rect['height'] * 0.18)}, {_num(right - rect['width'] * 0.18)} {_num(cy - rect['height'] * 0.08)} V {_num(top)}")
        if symbol_type == "cross":
            return "\n".join([line(left, cy, right, cy), line(cx, top, cx, bottom)])
        if symbol_type == "union":
            return "\n".join([line(left, cy, right, cy), path(f"M {_num(cx - rect['width'] * 0.18)} {_num(top + rect['height'] * 0.26)} L {_num(cx)} {_num(cy)} L {_num(cx - rect['width'] * 0.18)} {_num(bottom - rect['height'] * 0.26)}"), path(f"M {_num(cx + rect['width'] * 0.18)} {_num(top + rect['height'] * 0.26)} L {_num(cx)} {_num(cy)} L {_num(cx + rect['width'] * 0.18)} {_num(bottom - rect['height'] * 0.26)}")])
        if symbol_type == "pipe_break":
            return "\n".join([line(left, cy, cx - rect["width"] * 0.12, cy), path(f"M {_num(cx - rect['width'] * 0.05)} {_num(top + rect['height'] * 0.25)} L {_num(cx - rect['width'] * 0.15)} {_num(bottom - rect['height'] * 0.25)}"), path(f"M {_num(cx + rect['width'] * 0.15)} {_num(top + rect['height'] * 0.25)} L {_num(cx + rect['width'] * 0.05)} {_num(bottom - rect['height'] * 0.25)}"), line(cx + rect["width"] * 0.12, cy, right, cy)])
        if symbol_type == "flexible_hose":
            return path(f"M {_num(left)} {_num(cy)} H {_num(left + rect['width'] * 0.18)} C {_num(left + rect['width'] * 0.26)} {_num(top + rect['height'] * 0.15)}, {_num(left + rect['width'] * 0.34)} {_num(bottom - rect['height'] * 0.15)}, {_num(left + rect['width'] * 0.42)} {_num(cy)} C {_num(left + rect['width'] * 0.5)} {_num(top + rect['height'] * 0.15)}, {_num(left + rect['width'] * 0.58)} {_num(bottom - rect['height'] * 0.15)}, {_num(left + rect['width'] * 0.66)} {_num(cy)} C {_num(left + rect['width'] * 0.74)} {_num(top + rect['height'] * 0.15)}, {_num(left + rect['width'] * 0.82)} {_num(bottom - rect['height'] * 0.15)}, {_num(left + rect['width'] * 0.9)} {_num(cy)} H {_num(right)}")
        if symbol_type == "expansion_loop":
            return path(f"M {_num(left)} {_num(bottom - rect['height'] * 0.25)} H {_num(left + rect['width'] * 0.25)} V {_num(top + rect['height'] * 0.22)} H {_num(right - rect['width'] * 0.25)} V {_num(bottom - rect['height'] * 0.25)} H {_num(right)}")
        if symbol_type == "orifice_plate":
            return "\n".join([line(left, cy, right, cy), line(cx, top + rect["height"] * 0.14, cx, bottom - rect["height"] * 0.14), f'<circle {common} cx="{_num(cx)}" cy="{_num(cy)}" r="{_num(min(rect["width"], rect["height"]) * 0.08)}"/>'])
        r = min(rect["width"], rect["height"]) * 0.18
        return "\n".join([line(left, cy, cx - r * 1.8, cy), line(cx + r * 1.8, cy, right, cy), f'<circle {common} cx="{_num(cx - r * 0.6)}" cy="{_num(cy)}" r="{_num(r)}"/>', f'<circle {common} cx="{_num(cx + r * 0.6)}" cy="{_num(cy)}" r="{_num(r)}"/>', line(cx, cy - r, cx, cy + r)])
    if symbol_type == "valve":
        if orientation == "vertical":
            return "\n".join(
                [
                    line(cx, top, cx, bottom),
                    polygon([(left + rect["width"] * 0.2, top + rect["height"] * 0.18), (left + rect["width"] * 0.8, top + rect["height"] * 0.18), (cx, cy)]),
                    polygon([(left + rect["width"] * 0.2, top + rect["height"] * 0.82), (left + rect["width"] * 0.8, top + rect["height"] * 0.82), (cx, cy)]),
                    line(left + rect["width"] * 0.2, top + rect["height"] * 0.18, left + rect["width"] * 0.8, top + rect["height"] * 0.18),
                ]
            )
        return "\n".join(
            [
                line(left, cy, right, cy),
                polygon([(left + rect["width"] * 0.16, top + rect["height"] * 0.2), (left + rect["width"] * 0.16, top + rect["height"] * 0.8), (cx, cy)]),
                polygon([(left + rect["width"] * 0.84, top + rect["height"] * 0.2), (left + rect["width"] * 0.84, top + rect["height"] * 0.8), (cx, cy)]),
                line(left + rect["width"] * 0.84, top + rect["height"] * 0.2, left + rect["width"] * 0.84, top + rect["height"] * 0.8),
            ]
        )
    if symbol_type in {
        "globe_valve",
        "ball_valve",
        "butterfly_valve",
        "plug_valve",
        "needle_valve",
        "diaphragm_valve",
        "solenoid_valve",
        "three_way_valve",
        "angle_valve",
        "flanged_valve",
        "reducing_valve",
        "wedge_valve",
        "normally_open_valve",
        "normally_closed_valve",
        "fail_open_valve",
        "fail_closed_valve",
        "balancing_valve",
        "double_check_valve",
        "backpressure_valve",
        "powered_valve",
        "pressure_relief_valve",
        "relief_angle_valve",
    }:
        marks = [
            line(left, cy, right, cy),
            polygon([(left + rect["width"] * 0.16, top + rect["height"] * 0.2), (left + rect["width"] * 0.16, top + rect["height"] * 0.8), (cx, cy)]),
            polygon([(left + rect["width"] * 0.84, top + rect["height"] * 0.2), (left + rect["width"] * 0.84, top + rect["height"] * 0.8), (cx, cy)]),
        ]
        if symbol_type in {"angle_valve", "relief_angle_valve"}:
            marks.append(line(cx, cy, cx, bottom))
        if symbol_type == "three_way_valve":
            marks.append(line(cx, cy, cx, top))
        if symbol_type == "flanged_valve":
            marks.extend([line(left + rect["width"] * 0.12, top + rect["height"] * 0.18, left + rect["width"] * 0.12, bottom - rect["height"] * 0.18), line(right - rect["width"] * 0.12, top + rect["height"] * 0.18, right - rect["width"] * 0.12, bottom - rect["height"] * 0.18)])
        if symbol_type == "globe_valve":
            marks.append(f'<circle {common} cx="{_num(cx)}" cy="{_num(cy)}" r="{_num(min(rect["width"], rect["height"]) * 0.17)}"/>')
        if symbol_type == "ball_valve":
            marks.append(f'<circle {common} cx="{_num(cx)}" cy="{_num(cy)}" r="{_num(min(rect["width"], rect["height"]) * 0.13)}"/>')
        if symbol_type == "butterfly_valve":
            marks.append(line(cx - rect["width"] * 0.2, cy - rect["height"] * 0.2, cx + rect["width"] * 0.2, cy + rect["height"] * 0.2))
        if symbol_type == "plug_valve":
            marks.append(f'<rect {common} x="{_num(cx - rect["width"] * 0.12)}" y="{_num(cy - rect["height"] * 0.12)}" width="{_num(rect["width"] * 0.24)}" height="{_num(rect["height"] * 0.24)}"/>')
        if symbol_type == "needle_valve":
            marks.extend([line(cx, cy, cx, top + rect["height"] * 0.12), line(cx - rect["width"] * 0.12, top + rect["height"] * 0.12, cx + rect["width"] * 0.12, top + rect["height"] * 0.12), line(cx, cy, cx + rect["width"] * 0.18, top + rect["height"] * 0.24)])
        if symbol_type == "diaphragm_valve":
            marks.append(path(f"M {_num(left + rect['width'] * 0.26)} {_num(top + rect['height'] * 0.3)} Q {_num(cx)} {_num(top + rect['height'] * 0.08)}, {_num(right - rect['width'] * 0.26)} {_num(top + rect['height'] * 0.3)}"))
        if symbol_type == "solenoid_valve":
            marks.append(f'<rect {common} x="{_num(cx - rect["width"] * 0.13)}" y="{_num(top + rect["height"] * 0.06)}" width="{_num(rect["width"] * 0.26)}" height="{_num(rect["height"] * 0.18)}"/>')
        if symbol_type == "reducing_valve":
            marks.append(line(left + rect["width"] * 0.22, bottom - rect["height"] * 0.12, right - rect["width"] * 0.22, top + rect["height"] * 0.12))
        if symbol_type == "wedge_valve":
            marks.extend([line(cx - rect["width"] * 0.16, top + rect["height"] * 0.2, cx + rect["width"] * 0.16, bottom - rect["height"] * 0.2), line(cx + rect["width"] * 0.16, top + rect["height"] * 0.2, cx - rect["width"] * 0.16, bottom - rect["height"] * 0.2)])
        if symbol_type == "normally_open_valve":
            marks.append(line(cx - rect["width"] * 0.1, top + rect["height"] * 0.12, cx + rect["width"] * 0.1, top + rect["height"] * 0.12))
        if symbol_type == "normally_closed_valve":
            marks.append(line(cx - rect["width"] * 0.1, top + rect["height"] * 0.12, cx + rect["width"] * 0.1, top + rect["height"] * 0.32))
        if symbol_type == "fail_open_valve":
            marks.extend([line(cx - rect["width"] * 0.2, top + rect["height"] * 0.12, cx + rect["width"] * 0.2, top + rect["height"] * 0.12), line(cx, top + rect["height"] * 0.12, cx, top + rect["height"] * 0.28)])
        if symbol_type == "fail_closed_valve":
            marks.extend([line(cx - rect["width"] * 0.2, top + rect["height"] * 0.12, cx + rect["width"] * 0.2, top + rect["height"] * 0.32), line(cx, top + rect["height"] * 0.22, cx, top + rect["height"] * 0.36)])
        if symbol_type == "balancing_valve":
            marks.extend([line(cx - rect["width"] * 0.16, cy + rect["height"] * 0.16, cx + rect["width"] * 0.16, cy - rect["height"] * 0.16), line(cx - rect["width"] * 0.16, cy - rect["height"] * 0.16, cx + rect["width"] * 0.16, cy + rect["height"] * 0.16)])
        if symbol_type == "double_check_valve":
            marks.extend([path(f"M {_num(cx - rect['width'] * 0.25)} {_num(top + rect['height'] * 0.28)} L {_num(cx - rect['width'] * 0.06)} {_num(cy)} L {_num(cx - rect['width'] * 0.25)} {_num(bottom - rect['height'] * 0.28)}"), path(f"M {_num(cx + rect['width'] * 0.06)} {_num(top + rect['height'] * 0.28)} L {_num(cx + rect['width'] * 0.25)} {_num(cy)} L {_num(cx + rect['width'] * 0.06)} {_num(bottom - rect['height'] * 0.28)}")])
        if symbol_type == "backpressure_valve":
            marks.append(path(f"M {_num(cx - rect['width'] * 0.2)} {_num(top + rect['height'] * 0.24)} C {_num(cx - rect['width'] * 0.06)} {_num(top + rect['height'] * 0.08)}, {_num(cx + rect['width'] * 0.16)} {_num(top + rect['height'] * 0.08)}, {_num(cx + rect['width'] * 0.3)} {_num(top + rect['height'] * 0.24)}"))
        if symbol_type == "powered_valve":
            marks.extend([line(cx, cy, cx, top + rect["height"] * 0.2), f'<rect {common} x="{_num(cx - rect["width"] * 0.16)}" y="{_num(top + rect["height"] * 0.06)}" width="{_num(rect["width"] * 0.32)}" height="{_num(rect["height"] * 0.18)}" rx="3.0"/>'])
        if symbol_type in {"pressure_relief_valve", "relief_angle_valve"}:
            marks.extend([line(left + rect["width"] * 0.66, cy, left + rect["width"] * 0.66, top + rect["height"] * 0.18), path(f"M {_num(left + rect['width'] * 0.5)} {_num(top + rect['height'] * 0.22)} C {_num(left + rect['width'] * 0.58)} {_num(top + rect['height'] * 0.02)}, {_num(left + rect['width'] * 0.78)} {_num(top + rect['height'] * 0.02)}, {_num(left + rect['width'] * 0.86)} {_num(top + rect['height'] * 0.22)}"), line(left + rect["width"] * 0.72, top + rect["height"] * 0.18, left + rect["width"] * 0.72, top + rect["height"] * 0.34)])
        return "\n".join(marks)
    if symbol_type in {"gate_valve", "check_valve", "control_valve", "relief_valve"}:
        valve_markup = [
            line(left, cy, right, cy),
            polygon([(left + rect["width"] * 0.16, top + rect["height"] * 0.2), (left + rect["width"] * 0.16, top + rect["height"] * 0.8), (cx, cy)]),
        ]
        if symbol_type == "check_valve":
            valve_markup.extend(
                [
                    line(left + rect["width"] * 0.68, top + rect["height"] * 0.24, left + rect["width"] * 0.68, top + rect["height"] * 0.76),
                    path(f"M {_num(left + rect['width'] * 0.58)} {_num(top + rect['height'] * 0.32)} C {_num(left + rect['width'] * 0.7)} {_num(top + rect['height'] * 0.38)}, {_num(left + rect['width'] * 0.7)} {_num(top + rect['height'] * 0.62)}, {_num(left + rect['width'] * 0.58)} {_num(top + rect['height'] * 0.68)}"),
                ]
            )
        else:
            valve_markup.append(polygon([(left + rect["width"] * 0.84, top + rect["height"] * 0.2), (left + rect["width"] * 0.84, top + rect["height"] * 0.8), (cx, cy)]))
        if symbol_type == "gate_valve":
            valve_markup.extend([line(cx, cy, cx, top + rect["height"] * 0.12), line(cx - rect["width"] * 0.16, top + rect["height"] * 0.12, cx + rect["width"] * 0.16, top + rect["height"] * 0.12)])
        elif symbol_type == "control_valve":
            valve_markup.extend([line(cx, cy, cx, top + rect["height"] * 0.18), f'<circle {common} cx="{_num(cx)}" cy="{_num(top + rect["height"] * 0.1)}" r="{_num(min(rect["width"], rect["height"]) * 0.12)}"/>'])
        elif symbol_type == "relief_valve":
            valve_markup.extend([line(left + rect["width"] * 0.66, cy, left + rect["width"] * 0.66, top + rect["height"] * 0.18), path(f"M {_num(left + rect['width'] * 0.54)} {_num(top + rect['height'] * 0.24)} C {_num(left + rect['width'] * 0.62)} {_num(top + rect['height'] * 0.02)}, {_num(left + rect['width'] * 0.78)} {_num(top + rect['height'] * 0.02)}, {_num(left + rect['width'] * 0.86)} {_num(top + rect['height'] * 0.24)}")])
        return "\n".join(valve_markup)
    if symbol_type in {"pump", "centrifugal_pump"}:
        path = (
            f"M {_num(cx - radius * 0.45)} {_num(cy - radius * 0.34)} "
            f"C {_num(cx - radius * 0.1)} {_num(cy - radius * 0.55)}, {_num(cx + radius * 0.48)} {_num(cy - radius * 0.22)}, {_num(cx + radius * 0.48)} {_num(cy)} "
            f"C {_num(cx + radius * 0.48)} {_num(cy + radius * 0.22)}, {_num(cx - radius * 0.1)} {_num(cy + radius * 0.55)}, {_num(cx - radius * 0.45)} {_num(cy + radius * 0.34)}"
        )
        base = (
            f"M {_num(cx - radius * 0.7)} {_num(top + rect['height'] * 0.86)} "
            f"L {_num(cx + radius * 0.7)} {_num(top + rect['height'] * 0.86)} "
            f"L {_num(cx + radius * 0.95)} {_num(top + rect['height'] * 0.96)} "
            f"L {_num(cx - radius * 0.95)} {_num(top + rect['height'] * 0.96)} Z"
        )
        return "\n".join(
            [
                line(left, cy, cx - radius, cy),
                line(cx + radius, cy, right, cy),
                f'<circle {common} cx="{_num(cx)}" cy="{_num(cy)}" r="{_num(radius)}"/>',
                f'<path d="{_attr(path)}" fill="none" stroke="{_attr(stroke)}" stroke-width="{_num(stroke_width)}"/>',
                f'<path d="{_attr(f"M {_num(cx + radius * 0.72)} {_num(cy - radius * 0.34)} Q {_num(cx + radius * 1.25)} {_num(cy - radius * 0.2)}, {_num(cx + radius * 1.18)} {_num(cy + radius * 0.32)} Q {_num(cx + radius * 1.0)} {_num(cy + radius * 0.82)}, {_num(cx + radius * 0.52)} {_num(cy + radius * 0.68)}")}" fill="none" stroke="{_attr(stroke)}" stroke-width="{_num(stroke_width)}"/>' if symbol_type == "centrifugal_pump" else "",
                f'<path d="{_attr(base)}" fill="none" stroke="{_attr(stroke)}" stroke-width="{_num(stroke_width)}"/>',
            ]
        )
    if symbol_type == "compressor":
        body_r = min(rect["width"], rect["height"]) * 0.34
        body = f'<circle {common} cx="{_num(cx)}" cy="{_num(cy)}" r="{_num(body_r)}"/>'
        impeller = (
            f"M {_num(cx - body_r * 0.7)} {_num(cy + body_r * 0.46)} "
            f"L {_num(cx + body_r * 0.62)} {_num(cy)} "
            f"L {_num(cx - body_r * 0.7)} {_num(cy - body_r * 0.46)} Z"
        )
        crown = (
            f"M {_num(cx - body_r * 0.52)} {_num(cy - body_r * 0.9)} "
            f"C {_num(cx - body_r * 0.08)} {_num(cy - body_r * 1.28)}, {_num(cx + body_r * 0.62)} {_num(cy - body_r * 1.0)}, {_num(cx + body_r * 0.88)} {_num(cy - body_r * 0.48)}"
        )
        return "\n".join([line(left, cy, cx - body_r, cy), line(cx + body_r, cy, right, cy), body, path(impeller), path(crown), line(cx - body_r * 0.8, top + rect["height"] * 0.88, cx + body_r * 0.8, top + rect["height"] * 0.88)])
    if symbol_type in {"fan", "centrifugal_fan"}:
        fan_r = min(rect["width"], rect["height"]) * 0.34
        housing = path(f"M {_num(cx - fan_r * 0.9)} {_num(cy - fan_r * 0.65)} C {_num(cx - fan_r * 0.25)} {_num(cy - fan_r * 1.45)}, {_num(cx + fan_r * 1.1)} {_num(cy - fan_r * 1.05)}, {_num(cx + fan_r * 1.04)} {_num(cy)} C {_num(cx + fan_r * 0.96)} {_num(cy + fan_r * 1.1)}, {_num(cx - fan_r * 0.58)} {_num(cy + fan_r * 1.22)}, {_num(cx - fan_r * 0.86)} {_num(cy + fan_r * 0.44)}", fill) if symbol_type == "centrifugal_fan" else f'<circle {common} cx="{_num(cx)}" cy="{_num(cy)}" r="{_num(fan_r)}"/>'
        blades = [
            path(f"M {_num(cx)} {_num(cy)} Q {_num(cx + fan_r * 0.25)} {_num(cy - fan_r * 0.65)}, {_num(cx)} {_num(cy - fan_r)}"),
            path(f"M {_num(cx)} {_num(cy)} Q {_num(cx + fan_r * 0.75)} {_num(cy + fan_r * 0.2)}, {_num(cx + fan_r * 0.92)} {_num(cy - fan_r * 0.12)}"),
            path(f"M {_num(cx)} {_num(cy)} Q {_num(cx - fan_r * 0.72)} {_num(cy + fan_r * 0.28)}, {_num(cx - fan_r * 0.78)} {_num(cy + fan_r * 0.78)}"),
        ]
        return "\n".join([line(left, cy, cx - fan_r, cy), line(cx + fan_r, cy, right, cy), housing, *blades, f'<circle {common} cx="{_num(cx)}" cy="{_num(cy)}" r="{_num(max(2.4, fan_r * 0.12))}"/>'])
    if symbol_type == "cooling_tower":
        tower = (
            f"M {_num(left + rect['width'] * 0.28)} {_num(top + rect['height'] * 0.14)} "
            f"L {_num(left + rect['width'] * 0.72)} {_num(top + rect['height'] * 0.14)} "
            f"L {_num(left + rect['width'] * 0.82)} {_num(top + rect['height'] * 0.86)} "
            f"L {_num(left + rect['width'] * 0.18)} {_num(top + rect['height'] * 0.86)} Z"
        )
        crown = (
            f"M {_num(left + rect['width'] * 0.4)} {_num(top + rect['height'] * 0.14)} "
            f"C {_num(left + rect['width'] * 0.42)} {_num(top + rect['height'] * -0.02)}, {_num(left + rect['width'] * 0.58)} {_num(top + rect['height'] * -0.02)}, {_num(left + rect['width'] * 0.6)} {_num(top + rect['height'] * 0.14)}"
        )
        return "\n".join([line(left, cy, left + rect["width"] * 0.2, cy), line(left + rect["width"] * 0.8, cy, right, cy), path(tower, fill), line(left + rect["width"] * 0.3, top + rect["height"] * 0.4, left + rect["width"] * 0.7, top + rect["height"] * 0.4), line(left + rect["width"] * 0.26, top + rect["height"] * 0.66, left + rect["width"] * 0.74, top + rect["height"] * 0.66), path(crown)])
    if symbol_type == "skid":
        x = rect["x"] + rect["width"] * 0.18
        width = rect["width"] * 0.64
        y = top + rect["height"] * 0.22
        height = rect["height"] * 0.52
        return "\n".join([line(left, cy, x, cy), line(x + width, cy, right, cy), f'<rect {common} x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}"/>', line(x - rect["width"] * 0.06, top + rect["height"] * 0.88, x + width + rect["width"] * 0.06, top + rect["height"] * 0.88), line(x + width * 0.25, y, x + width * 0.25, y + height), line(x + width * 0.68, y, x + width * 0.68, y + height)])
    if symbol_type == "separator":
        x = rect["x"] + rect["width"] * 0.24
        width = rect["width"] * 0.52
        y = top + rect["height"] * 0.12
        height = rect["height"] * 0.76
        wave = f"M {_num(x + width * 0.18)} {_num(y + height * 0.66)} C {_num(x + width * 0.38)} {_num(y + height * 0.5)}, {_num(x + width * 0.58)} {_num(y + height * 0.82)}, {_num(x + width * 0.82)} {_num(y + height * 0.66)}"
        return "\n".join([line(left, cy, x, cy), line(x + width, cy, right, cy), f'<rect {common} x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}" rx="{_num(width * 0.3)}"/>', line(x + width * 0.18, y + height * 0.36, x + width * 0.82, y + height * 0.36), path(wave)])
    if symbol_type == "coil":
        x = rect["x"] + rect["width"] * 0.2
        width = rect["width"] * 0.6
        y = top + rect["height"] * 0.18
        height = rect["height"] * 0.64
        coil_path = f"M {_num(x + width * 0.16)} {_num(y + height * 0.88)} L {_num(x + width * 0.36)} {_num(y + height * 0.12)} L {_num(x + width * 0.56)} {_num(y + height * 0.88)} L {_num(x + width * 0.76)} {_num(y + height * 0.12)} L {_num(x + width * 0.92)} {_num(y + height * 0.88)}"
        return "\n".join([line(left, cy, x, cy), line(x + width, cy, right, cy), f'<rect {common} x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}"/>', path(coil_path)])
    if symbol_type in {"panel", "patch_panel", "control_panel", "computer_monitor", "lcd_monitor"}:
        x = rect["x"] + rect["width"] * 0.28
        width = rect["width"] * 0.44
        y = top + rect["height"] * 0.14
        height = rect["height"] * 0.72
        if symbol_type in {"computer_monitor", "lcd_monitor"}:
            monitor_y = top + rect["height"] * 0.18
            monitor_h = rect["height"] * 0.46
            return "\n".join([line(left, cy, x, cy), line(x + width, cy, right, cy), f'<rect {common} x="{_num(x)}" y="{_num(monitor_y)}" width="{_num(width)}" height="{_num(monitor_h)}" rx="4.0"/>', path(f"M {_num(cx - width * 0.12)} {_num(monitor_y + monitor_h)} L {_num(cx - width * 0.18)} {_num(bottom + rect['height'] * 0.18)} H {_num(cx + width * 0.18)} L {_num(cx + width * 0.12)} {_num(monitor_y + monitor_h)}"), line(cx - width * 0.26, bottom + rect["height"] * 0.18, cx + width * 0.26, bottom + rect["height"] * 0.18), line(x + width * 0.16, monitor_y + monitor_h * 0.82, x + width * 0.84, monitor_y + monitor_h * 0.82) if symbol_type == "lcd_monitor" else ""])
        detail_rows = [line(x + width * 0.18, y + height * row, x + width * 0.82, y + height * row) for row in ((0.2, 0.4, 0.6, 0.8) if symbol_type == "patch_panel" else (0.28, 0.5, 0.72))]
        status = f'<circle {common} cx="{_num(cx)}" cy="{_num(y + height * 0.14)}" r="{_num(min(width, height) * 0.08)}"/>' if symbol_type == "control_panel" else ""
        return "\n".join([line(left, cy, x, cy), line(x + width, cy, right, cy), f'<rect {common} x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}"/>', status, *detail_rows])
    if symbol_type in {"tank", "open_tank", "closed_tank", "covered_tank"}:
        x = rect["x"] + rect["width"] * 0.22
        width = rect["width"] * 0.56
        y = top + rect["height"] * 0.08
        height = rect["height"] * 0.84
        tank_top = f'<ellipse cx="{_num(cx)}" cy="{_num(top + rect["height"] * 0.22)}" rx="{_num(width * 0.45)}" ry="{_num(rect["height"] * 0.08)}" fill="none" stroke="{_attr(stroke)}" stroke-width="{_num(stroke_width)}"/>'
        open_lip = line(x + width * 0.18, top + rect["height"] * 0.16, x + width * 0.82, top + rect["height"] * 0.16) if symbol_type == "open_tank" else ""
        cover = path(f"M {_num(x + width * 0.12)} {_num(top + rect['height'] * 0.16)} C {_num(cx - width * 0.16)} {_num(top + rect['height'] * 0.02)}, {_num(cx + width * 0.16)} {_num(top + rect['height'] * 0.02)}, {_num(x + width * 0.88)} {_num(top + rect['height'] * 0.16)}") if symbol_type == "covered_tank" else ""
        return "\n".join(
            [
                line(left, cy, x, cy),
                line(x + width, cy, right, cy),
                f'<rect {common} x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}" rx="{_num(width * 0.28)}"/>',
                "" if symbol_type == "closed_tank" else tank_top,
                open_lip,
                cover,
                f'<ellipse cx="{_num(cx)}" cy="{_num(top + rect["height"] * 0.78)}" rx="{_num(width * 0.45)}" ry="{_num(rect["height"] * 0.08)}" fill="none" stroke="{_attr(stroke)}" stroke-width="{_num(stroke_width)}"/>',
            ]
        )
    if symbol_type == "vessel":
        x = rect["x"] + rect["width"] * 0.22
        width = rect["width"] * 0.56
        y = top + rect["height"] * 0.08
        height = rect["height"] * 0.84
        return "\n".join(
            [
                line(left, cy, x, cy),
                line(x + width, cy, right, cy),
                f'<rect {common} x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}" rx="{_num(width * 0.22)}"/>',
                line(cx, top, cx, y),
                line(cx, y + height, cx, bottom),
                line(x, cy, x + width, cy),
            ]
        )
    if symbol_type == "filter":
        x = rect["x"] + rect["width"] * 0.22
        width = rect["width"] * 0.56
        y = top + rect["height"] * 0.18
        height = rect["height"] * 0.64
        hatches = [
            line(x + width * (offset - 0.16), y + height * 0.9, x + width * (offset + 0.16), y + height * 0.1)
            for offset in (0.35, 0.5, 0.65)
        ]
        return "\n".join([line(left, cy, x, cy), line(x + width, cy, right, cy), f'<rect {common} x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}"/>', *hatches])
    if symbol_type in {"strainer", "y_strainer"}:
        x = rect["x"] + rect["width"] * 0.2
        width = rect["width"] * 0.64
        y = top + rect["height"] * 0.26
        height = rect["height"] * 0.44
        body = f"M {_num(x)} {_num(y)} L {_num(x + width * 0.78)} {_num(y)} L {_num(x + width)} {_num(cy)} L {_num(x + width * 0.78)} {_num(y + height)} L {_num(x)} {_num(y + height)} Z"
        return "\n".join(
            [
                line(left, cy, x, cy),
                line(x + width, cy, right, cy),
                path(body, fill),
                path(f"M {_num(x + width * 0.28)} {_num(y + height)} L {_num(x + width * (0.62 if symbol_type == 'y_strainer' else 0.54))} {_num(bottom + rect['height'] * 0.08)}"),
                line(x + width * 0.24, y + height * 0.82, x + width * 0.46, y + height * 0.18),
                line(x + width * 0.44, y + height * 0.9, x + width * 0.66, y + height * 0.2),
            ]
        )
    if symbol_type in {"reducer", "concentric_reducer", "eccentric_reducer"}:
        x = rect["x"] + rect["width"] * 0.16
        width = rect["width"] * 0.68
        if symbol_type == "eccentric_reducer":
            y = top + rect["height"] * 0.36
            height = rect["height"] * 0.28
            body = f"M {_num(x)} {_num(y)} L {_num(x + width * 0.52)} {_num(y)} L {_num(x + width)} {_num(cy)} L {_num(x + width * 0.52)} {_num(y + height)} L {_num(x)} {_num(y + height)} Z"
        else:
            y = top + rect["height"] * 0.28
            height = rect["height"] * 0.44
            body = f"M {_num(x)} {_num(y)} L {_num(x + width * 0.52)} {_num(y)} L {_num(x + width)} {_num(y + height * 0.28)} L {_num(x + width)} {_num(y + height * 0.72)} L {_num(x + width * 0.52)} {_num(y + height)} L {_num(x)} {_num(y + height)} Z"
        return "\n".join([line(left, cy, x, cy), line(x + width, cy, right, cy), path(body, fill), line(x + width * 0.52, y, x + width * 0.52, y + height)])

    if symbol_type == "heat_exchanger":
        x = rect["x"] + rect["width"] * 0.2
        width = rect["width"] * 0.6
        y = top + rect["height"] * 0.16
        height = rect["height"] * 0.68
        return "\n".join(
            [
                line(left, cy, x, cy),
                line(x + width, cy, right, cy),
                f'<rect {common} x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}" rx="{_num(height * 0.18)}"/>',
                line(x + width * 0.16, y + height * 0.26, x + width * 0.84, y + height * 0.26),
                line(x + width * 0.16, y + height * 0.5, x + width * 0.84, y + height * 0.5),
                line(x + width * 0.16, y + height * 0.74, x + width * 0.84, y + height * 0.74),
                line(x + width * 0.32, y, x + width * 0.32, y + height),
                line(x + width * 0.68, y, x + width * 0.68, y + height),
            ]
        )

    if symbol_type == "plate_heat_exchanger":
        x = rect["x"] + rect["width"] * 0.2
        width = rect["width"] * 0.6
        y = top + rect["height"] * 0.16
        height = rect["height"] * 0.68
        return "\n".join(
            [
                line(left, cy, x, cy),
                line(x + width, cy, right, cy),
                f'<rect {common} x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}" rx="{_num(height * 0.14)}"/>',
                path(f"M {_num(x + width * 0.2)} {_num(y + height * 0.1)} L {_num(x + width * 0.42)} {_num(y + height * 0.9)}"),
                path(f"M {_num(x + width * 0.42)} {_num(y + height * 0.1)} L {_num(x + width * 0.64)} {_num(y + height * 0.9)}"),
                path(f"M {_num(x + width * 0.64)} {_num(y + height * 0.1)} L {_num(x + width * 0.86)} {_num(y + height * 0.9)}"),
                line(x, y + height * 0.25, x + width, y + height * 0.25),
                line(x, y + height * 0.75, x + width, y + height * 0.75),
            ]
        )

    if symbol_type == "dashpot_piston":
        x = rect["x"] + rect["width"] * 0.24
        width = rect["width"] * 0.52
        y = top + rect["height"] * 0.28
        height = rect["height"] * 0.44
        return "\n".join([line(left, cy, x, cy), line(x + width, cy, right, cy), f'<rect {common} x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}" rx="{_num(height * 0.2)}"/>', line(cx, y, cx, y + height), line(x + width * 0.2, y + height * 0.32, cx, y + height * 0.32), line(cx, y + height * 0.68, x + width * 0.8, y + height * 0.68)])

    if symbol_type == "air_handler":
        x = rect["x"] + rect["width"] * 0.16
        width = rect["width"] * 0.68
        y = top + rect["height"] * 0.18
        height = rect["height"] * 0.64
        fan_r = min(width, height) * 0.18
        fan_x = x + width * 0.28
        coil_x = x + width * 0.58
        return "\n".join(
            [
                line(left, cy, x, cy),
                line(x + width, cy, right, cy),
                f'<rect {common} x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}"/>',
                f'<circle cx="{_num(fan_x)}" cy="{_num(cy)}" r="{_num(fan_r)}" fill="none" stroke="{_attr(stroke)}" stroke-width="{_num(stroke_width)}" opacity="{_scalar(opacity)}"/>',
                f'<path d="{_attr(f"M {_num(fan_x - fan_r * 0.7)} {_num(cy)} C {_num(fan_x - fan_r * 0.25)} {_num(cy - fan_r * 0.8)}, {_num(fan_x + fan_r * 0.6)} {_num(cy - fan_r * 0.3)}, {_num(fan_x + fan_r * 0.55)} {_num(cy + fan_r * 0.45)}")}" fill="none" stroke="{_attr(stroke)}" stroke-width="{_num(stroke_width)}"/>',
                line(coil_x, y + height * 0.18, coil_x + width * 0.22, y + height * 0.82),
                line(coil_x + width * 0.1, y + height * 0.18, coil_x + width * 0.32, y + height * 0.82),
            ]
        )

    if symbol_type == "terminal_unit":
        x = rect["x"] + rect["width"] * 0.2
        width = rect["width"] * 0.6
        y = top + rect["height"] * 0.24
        height = rect["height"] * 0.52
        return "\n".join(
            [
                line(left, cy, x, cy),
                line(x + width, cy, right, cy),
                f'<rect {common} x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}"/>',
                line(x + width * 0.18, y + height * 0.26, x + width * 0.82, y + height * 0.26),
                line(x + width * 0.18, y + height * 0.5, x + width * 0.82, y + height * 0.5),
                line(x + width * 0.18, y + height * 0.74, x + width * 0.82, y + height * 0.74),
            ]
        )

    if symbol_type == "drive":
        x = rect["x"] + rect["width"] * 0.24
        width = rect["width"] * 0.52
        y = top + rect["height"] * 0.2
        height = rect["height"] * 0.6
        return "\n".join(
            [
                line(left, cy, x, cy),
                line(x + width, cy, right, cy),
                f'<rect {common} x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}"/>',
                f'<path d="{_attr(f"M {_num(x + width * 0.14)} {_num(cy)} L {_num(x + width * 0.28)} {_num(y + height * 0.28)} L {_num(x + width * 0.45)} {_num(y + height * 0.72)} L {_num(x + width * 0.62)} {_num(y + height * 0.28)} L {_num(x + width * 0.84)} {_num(cy)}")}" fill="none" stroke="{_attr(stroke)}" stroke-width="{_num(stroke_width)}"/>',
            ]
        )
    if symbol_type == "motor":
        motor_r = min(rect["width"], rect["height"]) * 0.32
        motor_path = f"M {_num(cx - motor_r * 0.58)} {_num(cy + motor_r * 0.5)} L {_num(cx - motor_r * 0.58)} {_num(cy - motor_r * 0.5)} L {_num(cx)} {_num(cy + motor_r * 0.18)} L {_num(cx + motor_r * 0.58)} {_num(cy - motor_r * 0.5)} L {_num(cx + motor_r * 0.58)} {_num(cy + motor_r * 0.5)}"
        return "\n".join(
            [
                line(left, cy, cx - motor_r, cy),
                line(cx + motor_r, cy, right, cy),
                f'<circle {common} cx="{_num(cx)}" cy="{_num(cy)}" r="{_num(motor_r)}"/>',
                path(motor_path),
                line(cx - motor_r * 0.72, bottom + rect["height"] * 0.16, cx + motor_r * 0.72, bottom + rect["height"] * 0.16),
            ]
        )

    if symbol_type in {"chiller", "boiler", "dryer"}:
        x = rect["x"] + rect["width"] * 0.16
        width = rect["width"] * 0.68
        y = top + rect["height"] * 0.18
        height = rect["height"] * 0.64
        if symbol_type == "dryer":
            vessel_w = rect["width"] * 0.24
            left_x = rect["x"] + rect["width"] * 0.25
            right_x = rect["x"] + rect["width"] * 0.51
            vessel_y = top + rect["height"] * 0.12
            vessel_h = rect["height"] * 0.76
            return "\n".join(
                [
                    line(left, cy, left_x, cy),
                    line(right_x + vessel_w, cy, right, cy),
                    line(left_x + vessel_w, cy, right_x, cy),
                    f'<rect {common} x="{_num(left_x)}" y="{_num(vessel_y)}" width="{_num(vessel_w)}" height="{_num(vessel_h)}" rx="{_num(vessel_w * 0.35)}"/>',
                    f'<rect {common} x="{_num(right_x)}" y="{_num(vessel_y)}" width="{_num(vessel_w)}" height="{_num(vessel_h)}" rx="{_num(vessel_w * 0.35)}"/>',
                    line(left_x + vessel_w * 0.2, vessel_y + vessel_h * 0.5, left_x + vessel_w * 0.8, vessel_y + vessel_h * 0.5),
                    line(right_x + vessel_w * 0.2, vessel_y + vessel_h * 0.5, right_x + vessel_w * 0.8, vessel_y + vessel_h * 0.5),
                ]
            )
        body = f'<rect {common} x="{_num(x)}" y="{_num(y)}" width="{_num(width)}" height="{_num(height)}" rx="4.0"/>'
        internals = [line(left, cy, x, cy), line(x + width, cy, right, cy), body]
        if symbol_type == "chiller":
            internals.extend(
                [
                    line(x + width * 0.18, y + height * 0.32, x + width * 0.82, y + height * 0.32),
                    line(x + width * 0.18, y + height * 0.68, x + width * 0.82, y + height * 0.68),
                    f'<path d="{_attr(f"M {_num(x + width * 0.24)} {_num(y + height * 0.18)} C {_num(x + width * 0.36)} {_num(y + height * 0.45)}, {_num(x + width * 0.64)} {_num(y + height * 0.55)}, {_num(x + width * 0.76)} {_num(y + height * 0.82)}")}" fill="none" stroke="{_attr(stroke)}" stroke-width="{_num(stroke_width)}"/>',
                ]
            )
        else:
            internals.append(
                f'<path d="{_attr(f"M {_num(x + width * 0.26)} {_num(y + height * 0.72)} C {_num(x + width * 0.2)} {_num(y + height * 0.45)}, {_num(x + width * 0.43)} {_num(y + height * 0.44)}, {_num(x + width * 0.42)} {_num(y + height * 0.22)} C {_num(x + width * 0.62)} {_num(y + height * 0.45)}, {_num(x + width * 0.78)} {_num(y + height * 0.55)}, {_num(x + width * 0.7)} {_num(y + height * 0.74)}")}" fill="none" stroke="{_attr(stroke)}" stroke-width="{_num(stroke_width)}"/>'
            )
        return "\n".join(internals)

    body_x = rect["x"] + rect["width"] * 0.18
    body_width = rect["width"] * 0.64
    return (
        "\n".join(
            [
                line(left, cy, body_x, cy),
                line(body_x + body_width, cy, right, cy),
                f'<rect {common} x="{_num(body_x)}" y="{_num(top + rect["height"] * 0.18)}" width="{_num(body_width)}" height="{_num(rect["height"] * 0.64)}" rx="4.0"/>',
                line(body_x, cy, body_x + body_width, cy),
            ]
        )
    )


def _svg_symbol_label(obj: dict[str, Any], text: str, rect: dict[str, float]) -> str:
    fill = _text_fill(obj)
    font_size = _style_font_size(obj, 10.0)
    font_family = _clean_text(_style_str(obj, "fontFamily", "Arial"))
    return (
        f'<text data-id="{_attr(str(obj.get("id") or ""))}" x="{_num(rect["x"] + rect["width"] / 2.0)}" '
        f'y="{_num(rect["y"] + rect["height"] + font_size + 2.0)}" text-anchor="middle" '
        f'fill="{_attr(fill)}" font-family="{_attr(font_family)}" font-size="{_num(font_size)}">'
        f"{_text(text)}</text>"
    )


def _svg_polyline(obj: dict[str, Any], points: list[dict[str, float]], kind: str) -> str:
    stroke = _style_color(obj, "stroke", "#111827")
    opacity = _style_opacity(obj, 1.0)
    stroke_width = _style_stroke_width(obj, 2.0)
    dash = _dash_value(obj, "")
    dash_attr = f' stroke-dasharray="{_attr(dash)}"' if dash else ""
    arrow_start = _metadata_bool(obj, "arrowStart")
    arrow_end = _metadata_bool(obj, "arrowEnd")
    arrow_length = max(9.0, stroke_width * 4.8)
    line_points = _trim_points_for_arrowheads(points, arrow_start, arrow_end, arrow_length)
    point_values = " ".join(f'{_num(point["x"])},{_num(point["y"])}' for point in line_points)
    line = (
        f'<polyline data-kind="{_attr(kind)}" data-id="{_attr(str(obj.get("id") or ""))}" '
        f'points="{_attr(point_values)}" fill="none" stroke="{_attr(stroke)}" '
        f'stroke-width="{_num(stroke_width)}" opacity="{_scalar(opacity)}"{dash_attr}/>'
    )
    arrows = []
    if arrow_start:
        arrows.append(_svg_arrowhead(points, "start", stroke, stroke_width, opacity))
    if arrow_end:
        arrows.append(_svg_arrowhead(points, "end", stroke, stroke_width, opacity))
    return "\n".join([line, *[arrow for arrow in arrows if arrow]])


def _svg_arrowhead(points: list[dict[str, float]], at: str, stroke: str, stroke_width: float, opacity: float) -> str:
    arrow = _arrowhead_points(points, at, max(9.0, stroke_width * 4.8), max(7.0, stroke_width * 3.4))
    if not arrow:
        return ""
    point_values = " ".join(f'{_num(point["x"])},{_num(point["y"])}' for point in arrow)
    return (
        f'<polygon points="{_attr(point_values)}" fill="{_attr(stroke)}" stroke="{_attr(stroke)}" '
        f'stroke-width="{_num(max(0.8, stroke_width * 0.35))}" opacity="{_scalar(opacity)}"/>'
    )


def _svg_text(obj: dict[str, Any], text: str, x: float, y: float) -> str:
    fill = _text_fill(obj)
    font_size = _style_font_size(obj, 12.0)
    font_family = _clean_text(_style_str(obj, "fontFamily", "Arial"))
    transform = _svg_text_transform(obj, x, y)
    lines = _wrapped_text_lines(obj, text, font_size)
    if len(lines) > 1:
        tspans = []
        line_height = font_size * 1.18
        for index, line in enumerate(lines):
            dy_attr = "" if index == 0 else f' dy="{_num(line_height)}"'
            tspans.append(f'<tspan x="{_num(x)}"{dy_attr}>{_text(line)}</tspan>')
        return (
            f'<text data-id="{_attr(str(obj.get("id") or ""))}" x="{_num(x)}" y="{_num(y)}" '
            f'fill="{_attr(fill)}" font-family="{_attr(font_family)}" font-size="{_num(font_size)}"{transform}>'
            f"{''.join(tspans)}</text>"
        )
    return (
        f'<text data-id="{_attr(str(obj.get("id") or ""))}" x="{_num(x)}" y="{_num(y)}" '
        f'fill="{_attr(fill)}" font-family="{_attr(font_family)}" font-size="{_num(font_size)}"{transform}>'
        f"{_text(text)}</text>"
    )


def _svg_text_transform(obj: dict[str, Any], x: float, y: float) -> str:
    rotation = (obj.get("metadata") or {}).get("rotationDegrees")
    if not isinstance(rotation, (int, float)) or abs(float(rotation)) < 0.5:
        return ""
    return f' transform="rotate({_num(float(rotation))} {_num(x)} {_num(y)})"'


def _pdf_rect(c: Any, obj: dict[str, Any], rect: dict[str, float], kind: str, page_height: float) -> None:
    image_drawn = _pdf_source_image(c, obj, rect, page_height) if kind == "source_fragment" else False
    opacity = _style_opacity(obj, 0.18 if kind == "source_fragment" else 0.35)
    stroke = _style_color(obj, "stroke", "#94a3b8" if kind == "source_fragment" else "#2563eb")
    fill = "none" if image_drawn else _style_color(obj, "fill", "#f8fafc" if kind == "source_fragment" else "#dbeafe")
    stroke_width = _style_stroke_width(obj, 1.0)
    dash = _dash_numbers(obj, [6.0, 4.0] if kind == "source_fragment" else [])
    y = page_height - rect["y"] - rect["height"]

    c.saveState()
    _set_alpha(c, opacity)
    _set_fill(c, fill)
    _set_stroke(c, stroke)
    c.setLineWidth(stroke_width)
    if dash:
        c.setDash(dash)
    c.rect(
        rect["x"],
        y,
        rect["width"],
        rect["height"],
        fill=1 if fill.lower() != "none" else 0,
        stroke=1 if stroke.lower() != "none" else 0,
    )
    c.restoreState()


def _pdf_symbol(c: Any, obj: dict[str, Any], rect: dict[str, float], page_height: float) -> None:
    stroke = _style_color(obj, "stroke", "#334155")
    fill = _style_color(obj, "fill", "#ffffff")
    opacity = _style_opacity(obj, 1.0)
    stroke_width = _style_stroke_width(obj, 1.5)
    symbol_type = _symbol_type(obj)
    orientation = _symbol_orientation(obj)
    x = rect["x"]
    y = page_height - rect["y"] - rect["height"]
    cx = x + rect["width"] / 2.0
    cy = y + rect["height"] / 2.0
    radius = max(8.0, min(rect["width"] * 0.22, rect["height"] * 0.34))
    left = x
    right = x + rect["width"]
    top = y + rect["height"]
    bottom = y

    def line(x1: float, y1: float, x2: float, y2: float) -> None:
        c.line(x1, y1, x2, y2)

    def polygon(points: list[tuple[float, float]], fill_shape: int = 1) -> None:
        path = c.beginPath()
        first_x, first_y = points[0]
        path.moveTo(first_x, first_y)
        for point_x, point_y in points[1:]:
            path.lineTo(point_x, point_y)
        path.close()
        c.drawPath(path, stroke=1, fill=fill_shape)

    c.saveState()
    _set_alpha(c, opacity)
    _set_fill(c, fill)
    _set_stroke(c, stroke)
    c.setLineWidth(stroke_width)
    if symbol_type == "flow_arrow":
        _set_fill(c, stroke)
        if orientation == "left":
            polygon([(right, top), (left, cy), (right, bottom)])
        else:
            polygon([(left, top), (right, cy), (left, bottom)])
    elif symbol_type == "offpage":
        if orientation == "left":
            polygon([(right, top), (left + rect["width"] * 0.22, top), (left, cy), (left + rect["width"] * 0.22, bottom), (right, bottom)])
        else:
            polygon([(left, top), (left + rect["width"] * 0.78, top), (right, cy), (left + rect["width"] * 0.78, bottom), (left, bottom)])
    elif symbol_type == "instrument":
        r = min(rect["width"], rect["height"]) * 0.42
        line(cx, cy - r, cx, bottom)
        c.circle(cx, cy, r, fill=1, stroke=1)
        line(cx - r * 0.48, cy, cx + r * 0.48, cy)
        line(cx, cy - r * 0.48, cx, cy + r * 0.48)
    elif symbol_type == "valve":
        if orientation == "vertical":
            line(cx, top, cx, bottom)
            polygon([(x + rect["width"] * 0.2, top - rect["height"] * 0.18), (x + rect["width"] * 0.8, top - rect["height"] * 0.18), (cx, cy)])
            polygon([(x + rect["width"] * 0.2, bottom + rect["height"] * 0.18), (x + rect["width"] * 0.8, bottom + rect["height"] * 0.18), (cx, cy)])
            line(x + rect["width"] * 0.2, top - rect["height"] * 0.18, x + rect["width"] * 0.8, top - rect["height"] * 0.18)
        else:
            line(left, cy, right, cy)
            polygon([(x + rect["width"] * 0.16, bottom + rect["height"] * 0.2), (x + rect["width"] * 0.16, top - rect["height"] * 0.2), (cx, cy)])
            polygon([(x + rect["width"] * 0.84, bottom + rect["height"] * 0.2), (x + rect["width"] * 0.84, top - rect["height"] * 0.2), (cx, cy)])
            line(x + rect["width"] * 0.84, bottom + rect["height"] * 0.2, x + rect["width"] * 0.84, top - rect["height"] * 0.2)
    elif symbol_type == "pump":
        line(left, cy, cx - radius, cy)
        line(cx + radius, cy, right, cy)
        c.circle(cx, cy, radius, fill=1, stroke=1)
        path = c.beginPath()
        path.moveTo(cx - radius * 0.45, cy + radius * 0.34)
        path.curveTo(cx - radius * 0.1, cy + radius * 0.55, cx + radius * 0.48, cy + radius * 0.22, cx + radius * 0.48, cy)
        path.curveTo(cx + radius * 0.48, cy - radius * 0.22, cx - radius * 0.1, cy - radius * 0.55, cx - radius * 0.45, cy - radius * 0.34)
        c.drawPath(path, stroke=1, fill=0)
        base = c.beginPath()
        base.moveTo(cx - radius * 0.7, bottom + rect["height"] * 0.14)
        base.lineTo(cx + radius * 0.7, bottom + rect["height"] * 0.14)
        base.lineTo(cx + radius * 0.95, bottom + rect["height"] * 0.04)
        base.lineTo(cx - radius * 0.95, bottom + rect["height"] * 0.04)
        base.close()
        c.drawPath(base, stroke=1, fill=0)
    elif symbol_type == "tank":
        tank_x = x + rect["width"] * 0.22
        tank_w = rect["width"] * 0.56
        tank_y = y + rect["height"] * 0.08
        tank_h = rect["height"] * 0.84
        line(left, cy, tank_x, cy)
        line(tank_x + tank_w, cy, right, cy)
        c.roundRect(tank_x, tank_y, tank_w, tank_h, tank_w * 0.28, fill=1, stroke=1)
        c.ellipse(tank_x + tank_w * 0.05, bottom + rect["height"] * 0.70, tank_x + tank_w * 0.95, bottom + rect["height"] * 0.86, fill=0, stroke=1)
        c.ellipse(tank_x + tank_w * 0.05, bottom + rect["height"] * 0.14, tank_x + tank_w * 0.95, bottom + rect["height"] * 0.30, fill=0, stroke=1)
    elif symbol_type == "filter":
        core_x = x + rect["width"] * 0.22
        core_w = rect["width"] * 0.56
        core_y = y + rect["height"] * 0.18
        core_h = rect["height"] * 0.64
        line(left, cy, core_x, cy)
        line(core_x + core_w, cy, right, cy)
        c.rect(core_x, core_y, core_w, core_h, fill=1, stroke=1)
        for offset in (0.35, 0.5, 0.65):
            line(core_x + core_w * (offset - 0.16), core_y + core_h * 0.1, core_x + core_w * (offset + 0.16), core_y + core_h * 0.9)
    elif symbol_type == "dryer":
        vessel_w = rect["width"] * 0.24
        left_x = x + rect["width"] * 0.25
        right_x = x + rect["width"] * 0.51
        vessel_y = y + rect["height"] * 0.12
        vessel_h = rect["height"] * 0.76
        line(left, cy, left_x, cy)
        line(right_x + vessel_w, cy, right, cy)
        line(left_x + vessel_w, cy, right_x, cy)
        for vessel_x in (left_x, right_x):
            c.roundRect(vessel_x, vessel_y, vessel_w, vessel_h, vessel_w * 0.35, fill=1, stroke=1)
            line(vessel_x + vessel_w * 0.2, vessel_y + vessel_h * 0.5, vessel_x + vessel_w * 0.8, vessel_y + vessel_h * 0.5)
    elif symbol_type in {"chiller", "boiler"}:
        body_x = x + rect["width"] * 0.16
        body_w = rect["width"] * 0.68
        body_y = y + rect["height"] * 0.18
        body_h = rect["height"] * 0.64
        line(left, cy, body_x, cy)
        line(body_x + body_w, cy, right, cy)
        c.roundRect(body_x, body_y, body_w, body_h, 4.0, fill=1, stroke=1)
        if symbol_type == "chiller":
            line(body_x + body_w * 0.18, body_y + body_h * 0.68, body_x + body_w * 0.82, body_y + body_h * 0.68)
            line(body_x + body_w * 0.18, body_y + body_h * 0.32, body_x + body_w * 0.82, body_y + body_h * 0.32)
            path = c.beginPath()
            path.moveTo(body_x + body_w * 0.24, body_y + body_h * 0.82)
            path.curveTo(body_x + body_w * 0.36, body_y + body_h * 0.55, body_x + body_w * 0.64, body_y + body_h * 0.45, body_x + body_w * 0.76, body_y + body_h * 0.18)
            c.drawPath(path, stroke=1, fill=0)
        else:
            path = c.beginPath()
            path.moveTo(body_x + body_w * 0.26, body_y + body_h * 0.28)
            path.curveTo(body_x + body_w * 0.2, body_y + body_h * 0.55, body_x + body_w * 0.43, body_y + body_h * 0.56, body_x + body_w * 0.42, body_y + body_h * 0.78)
            path.curveTo(body_x + body_w * 0.62, body_y + body_h * 0.55, body_x + body_w * 0.78, body_y + body_h * 0.45, body_x + body_w * 0.7, body_y + body_h * 0.26)
            c.drawPath(path, stroke=1, fill=0)
    else:
        body_x = x + rect["width"] * 0.18
        body_w = rect["width"] * 0.64
        body_y = y + rect["height"] * 0.18
        body_h = rect["height"] * 0.64
        line(left, cy, body_x, cy)
        line(body_x + body_w, cy, right, cy)
        c.roundRect(body_x, body_y, body_w, body_h, 4.0, fill=1, stroke=1)
        line(body_x, cy, body_x + body_w, cy)
    c.restoreState()


def _pdf_symbol_label(c: Any, obj: dict[str, Any], text: str, rect: dict[str, float], page_height: float) -> None:
    fill = _text_fill(obj)
    font_size = _style_font_size(obj, 10.0)
    c.saveState()
    _set_fill(c, fill)
    c.setFont("Helvetica", font_size)
    clean = _clean_text(text)
    width = c.stringWidth(clean, "Helvetica", font_size)
    c.drawString(rect["x"] + rect["width"] / 2.0 - width / 2.0, page_height - (rect["y"] + rect["height"] + font_size + 2.0), clean)
    c.restoreState()


def _svg_source_image(obj: dict[str, Any], rect: dict[str, float]) -> str:
    png = _source_fragment_png(obj, rect)
    if png is None:
        return ""
    encoded = base64.b64encode(png).decode("ascii")
    return (
        f'<image data-kind="source_image" data-id="{_attr(str(obj.get("id") or ""))}" '
        f'x="{_num(rect["x"])}" y="{_num(rect["y"])}" width="{_num(rect["width"])}" height="{_num(rect["height"])}" '
        f'preserveAspectRatio="none" href="data:image/png;base64,{encoded}"/>'
    )


def _pdf_source_image(c: Any, obj: dict[str, Any], rect: dict[str, float], page_height: float) -> bool:
    png = _source_fragment_png(obj, rect)
    if png is None:
        return False
    try:
        from reportlab.lib.utils import ImageReader

        reader = ImageReader(io.BytesIO(png))
        c.drawImage(
            reader,
            rect["x"],
            page_height - rect["y"] - rect["height"],
            width=rect["width"],
            height=rect["height"],
            preserveAspectRatio=False,
            mask="auto",
        )
    except Exception:
        return False
    return True


def _source_fragment_png(obj: dict[str, Any], rect: dict[str, float]) -> bytes | None:
    metadata = obj.get("metadata")
    if not isinstance(metadata, dict):
        return None
    source_path = metadata.get("sourcePath")
    if not isinstance(source_path, str) or not source_path:
        return None
    path = Path(source_path)
    if not path.exists():
        return None
    try:
        import fitz

        page_number = max(1, int(_float(metadata.get("page"), 1.0)))
        doc = fitz.open(path)
        try:
            if page_number > len(doc):
                return None
            page = doc[page_number - 1]
            crop = _metadata_crop(metadata)
            clip = None
            clip_width = float(page.rect.width)
            if crop is not None:
                clip = fitz.Rect(crop["x"], crop["y"], crop["x"] + crop["width"], crop["y"] + crop["height"])
                clip_width = max(1.0, crop["width"])
            target_pixels = _clamp(rect["width"] * 1.6, 360.0, 1800.0)
            zoom = _clamp(target_pixels / max(1.0, clip_width), 0.18, 2.0)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, alpha=False)
            return pixmap.tobytes("png")
        finally:
            doc.close()
    except Exception:
        return None


def _metadata_crop(metadata: dict[str, Any]) -> dict[str, float] | None:
    crop = metadata.get("cropBounds")
    if not isinstance(crop, dict):
        return None
    x = _finite_float(crop.get("x"))
    y = _finite_float(crop.get("y"))
    width = _finite_float(crop.get("width"))
    height = _finite_float(crop.get("height"))
    if x is None or y is None or width is None or height is None or width <= 0 or height <= 0:
        return None
    return {"x": x, "y": y, "width": width, "height": height}


def _pdf_polyline(c: Any, obj: dict[str, Any], points: list[dict[str, float]], kind: str, page_height: float) -> None:
    stroke = _style_color(obj, "stroke", "#111827")
    opacity = _style_opacity(obj, 1.0)
    stroke_width = _style_stroke_width(obj, 2.0)
    dash = _dash_numbers(obj, [])
    if stroke.lower() == "none":
        return

    c.saveState()
    _set_alpha(c, opacity)
    _set_stroke(c, stroke)
    c.setLineWidth(stroke_width)
    if dash:
        c.setDash(dash)
    path = c.beginPath()
    arrow_start = _metadata_bool(obj, "arrowStart")
    arrow_end = _metadata_bool(obj, "arrowEnd")
    line_points = _trim_points_for_arrowheads(points, arrow_start, arrow_end, max(9.0, stroke_width * 4.8))
    first = line_points[0]
    path.moveTo(first["x"], page_height - first["y"])
    for point in line_points[1:]:
        path.lineTo(point["x"], page_height - point["y"])
    c.drawPath(path, stroke=1, fill=0)
    if arrow_start:
        _pdf_arrowhead(c, points, "start", stroke, stroke_width, page_height)
    if arrow_end:
        _pdf_arrowhead(c, points, "end", stroke, stroke_width, page_height)
    c.restoreState()


def _pdf_arrowhead(c: Any, points: list[dict[str, float]], at: str, stroke: str, stroke_width: float, page_height: float) -> None:
    arrow = _arrowhead_points(points, at, max(9.0, stroke_width * 4.8), max(7.0, stroke_width * 3.4))
    if not arrow:
        return
    _set_fill(c, stroke)
    path = c.beginPath()
    first = arrow[0]
    path.moveTo(first["x"], page_height - first["y"])
    for point in arrow[1:]:
        path.lineTo(point["x"], page_height - point["y"])
    path.close()
    c.drawPath(path, stroke=1, fill=1)


def _pdf_text(c: Any, obj: dict[str, Any], text: str, x: float, y: float, page_height: float) -> None:
    fill = _text_fill(obj)
    font_size = _style_font_size(obj, 12.0)
    lines = _wrapped_text_lines(obj, text, font_size)
    c.saveState()
    _set_fill(c, fill)
    c.setFont("Helvetica", font_size)
    line_height = font_size * 1.18
    for index, line in enumerate(lines):
        c.drawString(x, page_height - y - index * line_height, _clean_text(line))
    c.restoreState()


def _set_alpha(c: Any, alpha: float) -> None:
    if hasattr(c, "setFillAlpha"):
        c.setFillAlpha(alpha)
    if hasattr(c, "setStrokeAlpha"):
        c.setStrokeAlpha(alpha)


def _set_fill(c: Any, color: str) -> None:
    if color.lower() == "none":
        return
    c.setFillColor(_pdf_color(color))


def _set_stroke(c: Any, color: str) -> None:
    if color.lower() == "none":
        return
    c.setStrokeColor(_pdf_color(color))


def _pdf_color(color: str) -> Any:
    from reportlab.lib import colors

    if _HEX_COLOR_RE.fullmatch(color):
        try:
            return colors.HexColor(color)
        except Exception:
            return colors.black
    return getattr(colors, color.lower(), colors.black)


def _midpoint(points: list[dict[str, float]]) -> dict[str, float]:
    index = len(points) // 2
    if len(points) % 2:
        return points[index]
    first = points[index - 1]
    second = points[index]
    return {"x": (first["x"] + second["x"]) / 2.0, "y": (first["y"] + second["y"]) / 2.0}


def _symbol_type(obj: dict[str, Any]) -> str:
    metadata = obj.get("metadata")
    if isinstance(metadata, dict):
        symbol_type = metadata.get("symbolType")
        if isinstance(symbol_type, str) and symbol_type:
            return symbol_type
    return "equipment"


def _symbol_orientation(obj: dict[str, Any]) -> str:
    metadata = obj.get("metadata")
    if isinstance(metadata, dict):
        orientation = metadata.get("orientation")
        if isinstance(orientation, str) and orientation:
            return orientation
    return "right"


def _style(obj: dict[str, Any]) -> dict[str, Any]:
    style = obj.get("style")
    return style if isinstance(style, dict) else {}


def _style_str(obj: dict[str, Any], key: str, default: str) -> str:
    value = _style(obj).get(key, default)
    if value is None:
        return default
    return str(value)


def _style_float(obj: dict[str, Any], key: str, default: float) -> float:
    return _float(_style(obj).get(key), default)


def _style_opacity(obj: dict[str, Any], default: float) -> float:
    return _clamp(_style_float(obj, "opacity", default), 0.0, 1.0)


def _style_stroke_width(obj: dict[str, Any], default: float) -> float:
    return _clamp(_style_float(obj, "strokeWidth", default), 0.1, 20.0)


def _style_font_size(obj: dict[str, Any], default: float) -> float:
    return _clamp(_style_float(obj, "fontSize", default), 4.0, 72.0)


def _style_color(obj: dict[str, Any], key: str, default: str) -> str:
    value = _clean_text(_style_str(obj, key, default)).strip()
    if value.lower() == "none":
        return value
    if value.startswith("#") and not _HEX_COLOR_RE.fullmatch(value):
        return default
    return value or default


def _text_fill(obj: dict[str, Any]) -> str:
    style = _style(obj)
    fill = _clean_text(str(style.get("fill") or "")).lower()
    stroke = _clean_text(str(style.get("stroke") or "")).lower()
    if fill and fill not in {"none", "#fff", "#ffffff", "white"}:
        return _style_color(obj, "fill", "#111827")
    if stroke and stroke != "none":
        return _style_color(obj, "stroke", "#111827")
    return "#111827"


def _dash_value(obj: dict[str, Any], default: str) -> str:
    dash = _style(obj).get("dash")
    if dash is None:
        return _dash_string(default)
    return _dash_string(dash)


def _dash_numbers(obj: dict[str, Any], default: list[float]) -> list[float]:
    dash = _style(obj).get("dash")
    if dash is None:
        return _positive_finite_numbers(default)
    return _positive_finite_numbers(dash)


def _metadata_bool(obj: dict[str, Any], key: str) -> bool:
    metadata = obj.get("metadata")
    return isinstance(metadata, dict) and metadata.get(key) is True


def _wrapped_text_lines(obj: dict[str, Any], text: str, font_size: float) -> list[str]:
    clean = " ".join(_clean_text(text).split())
    if not clean:
        return []
    rect = _rect_from_object(obj)
    if rect is None:
        return [clean]
    max_chars = max(4, int(max(1.0, rect["width"] - 4.0) / max(1.0, font_size * 0.54)))
    if not _metadata_bool(obj, "textWrap") and len(clean) <= max_chars:
        return [clean]
    words = clean.split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(word) > max_chars:
            if current:
                lines.append(current)
                current = ""
            for start in range(0, len(word), max_chars):
                lines.append(word[start : start + max_chars])
            continue
        proposed = word if not current else f"{current} {word}"
        if len(proposed) <= max_chars:
            current = proposed
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    max_lines = max(1, int(max(rect["height"], font_size * 1.4) / max(font_size * 1.18, 1.0)))
    return lines[:max_lines] or [clean]


def _trim_points_for_arrowheads(
    points: list[dict[str, float]],
    trim_start: bool,
    trim_end: bool,
    length: float,
) -> list[dict[str, float]]:
    if len(points) < 2 or length <= 0:
        return points
    trimmed = [{"x": point["x"], "y": point["y"]} for point in points]
    if trim_start:
        trimmed[0] = _point_moved_toward(trimmed[0], trimmed[1], length)
    if trim_end:
        trimmed[-1] = _point_moved_toward(trimmed[-1], trimmed[-2], length)
    return trimmed


def _point_moved_toward(point: dict[str, float], neighbor: dict[str, float], distance: float) -> dict[str, float]:
    dx = neighbor["x"] - point["x"]
    dy = neighbor["y"] - point["y"]
    magnitude = math.hypot(dx, dy)
    if magnitude <= distance or magnitude < 0.01:
        return point
    return {"x": point["x"] + (dx / magnitude) * distance, "y": point["y"] + (dy / magnitude) * distance}


def _arrowhead_points(
    points: list[dict[str, float]],
    at: str,
    length: float,
    width: float,
) -> list[dict[str, float]]:
    if len(points) < 2:
        return []
    tip = points[-1] if at == "end" else points[0]
    neighbor = points[-2] if at == "end" else points[1]
    dx = tip["x"] - neighbor["x"]
    dy = tip["y"] - neighbor["y"]
    magnitude = math.hypot(dx, dy)
    if magnitude < 0.01:
        return []
    ux = dx / magnitude
    uy = dy / magnitude
    base = {"x": tip["x"] - ux * length, "y": tip["y"] - uy * length}
    px = -uy * (width / 2.0)
    py = ux * (width / 2.0)
    return [tip, {"x": base["x"] + px, "y": base["y"] + py}, {"x": base["x"] - px, "y": base["y"] - py}]


def _dash_string(value: Any) -> str:
    numbers = _positive_finite_numbers(value)
    return " ".join(_dash_num(item) for item in numbers)


def _positive_finite_numbers(value: Any) -> list[float]:
    if value in (None, ""):
        return []
    raw_values = value if isinstance(value, (list, tuple)) else str(value).replace(",", " ").split()
    numbers: list[float] = []
    for raw in raw_values:
        number = _finite_float(raw)
        if number is None or number <= 0:
            return []
        numbers.append(number)
    return numbers


def _float(value: Any, default: float) -> float:
    number = _finite_float(value)
    return default if number is None else number


def _finite_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)


def _num(value: float) -> str:
    return f"{float(value):.1f}"


def _scalar(value: float) -> str:
    return f"{float(value):.3f}".rstrip("0").rstrip(".")


def _dash_num(value: float) -> str:
    return f"{float(value):g}"


def _text(value: str) -> str:
    return html.escape(_clean_text(value), quote=True)


def _attr(value: str) -> str:
    return escape(_clean_text(value), {'"': "&quot;"})


def _clean_text(value: str) -> str:
    return "".join(char for char in value if _is_xml_char(char))


def _is_xml_char(char: str) -> bool:
    codepoint = ord(char)
    return (
        codepoint in {0x09, 0x0A, 0x0D}
        or 0x20 <= codepoint <= 0xD7FF
        or 0xE000 <= codepoint <= 0xFFFD
        or 0x10000 <= codepoint <= 0x10FFFF
    )
