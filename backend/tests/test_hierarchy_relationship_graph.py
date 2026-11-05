from __future__ import annotations

import unittest

from recreation_extractor.hierarchy.relationship_graph import normalize_hierarchy_views


class HierarchyRelationshipGraphTest(unittest.TestCase):
    def test_wraps_electrical_graph_as_hierarchy_view(self) -> None:
        electrical = {
            "nodes": [
                {"id": "n1", "tag": "GEN-15", "kind": "equipment", "confidence": 0.94},
                {"id": "n2", "tag": "RW4SWG2F6", "kind": "line_tag", "confidence": 0.94},
            ],
            "edges": [
                {"id": "e1", "source": "n1", "target": "n2", "kind": "attached_to_line", "confidence": 0.94}
            ],
            "metrics": {"roots": 1},
        }

        views = normalize_hierarchy_views({"electricalRelationshipGraph": electrical})

        self.assertEqual(len(views), 1)
        self.assertEqual(views[0]["id"], "electrical_power")
        self.assertEqual(views[0]["discipline"], "Electrical")
        self.assertEqual(views[0]["nodes"][0]["tag"], "GEN-15")

    def test_preserves_existing_shared_views(self) -> None:
        existing = {"hierarchyViews": [{"id": "process_flow", "label": "Process Flow Tree", "discipline": "Process / P&ID", "nodes": [], "edges": [], "metrics": {}}]}

        views = normalize_hierarchy_views(existing)

        self.assertEqual(views[0]["id"], "process_flow")

    def test_line_mounted_item_uses_upstream_line_parent(self) -> None:
        from recreation_extractor.hierarchy.relationship_graph import line_mounted_parent_id

        line = {
            "id": "line_101",
            "sourceEquipmentId": "pump_101",
            "targetEquipmentId": "tank_101",
            "flowDirection": "source_to_target",
        }
        instrument = {"id": "ft_101", "attachedLineId": "line_101"}

        self.assertEqual(line_mounted_parent_id(line, instrument), "line_101")
        self.assertEqual(line_mounted_parent_id(line, instrument, hide_line_nodes=True), "pump_101")

    def test_line_mounted_item_requires_non_empty_line_match(self) -> None:
        from recreation_extractor.hierarchy.relationship_graph import line_mounted_parent_id

        self.assertIsNone(line_mounted_parent_id({"sourceEquipmentId": "pump_101"}, {}, hide_line_nodes=True))
        self.assertIsNone(line_mounted_parent_id({"id": "", "sourceEquipmentId": "pump_101"}, {"attachedLineId": ""}, hide_line_nodes=True))
