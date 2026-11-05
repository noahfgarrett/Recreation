import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

from recreation_extractor.service import RecreationService


class PidStitchServiceTests(unittest.TestCase):
    def test_legacy_source_files_table_is_migrated_with_page_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            data_dir = tmp_path / "data"
            data_dir.mkdir()
            db_path = data_dir / "projects.sqlite"
            conn = sqlite3.connect(db_path)
            try:
                conn.executescript(
                    """
                    CREATE TABLE projects (
                      id TEXT PRIMARY KEY,
                      name TEXT NOT NULL,
                      created_at TEXT NOT NULL,
                      updated_at TEXT NOT NULL
                    );
                    CREATE TABLE source_files (
                      id TEXT PRIMARY KEY,
                      project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
                      path TEXT NOT NULL,
                      name TEXT NOT NULL,
                      sha256 TEXT NOT NULL
                    );
                    """
                )
            finally:
                conn.close()

            pdf_path = tmp_path / "legacy-source.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nlegacy fixture bytes\n")
            service = RecreationService(data_dir)
            project = service.create_project("Legacy source files")

            service.import_files(project.id, [str(pdf_path)])

            conn = sqlite3.connect(db_path)
            try:
                columns = {row[1] for row in conn.execute("PRAGMA table_info(source_files)")}
            finally:
                conn.close()
            self.assertIn("page_count", columns)
            self.assertEqual(service.store.list_source_files(project.id)[0]["page_count"], 0)

    def test_start_stitch_job_creates_layout_options_and_pipe_drawing(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first_pdf = tmp_path / "pid-001.pdf"
            second_pdf = tmp_path / "pid-002.pdf"
            self._write_continuation_pdf(first_pdf, "right", "TO SUPPLY HEADER", "DEMO-ME-4CHW02")
            self._write_continuation_pdf(second_pdf, "left", "FROM SUPPLY HEADER", "DEMO-ME-4CHW01")

            service = RecreationService(tmp_path / "data")
            project = service.create_project("Stitch fixture")
            service.import_files(project.id, [str(first_pdf), str(second_pdf)])

            result = self._wait_for_job(service, service.start_stitch_job(project.id))

            self.assertEqual(result["projectId"], project.id)
            self.assertEqual(
                set(result),
                {"projectId", "candidates", "matches", "layoutOptions", "layoutOptionIds", "drawingIds"},
            )
            self.assertIsInstance(result["candidates"], int)
            self.assertIsInstance(result["matches"], int)
            self.assertGreaterEqual(result["candidates"], 2)
            self.assertGreaterEqual(result["matches"], 1)
            self.assertGreaterEqual(result["layoutOptions"], 2)
            self.assertEqual(len(result["layoutOptionIds"]), result["layoutOptions"])
            self.assertEqual(len(result["drawingIds"]), result["layoutOptions"])

            options = service.store.list_layout_options(project.id)
            self.assertGreaterEqual(len(options), 3)
            self.assertTrue({"Clean overview", "Recommended", "Source-faithful"}.issubset({option["name"] for option in options}))
            self.assertTrue(
                any(
                    obj["kind"] == "pipe"
                    for option in options
                    for obj in option["drawingDocument"]["objects"]
                )
            )

    def test_start_stitch_job_fails_helpfully_without_imported_source_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            service = RecreationService(Path(tmp) / "data")
            project = service.create_project("No files")

            job_id = service.start_stitch_job(project.id)
            status = self._wait_for_terminal_status(service, job_id)

            self.assertEqual(status["status"], "failed")
            self.assertIn("No source files imported", status["error"])

    def test_same_pdf_imported_into_two_projects_keeps_both_project_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "shared.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nsame fixture bytes\n")
            service = RecreationService(tmp_path / "data")
            first_project = service.create_project("First")
            second_project = service.create_project("Second")

            first_import = service.import_files(first_project.id, [str(pdf_path)])
            second_import = service.import_files(second_project.id, [str(pdf_path)])

            first_sources = service.store.list_source_files(first_project.id)
            second_sources = service.store.list_source_files(second_project.id)
            self.assertEqual(len(first_sources), 1)
            self.assertEqual(len(second_sources), 1)
            self.assertEqual(first_sources[0]["id"], first_import["files"][0]["id"])
            self.assertEqual(second_sources[0]["id"], second_import["files"][0]["id"])
            self.assertNotEqual(first_sources[0]["id"], second_sources[0]["id"])

    def test_reimport_changed_same_path_replaces_stale_project_source_row(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "changed.pdf"
            service = RecreationService(tmp_path / "data")
            project = service.create_project("Changed same path")

            pdf_path.write_bytes(b"%PDF-1.4\nfirst content\n")
            first_import = service.import_files(project.id, [str(pdf_path)])
            pdf_path.write_bytes(b"%PDF-1.4\nsecond content\n")
            second_import = service.import_files(project.id, [str(pdf_path)])

            sources = service.store.list_source_files(project.id)
            self.assertEqual(len(sources), 1)
            self.assertEqual(sources[0]["path"], str(pdf_path))
            self.assertEqual(sources[0]["id"], second_import["files"][0]["id"])
            self.assertNotEqual(first_import["files"][0]["id"], second_import["files"][0]["id"])

    def test_import_selected_pages_creates_subset_pdf_for_extraction(self):
        try:
            import fitz  # type: ignore
        except Exception as exc:
            self.skipTest(f"PyMuPDF unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "four-page-package.pdf"
            self._write_numbered_pdf(
                pdf_path,
                [
                    "PAGE ONE NOT SELECTED",
                    "PAGE TWO SELECTED",
                    "PAGE THREE NOT SELECTED",
                    "PAGE FOUR SELECTED",
                ],
            )
            service = RecreationService(tmp_path / "data")
            project = service.create_project("Selected pages")

            imported = service.import_files(project.id, [{"path": str(pdf_path), "pages": [2, 4]}])

            self.assertEqual(len(imported["files"]), 1)
            imported_path = Path(imported["files"][0]["path"])
            self.assertNotEqual(imported_path, pdf_path)
            self.assertTrue(imported_path.exists())
            self.assertIn("pages 2,4", imported["files"][0]["name"])

            doc = fitz.open(imported_path)
            try:
                self.assertEqual(len(doc), 2)
                self.assertIn("PAGE TWO SELECTED", doc[0].get_text())
                self.assertIn("PAGE FOUR SELECTED", doc[1].get_text())
                self.assertNotIn("PAGE ONE NOT SELECTED", doc[0].get_text() + doc[1].get_text())
            finally:
                doc.close()

    def test_import_selected_pages_rejects_bool_page_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "bool-page-selection.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nfixture\n")
            service = RecreationService(tmp_path / "data")
            project = service.create_project("Bool page selection")

            with self.assertRaises(ValueError):
                service.import_files(project.id, [{"path": str(pdf_path), "pages": [True]}])

    def test_import_selected_pages_rejects_empty_page_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "empty-page-selection.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nfixture\n")
            service = RecreationService(tmp_path / "data")
            project = service.create_project("Empty page selection")

            with self.assertRaises(ValueError):
                service.import_files(project.id, [{"path": str(pdf_path), "pages": []}])

    def test_preflight_review_can_be_created_and_confirmed(self) -> None:
        try:
            import fitz  # type: ignore  # noqa: F401
        except Exception as exc:
            self.skipTest(f"PyMuPDF unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "preflight-source.pdf"
            self._write_numbered_pdf(
                pdf_path,
                [
                    "ELECTRICAL LEGEND ABBREVIATIONS POWER ONE-LINE LEGEND",
                    "PANEL SCHEDULE DESIGNATION RW4PP1E4 SUPPLY FROM RW4MDP4C6",
                ],
            )
            service = RecreationService(tmp_path / "data")
            project = service.create_project("Preflight project")
            service.import_files(project.id, [str(pdf_path)])

            review = service.run_preflight(project.id)

            self.assertEqual(review["projectId"], project.id)
            self.assertIn("disciplines", review)
            self.assertIn("pageRoles", review)

            confirmed = service.confirm_preflight(
                project.id,
                {
                    **review,
                    "status": "confirmed",
                    "disciplines": ["Electrical"],
                    "legendPages": [1],
                },
            )

            self.assertEqual(confirmed["status"], "confirmed")
            self.assertEqual(confirmed["disciplines"], ["Electrical"])
            self.assertEqual(service.get_preflight(project.id)["legendPages"], [1])

    def test_confirm_preflight_rejects_missing_source_after_page_count_cached(self) -> None:
        try:
            import fitz  # type: ignore  # noqa: F401
        except Exception as exc:
            self.skipTest(f"PyMuPDF unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "cached-count-source.pdf"
            self._write_numbered_pdf(pdf_path, ["ELECTRICAL LEGEND ABBREVIATIONS"])
            service = RecreationService(tmp_path / "data")
            project = service.create_project("Cached count missing source")
            service.import_files(project.id, [str(pdf_path)])
            review = service.run_preflight(project.id)
            pdf_path.unlink()

            with self.assertRaises(ValueError) as raised:
                service.confirm_preflight(project.id, review)

            self.assertIn("Imported PDF file is missing", str(raised.exception))
            self.assertIn(str(pdf_path), str(raised.exception))

    def test_confirm_preflight_uses_current_pdf_page_count_after_source_replaced(self) -> None:
        try:
            import fitz  # type: ignore  # noqa: F401
        except Exception as exc:
            self.skipTest(f"PyMuPDF unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "replaced-page-count-source.pdf"
            self._write_numbered_pdf(pdf_path, ["ELECTRICAL LEGEND ABBREVIATIONS", "PANEL SCHEDULE"])
            service = RecreationService(tmp_path / "data")
            project = service.create_project("Replaced page count")
            imported = service.import_files(project.id, [str(pdf_path)])
            review = service.run_preflight(project.id)
            self._write_numbered_pdf(pdf_path, ["ELECTRICAL LEGEND ABBREVIATIONS"])

            with self.assertRaises(ValueError):
                service.confirm_preflight(
                    project.id,
                    {
                        **review,
                        "pageRoles": [
                            {
                                "sourceFileId": imported["files"][0]["id"],
                                "page": 2,
                                "role": "legend_reference",
                                "confidence": 0.5,
                                "reason": "bad",
                            }
                        ],
                    },
                )

    def test_get_preflight_rejects_cached_review_when_source_is_missing(self) -> None:
        try:
            import fitz  # type: ignore  # noqa: F401
        except Exception as exc:
            self.skipTest(f"PyMuPDF unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "cached-review-source.pdf"
            self._write_numbered_pdf(pdf_path, ["ELECTRICAL LEGEND ABBREVIATIONS"])
            service = RecreationService(tmp_path / "data")
            project = service.create_project("Cached review missing source")
            service.import_files(project.id, [str(pdf_path)])
            service.run_preflight(project.id)
            pdf_path.unlink()

            with self.assertRaises(ValueError) as raised:
                service.get_preflight(project.id)

            self.assertIn("Imported PDF file is missing", str(raised.exception))
            self.assertIn(str(pdf_path), str(raised.exception))

    def test_run_preflight_reports_corrupt_imported_pdf_as_value_error(self) -> None:
        try:
            import fitz  # type: ignore  # noqa: F401
        except Exception as exc:
            self.skipTest(f"PyMuPDF unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "corrupt-preflight-source.pdf"
            pdf_path.write_bytes(b"%PDF-1.4\nnot a readable pdf\n")
            service = RecreationService(tmp_path / "data")
            project = service.create_project("Corrupt preflight source")
            service.import_files(project.id, [str(pdf_path)])

            with self.assertRaises(ValueError) as raised:
                service.run_preflight(project.id)

            self.assertIn("Unable to read imported PDF", str(raised.exception))
            self.assertIn(str(pdf_path), str(raised.exception))

    def test_run_preflight_reports_missing_imported_pdf_as_value_error(self) -> None:
        try:
            import fitz  # type: ignore  # noqa: F401
        except Exception as exc:
            self.skipTest(f"PyMuPDF unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "missing-preflight-source.pdf"
            self._write_numbered_pdf(pdf_path, ["ELECTRICAL LEGEND ABBREVIATIONS"])
            service = RecreationService(tmp_path / "data")
            project = service.create_project("Missing preflight source")
            service.import_files(project.id, [str(pdf_path)])
            pdf_path.unlink()

            with self.assertRaises(ValueError) as raised:
                service.run_preflight(project.id)

            self.assertIn("Imported PDF file is missing", str(raised.exception))
            self.assertIn(str(pdf_path), str(raised.exception))

    def test_confirm_preflight_rejects_invalid_payload_contract(self) -> None:
        try:
            import fitz  # type: ignore  # noqa: F401
        except Exception as exc:
            self.skipTest(f"PyMuPDF unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "invalid-confirm-source.pdf"
            self._write_numbered_pdf(pdf_path, ["ELECTRICAL LEGEND ABBREVIATIONS POWER ONE-LINE LEGEND"])
            service = RecreationService(tmp_path / "data")
            project = service.create_project("Invalid confirm project")
            imported = service.import_files(project.id, [str(pdf_path)])
            review = service.run_preflight(project.id)

            with self.assertRaises(ValueError):
                service.confirm_preflight(project.id, "not a payload")

            invalid_payloads = [
                {**review, "disciplines": ["Not A Discipline"]},
                {**review, "legendPages": [True]},
                {**review, "legendPages": [0]},
                {**review, "legendPages": [999]},
                {
                    **review,
                    "pageRoles": [
                        {
                            "sourceFileId": imported["files"][0]["id"],
                            "page": True,
                            "role": "legend_reference",
                            "confidence": 0.5,
                            "reason": "bad",
                        }
                    ],
                },
                {
                    **review,
                    "pageRoles": [
                        {
                            "sourceFileId": imported["files"][0]["id"],
                            "page": 999,
                            "role": "legend_reference",
                            "confidence": 0.5,
                            "reason": "bad",
                        }
                    ],
                },
                {
                    **review,
                    "pageRoles": [
                        {
                            "sourceFileId": imported["files"][0]["id"],
                            "page": 1,
                            "role": "not_a_role",
                            "confidence": 0.5,
                            "reason": "bad",
                        }
                    ],
                },
                {
                    **review,
                    "pageRoles": [
                        {
                            "sourceFileId": "missing_source",
                            "page": 1,
                            "role": "legend_reference",
                            "confidence": 0.5,
                            "reason": "bad",
                        }
                    ],
                },
            ]

            for payload in invalid_payloads:
                with self.subTest(payload=payload):
                    with self.assertRaises(ValueError):
                        service.confirm_preflight(project.id, payload)

    def test_preflight_route_returns_400_for_invalid_confirmation(self) -> None:
        try:
            from fastapi import HTTPException
            from recreation_extractor.app import ConfirmPreflightRequest, create_app
        except Exception as exc:
            self.skipTest(f"FastAPI dependencies unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(Path(tmp) / "data")
            confirm_preflight = self._route(app, "/projects/{project_id}/preflight", "PUT")
            service = RecreationService(Path(tmp) / "data")
            project = service.create_project("Invalid preflight route project")

            with self.assertRaises(HTTPException) as raised:
                confirm_preflight(
                    project.id,
                    ConfirmPreflightRequest(payload={"disciplines": ["Not A Discipline"], "legendPages": [], "pageRoles": []}),
                )

            self.assertEqual(raised.exception.status_code, 400)

    def test_import_file_selection_rejects_bool_pages(self) -> None:
        try:
            from pydantic import ValidationError
            from recreation_extractor.app import ImportFileSelection
        except Exception as exc:
            self.skipTest(f"FastAPI dependencies unavailable: {exc}")

        with self.assertRaises(ValidationError):
            ImportFileSelection.model_validate({"path": "/tmp/source.pdf", "pages": [True]})

    def test_preflight_suggests_template_id_from_stored_template_columns(self) -> None:
        try:
            import fitz  # type: ignore  # noqa: F401
        except Exception as exc:
            self.skipTest(f"PyMuPDF unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "preflight-template-source.pdf"
            self._write_numbered_pdf(pdf_path, ["ELECTRICAL LEGEND ABBREVIATIONS POWER ONE-LINE LEGEND"])
            service = RecreationService(tmp_path / "data")
            service.store.upsert_hierarchy_template(
                "template_electrical",
                "Electrical standard",
                {"disciplines": ["Electrical"], "description": "Saved"},
            )
            project = service.create_project("Preflight template project")
            service.import_files(project.id, [str(pdf_path)])

            review = service.run_preflight(project.id)

            self.assertIn("template_electrical", review["suggestedTemplateIds"])
            template = service.store.list_hierarchy_templates()[0]
            self.assertEqual(template["id"], "template_electrical")
            self.assertEqual(template["name"], "Electrical standard")

    def test_pdf_preview_routes_return_page_metadata_and_webp_thumbnail(self):
        try:
            from recreation_extractor.app import create_app
        except Exception as exc:
            self.skipTest(f"FastAPI dependencies unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            pdf_path = tmp_path / "preview-source.pdf"
            self._write_numbered_pdf(pdf_path, ["PREVIEW PAGE 1", "PREVIEW PAGE 2", "PREVIEW PAGE 3"])
            app = create_app(tmp_path / "data")
            preview_pdf = self._route(app, "/pdf-preview", "GET")
            preview_image = self._route(app, "/pdf-preview/page-image", "GET")

            preview = preview_pdf(str(pdf_path), 54)
            self.assertEqual(preview["pageCount"], 3)
            self.assertEqual([page["page"] for page in preview["pages"]], [1, 2, 3])
            self.assertTrue(preview["pages"][1]["thumbnailUrl"].endswith("page=2&dpi=54"))

            response = preview_image(str(pdf_path), 2, 54)
            self.assertEqual(response.media_type, "image/webp")
            self.assertGreater(len(response.body), 100)

    def test_routes_list_layout_options_and_update_drawing(self):
        try:
            from fastapi import HTTPException
            from recreation_extractor.app import CreateProjectRequest, ImportFilesRequest, create_app
        except Exception as exc:
            self.skipTest(f"FastAPI dependencies unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            first_pdf = tmp_path / "pid-001.pdf"
            second_pdf = tmp_path / "pid-002.pdf"
            self._write_continuation_pdf(first_pdf, "right", "TO SUPPLY HEADER", "DEMO-ME-4CHW02")
            self._write_continuation_pdf(second_pdf, "left", "FROM SUPPLY HEADER", "DEMO-ME-4CHW01")

            app = create_app(tmp_path / "data")
            create_project = self._route(app, "/projects", "POST")
            import_files = self._route(app, "/projects/{project_id}/imports", "POST")
            start_stitch = self._route(app, "/projects/{project_id}/jobs/stitch", "POST")
            get_job = self._route(app, "/jobs/{job_id}", "GET")
            list_options = self._route(app, "/projects/{project_id}/layout-options", "GET")
            get_drawing = self._route(app, "/projects/{project_id}/drawings/{drawing_id}", "GET")
            update_drawing = self._route(app, "/projects/{project_id}/drawings/{drawing_id}", "PUT")

            project = create_project(CreateProjectRequest(name="API stitch fixture"))
            imported = import_files(
                project["id"],
                ImportFilesRequest(paths=[str(first_pdf), str(second_pdf)]),
            )
            self.assertEqual(len(imported["files"]), 2)

            stitch_response = start_stitch(project["id"])
            status = self._wait_for_api_job(get_job, stitch_response["jobId"])
            self.assertEqual(status["status"], "completed", status.get("error"))

            options = list_options(project["id"])
            self.assertGreaterEqual(len(options), 2)
            drawing_id = options[0]["drawingId"]

            drawing = get_drawing(project["id"], drawing_id)
            drawing["name"] = "Reviewed stitch drawing"

            updated = update_drawing(project["id"], drawing_id, drawing)
            self.assertEqual(updated["name"], "Reviewed stitch drawing")

            with self.assertRaises(HTTPException) as raised:
                get_drawing(project["id"], "missing")
            self.assertEqual(raised.exception.status_code, 404)

    def test_stitch_and_layout_routes_validate_project_before_work(self):
        try:
            from fastapi import HTTPException
            from recreation_extractor.app import CreateProjectRequest, create_app
        except Exception as exc:
            self.skipTest(f"FastAPI dependencies unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(Path(tmp) / "data")
            create_project = self._route(app, "/projects", "POST")
            start_stitch = self._route(app, "/projects/{project_id}/jobs/stitch", "POST")
            list_options = self._route(app, "/projects/{project_id}/layout-options", "GET")

            with self.assertRaises(HTTPException) as raised:
                start_stitch("missing_project")
            self.assertEqual(raised.exception.status_code, 404)

            project = create_project(CreateProjectRequest(name="No imports yet"))
            with self.assertRaises(HTTPException) as raised:
                start_stitch(project["id"])
            self.assertEqual(raised.exception.status_code, 400)
            self.assertIn("No source files imported", raised.exception.detail)

            with self.assertRaises(HTTPException) as raised:
                list_options("missing_project")
            self.assertEqual(raised.exception.status_code, 404)

    def test_drawing_routes_validate_project_before_drawing_payload(self):
        try:
            from fastapi import HTTPException
            from recreation_extractor.app import create_app
        except Exception as exc:
            self.skipTest(f"FastAPI dependencies unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(Path(tmp) / "data")
            get_drawing = self._route(app, "/projects/{project_id}/drawings/{drawing_id}", "GET")
            update_drawing = self._route(app, "/projects/{project_id}/drawings/{drawing_id}", "PUT")

            with self.assertRaises(HTTPException) as raised:
                get_drawing("missing_project", "drawing_missing")
            self.assertEqual(raised.exception.status_code, 404)

            with self.assertRaises(HTTPException) as raised:
                update_drawing("missing_project", "drawing_missing", "bad payload")
            self.assertEqual(raised.exception.status_code, 404)

    def _wait_for_job(self, service: RecreationService, job_id: str) -> dict:
        status = self._wait_for_terminal_status(service, job_id)
        if status["status"] == "failed":
            self.fail(status["error"])
        return status["result"]

    def _wait_for_terminal_status(self, service: RecreationService, job_id: str) -> dict:
        for _ in range(100):
            status = service.jobs.get(job_id)
            if status["status"] in {"completed", "failed"}:
                return status
            time.sleep(0.02)
        self.fail(f"Job {job_id} did not finish")

    def _wait_for_api_job(self, get_job, job_id: str) -> dict:
        for _ in range(100):
            status = get_job(job_id)
            if status["status"] in {"completed", "failed"}:
                return status
            time.sleep(0.02)
        self.fail(f"Job {job_id} did not finish")

    def _route(self, app, path: str, method: str):
        for route in app.routes:
            if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
                return route.endpoint
        self.fail(f"Route {method} {path} is not registered")

    def _write_continuation_pdf(self, path: Path, edge: str, direction_text: str, sheet_ref: str) -> None:
        try:
            from reportlab.pdfgen import canvas
        except Exception:
            self.skipTest("reportlab not installed")

        c = canvas.Canvas(str(path), pagesize=(1000, 700))
        if edge == "right":
            c.line(820, 350, 965, 350)
            c.line(965, 350, 940, 365)
            c.line(965, 350, 940, 335)
            c.drawString(760, 372, '16"-CHWS-CS02')
            c.drawString(805, 390, direction_text)
            c.drawString(805, 408, sheet_ref)
        else:
            c.line(35, 350, 180, 350)
            c.line(35, 350, 60, 365)
            c.line(35, 350, 60, 335)
            c.drawString(30, 372, '16"-CHWS-CS02')
            c.drawString(30, 390, direction_text)
            c.drawString(30, 408, sheet_ref)
        c.save()

    def _write_numbered_pdf(self, path: Path, labels: list[str]) -> None:
        try:
            from reportlab.pdfgen import canvas
        except Exception:
            self.skipTest("reportlab not installed")

        c = canvas.Canvas(str(path), pagesize=(612, 792))
        for index, label in enumerate(labels, start=1):
            c.setFont("Helvetica", 14)
            c.drawString(72, 720, label)
            c.drawString(72, 700, f"SHEET {index}")
            c.showPage()
        c.save()


if __name__ == "__main__":
    unittest.main()
