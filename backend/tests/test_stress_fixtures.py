import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from recreation_extractor.extraction import extract_pdf, source_file_for_path
from recreation_extractor.graph import build_graph


ROOT = Path(__file__).resolve().parents[2]


class StressFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Generate into a temp dir so the run doesn't rewrite the committed fixtures.
        cls._tmp = tempfile.TemporaryDirectory(prefix="recreation-stress-")
        cls.fixture_dir = Path(cls._tmp.name)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "generate-stress-fixtures.py"), "--pages", "12", "--out", str(cls.fixture_dir)],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        cls.manifest = json.loads((cls.fixture_dir / "manifest.json").read_text())

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_vector_fixture_extracts_tags_and_review_items(self):
        source = source_file_for_path("stress_project", str(self.fixture_dir / "vector_pid_package_32.pdf"))
        source, pages, detections = extract_pdf(source)
        graph = build_graph("stress_project", detections)
        self.assertGreaterEqual(source.pageCount, 12)
        self.assertGreaterEqual(len(pages), 12)
        self.assertGreaterEqual(len(graph.nodes), 30)
        self.assertGreaterEqual(len(graph.reviewItems), 10)

    def test_cable_fixture_extracts_cable_ids(self):
        source = source_file_for_path("stress_cable", str(self.fixture_dir / "cable_continuation_package.pdf"))
        _source, _pages, detections = extract_pdf(source)
        cable_ids = [item for item in detections if item.kind == "cable_id"]
        continuations = [item for item in detections if item.kind == "continuation_ref"]
        self.assertGreaterEqual(len(cable_ids), 20)
        self.assertGreaterEqual(len(continuations), 8)


if __name__ == "__main__":
    unittest.main()
