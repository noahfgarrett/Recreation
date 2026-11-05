import unittest

from recreation_extractor.pid_stitch.models import ContinuationCandidate, PageEvidence, TextSpan
from recreation_extractor.pid_stitch.system_colors import (
    FALLBACK_PALETTE,
    discover_system_color_map,
    system_for_text,
)


class PidStitchSystemColorTests(unittest.TestCase):
    def test_discovers_water_and_unknown_electrical_systems(self):
        pages = [
            self._page(
                "src_a",
                [
                    '12"-CHWS-CS02',
                    '8"-CWR-CS01',
                    "480V-FEEDER-MCC-01",
                    "FUTURE PROCESS CONNECTION",
                ],
            )
        ]

        color_map = discover_system_color_map(pages, [], {"src_a": "DEMO-EL-480V-Electrical-Feeder.pdf"})

        self.assertIn("CHW", color_map.entries)
        self.assertIn("CW", color_map.entries)
        self.assertIn("480V", color_map.entries)
        self.assertIn("FUTURE", color_map.entries)
        self.assertEqual(color_map.entries["CHW"].color, FALLBACK_PALETTE[0])
        self.assertTrue(color_map.entries["480V"].color.startswith("#"))

    def test_process_sheets_ignore_incidental_electrical_annotation_systems(self):
        pages = [
            self._page(
                "src_a",
                [
                    '12"-CHWS-CS02',
                    '10"-HHWR-CS02',
                    "480V-FEEDER-MCC-01",
                    "PANEL NOTE",
                ],
            )
        ]

        color_map = discover_system_color_map(pages, [], {"src_a": "DEMO-ME-4HHW02.pdf"})

        self.assertIn("CHW", color_map.entries)
        self.assertIn("HHW", color_map.entries)
        self.assertNotIn("480V", color_map.entries)
        self.assertNotIn("PANEL", color_map.entries)

    def test_system_for_text_normalizes_related_tokens(self):
        color_map = discover_system_color_map(
            [self._page("src_a", ['12"-TCHWS-CS01', '16"-CHWR-CS02', '10"-HRWR-CS03'])],
            [],
            {},
        )

        self.assertEqual(system_for_text('12"-TCHWS-CS01', color_map), "CHW")
        self.assertEqual(system_for_text('16"-CHWR-CS02', color_map), "CHW")
        self.assertEqual(system_for_text('10"-HRWR-CS03', color_map), "HRW")
        self.assertEqual(system_for_text("TCHWS", color_map), "CHW")
        self.assertEqual(system_for_text("CHWR", color_map), "CHW")
        self.assertEqual(system_for_text("HRWR", color_map), "HRW")

    def test_discovers_plumbing_water_tokens_without_hyphenated_line_tags(self):
        color_map = discover_system_color_map(
            [
                self._page(
                    "src_a",
                    [
                        '10" POTCW',
                        "01-POTCW",
                        "01-ICW-BFP-01",
                        "DOMESTIC COLD WATER",
                        "PANEL",
                    ],
                )
            ],
            [],
            {"src_a": "DEMO-PB-3002 Domestic Water.pdf"},
        )

        self.assertIn("POTCW", color_map.entries)
        self.assertIn("ICW", color_map.entries)
        self.assertNotIn("PANEL", color_map.entries)
        self.assertEqual(system_for_text('10" POTCW', color_map), "POTCW")
        self.assertEqual(system_for_text("01-ICW-BFP-01", color_map), "ICW")

    def test_plumbing_component_words_do_not_become_systems(self):
        color_map = discover_system_color_map(
            [
                self._page(
                    "src_a",
                    [
                        '10" POTCW',
                        '6" GATE VALVE',
                        '8" HDPE',
                        "01-RPZ-01",
                        "01-DCVA-01",
                        '3" ABOVE CEILING',
                    ],
                )
            ],
            [],
            {"src_a": "DEMO-PB-3002 Domestic Water.pdf"},
        )

        self.assertIn("POTCW", color_map.entries)
        self.assertNotIn("GATE", color_map.entries)
        self.assertNotIn("HDPE", color_map.entries)
        self.assertNotIn("RPZ", color_map.entries)
        self.assertNotIn("DCVA", color_map.entries)
        self.assertNotIn("ABOVE", color_map.entries)

    def test_manager_review_words_do_not_become_system_legend_entries(self):
        color_map = discover_system_color_map(
            [
                self._page(
                    "src_a",
                    [
                        '6"-CDA-CS01',
                        '4" OF PIPE',
                        '6" THROUGH WALL',
                        '8" MANUAL VALVE',
                        '10" STRAINER',
                        '12" TANK INLET',
                        '14" WIDE OPENING',
                        '16" LIT PANEL',
                    ],
                )
            ],
            [],
            {},
        )

        self.assertIn("CDA", color_map.entries)
        for token in ("OF", "THROUGH", "MANUAL", "STRAINER", "TANK", "INLET", "WIDE", "LIT"):
            self.assertNotIn(token, color_map.entries)

    def test_common_aliases_roll_up_to_named_systems(self):
        color_map = discover_system_color_map(
            [self._page("src_a", ['6"-CA-CS01', '2"-SHHW-CS01'])],
            [],
            {},
        )

        self.assertIn("CDA", color_map.entries)
        self.assertIn("HHW", color_map.entries)
        self.assertNotIn("CA", color_map.entries)
        self.assertNotIn("SHHW", color_map.entries)

    def test_discovers_system_from_embedded_source_path_token(self):
        color_map = discover_system_color_map(
            [self._page("src_a", ["NO SYSTEM TEXT ON THIS PAGE"])],
            [],
            {"src_a": "DEMO-ME-4CHW01.pdf"},
        )

        self.assertIn("CHW", color_map.entries)

    def test_sheet_refs_and_equipment_tags_do_not_become_systems(self):
        color_map = discover_system_color_map(
            [self._page("src_a", ["DEMO-ME-4CHW01", "AHU-1", "HX-01"])],
            [],
            {},
        )

        self.assertNotIn("DEMO", color_map.entries)
        self.assertNotIn("AHU", color_map.entries)
        self.assertNotIn("HX", color_map.entries)

    def test_discovers_explicit_candidate_system_values(self):
        candidates = [
            self._candidate("cand_chw", "CHWS"),
            self._candidate("cand_hhw", "HHWR"),
            self._candidate("cand_cda", "CDA"),
        ]

        color_map = discover_system_color_map([], candidates, {})

        self.assertIn("CHW", color_map.entries)
        self.assertIn("HHW", color_map.entries)
        self.assertIn("CDA", color_map.entries)

    def test_palette_cycles_without_losing_systems(self):
        labels = [f'1"-SYS{i}-A' for i in range(20)]
        color_map = discover_system_color_map([self._page("src_a", labels)], [], {})

        self.assertGreaterEqual(len(color_map.entries), 20)
        for index in range(20):
            self.assertIn(f"SYS{index}", color_map.entries)
        self.assertTrue(all(entry.color.startswith("#") for entry in color_map.entries.values()))

    def _page(self, source_id, labels):
        spans = [
            TextSpan(str(label), 100.0, 100.0 + index * 20.0, 140.0, 12.0)
            for index, label in enumerate(labels)
        ]
        return PageEvidence(
            id=f"{source_id}_p1",
            sourceFileId=source_id,
            page=1,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=spans,
            vectorCount=0,
            vectorSegments=[],
        )

    def _candidate(self, candidate_id, system):
        return ContinuationCandidate(
            id=candidate_id,
            sourceFileId="src_a",
            page=1,
            sheetRef="",
            direction="unknown",
            label="",
            lineTag="",
            system=system,
            edge="inside",
            position={"x": 0.0, "y": 0.0},
            bounds={"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0},
            confidence=1.0,
            evidenceText="",
        )


if __name__ == "__main__":
    unittest.main()
