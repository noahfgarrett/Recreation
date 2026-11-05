from __future__ import annotations

import argparse
import json
import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.pdfgen import canvas


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "tests" / "fixtures" / "stress"
PAGE = landscape(letter)
RANDOM = random.Random(4107)


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Recreation stress-test drawing packages.")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="Output directory")
    parser.add_argument("--pages", type=int, default=32, help="Vector package sheet count")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    manifest = {
        "description": "Synthetic P&ID/cable stress fixtures for Recreation.",
        "fixtures": [],
        "groundTruth": {},
    }

    vector_pdf, vector_truth = make_vector_pid_package(out, args.pages)
    cable_pdf, cable_truth = make_cable_package(out)
    raster_pngs, raster_pdf, raster_truth = make_raster_scan_package(out)

    manifest["fixtures"].extend(
        [
            {"id": "vector_pid_32", "path": vector_pdf.name, "type": "pdf", "pages": args.pages},
            {"id": "cable_continuations", "path": cable_pdf.name, "type": "pdf", "pages": 8},
            {"id": "raster_scanned_pid", "path": raster_pdf.name, "type": "pdf", "pages": len(raster_pngs)},
            *[
                {"id": f"raster_png_{index + 1}", "path": path.name, "type": "png", "pages": 1}
                for index, path in enumerate(raster_pngs)
            ],
        ]
    )
    manifest["groundTruth"] = {
        "vector_pid_32": vector_truth,
        "cable_continuations": cable_truth,
        "raster_scanned_pid": raster_truth,
    }

    (out / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps({"out": str(out), "fixtures": len(manifest["fixtures"])}, indent=2))
    return 0


def make_vector_pid_package(out: Path, pages: int) -> tuple[Path, dict]:
    path = out / "vector_pid_package_32.pdf"
    c = canvas.Canvas(str(path), pagesize=PAGE)
    width, height = PAGE
    tags: list[str] = []
    continuations: list[dict] = []
    lines: list[str] = []

    for page_no in range(1, pages + 1):
        drawing = f"PID-{page_no:03d}"
        next_drawing = f"PID-{page_no + 1:03d}" if page_no < pages else "PID-001"
        prev_drawing = f"PID-{page_no - 1:03d}" if page_no > 1 else f"PID-{pages:03d}"
        draw_title_block(c, drawing, "SYNTHETIC PROCESS PACKAGE", page_no, pages)
        draw_grid(c, width, height)

        if page_no == 1:
            draw_legend(c, 54, 390)

        page_tags, page_lines, page_continuations = draw_complex_pid_sheet(
            c,
            drawing=drawing,
            next_drawing=next_drawing,
            prev_drawing=prev_drawing,
            page_no=page_no,
        )
        tags.extend(page_tags)
        lines.extend(page_lines)
        continuations.extend(page_continuations)

        if page_no % 4 == 0:
            draw_noise_notes(c, page_no)

        c.showPage()
    c.save()
    return path, {"tags": tags, "lineIds": lines, "continuations": continuations}


def draw_complex_pid_sheet(
    c: canvas.Canvas,
    drawing: str,
    next_drawing: str,
    prev_drawing: str,
    page_no: int,
) -> tuple[list[str], list[str], list[dict]]:
    width, _height = PAGE
    base = page_no * 10
    tags = [
        f"TK-{base + 1:03d}",
        f"P-{base + 1:03d}A",
        f"P-{base + 1:03d}B",
        f"HX-{base + 2:03d}",
        f"VSL-{base + 3:03d}",
        f"P-{base + 4:03d}A",
        f"XV-{base + 1:03d}",
        f"XV-{base + 2:03d}",
        f"CV-{base + 1:03d}",
        f"HV-{base + 3:03d}",
        f"FT-{base + 1:03d}",
        f"PT-{base + 2:03d}",
        f"TT-{base + 3:03d}",
        f"LT-{base + 4:03d}",
        f"TIC-{base + 5:03d}",
        f"PIC-{base + 6:03d}",
    ]
    line_ids = [
        f'6"-FW-{base + 101:04d}',
        f'4"-PW-{base + 102:04d}',
        f'3"-CW-{base + 103:04d}',
        f'2"-DR-{base + 104:04d}',
        f'2"-VR-{base + 105:04d}',
        f'1"-AI-{base + 106:04d}',
    ]

    tk, pump_a, pump_b, hx, vessel, export_pump = tags[:6]
    xv_in, xv_bypass, cv_main, hv_drain = tags[6:10]
    ft, pt, tt, lt, tic, pic = tags[10:]

    c.setStrokeColor(colors.HexColor("#25313f"))
    c.setFillColor(colors.black)
    c.setLineWidth(1.5)

    draw_offpage(c, 34, 432, f"FROM {prev_drawing}", "left")
    draw_offpage(c, width - 190, 232, f"TO {next_drawing}", "right")
    draw_offpage(c, 330, 520, f"TO {next_drawing}", "right")
    draw_offpage(c, 88, 186, f"FROM {prev_drawing}", "left")

    draw_vessel(c, 98, 348, tk, "FEED")
    draw_pump(c, 244, 314, pump_a)
    draw_pump(c, 244, 218, pump_b)
    draw_exchanger(c, 362, 348, hx)
    draw_valve(c, 492, 407, cv_main)
    draw_vertical_vessel(c, 604, 326, vessel)
    draw_pump(c, 682, 218, export_pump)
    draw_valve(c, 198, 426, xv_in)
    draw_valve(c, 432, 250, xv_bypass)
    draw_valve(c, 588, 188, hv_drain)

    draw_instrument(c, 268, 468, ft)
    draw_instrument(c, 448, 472, tt)
    draw_instrument(c, 652, 458, pt)
    draw_instrument(c, 658, 386, lt)
    draw_instrument(c, 512, 504, tic)
    draw_instrument(c, 720, 392, pic)

    # Main process line with elbows, a bypass, a recycle, and utility branches.
    draw_pipe(c, [(168, 432), (198, 432), (218, 432), (244, 344), (286, 344), (362, 380)])
    draw_pipe(c, [(408, 380), (492, 417), (512, 417), (604, 392)])
    draw_pipe(c, [(650, 392), (706, 392), (706, 248), (722, 248), (width - 190, 248)])
    draw_pipe(c, [(286, 248), (432, 260), (452, 260), (604, 348)])
    draw_pipe(c, [(650, 326), (668, 326), (668, 188), (608, 188), (608, 146), (164, 146), (164, 186)])
    draw_pipe(c, [(604, 432), (604, 520), (330, 520)])
    draw_pipe(c, [(406, 348), (406, 306), (526, 306), (526, 417)])

    draw_signal(c, [(268, 455), (268, 505), (492, 505), (492, 428)])
    draw_signal(c, [(448, 459), (448, 504), (512, 504)])
    draw_signal(c, [(652, 445), (720, 445), (720, 405)])
    draw_signal(c, [(658, 373), (604, 373), (604, 348)])

    c.setFont("Helvetica", 6)
    label_positions = [
        (122, 448),
        (318, 360),
        (456, 394),
        (606, 248),
        (452, 270),
        (184, 158),
    ]
    for line_id, (x, y) in zip(line_ids, label_positions):
        c.setFillColor(colors.white)
        c.rect(x - 3, y - 3, 48, 10, fill=1, stroke=0)
        c.setFillColor(colors.black)
        c.drawString(x, y, line_id)

    c.setFillColor(colors.HexColor("#526376"))
    c.setFont("Helvetica", 6)
    c.drawString(54, 514, "MATCH LINE A")
    c.drawString(560, 112, "DRAIN / SAMPLE HEADER")
    c.drawString(456, 536, "VENT HEADER")
    c.setFillColor(colors.black)

    continuations = [
        {"page": page_no, "from": drawing, "to": next_drawing, "label": f"TO {next_drawing}"},
        {"page": page_no, "from": drawing, "to": prev_drawing, "label": f"FROM {prev_drawing}"},
    ]
    return tags, line_ids, continuations


def make_cable_package(out: Path) -> tuple[Path, dict]:
    path = out / "cable_continuation_package.pdf"
    c = canvas.Canvas(str(path), pagesize=PAGE)
    width, height = PAGE
    cables: list[str] = []
    continuations: list[dict] = []
    for page_no in range(1, 9):
        drawing = f"CAB-{page_no:03d}"
        draw_title_block(c, drawing, "SYNTHETIC CABLE AND CONDUIT PACKAGE", page_no, 8)
        draw_grid(c, width, height)
        for index in range(8):
            y = 485 - index * 42
            src = f"JB-{page_no:03d}{index + 1}"
            dst = f"PNL-{page_no:03d}{index + 1}"
            cable = f"CBL-{page_no:03d}{index + 1:02d}"
            conduit = f"CNDT-{page_no:03d}{index + 1:02d}"
            cables.extend([cable, conduit])
            c.setStrokeColor(colors.HexColor("#25313f"))
            c.setLineWidth(1)
            c.rect(70, y - 12, 48, 24)
            c.rect(610, y - 12, 62, 24)
            c.drawString(76, y - 3, src)
            c.drawString(616, y - 3, dst)
            c.setDash(5, 4)
            c.line(118, y, 610, y)
            c.setDash()
            c.setFont("Helvetica", 7)
            c.drawString(260, y + 8, f"{cable} / {conduit}")
        continuation = f"TO CAB-{page_no + 1:03d}" if page_no < 8 else "TO CAB-001"
        draw_offpage(c, width - 180, 72, continuation, "right")
        continuations.append({"page": page_no, "label": continuation})
        c.showPage()
    c.save()
    return path, {"cableIds": cables, "continuations": continuations}


def make_raster_scan_package(out: Path) -> tuple[list[Path], Path, dict]:
    png_paths: list[Path] = []
    ground_truth = {"tags": [], "continuations": []}
    for page_no in range(1, 7):
        image = Image.new("RGB", (1650, 1050), "#f5f3ed")
        draw = ImageDraw.Draw(image)
        font = load_font(26)
        small = load_font(18)

        draw.rectangle((26, 26, 1624, 1024), outline="#2d3640", width=3)
        draw.text((55, 45), f"SCANNED PID-{page_no:03d}", fill="#1f2933", font=font)
        draw.text((1220, 45), "LOW CONTRAST / SKEW / SPECKLE", fill="#525f6d", font=small)

        previous = None
        for index in range(10):
            x = 90 + (index % 5) * 290
            y = 190 + (index // 5) * 270 + RANDOM.randint(-12, 12)
            tag = f"{'P' if index % 2 == 0 else 'XV'}-{page_no:03d}{index + 1}"
            ground_truth["tags"].append(tag)
            draw.rounded_rectangle((x, y, x + 150, y + 70), radius=9, outline="#1f2933", width=3, fill="#fbfaf6")
            draw.text((x + 18, y + 22), tag, fill="#1f2933", font=small)
            if previous:
                px, py = previous
                draw.line((px + 150, py + 35, x, y + 35), fill="#1f2933", width=4)
                draw.text(((px + x) // 2, (py + y) // 2 - 22), f"PW-{page_no:03d}{index:02d}", fill="#1f2933", font=small)
            previous = (x, y)

        continuation = f"TO PID-{page_no + 1:03d}" if page_no < 6 else "TO PID-001"
        draw.polygon([(1405, 825), (1585, 825), (1622, 862), (1585, 899), (1405, 899)], outline="#1f2933", fill="#fbfaf6")
        draw.text((1430, 850), continuation, fill="#1f2933", font=small)
        ground_truth["continuations"].append({"page": page_no, "label": continuation})

        image = add_scan_degradation(image, page_no)
        png_path = out / f"raster_scanned_pid_{page_no:02d}.png"
        image.save(png_path)
        png_paths.append(png_path)

    pdf_path = out / "raster_scanned_pid_package.pdf"
    first, *rest = [Image.open(path).convert("RGB") for path in png_paths]
    first.save(pdf_path, save_all=True, append_images=rest, resolution=150)
    return png_paths, pdf_path, ground_truth


def draw_title_block(c: canvas.Canvas, drawing: str, title: str, page_no: int, pages: int) -> None:
    width, _height = PAGE
    c.setStrokeColor(colors.HexColor("#25313f"))
    c.setFillColor(colors.white)
    c.rect(36, 34, width - 72, 52, fill=0, stroke=1)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(48, 65, title)
    c.setFont("Helvetica", 8)
    c.drawString(48, 48, "Generated stress fixture - no engineering authority")
    c.drawRightString(width - 48, 65, drawing)
    c.drawRightString(width - 48, 48, f"SHEET {page_no} OF {pages}")


def draw_grid(c: canvas.Canvas, width: float, height: float) -> None:
    c.setStrokeColor(colors.HexColor("#e5e9ef"))
    c.setLineWidth(0.25)
    for x in range(36, int(width - 36), 36):
        c.line(x, 96, x, height - 42)
    for y in range(96, int(height - 42), 36):
        c.line(36, y, width - 36, y)


def draw_legend(c: canvas.Canvas, x: float, y: float) -> None:
    c.setStrokeColor(colors.HexColor("#25313f"))
    c.setFillColor(colors.black)
    c.setLineWidth(1)
    c.rect(x, y, 170, 90)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + 8, y + 72, "LEGEND / SYMBOLS")
    c.setFont("Helvetica", 7)
    c.circle(x + 22, y + 48, 10)
    c.drawString(x + 42, y + 45, "Instrument bubble")
    c.rect(x + 12, y + 18, 22, 14)
    c.drawString(x + 42, y + 20, "Equipment / panel")


def draw_pipe(c: canvas.Canvas, points: list[tuple[float, float]]) -> None:
    c.setStrokeColor(colors.HexColor("#25313f"))
    c.setLineWidth(1.45)
    c.setDash()
    for start, end in zip(points, points[1:]):
        c.line(start[0], start[1], end[0], end[1])


def draw_signal(c: canvas.Canvas, points: list[tuple[float, float]]) -> None:
    c.setStrokeColor(colors.HexColor("#526376"))
    c.setLineWidth(0.8)
    c.setDash(4, 3)
    for start, end in zip(points, points[1:]):
        c.line(start[0], start[1], end[0], end[1])
    c.setDash()


def draw_pump(c: canvas.Canvas, x: float, y: float, tag: str) -> None:
    c.setStrokeColor(colors.HexColor("#25313f"))
    c.setFillColor(colors.white)
    c.setLineWidth(1.3)
    c.circle(x + 20, y + 20, 20, fill=0)
    c.line(x + 20, y + 20, x + 34, y + 28)
    c.line(x + 34, y + 28, x + 30, y + 17)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(x + 20, y - 10, tag)


def draw_vessel(c: canvas.Canvas, x: float, y: float, tag: str, label: str) -> None:
    c.setStrokeColor(colors.HexColor("#25313f"))
    c.setFillColor(colors.white)
    c.setLineWidth(1.3)
    c.roundRect(x, y, 70, 54, 8, fill=0)
    c.line(x + 10, y + 10, x + 60, y + 10)
    c.line(x + 10, y + 28, x + 60, y + 28)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(x + 35, y - 10, tag)
    c.setFont("Helvetica", 5.5)
    c.drawCentredString(x + 35, y + 44, label)


def draw_vertical_vessel(c: canvas.Canvas, x: float, y: float, tag: str) -> None:
    c.setStrokeColor(colors.HexColor("#25313f"))
    c.setFillColor(colors.white)
    c.setLineWidth(1.3)
    c.roundRect(x, y, 46, 116, 18, fill=0)
    c.line(x + 6, y + 32, x + 40, y + 32)
    c.line(x + 6, y + 78, x + 40, y + 78)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(x + 23, y - 10, tag)


def draw_exchanger(c: canvas.Canvas, x: float, y: float, tag: str) -> None:
    c.setStrokeColor(colors.HexColor("#25313f"))
    c.setFillColor(colors.white)
    c.setLineWidth(1.3)
    c.rect(x, y, 46, 64, fill=0)
    for offset in (12, 22, 32):
        c.arc(x + 8, y + offset, x + 38, y + offset + 18, 180, 180)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(x + 23, y - 10, tag)


def draw_equipment(c: canvas.Canvas, x: float, y: float, tag: str, index: int) -> None:
    c.setStrokeColor(colors.HexColor("#25313f"))
    c.setFillColor(colors.white)
    c.setLineWidth(1.3)
    if index % 2 == 0:
        c.circle(x + 26, y + 16, 18, fill=0)
    else:
        c.rect(x, y, 52, 32, fill=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7)
    c.drawCentredString(x + 26, y - 10, tag)


def draw_valve(c: canvas.Canvas, x: float, y: float, tag: str) -> None:
    c.setStrokeColor(colors.HexColor("#25313f"))
    c.setLineWidth(1)
    c.line(x, y, x + 20, y + 20)
    c.line(x + 20, y, x, y + 20)
    c.rect(x, y, 20, 20)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 6)
    c.drawCentredString(x + 10, y - 9, tag)


def draw_instrument(c: canvas.Canvas, x: float, y: float, tag: str) -> None:
    c.setStrokeColor(colors.HexColor("#25313f"))
    c.setLineWidth(0.8)
    c.circle(x, y, 13)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 5)
    c.drawCentredString(x, y - 2, tag)


def draw_offpage(c: canvas.Canvas, x: float, y: float, label: str, side: str) -> None:
    c.setStrokeColor(colors.HexColor("#25313f"))
    c.setFillColor(colors.white)
    c.setLineWidth(1.2)
    if side == "right":
        c.line(x, y, x + 115, y)
        c.line(x + 115, y, x + 135, y + 16)
        c.line(x + 135, y + 16, x + 115, y + 32)
        c.line(x + 115, y + 32, x, y + 32)
        c.line(x, y + 32, x, y)
    else:
        c.line(x + 135, y, x + 20, y)
        c.line(x + 20, y, x, y + 16)
        c.line(x, y + 16, x + 20, y + 32)
        c.line(x + 20, y + 32, x + 135, y + 32)
        c.line(x + 135, y + 32, x + 135, y)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(x + 14, y + 12, label[:26])


def draw_noise_notes(c: canvas.Canvas, page_no: int) -> None:
    c.setFont("Helvetica", 6)
    c.setFillColor(colors.HexColor("#526376"))
    for index in range(8):
        c.drawString(430 + index * 24, 108 + (index % 3) * 10, f"REV {page_no}.{index} HOLD")
    c.setFillColor(colors.black)


def load_font(size: int):
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ]
    for candidate in candidates:
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def add_scan_degradation(image: Image.Image, page_no: int) -> Image.Image:
    image = image.rotate(RANDOM.uniform(-1.2, 1.2), resample=Image.Resampling.BICUBIC, expand=False, fillcolor="#eeeae2")
    draw = ImageDraw.Draw(image)
    for _ in range(1800):
        x = RANDOM.randrange(image.width)
        y = RANDOM.randrange(image.height)
        shade = RANDOM.randrange(120, 220)
        draw.point((x, y), fill=(shade, shade, shade))
    for index in range(3):
        x = 320 + index * 360 + RANDOM.randint(-20, 20)
        draw.line((x, 30, x + RANDOM.randint(-10, 10), image.height - 30), fill="#d6d0c6", width=2)
    if page_no % 2 == 0:
        draw.ellipse((1140, 120, 1320, 250), outline="#d2c4a7", width=5)
    return image.filter(ImageFilter.GaussianBlur(radius=0.25))


if __name__ == "__main__":
    raise SystemExit(main())
