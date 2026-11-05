import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from recreation_extractor.pid_stitch.layout import generate_layout_options
from recreation_extractor.pid_stitch.models import ContinuationCandidate, ContinuationMatch, DrawingObject, DrawingStyle, PageEvidence, TextSpan, VectorSegment
from recreation_extractor.pid_stitch.semantic_overlay import _apply_source_cluster_breathing, _is_page_edge_frame_vector, _system_corridor_points, _merge_nearby_same_system_routes, _normalize_semantic_body_position, _route_clusters_for_system, _route_points_around_protected_bounds, _route_semantic_lines_around_dense_pockets, _semantic_symbol_bounds_for_item, _snap_attached_connector_endpoints, _system_bus_geometry


class PidStitchLayoutTests(unittest.TestCase):
    def test_semantic_drawing_is_primary_and_keeps_source_overlay_auditable(self):
        page_a = self._page(
            "src_a_p1",
            "src_a",
            'DEMO-ME-4CHW01 16"-CHWS-CS02 R-DEMO-CHW-P-01 PIT-101',
        )
        page_a.rotation = 0
        page_a.textSpans = [
            TextSpan('16"-CHWS-CS02', 1120.0, 320.0, 130.0, 16.0),
            TextSpan('16"-CHWS-CS02 TO DEMO-ME-4CHW02', 1160.0, 300.0, 220.0, 16.0),
            TextSpan("R-DEMO-CHW-P-01", 420.0, 560.0, 150.0, 18.0),
            TextSpan("SHW-406-FTR103", 430.0, 590.0, 140.0, 16.0),
            TextSpan("PIT-101", 490.0, 612.0, 72.0, 16.0),
            TextSpan("AT-70", 510.0, 640.0, 72.0, 16.0),
        ]
        page_a.vectorSegments = [
            VectorSegment(
                id="src_a_p1:main",
                kind="line",
                points=[{"x": 220.0, "y": 320.0}, {"x": 1240.0, "y": 320.0}],
                bounds={"x": 220.0, "y": 320.0, "width": 1020.0, "height": 0.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=False,
            )
        ] + [
            VectorSegment(
                id="src_a_p1:pointer_marker",
                kind="polyline",
                points=[
                    {"x": 1188.0, "y": 304.0},
                    {"x": 1270.0, "y": 304.0},
                    {"x": 1292.0, "y": 320.0},
                    {"x": 1270.0, "y": 336.0},
                    {"x": 1188.0, "y": 336.0},
                    {"x": 1188.0, "y": 304.0},
                ],
                bounds={"x": 1188.0, "y": 304.0, "width": 104.0, "height": 32.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=False,
            )
        ]
        page_b = self._page(
            "src_b_p1",
            "src_b",
            'DEMO-ME-4CHW02 16"-CHWS-CS02 R-DEMO-CHW-CH-01 FIT-202',
        )
        page_b.rotation = 0
        page_b.textSpans = [
            TextSpan('16"-CHWS-CS02', 150.0, 320.0, 130.0, 16.0),
            TextSpan('16"-CHWS-CS02 FROM DEMO-ME-4CHW01', 44.0, 304.0, 240.0, 16.0),
            TextSpan("R-DEMO-CHW-CH-01", 520.0, 560.0, 150.0, 18.0),
            TextSpan("FIT-202", 590.0, 612.0, 72.0, 16.0),
        ]
        page_b.vectorSegments = [
            VectorSegment(
                id="src_b_p1:main",
                kind="line",
                points=[{"x": 150.0, "y": 320.0}, {"x": 1180.0, "y": 320.0}],
                bounds={"x": 150.0, "y": 320.0, "width": 1030.0, "height": 0.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=False,
            )
        ] + [
            VectorSegment(
                id="src_b_p1:pointer_marker",
                kind="polyline",
                points=[
                    {"x": 38.0, "y": 304.0},
                    {"x": 118.0, "y": 304.0},
                    {"x": 150.0, "y": 320.0},
                    {"x": 118.0, "y": 336.0},
                    {"x": 38.0, "y": 336.0},
                    {"x": 38.0, "y": 304.0},
                ],
                bounds={"x": 38.0, "y": 304.0, "width": 112.0, "height": 32.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=False,
            )
        ]
        candidate_a = self._candidate("a_to_b", "src_a", "to", '16"-CHWS-CS02', "CHWS", "right")
        candidate_a.position = {"x": 1240.0, "y": 320.0}
        candidate_a.bounds = {"x": 1188.0, "y": 304.0, "width": 104.0, "height": 32.0}
        candidate_b = self._candidate("b_from_a", "src_b", "from", '16"-CHWS-CS02', "CHWS", "left")
        candidate_b.position = {"x": 150.0, "y": 320.0}
        candidate_b.bounds = {"x": 38.0, "y": 304.0, "width": 112.0, "height": 32.0}
        external_candidate = self._candidate("b_external", "src_b", "to", '8"-CHWR-CS02', "CHWR", "right")
        external_candidate.position = {"x": 1180.0, "y": 720.0}
        match = ContinuationMatch("match_ab", "a_to_b", "b_from_a", 96.0, ["same line tag", "to/from"], "confirmed")

        options = generate_layout_options(
            "project_semantic",
            [page_a, page_b],
            [candidate_a, candidate_b, external_candidate],
            [match],
            {
                "src_a": "/packages/DEMO-ME-4CHW01_ DEMO - MECHANICAL STANDARD CHILLER P&ID.pdf",
                "src_b": "/packages/DEMO-ME-4CHW02_ DEMO - MECHANICAL CHILLED WATER P&ID.pdf",
            },
        )
        option, document = options[0]

        self.assertEqual(option.name, "Semantic Drawing")
        self.assertTrue(option.metrics["primaryOutput"])
        self.assertTrue(option.metrics["semanticDrawing"])
        self.assertTrue(option.metrics["semanticOverlay"])
        self.assertIn(
            "CHILLED WATER SYSTEM OVERVIEW",
            {obj.label for obj in document.objects if obj.metadata.get("semanticTitle") is True},
        )
        self.assertEqual(option.metrics["sourceMapObjects"], 0)
        self.assertIn("Source-driven Combined P&ID", {layout.name for layout, _document in options})
        self.assertIn("Semantic Overlay", {layout.name for layout, _document in options})
        overlay_option, overlay_document = next(item for item in options if item[0].name == "Semantic Overlay")
        self.assertFalse(overlay_option.metrics["primaryOutput"])
        self.assertTrue(any(obj.metadata.get("semanticSourceMap") is True for obj in overlay_document.objects))
        self.assertFalse(any(obj.metadata.get("semanticSourceMap") is True for obj in document.objects))
        semantic_objects = [obj for obj in document.objects if obj.metadata.get("semanticOverlay") is True]
        self.assertTrue(semantic_objects)
        self.assertFalse(any(obj.metadata.get("semanticSourceMap") is True for obj in semantic_objects))
        self.assertFalse(any(obj.metadata.get("semanticTracePipe") is True for obj in semantic_objects))
        self.assertGreater(document.visualQa["semanticGeneratedRouteObjects"], 0)
        semantic_searchable = " ".join(obj.label for obj in semantic_objects).upper()
        for tag in ['16"-CHWS-CS02', "R-DEMO-CHW-P-01", "R-DEMO-CHW-CH-01", "SHW-406-FTR103", "PIT-101", "FIT-202", "AT-70"]:
            self.assertIn(tag, semantic_searchable)
        matched_connectors = [
            obj
            for obj in semantic_objects
            if obj.kind == "connector" and obj.metadata.get("semanticConnectorRole") == "matchedContinuation"
        ]
        self.assertEqual(len(matched_connectors), 1)
        self.assertEqual(matched_connectors[0].metadata.get("lineTag"), '16"-CHWS-CS02')
        self.assertIn("semanticGraphEdgeId", matched_connectors[0].metadata)
        self.assertIn("startObjectId", matched_connectors[0].metadata)
        self.assertIn("endObjectId", matched_connectors[0].metadata)
        attachment_connectors = [
            obj
            for obj in semantic_objects
            if obj.kind == "connector" and obj.metadata.get("semanticConnectorRole") == "graphAttachment"
        ]
        self.assertEqual(attachment_connectors, [])
        overlay_attachments = [
            obj
            for obj in overlay_document.objects
            if obj.kind == "connector" and obj.metadata.get("semanticConnectorRole") == "graphAttachment"
        ]
        self.assertGreaterEqual(len(overlay_attachments), 4)
        self.assertTrue(all(obj.metadata.get("semanticGraphEdgeId") for obj in overlay_attachments))
        self.assertTrue(all(obj.metadata.get("startObjectId") != obj.metadata.get("endObjectId") for obj in overlay_attachments))
        self.assertTrue(all(obj.metadata.get("endSnapSide") in {"top", "right", "bottom", "left"} for obj in overlay_attachments))
        attachment_lanes = [obj.metadata.get("routeLane") for obj in overlay_attachments]
        self.assertEqual(len(attachment_lanes), len(set(attachment_lanes)))
        self.assertTrue(all(obj.metadata.get("routeStrategy") == "lineTagFanout" for obj in overlay_attachments))
        self.assertTrue(all(obj.label == "" for obj in overlay_attachments))
        self.assertTrue(all(obj.metadata.get("hideCenterLabel") is True for obj in overlay_attachments))
        self.assertTrue(all(obj.metadata.get("lineTag") for obj in overlay_attachments))
        semantic_graph = document.visualQa["semanticRelationshipGraph"]
        self.assertGreaterEqual(semantic_graph["metrics"]["lineTagNodes"], 2)
        self.assertGreaterEqual(semantic_graph["metrics"]["continuationEdges"], 1)
        self.assertEqual(semantic_graph["qa"]["unresolvedContinuationNodes"], [])
        pump_symbol = next(obj for obj in semantic_objects if obj.kind == "symbol" and obj.label == "R-DEMO-CHW-P-01")
        self.assertIn("semanticGraphNodeId", pump_symbol.metadata)
        self.assertEqual(pump_symbol.metadata.get("symbolRegistry"), "iso_primitives")
        self.assertEqual(pump_symbol.metadata.get("symbolType"), "pump")
        self.assertTrue(all(obj.metadata.get("hideCenterLabel") is True for obj in semantic_objects if obj.kind == "symbol" and obj.metadata.get("semanticObject") is True))
        object_label_tags = {
            obj.metadata.get("tag")
            for obj in semantic_objects
            if obj.kind == "label" and obj.metadata.get("semanticObjectLabel") is True
        }
        self.assertIn("PIT-101", object_label_tags)
        self.assertIn("FIT-202", object_label_tags)
        self.assertFalse(
            any(
                obj.metadata.get("semanticEndpoint") is True
                and (obj.style.opacity or 0.0) > 0.05
                for obj in semantic_objects
            )
        )
        self.assertFalse(
            any(
                obj.metadata.get("semanticPipe") is True
                and obj.metadata.get("sourceVectorId") in {"src_a_p1:pointer_marker", "src_b_p1:pointer_marker"}
                for obj in semantic_objects
            )
        )
        unresolved_offpages = [
            obj
            for obj in semantic_objects
            if obj.kind == "symbol" and obj.metadata.get("symbolType") == "offpage"
        ]
        self.assertEqual(len(unresolved_offpages), 1)
        unresolved_leaders = [
            obj
            for obj in semantic_objects
            if obj.kind == "connector" and obj.metadata.get("semanticConnectorRole") == "unresolvedContinuationLeader"
        ]
        self.assertEqual(len(unresolved_leaders), 1)
        self.assertEqual(unresolved_leaders[0].metadata.get("endObjectId"), unresolved_offpages[0].id)
        self.assertEqual(document.visualQa["semanticMissingEquipmentTags"], [])
        self.assertEqual(document.visualQa["semanticMissingLineTags"], [])

    def test_semantic_overlay_keeps_unclassified_source_vectors_out_of_final_linework(self):
        page = PageEvidence(
            "src_misc_p1",
            "src_misc",
            1,
            900.0,
            600.0,
            0,
            {"x": 0.0, "y": 0.0, "width": 900.0, "height": 600.0},
            [TextSpan("PIT-101", 120.0, 178.0, 80.0, 12.0)],
            1,
            [
                VectorSegment(
                    id="src_misc_p1:annotation_box",
                    kind="line",
                    points=[{"x": 100.0, "y": 420.0}, {"x": 820.0, "y": 420.0}],
                    bounds={"x": 100.0, "y": 420.0, "width": 720.0, "height": 0.0},
                    stroke="#000000",
                    strokeWidth=1.0,
                    dashed=False,
                )
            ],
        )

        option, document = generate_layout_options("project_semantic_noise", [page], [], [])[0]

        self.assertEqual(option.name, "Semantic Drawing")
        self.assertFalse(
            any(
                obj.metadata.get("semanticPipe") is True
                and obj.metadata.get("sourceVectorId") == "src_misc_p1:annotation_box"
                for obj in document.objects
            )
        )
        self.assertFalse(any(obj.metadata.get("semanticSourceMap") is True for obj in document.objects))

    def test_attaches_preflight_review_and_document_rulebook_to_visual_qa(self):
        page = self._page("src_legend_p1", "src_legend", "SWG SWITCHGEAR GEN GENERATOR")
        page.textSpans = [
            TextSpan("SWG", 10.0, 10.0, 30.0, 10.0),
            TextSpan("SWITCHGEAR", 80.0, 10.0, 100.0, 10.0),
            TextSpan("GEN", 10.0, 30.0, 30.0, 10.0),
            TextSpan("GENERATOR", 80.0, 30.0, 100.0, 10.0),
        ]
        preflight_review = {
            "projectId": "project_rulebook",
            "disciplines": ["Electrical"],
            "legendPages": [1],
            "warnings": [],
        }

        options = generate_layout_options("project_rulebook", [page], [], [], preflight_review=preflight_review)

        self.assertTrue(options)
        for _option, document in options:
            self.assertEqual(document.visualQa["preflightReview"], preflight_review)
            rulebook = document.visualQa["documentRulebook"]
            self.assertEqual(rulebook["disciplines"], ["Electrical"])
            self.assertEqual(rulebook["legendPages"], [1])
            self.assertEqual(rulebook["acronymMap"]["SWG"], "SWITCHGEAR")
            self.assertEqual(rulebook["acronymMap"]["GEN"], "GENERATOR")
            self.assertEqual(document.visualQa["hierarchyViews"][0]["id"], "electrical_power")

    def test_single_page_semantic_drawing_uses_source_derived_pipe_vectors(self):
        page = PageEvidence(
            "src_single_p1",
            "src_single",
            '2"-HHWS-CS01 R-DEMO-HHW-P-01 PIT-101',
            1200.0,
            800.0,
            0,
            {"x": 0.0, "y": 0.0, "width": 1200.0, "height": 800.0},
            [
                TextSpan('2"-HHWS-CS01', 210.0, 216.0, 118.0, 14.0),
                TextSpan("R-DEMO-HHW-P-01", 500.0, 250.0, 160.0, 16.0),
                TextSpan("PIT-101", 610.0, 286.0, 70.0, 14.0),
            ],
            1,
            [
                VectorSegment(
                    id="src_single_p1:hhws_pipe",
                    kind="line",
                    points=[{"x": 150.0, "y": 220.0}, {"x": 930.0, "y": 220.0}],
                    bounds={"x": 150.0, "y": 220.0, "width": 780.0, "height": 0.0},
                    stroke="#000000",
                    strokeWidth=1.0,
                    dashed=False,
                )
            ],
        )

        option, document = generate_layout_options("project_single_semantic", [page], [], [])[0]

        self.assertEqual(option.name, "Semantic Drawing")
        self.assertTrue(option.metrics["singleSourceFaithful"])
        self.assertEqual(document.visualQa["semanticGeneratedRouteObjects"], 0)
        source_pipes = [
            obj
            for obj in document.objects
            if obj.metadata.get("semanticTracePipe") is True
            and obj.metadata.get("sourceVectorId") == "src_single_p1:hhws_pipe"
        ]
        self.assertEqual(len(source_pipes), 1)
        self.assertTrue(source_pipes[0].metadata.get("semanticPipe"))
        self.assertTrue(source_pipes[0].metadata.get("systemColorApplied"))
        self.assertEqual(source_pipes[0].metadata.get("system"), "HHW")
        self.assertFalse(any(obj.metadata.get("semanticSourceMap") is True for obj in document.objects))

    def test_single_page_semantic_drawing_filters_inset_sheet_frame_vectors(self):
        page = PageEvidence(
            "src_frame_p1",
            "src_frame",
            '2"-HRWS-CS01 R-DEMO-HRW-HX-01',
            3024.0,
            2160.0,
            0,
            {"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            [
                TextSpan('2"-HRWS-CS01', 640.0, 420.0, 118.0, 14.0),
                TextSpan("R-DEMO-HRW-HX-01", 830.0, 460.0, 160.0, 16.0),
            ],
            1,
            [
                VectorSegment(
                    id="src_frame_p1:actual_pipe",
                    kind="line",
                    points=[{"x": 540.0, "y": 426.0}, {"x": 1260.0, "y": 426.0}],
                    bounds={"x": 540.0, "y": 426.0, "width": 720.0, "height": 0.0},
                ),
                VectorSegment(
                    id="src_frame_p1:inset_vertical_frame",
                    kind="line",
                    points=[{"x": 276.0, "y": 58.0}, {"x": 276.0, "y": 2966.0}],
                    bounds={"x": 276.0, "y": 58.0, "width": 0.0, "height": 2908.0},
                ),
                VectorSegment(
                    id="src_frame_p1:inset_horizontal_frame",
                    kind="line",
                    points=[{"x": 54.0, "y": 58.0}, {"x": 2106.0, "y": 58.0}],
                    bounds={"x": 54.0, "y": 58.0, "width": 2052.0, "height": 0.0},
                ),
                VectorSegment(
                    id="src_frame_p1:right_inset_frame",
                    kind="line",
                    points=[{"x": 2106.0, "y": 58.0}, {"x": 2106.0, "y": 2966.0}],
                    bounds={"x": 2106.0, "y": 58.0, "width": 0.0, "height": 2908.0},
                ),
                VectorSegment(
                    id="src_frame_p1:partial_left_grid_rail",
                    kind="line",
                    points=[{"x": 259.0, "y": 763.0}, {"x": 259.0, "y": 1283.0}],
                    bounds={"x": 259.0, "y": 763.0, "width": 0.0, "height": 520.0},
                ),
            ],
        )

        self.assertTrue(_is_page_edge_frame_vector(page.vectorSegments[1].bounds, page))
        self.assertTrue(_is_page_edge_frame_vector(page.vectorSegments[2].bounds, page))
        self.assertTrue(_is_page_edge_frame_vector(page.vectorSegments[3].bounds, page))
        self.assertTrue(_is_page_edge_frame_vector(page.vectorSegments[4].bounds, page))

        _option, document = generate_layout_options("project_single_frame_filter", [page], [], [])[0]
        semantic_source_ids = {
            obj.metadata.get("sourceVectorId")
            for obj in document.objects
            if obj.metadata.get("semanticTracePipe") is True
        }
        self.assertIn("src_frame_p1:actual_pipe", semantic_source_ids)
        self.assertNotIn("src_frame_p1:inset_vertical_frame", semantic_source_ids)
        self.assertNotIn("src_frame_p1:inset_horizontal_frame", semantic_source_ids)
        self.assertNotIn("src_frame_p1:right_inset_frame", semantic_source_ids)
        self.assertNotIn("src_frame_p1:partial_left_grid_rail", semantic_source_ids)

    def test_single_page_semantic_drawing_colors_plumbing_pipe_size_tags(self):
        page = PageEvidence(
            "src_plumbing_p1",
            "src_plumbing",
            '10" POTCW 01-ICW-BFP-01 R-POTCW-BFP-01',
            1200.0,
            800.0,
            0,
            {"x": 0.0, "y": 0.0, "width": 1200.0, "height": 800.0},
            [
                TextSpan('10" POTCW', 210.0, 216.0, 118.0, 14.0),
                TextSpan("01-ICW-BFP-01", 210.0, 286.0, 130.0, 14.0),
                TextSpan("R-POTCW-BFP-01", 500.0, 250.0, 160.0, 16.0),
            ],
            1,
            [
                VectorSegment(
                    id="src_plumbing_p1:potcw_pipe",
                    kind="line",
                    points=[{"x": 150.0, "y": 220.0}, {"x": 930.0, "y": 220.0}],
                    bounds={"x": 150.0, "y": 220.0, "width": 780.0, "height": 0.0},
                ),
                VectorSegment(
                    id="src_plumbing_p1:icw_pipe",
                    kind="line",
                    points=[{"x": 150.0, "y": 290.0}, {"x": 930.0, "y": 290.0}],
                    bounds={"x": 150.0, "y": 290.0, "width": 780.0, "height": 0.0},
                ),
            ],
        )

        _option, document = generate_layout_options(
            "project_single_plumbing_color",
            [page],
            [],
            [],
            {"src_plumbing": "/packages/DEMO-PB-3002 Domestic Water.pdf"},
        )[0]
        source_pipes = {
            obj.metadata.get("sourceVectorId"): obj.metadata.get("system")
            for obj in document.objects
            if obj.metadata.get("semanticTracePipe") is True
        }

        self.assertEqual(source_pipes.get("src_plumbing_p1:potcw_pipe"), "POTCW")
        self.assertEqual(source_pipes.get("src_plumbing_p1:icw_pipe"), "ICW")

    def test_single_page_semantic_drawing_keeps_only_contextual_default_vectors(self):
        page = PageEvidence(
            "src_default_p1",
            "src_default",
            '2"-CHWS-CS01 R-DEMO-CHW-P-01',
            1200.0,
            800.0,
            0,
            {"x": 0.0, "y": 0.0, "width": 1200.0, "height": 800.0},
            [
                TextSpan('2"-CHWS-CS01', 210.0, 216.0, 118.0, 14.0),
                TextSpan("R-DEMO-CHW-P-01", 500.0, 250.0, 160.0, 16.0),
            ],
            1,
            [
                VectorSegment(
                    id="src_default_p1:colored_pipe",
                    kind="line",
                    points=[{"x": 150.0, "y": 220.0}, {"x": 930.0, "y": 220.0}],
                    bounds={"x": 150.0, "y": 220.0, "width": 780.0, "height": 0.0},
                ),
                VectorSegment(
                    id="src_default_p1:connected_fitting",
                    kind="line",
                    points=[{"x": 600.0, "y": 220.0}, {"x": 600.0, "y": 260.0}],
                    bounds={"x": 600.0, "y": 220.0, "width": 0.0, "height": 40.0},
                ),
                VectorSegment(
                    id="src_default_p1:equipment_detail",
                    kind="line",
                    points=[{"x": 520.0, "y": 255.0}, {"x": 560.0, "y": 255.0}],
                    bounds={"x": 520.0, "y": 255.0, "width": 40.0, "height": 0.0},
                ),
                VectorSegment(
                    id="src_default_p1:floating_grid_near_line_tag",
                    kind="line",
                    points=[{"x": 360.0, "y": 300.0}, {"x": 480.0, "y": 300.0}],
                    bounds={"x": 360.0, "y": 300.0, "width": 120.0, "height": 0.0},
                ),
                VectorSegment(
                    id="src_default_p1:floating_grid",
                    kind="line",
                    points=[{"x": 980.0, "y": 520.0}, {"x": 980.0, "y": 640.0}],
                    bounds={"x": 980.0, "y": 520.0, "width": 0.0, "height": 120.0},
                ),
            ],
        )

        _option, document = generate_layout_options("project_single_default_filter", [page], [], [])[0]
        semantic_source_ids = {
            obj.metadata.get("sourceVectorId")
            for obj in document.objects
            if obj.metadata.get("semanticTracePipe") is True
        }

        self.assertIn("src_default_p1:colored_pipe", semantic_source_ids)
        self.assertIn("src_default_p1:connected_fitting", semantic_source_ids)
        self.assertIn("src_default_p1:equipment_detail", semantic_source_ids)
        self.assertNotIn("src_default_p1:floating_grid_near_line_tag", semantic_source_ids)
        self.assertNotIn("src_default_p1:floating_grid", semantic_source_ids)

    def test_semantic_overlay_suppresses_unmatched_offpage_pointer_when_target_sheet_is_loaded(self):
        page_a = self._page(
            "src_cda_01_p1",
            "src_cda_01",
            'DEMO-ME-4CDA01 6"-CDA-SS01 R-DEMO-CDA-C-01',
        )
        page_b = self._page(
            "src_cda_02_p1",
            "src_cda_02",
            'DEMO-ME-4CDA02 6"-CDA-SS01 R-DEMO-CDA-AD-01',
        )
        loaded_pointer = self._candidate("loaded_target", "src_cda_01", "to", '6"-CDA-SS01', "CDA", "right")
        loaded_pointer.sheetRef = "DEMO-ME-4CDA02"
        loaded_pointer.label = 'TO 6"-CDA-SS01 DEMO-ME-4CDA02'
        loaded_pointer.evidenceText = loaded_pointer.label
        external_pointer = self._candidate("external_target", "src_cda_02", "to", '2"-CDA-SS99', "CDA", "right")
        external_pointer.sheetRef = "DEMO-ME-4CDA99"
        external_pointer.label = 'TO 2"-CDA-SS99 DEMO-ME-4CDA99'
        external_pointer.evidenceText = external_pointer.label
        bare_line_pointer = self._candidate("bare_line", "src_cda_02", "unknown", '6"-CDA-SS01', "CDA", "bottom")
        bare_line_pointer.sheetRef = ""
        bare_line_pointer.label = '6"-CDA-SS01'
        bare_line_pointer.evidenceText = bare_line_pointer.label

        _option, document = generate_layout_options(
            "project_semantic_loaded_pointer",
            [page_a, page_b],
            [loaded_pointer, external_pointer, bare_line_pointer],
            [],
            source_paths={
                "src_cda_01": "/packages/DEMO-ME-4CDA01_ DEMO - MECHANICAL CDA GENERATION P&ID.pdf",
                "src_cda_02": "/packages/DEMO-ME-4CDA02_ DEMO - MECHANICAL CDA DISTRIBUTION P&ID.pdf",
            },
        )[0]

        unresolved_offpages = [
            obj
            for obj in document.objects
            if obj.kind == "symbol" and obj.metadata.get("semanticConnectorRole") == "unresolvedContinuation"
        ]
        self.assertEqual([obj.metadata.get("sheetRef") for obj in unresolved_offpages], ["DEMO-ME-4CDA99"])
        unresolved_leaders = [
            obj
            for obj in document.objects
            if obj.kind == "connector" and obj.metadata.get("semanticConnectorRole") == "unresolvedContinuationLeader"
        ]
        self.assertEqual(len(unresolved_leaders), 1)
        self.assertEqual(unresolved_leaders[0].metadata.get("endObjectId"), unresolved_offpages[0].id)

    def test_semantic_unresolved_pointer_infers_system_from_plain_flow_label(self):
        page = self._page(
            "src_hrw_01_p1",
            "src_hrw_01",
            'DEMO-ME-4HRW01 8"-HRW-CS01 R-DEMO-HRW-HX-01',
        )
        pointer = self._candidate("hrw_temp", "src_hrw_01", "to", "", "", "right")
        pointer.sheetRef = "TEMPERATURE"
        pointer.label = "HRW SUPPLY TO HX TEMPERATURE"
        pointer.evidenceText = pointer.label

        _option, document = generate_layout_options(
            "project_semantic_plain_flow_label",
            [page],
            [pointer],
            [],
            source_paths={"src_hrw_01": "/packages/DEMO-ME-4HRW01_ DEMO - MECHANICAL HEAT RECOVERY WATER SYSTEM P&ID.pdf"},
        )[0]

        pointer_symbol = next(obj for obj in document.objects if obj.metadata.get("semanticConnectorRole") == "unresolvedContinuation")
        leader = next(obj for obj in document.objects if obj.metadata.get("semanticConnectorRole") == "unresolvedContinuationLeader")
        self.assertEqual(pointer_symbol.metadata.get("system"), "HRW")
        self.assertEqual(leader.metadata.get("system"), "HRW")
        self.assertNotEqual(leader.style.stroke, "#111827")

    def test_semantic_symbol_registry_assigns_iso_inspired_equipment_symbols(self):
        page = self._page(
            "src_symbols_p1",
            "src_symbols",
            '12"-HHWS-CS02 R-HHW-HX-01 R-SA-AHU-01 R-SA-AHU-01-VFD-01 R-DEMO-CDA-ST-01',
        )
        page.textSpans = [
            TextSpan('12"-HHWS-CS02', 160.0, 180.0, 120.0, 14.0),
            TextSpan("R-HHW-HX-01", 260.0, 260.0, 110.0, 14.0),
            TextSpan("R-SA-AHU-01", 380.0, 300.0, 110.0, 14.0),
            TextSpan("R-SA-AHU-01-VFD-01", 500.0, 340.0, 150.0, 14.0),
            TextSpan("R-DEMO-CDA-ST-01", 640.0, 380.0, 140.0, 14.0),
        ]

        _option, document = generate_layout_options("project_semantic_symbol_registry", [page], [], [])[0]

        symbol_by_tag = {
            obj.label: obj
            for obj in document.objects
            if obj.kind == "symbol" and obj.metadata.get("semanticObject") is True
        }
        self.assertEqual(symbol_by_tag["R-HHW-HX-01"].metadata.get("symbolType"), "heat_exchanger")
        self.assertEqual(symbol_by_tag["R-SA-AHU-01"].metadata.get("symbolType"), "air_handler")
        self.assertEqual(symbol_by_tag["R-SA-AHU-01-VFD-01"].metadata.get("symbolType"), "drive")
        self.assertEqual(symbol_by_tag["R-DEMO-CDA-ST-01"].metadata.get("symbolType"), "tank")
        self.assertTrue(all(symbol.metadata.get("symbolRegistry") == "iso_primitives" for symbol in symbol_by_tag.values()))

    def test_semantic_symbol_registry_covers_common_pid_equipment_families(self):
        page = self._page(
            "src_expanded_symbols_p1",
            "src_expanded_symbols",
            "R-CDA-C-01 R-CW-CT-01 R-EF-FAN-01 R-HHW-SKID-01 R-CDA-SEP-01 R-CDA-COIL-01 R-ELEC-PNL-01",
        )
        page.textSpans = [
            TextSpan("R-CDA-C-01", 200.0, 220.0, 100.0, 14.0),
            TextSpan("R-CW-CT-01", 300.0, 260.0, 100.0, 14.0),
            TextSpan("R-EF-FAN-01", 400.0, 300.0, 110.0, 14.0),
            TextSpan("R-HHW-SKID-01", 500.0, 340.0, 120.0, 14.0),
            TextSpan("R-CDA-SEP-01", 600.0, 380.0, 120.0, 14.0),
            TextSpan("R-CDA-COIL-01", 700.0, 420.0, 130.0, 14.0),
            TextSpan("R-ELEC-PNL-01", 800.0, 460.0, 130.0, 14.0),
        ]

        _option, document = generate_layout_options("project_semantic_expanded_symbol_registry", [page], [], [])[0]

        symbol_by_tag = {
            obj.label: obj
            for obj in document.objects
            if obj.kind == "symbol" and obj.metadata.get("semanticObject") is True
        }
        self.assertEqual(symbol_by_tag["R-CDA-C-01"].metadata.get("symbolType"), "compressor")
        self.assertEqual(symbol_by_tag["R-CW-CT-01"].metadata.get("symbolType"), "cooling_tower")
        self.assertEqual(symbol_by_tag["R-EF-FAN-01"].metadata.get("symbolType"), "fan")
        self.assertEqual(symbol_by_tag["R-HHW-SKID-01"].metadata.get("symbolType"), "skid")
        self.assertEqual(symbol_by_tag["R-CDA-SEP-01"].metadata.get("symbolType"), "separator")
        self.assertEqual(symbol_by_tag["R-CDA-COIL-01"].metadata.get("symbolType"), "coil")
        self.assertEqual(symbol_by_tag["R-ELEC-PNL-01"].metadata.get("symbolType"), "panel")

    def test_source_cluster_breathing_spreads_dense_equipment_without_losing_geometry(self):
        page = self._page("src_cluster_p1", "src_cluster", "R-CDA-C-01 R-CDA-C-02 R-CDA-C-03 R-CDA-C-04")
        placed = []
        for index in range(4):
            placed.append(
                {
                    "id": f"item_{index}",
                    "kind": "equipment",
                    "tag": f"R-CDA-C-0{index + 1}",
                    "system": "CDA",
                    "page": page,
                    "bounds": {"x": 420.0 + index * 5.0, "y": 300.0 + index * 4.0, "width": 70.0, "height": 16.0},
                    "sourceBounds": {"x": 420.0 + index * 5.0, "y": 300.0 + index * 4.0, "width": 70.0, "height": 16.0},
                    "displayBounds": {"x": 420.0 + index * 5.0, "y": 300.0 + index * 4.0, "width": 70.0, "height": 16.0},
                    "sourceEvidenceIds": [page.id],
                }
            )

        breathed = _apply_source_cluster_breathing(placed)

        breathing_items = [item for item in breathed if item.get("placementStrategy") == "sourceClusterBreathing"]
        self.assertEqual(len(breathing_items), 4)
        centers = [
            {
                "x": item["displayBounds"]["x"] + item["displayBounds"]["width"] / 2.0,
                "y": item["displayBounds"]["y"] + item["displayBounds"]["height"] / 2.0,
            }
            for item in breathing_items
        ]
        min_distance = min(
            ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5
            for index, a in enumerate(centers)
            for b in centers[index + 1 :]
        )
        max_source_shift = max(
            abs(item["displayBounds"]["x"] - item["sourceBounds"]["x"]) + abs(item["displayBounds"]["y"] - item["sourceBounds"]["y"])
            for item in breathing_items
        )
        self.assertGreaterEqual(min_distance, 58.0)
        self.assertLessEqual(max_source_shift, 180.0)

    def test_semantic_drawing_deconflicts_symbols_but_allows_lines_to_cross(self):
        page = self._page(
            "src_dense_p1",
            "src_dense",
            '6"-CDA-CS01 R-CDA-C-01 R-CDA-C-02 R-CDA-C-03 PIT-101 FIT-102',
        )
        page.textSpans = [
            TextSpan("R-CDA-C-01", 420.0, 300.0, 100.0, 14.0),
            TextSpan("R-CDA-C-02", 424.0, 304.0, 100.0, 14.0),
            TextSpan("R-CDA-C-03", 428.0, 308.0, 100.0, 14.0),
            TextSpan("PIT-101", 430.0, 312.0, 72.0, 14.0),
            TextSpan("FIT-102", 434.0, 316.0, 72.0, 14.0),
            TextSpan('6"-CDA-CS01', 250.0, 318.0, 120.0, 14.0),
        ]
        page.vectorSegments = [
            VectorSegment(
                id="src_dense_p1:horizontal",
                kind="line",
                points=[{"x": 220.0, "y": 320.0}, {"x": 760.0, "y": 320.0}],
                bounds={"x": 220.0, "y": 320.0, "width": 540.0, "height": 0.0},
            ),
            VectorSegment(
                id="src_dense_p1:vertical",
                kind="line",
                points=[{"x": 500.0, "y": 180.0}, {"x": 500.0, "y": 460.0}],
                bounds={"x": 500.0, "y": 180.0, "width": 0.0, "height": 280.0},
            ),
        ]

        _option, document = generate_layout_options("project_semantic_overlap", [page], [], [])[0]

        symbols = [
            obj
            for obj in document.objects
            if obj.kind == "symbol" and obj.metadata.get("semanticObject") is True
        ]
        self.assertGreaterEqual(len(symbols), 5)
        self.assertTrue(any(symbol.metadata.get("placementStrategy") == "sourceClusterBreathing" for symbol in symbols))
        object_labels = [
            obj
            for obj in document.objects
            if obj.kind == "label" and obj.metadata.get("semanticObjectLabel") is True
        ]
        self.assertTrue({"PIT-101", "FIT-102"}.issubset({label.metadata.get("tag") for label in object_labels}))
        self.assertGreaterEqual(len({label.metadata.get("labelSide") for label in object_labels if label.metadata.get("labelSide")}), 2)
        self.assertTrue(all((label.style.fontSize or 99.0) <= 4.8 for label in object_labels))
        for index, symbol in enumerate(symbols):
            for other in symbols[index + 1 :]:
                self.assertFalse(self._bounds_overlap(symbol.bounds, other.bounds, padding=3.0), f"{symbol.label} overlaps {other.label}")
        for label in object_labels:
            for symbol in symbols:
                if label.metadata.get("tag") == symbol.metadata.get("tag"):
                    continue
                self.assertFalse(self._bounds_overlap(label.bounds, symbol.bounds, padding=1.0), f"{label.label} label overlaps {symbol.label}")
        for index, label in enumerate(object_labels):
            for other in object_labels[index + 1 :]:
                self.assertFalse(self._bounds_overlap(label.bounds, other.bounds, padding=1.0), f"{label.label} overlaps {other.label}")

        semantic_pipes = [
            obj
            for obj in document.objects
            if obj.kind == "pipe"
            and (
                obj.metadata.get("semanticGeneratedRoute") is True
                or obj.metadata.get("semanticTracePipe") is True
            )
        ]
        self.assertGreaterEqual(len(semantic_pipes), 1)

    def test_semantic_route_merge_removes_near_duplicate_same_system_runs(self):
        first = DrawingObject(
            "route_a",
            "pipe",
            "",
            [{"x": 10.0, "y": 20.0}, {"x": 140.0, "y": 20.0}],
            {"x": 10.0, "y": 20.0, "width": 130.0, "height": 0.0},
            DrawingStyle(stroke="#0070c0", fill="none", strokeWidth=0.9),
            [],
            metadata={"semanticOverlay": True, "semanticGeneratedRoute": True, "semanticRouteRole": "systemBackbone", "system": "CHW"},
        )
        near_duplicate = DrawingObject(
            "route_b",
            "pipe",
            "",
            [{"x": 12.0, "y": 23.0}, {"x": 142.0, "y": 23.0}],
            {"x": 12.0, "y": 23.0, "width": 130.0, "height": 0.0},
            DrawingStyle(stroke="#0070c0", fill="none", strokeWidth=0.9),
            [],
            metadata={"semanticOverlay": True, "semanticGeneratedRoute": True, "semanticRouteRole": "systemBackbone", "system": "CHW"},
        )
        separate_system = DrawingObject(
            "route_c",
            "pipe",
            "",
            [{"x": 10.0, "y": 20.0}, {"x": 140.0, "y": 20.0}],
            {"x": 10.0, "y": 20.0, "width": 130.0, "height": 0.0},
            DrawingStyle(stroke="#ff0000", fill="none", strokeWidth=0.9),
            [],
            metadata={"semanticOverlay": True, "semanticGeneratedRoute": True, "semanticRouteRole": "systemBackbone", "system": "HHW"},
        )

        merged = _merge_nearby_same_system_routes([first, near_duplicate, separate_system])

        self.assertEqual([obj.id for obj in merged], ["route_a", "route_c"])
        self.assertEqual(merged[0].metadata.get("mergedRouteCount"), 2)

    def test_semantic_route_detours_around_dense_symbol_pockets(self):
        protected = [{"x": 50.0, "y": 45.0, "width": 30.0, "height": 20.0}]
        points = [{"x": 10.0, "y": 55.0}, {"x": 120.0, "y": 55.0}]

        routed = _route_points_around_protected_bounds(points, protected)

        self.assertGreater(len(routed), 2)
        self.assertNotEqual(routed, points)
        for start, end in zip(routed, routed[1:]):
            self.assertFalse(self._segment_intersects_bounds(start, end, protected[0]), f"{start}->{end} crosses protected symbol")

    def test_semantic_system_bus_runs_outside_dense_equipment_bank(self):
        page = self._page("src_bus_p1", "src_bus", "R-HHW-P-01 R-HHW-P-02 R-HHW-P-03")
        items = []
        for index, y in enumerate((100.0, 132.0, 164.0), start=1):
            items.append(
                {
                    "id": f"item_{index}",
                    "kind": "equipment",
                    "tag": f"R-HHW-P-0{index}",
                    "system": "HHW",
                    "page": page,
                    "bounds": {"x": 180.0 + index * 70.0, "y": y, "width": 72.0, "height": 16.0},
                    "displayBounds": {"x": 180.0 + index * 70.0, "y": y, "width": 72.0, "height": 16.0},
                    "sourceEvidenceIds": [page.id],
                }
            )

        bus_points, orientation = _system_bus_geometry(items)

        self.assertEqual(orientation, "horizontal")
        protected = [_semantic_symbol_bounds_for_item(item) for item in items]
        for start, end in zip(bus_points, bus_points[1:]):
            for bounds in protected:
                self.assertFalse(self._segment_intersects_bounds(start, end, bounds), f"{start}->{end} crosses {bounds}")

    def test_semantic_system_clusters_split_distant_equipment_pockets(self):
        page = self._page("src_pockets_p1", "src_pockets", "R-HHW-P-01 R-HHW-P-02 R-HHW-HX-01 R-HHW-HX-02")
        items = []
        for index, (x, y) in enumerate(((120.0, 160.0), (178.0, 168.0), (720.0, 620.0), (780.0, 630.0)), start=1):
            items.append(
                {
                    "id": f"item_{index}",
                    "kind": "equipment",
                    "tag": f"R-HHW-P-0{index}",
                    "system": "HHW",
                    "page": page,
                    "bounds": {"x": x, "y": y, "width": 72.0, "height": 16.0},
                    "displayBounds": {"x": x, "y": y, "width": 72.0, "height": 16.0},
                    "sourceEvidenceIds": [page.id],
                }
            )

        clusters = _route_clusters_for_system(items)

        self.assertEqual(len(clusters), 2)
        self.assertEqual(sorted(len(cluster) for cluster in clusters), [2, 2])

    def test_semantic_route_pocket_pass_keeps_main_system_backbones_direct(self):
        symbol = DrawingObject(
            "symbol_1",
            "symbol",
            "P-1",
            [],
            {"x": 50.0, "y": 45.0, "width": 30.0, "height": 20.0},
            DrawingStyle(stroke="#0070c0", fill="#ffffff", strokeWidth=1.0),
            [],
            metadata={"semanticOverlay": True, "semanticObject": True},
        )
        backbone = DrawingObject(
            "backbone_1",
            "pipe",
            "",
            [{"x": 10.0, "y": 55.0}, {"x": 120.0, "y": 55.0}],
            {"x": 10.0, "y": 55.0, "width": 110.0, "height": 0.0},
            DrawingStyle(stroke="#0070c0", fill="none", strokeWidth=1.0),
            [],
            metadata={"semanticOverlay": True, "semanticGeneratedRoute": True, "semanticRouteRole": "systemBackbone", "system": "CHW"},
        )

        _route_semantic_lines_around_dense_pockets([symbol, backbone])

        self.assertEqual(backbone.points, [{"x": 10.0, "y": 55.0}, {"x": 120.0, "y": 55.0}])
        self.assertIsNone(backbone.metadata.get("routeAvoidedDensePockets"))

    def test_semantic_snap_pass_repairs_attached_connector_endpoints(self):
        pump = DrawingObject(
            "semantic_equipment_pump_1",
            "symbol",
            "R-HHW-P-01",
            [],
            {"x": 100.0, "y": 80.0, "width": 42.0, "height": 28.0},
            DrawingStyle(stroke="#ff0000", fill="#ffffff", strokeWidth=1.0),
            [],
            metadata={"semanticOverlay": True, "semanticObject": True},
        )
        line = DrawingObject(
            "semantic_system_branch_1",
            "connector",
            "",
            [{"x": 40.0, "y": 93.0}, {"x": 92.0, "y": 93.0}],
            {"x": 40.0, "y": 93.0, "width": 52.0, "height": 0.0},
            DrawingStyle(stroke="#ff0000", fill="none", strokeWidth=0.8),
            [],
            metadata={
                "semanticOverlay": True,
                "semanticGeneratedRoute": True,
                "semanticRouteRole": "equipmentBranch",
                "endObjectId": "semantic_equipment_pump_1",
            },
        )

        _snap_attached_connector_endpoints([pump, line])

        self.assertEqual(line.points[-1], {"x": 100.0, "y": 94.0})
        self.assertEqual(line.metadata.get("endSnapSide"), "left")
        for start, end in zip(line.points, line.points[1:]):
            self.assertTrue(abs(start["x"] - end["x"]) < 0.5 or abs(start["y"] - end["y"]) < 0.5)

    def test_semantic_system_interconnect_uses_shared_corridor(self):
        anchors = [
            {"x": 120.0, "y": 260.0},
            {"x": 420.0, "y": 180.0},
            {"x": 780.0, "y": 340.0},
        ]

        points, orientation = _system_corridor_points(anchors, lane_offset=0.0)

        self.assertEqual(orientation, "horizontal")
        self.assertGreater(len(points), len(anchors))
        corridor_y_values = {
            round(point["y"], 1)
            for point in points[1:-1]
            if min(anchor["x"] for anchor in anchors) <= point["x"] <= max(anchor["x"] for anchor in anchors)
        }
        self.assertIn(260.0, corridor_y_values)
        self.assertEqual(points[0], anchors[0])
        self.assertEqual(points[-1], anchors[-1])
        self.assertTrue(any(point["x"] == anchors[1]["x"] and point["y"] == 260.0 for point in points))

    def test_semantic_body_position_compacts_large_header_gap_without_moving_title_or_legend(self):
        title = DrawingObject(
            "title",
            "label",
            "SEMANTIC DRAWING",
            [],
            {"x": 120.0, "y": 54.0, "width": 400.0, "height": 24.0},
            DrawingStyle(stroke="#0f172a", fill="none", fontSize=17.0),
            [],
            metadata={"semanticOverlay": True, "semanticTitle": True},
        )
        legend = DrawingObject(
            "legend",
            "region",
            "",
            [],
            {"x": 1200.0, "y": 48.0, "width": 330.0, "height": 96.0},
            DrawingStyle(stroke="#94a3b8", fill="#ffffff"),
            [],
            metadata={"semanticOverlay": True, "semanticLegend": True},
        )
        pipe = DrawingObject(
            "pipe",
            "pipe",
            "",
            [{"x": 200.0, "y": 620.0}, {"x": 700.0, "y": 620.0}],
            {"x": 200.0, "y": 620.0, "width": 500.0, "height": 0.0},
            DrawingStyle(stroke="#0070c0", fill="none", strokeWidth=1.0),
            [],
            metadata={"semanticOverlay": True, "semanticGeneratedRoute": True},
        )

        _normalize_semantic_body_position([title, legend, pipe])

        self.assertEqual(title.bounds["y"], 54.0)
        self.assertEqual(legend.bounds["y"], 48.0)
        self.assertLess(pipe.bounds["y"], 260.0)
        self.assertEqual(pipe.metadata.get("bodyPositionNormalized"), True)

    def test_primary_source_driven_combined_pid_infers_non_mechanical_groups(self):
        cda_page = self._page(
            "src_cda_01_p1",
            "src_cda_01",
            'DEMO-ME-4CDA01 COMPRESSED DRY AIR 6"-CDA-SS01 R-DEMO-CDA-C-01 R-DEMO-CDA-AD-01 R-DEMO-CDA-FLTR-01',
        )
        plumbing_page = self._page(
            "src_pb_6002_p1",
            "src_pb_6002",
            "DEMO-PB-3002 PLUMBING DOMESTIC WATER SAFETY SHOWER R-DEMO-PB-EWH-01 R-DEMO-PB-TMV-01",
        )

        options = generate_layout_options(
            "project_a",
            [cda_page, plumbing_page],
            [],
            [],
            source_paths={
                "src_cda_01": "/packages/DEMO-ME-4CDA01_ DEMO - MECHANICAL CDA GENERATION P&ID.pdf",
                "src_pb_6002": "/packages/DEMO-PB-3002_ DEMO - PLUMBING DOMESTIC WATER P&ID.pdf",
            },
        )

        option, document = self._source_driven(options)

        self.assertEqual(option.name, "Source-driven Combined P&ID")
        self.assertTrue(option.metrics["sourceDriven"])
        self.assertEqual(option.metrics["primaryOutput"], False)
        self.assertEqual(option.metrics["sourceAudit"], True)
        self.assertIn("CDA", option.metrics["detectedGroups"])
        self.assertIn("PLUMBING WATER", option.metrics["detectedGroups"])
        self.assertTrue(any(obj.metadata.get("layoutMode") == "source_driven_combined" for obj in document.objects))
        self.assertTrue(any("CDA" in obj.label for obj in document.objects))
        self.assertTrue(any("PLUMBING" in obj.label for obj in document.objects))
        self.assertFalse(any(obj.metadata.get("templateDerived") is True for obj in document.objects))
        self.assertFalse(any(obj.label in {"P-101A", "XV-101", "TO PID-002"} for obj in document.objects))

    def test_source_driven_combined_pid_carries_every_source_tag_without_review_callouts(self):
        page = self._page(
            "src_hhw_01_p1",
            "src_hhw_01",
            (
                'DEMO-ME-4HHW01 12"-HHWS-CS02 10"-HHWR-CS02 2"-SHRWS-CS01 '
                "R-DEMO-HHW-HWB-01 R-DEMO-HHW-P-01 R-DEMO-HHW-P-02 R-DEMO-HHW-P-03 "
                "R-DEMO-HHW-P-04 R-DEMO-HHW-P-05 R-DEMO-HHW-P-06 R-DEMO-HHW-P-07 "
                "R-DEMO-HRW-HX-01 AHU-101 AHU-101-CVR-101 AHU-101-VAR-101 "
                "PIT-101 FIT-202 TIT-303 PDIT-404 SHW-406-FTR103 CXA COMMENT FIELD REVIEW"
            ),
        )

        options = generate_layout_options(
            "project_a",
            [page],
            [],
            [],
            source_paths={"src_hhw_01": "/packages/DEMO-ME-4HHW01_ DEMO - MECHANICAL HEATING HOT WATER P&ID.pdf"},
        )
        _option, document = self._source_driven(options)

        searchable = " ".join(
            [obj.label for obj in document.objects]
            + [
                str(value)
                for obj in document.objects
                for value in obj.metadata.values()
                if isinstance(value, str)
            ]
        ).upper()
        for tag in [
            '12"-HHWS-CS02',
            '10"-HHWR-CS02',
            '2"-SHRWS-CS01',
            "R-DEMO-HHW-P-07",
            "AHU-101-CVR-101",
            "AHU-101-VAR-101",
            "PIT-101",
            "FIT-202",
            "TIT-303",
            "PDIT-404",
            "SHW-406-FTR103",
        ]:
            self.assertIn(tag, searchable)

        labels = " ".join(obj.label.upper() for obj in document.objects)
        self.assertNotIn("CXA COMMENT", labels)
        self.assertNotIn("FIELD REVIEW", labels)
        self.assertNotIn("REVIEW", labels)

    def test_source_driven_single_pid_reconstructs_source_vectors_and_text(self):
        page = self._page(
            "src_single_p1",
            "src_single",
            'DEMO-ME-4CDA01 6"-CDA-SS01 R-DEMO-CDA-C-01 PIT-101 CXA COMMENT',
        )
        page.rotation = 0
        page.textSpans = [
            TextSpan('6"-CDA-SS01', 260.0, 300.0, 120.0, 16.0),
            TextSpan("R-DEMO-CDA-C-01", 540.0, 420.0, 150.0, 18.0),
            TextSpan("PIT-101", 640.0, 520.0, 72.0, 16.0),
            TextSpan("CXA COMMENT", 100.0, 1800.0, 120.0, 16.0),
        ]
        page.vectorSegments = [
            VectorSegment(
                id="src_single_p1:line_a",
                kind="line",
                points=[{"x": 220.0, "y": 300.0}, {"x": 1100.0, "y": 300.0}],
                bounds={"x": 220.0, "y": 300.0, "width": 880.0, "height": 0.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=False,
            ),
            VectorSegment(
                id="src_single_p1:line_b",
                kind="polyline",
                points=[{"x": 540.0, "y": 420.0}, {"x": 540.0, "y": 300.0}, {"x": 720.0, "y": 300.0}],
                bounds={"x": 540.0, "y": 300.0, "width": 180.0, "height": 120.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=False,
            ),
        ]

        options = generate_layout_options(
            "project_a",
            [page],
            [],
            [],
            source_paths={"src_single": "/packages/DEMO-ME-4CDA01_ DEMO - MECHANICAL CDA GENERATION P&ID.pdf"},
        )
        _option, document = self._source_driven(options)

        reconstruction_vectors = [obj for obj in document.objects if obj.metadata.get("singleSheetReconstructionVector") is True]
        labels = {obj.label for obj in document.objects if obj.metadata.get("singleSheetReconstructionText") is True}

        self.assertEqual(len(reconstruction_vectors), 2)
        self.assertTrue(all(obj.style.stroke == "#000000" for obj in reconstruction_vectors))
        self.assertFalse(any(obj.metadata.get("systemColorApplied") is True for obj in reconstruction_vectors))
        self.assertFalse(any(obj.label == "SOURCE-DRIVEN COMBINED P&ID" for obj in document.objects))
        self.assertFalse(any(obj.id.startswith("overview_region_group_") for obj in document.objects))
        self.assertIn('6"-CDA-SS01', labels)
        self.assertIn("R-DEMO-CDA-C-01", labels)
        self.assertIn("PIT-101", labels)
        self.assertNotIn("CXA COMMENT", labels)

    def test_source_reconstruction_colors_vectors_from_nearby_line_tags(self):
        vector = VectorSegment(
            id="src_a_p1:chw_line",
            kind="line",
            points=[{"x": 100.0, "y": 200.0}, {"x": 600.0, "y": 200.0}],
            bounds={"x": 100.0, "y": 200.0, "width": 500.0, "height": 0.0},
            stroke="#000000",
            strokeWidth=1.0,
            dashed=False,
        )
        page = PageEvidence(
            "src_a_p1",
            "src_a",
            1,
            900.0,
            600.0,
            0,
            {"x": 0, "y": 0, "width": 900, "height": 600},
            [TextSpan('12"-CHWS-CS02', 120.0, 178.0, 110.0, 12.0)],
            1,
            [vector],
        )
        second_page = PageEvidence(
            "src_b_p1",
            "src_b",
            1,
            900.0,
            600.0,
            0,
            {"x": 0, "y": 0, "width": 900, "height": 600},
            [TextSpan("REFERENCE ONLY", 120.0, 178.0, 110.0, 12.0)],
            1,
            [],
        )

        _option, document = self._source_driven(generate_layout_options("project_vector_system_color", [page, second_page], [], []))

        reconstructed = next(obj for obj in document.objects if obj.metadata.get("sourceVectorId") == "src_a_p1:chw_line")
        self.assertEqual(reconstructed.metadata.get("system"), "CHW")
        self.assertTrue(reconstructed.metadata.get("systemColorApplied"))
        self.assertNotEqual(reconstructed.style.stroke, "#111827")
        self.assertIsNone(reconstructed.style.dash)

    def test_source_reconstruction_propagates_system_color_across_connected_pipe_run(self):
        tagged_branch = VectorSegment(
            id="src_a_p1:tagged_branch",
            kind="line",
            points=[{"x": 180.0, "y": 220.0}, {"x": 360.0, "y": 220.0}],
            bounds={"x": 180.0, "y": 220.0, "width": 180.0, "height": 0.0},
            stroke="#000000",
            strokeWidth=1.0,
            dashed=False,
        )
        connected_run = VectorSegment(
            id="src_a_p1:connected_run",
            kind="line",
            points=[{"x": 100.0, "y": 420.0}, {"x": 700.0, "y": 420.0}],
            bounds={"x": 100.0, "y": 420.0, "width": 600.0, "height": 0.0},
            stroke="#000000",
            strokeWidth=1.2,
            dashed=False,
        )
        tee_drop = VectorSegment(
            id="src_a_p1:tee_drop",
            kind="line",
            points=[{"x": 360.0, "y": 220.0}, {"x": 360.0, "y": 420.0}],
            bounds={"x": 360.0, "y": 220.0, "width": 0.0, "height": 200.0},
            stroke="#000000",
            strokeWidth=1.0,
            dashed=False,
        )
        page = PageEvidence(
            "src_a_p1",
            "src_a",
            1,
            900.0,
            600.0,
            0,
            {"x": 0, "y": 0, "width": 900, "height": 600},
            [TextSpan('12"-HHWS-CS02', 190.0, 198.0, 120.0, 12.0)],
            1,
            [connected_run, tagged_branch, tee_drop],
        )
        second_page = PageEvidence(
            "src_b_p1",
            "src_b",
            1,
            900.0,
            600.0,
            0,
            {"x": 0, "y": 0, "width": 900, "height": 600},
            [],
            1,
            [],
        )

        _option, document = self._source_driven(generate_layout_options("project_vector_connected_system_color", [page, second_page], [], []))

        reconstructed_by_source = {
            obj.metadata.get("sourceVectorId"): obj
            for obj in document.objects
            if obj.metadata.get("singleSheetReconstructionVector") is True
        }
        self.assertEqual(reconstructed_by_source["src_a_p1:tagged_branch"].metadata.get("system"), "HHW")
        self.assertEqual(reconstructed_by_source["src_a_p1:tee_drop"].metadata.get("system"), "HHW")
        self.assertEqual(reconstructed_by_source["src_a_p1:connected_run"].metadata.get("system"), "HHW")
        self.assertTrue(reconstructed_by_source["src_a_p1:connected_run"].metadata.get("systemColorApplied"))
        self.assertLess(reconstructed_by_source["src_a_p1:connected_run"].style.strokeWidth, 1.0)

    def test_source_reconstruction_preserves_raw_vector_stroke_without_nearby_system_text(self):
        vector = VectorSegment(
            id="src_a_p1:raw_line",
            kind="line",
            points=[{"x": 100.0, "y": 200.0}, {"x": 600.0, "y": 200.0}],
            bounds={"x": 100.0, "y": 200.0, "width": 500.0, "height": 0.0},
            stroke="#445566",
            strokeWidth=1.0,
            dashed=False,
        )
        page = PageEvidence(
            "src_a_p1",
            "src_a",
            1,
            900.0,
            600.0,
            0,
            {"x": 0, "y": 0, "width": 900, "height": 600},
            [TextSpan("PIT-101", 120.0, 178.0, 80.0, 12.0)],
            1,
            [vector],
        )
        second_page = PageEvidence(
            "src_b_p1",
            "src_b",
            1,
            900.0,
            600.0,
            0,
            {"x": 0, "y": 0, "width": 900, "height": 600},
            [],
            1,
            [],
        )

        _option, document = self._source_driven(generate_layout_options("project_vector_raw_color", [page, second_page], [], []))

        reconstructed = next(obj for obj in document.objects if obj.metadata.get("sourceVectorId") == "src_a_p1:raw_line")
        self.assertEqual(reconstructed.style.stroke, "#445566")
        self.assertFalse(reconstructed.metadata.get("systemColorApplied"))

    def test_source_reconstruction_does_not_color_long_vector_from_distant_system_tag(self):
        vector = VectorSegment(
            id="src_a_p1:long_line",
            kind="line",
            points=[{"x": 100.0, "y": 200.0}, {"x": 860.0, "y": 200.0}],
            bounds={"x": 100.0, "y": 200.0, "width": 760.0, "height": 0.0},
            stroke="#000000",
            strokeWidth=1.0,
            dashed=False,
        )
        page = PageEvidence(
            "src_a_p1",
            "src_a",
            1,
            900.0,
            600.0,
            0,
            {"x": 0, "y": 0, "width": 900, "height": 600},
            [TextSpan('12"-CHWS-CS02', 780.0, 232.0, 110.0, 12.0)],
            1,
            [vector],
        )
        second_page = PageEvidence(
            "src_b_p1",
            "src_b",
            1,
            900.0,
            600.0,
            0,
            {"x": 0, "y": 0, "width": 900, "height": 600},
            [],
            1,
            [],
        )

        _option, document = self._source_driven(generate_layout_options("project_vector_far_tag", [page, second_page], [], []))

        reconstructed = next(obj for obj in document.objects if obj.metadata.get("sourceVectorId") == "src_a_p1:long_line")
        self.assertEqual(reconstructed.style.stroke, "#000000")
        self.assertFalse(reconstructed.metadata.get("systemColorApplied"))

    def test_source_reconstruction_preserves_solid_vector_dash_when_system_entry_is_dashed(self):
        system_spans = [
            TextSpan(f'1"-SYS{chr(65 + index)}-CS01', 20.0, 20.0 + index * 14.0, 110.0, 10.0)
            for index in range(10)
        ]
        vector = VectorSegment(
            id="src_a_p1:late_system_line",
            kind="line",
            points=[{"x": 100.0, "y": 250.0}, {"x": 600.0, "y": 250.0}],
            bounds={"x": 100.0, "y": 250.0, "width": 500.0, "height": 0.0},
            stroke="#000000",
            strokeWidth=1.0,
            dashed=False,
        )
        page = PageEvidence(
            "src_a_p1",
            "src_a",
            1,
            900.0,
            600.0,
            0,
            {"x": 0, "y": 0, "width": 900, "height": 600},
            system_spans + [TextSpan('1"-SYSK-CS01', 120.0, 228.0, 110.0, 12.0)],
            1,
            [vector],
        )
        second_page = PageEvidence(
            "src_b_p1",
            "src_b",
            1,
            900.0,
            600.0,
            0,
            {"x": 0, "y": 0, "width": 900, "height": 600},
            [],
            1,
            [],
        )

        _option, document = self._source_driven(generate_layout_options("project_vector_solid_dash", [page, second_page], [], []))

        reconstructed = next(obj for obj in document.objects if obj.metadata.get("sourceVectorId") == "src_a_p1:late_system_line")
        self.assertEqual(reconstructed.metadata.get("system"), "SYSK")
        self.assertTrue(reconstructed.metadata.get("systemColorApplied"))
        self.assertIsNone(reconstructed.style.dash)

    def test_source_stitched_visual_hierarchy_matches_house_style(self):
        page_a = self._page(
            "src_a_p1",
            "src_a",
            'DEMO-ME-4CHW01 16"-CHWS-CS02 16"-CHWS-CS02 TO DEMO-ME-4CHW02',
        )
        page_a.rotation = 0
        page_a.textSpans = [TextSpan('16"-CHWS-CS02', 120.0, 178.0, 130.0, 12.0)]
        page_a.vectorSegments = [
            VectorSegment(
                id="src_a_p1:colored",
                kind="line",
                points=[{"x": 100.0, "y": 200.0}, {"x": 600.0, "y": 200.0}],
                bounds={"x": 100.0, "y": 200.0, "width": 500.0, "height": 0.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=False,
            ),
            VectorSegment(
                id="src_a_p1:future",
                kind="line",
                points=[{"x": 100.0, "y": 260.0}, {"x": 600.0, "y": 260.0}],
                bounds={"x": 100.0, "y": 260.0, "width": 500.0, "height": 0.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=True,
            ),
        ]
        page_b = self._page("src_b_p1", "src_b", 'DEMO-ME-4CHW02 16"-CHWS-CS02')
        candidate_a = self._candidate("a_to_b", "src_a", "to", '16"-CHWS-CS02', "CHWS", "right")
        candidate_b = self._candidate("b_from_a", "src_b", "from", '16"-CHWS-CS02', "CHWS", "left")
        match = ContinuationMatch("match_ab", "a_to_b", "b_from_a", 96.0, ["same line tag"], "confirmed")

        _option, document = self._source_driven(generate_layout_options("project_stitched_style", [page_a, page_b], [candidate_a, candidate_b], [match]))

        title = next(obj for obj in document.objects if obj.id.startswith("overview_label_source_stitched_title_"))
        subtitle = next(obj for obj in document.objects if obj.id.startswith("overview_label_source_stitched_subtitle_"))
        colored = next(obj for obj in document.objects if obj.metadata.get("sourceVectorId") == "src_a_p1:colored")
        future = next(obj for obj in document.objects if obj.metadata.get("sourceVectorId") == "src_a_p1:future")
        legend_samples = [obj for obj in document.objects if obj.metadata.get("sourceDrivenLegendSample") is True]
        legend_frame = next(obj for obj in document.objects if obj.id.startswith("overview_region_source_driven_system_legend_frame_"))

        self.assertLessEqual(title.style.fontSize or 0.0, 16.0)
        self.assertLessEqual(subtitle.style.fontSize or 0.0, 8.5)
        self.assertLess(len(subtitle.label), 70)
        self.assertGreaterEqual(colored.style.strokeWidth, 0.7)
        self.assertLessEqual(colored.style.strokeWidth, 1.05)
        self.assertGreaterEqual(colored.style.opacity, 0.95)
        self.assertEqual(future.style.dash, [9.0, 5.0])
        self.assertLessEqual(future.style.opacity, 0.72)
        self.assertTrue(legend_samples)
        self.assertTrue(all(obj.kind == "pipe" for obj in legend_samples))
        self.assertLessEqual(legend_frame.style.opacity, 0.72)

    def test_source_driven_multi_pid_stitches_reconstructed_pages_by_continuation_match(self):
        page_a = self._page(
            "src_a_p1",
            "src_a",
            'DEMO-ME-4CHW01 16"-CHWS-CS02 R-DEMO-CHW-P-01 PIT-101',
        )
        page_a.rotation = 0
        page_a.textSpans = [
            TextSpan('16"-CHWS-CS02', 1120.0, 320.0, 130.0, 16.0),
            TextSpan('16"-CHWS-CS02 TO DEMO-ME-4CHW02', 1160.0, 300.0, 220.0, 16.0),
            TextSpan("R-DEMO-CHW-P-01", 420.0, 560.0, 150.0, 18.0),
        ]
        page_a.vectorSegments = [
            VectorSegment(
                id="src_a_p1:main",
                kind="line",
                points=[{"x": 220.0, "y": 320.0}, {"x": 1240.0, "y": 320.0}],
                bounds={"x": 220.0, "y": 320.0, "width": 1020.0, "height": 0.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=False,
            )
        ] + [
            VectorSegment(
                id="src_a_p1:pointer_marker",
                kind="polyline",
                points=[
                    {"x": 1188.0, "y": 304.0},
                    {"x": 1270.0, "y": 304.0},
                    {"x": 1292.0, "y": 320.0},
                    {"x": 1270.0, "y": 336.0},
                    {"x": 1188.0, "y": 336.0},
                    {"x": 1188.0, "y": 304.0},
                ],
                bounds={"x": 1188.0, "y": 304.0, "width": 104.0, "height": 32.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=False,
            )
        ] + [
            VectorSegment(
                id="src_a_p1:sheet_border_top",
                kind="line",
                points=[{"x": 0.0, "y": 0.0}, {"x": 900.0, "y": 0.0}],
                bounds={"x": 0.0, "y": 0.0, "width": 900.0, "height": 0.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=False,
            ),
            VectorSegment(
                id="src_a_p1:sheet_border_left",
                kind="line",
                points=[{"x": 0.0, "y": 0.0}, {"x": 0.0, "y": 620.0}],
                bounds={"x": 0.0, "y": 0.0, "width": 0.0, "height": 620.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=False,
            )
        ]
        page_b = self._page(
            "src_b_p1",
            "src_b",
            'DEMO-ME-4CHW02 16"-CHWS-CS02 R-DEMO-CHW-CH-01 FIT-202',
        )
        page_b.rotation = 0
        page_b.textSpans = [
            TextSpan('16"-CHWS-CS02', 150.0, 900.0, 130.0, 16.0),
            TextSpan('16"-CHWS-CS02 FROM DEMO-ME-4CHW01', 44.0, 884.0, 240.0, 16.0),
            TextSpan("R-DEMO-CHW-CH-01", 520.0, 560.0, 150.0, 18.0),
        ]
        page_b.vectorSegments = [
            VectorSegment(
                id="src_b_p1:main",
                kind="line",
                points=[{"x": 150.0, "y": 900.0}, {"x": 1180.0, "y": 900.0}],
                bounds={"x": 150.0, "y": 900.0, "width": 1030.0, "height": 0.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=False,
            )
        ] + [
            VectorSegment(
                id="src_b_p1:external_pointer_marker",
                kind="polyline",
                points=[
                    {"x": 1120.0, "y": 1200.0},
                    {"x": 1202.0, "y": 1200.0},
                    {"x": 1224.0, "y": 1216.0},
                    {"x": 1202.0, "y": 1232.0},
                    {"x": 1120.0, "y": 1232.0},
                    {"x": 1120.0, "y": 1200.0},
                ],
                bounds={"x": 1120.0, "y": 1200.0, "width": 104.0, "height": 32.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=False,
            )
        ]
        candidate_a = self._candidate("a_to_b", "src_a", "to", '16"-CHWS-CS02', "CHWS", "right")
        candidate_a.position = {"x": 1240.0, "y": 320.0}
        candidate_a.bounds = {"x": 1188.0, "y": 304.0, "width": 104.0, "height": 32.0}
        candidate_b = self._candidate("b_from_a", "src_b", "from", '16"-CHWS-CS02', "CHWS", "left")
        candidate_b.position = {"x": 150.0, "y": 900.0}
        candidate_b.bounds = {"x": 38.0, "y": 880.0, "width": 244.0, "height": 42.0}
        external_candidate = self._candidate("b_external", "src_b", "to", '8"-CHWR-CS02', "CHWR", "right")
        external_candidate.position = {"x": 1224.0, "y": 1216.0}
        external_candidate.bounds = {"x": 1120.0, "y": 1200.0, "width": 104.0, "height": 32.0}
        match = ContinuationMatch("match_ab", "a_to_b", "b_from_a", 96.0, ["same line tag", "to/from"], "confirmed")

        options = generate_layout_options(
            "project_a",
            [page_a, page_b],
            [candidate_a, candidate_b, external_candidate],
            [match],
            source_paths={
                "src_a": "/packages/DEMO-ME-4CHW01_ DEMO - MECHANICAL STANDARD CHILLER P&ID.pdf",
                "src_b": "/packages/DEMO-ME-4CHW02_ DEMO - MECHANICAL CHILLED WATER P&ID.pdf",
            },
        )
        option, document = self._source_driven(options)

        self.assertEqual(option.name, "Source-driven Combined P&ID")
        self.assertTrue(option.metrics["stitchedSourcePages"])
        self.assertEqual(option.metrics["stitchedPageTiles"], 2)
        self.assertFalse(any(obj.id.startswith("overview_region_group_") for obj in document.objects))
        self.assertFalse(any(obj.metadata.get("stitchedSourcePageTile") is True for obj in document.objects))
        reconstructed_vectors = [obj for obj in document.objects if obj.metadata.get("singleSheetReconstructionVector") is True]
        source_vector_ids = {obj.metadata.get("sourceVectorId") for obj in reconstructed_vectors}
        self.assertIn("src_a_p1:main", source_vector_ids)
        self.assertIn("src_b_p1:main", source_vector_ids)
        self.assertNotIn("src_a_p1:pointer_marker", source_vector_ids)
        self.assertNotIn("src_a_p1:sheet_border_top", source_vector_ids)
        self.assertNotIn("src_a_p1:sheet_border_left", source_vector_ids)
        self.assertIn("src_b_p1:external_pointer_marker", source_vector_ids)
        stitched_connectors = [obj for obj in document.objects if obj.kind == "pipe" and obj.metadata.get("stitchedContinuationMatchId") == "match_ab"]
        self.assertEqual(len(stitched_connectors), 1)
        self.assertEqual(stitched_connectors[0].metadata.get("lineTag"), '16"-CHWS-CS02')
        self.assertEqual(stitched_connectors[0].style.stroke, "#0070c0")
        self.assertFalse(stitched_connectors[0].metadata.get("arrowEnd"))
        self.assertEqual(stitched_connectors[0].metadata.get("connectorRole"), "matchedOffPageContinuation")
        self.assertAlmostEqual(stitched_connectors[0].points[0]["y"], stitched_connectors[0].points[-1]["y"], delta=1.0)
        self.assertIn('16"-CHWS-CS02', " ".join(obj.label for obj in document.objects))
        self.assertIn("R-DEMO-CHW-P-01", " ".join(obj.label for obj in document.objects))
        self.assertIn("R-DEMO-CHW-CH-01", " ".join(obj.label for obj in document.objects))
        reconstructed_labels = [
            obj.label
            for obj in document.objects
            if obj.metadata.get("singleSheetReconstructionText") is True
        ]
        self.assertFalse(any("TO DEMO-ME-4CHW02" in label for label in reconstructed_labels))
        self.assertFalse(any("FROM DEMO-ME-4CHW01" in label for label in reconstructed_labels))

    def test_source_stitched_pages_are_compacted_with_quiet_continuation_connectors(self):
        def source_page(page_id, source_id, line_y):
            page = PageEvidence(
                page_id,
                source_id,
                1,
                1400.0,
                900.0,
                0,
                {"x": 0.0, "y": 0.0, "width": 1400.0, "height": 900.0},
                [TextSpan('12"-CHWS-CS01', 560.0, line_y - 26.0, 130.0, 16.0)],
                1,
            )
            page.vectorSegments = [
                VectorSegment(
                    id=f"{page_id}:main",
                    kind="line",
                    points=[{"x": 120.0, "y": line_y}, {"x": 1280.0, "y": line_y}],
                    bounds={"x": 120.0, "y": line_y, "width": 1160.0, "height": 0.0},
                    stroke="#000000",
                    strokeWidth=1.0,
                    dashed=False,
                )
            ]
            return page

        def continuation(candidate_id, source_id, direction, edge, x, y):
            return ContinuationCandidate(
                id=candidate_id,
                sourceFileId=source_id,
                page=1,
                sheetRef=None,
                direction=direction,
                label=f'{direction.upper()} 12"-CHWS-CS01',
                lineTag='12"-CHWS-CS01',
                system="CHWS",
                edge=edge,
                position={"x": x, "y": y},
                bounds={"x": x - 40.0, "y": y - 12.0, "width": 80.0, "height": 24.0},
                confidence=0.9,
                evidenceText=f'{direction.upper()} 12"-CHWS-CS01',
            )

        pages = [
            source_page("src_a_p1", "src_a", 240.0),
            source_page("src_b_p1", "src_b", 250.0),
            source_page("src_c_p1", "src_c", 260.0),
        ]
        candidates = [
            continuation("a_to_b", "src_a", "to", "right", 1280.0, 240.0),
            continuation("b_from_a", "src_b", "from", "left", 120.0, 250.0),
            continuation("b_to_c", "src_b", "to", "right", 1280.0, 250.0),
            continuation("c_from_b", "src_c", "from", "left", 120.0, 260.0),
        ]
        matches = [
            ContinuationMatch("ab", "a_to_b", "b_from_a", 96.0, ["same line tag"], "confirmed"),
            ContinuationMatch("bc", "b_to_c", "c_from_b", 95.0, ["same line tag"], "confirmed"),
        ]

        _option, document = self._source_driven(generate_layout_options("project_compact_stitch", pages, candidates, matches))
        connectors = [
            obj
            for obj in document.objects
            if obj.kind == "pipe" and obj.metadata.get("connectorRole") == "matchedOffPageContinuation"
        ]
        labels = [
            obj
            for obj in document.objects
            if obj.kind == "label" and obj.metadata.get("connectorRole") == "matchedOffPageContinuationLabel"
        ]

        self.assertLess(document.width, 4300.0)
        self.assertEqual(len(connectors), 2)
        for connector in connectors:
            routed_length = sum(
                ((end["x"] - start["x"]) ** 2 + (end["y"] - start["y"]) ** 2) ** 0.5
                for start, end in zip(connector.points, connector.points[1:])
            )
            self.assertLess(routed_length, 300.0)
            self.assertLessEqual(connector.style.strokeWidth, 1.0)
            self.assertLessEqual(connector.style.opacity, 0.78)

        self.assertEqual(len(labels), 2)
        for label in labels:
            self.assertLessEqual(label.style.fontSize or 0.0, 5.8)
            self.assertLessEqual(label.style.opacity, 0.7)
            self.assertLessEqual(label.bounds["width"], 160.0)

    def test_source_driven_legend_uses_detected_dynamic_systems(self):
        page = self._page(
            "src_elec_p1",
            "src_elec",
            '480V-FEEDER-MCC-01 12"-CHWS-CS02',
        )

        _option, document = self._source_driven(generate_layout_options("project_dynamic_systems", [page], [], [], {"src_elec": "Electrical feeder P&ID.pdf"}))

        labels = [
            obj.label
            for obj in document.objects
            if obj.kind == "label" and obj.metadata.get("sourceDrivenLegend") is True
        ]

        self.assertIn("480V", labels)
        self.assertIn("CHW / TCHW", labels)
        self.assertNotIn("HHWR", labels)

    def test_source_driven_legend_filters_electrical_annotations_from_process_sheets(self):
        page = self._page(
            "src_mech_p1",
            "src_mech",
            '480V PANEL 10"-HHWS-CS02 10"-HHWR-CS02',
        )

        _option, document = self._source_driven(generate_layout_options(
            "project_process_systems",
            [page],
            [],
            [],
            {"src_mech": "DEMO-ME-4HHW02 Mechanical Heating Hot Water P&ID.pdf"},
        ))

        labels = [
            obj.label
            for obj in document.objects
            if obj.kind == "label" and obj.metadata.get("sourceDrivenLegend") is True
        ]

        self.assertIn("HHW", labels)
        self.assertNotIn("480V", labels)
        self.assertNotIn("PANEL", labels)

    def test_matched_connector_uses_dynamic_system_color(self):
        page_a = self._page(
            "src_elec_a_p1",
            "src_elec_a",
            "480V-FEEDER-MCC-01 MCC-A",
        )
        page_b = self._page(
            "src_elec_b_p1",
            "src_elec_b",
            "480V-FEEDER-MCC-01 MCC-B",
        )
        candidate_a = self._candidate("elec_a_to_b", "src_elec_a", "to", "480V-FEEDER-MCC-01", "", "right")
        candidate_a.position = {"x": 1000.0, "y": 120.0}
        candidate_b = self._candidate("elec_b_from_a", "src_elec_b", "from", "480V-FEEDER-MCC-01", "", "left")
        candidate_b.position = {"x": 120.0, "y": 120.0}
        match = ContinuationMatch("elec_match", "elec_a_to_b", "elec_b_from_a", 96.0, ["same line tag", "to/from"], "confirmed")

        _option, document = self._source_driven(generate_layout_options(
            "project_dynamic_systems",
            [page_a, page_b],
            [candidate_a, candidate_b],
            [match],
            {"src_elec_a": "Electrical feeder A.pdf", "src_elec_b": "Electrical feeder B.pdf"},
        ))

        connector = next(
            obj
            for obj in document.objects
            if obj.kind == "pipe" and obj.metadata.get("stitchedContinuationMatchId") == "elec_match"
        )

        self.assertNotEqual(connector.style.stroke, "#111827")
        self.assertEqual(connector.style.stroke, "#0070c0")
        self.assertEqual(connector.metadata.get("system"), "480V")

    def test_matched_mechanical_connectors_preserve_exact_system_colors(self):
        page_a = self._page(
            "src_hhw_a_p1",
            "src_hhw_a",
            'DEMO-ME-4HHW01 12"-HHWS-CS01 10"-HHWR-CS01',
        )
        page_b = self._page(
            "src_hhw_b_p1",
            "src_hhw_b",
            'DEMO-ME-4HHW02 12"-HHWS-CS01 10"-HHWR-CS01',
        )
        hhws_a = self._candidate("hhws_a_to_b", "src_hhw_a", "to", '12"-HHWS-CS01', "", "right")
        hhws_a.position = {"x": 1000.0, "y": 120.0}
        hhws_b = self._candidate("hhws_b_from_a", "src_hhw_b", "from", '12"-HHWS-CS01', "", "left")
        hhws_b.position = {"x": 120.0, "y": 120.0}
        hhwr_a = self._candidate("hhwr_a_to_b", "src_hhw_a", "to", '10"-HHWR-CS01', "", "right")
        hhwr_a.position = {"x": 1000.0, "y": 220.0}
        hhwr_b = self._candidate("hhwr_b_from_a", "src_hhw_b", "from", '10"-HHWR-CS01', "", "left")
        hhwr_b.position = {"x": 120.0, "y": 220.0}
        matches = [
            ContinuationMatch("hhws_match", "hhws_a_to_b", "hhws_b_from_a", 96.0, ["same line tag"], "confirmed"),
            ContinuationMatch("hhwr_match", "hhwr_a_to_b", "hhwr_b_from_a", 95.0, ["same line tag"], "confirmed"),
        ]

        _option, document = self._source_driven(generate_layout_options(
            "project_mechanical_colors",
            [page_a, page_b],
            [hhws_a, hhws_b, hhwr_a, hhwr_b],
            matches,
            {
                "src_hhw_a": "/packages/DEMO-ME-4HHW01_ DEMO - MECHANICAL HEATING HOT WATER P&ID.pdf",
                "src_hhw_b": "/packages/DEMO-ME-4HHW02_ DEMO - MECHANICAL HEATING HOT WATER P&ID.pdf",
            },
        ))
        connectors = {
            obj.metadata.get("stitchedContinuationMatchId"): obj
            for obj in document.objects
            if obj.kind == "pipe" and obj.metadata.get("connectorRole") == "matchedOffPageContinuation"
        }

        self.assertEqual(connectors["hhws_match"].metadata.get("system"), "HHWS")
        self.assertEqual(connectors["hhws_match"].style.stroke, "#ff0000")
        self.assertEqual(connectors["hhwr_match"].metadata.get("system"), "HHWR")
        self.assertEqual(connectors["hhwr_match"].style.stroke, "#ff0000")

    def test_matched_connector_falls_back_to_source_group_color_when_tag_missing(self):
        page_a = self._page("src_hhw_a_p1", "src_hhw_a", "DEMO-ME-4HHW01 HEATING HOT WATER")
        page_b = self._page("src_hhw_b_p1", "src_hhw_b", "DEMO-ME-4HHW02 HEATING HOT WATER")
        candidate_a = self._candidate("group_a_to_b", "src_hhw_a", "to", "", "", "right")
        candidate_a.label = "TO DEMO-ME-4HHW02"
        candidate_a.evidenceText = candidate_a.label
        candidate_a.position = {"x": 1000.0, "y": 120.0}
        candidate_b = self._candidate("group_b_from_a", "src_hhw_b", "from", "", "", "left")
        candidate_b.label = "FROM DEMO-ME-4HHW01"
        candidate_b.evidenceText = candidate_b.label
        candidate_b.position = {"x": 120.0, "y": 120.0}
        match = ContinuationMatch("group_match", "group_a_to_b", "group_b_from_a", 91.0, ["sheet ref"], "confirmed")

        _option, document = self._source_driven(generate_layout_options(
            "project_group_fallback",
            [page_a, page_b],
            [candidate_a, candidate_b],
            [match],
            {
                "src_hhw_a": "/packages/DEMO-ME-4HHW01_ DEMO - MECHANICAL HEATING HOT WATER P&ID.pdf",
                "src_hhw_b": "/packages/DEMO-ME-4HHW02_ DEMO - MECHANICAL HEATING HOT WATER P&ID.pdf",
            },
        ))
        connector = next(
            obj
            for obj in document.objects
            if obj.kind == "pipe" and obj.metadata.get("stitchedContinuationMatchId") == "group_match"
        )

        self.assertEqual(connector.metadata.get("system"), "HHWS")
        self.assertEqual(connector.style.stroke, "#ff0000")

    def test_generates_recommended_and_source_faithful_drawings(self):
        pages = [
            PageEvidence("src_a_p1", "src_a", 1, 3024.0, 2160.0, 270, {"x": 0, "y": 0, "width": 2800, "height": 1900}, [], 50),
            PageEvidence("src_b_p1", "src_b", 1, 3024.0, 2160.0, 270, {"x": 0, "y": 0, "width": 2800, "height": 1900}, [], 50),
        ]
        candidates = [
            self._candidate("a", "src_a", "to", '16"-CHWS-CS02', "CHWS", "right"),
            self._candidate("b", "src_b", "from", '16"-CHWS-CS02', "CHWS", "left"),
        ]
        matches = [ContinuationMatch("m1", "a", "b", 92.0, ["line tag", "to/from"], "confirmed")]
        options = generate_layout_options("project_a", pages, candidates, matches)
        self.assertGreaterEqual(len(options), 2)
        names = {option.name for option, _document in options}
        self.assertIn("Recommended", names)
        self.assertIn("Source-faithful", names)
        recommended = next(document for option, document in options if option.name == "Recommended")
        self.assertTrue(any(obj.kind == "pipe" for obj in recommended.objects))
        self.assertTrue(any(obj.kind == "label" for obj in recommended.objects))
        self.assertEqual(recommended.visualQa["disconnectedContinuations"], 0)

    def test_nonzero_crop_bounds_source_fragment_aligns_with_candidate_labels(self):
        pages = [
            PageEvidence(
                "src_a_p1",
                "src_a",
                1,
                3024.0,
                2160.0,
                270,
                {"x": 50.0, "y": 40.0, "width": 2800.0, "height": 1900.0},
                [],
                50,
            )
        ]
        candidates = [self._candidate("a", "src_a", "to", '16"-CHWS-CS02', "CHWS", "right")]

        options = generate_layout_options("project_a", pages, candidates, [])
        _option, document = next(item for item in options if item[0].name == "Source-faithful")

        fragment = next(obj for obj in document.objects if obj.kind == "source_fragment")
        label = next(obj for obj in document.objects if obj.kind == "label")
        self.assertEqual(fragment.bounds["x"], 160.0)
        self.assertEqual(fragment.bounds["y"], 160.0)
        self.assertEqual(label.bounds["x"], fragment.bounds["x"] + 50.0)
        self.assertEqual(label.bounds["y"], fragment.bounds["y"] + 60.0)

    def test_recommended_layout_is_editable_combined_pid_not_source_montage(self):
        pages = [
            PageEvidence("src_a_p1", "src_a", 1, 3024.0, 2160.0, 270, {"x": 0, "y": 0, "width": 2800, "height": 1900}, [], 50)
        ]

        options = generate_layout_options("project_a", pages, [], [])
        _option, document = next(item for item in options if item[0].name == "Recommended")

        self.assertTrue(any(obj.kind == "symbol" for obj in document.objects))
        self.assertTrue(any(obj.kind == "pipe" for obj in document.objects))
        self.assertFalse(any(obj.kind == "source_fragment" for obj in document.objects))

    def test_clean_overview_keeps_horizontal_system_preview(self):
        pages = self._system_pages()

        options = generate_layout_options("project_a", pages, [], [], source_paths=self._system_source_paths())
        _option, document = next(item for item in options if item[0].name == "Clean overview")

        band_regions = [obj for obj in document.objects if obj.kind == "region" and obj.id.startswith("overview_region_group_")]
        self.assertGreaterEqual(len(band_regions), 3)
        self.assertTrue(any(obj.metadata.get("layoutMode") == "clean_overview" for obj in document.objects))

    def test_recommended_layout_uses_reference_style_single_sheet(self):
        pages = self._system_pages()
        candidates = [
            self._candidate("cda_to_dryers", "src_cda_01", "to", '6"-CDA-SS01', "CDA", "right"),
            self._candidate("chw_to_distribution", "src_chw_02", "to", '24"-CHWS-CS01', "CHWS", "right"),
            self._candidate("hhw_to_distribution", "src_hhw_02", "to", '12"-HHWS-CS01', "HHWS", "right"),
        ]
        candidates[0].sheetRef = "DEMO-ME-4CDA02"
        candidates[1].sheetRef = "DEMO-ME-4CHW03"
        candidates[2].sheetRef = "DEMO-ME-4HHW03"

        options = generate_layout_options(
            "project_a",
            pages,
            candidates,
            [],
            source_paths=self._system_source_paths(),
        )
        _option, document = next(item for item in options if item[0].name == "Recommended")

        self.assertTrue(any(obj.metadata.get("layoutMode") == "combined_pid" for obj in document.objects))
        band_regions = [obj for obj in document.objects if obj.kind == "region" and obj.id.startswith("overview_region_group_")]
        self.assertEqual(band_regions, [])
        zone_labels = {obj.label for obj in document.objects if obj.kind == "region"}
        self.assertIn("CHILLED WATER / COOLING WATER", zone_labels)
        self.assertIn("HEATED HOT WATER / HRW", zone_labels)
        self.assertIn("CDA / IA", zone_labels)
        pipes = [obj for obj in document.objects if obj.kind == "pipe"]
        self.assertTrue(any(obj.bounds["height"] > 800.0 for obj in pipes))
        self.assertTrue(any(obj.bounds["width"] > 1500.0 for obj in pipes))
        self.assertTrue(any(obj.kind == "symbol" and obj.metadata.get("symbolType") == "offpage" for obj in document.objects))

    def test_compiled_layout_uses_editable_source_derived_vectors(self):
        page = self._page(
            "src_chw_01_p1",
            "src_chw_01",
            'DEMO-ME-4CHW01 24"-CHWS-CS01 R-DEMO-CHW-CH-01 R-DEMO-CHW-P-01',
        )
        page.vectorSegments = [
            VectorSegment(
                id="src_chw_01_p1:vector_1_1",
                kind="line",
                points=[{"x": 220.0, "y": 380.0}, {"x": 1020.0, "y": 380.0}],
                bounds={"x": 220.0, "y": 380.0, "width": 800.0, "height": 0.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=False,
            ),
            VectorSegment(
                id="src_chw_01_p1:artifact_hairline",
                kind="line",
                points=[{"x": 520.0, "y": 620.0}, {"x": 520.0, "y": 644.0}],
                bounds={"x": 520.0, "y": 620.0, "width": 0.0, "height": 24.0},
                stroke="#000000",
                strokeWidth=0.5,
                dashed=False,
            )
        ]

        with patch.dict(os.environ, {"RECREATION_VISIO_TEMPLATE_DIR": "/tmp/recreation-missing-visio-templates"}):
            options = generate_layout_options("project_a", [page], [], [], source_paths=self._system_source_paths())
        option, document = next(item for item in options if item[0].name == "Compiled CHW/CW")

        source_vectors = [obj for obj in document.objects if obj.metadata.get("sourceDerived") is True]
        self.assertGreaterEqual(len(source_vectors), 1)
        self.assertTrue(all(obj.kind == "pipe" and not obj.locked for obj in source_vectors))
        self.assertTrue(all(obj.style.opacity <= 0.46 for obj in source_vectors))
        self.assertTrue(all(obj.style.stroke != "#111827" for obj in source_vectors))
        self.assertFalse(any(obj.metadata.get("sourceVectorId") == "src_chw_01_p1:artifact_hairline" for obj in source_vectors))
        self.assertEqual(option.metrics["sourceVectorObjects"], len(source_vectors))

    def test_source_generated_chw_cw_uses_source_content_without_template_objects(self):
        page = self._page(
            "src_chw_01_p1",
            "src_chw_01",
            'DEMO-ME-4CHW01 24"-CHWS-CS01 24"-CHWR-CS01 18"-CWS-CS01 R-DEMO-CHW-CH-01 R-DEMO-CHW-P-01',
        )
        page.vectorSegments = [
            VectorSegment(
                id="src_chw_01_p1:vector_1_1",
                kind="line",
                points=[{"x": 240.0, "y": 420.0}, {"x": 1040.0, "y": 420.0}],
                bounds={"x": 240.0, "y": 420.0, "width": 800.0, "height": 0.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=False,
            )
        ]
        candidate = self._candidate("chw_source_ref", "src_chw_01", "to", '24"-CHWS-CS01', "CHWS", "right")
        candidate.sheetRef = "DEMO-ME-4CHW02"
        candidate.label = '24"-CHWS-CS01 TO DEMO-ME-4CHW02'
        candidate.evidenceText = candidate.label
        equipment_candidate = self._candidate("chw_source_equipment_ref", "src_chw_01", "to", "", "CHWS", "right")
        equipment_candidate.sheetRef = "DEMO-ME-4CHW03"
        equipment_candidate.label = "TO EQUIPMENT HVAC CHW COILS 1 DEMO-ME-4CHW03"
        equipment_candidate.evidenceText = equipment_candidate.label

        with patch.dict(os.environ, {"RECREATION_VISIO_TEMPLATE_DIR": "/tmp/recreation-missing-visio-templates"}):
            options = generate_layout_options(
                "project_a",
                [page],
                [candidate, equipment_candidate],
                [],
                source_paths=self._system_source_paths(),
            )
        option, document = next(item for item in options if item[0].name == "Source-generated CHW/CW")

        self.assertTrue(option.metrics["sourceGenerated"])
        self.assertGreater(option.metrics["sourceVectorObjects"], 0)
        self.assertTrue(all(obj.metadata.get("sourceGenerated") is True for obj in document.objects))
        self.assertFalse(any(obj.metadata.get("templateDerived") is True for obj in document.objects))
        self.assertTrue(any("24\"-CHWS-CS01" in obj.label for obj in document.objects))
        self.assertTrue(any(obj.metadata.get("sourceDerived") is True for obj in document.objects))
        self.assertEqual(option.metrics["sourceAssemblies"], 4)
        self.assertTrue(any(obj.metadata.get("sourceAssembly") == "chiller_bank" for obj in document.objects))
        self.assertTrue(any(obj.metadata.get("sourceGeneratedDetailBox") == "chiller_bank" for obj in document.objects))
        self.assertTrue(any(obj.metadata.get("sourceGeneratedDistribution") is True for obj in document.objects))
        distribution_labels = [obj for obj in document.objects if obj.metadata.get("sourceGeneratedDistributionLabel") is True]
        self.assertGreaterEqual(len(distribution_labels), 2)
        self.assertTrue(any(obj.metadata.get("distributionLabelRole") == "line" for obj in distribution_labels))
        self.assertTrue(any(obj.metadata.get("distributionLabelRole") == "target" for obj in distribution_labels))
        self.assertTrue(all(" / " not in obj.label for obj in distribution_labels))
        self.assertTrue(all(obj.bounds["width"] <= 230.0 for obj in distribution_labels))
        line_labels = [obj.label for obj in distribution_labels if obj.metadata.get("distributionLabelRole") == "line"]
        self.assertFalse(any(label in {"TO", "FROM", "REF"} for label in line_labels))
        self.assertTrue(any("EQUIPMENT HVAC" in label for label in line_labels))
        self.assertTrue(any(obj.metadata.get("sourceGeneratedLineRack") is True for obj in document.objects))
        polished_routes = [obj for obj in document.objects if obj.metadata.get("sourceGeneratedRoutingPolish") is True]
        self.assertGreaterEqual(len(polished_routes), 3)
        self.assertTrue(all(obj.bounds["height"] < 1400.0 for obj in polished_routes if obj.kind == "pipe"))

    def test_source_generated_hhw_hrw_uses_source_content_without_template_objects(self):
        pages = [
            self._page(
                "src_hhw_02_p1",
                "src_hhw_02",
                'DEMO-ME-4HHW02 12"-HHWS-CS01 12"-HHWR-CS01 8"-HRW-CS01 R-DEMO-HHW-HWB-01 R-DEMO-HHW-P-01 R-DEMO-HRW-HX-01',
            ),
            self._page(
                "src_hrw_01_p1",
                "src_hrw_01",
                'DEMO-ME-4HRW01 10"-HHWS-CS02 10"-HHWR-CS02 20"-SHRWR-CS02 R-DEMO-HRW-P-01 R-DEMO-HRW-HX-02',
            ),
        ]
        pages[0].vectorSegments = [
            VectorSegment(
                id="src_hhw_02_p1:vector_1_1",
                kind="line",
                points=[{"x": 260.0, "y": 460.0}, {"x": 1180.0, "y": 460.0}],
                bounds={"x": 260.0, "y": 460.0, "width": 920.0, "height": 0.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=False,
            )
        ]
        pages[1].vectorSegments = [
            VectorSegment(
                id="src_hrw_01_p1:vector_1_1",
                kind="line",
                points=[{"x": 320.0, "y": 520.0}, {"x": 320.0, "y": 1250.0}],
                bounds={"x": 320.0, "y": 520.0, "width": 0.0, "height": 730.0},
                stroke="#000000",
                strokeWidth=1.0,
                dashed=False,
            )
        ]
        candidate = self._candidate("hhw_source_ref", "src_hhw_02", "to", '12"-HHWS-CS01', "HHWS", "right")
        candidate.sheetRef = "DEMO-ME-4HHW03"
        candidate.label = '12"-HHWS-CS01 TO DEMO-ME-4HHW03'
        candidate.evidenceText = candidate.label
        hrw_candidate = self._candidate("hrw_source_ref", "src_hrw_01", "from", '20"-SHRWR-CS02', "HRW", "left")
        hrw_candidate.sheetRef = "DEMO-ME-5MAU01"
        hrw_candidate.label = '20"-SHRWR-CS02 FROM DEMO-ME-5MAU01'
        hrw_candidate.evidenceText = hrw_candidate.label

        with patch.dict(os.environ, {"RECREATION_VISIO_TEMPLATE_DIR": "/tmp/recreation-missing-visio-templates"}):
            options = generate_layout_options(
                "project_a",
                pages,
                [candidate, hrw_candidate],
                [],
                source_paths={
                    "src_hhw_02": "/packages/DEMO-ME-4HHW02_ DEMO - MECHANICAL HEATING HOT WATER SYSTEM P&ID.pdf",
                    "src_hrw_01": "/packages/DEMO-ME-4HRW01_ DEMO - MECHANICAL HEAT RECOVERY WATER SYSTEM P&ID.pdf",
                },
            )
        option, document = next(item for item in options if item[0].name == "Source-generated HHW/HRW")

        self.assertTrue(option.metrics["sourceGenerated"])
        self.assertGreater(option.metrics["sourceVectorObjects"], 0)
        self.assertGreaterEqual(option.metrics["sourcePages"], 2)
        self.assertTrue(all(obj.metadata.get("sourceGenerated") is True for obj in document.objects))
        self.assertFalse(any(obj.metadata.get("templateDerived") is True for obj in document.objects))
        self.assertTrue(any("12\"-HHWS-CS01" in obj.label for obj in document.objects))
        self.assertTrue(any("20\"-SHRWR-CS02" in obj.label for obj in document.objects))
        self.assertTrue(any(obj.metadata.get("sourceDerived") is True for obj in document.objects))
        self.assertTrue(any(obj.metadata.get("sourceGeneratedDetailBox") == "hhw_boilers" for obj in document.objects))
        self.assertTrue(any(obj.metadata.get("sourceGeneratedDetailBox") == "hrw_recovery" for obj in document.objects))

    def test_presentation_clean_hhw_hrw_keeps_source_coverage_with_less_visual_noise(self):
        pages = [
            self._page(
                "src_hhw_02_p1",
                "src_hhw_02",
                'DEMO-ME-4HHW02 12"-HHWS-CS01 12"-HHWR-CS01 R-HHW-HWB-01 R-HHW-P-01',
            ),
            self._page(
                "src_hrw_01_p1",
                "src_hrw_01",
                'DEMO-ME-4HRW01 24"-HRW-CS02 20"-SHRWR-CS02 R-HRW-HX-01 R-HRW-P-01 DEMO-ME-5MAU01',
            ),
        ]
        for page in pages:
            page.vectorSegments = [
                VectorSegment(
                    id=f"{page.id}:vector_{index}",
                    kind="line",
                    points=[{"x": 200.0 + index * 20.0, "y": 420.0}, {"x": 980.0, "y": 420.0 + index * 8.0}],
                    bounds={"x": 200.0 + index * 20.0, "y": 420.0, "width": 780.0 - index * 20.0, "height": index * 8.0},
                    stroke="#000000",
                    strokeWidth=1.0,
                    dashed=False,
                )
                for index in range(40)
            ]
        candidate = self._candidate("hhw_clean_ref", "src_hhw_02", "to", '12"-HHWS-CS01', "HHWS", "right")
        candidate.sheetRef = "DEMO-ME-4HHW03"
        candidate.label = '12"-HHWS-CS01 TO DEMO-ME-4HHW03'
        candidate.evidenceText = candidate.label
        hrw_candidate = self._candidate("hrw_clean_ref", "src_hrw_01", "from", '20"-SHRWR-CS02', "HRW", "left")
        hrw_candidate.sheetRef = "DEMO-ME-5MAU01"
        hrw_candidate.label = '20"-SHRWR-CS02 FROM DEMO-ME-5MAU01'
        hrw_candidate.evidenceText = hrw_candidate.label

        with patch.dict(os.environ, {"RECREATION_VISIO_TEMPLATE_DIR": "/tmp/recreation-missing-visio-templates"}):
            options = generate_layout_options(
                "project_a",
                pages,
                [candidate, hrw_candidate],
                [],
                source_paths={
                    "src_hhw_02": "/packages/DEMO-ME-4HHW02_ DEMO - MECHANICAL HEATING HOT WATER SYSTEM P&ID.pdf",
                    "src_hrw_01": "/packages/DEMO-ME-4HRW01_ DEMO - MECHANICAL HEAT RECOVERY WATER SYSTEM P&ID.pdf",
                },
            )
        option, document = next(item for item in options if item[0].name == "Presentation-clean HHW/HRW")
        source_generated = next(document for opt, document in options if opt.name == "Source-generated HHW/HRW")

        self.assertTrue(option.metrics["sourceGenerated"])
        self.assertTrue(option.metrics["presentationClean"])
        self.assertFalse(any(obj.metadata.get("templateDerived") is True for obj in document.objects))
        self.assertLess(option.metrics["sourceVectorObjects"], source_generated.visualQa["sourceVectorObjects"] if "sourceVectorObjects" in source_generated.visualQa else 80)
        labels_and_metadata = "\n".join(obj.label for obj in document.objects) + "\n".join(str(obj.metadata) for obj in document.objects)
        self.assertIn('12"-HHWS-CS01', labels_and_metadata)
        self.assertIn('20"-SHRWR-CS02', labels_and_metadata)
        self.assertIn("R-HHW-HWB-01", labels_and_metadata)
        self.assertIn("R-HRW-HX-01", labels_and_metadata)
        self.assertIn("DEMO-ME-5MAU01", labels_and_metadata)
        self.assertTrue(any(obj.metadata.get("sourceGeneratedCoverageIndex") is True for obj in document.objects))
        route_bundle = [obj for obj in document.objects if obj.metadata.get("presentationRouteBundle") is True]
        self.assertGreaterEqual(len(route_bundle), 4)
        self.assertTrue({"HHWS", "HHWR", "HRW"}.issubset({obj.metadata.get("system") for obj in route_bundle}))
        continuation_rack = [obj for obj in document.objects if obj.metadata.get("presentationContinuationRack") is True]
        self.assertGreaterEqual(len(continuation_rack), 2)

    def test_full_combined_hhw_hrw_requires_all_equipment_tags_visible_in_drawing_body(self):
        pages = [
            self._page(
                "src_hhw_02_p1",
                "src_hhw_02",
                'DEMO-ME-4HHW02 12"-HHWS-CS02 12"-HHWR-CS02 R-HHW-HWB-01 R-HHW-HWB-02 R-HHW-P-10 P-01 P-02',
            ),
            self._page(
                "src_hrw_01_p1",
                "src_hrw_01",
                'DEMO-ME-4HRW01 24"-HRW-CS02 20"-SHRWS-CS02 R-HRW-HX-01 R-HRW-P-01 HX-XX',
            ),
            self._page(
                "src_hrw_02_p1",
                "src_hrw_02",
                'DEMO-ME-4HRW02 3"-SHRWS-CS02 3"-SHRWR-CS02 AHU-101 AHU-202 MAU-401 MAU-402',
            ),
        ]
        candidates = [
            self._candidate("hhw_supply_ref", "src_hhw_02", "to", '12"-HHWS-CS02', "HHWS", "right"),
            self._candidate("hrw_distribution_ref", "src_hrw_01", "to", '24"-HRW-CS02', "HRW", "right"),
        ]
        candidates[0].sheetRef = "DEMO-ME-4HRW01"
        candidates[1].sheetRef = "DEMO-ME-4HRW02"

        with patch.dict(os.environ, {"RECREATION_VISIO_TEMPLATE_DIR": "/tmp/recreation-missing-visio-templates"}):
            options = generate_layout_options(
                "project_a",
                pages,
                candidates,
                [],
                source_paths={
                    "src_hhw_02": "/packages/DEMO-ME-4HHW02_ DEMO - MECHANICAL HEATING HOT WATER SYSTEM P&ID.pdf",
                    "src_hrw_01": "/packages/DEMO-ME-4HRW01_ DEMO - MECHANICAL HEAT RECOVERY WATER SYSTEM P&ID.pdf",
                    "src_hrw_02": "/packages/DEMO-ME-4HRW02_ DEMO - MECHANICAL HEAT RECOVERY DISTRIBUTION P&ID.pdf",
                },
            )
        option, document = next(item for item in options if item[0].name == "Full Combined HHW/HRW")

        required_tags = {
            "R-HHW-HWB-01",
            "R-HHW-HWB-02",
            "R-HHW-P-10",
            "P-01",
            "P-02",
            "R-HRW-HX-01",
            "R-HRW-P-01",
            "HX-XX",
            "AHU-101",
            "AHU-202",
            "MAU-401",
            "MAU-402",
        }
        visible_required = {
            obj.metadata.get("equipmentTag")
            for obj in document.objects
            if obj.metadata.get("sourceRequiredEquipment") is True
            and obj.metadata.get("sourceGeneratedCoverageIndex") is not True
        }

        registered_required = visible_required | {
            item["tag"] for item in document.visualQa["equipmentRegister"]
        }

        self.assertEqual(required_tags, registered_required)
        self.assertFalse({"P-01", "P-02"} <= visible_required)
        self.assertTrue({"P-01", "P-02"} <= {item["tag"] for item in document.visualQa["equipmentRegister"]})
        self.assertEqual(option.metrics["requiredEquipmentTags"], len(required_tags))
        self.assertEqual(option.metrics["registeredEquipmentTags"], len(required_tags))
        self.assertEqual(option.metrics["missingRegisteredEquipmentTags"], 0)
        self.assertEqual(document.visualQa["missingRegisteredEquipmentTags"], 0)
        self.assertTrue(all(tag in "\n".join(obj.label for obj in document.objects) for tag in visible_required))

    def test_full_combined_hhw_hrw_uses_spacious_sheet_without_compact_coverage_index(self):
        line_tags = " ".join(f'{index}"-HHWS-CS{index:02d}' for index in range(1, 76))
        pages = [
            self._page(
                "src_hhw_02_p1",
                "src_hhw_02",
                f'DEMO-ME-4HHW02 {line_tags} R-HHW-HWB-01 R-HHW-HWB-02 R-HHW-HWB-03 R-HHW-HWB-04 R-HHW-P-01 R-HHW-P-02',
            ),
            self._page(
                "src_hrw_02_p1",
                "src_hrw_02",
                'DEMO-ME-4HRW02 24"-HRW-CS02 3"-SHRWS-CS02 AHU-101 AHU-202 AHU-303 AHU-304 MAU-401 MAU-402 MAU-403 MAU-404',
            ),
        ]

        with patch.dict(os.environ, {"RECREATION_VISIO_TEMPLATE_DIR": "/tmp/recreation-missing-visio-templates"}):
            options = generate_layout_options(
                "project_a",
                pages,
                [],
                [],
                source_paths={
                    "src_hhw_02": "/packages/DEMO-ME-4HHW02_ DEMO - MECHANICAL HEATING HOT WATER SYSTEM P&ID.pdf",
                    "src_hrw_02": "/packages/DEMO-ME-4HRW02_ DEMO - MECHANICAL HEAT RECOVERY DISTRIBUTION P&ID.pdf",
                },
            )
        _option, document = next(item for item in options if item[0].name == "Full Combined HHW/HRW")

        line_body_objects = [
            obj
            for obj in document.objects
            if obj.metadata.get("sourceRequiredLineTag") is True
        ]
        required_equipment_symbols = [
            obj
            for obj in document.objects
            if obj.metadata.get("sourceRequiredEquipment") is True and obj.kind == "symbol"
        ]

        self.assertGreaterEqual(document.width, 4200.0)
        self.assertGreaterEqual(document.height, 3600.0)
        self.assertEqual(line_body_objects, [])
        self.assertFalse(any(obj.label == "PUMP AND SKID EQUIPMENT" for obj in document.objects))
        self.assertEqual(len(document.visualQa["lineTagRegister"]), 77)
        self.assertTrue(any(item["tag"] == "R-HHW-P-01" for item in document.visualQa["equipmentRegister"]))
        self.assertTrue(any(item["tag"] == '75"-HHWS-CS75' for item in document.visualQa["lineTagRegister"]))
        self.assertFalse(any(obj.metadata.get("sourceGeneratedCoverageIndex") is True for obj in document.objects))
        self.assertTrue(required_equipment_symbols)
        self.assertTrue(all(obj.bounds["y"] + obj.bounds["height"] <= document.height - 260.0 for obj in required_equipment_symbols))
        self.assertEqual(document.visualQa["requiredLineTags"], document.visualQa["registeredLineTags"])
        self.assertEqual(document.visualQa["missingRegisteredLineTags"], 0)

    def test_full_combined_hhw_hrw_emits_connectivity_qa_and_explicit_endpoint_metadata(self):
        pages = [
            self._page(
                "src_hhw_02_p1",
                "src_hhw_02",
                'DEMO-ME-4HHW02 12"-HHWS-CS02 12"-HHWR-CS02 R-HHW-HWB-01 R-HHW-P-01',
            ),
            self._page(
                "src_hrw_01_p1",
                "src_hrw_01",
                'DEMO-ME-4HRW01 24"-HRW-CS02 R-HRW-HX-01 AHU-101 MAU-401',
            ),
        ]

        with patch.dict(os.environ, {"RECREATION_VISIO_TEMPLATE_DIR": "/tmp/recreation-missing-visio-templates"}):
            options = generate_layout_options(
                "project_a",
                pages,
                [],
                [],
                source_paths={
                    "src_hhw_02": "/packages/DEMO-ME-4HHW02_ DEMO - MECHANICAL HEATING HOT WATER SYSTEM P&ID.pdf",
                    "src_hrw_01": "/packages/DEMO-ME-4HRW01_ DEMO - MECHANICAL HEAT RECOVERY DISTRIBUTION P&ID.pdf",
                },
            )
        option, document = next(item for item in options if item[0].name == "Full Combined HHW/HRW")

        connectivity = document.visualQa["connectivity"]
        self.assertGreater(connectivity["connectablePipes"], 0)
        self.assertGreater(connectivity["connectedEndpoints"], 0)
        self.assertGreater(connectivity["nodeToNodePipes"], 0)
        self.assertEqual(connectivity["regionEndpointAttachments"], 0)
        self.assertEqual(option.metrics["connectivityConnectedEndpoints"], connectivity["connectedEndpoints"])

        required_equipment_branches = [
            obj
            for obj in document.objects
            if obj.kind == "pipe" and obj.metadata.get("sourceRequiredEquipment") is True
        ]
        self.assertTrue(required_equipment_branches)
        self.assertTrue(
            any(
                pipe.metadata.get("startObjectId") or pipe.metadata.get("endObjectId")
                for pipe in required_equipment_branches
            )
        )
        self.assertFalse(
            any(
                pipe.metadata.get("startObjectKind") == "region" or pipe.metadata.get("endObjectKind") == "region"
                for pipe in required_equipment_branches
            )
        )

    def test_trace_overlay_maps_source_callout_to_template_target(self):
        pages = [
            self._page(
                "src_chw_01_p1",
                "src_chw_01",
                'DEMO-ME-4CHW01 24"-CHWS-CS01 R-DEMO-CHW-CH-01',
            )
        ]
        candidate = self._candidate("chw_trace", "src_chw_01", "to", '24"-CHWS-CS01', "CHWS", "right")
        candidate.sheetRef = "DEMO-ME-4CHW02"
        candidate.label = '24"-CHWS-CS01 TO DEMO-ME-4CHW02'
        candidate.evidenceText = candidate.label
        template_object = DrawingObject(
            id="visio_pipe_fixture",
            kind="pipe",
            label="",
            points=[{"x": 100.0, "y": 100.0}, {"x": 600.0, "y": 100.0}],
            bounds={"x": 100.0, "y": 96.0, "width": 500.0, "height": 8.0},
            style=DrawingStyle(),
            sourceEvidenceIds=["src_chw_01_p1"],
            metadata={"templateDerived": True},
        )
        template_stats = SimpleNamespace(
            width=1800.0,
            height=1200.0,
            path="/tmp/template.vsdx",
            connectors=1,
            texts=0,
        )

        with patch(
            "recreation_extractor.pid_stitch.layout.load_visio_template_objects",
            return_value=([template_object], template_stats),
        ):
            options = generate_layout_options(
                "project_a",
                pages,
                [candidate],
                [],
                source_paths={"src_chw_01": "/tmp/DEMO-ME-4CHW01.pdf"},
            )

        option, document = next(item for item in options if item[0].name == "Source Trace Overlay")
        trace_objects = [obj for obj in document.objects if obj.metadata.get("traceOverlay") is True]
        self.assertGreaterEqual(len(trace_objects), 4)
        self.assertEqual(option.metrics["sourceTraceObjects"], len(trace_objects))
        self.assertTrue(any(obj.kind == "source_fragment" and obj.metadata.get("sourceCandidateId") == "chw_trace" for obj in trace_objects))
        self.assertTrue(any(obj.metadata.get("traceRole") == "source_to_template" for obj in trace_objects))

    def test_recommended_continuation_labels_stay_inside_sheet(self):
        pages = self._system_pages()
        candidates = [
            self._candidate(f"chw_ref_{index}", "src_chw_02", "to", f'{16 + index * 2}"-CHWS-CS0{index}', "CHWS", "right")
            for index in range(1, 9)
        ]
        for index, candidate in enumerate(candidates, start=1):
            candidate.sheetRef = f"DEMO-ME-4CHW{index + 2:02d}"

        options = generate_layout_options("project_a", pages, candidates, [], source_paths=self._system_source_paths())
        _option, document = next(item for item in options if item[0].name == "Recommended")

        continuation_labels = [
            obj
            for obj in document.objects
            if obj.kind == "label" and obj.id.startswith("overview_label_continuation_label_")
        ]
        self.assertGreaterEqual(len(continuation_labels), 1)
        for label in continuation_labels:
            self.assertGreaterEqual(label.bounds["x"], 0.0)
            self.assertLessEqual(label.bounds["x"] + label.bounds["width"], document.width)
            self.assertGreaterEqual(label.bounds["y"], 0.0)
            self.assertLessEqual(label.bounds["y"] + label.bounds["height"], document.height)

    def test_source_faithful_layout_compacts_source_pages_into_overview_sheet(self):
        pages = [
            PageEvidence(f"src_{index}_p1", f"src_{index}", 1, 3024.0, 2160.0, 270, {"x": 0, "y": 0, "width": 2800, "height": 1900}, [], 50)
            for index in range(6)
        ]

        options = generate_layout_options("project_a", pages, [], [])
        _option, document = next(item for item in options if item[0].name == "Source-faithful")

        fragments = [obj for obj in document.objects if obj.kind == "source_fragment"]
        self.assertEqual(len(fragments), 6)
        self.assertEqual(fragments[0].bounds["width"], pages[0].cropBounds["width"])

    def test_source_fragment_metadata_includes_source_path_when_provided(self):
        pages = [
            PageEvidence("src_a_p1", "src_a", 1, 3024.0, 2160.0, 270, {"x": 0, "y": 0, "width": 2800, "height": 1900}, [], 50)
        ]

        options = generate_layout_options(
            "project_a",
            pages,
            [],
            [],
            source_paths={"src_a": "/tmp/source-a.pdf"},
        )
        _option, document = next(item for item in options if item[0].name == "Source-faithful")

        fragment = next(obj for obj in document.objects if obj.kind == "source_fragment")
        self.assertEqual(fragment.metadata["sourcePath"], "/tmp/source-a.pdf")
        self.assertEqual(fragment.metadata["cropBounds"], pages[0].cropBounds)

    def test_missing_match_endpoint_counts_as_disconnected_and_draws_no_pipe(self):
        pages = [
            PageEvidence("src_a_p1", "src_a", 1, 3024.0, 2160.0, 270, {"x": 0, "y": 0, "width": 2800, "height": 1900}, [], 50)
        ]
        candidates = [self._candidate("a", "src_a", "to", '16"-CHWS-CS02', "CHWS", "right")]
        matches = [ContinuationMatch("m1", "a", "missing", 92.0, ["line tag"], "confirmed")]

        options = generate_layout_options("project_a", pages, candidates, matches)
        _option, document = next(item for item in options if item[0].name == "Source-faithful")

        self.assertFalse(any(obj.kind == "pipe" for obj in document.objects))
        self.assertEqual(document.visualQa["disconnectedContinuations"], 1)

    def test_option_and_drawing_ids_are_project_namespaced_and_deterministic(self):
        pages = [
            PageEvidence("src_a_p1", "src_a", 1, 3024.0, 2160.0, 270, {"x": 0, "y": 0, "width": 2800, "height": 1900}, [], 50)
        ]
        first = generate_layout_options("project_a", pages, [], [])
        second = generate_layout_options("project_b", pages, [], [])
        first_again = generate_layout_options("project_a", pages, [], [])

        self.assertNotEqual(first[0][0].id, second[0][0].id)
        self.assertNotEqual(first[0][1].id, second[0][1].id)
        self.assertEqual(first[0][0].id, first_again[0][0].id)
        self.assertEqual(first[0][1].id, first_again[0][1].id)

    def test_duplicate_candidate_ids_raise_useful_error(self):
        pages = [
            PageEvidence("src_a_p1", "src_a", 1, 3024.0, 2160.0, 270, {"x": 0, "y": 0, "width": 2800, "height": 1900}, [], 50)
        ]
        candidates = [
            self._candidate("duplicate", "src_a", "to", '16"-CHWS-CS02', "CHWS", "right"),
            self._candidate("duplicate", "src_a", "from", '16"-CHWR-CS02', "CHWR", "left"),
        ]

        with self.assertRaisesRegex(ValueError, "Duplicate continuation candidate id: duplicate"):
            generate_layout_options("project_a", pages, candidates, [])

    def test_score_remains_useful_for_many_unresolved_continuations(self):
        pages = [
            PageEvidence("src_a_p1", "src_a", 1, 3024.0, 2160.0, 270, {"x": 0, "y": 0, "width": 2800, "height": 1900}, [], 50)
        ]
        candidates = [
            self._candidate(f"candidate_{index}", "src_a", "to", f"{index}-CHWS-CS02", "CHWS", "right")
            for index in range(14)
        ]

        options = generate_layout_options("project_a", pages, candidates, [])
        option, _document = next(item for item in options if item[0].name == "Recommended")

        self.assertGreater(option.score, 0.0)
        self.assertLess(option.score, 100.0)

    def test_recommended_continuation_stack_filters_title_block_self_references(self):
        pages = [
            PageEvidence("src_a_p1", "src_a", 1, 3024.0, 2160.0, 270, {"x": 0, "y": 0, "width": 2800, "height": 1900}, [], 50)
        ]
        self_ref = self._candidate("self_ref", "src_a", "unknown", "", "", "bottom")
        self_ref.sheetRef = "DEMO-ME-4CDA01"
        self_ref.label = "DEMO-ME-4CDA01"
        self_ref.evidenceText = "DEMO-ME-4CDA01"
        real_ref = self._candidate("real_ref", "src_a", "to", '6"-CDA-SS01', "CDA", "right")
        real_ref.sheetRef = "DEMO-ME-4CDA03"
        real_ref.label = '6"-CDA-SS01 TO CDA DISTRIBUTION DEMO-ME-4CDA03'
        real_ref.evidenceText = real_ref.label

        options = generate_layout_options(
            "project_a",
            pages,
            [self_ref, real_ref],
            [],
            source_paths={"src_a": "/packages/DEMO-ME-4CDA01_ DEMO - MECHANICAL CDA GENERATION P&ID.pdf"},
        )
        _option, document = next(item for item in options if item[0].name == "Recommended")
        continuation_labels = [
            obj.label
            for obj in document.objects
            if obj.kind == "label" and obj.id.startswith("overview_label_continuation_label_")
        ]

        self.assertTrue(any("DEMO-ME-4CDA03" in label for label in continuation_labels))
        self.assertFalse(any("DEMO-ME-4CDA01" in label for label in continuation_labels))
        self.assertFalse(any("TO line" in label for label in continuation_labels))

    def test_recommended_continuation_stack_filters_direction_only_stubs(self):
        pages = [
            PageEvidence("src_a_p1", "src_a", 1, 3024.0, 2160.0, 270, {"x": 0, "y": 0, "width": 2800, "height": 1900}, [], 50)
        ]
        direction_only = self._candidate("direction_only", "src_a", "to", "", "CDA", "right")
        direction_only.label = "TO LOW POINT DRAINS"
        direction_only.evidenceText = direction_only.label
        real_ref = self._candidate("real_ref", "src_a", "to", '6"-CDA-SS01', "CDA", "right")
        real_ref.sheetRef = "DEMO-ME-4CDA03"
        real_ref.label = '6"-CDA-SS01 TO CDA DISTRIBUTION DEMO-ME-4CDA03'
        real_ref.evidenceText = real_ref.label

        options = generate_layout_options(
            "project_a",
            pages,
            [direction_only, real_ref],
            [],
            source_paths={"src_a": "/packages/DEMO-ME-4CDA01_ DEMO - MECHANICAL CDA GENERATION P&ID.pdf"},
        )
        _option, document = next(item for item in options if item[0].name == "Recommended")
        continuation_labels = [
            obj.label
            for obj in document.objects
            if obj.kind == "label" and obj.id.startswith("overview_label_continuation_label_")
        ]

        self.assertEqual(continuation_labels, ['TO 6"-CDA-SS01 / DEMO-ME-4CDA03'])

    def _candidate(self, id, source, direction, line, system, edge):
        return ContinuationCandidate(
            id=id,
            sourceFileId=source,
            page=1,
            sheetRef=None,
            direction=direction,
            label=f"{direction.upper()} {line}",
            lineTag=line,
            system=system,
            edge=edge,
            position={"x": 100.0, "y": 100.0},
            bounds={"x": 100.0, "y": 100.0, "width": 80.0, "height": 18.0},
            confidence=0.9,
            evidenceText=f"{direction.upper()} {line}",
        )

    def _source_driven(self, options):
        return next(item for item in options if item[0].name == "Source-driven Combined P&ID")

    def _bounds_overlap(self, a, b, padding=0.0):
        return not (
            a["x"] + a["width"] + padding < b["x"]
            or b["x"] + b["width"] + padding < a["x"]
            or a["y"] + a["height"] + padding < b["y"]
            or b["y"] + b["height"] + padding < a["y"]
        )

    def _segment_intersects_bounds(self, start, end, bounds):
        if abs(start["y"] - end["y"]) < 0.5:
            y = start["y"]
            min_x = min(start["x"], end["x"])
            max_x = max(start["x"], end["x"])
            return bounds["y"] <= y <= bounds["y"] + bounds["height"] and max_x >= bounds["x"] and min_x <= bounds["x"] + bounds["width"]
        if abs(start["x"] - end["x"]) < 0.5:
            x = start["x"]
            min_y = min(start["y"], end["y"])
            max_y = max(start["y"], end["y"])
            return bounds["x"] <= x <= bounds["x"] + bounds["width"] and max_y >= bounds["y"] and min_y <= bounds["y"] + bounds["height"]
        return False

    def _system_pages(self):
        return [
            self._page(
                "src_cda_01_p1",
                "src_cda_01",
                'DEMO-ME-4CDA01 6"-CDA-SS01 R-DEMO-CDA-C-01 R-DEMO-CDA-C-02 R-DEMO-CDA-AD-01 R-DEMO-CDA-ST-01',
            ),
            self._page(
                "src_cda_02_p1",
                "src_cda_02",
                'DEMO-ME-4CDA02 4"-CDA-SS02 R-DEMO-CDA-AD-02 R-DEMO-CDA-FLTR-01 R-DEMO-CDA-ST-02',
            ),
            self._page(
                "src_chw_01_p1",
                "src_chw_01",
                'DEMO-ME-4CHW01 24"-CHWS-CS01 24"-CHWR-CS01 R-DEMO-CHW-CH-01 R-DEMO-CHW-CH-02 R-DEMO-CHW-P-01',
            ),
            self._page(
                "src_chw_02_p1",
                "src_chw_02",
                'DEMO-ME-4CHW02 18"-CWS-CS01 18"-CWR-CS01 R-DEMO-CHW-P-02 R-DEMO-CHW-P-03 R-DEMO-CW-CT-01',
            ),
            self._page(
                "src_hhw_02_p1",
                "src_hhw_02",
                'DEMO-ME-4HHW02 12"-HHWS-CS01 12"-HHWR-CS01 8"-HRW-CS01 R-DEMO-HHW-HWB-01 R-DEMO-HHW-P-01 R-DEMO-HRW-HX-01',
            ),
        ]

    def _page(self, id, source, text):
        return PageEvidence(
            id,
            source,
            1,
            3024.0,
            2160.0,
            270,
            {"x": 0, "y": 0, "width": 2800, "height": 1900},
            [TextSpan(text, 100.0, 100.0, 900.0, 24.0)],
            50,
        )

    def _system_source_paths(self):
        return {
            "src_cda_01": "/packages/DEMO-ME-4CDA01_ DEMO - MECHANICAL CDA GENERATION P&ID.pdf",
            "src_cda_02": "/packages/DEMO-ME-4CDA02_ DEMO - MECHANICAL CDA DRYERS P&ID.pdf",
            "src_chw_01": "/packages/DEMO-ME-4CHW01_ DEMO - MECHANICAL STANDARD CHILLER P&ID.pdf",
            "src_chw_02": "/packages/DEMO-ME-4CHW02_ DEMO - MECHANICAL CHILLED WATER SYSTEM P&ID.pdf",
            "src_hhw_02": "/packages/DEMO-ME-4HHW02_ DEMO - MECHANICAL HEATING HOT WATER SYSTEM P&ID.pdf",
        }


if __name__ == "__main__":
    unittest.main()
