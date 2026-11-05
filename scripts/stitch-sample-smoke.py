#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from recreation_extractor.service import RecreationService  # noqa: E402


PDF_DIR = REPO_ROOT / "samples" / "demo-package"
JOB_TIMEOUT_SECONDS = 15 * 60


class SmokeFailure(RuntimeError):
    pass


def main() -> int:
    parser = argparse.ArgumentParser(description="Import a folder of P&ID PDFs, run the stitch job, and export the result.")
    parser.add_argument("pdf_dir", nargs="?", type=Path, default=PDF_DIR)
    pdfs = _sample_pdfs(parser.parse_args().pdf_dir)

    with tempfile.TemporaryDirectory(prefix="recreation-stitch-smoke-") as tmp:
        service = RecreationService(Path(tmp) / "data")
        project = service.create_project("P&ID Stitch Sample Smoke")
        service.import_files(project.id, [str(path) for path in pdfs])

        job_status = _wait_for_job(service, service.start_stitch_job(project.id))
        job_result = job_status["result"] or {}
        options = service.store.list_layout_options(project.id)
        if len(options) < 2:
            raise SmokeFailure(f"Expected at least 2 layout options, got {len(options)}")

        selected = _selected_option(options)
        drawing = selected.get("drawingDocument")
        if not isinstance(drawing, dict):
            raise SmokeFailure(f"Selected layout option {selected.get('id')} has no drawing document")

        objects = drawing.get("objects")
        if not isinstance(objects, list):
            raise SmokeFailure(f"Selected drawing {drawing.get('id')} has no object list")

        pipe_count = _count_objects(objects, "pipe")
        label_count = _count_objects(objects, "label")
        if pipe_count < 1:
            raise SmokeFailure(f"Selected drawing {drawing.get('id')} has no pipe objects")
        if label_count < 1:
            raise SmokeFailure(f"Selected drawing {drawing.get('id')} has no label objects")

        drawing_id = str(selected["drawingId"])
        svg_export = service.export_drawing(project.id, drawing_id, "svg")
        pdf_export = service.export_drawing(project.id, drawing_id, "pdf")
        svg_size = _assert_export(svg_export, "svg")
        pdf_size = _assert_export(pdf_export, "pdf")

        summary = {
            "projectId": project.id,
            "pdfsImported": len(pdfs),
            "layoutOptions": len(options),
            "jobLayoutOptions": job_result.get("layoutOptions"),
            "selectedLayoutOption": selected.get("id"),
            "selectedDrawing": drawing_id,
            "pipes": pipe_count,
            "labels": label_count,
            "exports": {
                "svg": {"path": svg_export["path"], "bytes": svg_size},
                "pdf": {"path": pdf_export["path"], "bytes": pdf_size},
            },
        }
        print(json.dumps(summary, sort_keys=True))
    return 0


def _sample_pdfs(directory: Path) -> list[Path]:
    if not directory.exists():
        raise SmokeFailure(f"Sample PDF directory does not exist: {directory}")
    pdfs = sorted(path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() == ".pdf")
    if not pdfs:
        raise SmokeFailure(f"No PDFs found in sample PDF directory: {directory}")
    return pdfs


def _wait_for_job(service: RecreationService, job_id: str) -> dict[str, Any]:
    deadline = time.monotonic() + JOB_TIMEOUT_SECONDS
    last_status: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        status = service.jobs.get(job_id)
        last_status = status
        if status["status"] == "completed":
            return status
        if status["status"] == "failed":
            raise SmokeFailure(f"Stitch job failed: {status.get('error')}")
        time.sleep(0.25)
    raise SmokeFailure(f"Stitch job timed out after {JOB_TIMEOUT_SECONDS}s: {last_status}")


def _selected_option(options: list[dict[str, Any]]) -> dict[str, Any]:
    for option in options:
        if str(option.get("name", "")).casefold() == "recommended":
            return option
    return options[0]


def _count_objects(objects: list[Any], kind: str) -> int:
    return sum(1 for obj in objects if isinstance(obj, dict) and obj.get("kind") == kind)


def _assert_export(export: dict[str, Any], export_type: str) -> int:
    path = Path(str(export.get("path", "")))
    if export.get("type") != export_type:
        raise SmokeFailure(f"Expected {export_type} export response, got {export}")
    if not path.exists():
        raise SmokeFailure(f"{export_type.upper()} export was not written: {path}")
    size = path.stat().st_size
    if size <= 0:
        raise SmokeFailure(f"{export_type.upper()} export is empty: {path}")
    return size


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SmokeFailure as exc:
        raise SystemExit(str(exc)) from exc
