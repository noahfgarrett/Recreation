#!/usr/bin/env python3
"""Draw a small, made-up chilled water / cooling water P&ID set.

Three 11x17 sheets with vector piping, equipment and instrument tags, line
tags, off-page TO/FROM callouts that point at each other, and a title block.
Everything here is invented. Sheet numbers and tags follow the conventions in
backend/recreation_extractor/conventions.py (project code DEMO).

    python3 scripts/generate-sample-package.py            # writes samples/demo-package/
    python3 scripts/generate-sample-package.py --out /tmp/pkg
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Callable
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "samples" / "demo-package"

PAGE_W, PAGE_H = 1224.0, 792.0  # 17 x 11 in, landscape
INK = (0.12, 0.15, 0.2)
GREY = (0.45, 0.5, 0.56)
SYSTEM_COLORS = {
    "CHWS": (0.05, 0.4, 0.8),
    "CHWR": (0.35, 0.6, 0.9),
    "CWS": (0.0, 0.55, 0.45),
    "CWR": (0.3, 0.7, 0.55),
}


@dataclass
class Sheet:
    number: str
    title: str
    draw: Callable[[fitz.Page], None]


def text(page: fitz.Page, x: float, y: float, value: str, size: float = 7.0, color=INK, bold: bool = False) -> None:
    page.insert_text((x, y), value, fontsize=size, fontname="hebo" if bold else "helv", color=color)


def pipe(page: fitz.Page, points: list[tuple[float, float]], system: str, width: float = 1.6) -> None:
    color = SYSTEM_COLORS[system]
    dashes = "[6 3] 0" if system.endswith("R") else None
    for start, end in zip(points, points[1:]):
        page.draw_line(start, end, color=color, width=width, dashes=dashes)


def pump(page: fitz.Page, x: float, y: float, tag: str) -> None:
    page.draw_circle((x, y), 14, color=INK, width=1.2)
    page.draw_line((x - 6, y + 8), (x + 10, y - 8), color=INK, width=1.0)
    text(page, x - 24, y + 28, tag, 6.5, bold=True)


def tank(page: fitz.Page, x: float, y: float, w: float, h: float, tag: str, label: str) -> None:
    page.draw_rect(fitz.Rect(x, y, x + w, y + h), color=INK, width=1.3)
    text(page, x + 6, y + 14, label, 6.0, GREY)
    text(page, x + 6, y + h + 12, tag, 6.5, bold=True)


def instrument(page: fitz.Page, x: float, y: float, tag: str, tap: tuple[float, float]) -> None:
    page.draw_line(tap, (x, y + 11), color=GREY, width=0.6, dashes="[2 2] 0")
    page.draw_circle((x, y), 11, color=INK, width=0.9)
    code, number = tag.split("-", 1)
    text(page, x - 7, y - 1, code, 5.2)
    text(page, x - 6, y + 6, number, 5.2)


def valve(page: fitz.Page, x: float, y: float, tag: str) -> None:
    page.draw_polyline([(x - 7, y - 5), (x + 7, y + 5), (x + 7, y - 5), (x - 7, y + 5), (x - 7, y - 5)], color=INK, width=0.9)
    text(page, x - 12, y + 16, tag, 5.5)


def offpage(page: fitz.Page, edge: str, y: float, direction: str, sheet_ref: str, line_tag: str, system: str) -> tuple[float, float]:
    """Pentagon callout at the left or right edge. Returns the pipe attachment point."""
    w, h = 112.0, 30.0
    if edge == "right":
        x0 = PAGE_W - 34 - w
        shape = [(x0, y - h / 2), (x0 + w - 14, y - h / 2), (x0 + w, y), (x0 + w - 14, y + h / 2), (x0, y + h / 2), (x0, y - h / 2)]
        attach = (x0, y)
        page.draw_line((x0 + w, y), (PAGE_W - 22, y), color=SYSTEM_COLORS[system], width=1.2)
    else:
        x0 = 34.0
        shape = [(x0 + 14, y - h / 2), (x0 + w, y - h / 2), (x0 + w, y + h / 2), (x0 + 14, y + h / 2), (x0, y), (x0 + 14, y - h / 2)]
        attach = (x0 + w, y)
        page.draw_line((22, y), (x0, y), color=SYSTEM_COLORS[system], width=1.2)
    page.draw_polyline(shape, color=INK, width=1.0)
    text(page, x0 + 18, y - 4, f"{direction} {sheet_ref}", 6.5, bold=True)
    text(page, x0 + 18, y + 8, line_tag, 6.0)
    return attach


def frame(page: fitz.Page, number: str, title: str) -> None:
    page.draw_rect(fitz.Rect(18, 18, PAGE_W - 18, PAGE_H - 18), color=INK, width=1.4)
    tb = fitz.Rect(PAGE_W - 420, PAGE_H - 100, PAGE_W - 18, PAGE_H - 18)
    page.draw_rect(tb, color=INK, width=1.2)
    page.draw_line((tb.x0, tb.y0 + 28), (tb.x1, tb.y0 + 28), color=INK, width=0.8)
    page.draw_line((tb.x1 - 130, tb.y0 + 28), (tb.x1 - 130, tb.y1), color=INK, width=0.8)
    text(page, tb.x0 + 10, tb.y0 + 18, "DEMO PROJECT - SYNTHETIC SAMPLE PACKAGE", 9, bold=True)
    text(page, tb.x0 + 10, tb.y0 + 46, title, 8, bold=True)
    text(page, tb.x0 + 10, tb.y0 + 62, "Made-up drawing for testing Recreation.", 6.5, GREY)
    text(page, tb.x0 + 10, tb.y0 + 74, "Not a real facility, owner, or design.", 6.5, GREY)
    text(page, tb.x1 - 122, tb.y0 + 62, number, 10, bold=True)


def draw_chiller_plant(page: fitz.Page) -> None:
    # Two chillers, two primary pumps, supply/return headers that leave the sheet.
    for i, x in enumerate((260.0, 470.0), start=1):
        tank(page, x, 300, 120, 70, f"R-DEMO-CHW-CH-0{i}", "CHILLER")
        pump(page, x - 60, 450, f"R-DEMO-CHW-P-0{i}")
        pipe(page, [(x - 46, 450), (x - 46 + 46 + 10, 450), (x + 10, 370)], "CHWR")
        pipe(page, [(x + 110, 300), (x + 110, 220)], "CHWS")
        instrument(page, x + 150, 250, f"TIT-1{i}1", (x + 110, 250))
        valve(page, x + 110, 270, f"XV-1{i}1")
        # condenser water connections drop to the bottom of the sheet
        pipe(page, [(x + 30, 370), (x + 30, 600)], "CWS")
        pipe(page, [(x + 80, 370), (x + 80, 580)], "CWR")
    pipe(page, [(370, 220), (900, 220)], "CHWS", 2.2)
    text(page, 640, 212, '8"-CHWS-101', 6.5)
    instrument(page, 760, 180, "PIT-102", (760, 220))
    instrument(page, 820, 180, "FIT-103", (820, 220))
    pipe(page, [(160, 520), (900, 520)], "CHWR", 2.2)
    text(page, 640, 512, '8"-CHWR-102', 6.5)
    pipe(page, [(160, 520), (160, 450), (200, 450)], "CHWR")
    pipe(page, [(160, 450), (160, 430), (410, 430), (410, 450)], "CHWR")
    pipe(page, [(300, 600), (900, 600)], "CWS", 2.0)
    text(page, 640, 594, '10"-CWS-201', 6.5)
    pipe(page, [(350, 580), (900, 580)], "CWR", 2.0)
    text(page, 640, 574, '10"-CWR-202', 6.5)
    attach = offpage(page, "right", 220, "TO", "DEMO-ME-4CHW02", '8"-CHWS-101', "CHWS")
    pipe(page, [(900, 220), attach], "CHWS", 2.2)
    # Callouts sit ~110 pt apart so each one's text neighborhood stays separate.
    attach = offpage(page, "right", 400, "FROM", "DEMO-ME-4CHW02", '8"-CHWR-102', "CHWR")
    pipe(page, [(900, 520), (940, 520), (940, 400), attach], "CHWR", 2.2)
    attach = offpage(page, "right", 530, "TO", "DEMO-ME-4CW01", '10"-CWR-202', "CWR")
    pipe(page, [(900, 580), (960, 580), (960, 530), attach], "CWR", 2.0)
    attach = offpage(page, "right", 640, "FROM", "DEMO-ME-4CW01", '10"-CWS-201', "CWS")
    pipe(page, [(900, 600), (920, 600), (920, 640), attach], "CWS", 2.0)


def draw_distribution(page: fitz.Page) -> None:
    attach = offpage(page, "left", 220, "FROM", "DEMO-ME-4CHW01", '8"-CHWS-101', "CHWS")
    pipe(page, [attach, (980, 220)], "CHWS", 2.2)
    text(page, 200, 212, '8"-CHWS-101', 6.5)
    attach = offpage(page, "left", 520, "TO", "DEMO-ME-4CHW01", '8"-CHWR-102', "CHWR")
    pipe(page, [attach, (980, 520)], "CHWR", 2.2)
    text(page, 200, 512, '8"-CHWR-102', 6.5)
    for i, x in enumerate((300.0, 520.0, 740.0), start=1):
        tank(page, x, 320, 110, 90, f"R-DEMO-CHW-AHU-0{i}", "AIR HANDLER")
        pipe(page, [(x + 25, 220), (x + 25, 320)], "CHWS")
        pipe(page, [(x + 85, 410), (x + 85, 520)], "CHWR")
        valve(page, x + 85, 460, f"FCV-2{i}1")
        instrument(page, x + 130, 470, f"TIT-2{i}1", (x + 85, 470))
        text(page, x + 30, 300, f'3"-CHWS-1{i}3', 5.8)
    instrument(page, 960, 180, "PIT-201", (960, 220))
    instrument(page, 960, 470, "PIT-202", (960, 520))
    page.draw_line((980, 220), (980, 520), color=INK, width=1.0)
    text(page, 990, 370, "END OF LOOP", 6, GREY)


def draw_cooling_water(page: fitz.Page) -> None:
    for i, x in enumerate((360.0, 600.0), start=1):
        tank(page, x, 180, 140, 80, f"R-DEMO-CW-CT-0{i}", "COOLING TOWER")
        pump(page, x + 70, 420, f"R-DEMO-CW-P-0{i}")
        pipe(page, [(x + 70, 260), (x + 70, 406)], "CWS")
        pipe(page, [(x + 120, 180), (x + 120, 150), (x + 160, 150)], "CWR")
        instrument(page, x + 110, 340, f"PIT-3{i}1", (x + 70, 340))
        pipe(page, [(x + 84, 420), (x + 120, 420), (x + 120, 520)], "CWS")
    attach = offpage(page, "left", 520, "TO", "DEMO-ME-4CHW01", '10"-CWS-201', "CWS")
    pipe(page, [attach, (720, 520)], "CWS", 2.0)
    text(page, 220, 512, '10"-CWS-201', 6.5)
    attach = offpage(page, "left", 120, "FROM", "DEMO-ME-4CHW01", '10"-CWR-202', "CWR")
    pipe(page, [attach, (760, 120), (760, 150)], "CWR", 2.0)
    text(page, 220, 112, '10"-CWR-202', 6.5)
    instrument(page, 820, 470, "AIT-301", (720, 520))
    text(page, 880, 300, "CHEMICAL TREATMENT BY OTHERS", 6, GREY)


SHEETS = [
    Sheet("DEMO-ME-4CHW01", "MECHANICAL CHILLER PLANT P&ID", draw_chiller_plant),
    Sheet("DEMO-ME-4CHW02", "MECHANICAL CHILLED WATER DISTRIBUTION P&ID", draw_distribution),
    Sheet("DEMO-ME-4CW01", "MECHANICAL COOLING WATER P&ID", draw_cooling_water),
]


def write_sheet(sheet: Sheet, out_dir: Path) -> Path:
    doc = fitz.open()
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    frame(page, sheet.number, sheet.title)
    sheet.draw(page)
    doc.set_metadata({"title": f"{sheet.number} {sheet.title}", "author": "", "creator": "generate-sample-package.py", "producer": "PyMuPDF"})
    path = out_dir / f"{sheet.number} {sheet.title.title().replace('P&Id', 'P&ID')}.pdf"
    doc.save(path, garbage=4, deflate=True, no_new_id=True)
    doc.close()
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    for sheet in SHEETS:
        print(write_sheet(sheet, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
