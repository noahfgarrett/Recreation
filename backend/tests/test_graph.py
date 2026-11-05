import unittest

from recreation_extractor.extraction import detect_from_pages, PageExtraction
from recreation_extractor.graph import build_graph


class GraphTests(unittest.TestCase):
    def test_builds_nodes_and_review_items_from_page_text(self):
        page = PageExtraction(
            id="src_a_p1",
            sourceFileId="src_a",
            page=1,
            width=1000,
            height=700,
            text="P-101A XV-101 PT-101 LEGEND TO PID-002",
            words=[
                {"text": "P-101A", "x": 10, "y": 20, "width": 40, "height": 12},
                {"text": "XV-101", "x": 90, "y": 20, "width": 40, "height": 12},
                {"text": "PT-101", "x": 170, "y": 20, "width": 40, "height": 12},
                {"text": "LEGEND", "x": 10, "y": 80, "width": 60, "height": 12},
                {"text": "TO", "x": 10, "y": 120, "width": 20, "height": 12},
                {"text": "PID-002", "x": 35, "y": 120, "width": 60, "height": 12},
            ],
            vectorCount=10,
            rasterized=False,
        )
        graph = build_graph("project_a", detect_from_pages([page]))
        self.assertGreaterEqual(len(graph.nodes), 3)
        self.assertGreaterEqual(len(graph.edges), 1)
        self.assertTrue(any(item.type == "symbol_confirmation" for item in graph.reviewItems))


if __name__ == "__main__":
    unittest.main()
