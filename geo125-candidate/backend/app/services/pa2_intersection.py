"""Interseção de duas retas de apoio para vértice V (PA2), pré-cálculo.

As quatro coordenadas UTM precisam ter o mesmo CRS e origem verificada.
Não infere precisão ou altitude a partir de RMS de vetores GNSS.
A saída NÃO pode ser exportada diretamente para SIGEF sem validação técnica.
"""
from __future__ import annotations

import math


def intersect_pa2(
    witnesses: list[dict], *,
    utm_zone: int | None = None,
    hemisphere: str | None = None,
    sirgas2000_confirmed: bool = False,
) -> dict:
    if len(witnesses) != 4:
        raise ValueError("PA2 exige dois alinhamentos, cada qual com dois marcos de apoio (4 no total).")
    names = [str(p.get("name") or "").strip() for p in witnesses]
    if len(set(names)) != 4 or any(not n for n in names):
        raise ValueError("Os quatro marcos testemunhos devem ser distintos e identificados.")
    points: list[tuple[float, float]] = []
    for p in witnesses:
        try:
            e, n = float(p["easting_m"]), float(p["northing_m"])
        except (KeyError, ValueError, TypeError) as e:
            raise ValueError("Cada testemunho precisa de coordenadas UTM E e N.") from e
        if not math.isfinite(e) or not math.isfinite(n):
            raise ValueError("Coordenadas não finitas.")
        points.append((e, n))
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = points
    ux, uy = bx - ax, by - ay
    vx, vy = dx - cx, dy - cy
    lu, lv = math.hypot(ux, uy), math.hypot(vx, vy)
    if lu < 0.01 or lv < 0.01:
        raise ValueError("Um alinhamento possui distância nula ou insuficiente.")
    cross = ux * vy - uy * vx
    sin_angle = abs(cross / (lu * lv))
    if sin_angle < math.sin(math.radians(5)):
        raise ValueError("Alinhamentos paralelos ou quase paralelos: interseção mal condicionada.")
    wx, wy = cx - ax, cy - ay
    t = (wx * vy - wy * vx) / cross
    u = (wx * uy - wy * ux) / cross
    x, y = ax + t * ux, ay + t * uy
    if not all(math.isfinite(z) for z in (x, y, t, u)):
        raise ValueError("Interseção numericamente inválida.")
    if abs(t) > 100 or abs(u) > 100:
        raise ValueError("Interseção muito distante dos marcos de apoio.")
    warnings = [
        "Coordenadas de interseção são preliminares: confirmar referencial, época, alinhamentos e realidade de campo.",
        "O cálculo PA2 não determina automaticamente a altitude h nem os sigmas sem metodologia altimétrica e covariâncias dos marcos.",
    ]
    longitude = latitude = None
    if sirgas2000_confirmed:
        if hemisphere not in ("N", "S") or not isinstance(utm_zone, int):
            raise ValueError("Confirme o hemisfério e zona UTM do SIRGAS2000.")
        if hemisphere == "N" and 18 <= utm_zone <= 22:
            epsg = 31954 + utm_zone
        elif hemisphere == "S" and 18 <= utm_zone <= 25:
            epsg = 31960 + utm_zone
        else:
            raise ValueError("Zona UTM fora da faixa SIRGAS2000 prevista no sistema.")
        from pyproj import Transformer
        longitude, latitude = Transformer.from_crs(
            f"EPSG:{epsg}", "EPSG:4674", always_xy=True,
        ).transform(x, y)
    else:
        warnings.append("SIRGAS2000 não confirmado: coordenadas geográficas não calculadas.")
    if t < 0 or t > 1 or u < 0 or u > 1:
        warnings.append("A interseção extrapola pelo menos um dos segmentos medidos.")
    return {
        "status": "DRAFT_REQUIRES_TECHNICAL_REVIEW",
        "method": "PA2",
        "vertex_type": "V",
        "easting_m": round(x, 4),
        "northing_m": round(y, 4),
        "longitude": longitude,
        "latitude": latitude,
        "angle_deg_acute": round(math.degrees(math.asin(sin_angle)), 4),
        "line_parameters": {"first_t": round(t, 8), "second_t": round(u, 8)},
        "height_m": None,
        "sigma_e_m": None,
        "sigma_n_m": None,
        "sigma_h_m": None,
        "witnesses": names,
        "warnings": warnings,
        "ready_for_sigef": False,
    }
