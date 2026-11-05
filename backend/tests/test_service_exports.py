import tempfile
import time
import unittest
from pathlib import Path

from recreation_extractor.service import RecreationService


class ServiceExportTests(unittest.TestCase):
    def test_import_extract_and_export_workbook(self):
        with tempfile.TemporaryDirectory() as tmp:
            pdf_path = Path(tmp) / "pid-001.pdf"
            self._write_pdf(pdf_path)
            service = RecreationService(Path(tmp) / "data")
            project = service.create_project("Fixture")
            service.import_files(project.id, [str(pdf_path)])
            sources = service.store.list_source_files(project.id)
            self.assertEqual(len(sources), 1)
            job_id = service.start_extract_job(project.id)
            graph_result = None
            for _ in range(100):
                status = service.jobs.get(job_id)
                if status["status"] == "completed":
                    graph_result = status["result"]
                    break
                if status["status"] == "failed":
                    self.fail(status["error"])
                time.sleep(0.02)
            self.assertIsNotNone(graph_result)
            self.assertGreaterEqual(graph_result["nodes"], 2)
            export = service.export(project.id, "xlsx")
            self.assertTrue(Path(export["path"]).exists())

    def _write_pdf(self, path: Path):
        try:
            from reportlab.pdfgen import canvas
        except Exception:
            self.skipTest("reportlab not installed")
        c = canvas.Canvas(str(path))
        c.drawString(72, 720, "P-101A XV-101 PT-101 LEGEND TO PID-002 CBL-1001")
        c.save()


if __name__ == "__main__":
    unittest.main()
