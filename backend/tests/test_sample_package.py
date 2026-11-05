import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from recreation_extractor.pid_stitch.evidence import extract_pid_evidence, find_continuation_candidates
from recreation_extractor.pid_stitch.matching import rank_continuation_matches


ROOT = Path(__file__).resolve().parents[2]


class SamplePackageTests(unittest.TestCase):
    """End to end on the generated three-sheet sample package: real PDFs, real extraction."""

    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory(prefix="recreation-sample-")
        out = Path(cls._tmp.name)
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "generate-sample-package.py"), "--out", str(out)],
            check=True,
            capture_output=True,
            text=True,
        )
        cls.source_paths = {f"src_{index}": str(path) for index, path in enumerate(sorted(out.glob("*.pdf")))}
        cls.pages = []
        for source_id, path in cls.source_paths.items():
            cls.pages.extend(extract_pid_evidence("sample", source_id, path, ocr_mode="never"))
        cls.candidates = find_continuation_candidates(cls.pages)
        cls.matches = rank_continuation_matches(cls.candidates, cls.source_paths)

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def test_generator_writes_three_single_page_sheets(self):
        self.assertEqual(len(self.source_paths), 3)
        self.assertEqual(len(self.pages), 3)
        self.assertTrue(all(page.textSpans and page.vectorSegments for page in self.pages))

    def test_edge_callouts_become_candidates_with_sheet_refs_and_line_tags(self):
        tagged = {(c.sourceFileId, c.direction, c.sheetRef, c.lineTag) for c in self.candidates if c.lineTag}
        self.assertIn(("src_0", "to", "DEMO-ME-4CHW02", '8"-CHWS-101'), tagged)
        self.assertIn(("src_1", "from", "DEMO-ME-4CHW01", '8"-CHWS-101'), tagged)
        self.assertIn(("src_2", "to", "DEMO-ME-4CHW01", '10"-CWS-201'), tagged)
        self.assertIn(("src_0", "from", "DEMO-ME-4CW01", '10"-CWS-201'), tagged)

    def test_each_callout_yields_one_candidate(self):
        tagged = [(c.sourceFileId, c.direction, c.sheetRef, c.lineTag) for c in self.candidates if c.lineTag]
        # Four lines cross sheets and each has a callout at both ends.
        self.assertEqual(len(tagged), 8)
        self.assertEqual(len(set(tagged)), 8)

    def test_equipment_tags_are_not_read_as_sheet_references(self):
        sheet_refs = {c.sheetRef for c in self.candidates if c.sheetRef}
        self.assertTrue(all(ref.startswith("DEMO-ME-") for ref in sheet_refs), sheet_refs)

    def test_nothing_is_left_for_review(self):
        self.assertEqual([m.status for m in self.matches if m.status != "confirmed"], [])

    def test_each_cross_sheet_line_is_confirmed_between_the_right_sheets(self):
        by_id = {candidate.id: candidate for candidate in self.candidates}
        confirmed = set()
        for match in self.matches:
            if match.status != "confirmed":
                continue
            source = by_id[match.sourceCandidateId]
            target = by_id[match.targetCandidateId]
            self.assertEqual(source.lineTag, target.lineTag, "a confirmed pair should agree on the line tag")
            confirmed.add((source.lineTag, frozenset({source.sourceFileId, target.sourceFileId})))

        self.assertEqual(
            confirmed,
            {
                ('8"-CHWS-101', frozenset({"src_0", "src_1"})),
                ('8"-CHWR-102', frozenset({"src_0", "src_1"})),
                ('10"-CWS-201', frozenset({"src_0", "src_2"})),
                ('10"-CWR-202', frozenset({"src_0", "src_2"})),
            },
        )


if __name__ == "__main__":
    unittest.main()
