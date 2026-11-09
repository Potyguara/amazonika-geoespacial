"""SIGEF Brasil: proxy OGC GetFeatureInfo sem quebrar o filtro por UF."""
import json
import unittest
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from starlette.datastructures import QueryParams

from app.api.routes import sources


class FakeResult:
    headers = SimpleNamespace(get_content_type=lambda: "application/json")

    def read(self, limit):
        return json.dumps({
            "type": "FeatureCollection", "features": [
                {"type": "Feature", "properties": {"nome_imovel": "TESTE"}}
            ]
        }).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


class FakeOpener:
    destination = None

    def open(self, request, timeout=0):
        self.destination = request.full_url
        return FakeResult()


class FakeDB:
    def __init__(self, source):
        self.source = source
        self.closed = False

    def get(self, model, source_id):
        return self.source

    def close(self):
        self.closed = True


class SigefWmsFeatureInfoTests(unittest.TestCase):
    def setUp(self):
        self.id = uuid4()
        self.db = FakeDB(SimpleNamespace(
            id=self.id, name="SIGEF - Brasil",
            slug="incra-sigef-brasil", institution="INCRA",
            metadata_json={
                "wms_enabled": True,
                "wms_url": "https://geonodeincra.serpro.gov.br/geoserver/geonode/sigef_geo/ows",
                "wms_theme": "geonode:sigef_geo",
                "wms_fixed_layer": "geonode:sigef_geo",
            },
        ))

    def request(self, query):
        return SimpleNamespace(query_params=QueryParams(query))

    def test_feature_info_query_passes_and_uf_is_applied_server_side(self):
        opener = FakeOpener()
        query = (
            "uf=ap&SERVICE=WMS&VERSION=1.1.1&REQUEST=GetFeatureInfo"
            "&LAYERS=geonode%3Asigef_geo&QUERY_LAYERS=geonode%3Asigef_geo"
            "&SRS=EPSG%3A3857&BBOX=-6000000%2C0%2C-5900000%2C100000"
            "&WIDTH=101&HEIGHT=101&X=50&Y=50&INFO_FORMAT=application%2Fjson"
            "&CQL_FILTER=uf_id%3D99"
        )
        with patch.object(sources, "build_opener", return_value=opener):
            response=sources.proxy_source_wms(
                self.id,self.request(query),self.db,
            )
        self.assertEqual(response.media_type,"application/json")
        payload=json.loads(response.body)
        self.assertEqual(payload["features"][0]["properties"]["nome_imovel"],"TESTE")
        params=parse_qs(urlsplit(opener.destination).query)
        self.assertEqual(params["REQUEST"],["GetFeatureInfo"])
        self.assertEqual(params["INFO_FORMAT"],["application/json"])
        self.assertEqual(params["QUERY_LAYERS"],["geonode:sigef_geo"])
        self.assertEqual(params["CQL_FILTER"],["uf_id=16"])
        self.assertNotIn("uf",params)
        self.assertTrue(self.db.closed)

    def test_all_brazil_has_no_cql_filter(self):
        opener=FakeOpener()
        query=(
            "uf=all&SERVICE=WMS&REQUEST=GetFeatureInfo"
            "&LAYERS=geonode%3Asigef_geo&INFO_FORMAT=application%2Fjson"
        )
        with patch.object(sources, "build_opener", return_value=opener):
            sources.proxy_source_wms(self.id,self.request(query),self.db)
        params=parse_qs(urlsplit(opener.destination).query)
        self.assertNotIn("CQL_FILTER",params)

    def test_foreign_host_is_rejected(self):
        self.db.source.metadata_json["wms_url"]="https://example.com/attack"
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as caught:
            sources.proxy_source_wms(
                self.id,self.request("uf=ap&REQUEST=GetFeatureInfo"),self.db
            )
        self.assertEqual(caught.exception.status_code,400)


if __name__=="__main__":
    unittest.main()
