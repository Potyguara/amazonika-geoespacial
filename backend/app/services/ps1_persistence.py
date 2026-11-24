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

def same_perimeter_cyclic(expected, actual):
    """Mesma sequencia e atributos, admitindo apenas outro vertice inicial.

    A ordem de percurso nunca e invertida. A correspondencia de cada vertice
    permanece subordinada ao comparador estrito same_vertex existente.
    """
    if not isinstance(expected, (list, tuple)) or not isinstance(actual, (list, tuple)):
        return False
    n = len(expected)
    if n < 3 or len(actual) != n:
        return False
    if any(not isinstance(p, dict) for p in expected) or any(not isinstance(p, dict) for p in actual):
        return False
    def code(p):
        return str(p.get("sigef_vertex_code") or p.get("name") or "").strip()
    original_codes = [code(p) for p in expected]
    new_codes = [code(p) for p in actual]
    if (any(not code for code in original_codes + new_codes)
            or len(set(original_codes)) != n or len(set(new_codes)) != n):
        return False
    try:
        offset = original_codes.index(new_codes[0])
    except ValueError:
        return False
    if new_codes != original_codes[offset:] + original_codes[:offset]:
        return False
    return all(same_vertex(expected[(offset+i) % n], actual[i]) for i in range(n))

