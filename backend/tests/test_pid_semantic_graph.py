import unittest

from recreation_extractor.pid_stitch.models import ContinuationCandidate, ContinuationMatch, PageEvidence, TextSpan, VectorSegment
from recreation_extractor.pid_stitch.source_graph import LINE_TAG_RE
from recreation_extractor.pid_stitch.semantic_graph import build_pid_relationship_graph
from recreation_extractor.pid_stitch.system_colors import discover_system_color_map


class PidSemanticGraphTests(unittest.TestCase):
    def test_builds_stable_nodes_and_relationships_from_extracted_pid_evidence(self):
        page_a = self._page(
            "src_hhw_02_p1",
            "src_hhw_02",
            [
                TextSpan('10"-HHWR-CS02', 260.0, 320.0, 130.0, 16.0),
                TextSpan("R-HHW-P-01", 300.0, 354.0, 92.0, 16.0),
                TextSpan("PIT-101", 324.0, 298.0, 72.0, 16.0),
            ],
        )
        page_b = self._page(
            "src_hhw_03_p1",
            "src_hhw_03",
            [
                TextSpan('10"-HHWR-CS02', 120.0, 320.0, 130.0, 16.0),
                TextSpan("R-HHW-HWB-01", 240.0, 360.0, 118.0, 16.0),
            ],
        )
        candidate_a = self._candidate("a_to_b", "src_hhw_02", '10"-HHWR-CS02', "DEMO-ME-4HHW03", "to")
        candidate_b = self._candidate("b_from_a", "src_hhw_03", '10"-HHWR-CS02', "DEMO-ME-4HHW02", "from")
        match = ContinuationMatch("match_hhwr", "a_to_b", "b_from_a", 96.0, ["same line"], "confirmed")
        color_map = discover_system_color_map(
            [page_a, page_b],
            [candidate_a, candidate_b],
            {
                "src_hhw_02": "/packages/DEMO-ME-4HHW02.pdf",
                "src_hhw_03": "/packages/DEMO-ME-4HHW03.pdf",
            },
        )

        graph = build_pid_relationship_graph(
            "project_graph",
            [page_a, page_b],
            [candidate_a, candidate_b],
            [match],
            {
                "src_hhw_02": "/packages/DEMO-ME-4HHW02.pdf",
                "src_hhw_03": "/packages/DEMO-ME-4HHW03.pdf",
            },
            color_map,
        )

        node_by_tag = {(node.kind, node.tag, node.sourceFileId): node for node in graph.nodes}
        pump = node_by_tag[("equipment", "R-HHW-P-01", "src_hhw_02")]
        instrument = node_by_tag[("instrument", "PIT-101", "src_hhw_02")]
        line_a = node_by_tag[("line_tag", '10"-HHWR-CS02', "src_hhw_02")]
        line_b = node_by_tag[("line_tag", '10"-HHWR-CS02', "src_hhw_03")]

        self.assertEqual(pump.id, "pidnode_equipment_src_hhw_02_p1_r-hhw-p-01")
        self.assertEqual(line_a.system, "HHW")
        self.assertTrue(
            any(edge.kind == "attached_to_line" and edge.sourceId == pump.id and edge.targetId == line_a.id for edge in graph.edges)
        )
        self.assertTrue(
            any(edge.kind == "instrument_on_line" and edge.sourceId == instrument.id and edge.targetId == line_a.id for edge in graph.edges)
        )
        continuation_edges = [edge for edge in graph.edges if edge.kind == "continues_to"]
        self.assertEqual(len(continuation_edges), 1)
        self.assertEqual(continuation_edges[0].sourceId, line_a.id)
        self.assertEqual(continuation_edges[0].targetId, line_b.id)
        self.assertEqual(continuation_edges[0].metadata["matchId"], "match_hhwr")
        self.assertEqual(graph.metrics["equipmentNodes"], 2)
        self.assertEqual(graph.metrics["instrumentNodes"], 1)
        self.assertEqual(graph.metrics["lineTagNodes"], 2)
        self.assertEqual(graph.qa["isolatedEquipmentNodes"], [])

    def test_extracts_valve_and_device_tags_into_single_page_pid_hierarchy(self):
        page = self._page(
            "src_cda_device_p1",
            "src_cda_device",
            [
                TextSpan('6"-CDA-SS01', 190.0, 180.0, 120.0, 16.0),
                TextSpan("R-CDA-C-04", 420.0, 210.0, 105.0, 16.0),
                TextSpan("PIT-420", 460.0, 248.0, 72.0, 16.0),
                TextSpan("XV-420", 492.0, 282.0, 72.0, 16.0),
                TextSpan("MOV-421", 526.0, 316.0, 80.0, 16.0),
            ],
        )
        color_map = discover_system_color_map([page], [], {"src_cda_device": "/packages/DEMO-ME-4CDA01.pdf"})

        graph = build_pid_relationship_graph("project_graph_devices", [page], [], [], {"src_cda_device": "/packages/DEMO-ME-4CDA01.pdf"}, color_map)

        node_by_tag = {node.tag: node for node in graph.nodes}
        line = node_by_tag['6"-CDA-SS01']
        self.assertIn("XV-420", node_by_tag)
        self.assertIn("MOV-421", node_by_tag)
        self.assertTrue(any(edge.kind == "instrument_on_line" and edge.sourceId == node_by_tag["PIT-420"].id and edge.targetId == line.id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "device_on_line" and edge.sourceId == node_by_tag["XV-420"].id and edge.targetId == line.id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "device_on_line" and edge.sourceId == node_by_tag["MOV-421"].id and edge.targetId == line.id for edge in graph.edges))
        self.assertEqual(graph.metrics["deviceNodes"], 2)

    def test_assembles_split_mechanical_instrument_and_device_tags(self):
        page = self._page(
            "src_hhw_split_p1",
            "src_hhw_split",
            [
                TextSpan('12"-HHWS-CS02', 220.0, 320.0, 130.0, 16.0),
                TextSpan("PIT", 430.0, 272.0, 30.0, 16.0),
                TextSpan("01-HHW", 428.0, 292.0, 62.0, 16.0),
                TextSpan("FIT", 506.0, 276.0, 30.0, 16.0),
                TextSpan("02-HHW", 504.0, 296.0, 62.0, 16.0),
                TextSpan("FCV", 584.0, 280.0, 34.0, 16.0),
                TextSpan("03-HHW", 582.0, 300.0, 62.0, 16.0),
            ],
        )
        color_map = discover_system_color_map([page], [], {"src_hhw_split": "/packages/DEMO-ME-4HHW02.pdf"})

        graph = build_pid_relationship_graph("project_graph_split_tags", [page], [], [], {"src_hhw_split": "/packages/DEMO-ME-4HHW02.pdf"}, color_map)

        node_by_tag = {node.tag: node for node in graph.nodes}
        line = node_by_tag['12"-HHWS-CS02']
        self.assertIn("PIT 01-HHW", node_by_tag)
        self.assertIn("FIT 02-HHW", node_by_tag)
        self.assertIn("FCV 03-HHW", node_by_tag)
        self.assertEqual(node_by_tag["PIT 01-HHW"].kind, "instrument")
        self.assertEqual(node_by_tag["FIT 02-HHW"].kind, "instrument")
        self.assertEqual(node_by_tag["FCV 03-HHW"].kind, "device")
        self.assertTrue(any(edge.kind == "instrument_on_line" and edge.sourceId == node_by_tag["PIT 01-HHW"].id and edge.targetId == line.id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "instrument_on_line" and edge.sourceId == node_by_tag["FIT 02-HHW"].id and edge.targetId == line.id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "device_on_line" and edge.sourceId == node_by_tag["FCV 03-HHW"].id and edge.targetId == line.id for edge in graph.edges))
        self.assertEqual(graph.metrics["instrumentNodes"], 2)
        self.assertEqual(graph.metrics["deviceNodes"], 1)

    def test_captures_fully_qualified_cleanroom_instrument_table_tags(self):
        page = self._page(
            "src_cleanroom_table_p59",
            "src_cleanroom_table",
            [
                TextSpan("P&ID - CLEANROOM MAU", 40.0, 40.0, 220.0, 16.0),
                TextSpan('8"-SCHWS-CS02', 160.0, 300.0, 128.0, 16.0),
                TextSpan('6"-SA-CS01', 160.0, 338.0, 128.0, 16.0),
                TextSpan("R-SA-MAU-XXX_VFD-01", 430.0, 300.0, 150.0, 16.0),
                TextSpan("CLEANROOM AIT", 900.0, 110.0, 120.0, 16.0),
                TextSpan("DEMO-SA-MAU-AIT-11A", 900.0, 140.0, 170.0, 16.0),
                TextSpan("DEMO-SA-MAU-TIT-11B", 1080.0, 140.0, 170.0, 16.0),
                TextSpan("DEMO-SA-MAU-PDIT-11", 1260.0, 140.0, 170.0, 16.0),
            ],
        )
        color_map = discover_system_color_map([page], [], {"src_cleanroom_table": "/packages/DEMO-ME-4MAU01.pdf"})

        graph = build_pid_relationship_graph("project_graph_cleanroom_table", [page], [], [], {"src_cleanroom_table": "/packages/DEMO-ME-4MAU01.pdf"}, color_map)

        node_by_tag = {node.tag: node for node in graph.nodes}
        self.assertIn("DEMO-SA-MAU-AIT-11A", node_by_tag)
        self.assertIn("DEMO-SA-MAU-TIT-11B", node_by_tag)
        self.assertIn("DEMO-SA-MAU-PDIT-11", node_by_tag)
        self.assertNotIn("AIT-11A", node_by_tag)
        self.assertNotIn("TIT-11B", node_by_tag)
        self.assertNotIn("PDIT-11", node_by_tag)
        self.assertEqual(node_by_tag["DEMO-SA-MAU-AIT-11A"].kind, "instrument")
        self.assertEqual(node_by_tag["DEMO-SA-MAU-AIT-11A"].system, "SA")
        self.assertEqual(node_by_tag["DEMO-SA-MAU-AIT-11A"].metadata["source"], "qualified_instrument_reference")
        table_node_ids = {node_by_tag[tag].id for tag in ["DEMO-SA-MAU-AIT-11A", "DEMO-SA-MAU-TIT-11B", "DEMO-SA-MAU-PDIT-11"]}
        self.assertFalse(any(edge.kind == "instrument_on_line" and edge.sourceId in table_node_ids for edge in graph.edges))
        self.assertEqual(graph.metrics["instrumentNodes"], 3)

    def test_external_flow_callout_becomes_source_traced_continuation_node(self):
        page = self._page(
            "src_icw_flow_p1",
            "src_icw_flow",
            [
                TextSpan('1 1/2"-ICW-PC05', 220.0, 320.0, 130.0, 16.0),
            ],
        )
        candidate = ContinuationCandidate(
            id="icw_source",
            sourceFileId="src_icw_flow",
            page=1,
            sheetRef="DEMO-ME-4ICW01",
            direction="from",
            label="FROM ICW SUPPLY DEMO-ME-4ICW01",
            lineTag='1 1/2"-ICW-PC05',
            system="ICW",
            edge="left",
            position={"x": 120.0, "y": 320.0},
            bounds={"x": 80.0, "y": 288.0, "width": 160.0, "height": 60.0},
            confidence=0.92,
            evidenceText="FROM ICW SUPPLY DEMO-ME-4ICW01",
            metadata={
                "externalFlowLabel": "ICW SUPPLY",
                "externalFlowRole": "source",
                "sourceDrawingRef": "DEMO-ME-4ICW01",
                "directionEvidence": "explicit_text",
                "calloutType": "rectangular_flow_callout",
            },
        )
        color_map = discover_system_color_map([page], [candidate], {"src_icw_flow": "/packages/DEMO-ME-4CDA01.pdf"})

        graph = build_pid_relationship_graph("project_graph_external_flow", [page], [candidate], [], {"src_icw_flow": "/packages/DEMO-ME-4CDA01.pdf"}, color_map)

        line = next(node for node in graph.nodes if node.kind == "line_tag")
        continuation = next(node for node in graph.nodes if node.kind == "continuation")
        self.assertEqual(continuation.tag, "External Source: ICW SUPPLY")
        self.assertEqual(continuation.metadata["sourceDrawingRef"], "DEMO-ME-4ICW01")
        self.assertEqual(continuation.metadata["directionEvidence"], "explicit_text")
        edge = next(edge for edge in graph.edges if edge.kind == "continuation_on_line")
        self.assertEqual(edge.sourceId, continuation.id)
        self.assertEqual(edge.targetId, line.id)
        self.assertEqual(edge.metadata["externalFlowLabel"], "ICW SUPPLY")
        self.assertEqual(edge.metadata["sourceDrawingRef"], "DEMO-ME-4ICW01")

    def test_mechanical_equipment_schedule_rows_become_hierarchy_nodes(self):
        page = self._page(
            "src_mech_sched_p188",
            "src_mech_sched",
            [
                TextSpan("DEMO-ME-3400", 2450.0, 1940.0, 92.0, 14.0),
                TextSpan("DEMO - MECHANICAL", 2450.0, 1970.0, 160.0, 14.0),
                TextSpan("EQUIPMENT SCHEDULES", 2450.0, 1990.0, 180.0, 14.0),
                TextSpan("PRIMARY CHILLED WATER PUMP SCHEDULE", 110.0, 120.0, 320.0, 16.0),
                TextSpan("TAG", 110.0, 156.0, 30.0, 14.0),
                TextSpan("UNIT LOCATION", 170.0, 156.0, 90.0, 14.0),
                TextSpan("SERVICE", 300.0, 156.0, 60.0, 14.0),
                TextSpan("R-CHW-P-01", 112.0, 190.0, 92.0, 14.0),
                TextSpan("LEVEL 1 - EUB PRIMARY CHILLED WATER 3,300 GPM", 170.0, 190.0, 360.0, 14.0),
                TextSpan("R-CHW-P-02", 112.0, 214.0, 92.0, 14.0),
                TextSpan("LEVEL 1 - EUB PRIMARY CHILLED WATER 3,300 GPM", 170.0, 214.0, 360.0, 14.0),
                TextSpan("CHEMICAL POT FEEDER SCHEDULE", 110.0, 350.0, 260.0, 16.0),
                TextSpan("TAG", 110.0, 386.0, 30.0, 14.0),
                TextSpan("LOCATION", 170.0, 386.0, 70.0, 14.0),
                TextSpan("SYSTEM", 300.0, 386.0, 58.0, 14.0),
                TextSpan("R-CHW-CFS-01", 112.0, 420.0, 104.0, 14.0),
                TextSpan("LEVEL 4 - EUB CHILLED WATER 7 GAL", 170.0, 420.0, 280.0, 14.0),
            ],
        )
        color_map = discover_system_color_map([page], [], {"src_mech_sched": "/packages/DEMO-ME-3400.pdf"})

        graph = build_pid_relationship_graph("project_graph_schedule", [page], [], [], {"src_mech_sched": "/packages/DEMO-ME-3400.pdf"}, color_map)

        node_by_tag = {node.tag: node for node in graph.nodes}
        self.assertIn("PRIMARY CHILLED WATER PUMP SCHEDULE", node_by_tag)
        self.assertIn("CHEMICAL POT FEEDER SCHEDULE", node_by_tag)
        self.assertIn("R-CHW-P-01", node_by_tag)
        self.assertIn("R-CHW-P-02", node_by_tag)
        self.assertIn("R-CHW-CFS-01", node_by_tag)
        self.assertEqual(node_by_tag["R-CHW-P-01"].metadata["source"], "mechanical_schedule_row")
        self.assertEqual(node_by_tag["R-CHW-P-01"].metadata["equipmentDescription"], "Primary Chilled Water Pump")
        self.assertEqual(node_by_tag["R-CHW-P-01"].metadata["scheduleTitle"], "PRIMARY CHILLED WATER PUMP SCHEDULE")
        self.assertTrue(
            any(
                edge.kind == "equipment_on_section"
                and edge.sourceId == node_by_tag["R-CHW-P-01"].id
                and edge.targetId == node_by_tag["PRIMARY CHILLED WATER PUMP SCHEDULE"].id
                for edge in graph.edges
            )
        )
        self.assertEqual(graph.metrics["mechanicalScheduleNodes"], 3)
        self.assertEqual(graph.metrics["pageClassifications"]["equipment_schedule"], 1)

    def test_mechanical_schedule_exact_tag_reuses_pid_equipment_node(self):
        pid_page = self._page(
            "src_mech_pkg_p50",
            "src_mech_pkg",
            [
                TextSpan("P&ID - PRIMARY CHILLED WATER", 40.0, 40.0, 220.0, 16.0),
                TextSpan('12"-CHWS-CS01', 180.0, 260.0, 128.0, 16.0),
                TextSpan("R-CHW-P-01", 420.0, 292.0, 92.0, 16.0),
            ],
        )
        schedule_page = self._page(
            "src_mech_pkg_p188",
            "src_mech_pkg",
            [
                TextSpan("DEMO-ME-3400", 2450.0, 1940.0, 92.0, 14.0),
                TextSpan("DEMO - MECHANICAL", 2450.0, 1970.0, 160.0, 14.0),
                TextSpan("EQUIPMENT SCHEDULES", 2450.0, 1990.0, 180.0, 14.0),
                TextSpan("PRIMARY CHILLED WATER PUMP SCHEDULE", 110.0, 120.0, 320.0, 16.0),
                TextSpan("TAG", 110.0, 156.0, 30.0, 14.0),
                TextSpan("SERVICE", 300.0, 156.0, 60.0, 14.0),
                TextSpan("R-CHW-P-01", 112.0, 190.0, 92.0, 14.0),
                TextSpan("LEVEL 1 - EUB PRIMARY CHILLED WATER 3,300 GPM", 170.0, 190.0, 360.0, 14.0),
            ],
        )
        pid_page.page = 50
        schedule_page.page = 188
        color_map = discover_system_color_map([pid_page, schedule_page], [], {"src_mech_pkg": "/packages/DEMO-ME-4CHW01.pdf"})

        graph = build_pid_relationship_graph(
            "project_graph_schedule_match",
            [pid_page, schedule_page],
            [],
            [],
            {"src_mech_pkg": "/packages/DEMO-ME-4CHW01.pdf"},
            color_map,
        )

        pumps = [node for node in graph.nodes if node.kind == "equipment" and node.tag == "R-CHW-P-01"]
        self.assertEqual(len(pumps), 1)
        self.assertEqual(pumps[0].sourcePageId, "src_mech_pkg_p50")
        section = next(node for node in graph.nodes if node.kind == "section" and node.tag == "PRIMARY CHILLED WATER PUMP SCHEDULE")
        schedule_edge = next(edge for edge in graph.edges if edge.kind == "equipment_on_section" and edge.targetId == section.id)
        self.assertEqual(schedule_edge.sourceId, pumps[0].id)
        self.assertEqual(schedule_edge.metadata["matchStrategy"], "exact_tag")
        self.assertEqual(schedule_edge.metadata["scheduleTag"], "R-CHW-P-01")
        self.assertEqual(graph.metrics["scheduleMatchedNodes"], 1)
        self.assertEqual(graph.metrics["mechanicalScheduleNodes"], 0)

    def test_mechanical_schedule_ignores_related_tags_outside_tag_column(self):
        page = self._page(
            "src_mech_sched_related_p198",
            "src_mech_sched_related",
            [
                TextSpan("DEMO - MECHANICAL", 2450.0, 1970.0, 160.0, 14.0),
                TextSpan("EQUIPMENT SCHEDULES", 2450.0, 1990.0, 180.0, 14.0),
                TextSpan("PROCESS VACUUM PUMP SCHEDULE", 110.0, 120.0, 300.0, 16.0),
                TextSpan("TAG", 110.0, 156.0, 30.0, 14.0),
                TextSpan("ASSOCIATED EQUIPMENT", 420.0, 156.0, 170.0, 14.0),
                TextSpan("R-HUM-P-01", 112.0, 190.0, 92.0, 14.0),
                TextSpan("SERVES R-SA-MAU-402", 420.0, 190.0, 160.0, 14.0),
            ],
        )
        color_map = discover_system_color_map([page], [], {"src_mech_sched_related": "/packages/DEMO-ME-3600.pdf"})

        graph = build_pid_relationship_graph(
            "project_graph_schedule_related_tags",
            [page],
            [],
            [],
            {"src_mech_sched_related": "/packages/DEMO-ME-3600.pdf"},
            color_map,
        )

        equipment_tags = {node.tag for node in graph.nodes if node.kind == "equipment"}
        self.assertIn("R-HUM-P-01", equipment_tags)
        self.assertNotIn("R-SA-MAU-402", equipment_tags)
        self.assertEqual(graph.metrics["mechanicalScheduleNodes"], 1)

    def test_title_block_plan_sheets_are_ignored_for_mechanical_hierarchy(self):
        page = self._page(
            "src_mech_plan_p69",
            "src_mech_plan",
            [
                TextSpan("R-SA-FCU-101", 300.0, 300.0, 92.0, 14.0),
                TextSpan("DEMO - MECHANICAL", 2450.0, 1970.0, 160.0, 14.0),
                TextSpan("LEVEL 1 & 2 - OVERALL PRESSURIZATION & CLASSIFICATION PLANS", 2300.0, 1990.0, 480.0, 14.0),
            ],
        )
        color_map = discover_system_color_map([page], [], {"src_mech_plan": "/packages/DEMO-ME-1201.pdf"})

        graph = build_pid_relationship_graph("project_graph_plan_skip", [page], [], [], {"src_mech_plan": "/packages/DEMO-ME-1201.pdf"}, color_map)

        self.assertEqual(graph.nodes, [])
        self.assertEqual(graph.metrics["pageClassifications"]["non_hierarchy"], 1)

    def test_attaches_equipment_to_line_tag_through_connected_vector_geometry(self):
        page = PageEvidence(
            id="src_hhw_01_p1",
            sourceFileId="src_hhw_01",
            page=1,
            width=1200.0,
            height=900.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 1200.0, "height": 900.0},
            textSpans=[
                TextSpan('12"-HHWS-CS02', 210.0, 148.0, 130.0, 16.0),
                TextSpan("R-HHW-P-01", 680.0, 530.0, 110.0, 16.0),
            ],
            vectorCount=3,
            vectorSegments=[
                VectorSegment(
                    id="src_hhw_01_p1:main",
                    kind="line",
                    points=[{"x": 180.0, "y": 170.0}, {"x": 740.0, "y": 170.0}],
                    bounds={"x": 180.0, "y": 170.0, "width": 560.0, "height": 0.0},
                ),
                VectorSegment(
                    id="src_hhw_01_p1:drop",
                    kind="line",
                    points=[{"x": 740.0, "y": 170.0}, {"x": 740.0, "y": 520.0}],
                    bounds={"x": 740.0, "y": 170.0, "width": 0.0, "height": 350.0},
                ),
                VectorSegment(
                    id="src_hhw_01_p1:pump_stub",
                    kind="line",
                    points=[{"x": 700.0, "y": 520.0}, {"x": 740.0, "y": 520.0}],
                    bounds={"x": 700.0, "y": 520.0, "width": 40.0, "height": 0.0},
                ),
            ],
        )
        color_map = discover_system_color_map([page], [], {"src_hhw_01": "/packages/DEMO-ME-4HHW01.pdf"})

        graph = build_pid_relationship_graph("project_graph_vectors", [page], [], [], {"src_hhw_01": "/packages/DEMO-ME-4HHW01.pdf"}, color_map)

        pump = next(node for node in graph.nodes if node.tag == "R-HHW-P-01")
        line = next(node for node in graph.nodes if node.tag == '12"-HHWS-CS02')
        edge = next(edge for edge in graph.edges if edge.kind == "attached_to_line" and edge.sourceId == pump.id)
        self.assertEqual(edge.targetId, line.id)
        self.assertEqual(edge.metadata["source"], "connected_vector_geometry")
        self.assertEqual(graph.qa["isolatedEquipmentNodes"], [])

    def test_line_tag_regex_rejects_equipment_like_and_plain_note_text(self):
        text = '01-CDA-FLTR-XX 6" ABOVE 6"-CDA-SS01 2"-TCHWS-CS02'

        self.assertEqual([match.group(0) for match in LINE_TAG_RE.finditer(text)], ['6"-CDA-SS01', '2"-TCHWS-CS02'])

    def test_attachment_prefers_same_system_line_over_nearer_different_system_line(self):
        page = PageEvidence(
            id="src_cda_p1",
            sourceFileId="src_cda",
            page=1,
            width=1200.0,
            height=900.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 1200.0, "height": 900.0},
            textSpans=[
                TextSpan('6"-CDA-SS01', 190.0, 180.0, 120.0, 16.0),
                TextSpan('2"-TCHWS-CS02', 190.0, 520.0, 130.0, 16.0),
                TextSpan("R-CDA-C-04", 760.0, 700.0, 105.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )
        color_map = discover_system_color_map([page], [], {"src_cda": "/packages/DEMO-ME-4CDA01.pdf"})

        graph = build_pid_relationship_graph("project_graph_same_system", [page], [], [], {"src_cda": "/packages/DEMO-ME-4CDA01.pdf"}, color_map)

        compressor = next(node for node in graph.nodes if node.tag == "R-CDA-C-04")
        cda_line = next(node for node in graph.nodes if node.tag == '6"-CDA-SS01')
        edge = next(edge for edge in graph.edges if edge.kind == "attached_to_line" and edge.sourceId == compressor.id)
        self.assertEqual(edge.targetId, cda_line.id)
        self.assertEqual(edge.system, "CDA")
        self.assertEqual(edge.metadata["source"], "system_context_fallback")
        self.assertEqual(edge.status, "needs_review")

    def test_single_same_system_line_keeps_far_equipment_in_reviewable_hierarchy(self):
        page = PageEvidence(
            id="src_cda_p1",
            sourceFileId="src_cda",
            page=1,
            width=1800.0,
            height=1200.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 1800.0, "height": 1200.0},
            textSpans=[
                TextSpan('6"-CDA-SS01', 120.0, 120.0, 120.0, 16.0),
                TextSpan("R-CDA-C-01", 1450.0, 1020.0, 105.0, 16.0),
            ],
            vectorCount=0,
            vectorSegments=[],
        )
        color_map = discover_system_color_map([page], [], {"src_cda": "/packages/DEMO-ME-4CDA01.pdf"})

        graph = build_pid_relationship_graph("project_graph_far_same_system", [page], [], [], {"src_cda": "/packages/DEMO-ME-4CDA01.pdf"}, color_map)

        compressor = next(node for node in graph.nodes if node.tag == "R-CDA-C-01")
        line = next(node for node in graph.nodes if node.tag == '6"-CDA-SS01')
        edge = next(edge for edge in graph.edges if edge.kind == "attached_to_line" and edge.sourceId == compressor.id)
        self.assertEqual(edge.targetId, line.id)
        self.assertEqual(edge.confidence, 0.62)
        self.assertEqual(edge.status, "needs_review")

    def test_nests_component_tags_under_parent_equipment_when_line_tags_are_absent(self):
        page = self._page(
            "src_fcu_p1",
            "src_fcu",
            [
                TextSpan("R-SA-FCU-102", 180.0, 180.0, 110.0, 16.0),
                TextSpan("FCU-102-TCV-01", 210.0, 232.0, 130.0, 16.0),
                TextSpan("FCU-102-TIT-01", 210.0, 258.0, 130.0, 16.0),
                TextSpan("FCU-102-LSH-01", 210.0, 284.0, 130.0, 16.0),
            ],
        )
        color_map = discover_system_color_map([page], [], {"src_fcu": "/packages/Mech Package.pdf"})

        graph = build_pid_relationship_graph("project_graph_components", [page], [], [], {"src_fcu": "/packages/Mech Package.pdf"}, color_map)

        node_by_tag = {node.tag: node for node in graph.nodes}
        parent = node_by_tag["R-SA-FCU-102"]
        for child_tag in ("FCU-102-TCV-01", "FCU-102-TIT-01", "FCU-102-LSH-01"):
            child = node_by_tag[child_tag]
            self.assertTrue(
                any(edge.kind == "equipment_component" and edge.sourceId == child.id and edge.targetId == parent.id for edge in graph.edges),
                child_tag,
            )
        self.assertEqual(graph.metrics["componentEdges"], 3)

    def test_standard_chiller_page_builds_control_panel_hierarchy_from_coordinates(self):
        page = PageEvidence(
            id="src_mech_p8",
            sourceFileId="src_mech",
            page=8,
            width=3024.0,
            height=2160.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 3024.0, "height": 2160.0},
            textSpans=[
                TextSpan("STANDARD CHILLER", 1948.8, 177.7, 11.1, 75.6),
                TextSpan("R-CHW-CH-04", 1996.6, 193.0, 11.1, 52.9),
                TextSpan("R-CHW-CH-05", 1974.4, 193.2, 11.1, 52.9),
                TextSpan("PRIMARY CHILLED WATER PUMP", 1951.2, 332.4, 11.1, 120.1),
                TextSpan("R-CHW-P-04", 1996.6, 372.2, 11.1, 46.7),
                TextSpan("R-CHW-P-05", 1974.4, 372.2, 11.1, 46.7),
                TextSpan("R-CHW-CH-XX_CP-01", 1252.2, 1225.2, 11.1, 80.4),
                TextSpan("01-CHW-CH04", 1135.2, 1237.2, 11.1, 53.8),
                TextSpan("HSI", 1151.8, 1257.3, 11.1, 13.6),
                TextSpan("01B-CHW-CH04", 1204.8, 1458.1, 11.1, 58.8),
                TextSpan("HS", 1221.5, 1482.3, 11.1, 10.5),
                TextSpan("CHILLER CONTROL PANEL", 1252.2, 1469.6, 11.1, 96.1),
                TextSpan("R-CHW-P-XX_VFD-01", 592.0, 370.5, 11.1, 79.5),
                TextSpan("01-CHW-P04", 666.9, 377.3, 11.1, 47.6),
                TextSpan("HSI", 683.0, 396.0, 11.1, 13.6),
                TextSpan("04-CW-CH04", 1500.0, 700.0, 11.1, 48.3),
                TextSpan("PI", 1516.0, 720.0, 11.1, 7.6),
            ],
            vectorCount=0,
            vectorSegments=[],
        )
        color_map = discover_system_color_map([page], [], {"src_mech": "/packages/Mech Package.pdf"})

        graph = build_pid_relationship_graph("project_graph_standard_chiller", [page], [], [], {"src_mech": "/packages/Mech Package.pdf"}, color_map)

        node_by_tag = {node.tag: node for node in graph.nodes}
        root = node_by_tag["STANDARD CHILLER P&ID"]
        chiller_panel = node_by_tag["R-CHW-CH-XX_CP-01"]
        pump_panel = node_by_tag["R-CHW-P-XX_VFD-01"]
        self.assertEqual(root.kind, "section")
        self.assertEqual(root.metadata["representedInstanceTags"], ["R-CHW-CH-04", "R-CHW-CH-05", "R-CHW-P-05", "R-CHW-P-04"])
        self.assertTrue(any(edge.kind == "represents_instance" and edge.sourceId == node_by_tag["R-CHW-CH-04"].id and edge.targetId == root.id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "control_panel_for" and edge.sourceId == chiller_panel.id and edge.targetId == node_by_tag["R-CHW-CH-04"].id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "control_panel_for" and edge.sourceId == pump_panel.id and edge.targetId == node_by_tag["R-CHW-P-04"].id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "control_point_on_panel" and graph_node(graph, edge.sourceId).tag == "HSI 01-CHW-CH04" and edge.targetId == chiller_panel.id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "control_point_on_panel" and graph_node(graph, edge.sourceId).tag == "HSI 01-CHW-P04" and edge.targetId == pump_panel.id for edge in graph.edges))
        self.assertTrue(any(edge.kind == "instrument_on_equipment" and graph_node(graph, edge.sourceId).tag == "PI 04-CW-CH04" and edge.targetId == node_by_tag["R-CHW-CH-04"].id for edge in graph.edges))

    def test_dense_vector_pages_skip_component_scan_and_fall_back_to_nearest_line(self):
        vectors = [
            VectorSegment(
                id=f"src_dense_p1:noise_{index}",
                kind="line",
                points=[{"x": float(index), "y": 500.0}, {"x": float(index + 24), "y": 500.0}],
                bounds={"x": float(index), "y": 500.0, "width": 24.0, "height": 0.0},
            )
            for index in range(725)
        ]
        vectors.extend(
            [
                VectorSegment(
                    id="src_dense_p1:main",
                    kind="line",
                    points=[{"x": 180.0, "y": 170.0}, {"x": 740.0, "y": 170.0}],
                    bounds={"x": 180.0, "y": 170.0, "width": 560.0, "height": 0.0},
                ),
                VectorSegment(
                    id="src_dense_p1:drop",
                    kind="line",
                    points=[{"x": 740.0, "y": 170.0}, {"x": 740.0, "y": 520.0}],
                    bounds={"x": 740.0, "y": 170.0, "width": 0.0, "height": 350.0},
                ),
            ]
        )
        page = PageEvidence(
            id="src_dense_p1",
            sourceFileId="src_dense",
            page=1,
            width=1200.0,
            height=900.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 1200.0, "height": 900.0},
            textSpans=[
                TextSpan('12"-HHWS-CS02', 210.0, 148.0, 130.0, 16.0),
                TextSpan("R-HHW-P-01", 680.0, 530.0, 110.0, 16.0),
            ],
            vectorCount=len(vectors),
            vectorSegments=vectors,
        )
        color_map = discover_system_color_map([page], [], {"src_dense": "/packages/Mech Package.pdf"})

        graph = build_pid_relationship_graph("project_graph_dense", [page], [], [], {"src_dense": "/packages/Mech Package.pdf"}, color_map)

        pump = next(node for node in graph.nodes if node.tag == "R-HHW-P-01")
        edge = next(edge for edge in graph.edges if edge.kind == "attached_to_line" and edge.sourceId == pump.id)
        self.assertEqual(edge.metadata["source"], "system_context_fallback")

    def _page(self, page_id: str, source_id: str, spans: list[TextSpan]) -> PageEvidence:
        return PageEvidence(
            id=page_id,
            sourceFileId=source_id,
            page=1,
            width=1200.0,
            height=800.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 1200.0, "height": 800.0},
            textSpans=spans,
            vectorCount=1,
            vectorSegments=[
                VectorSegment(
                    id=f"{page_id}:line",
                    kind="line",
                    points=[{"x": 180.0, "y": 320.0}, {"x": 800.0, "y": 320.0}],
                    bounds={"x": 180.0, "y": 320.0, "width": 620.0, "height": 0.0},
                )
            ],
        )

    def _candidate(self, candidate_id: str, source_id: str, line_tag: str, sheet_ref: str, direction: str) -> ContinuationCandidate:
        return ContinuationCandidate(
            id=candidate_id,
            sourceFileId=source_id,
            page=1,
            sheetRef=sheet_ref,
            direction=direction,
            label=f"{direction.upper()} {line_tag} {sheet_ref}",
            lineTag=line_tag,
            system="HHWR",
            edge="right" if direction == "to" else "left",
            position={"x": 960.0, "y": 320.0},
            bounds={"x": 900.0, "y": 304.0, "width": 112.0, "height": 32.0},
            confidence=0.9,
            evidenceText=f"{direction.upper()} {line_tag} {sheet_ref}",
        )


def graph_node(graph, node_id):
    return next(node for node in graph.nodes if node.id == node_id)


if __name__ == "__main__":
    unittest.main()
