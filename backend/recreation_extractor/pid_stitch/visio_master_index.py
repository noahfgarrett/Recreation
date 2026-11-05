from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET
from zipfile import BadZipFile, ZipFile


NS = {"v": "http://schemas.microsoft.com/office/visio/2012/main"}


@dataclass(frozen=True)
class VisioMasterIndexRow:
    source_file: str
    master_id: str
    name: str
    universal_name: str
    unique_id: str
    master_path: str
    symbol_hint: str


def extract_visio_master_index(paths: Iterable[Path | str]) -> list[VisioMasterIndexRow]:
    """Extract a deterministic index of named masters from Visio .vsdx packages."""
    rows: list[VisioMasterIndexRow] = []
    for path_like in paths:
        path = Path(path_like).expanduser()
        if not path.exists() or path.suffix.lower() != ".vsdx":
            continue
        rows.extend(_extract_package_masters(path))
    return sorted(rows, key=lambda row: (row.source_file.lower(), _master_sort_key(row.master_id), row.name.lower()))


def _extract_package_masters(path: Path) -> list[VisioMasterIndexRow]:
    try:
        with ZipFile(path) as package:
            if "visio/masters/masters.xml" not in package.namelist():
                return []
            root = ET.fromstring(package.read("visio/masters/masters.xml"))
            package_names = set(package.namelist())
    except (BadZipFile, KeyError, ET.ParseError):
        return []

    rows: list[VisioMasterIndexRow] = []
    for master in root.findall(".//v:Master", NS):
        master_id = (master.attrib.get("ID") or "").strip()
        universal_name = (master.attrib.get("NameU") or "").strip()
        name = universal_name or (master.attrib.get("Name") or "").strip()
        if not name:
            continue
        master_path = f"visio/masters/master{master_id}.xml" if master_id else ""
        rows.append(
            VisioMasterIndexRow(
                source_file=path.name,
                master_id=master_id,
                name=name,
                universal_name=universal_name,
                unique_id=(master.attrib.get("UniqueID") or "").strip(),
                master_path=master_path if master_path in package_names else "",
                symbol_hint=_symbol_hint(name),
            )
        )
    return rows


def _symbol_hint(name: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
    if not normalized:
        return "shape"

    signal_terms = {
        "capillary",
        "data",
        "electric",
        "electrical",
        "heat trace",
        "hydraulic",
        "mechanical",
        "p id",
        "pid",
        "pneumatic",
        "signal",
    }
    if any(term in normalized for term in signal_terms):
        return "signal"

    valve_terms = {
        "angle valve",
        "ball",
        "butterfly",
        "check",
        "diaphragm",
        "fail closed",
        "fail open",
        "float valve",
        "foot valve",
        "gate",
        "globe",
        "needle",
        "pinch",
        "piston valve",
        "plug",
        "pressure relief",
        "powered",
        "regulator",
        "prv",
        "reducing",
        "relief",
        "safety valve",
        "solenoid",
        "vacuum breaker",
        "valve",
        "wedge",
    }
    if any(term in normalized for term in valve_terms):
        return "valve"

    control_terms = {
        "cable tray",
        "control station",
        "contactor",
        "fuse",
        "ground",
        "junction box",
        "motor starter",
        "network switch",
        "panelboard",
        "panel board",
        "pull box",
        "relay",
        "uninterruptible",
        "ups",
    }
    if any(term in normalized for term in control_terms):
        return "control"

    if "pump" in normalized:
        return "pump"

    instrument_terms = {
        "analyzer",
        "alarm",
        "controller",
        "differential pressure",
        "flame detector",
        "fit",
        "flow meter",
        "flowmeter",
        "gas detector",
        "gauge",
        "indicator light",
        "indicator",
        "instrument",
        "io point",
        "i o point",
        "meter",
        "recorder",
        "smoke detector",
        "switch",
        "tit",
        "transmitter",
    }
    if any(term in normalized for term in instrument_terms):
        return "instrument"

    equipment_terms = {
        "air handler",
        "boiler",
        "cartridge filter",
        "chiller",
        "chemical tote",
        "coil",
        "column",
        "compressor",
        "conveyor",
        "cooling tower",
        "damper",
        "dash pot",
        "dashpot",
        "drum",
        "duct coil",
        "duct filter",
        "duct transition",
        "dryer",
        "ejector",
        "eye wash",
        "eyewash",
        "fan",
        "fire damper",
        "flame arrester",
        "calibration column",
        "bag filter",
        "filter",
        "heat exchanger",
        "hopper",
        "monitor",
        "panel",
        "plate type",
        "reactor",
        "safety shower",
        "scale",
        "separator",
        "silencer",
        "spray nozzle",
        "strainer",
        "static mixer",
        "inline mixer",
        "tank",
        "tank mixer",
        "vav",
        "vessel",
    }
    if any(term in normalized for term in equipment_terms):
        return "equipment"

    fitting_terms = {
        "blind",
        "cap",
        "elbow",
        "bellows",
        "flange",
        "hose",
        "line blind",
        "orifice",
        "pipe anchor",
        "pipe support",
        "plate",
        "quick connect",
        "quick disconnect",
        "reducer",
        "relief stack",
        "rupture disk",
        "rupture disc",
        "sample point",
        "sample probe",
        "injection quill",
        "open drain",
        "closed drain",
        "floor drain",
        "cleanout",
        "clean out",
        "hose bib",
        "guide support",
        "spring hanger",
        "sight glass",
        "spectacle",
        "tee",
        "union",
        "vent silencer",
        "vent",
    }
    if any(term in normalized for term in fitting_terms):
        return "fitting"

    return "shape"


def _master_sort_key(master_id: str) -> tuple[int, str]:
    try:
        return (int(master_id), master_id)
    except ValueError:
        return (999999, master_id)
