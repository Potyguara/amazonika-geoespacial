"""GEO-90B: experimental XYZ PNG tiles from one explicitly allowlisted INPE COG.

No public port, no arbitrary remote URLs, no SIGEF positioning/certification.
Deployment must be restricted to the GEO83 homology network and later routed
through authenticated FastAPI; this service is not a public-facing API.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from math import atan, degrees, exp, pi, sinh
from threading import BoundedSemaphore
import json
import re

from PIL import Image
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
# From INPE STAC scene bbox; use an initial geographical guard even before GDAL.
W, S, E, N = -51.251767, -0.504223, -50.256565, 0.471441
MAX_CONCURRENT = BoundedSemaphore(1)
MAX_ZOOM = 18
MIN_ZOOM = 10
TILE_RE = re.compile(r"^/tiles/(1[0-8])/(\d{1,7})/(\d{1,7})\.png$")


def tile_lonlat_bbox(z: int, x: int, y: int):
    if not MIN_ZOOM <= z <= MAX_ZOOM or not 0 <= x < 2**z or not 0 <= y < 2**z:
        raise ValueError("XYZ fora dos limites.")
    def lon(ix): return ix / (2 ** z) * 360.0 - 180.0
    def lat(iy): return degrees(atan(sinh(pi * (1 - 2 * iy / 2 ** z))))
    return lon(x), lat(y + 1), lon(x + 1), lat(y)


def intersects_scene(z: int, x: int, y: int):
    w, s, e, n = tile_lonlat_bbox(z, x, y)
    return w < E and e > W and s < N and n > S


def png_tile(z: int, x: int, y: int):
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
        with rasterio.open("/vsicurl/" + COG) as src:
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
    mask = ~data.mask.all(axis=0) if hasattr(data.mask, "all") else None
    alpha = (mask.astype("uint8") * 255) if mask is not None else None
    image = Image.fromarray(rgb, "RGB").convert("RGBA")
    if alpha is not None:
        image.putalpha(Image.fromarray(alpha, "L"))
    output = BytesIO()
    image.save(output, "PNG", optimize=True)
    return output.getvalue()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            return self.respond(200, b'{"status":"ok","scene":"fixed"}', "application/json")
        match = TILE_RE.fullmatch(self.path)
        if not match:
            return self.respond(404, b'{"error":"not found"}', "application/json")
        z, x, y = map(int, match.groups())
        try:
            if not intersects_scene(z, x, y):
                return self.respond(404, b'{"error":"outside scene"}', "application/json")
        except ValueError:
            return self.respond(422, b'{"error":"invalid xyz"}', "application/json")
        if not MAX_CONCURRENT.acquire(blocking=False):
            return self.respond(429, b'{"error":"renderer busy"}', "application/json")
        try:
            try:
                result = png_tile(z, x, y)
            except Exception:
                return self.respond(502, b'{"error":"remote raster unavailable"}', "application/json")
        finally:
            MAX_CONCURRENT.release()
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
