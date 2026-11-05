"""Verify CAR WFS exact lookup behavior without contacting a public service."""
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from app.services import rural_official_car as car

CODE = "AP-1600303-" + "A" * 32
POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [[-51.3, -0.4], [-51.2, -0.4], [-51.2, -0.3], [-51.3, -0.3], [-51.3, -0.4]]
    ],
}


class FakeResponse:
    def __init__(self, features):
        self.headers = {"Content-Type": "application/json; charset=utf-8"}
        self.payload = json.dumps({"type": "FeatureCollection", "features": features}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, length):
        return self.payload[:length]


def feature(code=CODE, geometry=POLYGON):
    return {
        "type": "Feature",
        "properties": {
            "cod_imovel": code, "area": 100.5, "status_imovel": "AT",
            "data_atualizacao": "2026-10-31T11:00:00Z",
        },
        "geometry": geometry,
    }


def test_car_format_and_state_validation():
    assert car.normalize_car("ap-1600303-" + "a" * 32) == CODE
    for invalid in ["AP-XYZ", "XX-1600303-" + "A" * 32,
                    "AP-1600303-' OR 1=1 --", "AP-1600303-" + "G" * 32]:
        with pytest.raises(ValueError):
            car.normalize_car(invalid)


def test_exact_server_side_lookup_never_scans_entire_state(monkeypatch):
    seen = {}

    def network(request, timeout):
        seen["url"] = request.full_url
        return FakeResponse([feature()])

    monkeypatch.setattr(car, "urlopen", network)
    candidate = car.fetch_car_candidate(CODE)
    query = parse_qs(urlsplit(seen["url"]).query)
    assert query["TYPENAME"] == ["sicar:sicar_imoveis_ap"]
    assert query["CQL_FILTER"] == [f"cod_imovel='{CODE}'"]
    assert query["MAXFEATURES"] == ["2"]
    assert candidate["retrieval"] == "OFFICIAL_CAR_WFS"
    assert candidate["cadastral_code"] == CODE
    assert candidate["declared_area_hectares"] == 100.5
    assert candidate["area_hectares"] > 0


def test_explicit_no_result_is_not_an_exception(monkeypatch):
    monkeypatch.setattr(car, "urlopen", lambda *args, **kwargs: FakeResponse([]))
    assert car.fetch_car_candidate(CODE) is None


def test_wrong_car_code_in_response_is_rejected(monkeypatch):
    monkeypatch.setattr(car, "urlopen", lambda *args, **kwargs:
                        FakeResponse([feature("AP-1600303-" + "B" * 32)]))
    with pytest.raises(car.OfficialCarQueryError, match="divergente"):
        car.fetch_car_candidate(CODE)


def test_retrieve_checks_geometry_fingerprint_again(monkeypatch):
    current = [feature()]
    monkeypatch.setattr(car, "urlopen", lambda *args, **kwargs: FakeResponse(current))
    candidate = car.fetch_car_candidate(CODE)
    verified = car.resolve_car_candidate(CODE, candidate["feature_id"])
    assert verified["geometry"]["type"] == "Polygon"
    current[0] = feature(CODE, {
        "type": "Polygon",
        "coordinates": [[[-51.31, -.4], [-51.2, -.4], [-51.2, -.3], [-51.31, -.4]]],
    })
    with pytest.raises(car.OfficialCarQueryError, match="mudou"):
        car.resolve_car_candidate(CODE, candidate["feature_id"])


def test_upstream_unavailable_never_becomes_no_car(monkeypatch):
    monkeypatch.setattr(car, "urlopen", lambda *args, **kwargs:
                        (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(car.OfficialCarQueryError, match="indisponível"):
        car.fetch_car_candidate(CODE)


def test_ogc_xml_error_is_rejected(monkeypatch):
    class XmlResponse:
        headers = {"Content-Type": "text/xml"}
        def __enter__(self): return self
        def __exit__(self, *_): return False
        def read(self, n):
            return b'<ServiceExceptionReport><ServiceException>Layer unavailable</ServiceException></ServiceExceptionReport>'
    monkeypatch.setattr(car, "urlopen", lambda *args, **kwargs: XmlResponse())
    with pytest.raises(car.OfficialCarQueryError, match="Layer unavailable"):
        car.fetch_car_candidate(CODE)


def test_multiple_features_fail_closed(monkeypatch):
    monkeypatch.setattr(car, "urlopen", lambda *args, **kwargs:
                        FakeResponse([feature(), feature()]))
    with pytest.raises(car.OfficialCarQueryError, match="múltiplos"):
        car.fetch_car_candidate(CODE)


def test_python_handshake_failure_falls_back_to_verified_curl(monkeypatch):
    import ssl
    from urllib.error import URLError
    from types import SimpleNamespace
    seen = {}

    def fail_python(*args, **kwargs):
        raise URLError(ssl.SSLError("SSLV3_ALERT_HANDSHAKE_FAILURE"))

    def fake_curl(argv, **kwargs):
        seen["argv"] = argv
        seen["kwargs"] = kwargs
        from pathlib import Path
        Path(argv[argv.index("--output") + 1]).write_bytes(
            json.dumps({"type":"FeatureCollection", "features":[feature()]}).encode()
        )
        return SimpleNamespace(returncode=0, stdout=b"application/json", stderr=b"")

    monkeypatch.setattr(car, "urlopen", fail_python)
    monkeypatch.setattr(car.subprocess, "run", fake_curl)
    candidate = car.fetch_car_candidate(CODE)
    assert candidate["retrieval"] == "OFFICIAL_CAR_WFS"
    argv = seen["argv"]
    assert argv[0] == "curl"
    assert argv[argv.index("--proto") + 1] == "=https"
    assert "--insecure" not in argv and "-k" not in argv
    assert argv[-1].startswith(car.SICAR_WFS)
    assert "CQL_FILTER=" in argv[-1]
    assert seen["kwargs"]["timeout"] == 30
    assert seen["kwargs"]["check"] is False


def test_certificate_error_never_falls_back_to_curl(monkeypatch):
    import ssl
    from urllib.error import URLError

    def reject(*args, **kwargs):
        raise URLError(ssl.SSLCertVerificationError("CERTIFICATE_VERIFY_FAILED"))

    monkeypatch.setattr(car, "urlopen", reject)
    monkeypatch.setattr(car.subprocess, "run",
                        lambda *a, **kw: pytest.fail("curl called after cert failure"))
    with pytest.raises(car.OfficialCarQueryError, match="certificado"):
        car.fetch_car_candidate(CODE)


def test_curl_nonzero_exit_never_becomes_empty_car(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(car.subprocess, "run",
        lambda *a, **kw: SimpleNamespace(returncode=60, stdout=b"", stderr=b"private"))
    with pytest.raises(car.OfficialCarQueryError, match="curl código 60"):
        car._curl_verified_https(car.SICAR_WFS)


def test_curl_oversize_response_rejected(monkeypatch):
    from pathlib import Path
    from types import SimpleNamespace
    monkeypatch.setattr(car, "MAX_RESPONSE_BYTES", 32)
    def huge(argv, **kw):
        Path(argv[argv.index("--output") + 1]).write_bytes(b"x" * 33)
        return SimpleNamespace(returncode=0, stdout=b"application/json", stderr=b"")
    monkeypatch.setattr(car.subprocess, "run", huge)
    with pytest.raises(car.OfficialCarQueryError, match="limite seguro"):
        car._curl_verified_https(car.SICAR_WFS)
