import tempfile
import unittest
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from recreation_extractor.pid_stitch.visio_master_index import extract_visio_master_index


class VisioMasterIndexTests(unittest.TestCase):
    def test_extracts_named_visio_masters_from_vsdx_package(self):
        with tempfile.TemporaryDirectory() as tmp:
            vsdx_path = Path(tmp) / "reference.vsdx"
            with ZipFile(vsdx_path, "w", ZIP_DEFLATED) as package:
                package.writestr(
                    "visio/masters/masters.xml",
                    """<?xml version="1.0" encoding="UTF-8"?>
                    <Masters xmlns="http://schemas.microsoft.com/office/visio/2012/main">
                      <Master ID="7" NameU="Centrifugal pump" Name="Centrifugal pump" UniqueID="{pump}"/>
                      <Master ID="8" NameU="PID Electric" Name="PID Electric"/>
                      <Master ID="9" Name="Wedge/ Parallel"/>
                      <Master ID="10"/>
                    </Masters>""",
                )
                package.writestr("visio/masters/master7.xml", "<MasterContents/>")
                package.writestr("visio/masters/master8.xml", "<MasterContents/>")
                package.writestr("visio/masters/master9.xml", "<MasterContents/>")

            rows = extract_visio_master_index([vsdx_path])

        self.assertEqual([row.name for row in rows], ["Centrifugal pump", "PID Electric", "Wedge/ Parallel"])
        self.assertEqual(rows[0].source_file, "reference.vsdx")
        self.assertEqual(rows[0].master_id, "7")
        self.assertEqual(rows[0].symbol_hint, "pump")
        self.assertEqual(rows[1].symbol_hint, "signal")
        self.assertEqual(rows[2].symbol_hint, "valve")


if __name__ == "__main__":
    unittest.main()
