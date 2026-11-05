import unittest

from recreation_extractor.pid_stitch.electrical_graph import build_electrical_relationship_graph, is_user_facing_equipment_tag
from recreation_extractor.pid_stitch.models import PageEvidence, TextSpan, VectorSegment


class PidElectricalGraphTests(unittest.TestCase):
    def test_selects_electrical_ruleset_from_page_evidence_without_touching_other_disciplines(self):
        process_page = PageEvidence(
            id="src_process_p1",
            sourceFileId="src_process",
            page=1,
            width=1200.0,
            height=800.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 1200.0, "height": 800.0},
            textSpans=[
                TextSpan("PROCESS CONDENSATE", 80.0, 80.0, 180.0, 16.0),
                TextSpan("10-PC-001", 120.0, 180.0, 80.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )
        electrical_page = PageEvidence(
            id="src_uploaded_p1",
            sourceFileId="src_uploaded",
            page=1,
            width=1200.0,
            height=800.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 1200.0, "height": 800.0},
            textSpans=[
                TextSpan("480Y/277V ONE LINE DIAGRAM", 80.0, 64.0, 220.0, 16.0),
                TextSpan("RSMSWG3C25", 80.0, 120.0, 100.0, 16.0),
                TextSpan("5000A 'SWING' BUS", 120.0, 210.0, 160.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph(
            "project_elec",
            [process_page, electrical_page],
            {"src_process": "/uploads/Process.pdf", "src_uploaded": "/uploads/Uploaded.pdf"},
        )

        self.assertEqual(graph.metrics["activeRulesets"], ["electrical_one_line_v1"])
        self.assertEqual(graph.metrics["discipline"], "Electrical")
        self.assertEqual(graph.metrics["pageClassifications"]["one_line"], 1)
        self.assertEqual(len(graph.metrics["pageProfiles"]), 1)
        self.assertTrue(all(node.sourceFileId == "src_uploaded" for node in graph.nodes))
        self.assertTrue(all(node.metadata["discipline"] == "Electrical" for node in graph.nodes))
        self.assertTrue(all(node.metadata["ruleset"] == "electrical_one_line_v1" for node in graph.nodes))

    def test_nests_bus_and_downstream_feeders_under_primary_line_tag(self):
        page = PageEvidence(
            id="src_elec_feeders_p1",
            sourceFileId="src_elec_feeders",
            page=1,
            width=1600.0,
            height=1000.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 1600.0, "height": 1000.0},
            textSpans=[
                TextSpan("480Y/277V ONE LINE DIAGRAM", 80.0, 64.0, 220.0, 16.0),
                TextSpan("RSMSWG3C25", 80.0, 120.0, 100.0, 16.0),
                TextSpan("5000A 'SWING' BUS", 160.0, 230.0, 160.0, 16.0),
                TextSpan("RW4MDP4F21", 860.0, 260.0, 110.0, 16.0),
                TextSpan("RW4SS2F27", 980.0, 390.0, 100.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_feeders": "/uploads/Electrical.pdf"})

        node_by_tag = {node.tag: node for node in graph.nodes}
        primary = node_by_tag["RSMSWG3C25"]
        bus = node_by_tag["5000A 'SWING' BUS"]
        mdp = node_by_tag["RW4MDP4F21"]
        substation = node_by_tag["RW4SS2F27"]
        self.assertTrue(any(edge.kind == "attached_to_line" and edge.sourceId == bus.id and edge.targetId == primary.id and edge.metadata["source"] == "electrical_bus_under_primary" for edge in graph.edges))
        self.assertTrue(any(edge.kind == "attached_to_line" and edge.sourceId == mdp.id and edge.targetId == bus.id and edge.metadata["source"] == "electrical_feeder_under_bus" for edge in graph.edges))
        self.assertTrue(any(edge.kind == "attached_to_line" and edge.sourceId == substation.id and edge.targetId == bus.id and edge.metadata["source"] == "electrical_feeder_under_bus" for edge in graph.edges))

    def test_detects_switchgear_breaker_cells_outside_bottom_half_layouts(self):
        page = PageEvidence(
            id="src_elec_upper_breaker_p1",
            sourceFileId="src_elec_upper_breaker",
            page=1,
            width=1600.0,
            height=1000.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 1600.0, "height": 1000.0},
            textSpans=[
                TextSpan("RW4SWG2F6", 700.0, 72.0, 100.0, 16.0),
                TextSpan("SW C", 140.0, 250.0, 36.0, 16.0),
                TextSpan("(SECTION 7)", 124.0, 266.0, 78.0, 16.0),
                TextSpan("TRANSFORMER", 260.0, 258.0, 98.0, 16.0),
                TextSpan("MAIN", 430.0, 318.0, 36.0, 16.0),
                TextSpan("BREAKER", 418.0, 334.0, 64.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_upper_breaker": "/uploads/Electrical.pdf"})

        node_by_tag = {node.tag: node for node in graph.nodes}
        self.assertIn("MAIN BREAKER", node_by_tag)
        self.assertTrue(any(edge.kind == "device_on_equipment" and edge.sourceId == node_by_tag["MAIN BREAKER"].id for edge in graph.edges))

    def test_builds_switchgear_tree_from_to_see_drawing_references(self):
        page = PageEvidence(
            id="src_elec_p1",
            sourceFileId="src_elec",
            page=1,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("RSMSWG3C25", 100.0, 100.0, 120.0, 16.0),
                TextSpan("5000A 'SWING' BUS", 120.0, 220.0, 200.0, 16.0),
                TextSpan("TO", 2400.0, 300.0, 30.0, 16.0),
                TextSpan("RW4MDP3C25", 2440.0, 300.0, 120.0, 16.0),
                TextSpan("SEE DRAWING", 2440.0, 322.0, 120.0, 16.0),
                TextSpan("DEMO-EE-4112", 2440.0, 344.0, 120.0, 16.0),
                TextSpan("AA 3000kVA", 420.0, 540.0, 120.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec": "/packages/Electrical Package.pdf"})

        node_by_tag = {node.tag: node for node in graph.nodes}
        self.assertIn("RSMSWG3C25", node_by_tag)
        self.assertIn("TO RW4MDP3C25 / DEMO-EE-4112", node_by_tag)
        self.assertIn("AA 3000KVA", node_by_tag)
        continuation = node_by_tag["TO RW4MDP3C25 / DEMO-EE-4112"]
        root = node_by_tag["RSMSWG3C25"]
        bus = node_by_tag["5000A 'SWING' BUS"]
        transformer = node_by_tag["AA 3000KVA"]
        self.assertTrue(any(edge.kind == "continuation_on_line" and edge.sourceId == continuation.id and edge.targetId == root.id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "attached_to_line" and edge.sourceId == transformer.id and edge.targetId in {root.id, bus.id} for edge in graph.edges))
        self.assertEqual(graph.metrics["lineTagNodes"], 2)
        self.assertEqual(graph.metrics["continuationNodes"], 1)

    def test_switchgear_oneline_uses_incoming_refs_owner_tags_and_bottom_arrow_targets_only(self):
        page = PageEvidence(
            id="src_elec_181_p1",
            sourceFileId="src_elec_181",
            page=181,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("ONELINE DIAGRAM", 1300.0, 80.0, 160.0, 16.0),
                TextSpan("FROM", 360.0, 92.0, 38.0, 14.0),
                TextSpan("RSMSWG3C25", 334.0, 106.0, 90.0, 14.0),
                TextSpan("SEE DRAWING", 334.0, 120.0, 90.0, 14.0),
                TextSpan("DEMO-EE-4001", 340.0, 135.0, 80.0, 14.0),
                TextSpan("FROM", 2234.0, 92.0, 38.0, 14.0),
                TextSpan("RSMSWG3C25", 2208.0, 106.0, 90.0, 14.0),
                TextSpan("SEE DRAWING", 2208.0, 120.0, 90.0, 14.0),
                TextSpan("DEMO-EE-4001", 2213.0, 135.0, 80.0, 14.0),
                TextSpan("RSMLSS3B27", 90.0, 228.0, 124.0, 18.0),
                TextSpan("(OFCI)", 90.0, 249.0, 58.0, 18.0),
                TextSpan("RSMLSS3D27", 2418.0, 228.0, 124.0, 18.0),
                TextSpan("(OFCI)", 2483.0, 249.0, 58.0, 18.0),
                TextSpan("SW A", 143.0, 1500.0, 34.0, 14.0),
                TextSpan("SW B", 2339.0, 1500.0, 34.0, 14.0),
                TextSpan("TO", 389.0, 1394.0, 18.0, 14.0),
                TextSpan("R-CHW-CH-05 (LH)", 342.0, 1408.0, 112.0, 14.0),
                TextSpan("TO", 515.0, 1394.0, 18.0, 14.0),
                TextSpan("R-CHW-CH-05 (RH)", 467.0, 1408.0, 114.0, 14.0),
                TextSpan("TO", 641.0, 1397.0, 18.0, 14.0),
                TextSpan("R-CHW-CH-03 (LH)", 594.0, 1411.0, 112.0, 14.0),
                TextSpan("TO", 767.0, 1397.0, 18.0, 14.0),
                TextSpan("R-CHW-CH-03 (RH)", 719.0, 1411.0, 114.0, 14.0),
                TextSpan("TO", 893.0, 1397.0, 18.0, 14.0),
                TextSpan("R-CHW-CH-01 (LH)", 846.0, 1411.0, 112.0, 14.0),
                TextSpan("TO", 1019.0, 1397.0, 18.0, 14.0),
                TextSpan("R-CHW-CH-01 (RH)", 971.0, 1411.0, 114.0, 14.0),
                TextSpan("TO", 1559.0, 1397.0, 18.0, 14.0),
                TextSpan("R-CHW-CH-02 (LH)", 1512.0, 1411.0, 112.0, 14.0),
                TextSpan("TO", 1685.0, 1397.0, 18.0, 14.0),
                TextSpan("R-CHW-CH-02 (RH)", 1637.0, 1411.0, 114.0, 14.0),
                TextSpan("TO", 1811.0, 1397.0, 18.0, 14.0),
                TextSpan("R-CHW-CH-04 (LH)", 1764.0, 1411.0, 112.0, 14.0),
                TextSpan("TO", 1937.0, 1397.0, 18.0, 14.0),
                TextSpan("R-CHW-CH-04 (RH)", 1889.0, 1411.0, 114.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_181": "/uploads/Electrical Package.pdf"})

        tags = [node.tag for node in graph.nodes]
        self.assertNotIn("DEMO-EE-4001", tags)
        self.assertEqual(tags.count("RSMSWG3C25"), 1)
        self.assertIn("RSMLSS3B27", tags)
        self.assertIn("RSMLSS3D27", tags)
        self.assertNotIn("RSMLSS3B27 (OFCI)", tags)
        self.assertNotIn("SW A", tags)
        self.assertNotIn("BREAKER", tags)

        nodes_by_tag = {}
        for node in graph.nodes:
            nodes_by_tag.setdefault(node.tag, []).append(node)
        incoming_ref = nodes_by_tag["RSMSWG3C25"][0]
        self.assertEqual(incoming_ref.metadata.get("sheetRef"), "DEMO-EE-4001")
        left_owner = nodes_by_tag["RSMLSS3B27"][0]
        right_owner = nodes_by_tag["RSMLSS3D27"][0]
        owner_parent_edges = [
            edge
            for edge in graph.edges
            if edge.targetId == incoming_ref.id and edge.metadata.get("source") == "incoming_reference_feeds_switchgear_owner"
        ]
        self.assertEqual({edge.sourceId for edge in owner_parent_edges}, {left_owner.id, right_owner.id})
        left_children = [
            next(node for node in graph.nodes if node.id == edge.sourceId).tag
            for edge in graph.edges
            if edge.targetId == left_owner.id and edge.metadata.get("source") == "bottom_arrow_target_under_switchgear_owner"
        ]
        right_children = [
            next(node for node in graph.nodes if node.id == edge.sourceId).tag
            for edge in graph.edges
            if edge.targetId == right_owner.id and edge.metadata.get("source") == "bottom_arrow_target_under_switchgear_owner"
        ]
        self.assertEqual(left_children, ["R-CHW-CH-05 (LH)", "R-CHW-CH-05 (RH)", "R-CHW-CH-03 (LH)", "R-CHW-CH-03 (RH)", "R-CHW-CH-01 (LH)", "R-CHW-CH-01 (RH)"])
        self.assertEqual(right_children, ["R-CHW-CH-02 (LH)", "R-CHW-CH-02 (RH)", "R-CHW-CH-04 (LH)", "R-CHW-CH-04 (RH)"])
        self.assertEqual(len(graph.nodes), 13)

    def test_combined_oneline_merges_matching_sheet_references_across_pages(self):
        page_one = PageEvidence(
            id="src_elec_181_p1",
            sourceFileId="src_elec_181",
            page=181,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("FROM", 360.0, 92.0, 38.0, 14.0),
                TextSpan("RSMSWG3C25", 334.0, 106.0, 90.0, 14.0),
                TextSpan("SEE DRAWING", 334.0, 120.0, 90.0, 14.0),
                TextSpan("DEMO-EE-4001", 340.0, 135.0, 80.0, 14.0),
                TextSpan("RSMLSS3B27", 90.0, 228.0, 124.0, 18.0),
                TextSpan("(OFCI)", 90.0, 249.0, 58.0, 18.0),
                TextSpan("TO", 389.0, 1394.0, 18.0, 14.0),
                TextSpan("R-CHW-CH-05 (LH)", 342.0, 1408.0, 112.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )
        page_two = PageEvidence(
            id="src_elec_185_p1",
            sourceFileId="src_elec_181",
            page=185,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("FROM", 360.0, 92.0, 38.0, 14.0),
                TextSpan("RSMSWG3C25", 334.0, 106.0, 90.0, 14.0),
                TextSpan("SEE DRAWING", 334.0, 120.0, 90.0, 14.0),
                TextSpan("DEMO-EE-4001", 340.0, 135.0, 80.0, 14.0),
                TextSpan("RS4SS2D6", 90.0, 228.0, 124.0, 18.0),
                TextSpan("(OFCI)", 90.0, 249.0, 58.0, 18.0),
                TextSpan("TO", 389.0, 1394.0, 18.0, 14.0),
                TextSpan("RS4MDP1F12", 342.0, 1408.0, 112.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page_one, page_two], {"src_elec_181": "/uploads/Electrical Package.pdf"})

        nodes_by_tag = {}
        for node in graph.nodes:
            nodes_by_tag.setdefault(node.tag, []).append(node)
        self.assertNotIn("DEMO-EE-4001", nodes_by_tag)
        self.assertEqual(len(nodes_by_tag["RSMSWG3C25"]), 1)
        incoming_ref = nodes_by_tag["RSMSWG3C25"][0]
        self.assertEqual(incoming_ref.metadata.get("sheetRef"), "DEMO-EE-4001")
        children = {
            next(node for node in graph.nodes if node.id == edge.sourceId).tag
            for edge in graph.edges
            if edge.targetId == incoming_ref.id and edge.metadata.get("source") == "incoming_reference_feeds_switchgear_owner"
        }
        self.assertEqual(children, {"RSMLSS3B27", "RS4SS2D6"})

    def test_combined_oneline_absorbs_from_reference_into_loaded_upstream_tag(self):
        upstream_page = PageEvidence(
            id="src_elec_179_p1",
            sourceFileId="src_elec_179",
            page=179,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("RSMSWG3C25", 420.0, 200.0, 90.0, 14.0),
                TextSpan("5000A 'SWING' BUS", 520.0, 420.0, 160.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )
        downstream_page = PageEvidence(
            id="src_elec_181_p1",
            sourceFileId="src_elec_179",
            page=181,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("FROM", 360.0, 92.0, 38.0, 14.0),
                TextSpan("RSMSWG3C25", 334.0, 106.0, 90.0, 14.0),
                TextSpan("SEE DRAWING", 334.0, 120.0, 90.0, 14.0),
                TextSpan("DEMO-EE-4001", 340.0, 135.0, 80.0, 14.0),
                TextSpan("RSMLSS3B27", 90.0, 228.0, 124.0, 18.0),
                TextSpan("(OFCI)", 90.0, 249.0, 58.0, 18.0),
                TextSpan("TO", 389.0, 1394.0, 18.0, 14.0),
                TextSpan("R-CHW-CH-05 (LH)", 342.0, 1408.0, 112.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [upstream_page, downstream_page], {"src_elec_179": "/uploads/Electrical Package.pdf"})

        nodes_by_tag = {}
        for node in graph.nodes:
            nodes_by_tag.setdefault(node.tag, []).append(node)
        self.assertNotIn("DEMO-EE-4001", nodes_by_tag)
        self.assertEqual(len(nodes_by_tag["RSMSWG3C25"]), 1)
        upstream = nodes_by_tag["RSMSWG3C25"][0]
        owner = nodes_by_tag["RSMLSS3B27"][0]
        self.assertTrue(
            any(
                edge.sourceId == owner.id
                and edge.targetId == upstream.id
                and edge.metadata.get("source") == "incoming_reference_feeds_switchgear_owner"
                for edge in graph.edges
            )
        )

    def test_generator_sheet_keeps_component_feed_as_source_evidence_not_generator_parent(self):
        page = PageEvidence(
            id="src_elec_180_p1",
            sourceFileId="src_elec_180",
            page=180,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("GEN-15", 1140.0, 430.0, 68.0, 18.0),
                TextSpan("FROM", 908.0, 604.0, 40.0, 14.0),
                TextSpan("RW4MDP4C6", 884.0, 620.0, 92.0, 14.0),
                TextSpan("SEE DRAWING", 884.0, 638.0, 94.0, 14.0),
                TextSpan("DEMO-EE-4114", 887.0, 656.0, 88.0, 14.0),
                TextSpan("GEN-15_PNL", 1144.0, 744.0, 90.0, 16.0),
                TextSpan("CABLE BUS", 1320.0, 940.0, 90.0, 16.0),
                TextSpan("RW4SWG2F6", 842.0, 996.0, 104.0, 18.0),
                TextSpan("(OFCI)", 844.0, 1018.0, 56.0, 18.0),
                TextSpan("TO", 990.0, 1348.0, 20.0, 14.0),
                TextSpan("RW4SS3F25 & D25", 936.0, 1364.0, 132.0, 14.0),
                TextSpan("SEE DRAWING", 936.0, 1380.0, 94.0, 14.0),
                TextSpan("DEMO-EE-4004", 936.0, 1396.0, 88.0, 14.0),
                TextSpan("TO", 1184.0, 1348.0, 20.0, 14.0),
                TextSpan("RW4SS3D26 & F26", 1130.0, 1364.0, 132.0, 14.0),
                TextSpan("SEE DRAWING", 1130.0, 1380.0, 94.0, 14.0),
                TextSpan("DEMO-EE-4005", 1130.0, 1396.0, 88.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_180": "/packages/Electrical Package.pdf"})

        nodes_by_tag = {}
        for node in graph.nodes:
            nodes_by_tag.setdefault(node.tag, []).append(node)
        self.assertNotIn("DEMO-EE-4114", nodes_by_tag)
        self.assertIn("RW4MDP4C6", nodes_by_tag)
        self.assertIn("GEN-15", nodes_by_tag)
        self.assertIn("RW4SWG2F6", nodes_by_tag)
        upstream = nodes_by_tag["RW4MDP4C6"][0]
        generator = nodes_by_tag["GEN-15"][0]
        switchgear = nodes_by_tag["RW4SWG2F6"][0]
        self.assertTrue(any(edge.kind == "power_source" and edge.sourceId == generator.id and edge.targetId == upstream.id and edge.metadata.get("source") == "incoming_reference_feeds_generator_component" for edge in graph.edges))
        self.assertFalse(any(edge.kind == "attached_to_line" and edge.sourceId == generator.id and edge.targetId == upstream.id for edge in graph.edges))
        self.assertTrue(any(edge.sourceId == switchgear.id and edge.targetId == generator.id and edge.metadata.get("source") == "generator_feeds_switchgear_owner" for edge in graph.edges))
        self.assertTrue(
            any(
                next(node for node in graph.nodes if node.id == edge.sourceId).tag == "RW4SS3F25 & D25"
                and edge.targetId == switchgear.id
                and edge.metadata.get("source") == "bottom_arrow_target_under_switchgear_owner"
                for edge in graph.edges
            )
        )

    def test_overall_oneline_scaffolds_hv_yard_mv_switchgear_and_eps_roots(self):
        page = PageEvidence(
            id="src_elec_178_p1",
            sourceFileId="src_elec_178",
            page=178,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("OVERALL ONELINE DIAGRAM", 2450.0, 2020.0, 260.0, 18.0),
                TextSpan("FROM", 90.0, 120.0, 36.0, 14.0),
                TextSpan("HV YARD SWG", 90.0, 140.0, 92.0, 14.0),
                TextSpan("SEE DRAWING", 90.0, 160.0, 92.0, 14.0),
                TextSpan("U-E-202", 90.0, 180.0, 76.0, 14.0),
                TextSpan("RSMSWG3C25", 120.0, 280.0, 106.0, 18.0),
                TextSpan("MV SWITCHGEAR (13.8kV)", 120.0, 304.0, 180.0, 14.0),
                TextSpan("GEN-15", 2440.0, 280.0, 68.0, 18.0),
                TextSpan("RW4SWG2F6", 2220.0, 500.0, 104.0, 18.0),
                TextSpan("EPS SWITCHGEAR (480V)", 2220.0, 524.0, 170.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_178": "/packages/Electrical Package.pdf"})

        nodes_by_tag = {node.tag: node for node in graph.nodes}
        self.assertIn("HV YARD SWG", nodes_by_tag)
        self.assertIn("RSMSWG3C25", nodes_by_tag)
        self.assertIn("GEN-15", nodes_by_tag)
        self.assertIn("RW4SWG2F6", nodes_by_tag)
        hv_yard = nodes_by_tag["HV YARD SWG"]
        mv_switchgear = nodes_by_tag["RSMSWG3C25"]
        generator = nodes_by_tag["GEN-15"]
        eps_switchgear = nodes_by_tag["RW4SWG2F6"]
        self.assertEqual(hv_yard.metadata.get("sheetRef"), "U-E-202")
        self.assertTrue(any(edge.kind == "attached_to_line" and edge.sourceId == mv_switchgear.id and edge.targetId == hv_yard.id and edge.metadata.get("source") == "overall_oneline_hv_yard_feed" for edge in graph.edges))
        self.assertTrue(any(edge.kind == "attached_to_line" and edge.sourceId == eps_switchgear.id and edge.targetId == generator.id and edge.metadata.get("source") == "overall_oneline_generator_feed" for edge in graph.edges))
        self.assertFalse(any(edge.kind == "attached_to_line" and edge.sourceId == generator.id and edge.targetId == mv_switchgear.id for edge in graph.edges))
        self.assertFalse(any(edge.kind == "attached_to_line" and edge.sourceId == eps_switchgear.id and edge.targetId == mv_switchgear.id for edge in graph.edges))

    def test_panel_schedule_nests_designation_under_supply_from_and_circuits_under_panel(self):
        page = PageEvidence(
            id="src_elec_164_p1",
            sourceFileId="src_elec_164",
            page=164,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("PANEL SCHEDULES", 2460.0, 2020.0, 180.0, 18.0),
                TextSpan("DESIGNATION:", 120.0, 120.0, 100.0, 14.0),
                TextSpan("RS2PP1B4", 232.0, 120.0, 92.0, 14.0),
                TextSpan("SUPPLY FROM:", 120.0, 144.0, 100.0, 14.0),
                TextSpan("RS4MDP4D5 VIA RSTT1B4", 232.0, 144.0, 190.0, 14.0),
                TextSpan("CKT", 120.0, 190.0, 32.0, 14.0),
                TextSpan("EQUIPMENT DESCRIPTION", 184.0, 190.0, 180.0, 14.0),
                TextSpan("1", 126.0, 220.0, 14.0, 14.0),
                TextSpan("RECP SUBFAB 204 COL B3", 184.0, 220.0, 190.0, 14.0),
                TextSpan("2", 126.0, 244.0, 14.0, 14.0),
                TextSpan("SPARE", 184.0, 244.0, 52.0, 14.0),
                TextSpan("3", 126.0, 268.0, 14.0, 14.0),
                TextSpan("LIGHTING CONTROL PANEL LCP-2", 184.0, 268.0, 220.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_164": "/packages/Electrical Package.pdf"})

        nodes_by_tag = {node.tag: node for node in graph.nodes}
        self.assertIn("RS4MDP4D5", nodes_by_tag)
        self.assertIn("RSTT1B4", nodes_by_tag)
        self.assertIn("RS2PP1B4", nodes_by_tag)
        self.assertIn("RS2PP1B4 CKT 1", nodes_by_tag)
        self.assertIn("RS2PP1B4 CKT 3", nodes_by_tag)
        self.assertNotIn("RS2PP1B4 CKT 2", nodes_by_tag)
        supply = nodes_by_tag["RS4MDP4D5"]
        transformer = nodes_by_tag["RSTT1B4"]
        designation = nodes_by_tag["RS2PP1B4"]
        circuit_one = nodes_by_tag["RS2PP1B4 CKT 1"]
        circuit_three = nodes_by_tag["RS2PP1B4 CKT 3"]
        self.assertTrue(any(edge.kind == "panel_schedule_feeds" and edge.sourceId == transformer.id and edge.targetId == supply.id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "panel_schedule_feeds" and edge.sourceId == designation.id and edge.targetId == transformer.id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "panel_circuit" and edge.sourceId == circuit_one.id and edge.targetId == designation.id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "panel_circuit" and edge.sourceId == circuit_three.id and edge.targetId == designation.id for edge in graph.edges))
        self.assertEqual(circuit_one.kind, "circuit")
        self.assertEqual(circuit_one.metadata["circuitNumber"], "1")
        self.assertEqual(circuit_one.metadata["equipmentDescription"], "RECP SUBFAB 204 COL B3")

    def test_panel_schedule_does_not_parent_generator_designation_under_supply_from(self):
        page = PageEvidence(
            id="src_elec_164_gen_p1",
            sourceFileId="src_elec_164_gen",
            page=164,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("PANEL SCHEDULE", 1200.0, 80.0, 180.0, 16.0),
                TextSpan("DESIGNATION:", 120.0, 120.0, 100.0, 14.0),
                TextSpan("GEN-15", 232.0, 120.0, 68.0, 14.0),
                TextSpan("SUPPLY FROM:", 120.0, 144.0, 100.0, 14.0),
                TextSpan("RW4MDP4C6", 232.0, 144.0, 92.0, 14.0),
                TextSpan("CKT", 120.0, 190.0, 32.0, 14.0),
                TextSpan("EQUIPMENT DESCRIPTION", 184.0, 190.0, 180.0, 14.0),
                TextSpan("1", 126.0, 220.0, 14.0, 14.0),
                TextSpan("GENERATOR ACCESSORY PANEL", 184.0, 220.0, 200.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_164_gen": "/packages/Electrical Package.pdf"})

        nodes_by_tag = {node.tag: node for node in graph.nodes}
        upstream = nodes_by_tag["RW4MDP4C6"]
        generator = nodes_by_tag["GEN-15"]
        circuit = nodes_by_tag["GEN-15 CKT 1"]
        self.assertFalse(
            any(
                edge.kind == "panel_schedule_feeds"
                and edge.sourceId == generator.id
                and edge.targetId == upstream.id
                for edge in graph.edges
            )
        )
        self.assertTrue(any(edge.kind == "panel_circuit" and edge.sourceId == circuit.id and edge.targetId == generator.id for edge in graph.edges))

    def test_user_facing_equipment_filter_omits_ratings_and_keeps_equipment_tags(self):
        kept = {"HV YARD SWG", "RW4MDP4C6", "GEN-15", "RW4SWG2F6", "R-CHW-CH-05 (LH)", "RW4SS3F25 & D25", "VFD-CH-01", "PANEL-A"}
        omitted = {"480Y/277V", "13.8KV-4160V", "5000A 'SWING' BUS", "5000AF", "52", "M1", "AA 3000KVA", "TRAYS", "TRENCH", "TRAILER", "PANELS", "VFDS", "PANELBOARD", "REFRIGERATOR"}

        self.assertTrue(all(is_user_facing_equipment_tag(tag) for tag in kept))
        self.assertFalse(any(is_user_facing_equipment_tag(tag) for tag in omitted))

    def test_uses_front_matter_legend_as_electrical_document_guide_without_extracting_noise(self):
        guide_page = PageEvidence(
            id="src_elec_p1",
            sourceFileId="src_elec",
            page=1,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("ABBREVIATIONS", 120.0, 80.0, 120.0, 16.0),
                TextSpan("MDP MAIN DISTRIBUTION PANEL", 120.0, 132.0, 210.0, 16.0),
                TextSpan("SWG SWITCHGEAR", 120.0, 154.0, 120.0, 16.0),
                TextSpan("OFCI OWNER FURNISHED CONTRACTOR INSTALLED", 120.0, 176.0, 310.0, 16.0),
                TextSpan("EQUIPMENT TAGGING LEGEND", 1180.0, 560.0, 240.0, 16.0),
                TextSpan("BUILDING POWER SYSTEM VOLTAGE COMPONENT LEVEL GRID LOCATION", 1180.0, 594.0, 520.0, 16.0),
                TextSpan("POWER ONE-LINE LEGEND", 2140.0, 1120.0, 240.0, 16.0),
                TextSpan("52 AC CIRCUIT BREAKER", 2140.0, 1170.0, 170.0, 16.0),
                TextSpan("87 DIFFERENTIAL RELAY", 2140.0, 1192.0, 170.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )
        one_line_page = PageEvidence(
            id="src_elec_p180",
            sourceFileId="src_elec",
            page=180,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("GEN-15", 1140.0, 430.0, 68.0, 18.0),
                TextSpan("FROM", 908.0, 604.0, 40.0, 14.0),
                TextSpan("RW4MDP4C6", 884.0, 620.0, 92.0, 14.0),
                TextSpan("SEE DRAWING", 884.0, 638.0, 94.0, 14.0),
                TextSpan("DEMO-EE-4114", 887.0, 656.0, 88.0, 14.0),
                TextSpan("RW4SWG2F6", 842.0, 996.0, 104.0, 18.0),
                TextSpan("(OFCI)", 844.0, 1018.0, 56.0, 18.0),
                TextSpan("TO", 990.0, 1348.0, 20.0, 14.0),
                TextSpan("RW4SS3F25 & D25", 936.0, 1364.0, 132.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [guide_page, one_line_page], {"src_elec": "/packages/Electrical Package.pdf"})

        self.assertEqual(graph.metrics["pageClassifications"]["guide"], 1)
        guide = graph.metrics["documentGuide"]
        self.assertEqual(guide["sourcePageIds"], ["src_elec_p1"])
        self.assertEqual(guide["abbreviations"]["MDP"], "MAIN DISTRIBUTION PANEL")
        self.assertEqual(guide["abbreviations"]["SWG"], "SWITCHGEAR")
        self.assertIn("GRID LOCATION", guide["equipmentTagSchema"])
        tags = [node.tag for node in graph.nodes]
        self.assertIn("RW4MDP4C6", tags)
        self.assertIn("GEN-15", tags)
        self.assertNotIn("52", tags)
        self.assertNotIn("87", tags)

    def test_one_line_and_panel_schedule_pages_contribute_to_hierarchy_in_full_file_runs(self):
        one_line_page = PageEvidence(
            id="src_elec_p180",
            sourceFileId="src_elec",
            page=180,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("ONE-LINE DIAGRAM", 1200.0, 80.0, 180.0, 16.0),
                TextSpan("RW4SWG2F6", 842.0, 996.0, 104.0, 18.0),
                TextSpan("RW4MDP4C6", 884.0, 1160.0, 92.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )
        riser_page = PageEvidence(
            id="src_elec_p40",
            sourceFileId="src_elec",
            page=40,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("FEEDER RISER DIAGRAM", 1200.0, 80.0, 220.0, 16.0),
                TextSpan("RW4MDP4F21", 884.0, 620.0, 92.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )
        control_page = PageEvidence(
            id="src_elec_p160",
            sourceFileId="src_elec",
            page=160,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("CONTROL SCHEMATIC", 1200.0, 80.0, 180.0, 16.0),
                TextSpan("RS4MDP1F12", 884.0, 620.0, 92.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )
        schedule_page = PageEvidence(
            id="src_elec_p65",
            sourceFileId="src_elec",
            page=65,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("PANEL SCHEDULE", 1200.0, 80.0, 180.0, 16.0),
                TextSpan("DESIGNATION:", 120.0, 120.0, 100.0, 14.0),
                TextSpan("RS4PPB10", 232.0, 120.0, 92.0, 14.0),
                TextSpan("SUPPLY FROM:", 120.0, 144.0, 100.0, 14.0),
                TextSpan("RW4SWG2F6", 232.0, 144.0, 92.0, 14.0),
                TextSpan("CKT", 120.0, 190.0, 32.0, 14.0),
                TextSpan("EQUIPMENT DESCRIPTION", 184.0, 190.0, 180.0, 14.0),
                TextSpan("1", 126.0, 220.0, 14.0, 14.0),
                TextSpan("RECP CLEANROOM 101", 184.0, 220.0, 170.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )
        power_plan_page = PageEvidence(
            id="src_elec_p2",
            sourceFileId="src_elec",
            page=2,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("DEMO - ELECTRICAL", 2752.0, 2029.0, 172.0, 18.0),
                TextSpan("POWER PLAN", 2775.0, 2071.0, 127.0, 18.0),
                TextSpan("RW4MDP4F21", 884.0, 620.0, 92.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )
        feeder_schedule_page = PageEvidence(
            id="src_elec_p160",
            sourceFileId="src_elec",
            page=160,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("DEMO - ELECTRICAL", 2752.0, 2029.0, 172.0, 18.0),
                TextSpan("FEEDER", 2780.0, 2050.0, 80.0, 18.0),
                TextSpan("SCHEDULES", 2781.0, 2071.0, 115.0, 18.0),
                TextSpan("RS4MDP1F12", 884.0, 620.0, 92.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph(
            "project_elec",
            [one_line_page, riser_page, control_page, schedule_page, power_plan_page, feeder_schedule_page],
            {"src_elec": "/packages/Electrical Package.pdf"},
        )

        self.assertEqual(graph.metrics["pageClassifications"]["one_line"], 1)
        self.assertEqual(graph.metrics["pageClassifications"]["riser"], 1)
        self.assertEqual(graph.metrics["pageClassifications"]["control_schematic"], 1)
        self.assertEqual(graph.metrics["pageClassifications"]["panel_schedule"], 2)
        self.assertEqual(graph.metrics["pageClassifications"]["power_plan"], 1)
        tags = {node.tag for node in graph.nodes}
        self.assertIn("RW4SWG2F6", tags)
        self.assertIn("RW4MDP4C6", tags)
        self.assertIn("RS4PPB10", tags)
        self.assertIn("RS4PPB10 CKT 1", tags)
        self.assertNotIn("RW4MDP4F21", tags)
        self.assertNotIn("RS4MDP1F12", tags)
        self.assertEqual({node.page for node in graph.nodes}, {65, 180})

    def test_document_guide_profiles_component_tags_and_marks_incomplete_aliases(self):
        guide_page = PageEvidence(
            id="src_elec_p1",
            sourceFileId="src_elec",
            page=1,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("ABBREVIATIONS", 120.0, 80.0, 120.0, 16.0),
                TextSpan("ATS", 56.0, 132.0, 18.0, 16.0),
                TextSpan("AUTOMATIC TRANSFER SWITCH", 100.0, 132.0, 210.0, 16.0),
                TextSpan("VFD", 556.0, 132.0, 20.0, 16.0),
                TextSpan("VARIABLE FREQUENCY DRIVE", 600.0, 132.0, 210.0, 16.0),
                TextSpan("MDP", 56.0, 154.0, 20.0, 16.0),
                TextSpan("MAIN DISTRIBUTION PANEL", 100.0, 154.0, 210.0, 16.0),
                TextSpan("PC", 556.0, 154.0, 20.0, 16.0),
                TextSpan("PHOTOCELL", 600.0, 154.0, 80.0, 16.0),
                TextSpan("SS", 56.0, 176.0, 14.0, 16.0),
                TextSpan("SUBSTATION", 100.0, 176.0, 120.0, 16.0),
                TextSpan("SWG", 56.0, 198.0, 22.0, 16.0),
                TextSpan("SWITCHGEAR", 100.0, 198.0, 120.0, 16.0),
                TextSpan("SS", 56.0, 220.0, 14.0, 16.0),
                TextSpan("_", 100.0, 220.0, 20.0, 16.0),
                TextSpan("EQUIPMENT TAGGING LEGEND", 1180.0, 560.0, 240.0, 16.0),
                TextSpan("BUILDING POWER SYSTEM VOLTAGE COMPONENT LEVEL GRID LOCATION", 1180.0, 594.0, 520.0, 16.0),
                TextSpan("POWER ONE-LINE LEGEND", 2140.0, 1120.0, 240.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )
        one_line_page = PageEvidence(
            id="src_elec_p180",
            sourceFileId="src_elec",
            page=180,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("RW4SWG2F6", 842.0, 996.0, 104.0, 18.0),
                TextSpan("RW4MDP4C6", 884.0, 1160.0, 92.0, 14.0),
                TextSpan("RW4MDP4F", 1020.0, 1160.0, 82.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [guide_page, one_line_page], {"src_elec": "/packages/Electrical Package.pdf"})

        profile = graph.metrics["documentProfile"]
        self.assertEqual(profile["equipmentComponentCodes"]["MDP"], "MAIN DISTRIBUTION PANEL")
        self.assertEqual(profile["equipmentComponentCodes"]["SS"], "SUBSTATION")
        self.assertEqual(profile["equipmentComponentCodes"]["SWG"], "SWITCHGEAR")
        self.assertEqual(profile["equipmentComponentCodes"]["ATS"], "AUTOMATIC TRANSFER SWITCH")
        self.assertNotIn("PHOTOCELL", profile["equipmentComponentCodes"]["MDP"])
        nodes_by_tag = {node.tag: node for node in graph.nodes}
        mdp_profile = nodes_by_tag["RW4MDP4C6"].metadata["tagProfile"]
        self.assertEqual(mdp_profile["componentCode"], "MDP")
        self.assertEqual(mdp_profile["componentDescription"], "MAIN DISTRIBUTION PANEL")
        self.assertEqual(mdp_profile["level"], "4")
        self.assertEqual(mdp_profile["gridLocation"], "C6")
        self.assertTrue(mdp_profile["complete"])
        partial_profile = nodes_by_tag["RW4MDP4F"].metadata["tagProfile"]
        self.assertFalse(partial_profile["complete"])
        self.assertEqual(partial_profile["missingFields"], ["gridLocation"])
        self.assertTrue(nodes_by_tag["RW4MDP4F"].metadata["suppressInEquipmentFlow"])

    def test_merges_cross_page_duplicate_equipment_targets_into_one_hierarchy_branch(self):
        upstream_page = PageEvidence(
            id="src_elec_p180",
            sourceFileId="src_elec",
            page=180,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("GEN-15", 1140.0, 430.0, 68.0, 18.0),
                TextSpan("FROM", 908.0, 604.0, 40.0, 14.0),
                TextSpan("RW4MDP4C6", 884.0, 620.0, 92.0, 14.0),
                TextSpan("SEE DRAWING", 884.0, 638.0, 94.0, 14.0),
                TextSpan("DEMO-EE-4114", 887.0, 656.0, 88.0, 14.0),
                TextSpan("RW4SWG2F6", 842.0, 996.0, 104.0, 18.0),
                TextSpan("(OFCI)", 844.0, 1018.0, 56.0, 18.0),
                TextSpan("TO", 990.0, 1348.0, 20.0, 14.0),
                TextSpan("RW4SS3F25", 936.0, 1364.0, 100.0, 14.0),
                TextSpan("SEE DRAWING", 936.0, 1380.0, 94.0, 14.0),
                TextSpan("DEMO-EE-4004", 936.0, 1396.0, 88.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )
        downstream_page = PageEvidence(
            id="src_elec_p182",
            sourceFileId="src_elec",
            page=182,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("FROM", 360.0, 92.0, 38.0, 14.0),
                TextSpan("RW4SWG2F6", 334.0, 106.0, 90.0, 14.0),
                TextSpan("SEE DRAWING", 334.0, 120.0, 90.0, 14.0),
                TextSpan("DEMO-EE-4115", 340.0, 135.0, 80.0, 14.0),
                TextSpan("RW4SS3F25", 90.0, 228.0, 124.0, 18.0),
                TextSpan("(OFCI)", 96.0, 249.0, 58.0, 18.0),
                TextSpan("TO", 389.0, 1394.0, 18.0, 14.0),
                TextSpan("RW4MDP4F21", 342.0, 1408.0, 112.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [upstream_page, downstream_page], {"src_elec": "/packages/Electrical Package.pdf"})

        nodes_by_tag = {}
        for node in graph.nodes:
            nodes_by_tag.setdefault(node.tag, []).append(node)
        self.assertEqual(len(nodes_by_tag["RW4SS3F25"]), 1)
        owner = nodes_by_tag["RW4SS3F25"][0]
        switchgear = nodes_by_tag["RW4SWG2F6"][0]
        mdp = nodes_by_tag["RW4MDP4F21"][0]
        self.assertIn("mergedFromNodeIds", owner.metadata)
        self.assertTrue(any(edge.sourceId == owner.id and edge.targetId == switchgear.id for edge in graph.edges))
        self.assertTrue(any(edge.sourceId == mdp.id and edge.targetId == owner.id for edge in graph.edges))
        self.assertGreaterEqual(graph.metrics["crossPageDedupe"]["mergedDuplicateTags"], 1)

    def test_cross_page_duplicate_merge_preserves_generator_component_feed_without_parenting_generator(self):
        generator_page = PageEvidence(
            id="src_elec_p180",
            sourceFileId="src_elec",
            page=180,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("GEN-15", 1140.0, 430.0, 68.0, 18.0),
                TextSpan("FROM", 908.0, 604.0, 40.0, 14.0),
                TextSpan("RW4MDP4C6", 884.0, 620.0, 92.0, 14.0),
                TextSpan("SEE DRAWING", 884.0, 638.0, 94.0, 14.0),
                TextSpan("DEMO-EE-4114", 887.0, 656.0, 88.0, 14.0),
                TextSpan("RW4SWG2F6", 842.0, 996.0, 104.0, 18.0),
                TextSpan("(OFCI)", 844.0, 1018.0, 56.0, 18.0),
                TextSpan("TO", 990.0, 1348.0, 20.0, 14.0),
                TextSpan("RW4SS3F25", 936.0, 1364.0, 100.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )
        downstream_page = PageEvidence(
            id="src_elec_p182",
            sourceFileId="src_elec",
            page=182,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("RW4SWG2F6", 840.0, 110.0, 104.0, 18.0),
                TextSpan("RW4MDP4C6", 840.0, 420.0, 104.0, 18.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [generator_page, downstream_page], {"src_elec": "/packages/Electrical Package.pdf"})

        nodes_by_tag = {}
        for node in graph.nodes:
            nodes_by_tag.setdefault(node.tag, []).append(node)
        self.assertEqual(len(nodes_by_tag["RW4MDP4C6"]), 1)
        upstream = nodes_by_tag["RW4MDP4C6"][0]
        generator = nodes_by_tag["GEN-15"][0]
        switchgear = next(node for node in nodes_by_tag["RW4SWG2F6"] if node.metadata.get("source") == "switchgear_ofci_owner_tag")
        self.assertEqual(upstream.metadata.get("source"), "incoming_sheet_reference")
        self.assertTrue(any(edge.kind == "power_source" and edge.sourceId == generator.id and edge.targetId == upstream.id for edge in graph.edges))
        self.assertFalse(any(edge.kind == "attached_to_line" and edge.sourceId == generator.id and edge.targetId == upstream.id for edge in graph.edges))
        self.assertTrue(any(edge.sourceId == switchgear.id and edge.targetId == generator.id for edge in graph.edges))
        self.assertFalse(any(edge.sourceId == upstream.id and edge.targetId == switchgear.id for edge in graph.edges))

    def test_marks_compound_targets_resolved_when_loaded_downstream_tags_exist(self):
        upstream_page = PageEvidence(
            id="src_elec_p180",
            sourceFileId="src_elec",
            page=180,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("GEN-15", 1140.0, 430.0, 68.0, 18.0),
                TextSpan("FROM", 908.0, 604.0, 40.0, 14.0),
                TextSpan("RW4MDP4C6", 884.0, 620.0, 92.0, 14.0),
                TextSpan("SEE DRAWING", 884.0, 638.0, 94.0, 14.0),
                TextSpan("DEMO-EE-4114", 887.0, 656.0, 88.0, 14.0),
                TextSpan("RW4SWG2F6", 842.0, 996.0, 104.0, 18.0),
                TextSpan("(OFCI)", 844.0, 1018.0, 56.0, 18.0),
                TextSpan("TO", 1184.0, 1348.0, 20.0, 14.0),
                TextSpan("RW4SS3D26 & F26", 1130.0, 1364.0, 132.0, 14.0),
                TextSpan("SEE DRAWING", 1130.0, 1380.0, 94.0, 14.0),
                TextSpan("DEMO-EE-4005", 1130.0, 1396.0, 88.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )
        downstream_page = PageEvidence(
            id="src_elec_p183",
            sourceFileId="src_elec",
            page=183,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("FROM", 360.0, 92.0, 38.0, 14.0),
                TextSpan("RW4SWG2F6", 334.0, 106.0, 90.0, 14.0),
                TextSpan("SEE DRAWING", 334.0, 120.0, 90.0, 14.0),
                TextSpan("DEMO-EE-4115", 340.0, 135.0, 80.0, 14.0),
                TextSpan("RW4SS3D26", 90.0, 228.0, 124.0, 18.0),
                TextSpan("(OFCI)", 90.0, 249.0, 58.0, 18.0),
                TextSpan("RW4SS3F26", 2418.0, 228.0, 124.0, 18.0),
                TextSpan("(OFCI)", 2483.0, 249.0, 58.0, 18.0),
                TextSpan("TO", 389.0, 1394.0, 18.0, 14.0),
                TextSpan("RW4MDP4F21", 342.0, 1408.0, 112.0, 14.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [upstream_page, downstream_page], {"src_elec": "/packages/Electrical Package.pdf"})

        compound = next(node for node in graph.nodes if node.tag == "RW4SS3D26 & F26")
        self.assertEqual(compound.metadata["resolvedAliasTags"], ["RW4SS3D26", "RW4SS3F26"])
        self.assertTrue(compound.metadata["suppressInEquipmentFlow"])
        self.assertEqual(graph.metrics["crossPageDedupe"]["resolvedCompoundTargets"], 1)

    def test_extracts_single_page_device_hierarchy_under_major_equipment(self):
        page = PageEvidence(
            id="src_elec_device_p1",
            sourceFileId="src_elec_device",
            page=1,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("RW4SWG2F6", 100.0, 100.0, 120.0, 16.0),
                TextSpan("AA 3000kVA", 280.0, 260.0, 120.0, 16.0),
                TextSpan("52-M1", 300.0, 314.0, 70.0, 16.0),
                TextSpan("METER-M1", 306.0, 350.0, 90.0, 16.0),
                TextSpan("CT-1", 312.0, 386.0, 70.0, 16.0),
                TextSpan("M1", 318.0, 422.0, 32.0, 16.0),
                TextSpan("RW4MDP4F21", 680.0, 720.0, 120.0, 16.0),
                TextSpan("600A", 700.0, 760.0, 70.0, 16.0),
                TextSpan("GENERAL NOTES", 900.0, 1000.0, 130.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_device": "/packages/Electrical Package.pdf"})

        node_by_tag = {node.tag: node for node in graph.nodes}
        self.assertIn("52-M1", node_by_tag)
        self.assertIn("METER-M1", node_by_tag)
        self.assertIn("CT-1", node_by_tag)
        self.assertIn("M1", node_by_tag)
        self.assertIn("600A", node_by_tag)
        self.assertNotIn("GENERAL", node_by_tag)
        transformer = node_by_tag["AA 3000KVA"]
        breaker = node_by_tag["52-M1"]
        meter = node_by_tag["METER-M1"]
        current_transformer = node_by_tag["CT-1"]
        motor_device = node_by_tag["M1"]
        feeder = node_by_tag["RW4MDP4F21"]
        rating = node_by_tag["600A"]
        self.assertTrue(any(edge.kind == "device_on_equipment" and edge.sourceId == breaker.id and edge.targetId == transformer.id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "device_on_equipment" and edge.sourceId == meter.id and edge.targetId == transformer.id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "device_on_equipment" and edge.sourceId == current_transformer.id and edge.targetId == transformer.id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "device_on_equipment" and edge.sourceId == motor_device.id and edge.targetId == transformer.id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "device_on_line" and edge.sourceId == rating.id and edge.targetId == feeder.id and edge.metadata["source"] == "electrical_line_annotation" for edge in graph.edges))
        self.assertEqual(graph.metrics["deviceNodes"], 5)
        self.assertEqual(graph.metrics["deviceEdges"], 5)

    def test_extracts_switchgear_a_b_side_section_hierarchy(self):
        page = PageEvidence(
            id="src_elec_switchgear_p1",
            sourceFileId="src_elec_switchgear",
            page=1,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("RW4SWG2F6", 1240.0, 107.0, 80.0, 16.0),
                TextSpan("SW A", 111.0, 1401.0, 36.0, 16.0),
                TextSpan("(SECTION 1)", 90.0, 1415.0, 78.0, 16.0),
                TextSpan("TRANSFORMER", 331.0, 1408.0, 98.0, 16.0),
                TextSpan("MAIN", 642.0, 1568.0, 36.0, 16.0),
                TextSpan("BREAKER", 628.0, 1582.0, 64.0, 16.0),
                TextSpan("(SECTION 2)", 621.0, 1596.0, 78.0, 16.0),
                TextSpan("RW4MDP4F21", 861.0, 1501.0, 84.0, 16.0),
                TextSpan("3A", 786.0, 1420.0, 20.0, 16.0),
                TextSpan("SW B", 2415.0, 1401.0, 36.0, 16.0),
                TextSpan("(SECTION 13)", 2391.0, 1415.0, 86.0, 16.0),
                TextSpan("TRANSFORMER", 2131.0, 1408.0, 98.0, 16.0),
                TextSpan("M2", 2386.0, 1206.0, 24.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_switchgear": "/packages/Electrical Package.pdf"})

        node_by_tag = {node.tag: node for node in graph.nodes}
        self.assertIn("SW A (SECTION 1)", node_by_tag)
        self.assertIn("SW B (SECTION 13)", node_by_tag)
        self.assertIn("SW A TRANSFORMER", node_by_tag)
        self.assertIn("MAIN BREAKER (SECTION 2)", node_by_tag)
        self.assertIn("RW4MDP4F21", node_by_tag)
        section_a = node_by_tag["SW A (SECTION 1)"]
        transformer_a = node_by_tag["SW A TRANSFORMER"]
        breaker = node_by_tag["MAIN BREAKER (SECTION 2)"]
        panel = node_by_tag["RW4MDP4F21"]
        self.assertTrue(any(edge.kind == "equipment_on_section" and edge.sourceId == transformer_a.id and edge.targetId == section_a.id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "device_on_equipment" and edge.sourceId == breaker.id and edge.targetId == transformer_a.id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "feeds_panel" and edge.sourceId == panel.id and edge.targetId == breaker.id for edge in graph.edges))
        self.assertEqual(graph.metrics["sectionNodes"], 2)
        self.assertGreaterEqual(graph.metrics["switchgearHierarchyEdges"], 3)

    def test_reads_switchgear_section_labels_from_drawing_not_fixed_a_b_only(self):
        page = PageEvidence(
            id="src_elec_switchgear_c_p1",
            sourceFileId="src_elec_switchgear_c",
            page=1,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("RW4SWG2F6", 1240.0, 107.0, 80.0, 16.0),
                TextSpan("SW C", 111.0, 760.0, 36.0, 16.0),
                TextSpan("(SECTION 7)", 90.0, 774.0, 78.0, 16.0),
                TextSpan("TRANSFORMER", 331.0, 768.0, 98.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_switchgear_c": "/packages/Electrical Package.pdf"})

        node_by_tag = {node.tag: node for node in graph.nodes}
        self.assertIn("SW C (SECTION 7)", node_by_tag)
        self.assertIn("SW C TRANSFORMER", node_by_tag)
        section = node_by_tag["SW C (SECTION 7)"]
        transformer = node_by_tag["SW C TRANSFORMER"]
        self.assertTrue(any(edge.kind == "equipment_on_section" and edge.sourceId == transformer.id and edge.targetId == section.id for edge in graph.edges))

    def test_promotes_ofci_corner_labels_as_switchgear_section_roots(self):
        page = PageEvidence(
            id="src_elec_ofci_p1",
            sourceFileId="src_elec_ofci",
            page=183,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("RW4SS3D26", 92.0, 96.0, 86.0, 16.0),
                TextSpan("(OFCI)", 96.0, 118.0, 52.0, 16.0),
                TextSpan("RW4SS3F26", 2598.0, 96.0, 86.0, 16.0),
                TextSpan("(OFCI)", 2602.0, 118.0, 52.0, 16.0),
                TextSpan("DEMO - ELECTRICAL FACILITY SUBSTATION RW4SS3D26/F26 ONELINE DIAGRAM", 1000.0, 72.0, 760.0, 16.0),
                TextSpan("SW A", 124.0, 1401.0, 36.0, 16.0),
                TextSpan("(SECTION 1)", 104.0, 1415.0, 78.0, 16.0),
                TextSpan("TRANSFORMER", 331.0, 1408.0, 98.0, 16.0),
                TextSpan("SW B", 2415.0, 1401.0, 36.0, 16.0),
                TextSpan("(SECTION 13)", 2391.0, 1415.0, 86.0, 16.0),
                TextSpan("TRANSFORMER", 2131.0, 1408.0, 98.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_ofci": "/packages/Electrical Package.pdf"})

        node_by_tag = {node.tag: node for node in graph.nodes}
        self.assertIn("RW4SS3D26 (OFCI)", node_by_tag)
        self.assertIn("RW4SS3F26 (OFCI)", node_by_tag)
        self.assertEqual(node_by_tag["RW4SS3D26 (OFCI)"].metadata["procurement"], "OFCI")
        self.assertEqual(node_by_tag["RW4SS3F26 (OFCI)"].metadata["procurement"], "OFCI")
        section_a = node_by_tag["SW A (SECTION 1)"]
        section_b = node_by_tag["SW B (SECTION 13)"]
        owner_d = node_by_tag["RW4SS3D26 (OFCI)"]
        owner_f = node_by_tag["RW4SS3F26 (OFCI)"]
        self.assertTrue(any(edge.sourceId == section_a.id and edge.targetId == owner_d.id for edge in graph.edges))
        self.assertTrue(any(edge.sourceId == section_b.id and edge.targetId == owner_f.id for edge in graph.edges))
        self.assertGreaterEqual(graph.metrics["sectionNodes"], 4)

    def test_promotes_mswg_and_swg_ofci_labels_as_owner_roots(self):
        page = PageEvidence(
            id="src_elec_mswg_ofci_p1",
            sourceFileId="src_elec_mswg_ofci",
            page=179,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("RSMSWG3C25", 120.0, 120.0, 112.0, 16.0),
                TextSpan("(OFCI)", 124.0, 142.0, 52.0, 16.0),
                TextSpan("SW A", 180.0, 760.0, 36.0, 16.0),
                TextSpan("(SECTION 1)", 160.0, 774.0, 78.0, 16.0),
                TextSpan("TRANSFORMER", 330.0, 768.0, 98.0, 16.0),
                TextSpan("RS4SWG2F25", 2470.0, 120.0, 112.0, 16.0),
                TextSpan("(OFCI)", 2474.0, 142.0, 52.0, 16.0),
                TextSpan("SW B", 2380.0, 760.0, 36.0, 16.0),
                TextSpan("(SECTION 12)", 2360.0, 774.0, 86.0, 16.0),
                TextSpan("TRANSFORMER", 2200.0, 768.0, 98.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_mswg_ofci": "/packages/Electrical Package.pdf"})

        node_by_tag = {node.tag: node for node in graph.nodes}
        self.assertIn("RSMSWG3C25 (OFCI)", node_by_tag)
        self.assertIn("RS4SWG2F25 (OFCI)", node_by_tag)
        self.assertEqual(node_by_tag["RSMSWG3C25 (OFCI)"].metadata["equipmentClass"], "main_switchgear")
        self.assertEqual(node_by_tag["RS4SWG2F25 (OFCI)"].metadata["equipmentClass"], "switchgear")
        self.assertTrue(any(edge.sourceId == node_by_tag["RSMSWG3C25"].id and edge.targetId == node_by_tag["RSMSWG3C25 (OFCI)"].id for edge in graph.edges))
        self.assertTrue(any(edge.sourceId == node_by_tag["SW A (SECTION 1)"].id and edge.targetId == node_by_tag["RSMSWG3C25 (OFCI)"].id for edge in graph.edges))
        self.assertTrue(any(edge.sourceId == node_by_tag["SW B (SECTION 12)"].id and edge.targetId == node_by_tag["RS4SWG2F25 (OFCI)"].id for edge in graph.edges))

    def test_ignores_unpaired_switch_side_markers_and_generic_transformer_text(self):
        page = PageEvidence(
            id="src_elec_side_markers_p1",
            sourceFileId="src_elec_side_markers",
            page=186,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("RS4SS2F25", 300.0, 160.0, 96.0, 16.0),
                TextSpan("(OFCI)", 304.0, 182.0, 52.0, 16.0),
                TextSpan("SW A", 140.0, 220.0, 36.0, 16.0),
                TextSpan("M1", 190.0, 220.0, 24.0, 16.0),
                TextSpan("T1", 230.0, 220.0, 24.0, 16.0),
                TextSpan("SW B", 300.0, 220.0, 36.0, 16.0),
                TextSpan("M2", 350.0, 220.0, 24.0, 16.0),
                TextSpan("T2", 390.0, 220.0, 24.0, 16.0),
                TextSpan("TRANSFORMER", 600.0, 420.0, 98.0, 16.0),
                TextSpan("SW A", 640.0, 1320.0, 36.0, 16.0),
                TextSpan("(SECTION 6)", 620.0, 1334.0, 78.0, 16.0),
                TextSpan("TRANSFORMER", 760.0, 1328.0, 98.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_side_markers": "/packages/Electrical Package.pdf"})

        section_tags = [node.tag for node in graph.nodes if node.kind == "section"]
        equipment_tags = [node.tag for node in graph.nodes if node.kind == "equipment"]
        self.assertEqual(section_tags.count("SW A SECTION"), 0)
        self.assertEqual(section_tags.count("SW B SECTION"), 0)
        self.assertIn("SW A (SECTION 6)", section_tags)
        self.assertNotIn("TRANSFORMER", equipment_tags)
        self.assertIn("SW A TRANSFORMER", equipment_tags)

    def test_prefers_linework_connected_line_over_nearest_text_label(self):
        page = PageEvidence(
            id="src_elec_vector_p1",
            sourceFileId="src_elec_vector",
            page=1,
            width=1200.0,
            height=800.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 1200.0, "height": 800.0},
            textSpans=[
                TextSpan("RW4SWG2F6", 80.0, 492.0, 100.0, 16.0),
                TextSpan("RW4MDP4F21", 80.0, 150.0, 110.0, 16.0),
                TextSpan("AA 3000kVA", 500.0, 488.0, 100.0, 16.0),
            ],
            vectorCount=1,
            vectorSegments=[
                VectorSegment(
                    id="v1",
                    kind="line",
                    points=[{"x": 160.0, "y": 500.0}, {"x": 540.0, "y": 500.0}],
                    bounds={"x": 160.0, "y": 500.0, "width": 380.0, "height": 1.0},
                    stroke="#111111",
                    strokeWidth=1.0,
                )
            ],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_vector": "/packages/Electrical Package.pdf"})

        node_by_tag = {node.tag: node for node in graph.nodes}
        transformer = node_by_tag["AA 3000KVA"]
        switchgear = node_by_tag["RW4SWG2F6"]
        self.assertTrue(any(edge.kind == "attached_to_line" and edge.sourceId == transformer.id and edge.targetId == switchgear.id and edge.metadata["source"] == "linework_geometry" for edge in graph.edges))

    def test_uses_enclosure_rectangles_to_nest_internal_devices_under_panel(self):
        page = PageEvidence(
            id="src_elec_enclosure_p1",
            sourceFileId="src_elec_enclosure",
            page=1,
            width=1200.0,
            height=800.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 1200.0, "height": 800.0},
            textSpans=[
                TextSpan("RW4SWG2F6", 70.0, 70.0, 100.0, 16.0),
                TextSpan("VFD-CH-01", 300.0, 210.0, 90.0, 16.0),
                TextSpan("52-M1", 330.0, 280.0, 60.0, 16.0),
                TextSpan("CT-1", 340.0, 330.0, 45.0, 16.0),
            ],
            vectorCount=1,
            vectorSegments=[
                VectorSegment(
                    id="rect1",
                    kind="rect",
                    points=[],
                    bounds={"x": 280.0, "y": 190.0, "width": 220.0, "height": 220.0},
                    stroke="#111111",
                    strokeWidth=1.0,
                )
            ],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_enclosure": "/packages/Electrical Package.pdf"})

        node_by_tag = {node.tag: node for node in graph.nodes}
        vfd = node_by_tag["VFD-CH-01"]
        breaker = node_by_tag["52-M1"]
        ct = node_by_tag["CT-1"]
        self.assertEqual(vfd.kind, "equipment")
        self.assertEqual(vfd.metadata["equipmentClass"], "vfd")
        self.assertTrue(any(edge.kind == "device_on_equipment" and edge.sourceId == breaker.id and edge.targetId == vfd.id and edge.metadata["source"] == "enclosure_containment" for edge in graph.edges))
        self.assertTrue(any(edge.kind == "device_on_equipment" and edge.sourceId == ct.id and edge.targetId == vfd.id and edge.metadata["source"] == "enclosure_containment" for edge in graph.edges))

    def test_classifies_ansi_device_numbers_and_reports_proximity_only_edges(self):
        page = PageEvidence(
            id="src_elec_ansi_p1",
            sourceFileId="src_elec_ansi",
            page=1,
            width=1200.0,
            height=800.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 1200.0, "height": 800.0},
            textSpans=[
                TextSpan("RW4SWG2F6", 70.0, 70.0, 100.0, 16.0),
                TextSpan("52-M1", 210.0, 130.0, 60.0, 16.0),
                TextSpan("87T", 260.0, 160.0, 45.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_ansi": "/packages/Electrical Package.pdf"})

        node_by_tag = {node.tag: node for node in graph.nodes}
        self.assertEqual(node_by_tag["52-M1"].metadata["deviceClass"], "circuit_breaker")
        self.assertEqual(node_by_tag["87T"].metadata["deviceClass"], "transformer_differential_relay")
        self.assertTrue(any(edge.metadata["source"] == "electrical_line_annotation" for edge in graph.edges))
        self.assertEqual(graph.metrics["pageClassifications"]["one_line"], 1)

    def test_does_not_extract_voltage_and_impedance_numbers_as_ansi_devices(self):
        page = PageEvidence(
            id="src_elec_noise_p1",
            sourceFileId="src_elec_noise",
            page=1,
            width=1200.0,
            height=800.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 1200.0, "height": 800.0},
            textSpans=[
                TextSpan("RW4SWG2F6", 70.0, 70.0, 100.0, 16.0),
                TextSpan("13.8kV-480Y/277V", 180.0, 120.0, 130.0, 16.0),
                TextSpan("5.75%Z", 180.0, 145.0, 60.0, 16.0),
                TextSpan("52", 240.0, 210.0, 28.0, 16.0),
                TextSpan("51N", 280.0, 240.0, 36.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_noise": "/packages/Electrical Package.pdf"})

        node_by_tag = {node.tag: node for node in graph.nodes}
        self.assertNotIn("13", node_by_tag)
        self.assertNotIn("75", node_by_tag)
        self.assertNotIn("00", node_by_tag)
        self.assertIn("52", node_by_tag)
        self.assertIn("51N", node_by_tag)

    def test_classifies_amp_ratings_as_ratings_not_protective_relay_numbers(self):
        page = PageEvidence(
            id="src_elec_rating_p1",
            sourceFileId="src_elec_rating",
            page=1,
            width=1200.0,
            height=800.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 1200.0, "height": 800.0},
            textSpans=[
                TextSpan("480Y/277V ONE LINE DIAGRAM", 70.0, 50.0, 210.0, 16.0),
                TextSpan("RW4SWG2F6", 70.0, 80.0, 100.0, 16.0),
                TextSpan("5000A", 210.0, 130.0, 56.0, 16.0),
                TextSpan("5000AF", 280.0, 130.0, 66.0, 16.0),
                TextSpan("50", 360.0, 130.0, 24.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        graph = build_electrical_relationship_graph("project_elec", [page], {"src_elec_rating": "/uploads/Electrical.pdf"})

        node_by_tag = {node.tag: node for node in graph.nodes}
        self.assertEqual(node_by_tag["5000A"].metadata["deviceClass"], "current_rating")
        self.assertEqual(node_by_tag["5000AF"].metadata["deviceClass"], "frame_rating")
        self.assertEqual(node_by_tag["50"].metadata["deviceClass"], "overcurrent_relay")


if __name__ == "__main__":
    unittest.main()
