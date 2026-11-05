import unittest

from recreation_extractor.pid_stitch.matching import rank_continuation_matches
from recreation_extractor.pid_stitch.models import ContinuationCandidate


class PidStitchMatchingTests(unittest.TestCase):
    def test_scores_exact_sheet_line_and_to_from_match_highest(self):
        candidates = [
            self._candidate("a", "src_a", "to", "DEMO-ME-4CHW02", '16"-CHWS-CS02', "CHWS", "right"),
            self._candidate("b", "src_b", "from", "DEMO-ME-4CHW01", '16"-CHWS-CS02', "CHWS", "left"),
            self._candidate("c", "src_c", "from", "DEMO-ME-4CDA01", '6"-CDA-SS01', "CDA", "left"),
        ]
        matches = rank_continuation_matches(candidates)
        self.assertGreaterEqual(matches[0].score, 80)
        self.assertEqual(matches[0].sourceCandidateId, "a")
        self.assertEqual(matches[0].targetCandidateId, "b")
        self.assertIn("line tag", matches[0].reasons)
        self.assertIn("to/from", matches[0].reasons)

    def test_rejects_same_source_file_pairs(self):
        candidates = [
            self._candidate("a", "src_a", "to", "DEMO-ME-4CHW02", '16"-CHWS-CS02', "CHWS", "right"),
            self._candidate("b", "src_a", "from", "DEMO-ME-4CHW01", '16"-CHWS-CS02', "CHWS", "left"),
        ]
        matches = rank_continuation_matches(candidates)
        self.assertEqual(matches, [])

    def test_allows_same_source_file_different_page_pairs(self):
        candidates = [
            self._candidate("a", "src_a", "to", "DEMO-ME-4CHW02", '16"-CHWS-CS02', "CHWS", "right", page=1),
            self._candidate("b", "src_a", "from", "DEMO-ME-4CHW01", '16"-CHWS-CS02', "CHWS", "left", page=2),
        ]

        matches = rank_continuation_matches(candidates)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].sourceCandidateId, "a")
        self.assertEqual(matches[0].targetCandidateId, "b")

    def test_duplicate_candidates_select_one_to_one_matches(self):
        candidates = [
            self._candidate("a", "src_a", "to", "DEMO-ME-4CHW02", '16"-CHWS-CS02', "CHWS", "right"),
            self._candidate("b", "src_b", "from", "DEMO-ME-4CHW01", '16"-CHWS-CS02', "CHWS", "left"),
            self._candidate("c", "src_c", "from", "DEMO-ME-4CHW01", '16"-CHWS-CS02', "CHWS", "left"),
        ]
        matches = rank_continuation_matches(candidates)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].sourceCandidateId, "a")
        self.assertEqual(matches[0].targetCandidateId, "b")

    def test_orders_equal_scores_deterministically(self):
        candidates = [
            self._candidate("source_b", "src_b", "to", "DEMO-ME-4CHW02", '16"-CHWS-CS02', "CHWS", "right"),
            self._candidate("target_b", "src_d", "from", "DEMO-ME-4CHW01", '16"-CHWS-CS02', "CHWS", "left"),
            self._candidate("source_a", "src_a", "to", "DEMO-ME-4HWS02", '8"-HHWS-CS01', "HHWS", "right"),
            self._candidate("target_a", "src_c", "from", "DEMO-ME-4HWS01", '8"-HHWS-CS01', "HHWS", "left"),
        ]
        matches = rank_continuation_matches(candidates)
        self.assertEqual(
            [(match.sourceCandidateId, match.targetCandidateId) for match in matches],
            [("source_a", "target_a"), ("source_b", "target_b")],
        )

    def test_rejects_same_known_direction_pairs(self):
        candidates = [
            self._candidate("a", "src_a", "to", "DEMO-ME-4CHW02", '16"-CHWS-CS02', "CHWS", "right"),
            self._candidate("b", "src_b", "to", "DEMO-ME-4CHW01", '16"-CHWS-CS02', "CHWS", "left"),
        ]
        matches = rank_continuation_matches(candidates)
        self.assertEqual(matches, [])

    def test_unknown_direction_match_remains_needs_review(self):
        candidates = [
            self._candidate("a", "src_a", "unknown", "DEMO-ME-4CHW01", '16"-CHWS-CS02', "CHWS", "right"),
            self._candidate("b", "src_b", "from", "DEMO-ME-4CHW01", '16"-CHWS-CS02', "CHWS", "left"),
        ]
        matches = rank_continuation_matches(candidates)
        self.assertGreaterEqual(matches[0].score, 80)
        self.assertEqual(matches[0].status, "needs_review")

    def test_partial_sheet_reference_does_not_match(self):
        source = self._candidate("a", "src_a", "to", "DEMO-ME-4CHW02", '16"-CHWS-CS02', "CHWS", "right")
        target = self._candidate("b", "src_b", "from", "DEMO-ME-4CHW020", '16"-CHWS-CS02', "CHWS", "left")
        target.evidenceText = 'FROM DEMO-ME-4CHW020 16"-CHWS-CS02'

        matches = rank_continuation_matches([source, target])

        self.assertNotIn("sheet reference", matches[0].reasons)

    def test_scores_reciprocal_sheet_identity_from_source_paths(self):
        candidates = [
            self._candidate("a", "src_hash_a", "to", "DEMO-ME-4CDA02", "", "CDA", "bottom"),
            self._candidate("b", "src_hash_b", "from", "DEMO-ME-4CDA01", "", "CDA", "top"),
        ]

        matches = rank_continuation_matches(
            candidates,
            source_paths={
                "src_hash_a": "/packages/DEMO-ME-4CDA01_ DEMO - MECHANICAL CDA GENERATION P&ID.pdf",
                "src_hash_b": "/packages/DEMO-ME-4CDA02_ DEMO - MECHANICAL CDA DRYERS P&ID.pdf",
            },
        )

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].status, "confirmed")
        self.assertGreaterEqual(matches[0].score, 80)
        self.assertIn("target sheet", matches[0].reasons)
        self.assertIn("source sheet", matches[0].reasons)
        self.assertIn("reciprocal sheet", matches[0].reasons)

    def test_rejects_general_notes_references_even_when_other_side_points_to_source_sheet(self):
        general_note = self._candidate("a", "src_chw02", "to", "DEMO-IE-0005", "", "", "bottom")
        general_note.evidenceText = "DEMO-IE-0005. GENERAL NOTES TO LOW POINT DRAINS"
        continuation = self._candidate("b", "src_chw01", "from", "DEMO-ME-4CHW02", "", "", "top")

        matches = rank_continuation_matches(
            [general_note, continuation],
            source_paths={
                "src_chw01": "/packages/DEMO-ME-4CHW01_ DEMO - MECHANICAL STANDARD CHILLER P&ID.pdf",
                "src_chw02": "/packages/DEMO-ME-4CHW02_ DEMO - MECHANICAL CHILLED WATER SYSTEM P&ID.pdf",
            },
        )

        self.assertEqual(matches, [])

    def test_rejects_one_sided_sheet_identity_when_other_side_has_no_process_anchor(self):
        drain_note = self._candidate("a", "src_chw02", "to", "", "", "", "bottom")
        drain_note.evidenceText = "TO LOW POINT DRAINS"
        continuation = self._candidate("b", "src_chw01", "from", "DEMO-ME-4CHW02", "", "", "top")

        matches = rank_continuation_matches(
            [drain_note, continuation],
            source_paths={
                "src_chw01": "/packages/DEMO-ME-4CHW01_ DEMO - MECHANICAL STANDARD CHILLER P&ID.pdf",
                "src_chw02": "/packages/DEMO-ME-4CHW02_ DEMO - MECHANICAL CHILLED WATER SYSTEM P&ID.pdf",
            },
        )

        self.assertEqual(matches, [])

    def test_rejects_duplicate_revision_files_with_same_drawing_number(self):
        candidates = [
            self._candidate("a", "src_pk", "to", "DEMO-ME-4CHW02", '20"-CWR-CS02', "CWR", "bottom"),
            self._candidate("b", "src_published", "from", "DEMO-ME-4CHW02", '20"-CWR-CS02', "CWR", "top"),
        ]

        matches = rank_continuation_matches(
            candidates,
            source_paths={
                "src_pk": "/packages/DEMO-ME-4CHW01_ DEMO - MECHANICAL STANDARD CHILLER P&ID Rev.A markup draft.pdf",
                "src_published": "/packages/DEMO-ME-4CHW01_ DEMO - MECHANICAL STANDARD CHILLER P&ID Rev.A markup published.pdf",
            },
        )

        self.assertEqual(matches, [])

    def test_rejects_one_sided_sheet_identity_to_different_sheet_reference(self):
        source = self._candidate("a", "src_chw01", "to", "DEMO-ME-4CHW02", '20"-CWR-CS02', "CWR", "bottom")
        target = self._candidate("b", "src_chw02", "from", "DEMO-ME-4CHW03", "", "", "bottom")

        matches = rank_continuation_matches(
            [source, target],
            source_paths={
                "src_chw01": "/packages/DEMO-ME-4CHW01_ DEMO - MECHANICAL STANDARD CHILLER P&ID.pdf",
                "src_chw02": "/packages/DEMO-ME-4CHW02_ DEMO - MECHANICAL CHILLED WATER SYSTEM P&ID.pdf",
            },
        )

        self.assertEqual(matches, [])

    def _candidate(self, id, source, direction, sheet, line, system, edge, page=1):
        return ContinuationCandidate(
            id=id,
            sourceFileId=source,
            page=page,
            sheetRef=sheet,
            direction=direction,
            label=f"{direction.upper()} {sheet} {line}",
            lineTag=line,
            system=system,
            edge=edge,
            position={"x": 1.0, "y": 1.0},
            bounds={"x": 1.0, "y": 1.0, "width": 10.0, "height": 10.0},
            confidence=0.9,
            evidenceText=f"{direction.upper()} {sheet} {line}",
        )


if __name__ == "__main__":
    unittest.main()
