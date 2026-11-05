from __future__ import annotations

import unittest
from unittest.mock import patch

from recreation_extractor.hierarchy.dependency_rules import build_dependency_graph, is_dependency_equipment_tag
from recreation_extractor.hierarchy.extraction import build_hierarchy_document
from recreation_extractor.pid_stitch.electrical_graph import ElectricalGraphEdge, ElectricalGraphNode, ElectricalRelationshipGraph
from recreation_extractor.pid_stitch.models import PageEvidence
from recreation_extractor.pid_stitch.semantic_graph import PidGraphNode, PidRelationshipGraph


class HierarchyDependencyGraphTest(unittest.TestCase):
    def test_pump_depends_on_upstream_distribution_from_electrical_graph(self) -> None:
        graph = build_dependency_graph("project_dep", _semantic_graph(), _electrical_graph())

        edge_index = {(edge.sourceTag, edge.targetTag, edge.kind): edge for edge in graph.edges}

        self.assertIn(("RW4PP1E4", "R-CW-P-03", "requires_power"), edge_index)
        self.assertIn(("RW4MDP4C6", "R-CW-P-03", "requires_upstream_distribution"), edge_index)
        self.assertEqual(edge_index[("RW4PP1E4", "R-CW-P-03", "requires_power")].status, "confirmed")
        self.assertEqual(edge_index[("RW4MDP4C6", "R-CW-P-03", "requires_upstream_distribution")].status, "confirmed")

    def test_pump_depends_on_drive_motor_and_controls_by_real_tag_matching(self) -> None:
        graph = build_dependency_graph("project_dep", _semantic_graph(), _electrical_graph())

        edge_index = {(edge.sourceTag, edge.targetTag, edge.kind): edge for edge in graph.edges}

        self.assertIn(("VFD-R-CW-P-03", "R-CW-P-03", "requires_drive"), edge_index)
        self.assertIn(("R-CW-P-03-MTR", "R-CW-P-03", "requires_motor"), edge_index)
        self.assertIn(("BAS-CP-01", "R-CW-P-03", "requires_control_panel"), edge_index)
        self.assertIn(("PIT-R-CW-P-03", "R-CW-P-03", "requires_instrument"), edge_index)
        self.assertEqual(edge_index[("VFD-R-CW-P-03", "R-CW-P-03", "requires_drive")].status, "inferred")
        self.assertEqual(edge_index[("R-CW-P-03-MTR", "R-CW-P-03", "requires_motor")].status, "inferred")
        self.assertEqual(edge_index[("PIT-R-CW-P-03", "R-CW-P-03", "requires_instrument")].metadata["sourceDiscipline"], "Instrumentation & Control")

    def test_missing_expected_vfd_dependencies_create_qa_warnings_without_fake_nodes(self) -> None:
        graph = build_dependency_graph(
            "project_dep",
            _semantic_graph(include_driven=False, include_motor=False, include_control=False, include_instrument=False),
            _electrical_graph(),
        )

        tags = {node.tag for node in graph.nodes}
        warning_text = " ".join(item.get("message", "") for item in graph.qa.get("reviewItems", []))

        self.assertNotIn("MOTOR", tags)
        self.assertNotIn("CONTROL SOURCE", tags)
        self.assertNotIn("power", tags)
        self.assertIn("Expected driven equipment not found for VFD-R-CW-P-03", warning_text)
        self.assertIn("Expected control source not found for VFD-R-CW-P-03", warning_text)

    def test_dependency_equipment_tag_filter_suppresses_non_asset_annotations(self) -> None:
        accepted = [
            ("RW4MDP4C6", "equipment", {}),
            ("GEN-15", "equipment", {}),
            ("VFD-R-CW-P-03", "equipment", {}),
            ("R-CW-P-03", "equipment", {}),
            ("R-CW-P-03-MTR", "equipment", {}),
            ("BAS-CP-01", "equipment", {"equipmentClass": "control_panel"}),
        ]
        rejected = [
            ("480V", "equipment", {}),
            ("1200A", "equipment", {}),
            ("50/51", "device", {}),
            ("DEMO-EE-4101", "equipment", {}),
            ("5000A 'SWING' BUS", "line_tag", {}),
            ("power", "equipment", {}),
            ("feedback", "instrument", {}),
            ("ROOM 301", "equipment", {}),
        ]

        for tag, kind, metadata in accepted:
            with self.subTest(tag=tag):
                self.assertTrue(is_dependency_equipment_tag(tag, kind, metadata))
        for tag, kind, metadata in rejected:
            with self.subTest(tag=tag):
                self.assertFalse(is_dependency_equipment_tag(tag, kind, metadata))

    def test_duplicate_dependencies_merge_into_one_edge(self) -> None:
        graph = build_dependency_graph("project_dep", _semantic_graph(), _electrical_graph(include_duplicate_panel_edge=True))

        panel_edges = [
            edge
            for edge in graph.edges
            if edge.sourceTag == "RW4PP1E4"
            and edge.targetTag == "R-CW-P-03"
            and edge.kind == "requires_power"
        ]

        self.assertEqual(len(panel_edges), 1)
        self.assertEqual(panel_edges[0].sourceEvidenceIds, ["ev:vfd", "ev:panel", "ev:panel-duplicate"])

    def test_dependency_graph_appears_as_separate_hierarchy_view(self) -> None:
        semantic_graph = _semantic_graph()
        electrical_graph = _electrical_graph()
        with (
            patch("recreation_extractor.hierarchy.extraction.build_pid_relationship_graph", return_value=semantic_graph),
            patch("recreation_extractor.hierarchy.extraction.build_electrical_relationship_graph", return_value=electrical_graph),
        ):
            document = build_hierarchy_document(
                "project_dep",
                [_page("page_1", "source_elec", 1)],
                [],
                [],
                {"source_elec": "/uploads/Electrical.pdf"},
            )

        dependency_graph = document.visualQa["dependencyGraph"]
        dependency_view = next(view for view in document.visualQa["hierarchyViews"] if view["id"] == "commissioning_dependencies")

        self.assertEqual(dependency_graph["nodes"][0]["tag"], "R-CW-P-03")
        self.assertEqual(dependency_view["label"], "Dependency View")
        self.assertEqual(dependency_view["sourceGraph"], "dependencyGraph")
        self.assertEqual(dependency_view["nodes"], dependency_graph["nodes"])
        self.assertEqual(dependency_view["edges"], dependency_graph["edges"])

    def test_stitch_layout_options_carry_the_dependency_view(self) -> None:
        # The stitch job (generate_layout_options) is what the app runs, so the view has to be built there too.
        from recreation_extractor.pid_stitch.layout import generate_layout_options

        with (
            patch("recreation_extractor.pid_stitch.layout.build_pid_relationship_graph", return_value=_semantic_graph()),
            patch("recreation_extractor.pid_stitch.layout.build_electrical_relationship_graph", return_value=_electrical_graph()),
        ):
            options = generate_layout_options("project_dep", [_page("page_1", "source_elec", 1)], [], [], {"source_elec": "/uploads/Electrical.pdf"})

        self.assertTrue(options)
        for _option, document in options:
            view = next(view for view in document.visualQa["hierarchyViews"] if view["id"] == "commissioning_dependencies")
            self.assertEqual(view["nodes"][0]["tag"], "R-CW-P-03")
            self.assertTrue(view["edges"])

    def test_dependency_export_contains_real_equipment_id_rows_only(self) -> None:
        graph = build_dependency_graph("project_dep", _semantic_graph(), _electrical_graph())

        rows = graph.to_export_rows()
        depends_on_tags = {row["Depends On Equipment Tag"] for row in rows}
        exported_text = " ".join(str(value) for row in rows for value in row.values())

        self.assertEqual({row["Target Equipment Tag"] for row in rows}, {"R-CW-P-03"})
        self.assertEqual(
            depends_on_tags,
            {"VFD-R-CW-P-03", "RW4PP1E4", "RW4MDP4C6", "R-CW-P-03-MTR", "BAS-CP-01", "PIT-R-CW-P-03"},
        )
        self.assertIn("Target Discipline", rows[0])
        self.assertEqual(rows[0]["Target Discipline"], "Mechanical")
        self.assertIn("Dependency Discipline", rows[0])
        self.assertIn("Dependency Path", rows[0])
        self.assertIn("Commissioning Use", rows[0])
        self.assertNotIn("480V", exported_text)
        self.assertNotIn("1200A", exported_text)
        self.assertNotIn("50/51", exported_text)
        self.assertNotIn("DEMO-EE-4101", exported_text)
        self.assertNotIn("SWING BUS", exported_text)


def _electrical_graph(*, include_duplicate_panel_edge: bool = False) -> ElectricalRelationshipGraph:
    nodes = [
        _electrical_node("vfd", "equipment", "VFD-R-CW-P-03", "vfd", evidence=["ev:vfd"]),
        _electrical_node("panel", "equipment", "RW4PP1E4", "panel", evidence=["ev:panel"]),
        _electrical_node("mdp", "equipment", "RW4MDP4C6", "main_distribution_panel", evidence=["ev:mdp"]),
        _electrical_node("voltage", "device", "480V", "", evidence=["ev:voltage"]),
        _electrical_node("amps", "device", "1200A", "", evidence=["ev:amps"]),
        _electrical_node("relay", "device", "50/51", "", evidence=["ev:relay"]),
        _electrical_node("sheet", "equipment", "DEMO-EE-4101", "", evidence=["ev:sheet"]),
        _electrical_node("bus", "line_tag", "5000A 'SWING' BUS", "", evidence=["ev:bus"]),
    ]
    edges = [
        ElectricalGraphEdge(
            id="edge_vfd_panel",
            kind="panel_schedule_feeds",
            sourceId="vfd",
            targetId="panel",
            label="RW4PP1E4",
            lineTag="",
            system="ELEC",
            sourceEvidenceIds=["ev:vfd", "ev:panel"],
            confidence=0.94,
            status="confirmed",
            metadata={"source": "panel_schedule"},
        ),
        ElectricalGraphEdge(
            id="edge_panel_mdp",
            kind="panel_schedule_feeds",
            sourceId="panel",
            targetId="mdp",
            label="RW4MDP4C6",
            lineTag="",
            system="ELEC",
            sourceEvidenceIds=["ev:panel", "ev:mdp"],
            confidence=0.96,
            status="confirmed",
            metadata={"source": "panel_schedule"},
        ),
    ]
    if include_duplicate_panel_edge:
        edges.append(
            ElectricalGraphEdge(
                id="edge_vfd_panel_duplicate",
                kind="panel_schedule_feeds",
                sourceId="vfd",
                targetId="panel",
                label="RW4PP1E4",
                lineTag="",
                system="ELEC",
                sourceEvidenceIds=["ev:panel-duplicate"],
                confidence=0.84,
                status="inferred",
                metadata={"source": "panel_schedule"},
            )
        )
    return ElectricalRelationshipGraph(projectId="project_dep", nodes=nodes, edges=edges, metrics={}, qa={})


def _semantic_graph(
    *,
    include_driven: bool = True,
    include_motor: bool = True,
    include_control: bool = True,
    include_instrument: bool = True,
) -> PidRelationshipGraph:
    nodes = []
    if include_driven:
        nodes.append(_pid_node("pump", "equipment", "R-CW-P-03", "CW", {"equipmentDescription": "Condenser water pump"}))
    if include_motor:
        nodes.append(_pid_node("motor", "equipment", "R-CW-P-03-MTR", "CW", {"equipmentDescription": "Pump motor"}))
    if include_control:
        nodes.append(
            _pid_node(
                "bas_cp",
                "equipment",
                "BAS-CP-01",
                "BAS",
                {"equipmentClass": "control_panel", "equipmentDescription": "BAS control panel", "discipline": "Controls / BAS"},
            )
        )
    if include_instrument:
        nodes.append(
            _pid_node(
                "pit_cwp_03",
                "instrument",
                "PIT-R-CW-P-03",
                "I&C",
                {
                    "equipmentDescription": "Pump discharge pressure transmitter",
                    "discipline": "Instrumentation & Control",
                    "requiredForOperation": True,
                    "controlledEquipmentTag": "R-CW-P-03",
                },
            )
        )
    return PidRelationshipGraph(projectId="project_dep", nodes=nodes, edges=[], metrics={}, qa={})


def _electrical_node(
    node_id: str,
    kind: str,
    tag: str,
    equipment_class: str,
    *,
    evidence: list[str],
) -> ElectricalGraphNode:
    metadata = {"discipline": "Electrical", "sourcePath": "/uploads/Electrical.pdf"}
    if equipment_class:
        metadata["equipmentClass"] = equipment_class
    return ElectricalGraphNode(
        id=node_id,
        kind=kind,  # type: ignore[arg-type]
        tag=tag,
        system="ELEC",
        sourceFileId="source_elec",
        sourcePageId="page_1",
        page=1,
        bounds={"x": 10.0, "y": 20.0, "width": 80.0, "height": 16.0},
        sourceEvidenceIds=evidence,
        confidence=0.9,
        metadata=metadata,
    )


def _pid_node(node_id: str, kind: str, tag: str, system: str, metadata: dict[str, object]) -> PidGraphNode:
    return PidGraphNode(
        id=node_id,
        kind=kind,  # type: ignore[arg-type]
        tag=tag,
        system=system,
        sourceFileId="source_mech",
        sourcePageId="page_2",
        page=2,
        bounds={"x": 30.0, "y": 40.0, "width": 90.0, "height": 18.0},
        sourceEvidenceIds=[f"ev:{node_id}"],
        confidence=0.88,
        metadata={"sourcePath": "/uploads/Mechanical.pdf", **metadata},
    )


def _page(page_id: str, source_file_id: str, page: int) -> PageEvidence:
    return PageEvidence(
        id=page_id,
        sourceFileId=source_file_id,
        page=page,
        width=1200.0,
        height=800.0,
        rotation=0,
        cropBounds={"x": 0.0, "y": 0.0, "width": 1200.0, "height": 800.0},
        textSpans=[],
        vectorCount=0,
        vectorSegments=[],
    )


if __name__ == "__main__":
    unittest.main()
