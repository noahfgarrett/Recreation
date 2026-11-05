from unittest.mock import patch
import tempfile
import unittest
from pathlib import Path

from recreation_extractor.pid_stitch.evidence import _rotation_from_line, _text_spans_from_tesseract_tsv, extract_pid_evidence, find_continuation_candidates
from recreation_extractor.pid_stitch.models import PageEvidence, TextSpan, VectorSegment


class PidStitchEvidenceTests(unittest.TestCase):
    def test_extracts_page_text_and_vectors_from_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pid.pdf"
            self._write_fixture_pdf(path)
            pages = extract_pid_evidence("project_a", "src_a", path)
            self.assertEqual(len(pages), 1)
            self.assertGreater(pages[0].width, 0)
            self.assertGreater(pages[0].height, 0)
            self.assertTrue(any("TO SUPPLY HEADER" in span.text for span in pages[0].textSpans))
            self.assertGreaterEqual(pages[0].vectorCount, 1)
            self.assertTrue(any(segment.kind == "line" for segment in pages[0].vectorSegments))
            first_segment = pages[0].vectorSegments[0]
            self.assertGreaterEqual(len(first_segment.points), 2)
            self.assertGreater(first_segment.bounds["width"] + first_segment.bounds["height"], 0)

    def test_finds_edge_continuation_candidate(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pid.pdf"
            self._write_fixture_pdf(path)
            pages = extract_pid_evidence("project_a", "src_a", path)
            candidates = find_continuation_candidates(pages)
            self.assertEqual(len(candidates), 1)
            self.assertEqual(candidates[0].direction, "to")
            self.assertEqual(candidates[0].sheetRef, "DEMO-ME-4CHW02")
            self.assertEqual(candidates[0].lineTag, '16"-CHWS-CS02')
            self.assertEqual(candidates[0].system, "CHWS")
            self.assertEqual(candidates[0].edge, "right")

    def test_rotation_comes_from_line_direction(self):
        self.assertAlmostEqual(_rotation_from_line({"dir": (0, 1)}), 90.0)
        self.assertAlmostEqual(_rotation_from_line({"dir": (1, 0)}), 0.0)

    def test_noisy_edge_annotation_does_not_override_continuation_group(self):
        page = self._page_with_spans(
            [
                self._span('16"-CHWS-CS02', 760, 332),
                self._span("TO SUPPLY HEADER", 805, 350),
                self._span("DEMO-ME-4CHW02", 805, 368),
                self._span('12"-CDA-CS01', 790, 425),
                self._span("FROM AIR COMPRESSOR", 805, 443),
                self._span("DEMO-ME-4CDA01", 805, 461),
            ]
        )

        candidates = find_continuation_candidates([page])

        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].direction, "to")
        self.assertEqual(candidates[0].sheetRef, "DEMO-ME-4CHW02")
        self.assertEqual(candidates[0].lineTag, '16"-CHWS-CS02')
        self.assertEqual(candidates[0].system, "CHWS")
        self.assertNotIn("DEMO-ME-4CDA01", candidates[0].evidenceText)

    def test_keeps_duplicate_same_edge_callouts_when_spatially_distinct(self):
        page = self._page_with_spans(
            [
                self._span('16"-CHWS-CS02', 760, 120),
                self._span("TO SUPPLY HEADER", 805, 138),
                self._span("DEMO-ME-4CHW02", 805, 156),
                self._span('16"-CHWS-CS02', 760, 450),
                self._span("TO SUPPLY HEADER", 805, 468),
                self._span("DEMO-ME-4CHW02", 805, 486),
            ]
        )

        candidates = find_continuation_candidates([page])

        self.assertEqual(len(candidates), 2)
        self.assertEqual([candidate.sheetRef for candidate in candidates], ["DEMO-ME-4CHW02", "DEMO-ME-4CHW02"])

    def test_keeps_close_stacked_same_edge_callouts_clean(self):
        page = self._page_with_spans(
            [
                self._span('16"-CHWS-CS02', 760, 120),
                self._span("TO SUPPLY HEADER", 805, 138),
                self._span("DEMO-ME-4CHW02", 805, 156),
                self._span('16"-CHWS-CS02', 760, 184),
                self._span("TO RETURN HEADER", 805, 202),
                self._span("DEMO-ME-4CHW03", 805, 220),
                self._span("MATCH LINE", 825, 248),
            ]
        )

        candidates = find_continuation_candidates([page])

        self.assertEqual(len(candidates), 2)
        self.assertEqual(candidates[0].sheetRef, "DEMO-ME-4CHW02")
        self.assertEqual(candidates[1].sheetRef, "DEMO-ME-4CHW03")
        self.assertNotIn("DEMO-ME-4CHW03", candidates[0].evidenceText)
        self.assertNotIn("RETURN HEADER", candidates[0].label)
        self.assertNotIn("DEMO-ME-4CHW02", candidates[1].evidenceText)
        self.assertNotIn("SUPPLY HEADER", candidates[1].label)
        self.assertNotIn("MATCH LINE", candidates[1].label)

    def test_keeps_distinct_direction_only_candidates(self):
        page = self._page_with_spans(
            [
                self._span("TO FUTURE CONNECTION", 815, 110),
                self._span("FROM EXISTING CONNECTION", 805, 360),
            ]
        )

        candidates = find_continuation_candidates([page])

        self.assertEqual(len(candidates), 2)
        self.assertEqual([candidate.direction for candidate in candidates], ["to", "from"])
        self.assertTrue(all(candidate.sheetRef == "" for candidate in candidates))
        self.assertTrue(all(candidate.lineTag == "" for candidate in candidates))

    def test_rejects_title_block_line_tags_without_edge_leader(self):
        page = self._page_with_spans(
            [
                self._span('20"-CHWR-CS02', 760, 635),
                self._span("DESR", 720, 650),
                self._span("CHKD", 780, 650),
                self._span("APPR", 840, 650),
            ],
            vectors=[
                self._vector("revision_box", [(690, 620), (930, 620), (930, 680), (690, 680), (690, 620)]),
            ],
        )

        candidates = find_continuation_candidates([page])

        self.assertEqual(candidates, [])

    def test_rejects_legal_notes_that_look_like_directional_callouts(self):
        page = self._page_with_spans(
            [
                self._span("TO ALTER THIS DOCUMENT IN ANY WAY", 105, 635),
                self._span("FOR GENERAL NOTES SEE DRAWINGS DEMO-IE-0001", 780, 620),
            ],
            vectors=[
                self._vector("title_block", [(90, 612), (930, 612), (930, 686), (90, 686), (90, 612)]),
            ],
        )

        candidates = find_continuation_candidates([page])

        self.assertEqual(candidates, [])

    def test_keeps_bare_edge_line_tag_when_attached_to_leader(self):
        page = self._page_with_spans(
            [
                self._span('20"-CHWR-CS02', 760, 635),
            ],
            vectors=[
                self._vector("edge_leader", [(780, 642), (780, 699)]),
            ],
        )

        candidates = find_continuation_candidates([page])

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].lineTag, '20"-CHWR-CS02')
        self.assertEqual(candidates[0].edge, "bottom")

    def test_rejects_red_review_markup_direction_notes(self):
        page = self._page_with_spans(
            [
                self._span("TO BE VERIFIED BY FIELD TEAM", 815, 120, color="#ff0000"),
                self._span("KEYED NOTES ARE OFFSET FOR REVIEW", 815, 138, color="#ff0000"),
            ]
        )

        candidates = find_continuation_candidates([page])

        self.assertEqual(candidates, [])

    def test_rejects_edge_prose_that_only_contains_direction_words(self):
        page = self._page_with_spans(
            [
                self._span("ARE SUBJECT TO VERIFICATION ON SITE.", 770, 120),
                self._span("THE PANEL TO ALLOW FUTURE ACCESS WITHOUT", 705, 152),
                self._span("INSTALLED TO A COMMON ACCESSIBLE TROUGH ABOVE", 695, 184),
            ]
        )

        candidates = find_continuation_candidates([page])

        self.assertEqual(candidates, [])

    def test_groups_rotated_edge_callout_parts(self):
        page = self._page_with_spans(
            [
                self._span('24"-CHWS-CS01', 926, 238, width=12, height=96, rotation=90),
                self._span("TO SUPPLY HEADER", 846, 254, width=12, height=92, rotation=90),
                self._span("DEMO-ME-4CHW02", 806, 254, width=12, height=86, rotation=90),
            ],
            vectors=[
                self._vector("edge_leader", [(910, 290), (998, 290)]),
            ],
        )

        candidates = find_continuation_candidates([page])

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].direction, "to")
        self.assertEqual(candidates[0].sheetRef, "DEMO-ME-4CHW02")
        self.assertEqual(candidates[0].lineTag, '24"-CHWS-CS01')

    def test_rectangular_flow_callout_records_external_source_and_fractional_line_tag(self):
        page = self._page_with_spans(
            [
                self._span("DEMO-ME-4TCHW01", 1172, 130, width=12, height=69, rotation=90),
                self._span("TERTIARY CHILLED WATER", 1188, 129, width=12, height=100, rotation=90),
                self._span("DEMO-ME-4ICW01", 1381, 130, width=12, height=62, rotation=90),
                self._span("FROM ICW SUPPLY", 1396, 129, width=12, height=70, rotation=90),
                self._span('1 1/2"-ICW-PC05', 1398, 277, width=12, height=64, rotation=90),
            ],
            vectors=[
                self._vector("callout_box", [(1320, 110), (1430, 110), (1430, 260), (1320, 260), (1320, 110)]),
                self._vector("callout_arrow", [(1430, 185), (1465, 210), (1430, 235), (1430, 185)]),
            ],
        )

        candidates = find_continuation_candidates([page])

        sources = [candidate for candidate in candidates if candidate.metadata.get("externalFlowLabel") == "ICW SUPPLY"]
        self.assertEqual(len(sources), 1)
        source = sources[0]
        self.assertEqual(source.direction, "from")
        self.assertEqual(source.sheetRef, "DEMO-ME-4ICW01")
        self.assertEqual(source.lineTag, '1 1/2"-ICW-PC05')
        self.assertEqual(source.system, "ICW")
        self.assertEqual(source.metadata["externalFlowRole"], "source")
        self.assertEqual(source.metadata["sourceDrawingRef"], "DEMO-ME-4ICW01")
        self.assertEqual(source.metadata["directionEvidence"], "explicit_text")
        self.assertNotIn("DEMO-ME-4TCHW01", source.evidenceText)

    def test_flow_callout_infers_ca_system_from_connected_line_tag(self):
        page = self._page_with_spans(
            [
                self._span('6"-CA-CS01', 720, 110, width=80, height=12),
                self._span("TO WET RECEIVER", 805, 110, width=90, height=12),
                self._span("DEMO-ME-4CDA02", 900, 110, width=90, height=12),
            ]
        )

        candidates = find_continuation_candidates([page])

        destination = next(candidate for candidate in candidates if candidate.metadata.get("externalFlowLabel") == "WET RECEIVER")
        self.assertEqual(destination.direction, "to")
        self.assertEqual(destination.lineTag, '6"-CA-CS01')
        self.assertEqual(destination.system, "CA")
        self.assertEqual(destination.metadata["externalFlowRole"], "destination")

    def test_flow_callout_infers_secondary_chilled_water_system_from_line_tag(self):
        page = self._page_with_spans(
            [
                self._span('3/4"-SCHWS-CS01', 720, 110, width=92, height=12),
                self._span("TO CHILLED WATER SYSTEM", 820, 110, width=146, height=12),
                self._span("DEMO-ME-4SCHW02", 820, 130, width=96, height=12),
            ]
        )

        candidates = find_continuation_candidates([page])

        destination = next(candidate for candidate in candidates if candidate.metadata.get("externalFlowLabel") == "CHILLED WATER SYSTEM")
        self.assertEqual(destination.lineTag, '3/4"-SCHWS-CS01')
        self.assertEqual(destination.system, "SCHWS")

    def test_note_reference_without_connected_line_tag_is_not_external_flow_metadata(self):
        page = self._page_with_spans(
            [
                self._span("TO SCHEDULE .", 850, 110, width=100, height=12),
                self._span("DEMO-ME-2400", 850, 130, width=82, height=12),
            ]
        )

        candidates = find_continuation_candidates([page])

        self.assertTrue(candidates)
        self.assertTrue(all("externalFlowLabel" not in candidate.metadata for candidate in candidates))

    def test_split_flow_callout_text_records_external_source_metadata(self):
        page = self._page_with_spans(
            [
                self._span("FROM", 805, 130, width=35, height=12),
                self._span("ICW SUPPLY", 845, 130, width=76, height=12),
                self._span("DEMO-ME-4ICW01", 845, 148, width=92, height=12),
                self._span('1 1/2"-ICW-PC05', 805, 166, width=115, height=12),
            ]
        )

        candidates = find_continuation_candidates([page])

        source = next(candidate for candidate in candidates if candidate.metadata.get("externalFlowLabel") == "ICW SUPPLY")
        self.assertEqual(source.direction, "from")
        self.assertEqual(source.sheetRef, "DEMO-ME-4ICW01")
        self.assertEqual(source.lineTag, '1 1/2"-ICW-PC05')
        self.assertEqual(source.system, "ICW")
        self.assertEqual(source.metadata["directionEvidence"], "explicit_text")

    def test_uses_ocr_fallback_for_vector_heavy_pages_with_weak_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weak-text.pdf"
            self._write_vector_heavy_fixture_pdf(path)
            ocr_span = TextSpan("RS4SS2F26", 120.0, 150.0, 86.0, 14.0)

            with patch(
                "recreation_extractor.pid_stitch.evidence._extract_ocr_text_spans",
                return_value=([ocr_span], "ocr_applied"),
            ) as ocr:
                pages = extract_pid_evidence("project_a", "src_a", path)

            self.assertTrue(ocr.called)
            self.assertTrue(any(span.text == "RS4SS2F26" for span in pages[0].textSpans))
            self.assertEqual(pages[0].metadata["textExtraction"]["mode"], "native+ocr")
            self.assertEqual(pages[0].metadata["textExtraction"]["ocrSpanCount"], 1)

    def test_skips_ocr_for_pages_with_good_native_text(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "pid.pdf"
            self._write_fixture_pdf(path)

            with patch("recreation_extractor.pid_stitch.evidence._extract_ocr_text_spans") as ocr:
                pages = extract_pid_evidence("project_a", "src_a", path)

            self.assertFalse(ocr.called)
            self.assertEqual(pages[0].metadata["textExtraction"]["mode"], "native")

    def test_records_ocr_unavailable_without_breaking_import(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weak-text.pdf"
            self._write_vector_heavy_fixture_pdf(path)

            with patch(
                "recreation_extractor.pid_stitch.evidence._extract_ocr_text_spans",
                return_value=([], "ocr_unavailable"),
            ):
                pages = extract_pid_evidence("project_a", "src_a", path)

            self.assertEqual(pages[0].metadata["textExtraction"]["mode"], "ocr_unavailable")
            self.assertEqual(pages[0].metadata["textExtraction"]["ocrSpanCount"], 0)

    def test_native_ocr_returns_unavailable_when_tesseract_is_not_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "weak-text.pdf"
            self._write_vector_heavy_fixture_pdf(path)
            import fitz

            doc = fitz.open(path)
            try:
                with patch("recreation_extractor.pid_stitch.evidence.shutil.which", return_value=None):
                    spans, status = __import__(
                        "recreation_extractor.pid_stitch.evidence",
                        fromlist=["_extract_ocr_text_spans"],
                    )._extract_ocr_text_spans(doc[0])
            finally:
                doc.close()

            self.assertEqual(spans, [])
            self.assertEqual(status, "ocr_unavailable")

    def test_one_callout_reached_from_two_seed_spans_gives_one_candidate(self):
        # Geometry taken from the left-edge callout on the sample package's distribution sheet.
        page = PageEvidence(
            id="src_a_p1",
            sourceFileId="src_a",
            page=1,
            width=1224.0,
            height=792.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 1224.0, "height": 792.0},
            textSpans=[
                TextSpan("FROM DEMO-ME-4CHW01", 52.0, 209.0, 81.0, 9.0),
                TextSpan('8"-CHWS-101', 52.0, 221.5, 38.0, 8.2),
                # the same line tag printed along the pipe, close enough to share the neighborhood
                TextSpan('8"-CHWS-101', 200.0, 205.0, 41.0, 8.9),
            ],
            vectorCount=0,
            vectorSegments=[],
        )

        tagged = [c for c in find_continuation_candidates([page]) if c.lineTag]

        self.assertEqual(len(tagged), 1)
        self.assertEqual((tagged[0].direction, tagged[0].sheetRef, tagged[0].lineTag), ("from", "DEMO-ME-4CHW01", '8"-CHWS-101'))

    def test_equipment_tag_with_project_code_is_not_a_sheet_reference(self):
        page = self._page_with_spans([TextSpan("R-DEMO-CHW-P-01", 30.0, 300.0, 70.0, 9.0)])

        self.assertEqual(find_continuation_candidates([page]), [])

    def test_parses_rendered_tesseract_tsv_into_page_coordinates(self):
        tsv = "\n".join(
            [
                "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
                "5\t1\t1\t1\t1\t1\t200\t120\t80\t20\t93\tGEN-15",
                "5\t1\t1\t1\t2\t1\t220\t170\t110\t20\t88\tRW4MDP4C6",
                "5\t1\t1\t1\t3\t1\t220\t210\t110\t20\t-1\t",
            ]
        )

        spans = _text_spans_from_tesseract_tsv(tsv, zoom=2.0)

        self.assertEqual([span.text for span in spans], ["GEN-15", "RW4MDP4C6"])
        self.assertEqual(spans[0].x, 100.0)
        self.assertEqual(spans[0].y, 60.0)
        self.assertEqual(spans[0].width, 40.0)
        self.assertEqual(spans[0].height, 10.0)

    def _write_fixture_pdf(self, path: Path):
        try:
            from reportlab.pdfgen import canvas
        except Exception:
            self.skipTest("reportlab not installed")
        c = canvas.Canvas(str(path), pagesize=(1000, 700))
        c.line(820, 350, 965, 350)
        c.line(965, 350, 940, 365)
        c.line(965, 350, 940, 335)
        c.drawString(760, 372, '16"-CHWS-CS02')
        c.drawString(805, 390, "TO SUPPLY HEADER")
        c.drawString(805, 408, "DEMO-ME-4CHW02")
        c.save()

    def _write_vector_heavy_fixture_pdf(self, path: Path):
        try:
            from reportlab.pdfgen import canvas
        except Exception:
            self.skipTest("reportlab not installed")
        c = canvas.Canvas(str(path), pagesize=(1000, 700))
        c.drawString(90, 80, "RFI 1979")
        for index in range(0, 1200):
            x = 40 + (index % 60) * 15
            y = 120 + (index // 60) * 12
            c.line(x, y, x + 8, y)
        c.save()

    def _page_with_spans(self, spans: list[TextSpan], vectors: list[VectorSegment] | None = None) -> PageEvidence:
        return PageEvidence(
            id="src_a_p1",
            sourceFileId="src_a",
            page=1,
            width=1000.0,
            height=700.0,
            rotation=0,
            cropBounds={"x": 0.0, "y": 0.0, "width": 1000.0, "height": 700.0},
            textSpans=spans,
            vectorCount=1,
            vectorSegments=vectors or [],
        )

    def _span(
        self,
        text: str,
        x: float,
        y: float,
        width: float | None = None,
        height: float = 12.0,
        rotation: float = 0.0,
        color: str | None = None,
    ) -> TextSpan:
        return TextSpan(
            text=text,
            x=x,
            y=y,
            width=width if width is not None else max(42.0, len(text) * 6.0),
            height=height,
            rotation=rotation,
            color=color,
        )

    def _vector(self, vector_id: str, points: list[tuple[float, float]]) -> VectorSegment:
        clean_points = [{"x": x, "y": y} for x, y in points]
        min_x = min(point["x"] for point in clean_points)
        min_y = min(point["y"] for point in clean_points)
        max_x = max(point["x"] for point in clean_points)
        max_y = max(point["y"] for point in clean_points)
        return VectorSegment(
            id=vector_id,
            kind="polyline",
            points=clean_points,
            bounds={"x": min_x, "y": min_y, "width": max_x - min_x, "height": max_y - min_y},
        )


if __name__ == "__main__":
    unittest.main()
