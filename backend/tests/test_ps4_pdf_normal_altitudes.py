"""Regressão: quadro cartográfico sempre usa HN, nunca a h GNSS."""
import unittest
from pyproj import Transformer
from app.services.plant_memorial_v2 import prepare_parcels
from app.services.plant_template_engine import _rows


class TestPs4PdfNormalAltitudes(unittest.TestCase):
    def test_normal_altitudes_match_memorial_and_mark_estimated_v(self):
        original = [-17.70, None, None, -20.88]
        hn = [5.86, 5.59, 5.40, 2.64]
        raw = [{
            "name": "Teste M-V-M",
            "geometry": {"type": "Polygon", "coordinates": [[
                [-50.876, 0.407], [-50.875, 0.407],
                [-50.874, 0.406], [-50.873, 0.404],
                [-50.876, 0.407],
            ]]},
            "vertex_names": ["CPBR-M-578", "VIRTUAL-V-0001",
                             "VIRTUAL-V-0002", "CPBR-M-581"],
            "altitudes_m": original,
            "normal_altitudes_m": hn,
        }]
        parcel = prepare_parcels(raw)
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:32622",
                                           always_xy=True)
        rows = _rows(parcel, transformer)
        self.assertEqual(len(rows), 4)
        self.assertEqual([row[5] for row in rows],
                         ["5,86", "5,59~", "5,40~", "2,64"])
        self.assertNotIn("-17,70", str(rows))
        self.assertNotIn("-20,88", str(rows))

    def test_missing_normal_is_not_replaced_by_ellipsoidal_height(self):
        raw = [{
            "name": "Sem HN",
            "geometry": {"type": "Polygon", "coordinates": [[
                [-50.876, 0.407], [-50.875, 0.406],
                [-50.874, 0.404], [-50.876, 0.407]
            ]]},
            "vertex_names": ["M-1", "VIRTUAL-V-0001", "M-2"],
            "altitudes_m": [-22.0, None, -18.0],
            "normal_altitudes_m": [None, None, None],
        }]
        parcel = prepare_parcels(raw)
        transformer = Transformer.from_crs("EPSG:4326", "EPSG:32622",
                                           always_xy=True)
        rows = _rows(parcel, transformer)
        self.assertEqual([row[5] for row in rows], ["—", "—", "—"])


if __name__ == "__main__":
    unittest.main()
