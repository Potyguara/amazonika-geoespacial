"""Offline cartographic thumbnail tests. No CAR, GEE, or internet calls."""
from io import BytesIO
from types import SimpleNamespace

from PIL import Image
import pytest

from app.services import rural_mapbiomas_cartography as cm
from app.services import rural_mapbiomas as mb

SUBJECT = {"type": "Polygon", "coordinates": [[
    [-51.20, 0.030], [-51.18, 0.030], [-51.18, 0.049],
    [-51.20, 0.049], [-51.20, 0.030],
]]}


def _sample_png(width=10, height=10):
    buffer = BytesIO()
    Image.new("RGBA", (width, height), (30, 125, 80, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


def test_thumbnail_limits_and_aspect_ratio():
    w, h = cm._thumbnail_dimensions((-51.2, 0.03, -51.18, 0.049))
    assert 0 < w <= 640 and 0 < h <= 640
    assert w * h <= cm.MAX_THUMB_PIXELS


def test_thumbnail_rejects_unverified_class_without_authenticating(monkeypatch):
    monkeypatch.setattr(cm, "_initialize_gee", lambda: pytest.fail("GEE called"))
    with pytest.raises(ValueError, match="sem cor oficial"):
        cm.fetch_mapbiomas_thematic_thumbnail(
            SUBJECT, year=2025, class_codes=[999]
        )


def test_actual_png_thumbnail_uses_real_class_asset_without_storing(monkeypatch):
    requests = []
    class FakeImage:
        def select(self, key):
            requests.append(("select", key))
            return self
        def remap(self, src, dst, default):
            requests.append(("remap", list(src), list(dst), default))
            return self
        def updateMask(self, mask): return self
        def neq(self, value): return self
        def clip(self, roi):
            requests.append(("clip", True))
            return self
        def visualize(self, **kwargs):
            requests.append(("palette", kwargs["palette"]))
            return self
        def getThumbURL(self, opts):
            requests.append(("thumb", opts))
            return "https://earthengine.googleapis.com/v1/projects/test/thumbnails/sample"
    class FakeEE:
        Geometry = staticmethod(lambda geom, **kwargs: geom)
        Image = staticmethod(lambda asset: FakeImage())
    FakeEE.Geometry.Rectangle = lambda *a, **kw: {"bbox": True}
    monkeypatch.setattr(cm, "_initialize_gee", lambda: FakeEE)
    class FakeResponse:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            requests.append(("read_limit", limit))
            return _sample_png()
    monkeypatch.setattr(cm, "urlopen", lambda url, timeout: FakeResponse())
    result = cm.fetch_mapbiomas_thematic_thumbnail(
        SUBJECT, year=2025, class_codes=[11, 6, 3],
    )
    assert result.width == 10 and result.height == 10
    assert result.png.startswith(bytes.fromhex("89504e470d0a1a0a"))
    assert ("select", "classification_2025") in requests
    assert ("clip", True) in requests
    assert any(item[0] == "thumb" for item in requests)
    thumb_options = next(item[1] for item in requests if item[0] == "thumb")
    ring = thumb_options["region"]
    assert isinstance(ring, list) and len(ring) == 5
    assert ring[0] == ring[-1]
    assert ring[0] == [-51.20, 0.030]
    assert thumb_options["crs"] == "EPSG:4326"
    assert ("read_limit", cm.MAX_THUMB_BYTES + 1) in requests


def test_pdf_second_page_renders_real_pixel_thumbnail():
    from datetime import datetime, timezone
    from pypdf import PdfReader
    from app.services.rural_mapbiomas_pdf import mapbiomas_pdf
    report = mb._normalize_statistics(
        {"groups": [{"class":11, "sum":8}, {"class":6, "sum":2}]},
        2025, 10,
    )
    thumb = cm.ThematicThumbnail(
        png=_sample_png(120, 100),
        bounds=(-51.2, 0.03, -51.18, 0.049),
        width=120, height=100, year=2025, class_codes=(6,11),
    )
    output = mapbiomas_pdf(
        property_name="Teste", cadastral_source="SICAR", cadastral_code="Reservado",
        report=report, generated_at=datetime(2026, 11, 5, tzinfo=timezone.utc),
        thematic_map=thumb,
    )
    reader = PdfReader(BytesIO(output))
    assert len(reader.pages) >= 2
    text = "\n".join(page.extract_text() for page in reader.pages)
    assert "Mapa temático" in text
    assert "não substitui planta georreferenciada" in text


def test_ee_thumbnail_request_failure_has_safe_stage_not_remote_details(monkeypatch):
    class FakeImage:
        def select(self, *a): return self
        def remap(self, *a): return self
        def updateMask(self, *a): return self
        def neq(self, *a): return self
        def clip(self, *a): return self
        def visualize(self, **kw): return self
        def getThumbURL(self, *a):
            raise RuntimeError("secret-token-and-url-should-never-leak")
    class FakeEE:
        Geometry = staticmethod(lambda *a, **kw: None)
        Image = staticmethod(lambda *a: FakeImage())
    FakeEE.Geometry.Rectangle = lambda *a, **kw: None
    monkeypatch.setattr(cm, "_initialize_gee", lambda: FakeEE)
    with pytest.raises(RuntimeError, match="EE_GET_THUMB_URL") as exc:
        cm.fetch_mapbiomas_thematic_thumbnail(
            SUBJECT, year=2025, class_codes=[11, 6]
        )
    assert "secret-token" not in str(exc.value)


def test_ee_thumbnail_unapproved_host_rejected_without_download(monkeypatch):
    class FakeImage:
        def select(self, *a): return self
        def remap(self, *a): return self
        def updateMask(self, *a): return self
        def neq(self, *a): return self
        def clip(self, *a): return self
        def visualize(self, **kw): return self
        def getThumbURL(self, *a): return "https://example.invalid/secret-token"
    class FakeEE:
        Geometry = staticmethod(lambda *a, **kw: None)
        Image = staticmethod(lambda *a: FakeImage())
    FakeEE.Geometry.Rectangle = lambda *a, **kw: None
    monkeypatch.setattr(cm, "_initialize_gee", lambda: FakeEE)
    monkeypatch.setattr(cm, "urlopen", lambda *a, **kw: pytest.fail("Downloaded untrusted host"))
    with pytest.raises(RuntimeError, match="EE_THUMB_HOST") as exc:
        cm.fetch_mapbiomas_thematic_thumbnail(
            SUBJECT, year=2025, class_codes=[11, 6]
        )
    assert "secret-token" not in str(exc.value)
