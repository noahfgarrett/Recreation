from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from recreation_extractor.pid_stitch.models import BoundsDict, DrawingObject, DrawingStyle, Point


NS = {"v": "http://schemas.microsoft.com/office/visio/2012/main"}
DEFAULT_TEMPLATE_DIR = Path("data/visio-templates")
PX_PER_IN = 72.0
LEGEND_SYSTEM_CODES = ("TCHW", "FUTURE", "CHW", "HRW", "HHW", "CDA", "CW")


@dataclass(frozen=True)
class VisioTemplateStats:
    path: str
    masters: int
    shapes: int
    connectors: int
    texts: int
    width: float
    height: float


@dataclass(frozen=True)
class VisioStyleProfile:
    path: str
    dominantLineColors: list[str]
    legendSystems: list[str]
    lineWeights: list[float]
    pointerLikeObjects: int
    zoneLikeObjects: int
    objectCount: int


@dataclass(frozen=True)
class _VisioFrame:
    left: float
    bottom: float
    page_height: float


def style_profile_from_objects(path: str, objects: list[DrawingObject]) -> VisioStyleProfile:
    line_colors: dict[str, int] = {}
    line_weights: set[float] = set()
    legend_systems: set[str] = set()
    pointer_like = 0
    zone_like = 0
    for obj in objects:
        if obj.kind in {"pipe", "connector"}:
            color = (obj.style.stroke or "").lower()
            if color.startswith("#") and color not in {"#111827", "#000000"}:
                line_colors[color] = line_colors.get(color, 0) + 1
            line_weights.add(round(float(obj.style.strokeWidth or 1.0), 2))
        if obj.label:
            legend_systems.update(_legend_systems_for_text(obj.label))
        if _is_pointer_like_profile_object(obj):
            pointer_like += 1
        if obj.kind == "region" and obj.bounds["width"] * obj.bounds["height"] > 25000:
            zone_like += 1
    return VisioStyleProfile(
        path=path,
        dominantLineColors=[color for color, _count in sorted(line_colors.items(), key=lambda item: (-item[1], item[0]))],
        legendSystems=sorted(legend_systems),
        lineWeights=sorted(line_weights),
        pointerLikeObjects=pointer_like,
        zoneLikeObjects=zone_like,
        objectCount=len(objects),
    )


def _legend_systems_for_text(text: str) -> set[str]:
    systems: set[str] = set()
    occupied_spans: list[tuple[int, int]] = []
    for system in sorted(LEGEND_SYSTEM_CODES, key=len, reverse=True):
        pattern = re.compile(rf"(?<![A-Z0-9]){re.escape(system)}(?![A-Z0-9])")
        for match in pattern.finditer(text.upper()):
            span = match.span()
            if any(span[0] < occupied[1] and occupied[0] < span[1] for occupied in occupied_spans):
                continue
            systems.add(system)
            occupied_spans.append(span)
    return systems


def _is_pointer_like_profile_object(obj: DrawingObject) -> bool:
    metadata = obj.metadata
    if metadata.get("symbolType") == "offpage":
        return True

    master = str(metadata.get("visioMaster") or "").upper()
    pointer_tokens = (
        "OFFPAGE",
        "OFF-PAGE",
        "OFF PAGE",
        "OFFSHEET",
        "OFF-SHEET",
        "OFF SHEET",
        "POINTER",
        "CALLOUT",
        "CONTINUATION",
    )
    return any(token in master for token in pointer_tokens)


def load_visio_template_objects(group_name: str, slug: str, evidence_ids: list[str]) -> tuple[list[DrawingObject], VisioTemplateStats | None]:
    path = _template_path_for_group(group_name, slug)
    if path is None:
        return [], None
    return _load_template_objects(path, slug, evidence_ids)


def _template_path_for_group(group_name: str, slug: str) -> Path | None:
    template_dir = Path(os.environ.get("RECREATION_VISIO_TEMPLATE_DIR", str(DEFAULT_TEMPLATE_DIR))).expanduser()
    if not template_dir.exists():
        return None

    candidates = sorted(template_dir.glob("*.vsdx"))
    if slug == "compiled_chw_ctw_baseline":
        preferred = [path for path in candidates if "LEVEL 1" in path.name.upper() and "CHW_OVERVIEW" in path.name.upper()]
    elif group_name == "CHW / CW":
        preferred = [path for path in candidates if "CHW" in path.name.upper() and "CW SYSTEM OVERVIEW" in path.name.upper()]
    elif group_name == "HHW / HRW":
        preferred = [path for path in candidates if "HHW" in path.name.upper() and "HRW" in path.name.upper()]
    else:
        preferred = []
    return preferred[0] if preferred else None


def _load_template_objects(path: Path, slug: str, evidence_ids: list[str]) -> tuple[list[DrawingObject], VisioTemplateStats]:
    with ZipFile(path) as package:
        masters = _master_names(package)
        page_name = _first_page_name(package)
        page_width, page_height = _page_size(package)
        root = ET.fromstring(package.read(page_name))
        shapes_parent = root.find("v:Shapes", NS)
        shapes = shapes_parent.findall("v:Shape", NS) if shapes_parent is not None else []
        connects = root.findall(".//v:Connect", NS)

        objects: list[DrawingObject] = []
        root_frame = _VisioFrame(left=0.0, bottom=0.0, page_height=page_height)
        for shape in shapes:
            objects.extend(_shape_to_objects(shape, masters, slug, root_frame, evidence_ids))

        connector_count = sum(1 for obj in objects if obj.kind in {"pipe", "connector"})
        text_count = sum(1 for obj in objects if obj.label)

    stats = VisioTemplateStats(
        path=str(path),
        masters=len(masters),
        shapes=len(objects),
        connectors=max(connector_count, len(connects)),
        texts=text_count,
        width=page_width,
        height=page_height,
    )
    return objects, stats


def _master_names(package: ZipFile) -> dict[str, str]:
    if "visio/masters/masters.xml" not in package.namelist():
        return {}
    root = ET.fromstring(package.read("visio/masters/masters.xml"))
    names: dict[str, str] = {}
    for master in root.findall(".//v:Master", NS):
        master_id = master.attrib.get("ID")
        if master_id:
            names[master_id] = master.attrib.get("NameU") or master.attrib.get("Name") or ""
    return names


def _first_page_name(package: ZipFile) -> str:
    names = [
        name
        for name in package.namelist()
        if name.startswith("visio/pages/page") and name.endswith(".xml") and name != "visio/pages/pages.xml"
    ]
    return sorted(names, key=_page_sort_key)[0]


def _page_sort_key(name: str) -> tuple[int, str]:
    match = re.search(r"page(\d+)\.xml$", name)
    return (int(match.group(1)) if match else 9999, name)


def _page_size(package: ZipFile) -> tuple[float, float]:
    if "visio/pages/pages.xml" not in package.namelist():
        return 48.0 * PX_PER_IN, 36.0 * PX_PER_IN
    root = ET.fromstring(package.read("visio/pages/pages.xml"))
    page = root.find("v:Page", NS)
    page_sheet = page.find("v:PageSheet", NS) if page is not None else None
    cells = _cells(page_sheet) if page_sheet is not None else {}
    width = _float(cells.get("PageWidth"), 48.0) * PX_PER_IN
    height = _float(cells.get("PageHeight"), 36.0) * PX_PER_IN
    return max(width, 1.0), max(height, 1.0)


def _shape_to_objects(
    shape: ET.Element,
    masters: dict[str, str],
    slug: str,
    frame: _VisioFrame,
    evidence_ids: list[str],
    id_prefix: str = "",
) -> list[DrawingObject]:
    cells = _cells(shape)
    shape_id = shape.attrib.get("ID", "unknown")
    object_id = f"{id_prefix}_{shape_id}" if id_prefix else shape_id
    children_parent = shape.find("v:Shapes", NS)
    children = children_parent.findall("v:Shape", NS) if children_parent is not None else []
    master_name = masters.get(shape.attrib.get("Master", ""), "")

    if not children:
        obj = _shape_to_object(shape, masters, slug, evidence_ids, object_id, frame)
        return [obj] if obj is not None else []

    objects: list[DrawingObject] = []
    parent = _shape_to_object(shape, masters, slug, evidence_ids, object_id, frame)
    if parent is not None and _symbol_type(master_name):
        return [parent]

    if parent is not None and _should_render_group_parent(parent, master_name):
        objects.append(parent)

    child_frame = _child_frame(cells, frame)
    for child in children:
        objects.extend(_shape_to_objects(child, masters, slug, child_frame, evidence_ids, object_id))
    return objects


def _shape_to_object(
    shape: ET.Element,
    masters: dict[str, str],
    slug: str,
    evidence_ids: list[str],
    object_id: str,
    frame: _VisioFrame,
) -> DrawingObject | None:
    cells = _cells(shape)
    shape_id = shape.attrib.get("ID", "unknown")
    master_name = masters.get(shape.attrib.get("Master", ""), "")
    text = _shape_text(shape)
    line_points = _line_points(cells, frame)
    if line_points is not None:
        stroke = _style_color(cells, "LineColor", "#111827")
        stroke_width = max(0.45, _float(cells.get("LineWeight"), 0.012) * PX_PER_IN)
        return DrawingObject(
            id=f"visio_pipe_{slug}_{object_id}",
            kind="pipe",
            label=text,
            points=line_points,
            bounds=_bounds_for_points(line_points, 4.0),
            style=DrawingStyle(stroke=stroke, fill="none", strokeWidth=stroke_width, opacity=1.0, dash=_dash_for_line(cells)),
            sourceEvidenceIds=evidence_ids,
            metadata={
                "overview": True,
                "templateDerived": True,
                "visioShapeId": shape_id,
                "visioMaster": master_name,
                "visioBeginArrow": cells.get("BeginArrow", ""),
                "visioEndArrow": cells.get("EndArrow", ""),
                "arrowStart": _line_arrow(cells.get("BeginArrow")),
                "arrowEnd": _line_arrow(cells.get("EndArrow")),
                "system": _system_for_color_or_text(stroke, text),
            },
        )

    bounds = _shape_bounds(cells, frame)
    if bounds is None:
        return None
    if bounds["width"] < 1.0 and bounds["height"] < 1.0 and not text:
        return None

    style = _shape_style(cells, master_name)
    metadata: dict[str, Any] = {
        "overview": True,
        "templateDerived": True,
        "visioShapeId": shape_id,
        "visioMaster": master_name,
    }

    if _is_label_shape(master_name, text, bounds, cells):
        font_size = max(5.5, min(18.0, _font_size(cells)))
        style.fontSize = font_size
        style.stroke = _style_color(cells, "Color", style.stroke)
        metadata.update({"textBox": _has_visible_fill(cells), "textAlign": _text_align(cells)})
        return DrawingObject(
            id=f"visio_label_{slug}_{object_id}",
            kind="label",
            label=text,
            points=[{"x": bounds["x"], "y": bounds["y"]}],
            bounds=bounds,
            style=style,
            sourceEvidenceIds=evidence_ids,
            metadata=metadata,
        )

    symbol_type = _symbol_type(master_name)
    if symbol_type:
        return DrawingObject(
            id=f"visio_symbol_{slug}_{object_id}",
            kind="symbol",
            label=text,
            points=_rect_points(bounds),
            bounds=bounds,
            style=style,
            sourceEvidenceIds=evidence_ids,
            metadata={**metadata, "symbolType": symbol_type, "orientation": _orientation_for_master(master_name)},
        )

    return DrawingObject(
        id=f"visio_region_{slug}_{object_id}",
        kind="region",
        label=text,
        points=_rect_points(bounds),
        bounds=bounds,
        style=style,
        sourceEvidenceIds=evidence_ids,
        metadata={**metadata, "hideCenterLabel": not bool(text)},
    )


def _should_render_group_parent(parent: DrawingObject, master_name: str) -> bool:
    if parent.kind == "label":
        return True
    if parent.kind in {"pipe", "connector"}:
        return True
    if parent.style.fill != "none" and parent.bounds["width"] * parent.bounds["height"] > 25000.0:
        return True
    return bool(parent.label)


def _cells(element: ET.Element | None) -> dict[str, str]:
    values: dict[str, str] = {}
    if element is None:
        return values
    for cell in element.findall("v:Cell", NS):
        name = cell.attrib.get("N")
        value = cell.attrib.get("V") or cell.attrib.get("F")
        if name and value is not None:
            values[name] = value
    return values


def _shape_text(shape: ET.Element) -> str:
    text_node = shape.find("v:Text", NS)
    if text_node is None:
        return ""
    text = "".join(text_node.itertext())
    return re.sub(r"\s+", " ", text).strip()


def _line_points(cells: dict[str, str], frame: _VisioFrame) -> list[Point] | None:
    begin_x = _optional_float(cells.get("BeginX"))
    begin_y = _optional_float(cells.get("BeginY"))
    end_x = _optional_float(cells.get("EndX"))
    end_y = _optional_float(cells.get("EndY"))
    if None in (begin_x, begin_y, end_x, end_y):
        return None
    return [
        {"x": (frame.left + begin_x) * PX_PER_IN, "y": frame.page_height - (frame.bottom + begin_y) * PX_PER_IN},
        {"x": (frame.left + end_x) * PX_PER_IN, "y": frame.page_height - (frame.bottom + end_y) * PX_PER_IN},
    ]


def _shape_bounds(cells: dict[str, str], frame: _VisioFrame) -> BoundsDict | None:
    pin_x = _optional_float(cells.get("PinX"))
    pin_y = _optional_float(cells.get("PinY"))
    width = _optional_float(cells.get("Width"))
    height = _optional_float(cells.get("Height"))
    if None in (pin_x, pin_y, width, height):
        return None
    w = abs(width) * PX_PER_IN
    h = abs(height) * PX_PER_IN
    page_pin_x = frame.left + pin_x
    page_pin_y = frame.bottom + pin_y
    return {
        "x": page_pin_x * PX_PER_IN - w / 2.0,
        "y": frame.page_height - (page_pin_y * PX_PER_IN + h / 2.0),
        "width": w,
        "height": h,
    }


def _child_frame(cells: dict[str, str], frame: _VisioFrame) -> _VisioFrame:
    pin_x = _float(cells.get("PinX"), 0.0)
    pin_y = _float(cells.get("PinY"), 0.0)
    width = abs(_float(cells.get("Width"), 0.0))
    height = abs(_float(cells.get("Height"), 0.0))
    loc_pin_x = _float(cells.get("LocPinX"), width / 2.0)
    loc_pin_y = _float(cells.get("LocPinY"), height / 2.0)
    return _VisioFrame(
        left=frame.left + pin_x - loc_pin_x,
        bottom=frame.bottom + pin_y - loc_pin_y,
        page_height=frame.page_height,
    )


def _shape_style(cells: dict[str, str], master_name: str) -> DrawingStyle:
    stroke = _style_color(cells, "LineColor", "#111827")
    fill = _fill_color(cells, master_name)
    line_weight = max(0.45, _float(cells.get("LineWeight"), 0.012) * PX_PER_IN)
    opacity = 1.0
    if _is_zone_fill(fill, cells):
        fill = _soft_zone_fill(fill)
    return DrawingStyle(stroke=stroke, fill=fill, strokeWidth=line_weight, opacity=opacity, dash=_dash_for_line(cells), fontSize=8.0)


def _fill_color(cells: dict[str, str], master_name: str) -> str:
    if cells.get("NoFill") == "1" or cells.get("FillPattern") == "0":
        return "none"
    fill = _style_color(cells, "FillForegnd", "")
    if fill:
        return fill
    if _symbol_type(master_name):
        return "#ffffff"
    return "none"


def _style_color(cells: dict[str, str], key: str, fallback: str) -> str:
    value = cells.get(key)
    if not value or value in {"Themed", "Inh"}:
        return fallback
    if re.match(r"^#[0-9a-fA-F]{6}$", value):
        return value.lower()
    if value.isdigit():
        if value == "0":
            return "#000000"
        if value == "1":
            return "#ffffff"
    return fallback


def _dash_for_line(cells: dict[str, str]) -> list[float] | None:
    pattern = cells.get("LinePattern")
    if pattern in {"2", "3", "4", "5"}:
        return [6.0, 4.0]
    return None


def _line_arrow(value: str | None) -> bool:
    if value in (None, "", "0"):
        return False
    try:
        return int(float(value)) > 0
    except ValueError:
        return False


def _is_label_shape(master_name: str, text: str, bounds: BoundsDict, cells: dict[str, str]) -> bool:
    if not text:
        return False
    if _symbol_type(master_name):
        return False
    if _has_visible_fill(cells) and bounds["width"] > 32.0 and bounds["height"] > 12.0:
        return False
    return True


def _has_visible_fill(cells: dict[str, str]) -> bool:
    return bool(_style_color(cells, "FillForegnd", "")) and cells.get("FillPattern") != "0" and cells.get("NoFill") != "1"


def _font_size(cells: dict[str, str]) -> float:
    return _float(cells.get("Size"), 0.12) * PX_PER_IN


def _text_align(cells: dict[str, str]) -> str:
    align = cells.get("HorzAlign")
    if align == "1":
        return "center"
    if align == "2":
        return "right"
    return "left"


def _symbol_type(master_name: str) -> str:
    name = master_name.lower()
    if "centrifugal pump" in name:
        return "centrifugal_pump"
    if "rotary pump" in name:
        return "rotary_pump"
    if "flowmeter" in name or "flow meter" in name:
        return "flow_meter"
    if "differential pressure" in name:
        return "differential_pressure_transmitter"
    if "pressure switch" in name:
        return "pressure_switch"
    if "temperature switch" in name:
        return "temperature_switch"
    if "flow switch" in name:
        return "flow_switch"
    if "level switch" in name:
        return "level_switch"
    if "recorder" in name:
        return "recorder"
    if "alarm" in name:
        return "alarm"
    if "indicator light" in name:
        return "indicator_light"
    if "flame detector" in name:
        return "flame_detector"
    if "gas detector" in name:
        return "gas_detector"
    if "smoke detector" in name:
        return "smoke_detector"
    if "i/o point" in name or "io point" in name:
        return "io_point"
    if "correcting element" in name:
        return "correcting_element"
    if "reference circle" in name:
        return "reference_circle"
    if name == "circle":
        return "tag_circle"
    if name == "square":
        return "tag_square"
    if "pressure" == name or name.endswith(" pressure"):
        return "pressure_sensor"
    if "indicator" in name or name == "circle":
        return "instrument"
    if "pump" in name:
        return "pump"
    if "centrifugal fan" in name:
        return "centrifugal_fan"
    if "chiller" in name:
        return "chiller"
    if "boiler" in name:
        return "boiler"
    if "cooling tower" in name:
        return "cooling_tower"
    if "tank mixer" in name or "agitator" in name:
        return "tank_mixer"
    if "inline mixer" in name:
        return "inline_mixer"
    if "static mixer" in name:
        return "static_mixer"
    if "calibration column" in name:
        return "calibration_column"
    if "safety shower" in name:
        return "safety_shower"
    if "eyewash" in name or "eye wash" in name:
        return "eyewash"
    if "chemical tote" in name or "ibc" in name:
        return "chemical_tote"
    if name == "drum" or "barrel" in name:
        return "drum"
    if "open/closed" in name or "open closed" in name:
        return "open_tank"
    if "closed tank" in name:
        return "closed_tank"
    if "covered tank" in name:
        return "covered_tank"
    if "tank" in name:
        return "tank"
    if "vessel" in name:
        return "vessel"
    if "plate type" in name:
        return "plate_heat_exchanger"
    if "horizontal vessel" in name:
        return "horizontal_vessel"
    if "vertical vessel" in name:
        return "vertical_vessel"
    if "silencer" in name:
        return "silencer"
    if "ejector" in name:
        return "ejector"
    if "spray nozzle" in name or name == "nozzle":
        return "spray_nozzle"
    if "hopper" in name:
        return "hopper"
    if "flame arrester" in name:
        return "flame_arrester"
    if "y strainer" in name:
        return "y_strainer"
    if "basket strainer" in name:
        return "basket_strainer"
    if "duplex strainer" in name:
        return "duplex_strainer"
    if "temporary strainer" in name:
        return "temporary_strainer"
    if "bag filter" in name:
        return "bag_filter"
    if "cartridge filter" in name:
        return "cartridge_filter"
    if "centrifugal separator" in name:
        return "centrifugal_separator"
    if "filter" in name or "strainer" in name:
        return "filter"
    if "conveyor" in name:
        return "conveyor"
    if name == "scale" or "weigh" in name:
        return "scale"
    if "duct transition" in name:
        return "duct_transition"
    if "duct filter" in name:
        return "duct_filter"
    if "duct coil" in name:
        return "duct_coil"
    if "vav" in name:
        return "vav_box"
    if "fire damper" in name:
        return "fire_damper"
    if "damper" in name:
        return "damper"
    if "patch panel" in name:
        return "patch_panel"
    if "control panel" in name:
        return "control_panel"
    if "lcd monitor" in name:
        return "lcd_monitor"
    if "computer" in name or "monitor" in name:
        return "computer_monitor"
    if name == "plc" or "programmable logic" in name:
        return "plc"
    if name == "vfd" or "variable frequency" in name:
        return "vfd"
    if "transformer" in name:
        return "transformer"
    if "disconnect" in name:
        return "disconnect_switch"
    if "circuit breaker" in name or name == "breaker":
        return "circuit_breaker"
    if "terminal block" in name:
        return "terminal_block"
    if "motor starter" in name or "starter" in name:
        return "motor_starter"
    if "panelboard" in name or "panel board" in name:
        return "panelboard"
    if "contactor" in name:
        return "contactor"
    if "relay" in name:
        return "relay"
    if name == "fuse" or " fuse" in name:
        return "fuse"
    if "ground" in name or "earth" in name:
        return "ground"
    if "cable tray" in name:
        return "cable_tray"
    if name == "ups" or "uninterruptible" in name:
        return "ups"
    if "junction box" in name:
        return "junction_box"
    if "pull box" in name:
        return "pull_box"
    if "control station" in name:
        return "control_station"
    if "network switch" in name:
        return "network_switch"
    if "backflow prevent" in name:
        return "backflow_preventer"
    if "piston valve" in name:
        return "piston_valve"
    if "dash-pot" in name or "dashpot" in name or "piston" in name:
        return "dashpot_piston"
    if "butterfly" in name:
        return "butterfly_valve"
    if "globe" in name:
        return "globe_valve"
    if "ball" in name:
        return "ball_valve"
    if "check" in name:
        return "check_valve"
    if "knife gate" in name:
        return "knife_gate_valve"
    if "powered valve" in name or "powered valves" in name:
        return "powered_valve"
    if "pinch valve" in name:
        return "pinch_valve"
    if "float valve" in name:
        return "float_valve"
    if "safety valve" in name:
        return "safety_valve"
    if "vacuum breaker" in name:
        return "vacuum_breaker"
    if "foot valve" in name:
        return "foot_valve"
    if "pressure regulator" in name or "regulator" in name:
        return "pressure_regulator"
    if "pressure relief" in name:
        return "pressure_relief_valve"
    if "relief" in name and "angle" in name:
        return "relief_angle_valve"
    if "prv" in name or "relief" in name:
        return "relief_valve"
    if "valve" in name:
        return "valve"
    if "triangle" in name:
        return "flow_arrow"
    if "sight glass" in name:
        return "sight_glass"
    if "rupture disk" in name or "rupture disc" in name:
        return "rupture_disk"
    if "sample point" in name:
        return "sample_point"
    if "sample probe" in name:
        return "sample_probe"
    if "injection quill" in name:
        return "injection_quill"
    if "vent silencer" in name:
        return "vent_silencer"
    if "relief stack" in name:
        return "relief_stack"
    if name == "vent" or "vent " in name:
        return "vent"
    if "pipe anchor" in name or name == "anchor":
        return "pipe_anchor"
    if "pipe support" in name:
        return "pipe_support"
    if "guide support" in name:
        return "guide_support"
    if "spring hanger" in name:
        return "spring_hanger"
    if "open drain" in name:
        return "open_drain"
    if "closed drain" in name:
        return "closed_drain"
    if "floor drain" in name:
        return "floor_drain"
    if "cleanout" in name or "clean out" in name:
        return "cleanout"
    if "hose bib" in name or "hose bibb" in name:
        return "hose_bib"
    if "quick connect" in name or "quick disconnect" in name:
        return "quick_connect"
    if "line blind" in name:
        return "line_blind"
    if "bellows" in name:
        return "expansion_bellows"
    return ""


def _orientation_for_master(master_name: str) -> str:
    name = master_name.lower()
    if "rotated" in name:
        return "left"
    if "triangle" in name:
        return "right"
    return "right"


def _is_zone_fill(fill: str, cells: dict[str, str]) -> bool:
    width = _float(cells.get("Width"), 0.0) * PX_PER_IN
    height = _float(cells.get("Height"), 0.0) * PX_PER_IN
    return fill != "none" and width * height > 25000.0


def _soft_zone_fill(fill: str) -> str:
    match = re.fullmatch(r"#([0-9a-fA-F]{6})", fill)
    if not match:
        return fill
    red = int(match.group(1)[0:2], 16)
    green = int(match.group(1)[2:4], 16)
    blue = int(match.group(1)[4:6], 16)
    channel_range = max(red, green, blue) - min(red, green, blue)
    amount = 0.12 if channel_range > 40 else 0.55
    blended = tuple(round(255 - (255 - channel) * amount) for channel in (red, green, blue))
    return f"#{blended[0]:02x}{blended[1]:02x}{blended[2]:02x}"


def _system_for_color_or_text(stroke: str, text: str) -> str:
    upper = text.upper()
    if "HHW" in upper:
        return "HHWS"
    if "HRW" in upper:
        return "HRW"
    if "CWR" in upper:
        return "CWR"
    if "CWS" in upper or "CTW" in upper:
        return "CWS"
    if "CHWR" in upper:
        return "CHWR"
    if "CHW" in upper:
        return "CHWS"
    color = stroke.lower()
    if color in {"#7030a0", "#7c3aed"}:
        return "CHWS"
    if color in {"#0070c0", "#2563eb"}:
        return "CHWS"
    if color in {"#00b050", "#16a34a"}:
        return "CWS"
    if color in {"#ff0000", "#dc2626"}:
        return "HHWS"
    if color in {"#ff6600", "#ea580c"}:
        return "HHWR"
    return "DEFAULT"


def _bounds_for_points(points: list[Point], padding: float) -> BoundsDict:
    x0 = min(point["x"] for point in points) - padding
    y0 = min(point["y"] for point in points) - padding
    x1 = max(point["x"] for point in points) + padding
    y1 = max(point["y"] for point in points) + padding
    return {"x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0}


def _rect_points(bounds: BoundsDict) -> list[Point]:
    x = bounds["x"]
    y = bounds["y"]
    right = x + bounds["width"]
    bottom = y + bounds["height"]
    return [{"x": x, "y": y}, {"x": right, "y": y}, {"x": right, "y": bottom}, {"x": x, "y": bottom}]


def _optional_float(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _float(value: str | None, default: float) -> float:
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default
