"""Comparação de perímetro PS1: tolerância apenas de serialização angular."""
from math import isfinite

KEYS = ("sigef_vertex_code", "sigef_method", "ellipsoidal_height_m",
        "sigma_lon_m", "sigma_lat_m", "sigma_h_m", "height_reference_confirmed",
        "boundary_type", "confrontant", "confrontant_cns", "confrontant_registration")


def same_vertex(a, b):
    if not isinstance(a, dict) or not isinstance(b, dict):
        return False
    for k in ("longitude", "latitude"):
        x, y = a.get(k), b.get(k)
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and isfinite(v) for v in (x, y)):
            return False
        # GeoJSON da interface grava 9 casas decimais; não é tolerância de levantamento.
        if abs(x-y) > 5.1e-10:
            return False
    for k in KEYS:
        x, y = a.get(k), b.get(k)
        if k in ("confrontant_cns", "confrontant_registration"):
            x, y = x or "", y or ""
        if x != y:
            return False
    return True


def same_perimeter(expected, actual):
    return bool(expected and len(expected) == len(actual) and
                all(same_vertex(a,b) for a,b in zip(expected,actual)))
