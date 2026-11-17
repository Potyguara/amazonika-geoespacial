import unittest
from app.services.pb1_report import build_pb1_report

class PB1ReportTests(unittest.TestCase):
    def test_preliminary_pdf_without_optional_data(self):
        snapshot={"topcon":{"pb1_draft":[
            {"name":"TEST-V-0001","latitude":0.23,"longitude":-51.36,"source_elevation_m":13.575},
            {"name":"TEST-V-0002","latitude":0.22,"longitude":-51.35,"source_elevation_m":None}],
            "pb1_source":{"product":"Base <oficial> & teste"}}}
        pdf=build_pb1_report("Fazenda teste","test-id",snapshot,{})
        self.assertTrue(pdf.startswith(b"%PDF-"))
        self.assertGreater(len(pdf),1000)

    def test_empty_vertices_rejected(self):
        with self.assertRaises(ValueError):
            build_pb1_report("Teste","id",{}, {})
