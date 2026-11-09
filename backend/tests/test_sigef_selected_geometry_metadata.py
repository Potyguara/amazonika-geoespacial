"""Aceite: polígono SIGEF por WFS e atualização oficial não inventada."""
import json
import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from fastapi import HTTPException
from app.api.routes import sources


class ResponseStub:
    def __init__(self, data):
        self.data=json.dumps(data).encode()
    def read(self, length):
        return self.data
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False


class Opener:
    def __init__(self, payloads):
        self.payloads=list(payloads)
        self.urls=[]
    def open(self, request, timeout=None):
        self.urls.append(request.full_url)
        return ResponseStub(self.payloads.pop(0) if self.payloads else {"datasets": []})


class FakeDB:
    def __init__(self):
        self.source=SimpleNamespace(slug="incra-sigef-brasil",is_active=True)
        self.closed=False
    def get(self, *_args):
        return self.source
    def close(self):
        self.closed=True


class SigefSelectionTests(unittest.TestCase):
    def test_exact_wfs_featureid_geometry(self):
        geometry={
            "type":"Polygon",
            "coordinates":[[[-51,1],[-50.9,1],[-50.9,1.1],[-51,1]]],
        }
        opener=Opener([{
            "type":"FeatureCollection",
            "features":[{"type":"Feature", "geometry":geometry,"properties":{}}],
        }])
        db=FakeDB()
        with patch.object(sources,"build_opener",return_value=opener):
            result=sources.sigef_selected_geometry(
                uuid4(),feature_id="sigef_geo.10983",parcel_code="",db=db,
            )
        self.assertEqual(result["geometry"],geometry)
        params=parse_qs(urlsplit(opener.urls[0]).query)
        self.assertEqual(params["FEATUREID"],["sigef_geo.10983"])
        self.assertTrue(db.closed)

    def test_real_feature_id_multipolygon_is_preserved(self):
        # Identificador e tipo geométrico confirmados na consulta à VPS.
        geom={
            "type":"MultiPolygon",
            "coordinates":[[[[-51.0, 1.0],[-50.9, 1.0],
                             [-50.9, 1.1],[-51.0, 1.0]]]],
        }
        opener=Opener([{
            "type":"FeatureCollection",
            "features":[{"type":"Feature","id":"sigef_geo.288728",
                         "geometry":geom,"properties":{}}],
        }])
        with patch.object(sources,"build_opener",return_value=opener):
            response=sources.sigef_selected_geometry(
                uuid4(),feature_id="sigef_geo.288728",
                parcel_code="",db=FakeDB(),
            )
        self.assertEqual(response["geometry"],geom)
        args=parse_qs(urlsplit(opener.urls[0]).query)
        self.assertEqual(args["FEATUREID"],["sigef_geo.288728"])
        self.assertEqual(args["SRSNAME"],["EPSG:4326"])

    def test_fallback_on_parcel_uuid_if_featureid_has_no_geometry(self):
        parcel="8a070fa2-0261-4141-892c-30d03169a45e"
        geometry={"type":"Polygon","coordinates":[[[-51,1],[-50.9,1],[-51,1]]]}
        empty={"type":"FeatureCollection","features":[]}
        full={"type":"FeatureCollection","features":[{"geometry":geometry}]}
        opener=Opener([empty,full])
        with patch.object(sources,"build_opener",return_value=opener):
            result=sources.sigef_selected_geometry(
                uuid4(),feature_id="sigef_geo.1234",parcel_code=parcel,db=FakeDB(),
            )
        self.assertEqual(result["geometry"],geometry)
        self.assertIn("CQL_FILTER",parse_qs(urlsplit(opener.urls[1]).query))
        self.assertIn(parcel,opener.urls[1])

    def test_invalid_codes_cannot_be_injected_into_cql(self):
        with self.assertRaises(HTTPException) as caught:
            sources.sigef_selected_geometry(
                uuid4(),feature_id="sigef_geo.1;DROP",parcel_code="bad'",
                db=FakeDB(),
            )
        self.assertEqual(caught.exception.status_code,422)

    def test_official_date_only_when_provider_supplies_modified(self):
        sample={"datasets":[{"alternate":"geonode:sigef_geo",
                            "last_updated":"2026-11-01T12:30:00Z"}]}
        opener=Opener([sample])
        with patch.object(sources,"build_opener",return_value=opener):
            result=sources.sigef_official_base_metadata(uuid4(),db=FakeDB())
        self.assertEqual(result["last_updated"],"2026-11-01T12:30:00Z")
        self.assertEqual(result["status"],"PUBLISHED")
        self.assertEqual(urlsplit(opener.urls[0]).hostname, "geoportal.incra.gov.br")

    def test_catalogue_resources_response_with_official_modification(self):
        example={"resources":[{"title":"Sigef - todas parcelas",
                              "last_updated":"2026-11-09T01:21:00Z"}]}
        opener=Opener([example])
        with patch.object(sources,"build_opener",return_value=opener):
            result=sources.sigef_official_base_metadata(uuid4(),db=FakeDB())
        self.assertEqual(result["last_updated"],"2026-11-09T01:21:00Z")
        self.assertEqual(result["resource"],"Sigef - todas parcelas")

    def test_missing_official_date_never_becomes_current_date(self):
        opener=Opener([{"datasets":[{"alternate":"geonode:sigef_geo",
                                     "date":"2021-04-01"}]}])
        with patch.object(sources,"build_opener",return_value=opener):
            result=sources.sigef_official_base_metadata(uuid4(),db=FakeDB())
        self.assertIsNone(result["last_updated"])
        self.assertEqual(result["status"],"NOT_PUBLISHED")
        self.assertIsInstance(datetime.fromisoformat(result["checked_at"]),datetime)


if __name__=="__main__":
    unittest.main()
