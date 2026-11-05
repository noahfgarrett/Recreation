import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from xml.etree import ElementTree

from recreation_extractor.pid_stitch.export import export_drawing_pdf, export_drawing_svg
from recreation_extractor.pid_stitch.models import LayoutOption
from recreation_extractor.service import RecreationService


class PidStitchExportTests(unittest.TestCase):
    def test_svg_export_renders_structured_drawing_primitives(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "drawing.svg"

            path = export_drawing_svg(self._document(), output_path)

            self.assertEqual(path, output_path)
            svg = output_path.read_text(encoding="utf-8")
            self.assertIn("<svg", svg)
            self.assertIn('viewBox="0 0 420.0 260.0"', svg)
            self.assertIn("<polyline", svg)
            self.assertIn('stroke-dasharray="8 4"', svg)
            self.assertIn("SAFE LABEL", svg)
            self.assertIn("5 &lt; 7 &amp; &quot;risky&quot;", svg)
            self.assertIn("Source p1", svg)
            self.assertIn("Zone", svg)
            self.assertIn("<rect", svg)
            self.assertIn('data-kind="region"', svg)
            self.assertIn('data-kind="source_fragment"', svg)

    def test_svg_export_parses_with_risky_and_control_character_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "drawing.svg"
            document = self._document()
            document["objects"].append(
                {
                    "id": "bad\x01id",
                    "kind": "label",
                    "label": 'Risk <>& "\x01 text',
                    "points": [{"x": 28.0, "y": 238.0}],
                    "style": {"fill": "#111827"},
                }
            )

            export_drawing_svg(document, output_path)

            svg = output_path.read_text(encoding="utf-8")
            ElementTree.fromstring(svg)
            self.assertIn("Risk &lt;&gt;&amp; &quot; text", svg)
            self.assertNotIn("\x01", svg)

    def test_svg_export_uses_vector_pack_for_expanded_symbols(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "drawing.svg"
            document = self._document()
            symbol_types = [
                "air_handler",
                "boiler",
                "check_valve",
                "chiller",
                "coil",
                "compressor",
                "control_valve",
                "cooling_tower",
                "covered_tank",
                "control_panel",
                "computer_monitor",
                "centrifugal_fan",
                "centrifugal_pump",
                "circuit_breaker",
                "closed_tank",
                "dashpot_piston",
                "disconnect_switch",
                "drive",
                "dryer",
                "ejector",
                "expansion_bellows",
                "equipment",
                "fan",
                "filter",
                "flame_arrester",
                "flow_arrow",
                "flow_controller",
                "flow_element",
                "flow_indicator",
                "flow_meter",
                "gate_valve",
                "gauge",
                "heat_exchanger",
                "hand_switch",
                "handwheel_actuator",
                "hopper",
                "horizontal_vessel",
                "instrument",
                "knife_gate_valve",
                "level_controller",
                "level_element",
                "line_blind",
                "motor",
                "normally_open_valve",
                "normally_closed_valve",
                "offpage",
                "open_tank",
                "orifice_plate",
                "panel",
                "panel_instrument",
                "patch_panel",
                "pipe_anchor",
                "pid_electric_binary",
                "pid_electromagnetic",
                "pid_heated_cooled",
                "pid_pneumatic_binary",
                "pipe_break",
                "plate_heat_exchanger",
                "plc",
                "pneumatic_actuator",
                "position_switch",
                "powered_valve",
                "pressure_controller",
                "pressure_element",
                "pressure_regulator",
                "pump",
                "reducer",
                "concentric_reducer",
                "eccentric_reducer",
                "relief_valve",
                "pressure_relief_valve",
                "pressure_sensor",
                "reference_circle",
                "relief_angle_valve",
                "rupture_disk",
                "sample_point",
                "separator",
                "skid",
                "sight_glass",
                "silencer",
                "spectacle_blind",
                "spray_nozzle",
                "strainer",
                "tank",
                "tee",
                "temperature_controller",
                "temperature_element",
                "terminal_unit",
                "terminal_block",
                "transformer",
                "union",
                "valve",
                "vent",
                "vessel",
                "vertical_vessel",
                "vfd",
                "tag_circle",
                "tag_square",
                "backpressure_valve",
                "balancing_valve",
                "cross",
                "double_check_valve",
                "elbow",
                "electric_actuator",
                "expansion_loop",
                "fail_closed_valve",
                "fail_open_valve",
                "flexible_hose",
                "lcd_monitor",
                "y_strainer",
                "differential_pressure_transmitter",
                "pressure_switch",
                "temperature_switch",
                "flow_switch",
                "level_switch",
                "recorder",
                "alarm",
                "indicator_light",
                "pinch_valve",
                "piston_valve",
                "float_valve",
                "safety_valve",
                "vacuum_breaker",
                "foot_valve",
                "bag_filter",
                "cartridge_filter",
                "centrifugal_separator",
                "tank_mixer",
                "chemical_tote",
                "drum",
                "conveyor",
                "scale",
                "damper",
                "duct_transition",
                "fuse",
                "relay",
                "contactor",
                "motor_starter",
                "panelboard",
                "ground",
                "cable_tray",
                "ups",
                "basket_strainer",
                "duplex_strainer",
                "temporary_strainer",
                "static_mixer",
                "inline_mixer",
                "injection_quill",
                "sample_probe",
                "calibration_column",
                "open_drain",
                "closed_drain",
                "floor_drain",
                "cleanout",
                "hose_bib",
                "quick_connect",
                "pipe_support",
                "guide_support",
                "spring_hanger",
                "vent_silencer",
                "relief_stack",
                "flame_detector",
                "gas_detector",
                "smoke_detector",
                "safety_shower",
                "eyewash",
                "fire_damper",
                "duct_filter",
                "duct_coil",
                "vav_box",
                "junction_box",
                "pull_box",
                "control_station",
                "network_switch",
            ]
            document["objects"] = [self._symbol(f"symbol_{index}", symbol_type.upper(), symbol_type, 24.0 + index * 56.0) for index, symbol_type in enumerate(symbol_types)]

            export_drawing_svg(document, output_path)

            svg = output_path.read_text(encoding="utf-8")
            ElementTree.fromstring(svg)
            self.assertIn('data-symbol-registry="recreation-vector-pack"', svg)
            for symbol_type in symbol_types:
                self.assertIn(f'data-symbol-type="{symbol_type}"', svg)
            self.assertGreaterEqual(svg.count("<path"), 3)

    def test_malformed_styles_and_points_do_not_crash_or_emit_bad_svg_points(self):
        try:
            import reportlab  # noqa: F401
        except Exception as exc:
            self.skipTest(f"reportlab unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            document = self._malformed_document()

            export_drawing_svg(document, tmp_path / "drawing.svg")
            export_drawing_pdf(document, tmp_path / "drawing.pdf")

            svg = (tmp_path / "drawing.svg").read_text(encoding="utf-8")
            ElementTree.fromstring(svg)
            self.assertIn("<polyline", svg)
            self.assertIn("10.0,10.0 20.0,20.0", svg)
            self.assertNotIn("nan", svg.lower())
            self.assertNotIn("inf", svg.lower())
            self.assertNotIn("stroke-dasharray", svg)
            self.assertTrue((tmp_path / "drawing.pdf").exists())
            self.assertGreater((tmp_path / "drawing.pdf").stat().st_size, 500)

    def test_pdf_export_creates_nontrivial_file(self):
        try:
            import reportlab  # noqa: F401
        except Exception as exc:
            self.skipTest(f"reportlab unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            output_path = Path(tmp) / "drawing.pdf"

            path = export_drawing_pdf(self._document(), output_path)

            self.assertEqual(path, output_path)
            self.assertTrue(output_path.exists())
            self.assertGreater(output_path.stat().st_size, 500)

    def test_service_and_api_export_stored_drawing_and_reject_bad_type(self):
        try:
            from fastapi import HTTPException
            from recreation_extractor.app import CreateProjectRequest, create_app
        except Exception as exc:
            self.skipTest(f"FastAPI dependencies unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            data_dir = Path(tmp) / "data"
            service = RecreationService(data_dir)
            project = service.create_project("Drawing export")
            drawing_id = "drawing_test"
            service.store.replace_drawing_options(
                project.id,
                [(self._layout_option(project.id, drawing_id), self._document(project.id, drawing_id))],
            )

            result = service.export_drawing(project.id, drawing_id, "svg")

            self.assertEqual(
                set(result),
                {"projectId", "drawingId", "type", "path"},
            )
            self.assertEqual(result["projectId"], project.id)
            self.assertEqual(result["drawingId"], drawing_id)
            self.assertEqual(result["type"], "svg")
            self.assertTrue(Path(result["path"]).exists())
            self.assertEqual(self._latest_export_type(data_dir), "drawing_svg")

            app = create_app(data_dir)
            create_project = self._route(app, "/projects", "POST")
            export_drawing = self._route(
                app,
                "/projects/{project_id}/drawings/{drawing_id}/exports/{export_type}",
                "POST",
            )
            api_project = create_project(CreateProjectRequest(name="API drawing export"))
            api_drawing_id = "drawing_api_test"
            service.store.replace_drawing_options(
                api_project["id"],
                [
                    (
                        self._layout_option(api_project["id"], api_drawing_id),
                        self._document(api_project["id"], api_drawing_id),
                    )
                ],
            )

            api_result = export_drawing(api_project["id"], api_drawing_id, "pdf")

            self.assertEqual(api_result["projectId"], api_project["id"])
            self.assertEqual(api_result["drawingId"], api_drawing_id)
            self.assertEqual(api_result["type"], "pdf")
            self.assertTrue(Path(api_result["path"]).exists())

            with self.assertRaises(HTTPException) as raised:
                export_drawing(api_project["id"], api_drawing_id, "png")
            self.assertEqual(raised.exception.status_code, 400)

            with self.assertRaises(HTTPException) as raised:
                export_drawing("missing_project", drawing_id, "svg")
            self.assertEqual(raised.exception.status_code, 404)

            with self.assertRaises(HTTPException) as raised:
                export_drawing("missing_project", drawing_id, "png")
            self.assertEqual(raised.exception.status_code, 404)

            with self.assertRaises(HTTPException) as raised:
                export_drawing(api_project["id"], "missing_drawing", "svg")
            self.assertEqual(raised.exception.status_code, 404)

    def test_project_scoped_routes_validate_missing_project_before_work(self):
        try:
            from fastapi import HTTPException
            from recreation_extractor.app import ImportFilesRequest, LayoutUpdateRequest, create_app
        except Exception as exc:
            self.skipTest(f"FastAPI dependencies unavailable: {exc}")

        with tempfile.TemporaryDirectory() as tmp:
            app = create_app(Path(tmp) / "data")
            import_files = self._route(app, "/projects/{project_id}/imports", "POST")
            extract = self._route(app, "/projects/{project_id}/jobs/extract", "POST")
            get_graph = self._route(app, "/projects/{project_id}/graph", "GET")
            put_layout = self._route(app, "/projects/{project_id}/layout", "PUT")
            export_graph = self._route(app, "/projects/{project_id}/exports/{export_type}", "POST")
            list_sources = self._route(app, "/projects/{project_id}/sources", "GET")

            route_calls = [
                lambda: import_files("missing_project", ImportFilesRequest(paths=["not-a-pdf.txt"])),
                lambda: extract("missing_project"),
                lambda: get_graph("missing_project"),
                lambda: put_layout("missing_project", LayoutUpdateRequest(nodes=[], edges=[])),
                lambda: export_graph("missing_project", "png"),
                lambda: list_sources("missing_project"),
            ]
            for call in route_calls:
                with self.assertRaises(HTTPException) as raised:
                    call()
                self.assertEqual(raised.exception.status_code, 404)

    def _document(self, project_id: str = "project_test", drawing_id: str = "drawing_test") -> dict:
        return {
            "id": drawing_id,
            "projectId": project_id,
            "name": "Test drawing",
            "width": 420.0,
            "height": 260.0,
            "objects": [
                {
                    "id": "source_1",
                    "kind": "source_fragment",
                    "label": "Source p1",
                    "bounds": {"x": 12.0, "y": 16.0, "width": 140.0, "height": 90.0},
                    "style": {"stroke": "#64748b", "fill": "#f8fafc", "strokeWidth": 1.0, "opacity": 0.25},
                },
                {
                    "id": "region_1",
                    "kind": "region",
                    "label": "Zone",
                    "bounds": {"x": 180.0, "y": 30.0, "width": 90.0, "height": 70.0},
                    "style": {"stroke": "#2563eb", "fill": "#dbeafe", "strokeWidth": 1.5, "opacity": 0.4},
                },
                {
                    "id": "pipe_1",
                    "kind": "pipe",
                    "label": '5 < 7 & "risky"',
                    "points": [{"x": 40.0, "y": 180.0}, {"x": 210.0, "y": 180.0}, {"x": 210.0, "y": 130.0}],
                    "style": {"stroke": "#0f766e", "strokeWidth": 3.0, "opacity": 0.85, "dash": [8, 4]},
                },
                {
                    "id": "label_1",
                    "kind": "label",
                    "label": "SAFE LABEL",
                    "points": [{"x": 44.0, "y": 58.0}],
                    "style": {"fill": "#111827", "fontSize": 13.0, "fontFamily": "Arial"},
                },
            ],
        }

    def _symbol(self, object_id: str, label: str, symbol_type: str, x: float) -> dict:
        return {
            "id": object_id,
            "kind": "symbol",
            "label": label,
            "bounds": {"x": x, "y": 40.0, "width": 42.0, "height": 28.0},
            "style": {"stroke": "#ea700d", "fill": "#ffffff", "strokeWidth": 1.1, "opacity": 1.0},
            "metadata": {"symbolType": symbol_type, "hideCenterLabel": True},
            "sourceEvidenceIds": [],
        }

    def _malformed_document(self) -> dict:
        return {
            "id": "drawing_malformed",
            "projectId": "project_test",
            "name": "Malformed drawing",
            "width": float("nan"),
            "height": float("inf"),
            "objects": [
                {
                    "id": "source_bad",
                    "kind": "source_fragment",
                    "label": "Bad source",
                    "bounds": {"x": float("nan"), "y": 4.0, "width": float("inf"), "height": 80.0},
                    "style": {
                        "stroke": "#nothex",
                        "fill": "#also-bad",
                        "strokeWidth": float("inf"),
                        "opacity": float("nan"),
                        "dash": [0, -2, float("inf")],
                    },
                },
                {
                    "id": "pipe_bad",
                    "kind": "pipe",
                    "label": "Bad pipe",
                    "points": [
                        {"x": float("nan"), "y": 1.0},
                        {"x": 10.0, "y": 10.0},
                        {"x": float("inf"), "y": 12.0},
                        {"x": 20.0, "y": 20.0},
                    ],
                    "style": {
                        "stroke": "#zzzzzz",
                        "strokeWidth": -100,
                        "opacity": 20,
                        "dash": ["bad", 0],
                    },
                },
                {
                    "id": "label_bad",
                    "kind": "label",
                    "label": "Bad label",
                    "points": [{"x": 30.0, "y": 40.0}],
                    "style": {"fill": "not-a-color", "fontSize": float("inf")},
                },
            ],
        }

    def _layout_option(self, project_id: str, drawing_id: str) -> LayoutOption:
        return LayoutOption(
            id=f"layout_{drawing_id}",
            projectId=project_id,
            drawingId=drawing_id,
            name="Test",
            description="Synthetic drawing export fixture",
            score=100.0,
            metrics={},
        )

    def _route(self, app, path: str, method: str):
        for route in app.routes:
            if getattr(route, "path", None) == path and method in getattr(route, "methods", set()):
                return route.endpoint
        self.fail(f"Route {method} {path} is not registered")

    def _latest_export_type(self, data_dir: Path) -> str:
        with closing(sqlite3.connect(data_dir / "projects.sqlite")) as conn:
            row = conn.execute("SELECT export_type FROM export_history ORDER BY id DESC LIMIT 1").fetchone()
        self.assertIsNotNone(row)
        return row[0]


if __name__ == "__main__":
    unittest.main()
