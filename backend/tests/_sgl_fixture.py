"""Pontos de teste definidos num plano local (e, n) em torno de Macapá."""
import math

from app.services.pa_offset_intersection import LocalFrame

ORIGIN = (-51.06, 0.03, 12.0)  # lon, lat, h
_FRAME = LocalFrame([ORIGIN])


def P(name, e, n, s=None, h=12.0, sh=None):
    lon, lat = _FRAME.geodetic_at_height(e, n, h)
    d = {"name": name, "latitude": lat, "longitude": lon, "ellipsoidal_height_m": h}
    if s is not None:
        d.update(sigma_e_m=s, sigma_n_m=s)
    if sh is not None:
        d["sigma_h_m"] = sh
    return d


def local(result):
    """(e, n) do resultado no plano local do teste, pela latitude/longitude."""
    e, n, _ = _FRAME.to_local(result["longitude"], result["latitude"], result["height_m"])
    return e, n


def close(a, b, tol=0.005):
    return all(math.isclose(x, y, abs_tol=tol) for x, y in zip(a, b))
