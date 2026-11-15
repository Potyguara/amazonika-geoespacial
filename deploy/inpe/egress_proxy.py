"""GEO-90 INPE egress: fixed upstream STAC proxy; no arbitrary URL forwarding.

Exposes only GET /collections/{allowlisted}/items with a bounded bbox & limit.
No database credentials, no user-supplied upstream domain, no arbitrary assets.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit, urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
import json
import math
import os

HOST = "0.0.0.0"
PORT = 8088
ORIGIN = "https://data.inpe.br/bdc/stac/v1"
COLLECTIONS = {"CB4A-WPM-L4-DN-1", "CB4A-WPM-PCA-FUSED-1"}
MAX_BYTES = 2_000_000


def upstream_for(target: str) -> str:
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or parsed.fragment:
        raise ValueError("Invalid target.")
    parts = parsed.path.strip("/").split("/")
    if len(parts) != 3 or parts[0] != "collections" or parts[1] not in COLLECTIONS or parts[2] != "items":
        raise ValueError("Route unavailable.")
    params = parse_qs(parsed.query, keep_blank_values=True)
    if set(params) != {"bbox", "limit"} or any(len(v) != 1 for v in params.values()):
        raise ValueError("Invalid parameters.")
    bbox = [float(v) for v in params["bbox"][0].split(",")]
    limit = int(params["limit"][0])
    if len(bbox) != 4 or not all(math.isfinite(x) for x in bbox):
        raise ValueError("Invalid bbox.")
    w, s, e, n = bbox
    if not (-180 <= w < e <= 180 and -90 <= s < n <= 90 and e - w <= 1 and n - s <= 1):
        raise ValueError("Bbox outside limits.")
    if not 1 <= limit <= 20:
        raise ValueError("Limit outside range.")
    return f"{ORIGIN}/collections/{parts[1]}/items?" + urlencode({
        "bbox": ",".join(str(x) for x in bbox), "limit": limit,
    })


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            upstream = upstream_for(self.path)
        except (ValueError, KeyError, OverflowError):
            return self.reply(422, {"error": "Invalid or unsupported STAC request."})
        try:
            request = Request(upstream, headers={
                "Accept": "application/geo+json, application/json",
                "User-Agent": "Amazonika-Geoespacial-GEO90/1.0",
            })
            with urlopen(request, timeout=20) as response:
                raw = response.read(MAX_BYTES + 1)
                if len(raw) > MAX_BYTES:
                    raise ValueError("Response too large.")
                parsed = json.loads(raw)
                if not isinstance(parsed, dict) or not isinstance(parsed.get("features"), list):
                    raise ValueError("Invalid STAC response.")
                return self.reply(200, parsed)
        except HTTPError as exc:
            return self.reply(502, {"error": f"INPE HTTP {exc.code}"})
        except (URLError, TimeoutError, ValueError, json.JSONDecodeError):
            return self.reply(502, {"error": "INPE STAC unavailable or invalid."})

    def reply(self, status: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
