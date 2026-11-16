"""GEO-90B: experimental XYZ PNG tiles from one explicitly allowlisted INPE COG.

No public port, no arbitrary remote URLs, no SIGEF positioning/certification.
Deployment must be restricted to the GEO83 homology network and later routed
through authenticated FastAPI; this service is not a public-facing API.
"""
from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from math import atan, degrees, exp, pi, sinh
from threading import BoundedSemaphore
from collections import OrderedDict
from threading import Lock
import re
from urllib.request import Request, urlopen
from urllib.parse import urlparse
from urllib.error import URLError, HTTPError
import json

from PIL import Image
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.env import Env
from rasterio.vrt import WarpedVRT
from rasterio.windows import from_bounds
from rasterio.warp import transform_bounds

COG = (
    "https://data.inpe.br/bdc/data/CB4A-WPM-PCA-FUSED/"
    "v001/214/113/2026/10/"
    "CBERS4A_WPM_PCA_RGB321_20261016_214_113.tif"
)
SCENE_ID = "CBERS4A_WPM_PCA_RGB321_20261016_214_113"
# Fixed scene IDs, but actual COG locations must come from the INPE STAC tci asset.
# Historical file locations must NEVER be inferred from YYYY/MM.
SCENE_COGS = {
    SCENE_ID: COG,
    "CBERS4A_WPM_PCA_RGB321_20260815_214_113": None,
    "CBERS4A_WPM_PCA_RGB321_20260715_214_113": None,
}
STAC_COLLECTION = "CB4A-WPM-PCA-FUSED-1"
STAC_PREFIX = "https://data.inpe.br/bdc/stac/v1/collections/"
ASSET_PREFIX = "https://data.inpe.br/bdc/data/CB4A-WPM-PCA-FUSED/"
ASSET_LOCK = Lock()
RESOLVED_ASSETS = {SCENE_ID: COG}


def resolve_scene_cog(scene_id: str) -> str:
    """Fetch the authoritative tci asset for a fixed, allowlisted scene ID.

    No dynamic host, path, redirect or user-supplied asset is accepted.
    A 404 is explicit; do not turn a missing scene into the October image.
    """
    if scene_id not in SCENE_COGS:
        raise ValueError("Cena não autorizada.")
    with ASSET_LOCK:
        if scene_id in RESOLVED_ASSETS:
            return RESOLVED_ASSETS[scene_id]
        item_url = (
            STAC_PREFIX + STAC_COLLECTION + "/items/" + scene_id
        )
        request = Request(item_url, headers={
            "Accept": "application/geo+json, application/json",
            "User-Agent": "Amazonika-GEO98/1.1",
        })
        # Fixed official host, with redirects not allowed to arbitrary domains.
        from urllib.request import build_opener, HTTPRedirectHandler
        class NoRedirect(HTTPRedirectHandler):
            def redirect_request(self, request, fp, code, msg, headers, newurl):
                return None
        try:
            with build_opener(NoRedirect).open(request, timeout=15) as response:
                raw = response.read(1_000_001)
        except (HTTPError, URLError, TimeoutError) as exc:
            raise RuntimeError("Item STAC do INPE indisponível: " + scene_id) from exc
        if len(raw) > 1_000_000:
            raise RuntimeError("Metadados STAC excederam o limite.")
        item = json.loads(raw)
        if not isinstance(item, dict) or item.get("id") != scene_id:
            raise RuntimeError("Item STAC inesperado.")
        tci = (item.get("assets") or {}).get("tci")
        href = tci.get("href") if isinstance(tci, dict) else None
        parsed = urlparse(href) if isinstance(href, str) else None
        if (
            parsed is None or parsed.scheme != "https"
            or parsed.netloc != "data.inpe.br"
            or parsed.username or parsed.password
            or parsed.query or parsed.fragment
            or not parsed.path.startswith("/bdc/data/CB4A-WPM-PCA-FUSED/")
            or not parsed.path.endswith("/" + scene_id + ".tif")
        ):
            raise RuntimeError("Asset COG fora da origem, coleção ou ID autorizados.")
        RESOLVED_ASSETS[scene_id] = href
        return href


# From INPE STAC scene bbox; use an initial geographical guard even before GDAL.
W, S, E, N = -51.251767, -0.504223, -50.256565, 0.471441
MAX_CONCURRENT = BoundedSemaphore(1)
MAX_WAITERS = BoundedSemaphore(16)
CACHE = OrderedDict()
CACHE_LOCK = Lock()
CACHE_LIMIT = 128
MAX_PNG_BYTES = 500_000
MAX_ZOOM = 18
MIN_ZOOM = 10
TILE_RE = re.compile(
    r"^/tiles/(?:(CBERS4A_WPM_PCA_RGB321_\d{8}_214_113)/)?"
    r"(1[0-8])/(\d{1,7})/(\d{1,7})\.png$"
)


def tile_lonlat_bbox(z: int, x: int, y: int):
    if not MIN_ZOOM <= z <= MAX_ZOOM or not 0 <= x < 2**z or not 0 <= y < 2**z:
        raise ValueError("XYZ fora dos limites.")
    def lon(ix): return ix / (2 ** z) * 360.0 - 180.0
    def lat(iy): return degrees(atan(sinh(pi * (1 - 2 * iy / 2 ** z))))
    return lon(x), lat(y + 1), lon(x + 1), lat(y)


def intersects_scene(z: int, x: int, y: int):
    w, s, e, n = tile_lonlat_bbox(z, x, y)
    return w < E and e > W and s < N and n > S


def png_tile(z: int, x: int, y: int, scene_id: str = SCENE_ID):
    if scene_id not in SCENE_COGS:
        raise ValueError("Cena não autorizada.")
    if not intersects_scene(z, x, y):
        raise ValueError("Tile fora da cena autorizada.")
    w, s, e, n = tile_lonlat_bbox(z, x, y)
    merc = transform_bounds("EPSG:4326", "EPSG:3857", w, s, e, n, densify_pts=2)
    with Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
        GDAL_HTTP_MAX_RETRY="1",
        GDAL_HTTP_CONNECTTIMEOUT="10",
        GDAL_HTTP_TIMEOUT="25",
        VSI_CACHE="FALSE",
        GDAL_NUM_THREADS="1",
    ):
        with rasterio.open("/vsicurl/" + resolve_scene_cog(scene_id)) as src:
            with WarpedVRT(src, crs="EPSG:3857", resampling=Resampling.bilinear) as vrt:
                window = from_bounds(*merc, transform=vrt.transform)
                data = vrt.read(
                    indexes=(1, 2, 3),
                    window=window,
                    out_shape=(3, 256, 256),
                    resampling=Resampling.bilinear,
                    masked=True,
                )
    # COG is verified RGB uint8; alpha 0 for nodata.
    rgb = data.filled(0).transpose(1, 2, 0)
    valid = ~np.ma.getmaskarray(data).all(axis=0)
    alpha = (valid.astype("uint8") * 255)
    image = Image.fromarray(rgb, "RGB").convert("RGBA")
    image.putalpha(Image.fromarray(alpha, "L"))
    output = BytesIO()
    image.save(output, "PNG", optimize=True)
    return output.getvalue()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            return self.respond(200, b'{"status":"ok","scene":"allowlisted"}', "application/json")
        match = TILE_RE.fullmatch(self.path)
        if not match:
            return self.respond(404, b'{"error":"not found"}', "application/json")
        scene_id = match.group(1) or SCENE_ID
        if scene_id not in SCENE_COGS:
            return self.respond(404, b'{"error":"scene unavailable"}', "application/json")
        z, x, y = map(int, match.groups()[1:])
        try:
            if not intersects_scene(z, x, y):
                return self.respond(404, b'{"error":"outside scene"}', "application/json")
        except ValueError:
            return self.respond(422, b'{"error":"invalid xyz"}', "application/json")
        key = (scene_id, z, x, y)
        with CACHE_LOCK:
            result = CACHE.get(key)
            if result is not None:
                CACHE.move_to_end(key)
        if result is not None:
            return self.respond(200, result, "image/png", max_age=600)
        if not MAX_WAITERS.acquire(blocking=False):
            return self.respond(503, b'{"error":"renderer queue full"}', "application/json")
        if not MAX_CONCURRENT.acquire(timeout=110):
            MAX_WAITERS.release()
            return self.respond(503, b'{"error":"renderer busy"}', "application/json")
        try:
            # Second lookup: another worker might already have rendered the same tile.
            with CACHE_LOCK:
                result = CACHE.get(key)
                if result is not None:
                    CACHE.move_to_end(key)
            if result is None:
                try:
                    result = png_tile(z, x, y, scene_id)
                except Exception:
                    return self.respond(502, b'{"error":"remote raster unavailable"}', "application/json")
                if len(result) > MAX_PNG_BYTES:
                    return self.respond(502, b'{"error":"tile too large"}', "application/json")
                with CACHE_LOCK:
                    CACHE[key] = result
                    CACHE.move_to_end(key)
                    while len(CACHE) > CACHE_LIMIT:
                        CACHE.popitem(last=False)
        finally:
            MAX_CONCURRENT.release()
            MAX_WAITERS.release()
        return self.respond(200, result, "image/png", max_age=600)

    def respond(self, status: int, body: bytes, content_type: str, max_age=0):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", f"private, max-age={max_age}" if max_age else "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8090), Handler).serve_forever()
