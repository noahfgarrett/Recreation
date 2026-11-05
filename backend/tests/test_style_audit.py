import importlib.util
import os
import subprocess
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "style-audit.py"
REPO_ROOT = SCRIPT_PATH.parents[1]


def load_script():
    spec = importlib.util.spec_from_file_location("style_audit", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class StyleAuditTests(unittest.TestCase):
    def test_cli_help_runs_without_pythonpath(self):
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)

        result = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--help"],
            cwd=REPO_ROOT,
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--groups-dir", result.stdout)

    def test_summarizes_detected_systems_and_missing_tags(self):
        audit = load_script()
        drawing = {
            "objects": [
                {"kind": "label", "label": '12"-CHWS-CS02'},
                {"kind": "label", "label": "R-DEMO-CHW-P-01"},
                {"kind": "pipe", "style": {"stroke": "#0070c0"}, "metadata": {"system": "CHW"}},
                {"kind": "region", "metadata": {"stitchedSourcePageTile": True}},
            ],
            "sourcePages": [
                {
                    "textSpans": [
                        {"text": '12"-CHWS-CS02'},
                        {"text": "R-DEMO-CHW-P-01"},
                        {"text": "PIT-101"},
                    ]
                }
            ],
        }

        summary = audit.summarize_drawing("sample", drawing, [])

        self.assertEqual(summary["detectedSystems"], ["CHW"])
        self.assertEqual(summary["hiddenFrames"], 1)
        self.assertEqual(summary["missingTags"], 1)
        self.assertEqual(summary["missingSample"], ["PIT-101"])
        self.assertEqual(summary["hiddenInventoryTags"], 0)

    def test_hidden_inventory_does_not_count_as_visible_tag_coverage(self):
        audit = load_script()
        drawing = {
            "objects": [
                {
                    "kind": "region",
                    "label": "",
                    "bounds": {"x": 0, "y": 0, "width": 1, "height": 1},
                    "style": {"opacity": 0},
                    "metadata": {
                        "sourceCoverage": True,
                        "sourceCoverageRole": "instrumentInventory",
                        "instrumentTags": "PIT-101 FIT-202",
                    },
                }
            ],
            "sourcePages": [{"textSpans": [{"text": "PIT-101 FIT-202"}]}],
        }

        summary = audit.summarize_drawing("sample", drawing, [])

        self.assertEqual(summary["missingTags"], 2)
        self.assertEqual(summary["hiddenInventoryTags"], 2)
        self.assertEqual(summary["hiddenInventorySample"], ["PIT-101", "FIT-202"])

    def test_source_tag_scan_does_not_treat_prose_at_pressure_as_instrument_tag(self):
        audit = load_script()

        prose_tags = audit._source_tags(
            [
                {
                    "textSpans": [
                        {"text": "Water supply pressure to be maintained at 70 psi per"},
                    ]
                }
            ]
        )
        explicit_tags = audit._source_tags(
            [
                {
                    "textSpans": [
                        {"text": "AT-70"},
                    ]
                }
            ]
        )

        self.assertEqual(prose_tags, [])
        self.assertEqual(explicit_tags, ["AT-70"])

    def test_svg_output_dir_tracks_json_output_path(self):
        audit = load_script()

        self.assertEqual(
            audit._svg_output_dir_for(Path("/tmp/recreation-audit/report.json")),
            Path("/tmp/recreation-audit/report"),
        )

    def test_style_profile_match_reports_color_details(self):
        audit = load_script()
        profile = SimpleNamespace(
            path="reference.vsdx",
            dominantLineColors=["#0070c0", "#7030a0", "#ea700d"],
            legendSystems=["CHW", "CW", "HRW"],
            lineWeights=[1.5],
            pointerLikeObjects=0,
            zoneLikeObjects=2,
            objectCount=12,
        )

        matches = audit._style_profile_matches(["#0070c0", "#ff0000"], [profile])

        self.assertEqual(matches[0]["lineColorOverlap"], 1)
        self.assertEqual(matches[0]["lineColorOverlapRatio"], 0.333)
        self.assertEqual(matches[0]["matchedLineColors"], ["#0070c0"])
        self.assertEqual(matches[0]["missingReferenceColors"], ["#7030a0", "#ea700d"])

    def test_summarizes_similarity_qa_metrics(self):
        audit = load_script()
        profile = SimpleNamespace(
            path="reference.vsdx",
            dominantLineColors=["#0070c0", "#ff0000", "#7030a0"],
            legendSystems=["CHW", "HHW"],
            lineWeights=[0.8, 2.0],
            pointerLikeObjects=1,
            zoneLikeObjects=2,
            objectCount=12,
        )
        drawing = {
            "objects": [
                {
                    "kind": "pipe",
                    "label": '10"-CHWS-CS02',
                    "style": {"stroke": "#0070c0", "strokeWidth": 0.8},
                    "metadata": {"sourceDerived": True, "sourceVectorId": "v1", "system": "CHW", "systemColorApplied": True},
                },
                {
                    "kind": "pipe",
                    "style": {"stroke": "#000000", "strokeWidth": 0.8},
                    "metadata": {"sourceDerived": True, "sourceVectorId": "v2", "system": "DEFAULT", "systemColorApplied": False},
                },
                {
                    "kind": "pipe",
                    "style": {"stroke": "#ff0000", "strokeWidth": 0.6},
                    "metadata": {"sourceDerived": True, "sourceVectorId": "v3", "system": "HHW", "systemColorApplied": True},
                },
                {
                    "kind": "pipe",
                    "style": {"stroke": "#0070c0", "strokeWidth": 2.0},
                    "metadata": {"connectorRole": "matchedOffPageContinuation", "system": "CHW"},
                },
                {
                    "kind": "connector",
                    "style": {"stroke": "#ff0000", "strokeWidth": 2.0},
                    "metadata": {"system": "HHW"},
                },
                {"kind": "label", "label": "PIT-101"},
                {
                    "kind": "region",
                    "style": {"opacity": 0},
                    "bounds": {"x": 0, "y": 0, "width": 1, "height": 1},
                    "metadata": {
                        "sourceCoverage": True,
                        "sourceCoverageRole": "instrumentInventory",
                        "instrumentTags": "FIT-202",
                    },
                },
            ],
            "sourcePages": [{"textSpans": [{"text": '10"-CHWS-CS02 PIT-101 FIT-202 AIT-303'}]}],
        }

        summary = audit.summarize_drawing("sample", drawing, [profile])

        self.assertEqual(summary["sourceDerivedPipeVectors"], 3)
        self.assertEqual(summary["sourceDerivedPipeVectorsRecoloredBySystem"], 2)
        self.assertEqual(summary["sourceDerivedPipeVectorsRecoloredBySystemPercent"], 66.667)
        self.assertEqual(summary["dominantConnectorLineWeight"], 2.0)
        self.assertEqual(summary["dominantSourceLineWeight"], 0.8)
        self.assertEqual(summary["connectorToSourceRatio"], 0.667)
        self.assertEqual(summary["hiddenVsVisibleCoverage"]["sourceTags"], 4)
        self.assertEqual(summary["hiddenVsVisibleCoverage"]["visibleCoveredTags"], 2)
        self.assertEqual(summary["hiddenVsVisibleCoverage"]["hiddenInventoryTags"], 1)
        self.assertEqual(summary["hiddenVsVisibleCoverage"]["visibleCoverageRatio"], 0.5)
        self.assertEqual(summary["paletteOverlap"]["referenceColorCount"], 3)
        self.assertEqual(summary["paletteOverlap"]["drawingColorCount"], 3)
        self.assertEqual(summary["paletteOverlap"]["overlapCount"], 2)
        self.assertEqual(summary["paletteOverlap"]["overlapRatio"], 0.667)

    def test_summarizes_colored_source_vector_coverage(self):
        audit = load_script()
        drawing = {
            "objects": [
                {
                    "kind": "pipe",
                    "style": {"stroke": "#0070c0"},
                    "metadata": {
                        "singleSheetReconstructionVector": True,
                        "sourceVectorId": "v1",
                        "system": "CHW",
                        "systemColorApplied": True,
                    },
                },
                {
                    "kind": "pipe",
                    "style": {"stroke": "#111827"},
                    "metadata": {
                        "singleSheetReconstructionVector": True,
                        "sourceVectorId": "v2",
                        "system": "DEFAULT",
                        "systemColorApplied": False,
                    },
                },
                {
                    "kind": "pipe",
                    "style": {"stroke": "#ff0000"},
                    "metadata": {
                        "singleSheetReconstructionVector": True,
                        "sourceVectorId": "v3",
                        "system": "HHWS",
                        "systemColorApplied": True,
                    },
                },
            ],
            "sourcePages": [],
        }

        summary = audit.summarize_drawing("sample", drawing, [])

        self.assertEqual(
            summary["sourceVectorColorCoverage"],
            {
                "colored": 2,
                "total": 3,
                "ratio": 0.667,
                "bySystem": {"CHW": 1, "HHWS": 1},
            },
        )


if __name__ == "__main__":
    unittest.main()
