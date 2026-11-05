import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import fitz

from recreation_extractor.pid_stitch.evidence import extract_pid_evidence
from recreation_extractor.pid_stitch.models import TextSpan


ROOT = Path(__file__).resolve().parents[2]


def _write_image_only_pdf(path: Path) -> None:
    """One page that is a single raster image with no text layer, like a scan."""
    pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 400, 300), False)
    pix.set_rect(pix.irect, (250, 250, 250))
    doc = fitz.open()
    page = doc.new_page(width=792, height=612)
    page.insert_image(page.rect, pixmap=pix)
    doc.save(path)
    doc.close()


class ScannedPageOcrTriggerTests(unittest.TestCase):
    def test_auto_mode_runs_ocr_on_image_only_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scan.pdf"
            _write_image_only_pdf(path)
            ocr_span = TextSpan("P-101", 100.0, 100.0, 40.0, 12.0)
            with patch(
                "recreation_extractor.pid_stitch.evidence._extract_ocr_text_spans",
                return_value=([ocr_span], "ocr"),
            ) as ocr:
                pages = extract_pid_evidence("project_a", "src_a", path)

        self.assertTrue(ocr.called)
        extraction = pages[0].metadata["textExtraction"]
        self.assertEqual(extraction["vectorCount"], 0)
        self.assertGreaterEqual(extraction["imageCoverage"], 0.9)
        self.assertEqual(extraction["mode"], "native+ocr")
        self.assertEqual([span.text for span in pages[0].textSpans], ["P-101"])

    def test_never_mode_still_skips_ocr_on_image_only_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "scan.pdf"
            _write_image_only_pdf(path)
            with patch("recreation_extractor.pid_stitch.evidence._extract_ocr_text_spans") as ocr:
                pages = extract_pid_evidence("project_a", "src_a", path, ocr_mode="never")

        self.assertFalse(ocr.called)
        self.assertEqual(pages[0].textSpans, [])


@unittest.skipUnless(shutil.which("tesseract"), "tesseract is not installed")
class RasterStressPackageOcrTests(unittest.TestCase):
    """Real OCR on the scanned-style stress sheets (skew, speckle, low contrast)."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="recreation-raster-")
        out = Path(cls._tmp.name)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "generate-stress-fixtures.py"), "--pages", "2", "--out", str(out)],
            check=True,
            capture_output=True,
            text=True,
        )
        cls.truth = json.loads((out / "manifest.json").read_text())["groundTruth"]["raster_scanned_pid"]["tags"]
        cls.pages = extract_pid_evidence("stress", "src_raster", out / "raster_scanned_pid_package.pdf")

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_auto_mode_ocrs_every_scanned_sheet(self):
        self.assertEqual({page.metadata["textExtraction"]["vectorCount"] for page in self.pages}, {0})
        self.assertTrue(all(page.metadata["textExtraction"]["ocrSpanCount"] > 0 for page in self.pages))

    def test_auto_mode_recovers_a_useful_share_of_the_tags(self):
        text = " ".join(span.text for page in self.pages for span in page.textSpans)
        found = [tag for tag in self.truth if re.search(r"(?<![A-Z0-9-])" + re.escape(tag) + r"(?![A-Z0-9])", text)]
        # OCR on these deliberately degraded sheets is imperfect; locally it finds 30 of 60.
        self.assertGreaterEqual(len(found), 20, f"found {len(found)} of {len(self.truth)} tags")


if __name__ == "__main__":
    unittest.main()
