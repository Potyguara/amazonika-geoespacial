"""MapBiomas Collection 11 adapter tests: no network, no credentials."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.services import rural_mapbiomas as mb
from app.api.routes import rural_diagnostics as routes

SUBJECT = {
    "type": "Polygon",
    "coordinates": [[[-51.2,-0.2],[-51.1,-0.2],[-51.1,-0.1],[-51.2,-0.1],[-51.2,-0.2]]],
}


def test_collection_11_asset_and_years():
    assert mb.COLLECTION == 11
    assert "collection11" in mb.ASSET_ID
    assert mb.MAX_YEAR == 2025
    assert mb.RESOLUTION_M == 30


def test_credentialless_configuration_does_not_reveal_secrets(monkeypatch):
    monkeypatch.setattr(mb, "get_settings", lambda: SimpleNamespace(
        gee_project_id=None,
        gee_service_account_email=None,
        gee_service_account_key_file=None,
    ))
    result = mb.gee_configuration()
    assert not result["enabled"]
    assert "service_account_email" not in result
    assert "key_file" not in result
    with pytest.raises(mb.MapBiomasError, match="não está habilitado"):
        mb._initialize_gee()


def test_geometry_and_extent_validation():
    assert mb.validate_geometry(SUBJECT).geom_type == "Polygon"
    for bad in [
        {"type":"Point","coordinates":[-51.1,-0.1]},
        {"type":"Polygon","coordinates":[[
            [-53,-1],[-52,-1],[-52,0],[-53,0],[-53,-1]
        ]]},
    ]:
        with pytest.raises(ValueError):
            mb.validate_geometry(bad)


def test_invalid_year_fails_before_connecting_gee(monkeypatch):
    monkeypatch.setattr(mb,"_initialize_gee",lambda: pytest.fail("should not authenticate"))
    with pytest.raises(ValueError, match="Ano indisponível"):
        mb.mapbiomas_preview(SUBJECT, 2026)


def test_class_area_results_and_unmapped_codes_are_not_invented():
    raw = {"groups": [
        {"class": 3, "sum": 200},
        {"class": 15, "sum": 100},
        {"class": 999, "sum": 20},
    ]}
    result = mb._normalize_statistics(raw, 2025, 330)
    assert result["classified_area_hectares"] == 320
    assert result["geometry_area_hectares"] == 330
    assert result["classes"][0]["name"] == "Formação Florestal"
    assert result["classes"][1]["name"] == "Pastagem"
    assert "consultar legenda" in result["classes"][2]["name"]
    assert sum(row["percent_classified"] for row in result["classes"]) == pytest.approx(100, abs=.01)


def test_rejects_missing_groups_duplicates_and_negative_class_area():
    for raw in [{}, {"groups": [{"class": 3, "sum": -1}]},
                {"groups": [{"class":3,"sum":10},{"class":3,"sum":5}]}]:
        with pytest.raises(mb.MapBiomasError):
            mb._normalize_statistics(raw, 2025, 50)


def test_api_maps_disabled_gee_to_503(monkeypatch):
    monkeypatch.setattr(routes, "mapbiomas_preview",
                        lambda *args: (_ for _ in ()).throw(
                            mb.MapBiomasError("Credenciais ausentes")
                        ))
    with pytest.raises(HTTPException) as err:
        routes.rural_mapbiomas_preview(routes.MapBiomasPreviewRequest(
            geometry=SUBJECT, year=2025))
    assert err.value.status_code == 503


def test_gee_reduce_uses_remote_pixel_area_and_grouped_classification():
    calls = []
    class FakeOutput:
        def getInfo(self):
            return {"groups":[{"class":3,"sum":15.5}]}
    class FakeImage:
        def select(self, key):
            calls.append(("select", key)); return self
        def rename(self,key):
            calls.append(("rename",key)); return self
        def divide(self,n):
            calls.append(("divide",n));return self
        def addBands(self,b):
            calls.append(("addBands", True));return self
        def reduceRegion(self,**kw):
            calls.append(("reduceRegion", kw)); return FakeOutput()
    class FakeReducer:
        def group(self,**kw):
            calls.append(("group", kw)); return self
    class FakeEE:
        Geometry = staticmethod(lambda geom,**kw: geom)
        Image = staticmethod(lambda asset: FakeImage())
        Reducer = SimpleNamespace(sum=lambda: FakeReducer())
    FakeEE.Image.pixelArea = lambda: FakeImage()
    result = mb._reduce_class_areas(FakeEE, SUBJECT, 2025)
    assert result["groups"][0]["sum"] == 15.5
    assert ("select","classification_2025") in calls
    assert ("group",{"groupField":1,"groupName":"class"}) in calls
    opts = next(v for k,v in calls if k=="reduceRegion")
    assert opts["scale"] == 30 and opts["bestEffort"] is False
    assert opts["maxPixels"] == mb.MAX_PIXELS


def test_preliminary_mapbiomas_pdf_document():
    from datetime import datetime, timezone
    from app.services.rural_mapbiomas_pdf import mapbiomas_pdf
    report = mb._normalize_statistics(
        {"groups": [{"class":3,"sum":21.5},{"class":15,"sum":12}]},
        2025, 35,
    )
    pdf = mapbiomas_pdf(
        property_name="Fazenda Teste",
        cadastral_source="SIGEF",
        cadastral_code="BR-123",
        report=report,
        generated_at=datetime(2026,11,5,tzinfo=timezone.utc),
    )
    assert pdf.startswith(b"%PDF")
    assert len(pdf) > 2000


def test_mapbiomas_pdf_route_revalidates_and_recomputes(monkeypatch):
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(gee_browser_preview_enabled=True))
    from uuid import uuid4
    identifier = uuid4()
    calls = {}
    monkeypatch.setattr(routes, "resolve_rural_perimeter", lambda uid, db: (
        calls.update({"id": uid}) or {
            "name":"Teste","source_name":"SIGEF","geometry":SUBJECT,
            "feature_id":str(uid),
        }
    ))
    def fake_preview(geometry,year):
        calls["year"] = year
        calls["geometry"] = geometry
        return mb._normalize_statistics(
            {"groups":[{"class":3,"sum":5.5}]}, year, 5.8)
    monkeypatch.setattr(routes, "mapbiomas_preview", fake_preview)
    subject = routes.RuralPreviewPdfRequest(
        retrieval="LOCAL_VECTOR",feature_id=str(identifier))
    payload = routes.MapBiomasPdfRequest(subject=subject,year=2025)
    response = routes.rural_mapbiomas_pdf(payload, db=object())
    assert response.body.startswith(b"%PDF")
    assert response.headers["x-report-type"] == "preliminary-rural-mapbiomas"
    assert calls == {"id": identifier,"year":2025,"geometry":SUBJECT}


def test_real_world_mapbiomas_sample_class_identification():
    """Regressão dos códigos observados na primeira consulta GEE real."""
    data = {"groups": [{"class": 24, "sum": 3.9815}, {"class": 11, "sum": 0.9087}]}
    result = mb._normalize_statistics(data, 2025, 4.9)
    assert result["classified_area_hectares"] == pytest.approx(4.8902)
    assert result["classes"][0]["name"] == "Área Urbanizada"
    assert result["classes"][1]["name"] == "Campo Alagado e Área Pantanosa"
    assert result["classes"][0]["percent_classified"] == pytest.approx(81.418, abs=.003)


def test_verified_mapbiomas_real_car_2025_class_legend():
    """2026-11-05 official EE sample: six observed Collection 11 codes."""
    sample = {"groups": [
        {"class": 11, "sum": 870.7678},
        {"class": 6, "sum": 215.6480},
        {"class": 3, "sum": 18.1312},
        {"class": 9, "sum": 8.0247},
        {"class": 33, "sum": 1.3431},
        {"class": 21, "sum": 1.1622},
    ]}
    result = mb._normalize_statistics(sample, 2025, 1115.1093)
    expected = {
        11: ("Campo Alagado e Área Pantanosa", "#519799"),
        6: ("Floresta Alagável", "#007785"),
        3: ("Formação Florestal", "#1f8d49"),
        9: ("Silvicultura", "#7a5900"),
        33: ("Rio, Lago e Oceano", "#2532e4"),
        21: ("Mosaico de Usos", "#ffefc3"),
    }
    assert result["status"] == "ANALYZED"
    assert result["classified_area_hectares"] == pytest.approx(1115.077, abs=0.0001)
    assert result["geometry_area_hectares"] == pytest.approx(1115.1093)
    for item in result["classes"]:
        assert (item["name"], item["color"]) == expected[item["code"]]
    assert result["classes"][0]["percent_classified"] == pytest.approx(78.09, abs=0.01)


def test_public_mapbiomas_preview_and_pdf_disabled_even_with_server_credentials(monkeypatch):
    monkeypatch.setattr(routes, "get_settings", lambda: SimpleNamespace(gee_browser_preview_enabled=False))
    monkeypatch.setattr(routes, "mapbiomas_preview",
                        lambda *args, **kwargs: pytest.fail("Billed GEE call invoked"))
    payload = routes.MapBiomasPreviewRequest(geometry=SUBJECT, year=2025)
    with pytest.raises(HTTPException) as preview:
        routes.rural_mapbiomas_preview(payload)
    assert preview.value.status_code == 503
    from uuid import uuid4
    body = routes.MapBiomasPdfRequest(
        subject=routes.RuralPreviewPdfRequest(retrieval="LOCAL_VECTOR",
                                               feature_id=str(uuid4())),
        year=2025,
    )
    with pytest.raises(HTTPException) as pdf:
        routes.rural_mapbiomas_pdf(body, db=object())
    assert pdf.value.status_code == 503


def test_gee_status_stays_disabled_for_browser_during_server_canary(monkeypatch, tmp_path):
    fake_key = tmp_path / "service-account.json"
    fake_key.write_text('{"private_key":"not_a_real_key"}')
    monkeypatch.setattr(mb, "get_settings", lambda: SimpleNamespace(
        gee_enabled=True,
        gee_browser_preview_enabled=False,
        gee_project_id="amazonika-geoespacial",
        gee_service_account_email="canary@example.com",
        gee_service_account_key_file=str(fake_key),
    ))
    result = mb.gee_configuration()
    assert result["enabled"] is False
    assert "private_key" not in str(result)


def test_preliminary_pdf_adds_class_bars_without_inventing_spatial_map():
    from datetime import datetime, timezone
    from app.services.rural_mapbiomas_pdf import mapbiomas_pdf, MapBiomasClassBars
    data = mb._normalize_statistics(
        {"groups": [
            {"class": 11, "sum": 870.7678},
            {"class": 6, "sum": 215.6480},
            {"class": 3, "sum": 18.1312},
            {"class": 9, "sum": 8.0247},
            {"class": 33, "sum": 1.3431},
            {"class": 21, "sum": 1.1622},
        ]}, 2025, 1115.1093,
    )
    plot = MapBiomasClassBars(data["classes"])
    assert plot.height > 0 and len(plot.classes) == 6
    doc = mapbiomas_pdf(
        property_name="Imóvel teste",
        cadastral_source="SICAR",
        cadastral_code="Reservado",
        report=data,
        generated_at=datetime(2026, 11, 5, tzinfo=timezone.utc),
    )
    assert doc.startswith(b"%PDF")
    assert len(doc) > 2500
    # The real canary PDF revealed an orphan "3. Participação por classe"
    # heading on page one. Keep heading, bars and caption on the same page.
    from io import BytesIO
    from pypdf import PdfReader
    pages = [page.extract_text() or "" for page in PdfReader(BytesIO(doc)).pages]
    for index, page in enumerate(pages):
        if "3. Participação por classe" in page:
            assert "11 — Campo Alagado e Área Pantanosa" in page
            assert "Gráfico de participação relativa" in page
            break
    else:
        pytest.fail("Cabeçalho da participação por classe ausente")
