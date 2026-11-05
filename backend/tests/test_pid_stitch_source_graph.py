import unittest

from recreation_extractor.pid_stitch.models import ContinuationCandidate, PageEvidence, TextSpan
from recreation_extractor.pid_stitch.source_graph import build_source_graph


class PidStitchSourceGraphTests(unittest.TestCase):
    def test_groups_chw_cw_equipment_and_continuations_into_assemblies(self):
        page = self._page(
            [
                'DEMO-ME-4CHW01 30"-CHWS-CS03 30"-CHWR-CS03 18"-CWS-CS01',
                "R-DEMO-CHW-CH-01 R-DEMO-CHW-CH-02 R-DEMO-CHW-CH-03",
                "R-DEMO-CHW-P-01 R-DEMO-CHW-P-02 R-DEMO-CW-P-01",
                "R-DEMO-CW-CT-01 R-DEMO-CW-HX-01",
            ]
        )
        candidates = [
            self._candidate("to_chw", '30"-CHWS-CS03', "CHWS", "DEMO-ME-4CHW02"),
            self._candidate("to_cw", '18"-CWS-CS01', "CWS", "DEMO-ME-4CHW02"),
            self._candidate("to_hhw", '12"-HHWS-CS01', "HHWS", "DEMO-ME-4HHW02"),
        ]

        graph = build_source_graph(
            [page],
            candidates,
            {"src_chw": "/packages/DEMO-ME-4CHW01_ DEMO - MECHANICAL STANDARD CHILLER P&ID.pdf"},
            "CHW / CW",
        )

        self.assertEqual(graph.groupName, "CHW / CW")
        self.assertEqual(graph.sourcePageIds, ["src_chw_p1"])
        self.assertEqual(graph.metrics["equipmentTags"], 8)
        self.assertEqual(graph.metrics["lineTags"], 3)
        self.assertEqual(graph.metrics["continuations"], 2)
        assemblies = {assembly.kind: assembly for assembly in graph.assemblies}
        self.assertEqual(assemblies["chiller_bank"].equipmentTags, ["R-DEMO-CHW-CH-01", "R-DEMO-CHW-CH-02", "R-DEMO-CHW-CH-03"])
        self.assertEqual(assemblies["chw_pumps"].equipmentTags, ["R-DEMO-CHW-P-01", "R-DEMO-CHW-P-02"])
        self.assertEqual(assemblies["cw_pumps"].equipmentTags, ["R-DEMO-CW-P-01"])
        self.assertEqual(assemblies["cooling_water"].equipmentTags, ["R-DEMO-CW-CT-01", "R-DEMO-CW-HX-01"])
        self.assertEqual([candidate.id for candidate in graph.continuations], ["to_chw", "to_cw"])

    def test_groups_fractional_icw_line_tags_under_icw_system(self):
        page = self._page(['1 1/2"-ICW-PC05'])

        graph = build_source_graph([page], [], {"src_chw": "/packages/DEMO-ME-4ICW01.pdf"}, "ICW")

        self.assertEqual(graph.lineTagsBySystem, {"ICW": ['1 1/2"-ICW-PC05']})

    def _page(self, texts: list[str]) -> PageEvidence:
        return PageEvidence(
            id="src_chw_p1",
            sourceFileId="src_chw",
            page=1,
            width=1000.0,
            height=700.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 1000.0, "height": 700.0},
            textSpans=[
                TextSpan(text=text, x=100.0, y=100.0 + index * 20.0, width=600.0, height=12.0)
                for index, text in enumerate(texts)
            ],
            vectorCount=0,
            vectorSegments=[],
        )

    def _candidate(self, candidate_id: str, line_tag: str, system: str, sheet_ref: str) -> ContinuationCandidate:
        return ContinuationCandidate(
            id=candidate_id,
            sourceFileId="src_chw",
            page=1,
            sheetRef=sheet_ref,
            direction="to",
            label=f"TO {line_tag} / {sheet_ref}",
            lineTag=line_tag,
            system=system,
            edge="right",
            position={"x": 950.0, "y": 300.0},
            bounds={"x": 900.0, "y": 290.0, "width": 90.0, "height": 18.0},
            confidence=0.9,
            evidenceText=f"TO {line_tag} / {sheet_ref}",
        )


if __name__ == "__main__":
    unittest.main()
