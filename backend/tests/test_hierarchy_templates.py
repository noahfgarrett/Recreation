from __future__ import annotations

import unittest
from tempfile import TemporaryDirectory

from recreation_extractor.hierarchy.preflight import PreflightPageSummary
from recreation_extractor.hierarchy.templates import build_template_payload, score_template_match
from recreation_extractor.models import SourceFile
from recreation_extractor.service import RecreationService


class HierarchyTemplatesTest(unittest.TestCase):
    def test_build_template_payload_keeps_review_shape(self) -> None:
        review = {
            "projectId": "project_a",
            "disciplines": ["Electrical"],
            "legendPages": [1, 2],
            "pageRoles": [
                {"sourceFileId": "source_a", "page": 1, "role": "legend_reference", "confidence": 0.9, "reason": "Legend heading"}
            ],
            "tableFamilies": ["panel_schedule"],
        }

        template = build_template_payload("template_a", "Site Electrical", review)

        self.assertEqual(template["id"], "template_a")
        self.assertEqual(template["name"], "Site Electrical")
        self.assertEqual(template["disciplines"], ["Electrical"])
        self.assertEqual(template["payload"]["legendPages"], [1, 2])

    def test_score_template_match_scores_shared_disciplines_and_table_families(self) -> None:
        review = {
            "disciplines": ["Electrical"],
            "legendPages": [1],
            "pageRoles": [],
            "tableFamilies": ["panel_schedule"],
        }
        template = build_template_payload(
            "template_a",
            "Site Electrical",
            {
                "disciplines": ["Electrical"],
                "legendPages": [1, 2],
                "pageRoles": [],
                "tableFamilies": ["panel_schedule", "equipment_schedule"],
            },
        )

        self.assertGreaterEqual(score_template_match(template, review), 0.75)

    def test_run_preflight_ranks_matching_template_ahead_of_name_order(self) -> None:
        with TemporaryDirectory() as data_dir:
            service = RecreationService(data_dir)
            project = service.create_project("Template Ranking")
            service.store.add_source_file(
                SourceFile(
                    id="source_a",
                    projectId=project.id,
                    path="/tmp/source-a.pdf",
                    name="source-a.pdf",
                    sha256="abc123",
                    pageCount=2,
                )
            )
            for template_id, name, discipline, table_family in [
                ("template_arch", "A Architectural", "CSA", "mechanical_schedule"),
                ("template_bms", "B BAS", "Controls / BAS", "io_schedule"),
                ("template_fire", "C Fire", "Fire Alarm", "cable_schedule"),
                ("template_electrical", "Z Electrical", "Electrical", "panel_schedule"),
            ]:
                template = build_template_payload(
                    template_id,
                    name,
                    {
                        "disciplines": [discipline],
                        "legendPages": [1],
                        "pageRoles": [],
                        "tableFamilies": [table_family],
                    },
                )
                service.store.upsert_hierarchy_template(template_id, name, template)

            service._preflight_page_summaries = lambda _source_id, _path: [
                PreflightPageSummary("source_a", 1, "ELECTRICAL SYMBOLS AND ABBREVIATIONS LEGEND"),
                PreflightPageSummary("source_a", 2, "PANEL SCHEDULE MDP"),
            ]
            service._persist_preflight_page_count = lambda _project_id, _source_row, _page_count: None

            review = service.run_preflight(project.id)

        self.assertIn("template_electrical", review["suggestedTemplateIds"])
        self.assertEqual(review["suggestedTemplateIds"][0], "template_electrical")
        self.assertNotIn("template_arch", review["suggestedTemplateIds"])


if __name__ == "__main__":
    unittest.main()
