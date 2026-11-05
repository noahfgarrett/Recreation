import unittest

from recreation_extractor.pid_stitch.models import DrawingObject, DrawingStyle
from recreation_extractor.pid_stitch.visio_template import style_profile_from_objects


class PidStitchVisioStyleProfileTests(unittest.TestCase):
    def test_style_profile_extracts_dominant_line_colors_and_legend_hints(self):
        objects = [
            self._pipe("chw", "#2563eb", '12"-CHWS-CS02'),
            self._pipe("cw", "#7c3aed", '8"-CWS-CS01'),
            self._pipe("hrw", "#ea580c", '10"-HRW-CS03'),
            self._pipe("chw_2", "#2563eb", '6"-CHWR-CS04'),
            self._label("legend_chw", "CHW / TCHW", "#111827"),
            self._label("legend_cw", "CW", "#111827"),
            self._label("legend_hrw", "HRW", "#111827"),
            self._region("zone", 200.0, 150.0),
        ]

        profile = style_profile_from_objects("reference.vsdx", objects)

        self.assertEqual(profile.path, "reference.vsdx")
        self.assertEqual(profile.dominantLineColors[0], "#2563eb")
        self.assertIn("#7c3aed", profile.dominantLineColors)
        self.assertIn("#ea580c", profile.dominantLineColors)
        self.assertIn("CHW", profile.legendSystems)
        self.assertIn("TCHW", profile.legendSystems)
        self.assertIn("CW", profile.legendSystems)
        self.assertIn("HRW", profile.legendSystems)
        self.assertEqual(profile.lineWeights, [1.2])
        self.assertEqual(profile.zoneLikeObjects, 1)
        self.assertEqual(profile.objectCount, len(objects))

    def test_legend_detection_uses_boundaries_for_overlapping_codes(self):
        tchw_profile = style_profile_from_objects("reference.vsdx", [self._label("legend_tchw", "TCHW", "#111827")])
        combined_profile = style_profile_from_objects("reference.vsdx", [self._label("legend_chw_tchw", "CHW / TCHW", "#111827")])

        self.assertIn("TCHW", tchw_profile.legendSystems)
        self.assertNotIn("CHW", tchw_profile.legendSystems)
        self.assertIn("CHW", combined_profile.legendSystems)
        self.assertIn("TCHW", combined_profile.legendSystems)

    def test_pointer_like_count_excludes_regular_right_oriented_symbols(self):
        objects = [
            self._symbol("pump", "P-101", {"symbolType": "pump", "orientation": "right"}),
            self._symbol("offpage", "TO SHEET M-102", {"symbolType": "offpage", "orientation": "right"}),
        ]

        profile = style_profile_from_objects("reference.vsdx", objects)

        self.assertEqual(profile.pointerLikeObjects, 1)

    def test_pointer_like_count_ignores_off_sheet_notes(self):
        objects = [
            self._label("note", "OFF-SHEET REFERENCES REQUIRE FIELD REVIEW", "#111827"),
            self._symbol("offpage", "", {"symbolType": "offpage", "orientation": "left"}),
        ]

        profile = style_profile_from_objects("reference.vsdx", objects)

        self.assertEqual(profile.pointerLikeObjects, 1)

    def test_pointer_like_count_uses_visio_master_for_non_symbol_objects(self):
        objects = [
            self._label("offpage_label", "", "#111827", {"visioMaster": "Off-page reference"}),
            self._region("continuation_region", 24.0, 12.0, {"visioMaster": "Continuation callout"}),
            self._label("note", "OFF-SHEET REFERENCES REQUIRE FIELD REVIEW", "#111827"),
        ]

        profile = style_profile_from_objects("reference.vsdx", objects)

        self.assertEqual(profile.pointerLikeObjects, 2)

    def _pipe(self, object_id, color, label):
        return DrawingObject(
            id=object_id,
            kind="pipe",
            label=label,
            points=[{"x": 0.0, "y": 0.0}, {"x": 100.0, "y": 0.0}],
            bounds={"x": 0.0, "y": 0.0, "width": 100.0, "height": 2.0},
            style=DrawingStyle(stroke=color, fill="none", strokeWidth=1.2),
            sourceEvidenceIds=[],
        )

    def _label(self, object_id, label, color, metadata=None):
        return DrawingObject(
            id=object_id,
            kind="label",
            label=label,
            points=[{"x": 0.0, "y": 0.0}],
            bounds={"x": 0.0, "y": 0.0, "width": 80.0, "height": 12.0},
            style=DrawingStyle(stroke=color, fill="#ffffff", strokeWidth=0.5),
            sourceEvidenceIds=[],
            metadata=metadata or {},
        )

    def _region(self, object_id, width, height, metadata=None):
        return DrawingObject(
            id=object_id,
            kind="region",
            label="",
            points=[{"x": 0.0, "y": 0.0}, {"x": width, "y": height}],
            bounds={"x": 0.0, "y": 0.0, "width": width, "height": height},
            style=DrawingStyle(stroke="#111827", fill="#e5e7eb", strokeWidth=0.5),
            sourceEvidenceIds=[],
            metadata=metadata or {},
        )

    def _symbol(self, object_id, label, metadata):
        return DrawingObject(
            id=object_id,
            kind="symbol",
            label=label,
            points=[{"x": 0.0, "y": 0.0}, {"x": 24.0, "y": 24.0}],
            bounds={"x": 0.0, "y": 0.0, "width": 24.0, "height": 24.0},
            style=DrawingStyle(stroke="#111827", fill="#ffffff", strokeWidth=0.8),
            sourceEvidenceIds=[],
            metadata=metadata,
        )


if __name__ == "__main__":
    unittest.main()
