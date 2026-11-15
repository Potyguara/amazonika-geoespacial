"""GEO89 — inserção de ponto V sobre linha de dois marcos, com relatório analítico.

Difere da interseção PA2 de quatro testemunhos. A variante segue o fluxo de
inserção assistida por segmento descrito na documentação do Métrica TOPO;
o resultado permanece provisório, sujeito a comprovação técnica.
"""
from __future__ import annotations
import math
from pyproj import Transformer


def pa2_support_line(payload: dict) -> dict:
    supports = payload.get("supports")
    if not isinstance(supports, list) or len(supports) != 2:
        raise ValueError("Selecione exatamente dois marcos de apoio.")
    names = [str(p.get("name", "")).strip() for p in supports]
    if not all(names) or names[0] == names[1]:
        raise ValueError("Marcos de apoio devem ser distintos.")
    if payload.get("sirgas2000_confirmed") is not True:
        raise ValueError("Confirme referencial SIRGAS2000 antes de posicionar o vértice.")
    zone, hemi = payload.get("utm_zone"), payload.get("hemisphere")
    if not isinstance(zone, int) or hemi not in ("N", "S"):
        raise ValueError("Informe zona UTM e hemisfério consistentes.")
    if hemi == "N" and 18 <= zone <= 22:
        epsg = 31954 + zone
    elif hemi == "S" and 18 <= zone <= 25:
        epsg = 31960 + zone
    else:
        raise ValueError("Zona/hemisfério fora da faixa SIRGAS2000 suportada.")
    try:
        e1, n1 = float(supports[0]["easting_m"]), float(supports[0]["northing_m"])
        e2, n2 = float(supports[1]["easting_m"]), float(supports[1]["northing_m"])
        lon, lat = float(payload["hint_longitude"]), float(payload["hint_latitude"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Coordenadas de apoio ou clique indisponíveis.") from exc
    if not all(math.isfinite(z) for z in (e1, n1, e2, n2, lon, lat)):
        raise ValueError("Coordenadas não finitas.")
    transform = Transformer.from_crs("EPSG:4674", f"EPSG:{epsg}", always_xy=True)
    pe, pn = transform.transform(lon, lat)
    dx, dy = e2 - e1, n2 - n1
    ab2 = dx*dx + dy*dy
    if ab2 < 0.01:
        raise ValueError("Linha de apoio muito curta.")
    t = ((pe-e1)*dx + (pn-n1)*dy)/ab2
    if t < 0 or t > 1:
        raise ValueError("Clique está fora do segmento entre os marcos de apoio.")
    e, n = e1 + t*dx, n1 + t*dy
    offset = math.hypot(pe-e, pn-n)
    if offset > max(20.0, math.sqrt(ab2)*0.08):
        raise ValueError("Clique muito distante da linha de apoio; amplie o mapa e tente novamente.")
    final_lon, final_lat = Transformer.from_crs(
        f"EPSG:{epsg}", "EPSG:4674", always_xy=True,
    ).transform(e, n)
    kind = payload.get("altitude_type")
    if kind not in ("HN", "H"):
        raise ValueError("Defina um modelo físico único: HN ou H.")
    try:
        h1 = float(supports[0]["physical_altitude_m"])
        h2 = float(supports[1]["physical_altitude_m"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("Os dois marcos precisam ter altitude física calculada.") from exc
    if not (math.isfinite(h1) and math.isfinite(h2)):
        raise ValueError("Altitudes inválidas.")
    physical_h = h1 + t*(h2-h1)

    def avg_sigma(key: str):
        try:
            v = [float(p[key]) for p in supports]
        except (ValueError, TypeError, KeyError):
            return None
        if any(not math.isfinite(x) or x < 0 for x in v):
            return None
        # Modelo de média aritmética apresentado no relatório analítico fornecido
        # pelo usuário; não representa propagação de covariância completa.
        return (v[0] + v[1])/2

    sigma_e, sigma_n, sigma_h = (
        avg_sigma("sigma_e_m"), avg_sigma("sigma_n_m"), avg_sigma("sigma_h_m")
    )
    return {
        "status": "DRAFT_REQUIRES_TECHNICAL_REVIEW",
        "method": "PA2", "operation": "SUPPORT_LINE_PROJECTION",
        "vertex_type": "V", "easting_m": round(e,4),
        "northing_m": round(n,4), "longitude": final_lon,
        "latitude": final_lat, "height_m": None,
        "physical_altitude_type": kind,
        "physical_altitude_m": round(physical_h,4),
        "sigma_e_m": sigma_e, "sigma_n_m": sigma_n,
        "sigma_h_m": sigma_h, "ready_for_sigef": False,
        "angle_deg_acute": None,
        "witnesses": names, "fraction": t,
        "distance_a_v_m": round(t*math.sqrt(ab2),4),
        "distance_a_b_m": round(math.sqrt(ab2),4),
        "click_offset_m": round(offset,4),
        "warnings": [
            "Interpolação altimétrica efetuada entre altitudes físicas HN/H dos marcos A/B.",
            "A altura elipsoidal h do novo vértice exige fator/modelo específico; não é igual à altitude física interpolada.",
            "Sigmas apresentados por média aritmética do relatório analítico de referência, apenas quando informados para ambos os marcos; revisar metodologia e precisão antes da certificação.",
            "Inserção por projeção em linha de apoio; confirmar enquadramento no método PA2 e evidências de campo pelo responsável técnico.",
        ],
    }
