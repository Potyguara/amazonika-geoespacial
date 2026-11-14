"""Regressão da pré-validação multiparcelas e conflito cartográfico."""
import copy
import unittest

from app.services.sigef_parcel_review import review_sigef_parcels


def polygon(x1, y1, x2, y2):
    return {"type": "Polygon", "coordinates": [[
        [x1, y1], [x1, y2], [x2, y2], [x2, y1], [x1, y1]
    ]]}


IDENT = {
    "holder_name": "TITULAR TESTE",
    "holder_document": "12345678901",
    "property_name": "IMOVEL TESTE",
    "situation": "Área não Titulada",
    "municipalities": ["Macapá-AP", "Santana-AP"],
}


class SigefParcelReviewTests(unittest.TestCase):
    def payload(self):
        return {"identification": copy.deepcopy(IDENT), "parcels": [
            {"number": "1", "name": "Parcela 1",
             "geometry": polygon(-51.3, 0.1, -51.2, 0.2)},
            {"number": "2", "name": "Parcela 2",
             "geometry": polygon(-51.2, 0.1, -51.1, 0.2)},
        ]}

    def test_two_municipalities_and_touching_parcels(self):
        result = review_sigef_parcels(self.payload())
        self.assertEqual(result["status"], "PREVALIDATED", result["errors"])
        self.assertEqual(result["municipalities"], ["Macapá-AP", "Santana-AP"])
        self.assertEqual(result["parcel_count"], 2)
        self.assertFalse(result["internal_overlaps"])
        self.assertFalse(result["eligible_for_official_submission"])

    def test_internal_parcel_overlap_blocks(self):
        payload = self.payload()
        payload["parcels"][1]["geometry"] = polygon(-51.25, 0.15, -51.15, 0.25)
        result = review_sigef_parcels(payload)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertGreater(result["internal_overlaps"][0]["overlap_ha"], 0)

    def test_neighbor_overlap_no_coordinate_change(self):
        payload = self.payload()
        payload["neighbors"] = [{
            "reference_id": "SIGEF-TESTE",
            "provenance": "SIGEF_CERTIFICADA_VERIFICADA",
            "geometry": polygon(-51.29, 0.11, -51.22, 0.19),
        }]
        before = copy.deepcopy(payload)
        result = review_sigef_parcels(payload)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(len(result["neighbor_overlaps"]), 1)
        conflict = result["neighbor_overlaps"][0]
        self.assertGreater(conflict["overlap_ha"], 0)
        self.assertFalse(conflict["change_applied"])
        self.assertTrue(conflict["requires_resurvey_and_technical_approval"])
        self.assertGreater(len(conflict["reference_displacements"]), 0)
        self.assertFalse(result["coordinates_modified"])
        self.assertEqual(payload, before)

    def test_registered_property_requires_registration(self):
        payload = self.payload()
        payload["identification"]["situation"] = "Imóvel Registrado"
        result = review_sigef_parcels(payload)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertTrue(any("matrícula" in msg for msg in result["errors"]))

    def test_duplicate_municipality_blocks(self):
        payload = self.payload()
        payload["identification"]["municipalities"].append("Macapá-AP")
        result = review_sigef_parcels(payload)
        self.assertEqual(result["status"], "BLOCKED")

    def test_invalid_geometry_blocks(self):
        payload = self.payload()
        payload["parcels"][0]["geometry"] = {
            "type": "Polygon",
            "coordinates": [[[-51.3, 0.1], [-51.2, 0.2], [-51.3, 0.2],
                             [-51.2, 0.1], [-51.3, 0.1]]],
        }
        with self.assertRaises(ValueError):
            review_sigef_parcels(payload)

    def test_internal_hole_requires_confirmation(self):
        payload = self.payload()
        payload["parcels"] = [{
            "number": "1", "name": "Parcela Encravada",
            "geometry": {"type": "Polygon", "coordinates": [
                [[-51.3, 0.1], [-51.3, 0.3], [-51.1, 0.3],
                 [-51.1, 0.1], [-51.3, 0.1]],
                [[-51.25, 0.15], [-51.15, 0.15],
                 [-51.15, 0.25], [-51.25, 0.25], [-51.25, 0.15]],
            ]},
        }]
        result = review_sigef_parcels(payload)
        self.assertEqual(result["status"], "BLOCKED")
        self.assertEqual(result["parcels"][0]["internal_perimeter_count"], 1)


if __name__ == "__main__":
    unittest.main()
