import unittest
from app.services.pb1_diagnostic import compare_mdt_controls, summarize_residuals

class DiagnosticTests(unittest.TestCase):
    def test_metrics(self):
        r=summarize_residuals([3,-3])
        self.assertEqual(r["mean_m"],0)
        self.assertEqual(r["rmse_m"],3)
        self.assertEqual(r["max_abs_m"],3)

    def test_missing(self):
        self.assertIsNone(summarize_residuals([]))
        self.assertIsNone(summarize_residuals([2])["sample_std_m"])

    def test_only_marcos_and_confirmed_h(self):
        rows=[{"name":"M1","sigef_vertex_code":"TEST-M-0001","latitude":0.2,"longitude":-51,
               "ellipsoidal_height_m":-5,"height_reference_confirmed":True},
              {"name":"V1","sigef_vertex_code":"TEST-V-0001","latitude":0.2,"longitude":-51}]
        result=compare_mdt_controls(rows,[{"name":"M1","normal_height_m":15}],lambda x,y:16)
        self.assertEqual(len(result["rows"]),1)
        self.assertEqual(result["vs_h"]["mean_m"],21)
        self.assertEqual(result["vs_hn"]["mean_m"],1)
        self.assertEqual(result["status"],"DIAGNOSTIC_ONLY")

    def test_nodata_not_zero(self):
        def fail(x,y): raise ValueError("NoData")
        result=compare_mdt_controls([{"name":"TEST-M-0001","latitude":0.2,"longitude":-51}],[],fail)
        self.assertIsNone(result["rows"][0]["mdt_m"])
        self.assertIsNone(result["vs_h"])
