from __future__ import annotations

import unittest

from recreation_extractor.hierarchy.models import (
    DISCIPLINES,
    HIERARCHY_VIEW_IDS,
    PAGE_ROLES,
    HierarchyView,
    PageRoleAssignment,
    PreflightReview,
    discipline_from_text,
    page_role_from_text,
    to_plain_dict,
)


class HierarchyModelsTest(unittest.TestCase):
    def test_disciplines_match_canonical_user_facing_buckets(self) -> None:
        self.assertEqual(
            DISCIPLINES,
            (
                "Electrical",
                "Process / P&ID",
                "Mechanical",
                "Mechanical Dry",
                "Mechanical Wet",
                "Plumbing",
                "Instrumentation & Control",
                "Security",
                "Fire Alarm",
                "Fire Protection",
                "Life Safety Services",
                "Telecom / Low Voltage",
                "Controls / BAS",
                "CSA",
                "General / Reference",
                "Mixed Package",
                "Unknown",
            ),
        )

    def test_page_roles_match_canonical_values(self) -> None:
        self.assertEqual(
            PAGE_ROLES,
            (
                "legend_reference",
                "abbreviations",
                "general_notes",
                "sheet_index",
                "one_line",
                "riser",
                "pid",
                "plan_view",
                "detail_sheet",
                "panel_schedule",
                "equipment_schedule",
                "line_list",
                "instrument_index",
                "loop_sheet",
                "cable_schedule",
                "io_schedule",
                "control_panel",
                "fire_alarm_riser",
                "security_riser",
                "plumbing_riser",
                "mechanical_schedule",
                "csa_plan_detail",
                "vendor_drawing",
                "unknown",
            ),
        )

    def test_hierarchy_view_ids_match_plan(self) -> None:
        self.assertEqual(
            HIERARCHY_VIEW_IDS,
            (
                "electrical_power",
                "commissioning_dependencies",
                "process_flow",
                "mechanical_system",
                "ic_loop",
                "security_device",
                "fire_life_safety",
                "plumbing_fire_protection",
                "equipment_asset",
                "location_area",
                "source_document",
                "overview_export",
            ),
        )

    def test_discpline_aliases_normalize_common_sheet_terms(self) -> None:
        self.assertEqual(discipline_from_text("ELECTRICAL ONE-LINE DIAGRAM"), "Electrical")
        self.assertEqual(discipline_from_text("PIPING AND INSTRUMENTATION DIAGRAM"), "Process / P&ID")
        self.assertEqual(discipline_from_text("I&C LOOP SHEET"), "Instrumentation & Control")
        self.assertEqual(discipline_from_text("CIVIL STRUCTURAL ARCHITECTURAL DETAILS"), "CSA")
        self.assertEqual(discipline_from_text("unlabeled sheet"), "Unknown")

    def test_page_role_aliases_normalize_common_headers(self) -> None:
        self.assertEqual(page_role_from_text("PANEL SCHEDULE RW4PP1E4"), "panel_schedule")
        self.assertEqual(page_role_from_text("OVERALL ONE LINE DIAGRAM"), "one_line")
        self.assertEqual(page_role_from_text("INSTRUMENT INDEX"), "instrument_index")
        self.assertEqual(page_role_from_text("LINE LIST"), "line_list")
        self.assertIn(page_role_from_text("GENERAL NOTES AND SYMBOLS"), {"legend_reference", "general_notes"})

    def test_preflight_review_serializes_to_frontend_shape(self) -> None:
        review = PreflightReview(
            projectId="project_a",
            status="draft",
            disciplines=["Electrical"],
            disciplineConfidence=0.91,
            legendPages=[1],
            legendConfidence=0.87,
            pageRoles=[
                PageRoleAssignment(sourceFileId="source_a", page=1, role="legend_reference", confidence=0.88, reason="legend heading")
            ],
            tableFamilies=["panel_schedule"],
            suggestedTemplateIds=["template_ref"],
            appliedTemplateId=None,
            warnings=[],
        )

        payload = to_plain_dict(review)

        self.assertEqual(payload["projectId"], "project_a")
        self.assertEqual(payload["disciplines"], ["Electrical"])
        self.assertEqual(payload["pageRoles"][0]["role"], "legend_reference")
        self.assertEqual(payload["tableFamilies"], ["panel_schedule"])

    def test_hierarchy_view_serializes_nodes_edges_and_metrics(self) -> None:
        view = HierarchyView(
            id="electrical_power",
            label="Electrical Power Tree",
            discipline="Electrical",
            nodes=[{"id": "node_a", "tag": "GEN-15", "kind": "equipment"}],
            edges=[{"id": "edge_a", "parentId": "node_a", "childId": "node_b", "kind": "feeds"}],
            metrics={"roots": 1},
        )

        payload = to_plain_dict(view)

        self.assertEqual(payload["id"], "electrical_power")
        self.assertEqual(payload["nodes"][0]["tag"], "GEN-15")
        self.assertEqual(payload["metrics"]["roots"], 1)


if __name__ == "__main__":
    unittest.main()
