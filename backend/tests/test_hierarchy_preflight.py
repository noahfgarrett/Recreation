from __future__ import annotations

import unittest

from recreation_extractor.hierarchy.preflight import PreflightPageSummary, build_preflight_review


class HierarchyPreflightTest(unittest.TestCase):
    def test_detects_electrical_legend_and_panel_schedule_roles(self) -> None:
        pages = [
            PreflightPageSummary("source_a", 1, "ELECTRICAL LEGEND ABBREVIATIONS POWER ONE-LINE LEGEND"),
            PreflightPageSummary("source_a", 164, "PANEL SCHEDULE DESIGNATION RW4PP1E4 SUPPLY FROM RW4MDP4C6"),
            PreflightPageSummary("source_a", 178, "OVERALL ONE LINE DIAGRAM HV YARD SWITCHGEAR GENERATOR"),
        ]

        review = build_preflight_review("project_a", pages, templates=[])

        self.assertEqual(review.disciplines[0], "Electrical")
        self.assertIn(1, review.legendPages)
        roles = {(item.page, item.role) for item in review.pageRoles}
        self.assertIn((1, "legend_reference"), roles)
        self.assertIn((164, "panel_schedule"), roles)
        self.assertIn((178, "one_line"), roles)
        self.assertIn("panel_schedule", review.tableFamilies)

    def test_detects_mixed_process_and_ic_package(self) -> None:
        pages = [
            PreflightPageSummary("source_b", 2, "P&ID LEGEND LINE DESIGNATION EQUIPMENT TAGGING LEGEND"),
            PreflightPageSummary("source_b", 12, "PIPING AND INSTRUMENTATION DIAGRAM P-101 FT-101"),
            PreflightPageSummary("source_b", 43, "INSTRUMENT INDEX LOOP NO I/O PANEL"),
        ]

        review = build_preflight_review("project_b", pages, templates=[])

        self.assertIn("Process / P&ID", review.disciplines)
        self.assertIn("Instrumentation & Control", review.disciplines)
        self.assertIn(2, review.legendPages)
        self.assertIn("instrument_index", review.tableFamilies)

    def test_pid_legend_symbols_page_is_legend_reference(self) -> None:
        pages = [PreflightPageSummary("source_pid", 3, "P&ID LEGEND SYMBOLS LINE DESIGNATION")]

        review = build_preflight_review("project_pid", pages, templates=[])

        self.assertEqual(review.disciplines, ["Process / P&ID"])
        self.assertEqual(review.legendPages, [3])
        self.assertEqual(review.pageRoles[0].role, "legend_reference")
        self.assertNotIn("No likely legend/reference page found.", review.warnings)

    def test_incidental_legend_text_does_not_mask_electrical_sheet_roles(self) -> None:
        pages = [
            PreflightPageSummary("source_e", 164, "PANEL SCHEDULE RW4PP1E4 ABBREVIATION LEGEND"),
            PreflightPageSummary(
                "source_e",
                178,
                "RSMSWG3C25 FROM HV YARD SWG SEE DRAWING U-E-202 13.8KV SWITCHGEAR ABBREVIATION LEGEND POWER ONE-LINE LEGEND",
            ),
        ]

        review = build_preflight_review("project_e", pages, templates=[])
        roles = {(item.page, item.role) for item in review.pageRoles}

        self.assertIn((164, "panel_schedule"), roles)
        self.assertIn((178, "one_line"), roles)
        self.assertEqual(review.legendPages, [])

    def test_low_confidence_missing_legend_yields_warning(self) -> None:
        pages = [PreflightPageSummary("source_c", 7, "FLOOR PLAN LEVEL 2 ROOM NAMES")]

        review = build_preflight_review("project_c", pages, templates=[])

        self.assertEqual(review.disciplines, ["Unknown"])
        self.assertEqual(review.legendPages, [])
        self.assertIn("No likely legend/reference page found.", review.warnings)
