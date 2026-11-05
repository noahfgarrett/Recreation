import unittest

from recreation_extractor.models import to_dict
from recreation_extractor.pid_stitch.models import (
    DrawingDocument,
    DrawingObject,
    DrawingStyle,
    LayoutOption,
    PageEvidence,
    TextSpan,
)


class PidStitchModelTests(unittest.TestCase):
    def test_drawing_document_serializes_to_camel_compatible_dict(self):
        page = PageEvidence(
            id="src_a_p1",
            sourceFileId="src_a",
            page=1,
            width=3024.0,
            height=2160.0,
            rotation=270,
            cropBounds={"x": 50.0, "y": 40.0, "width": 2860.0, "height": 1900.0},
            textSpans=[TextSpan(text="TO SUPPLY HEADER", x=10.0, y=20.0, width=120.0, height=12.0, rotation=0.0)],
            vectorCount=42,
        )
        document = DrawingDocument(
            id="drawing_a",
            projectId="project_a",
            name="Recommended Combined P&ID",
            width=3456.0,
            height=2592.0,
            objects=[
                DrawingObject(
                    id="pipe_1",
                    kind="pipe",
                    label='16"-CHWS-CS02',
                    points=[{"x": 10.0, "y": 20.0}, {"x": 240.0, "y": 20.0}],
                    bounds={"x": 10.0, "y": 16.0, "width": 230.0, "height": 8.0},
                    style=DrawingStyle(stroke="#111827", strokeWidth=1.2),
                    sourceEvidenceIds=["src_a_p1:span_1"],
                    locked=False,
                    groupId=None,
                )
            ],
            sourcePages=[page],
            styles={"CHWS": DrawingStyle(stroke="#2563eb", strokeWidth=1.4)},
            visualQa={"crossings": 0, "labelOverlaps": 0, "disconnectedContinuations": 0},
        )
        payload = to_dict(document)
        self.assertEqual(payload["id"], "drawing_a")
        self.assertEqual(payload["objects"][0]["kind"], "pipe")
        self.assertEqual(payload["sourcePages"][0]["sourceFileId"], "src_a")
        self.assertEqual(payload["styles"]["CHWS"]["stroke"], "#2563eb")

    def test_layout_option_references_a_drawing_document(self):
        option = LayoutOption(
            id="layout_recommended",
            projectId="project_a",
            drawingId="drawing_a",
            name="Recommended",
            description="Balanced layout with low crossings",
            score=94.0,
            metrics={"crossings": 1, "labelOverlaps": 0, "sourceFaithfulness": 0.72},
        )
        payload = to_dict(option)
        self.assertEqual(payload["drawingId"], "drawing_a")
        self.assertGreater(payload["score"], 90)


if __name__ == "__main__":
    unittest.main()
