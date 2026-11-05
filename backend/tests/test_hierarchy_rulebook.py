from __future__ import annotations

import unittest

from recreation_extractor.hierarchy.rulebook import build_rulebook
from recreation_extractor.pid_stitch.models import BoundsDict, PageEvidence, TextSpan


class HierarchyRulebookTest(unittest.TestCase):
    def test_builds_acronyms_from_legend_page_text_spans(self) -> None:
        page = PageEvidence(
            id="page_1",
            sourceFileId="source_a",
            page=1,
            width=1000,
            height=700,
            rotation=0,
            cropBounds=BoundsDict(x=0, y=0, width=1000, height=700),
            textSpans=[
                TextSpan("SWG", 10, 10, 30, 10),
                TextSpan("SWITCHGEAR", 80, 10, 100, 10),
                TextSpan("GEN", 10, 30, 30, 10),
                TextSpan("GENERATOR", 80, 30, 100, 10),
            ],
            vectorCount=0,
        )
        preflight = {
            "projectId": "project_a",
            "disciplines": ["Electrical"],
            "legendPages": [1],
            "warnings": [],
        }

        rulebook = build_rulebook("project_a", [page], preflight)

        self.assertEqual(rulebook.acronymMap["SWG"], "SWITCHGEAR")
        self.assertEqual(rulebook.acronymMap["GEN"], "GENERATOR")
        self.assertEqual(rulebook.disciplines, ["Electrical"])
        self.assertEqual(rulebook.legendPages, [1])

    def test_uses_page_role_source_identity_for_legend_filter_and_evidence(self) -> None:
        legend_page = PageEvidence(
            id="source_a_page_1",
            sourceFileId="source_a",
            page=1,
            width=1000,
            height=700,
            rotation=0,
            cropBounds=BoundsDict(x=0, y=0, width=1000, height=700),
            textSpans=[
                TextSpan("SWG", 10, 10, 30, 10),
                TextSpan("SWITCHGEAR", 80, 10, 100, 10),
            ],
            vectorCount=0,
        )
        non_legend_page = PageEvidence(
            id="source_b_page_1",
            sourceFileId="source_b",
            page=1,
            width=1000,
            height=700,
            rotation=0,
            cropBounds=BoundsDict(x=0, y=0, width=1000, height=700),
            textSpans=[
                TextSpan("GEN", 10, 10, 30, 10),
                TextSpan("GENERATOR", 80, 10, 100, 10),
            ],
            vectorCount=0,
        )
        preflight = {
            "projectId": "project_a",
            "disciplines": ["Electrical"],
            "legendPages": [1],
            "pageRoles": [
                {
                    "sourceFileId": "source_a",
                    "page": 1,
                    "role": "legend_reference",
                    "confidence": 0.95,
                    "reason": "legend",
                }
            ],
            "warnings": [],
        }

        rulebook = build_rulebook("project_a", [legend_page, non_legend_page], preflight)

        self.assertEqual(rulebook.acronymMap, {"SWG": "SWITCHGEAR"})
        self.assertEqual(
            rulebook.sourceEvidence,
            [
                {
                    "sourceFileId": "source_a",
                    "pageId": "source_a_page_1",
                    "page": 1,
                    "type": "acronym",
                    "key": "SWG",
                    "value": "SWITCHGEAR",
                }
            ],
        )

    def test_confirmed_legend_pages_override_stale_legend_page_roles(self) -> None:
        stale_auto_legend = PageEvidence(
            id="source_a_page_1",
            sourceFileId="source_a",
            page=1,
            width=1000,
            height=700,
            rotation=0,
            cropBounds=BoundsDict(x=0, y=0, width=1000, height=700),
            textSpans=[
                TextSpan("BAD", 10, 10, 30, 10),
                TextSpan("STALE LEGEND", 80, 10, 100, 10),
            ],
            vectorCount=0,
        )
        confirmed_legend = PageEvidence(
            id="source_a_page_2",
            sourceFileId="source_a",
            page=2,
            width=1000,
            height=700,
            rotation=0,
            cropBounds=BoundsDict(x=0, y=0, width=1000, height=700),
            textSpans=[
                TextSpan("GEN", 10, 10, 30, 10),
                TextSpan("GENERATOR", 80, 10, 100, 10),
            ],
            vectorCount=0,
        )
        preflight = {
            "projectId": "project_a",
            "disciplines": ["Electrical"],
            "legendPages": [2],
            "pageRoles": [
                {
                    "sourceFileId": "source_a",
                    "page": 1,
                    "role": "legend_reference",
                    "confidence": 0.95,
                    "reason": "stale auto-detected legend",
                }
            ],
            "warnings": [],
        }

        rulebook = build_rulebook("project_a", [stale_auto_legend, confirmed_legend], preflight)

        self.assertEqual(rulebook.legendPages, [2])
        self.assertEqual(rulebook.acronymMap, {"GEN": "GENERATOR"})

    def test_confirmed_legend_pages_include_pages_with_stale_unknown_roles(self) -> None:
        page_one = PageEvidence(
            id="source_a_page_1",
            sourceFileId="source_a",
            page=1,
            width=1000,
            height=700,
            rotation=0,
            cropBounds=BoundsDict(x=0, y=0, width=1000, height=700),
            textSpans=[
                TextSpan("SWG", 10, 10, 30, 10),
                TextSpan("SWITCHGEAR", 80, 10, 100, 10),
            ],
            vectorCount=0,
        )
        page_two = PageEvidence(
            id="source_a_page_2",
            sourceFileId="source_a",
            page=2,
            width=1000,
            height=700,
            rotation=0,
            cropBounds=BoundsDict(x=0, y=0, width=1000, height=700),
            textSpans=[
                TextSpan("GEN", 10, 10, 30, 10),
                TextSpan("GENERATOR", 80, 10, 100, 10),
            ],
            vectorCount=0,
        )
        preflight = {
            "projectId": "project_a",
            "disciplines": ["Electrical"],
            "legendPages": [1, 2],
            "pageRoles": [
                {
                    "sourceFileId": "source_a",
                    "page": 1,
                    "role": "legend_reference",
                    "confidence": 0.95,
                    "reason": "auto",
                },
                {
                    "sourceFileId": "source_a",
                    "page": 2,
                    "role": "unknown",
                    "confidence": 0.25,
                    "reason": "stale",
                },
            ],
            "warnings": [],
        }

        rulebook = build_rulebook("project_a", [page_one, page_two], preflight)

        self.assertEqual(rulebook.acronymMap, {"SWG": "SWITCHGEAR", "GEN": "GENERATOR"})

    def test_confirmed_empty_legend_pages_do_not_extract_from_stale_page_roles(self) -> None:
        stale_auto_legend = PageEvidence(
            id="source_a_page_1",
            sourceFileId="source_a",
            page=1,
            width=1000,
            height=700,
            rotation=0,
            cropBounds=BoundsDict(x=0, y=0, width=1000, height=700),
            textSpans=[
                TextSpan("GEN", 10, 10, 30, 10),
                TextSpan("GENERATOR", 80, 10, 100, 10),
            ],
            vectorCount=0,
        )
        preflight = {
            "projectId": "project_a",
            "disciplines": ["Electrical"],
            "legendPages": [],
            "pageRoles": [
                {
                    "sourceFileId": "source_a",
                    "page": 1,
                    "role": "legend_reference",
                    "confidence": 0.95,
                    "reason": "stale auto-detected legend",
                }
            ],
            "warnings": [],
        }

        rulebook = build_rulebook("project_a", [stale_auto_legend], preflight)

        self.assertEqual(rulebook.acronymMap, {})


if __name__ == "__main__":
    unittest.main()
