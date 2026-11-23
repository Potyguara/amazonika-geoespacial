"""Vértice V pela interseção de duas retas paralelas a alinhamentos medidos.

Cada reta é definida por dois pontos com coordenadas UTM conhecidas (por
exemplo, pontos P rastreados por GNSS na margem) e por um afastamento
perpendicular com lado (esquerdo/direito no sentido A→B). Afastamento zero
usa o próprio alinhamento. O vértice resulta da interseção das duas retas,
sem clique no mapa: a coordenada é determinada só por geometria analítica.

A precisão horizontal é propagada em primeira ordem (lei de propagação de
covariâncias) a partir dos desvios-padrão E/N de cada ponto de apoio e do
desvio-padrão de cada afastamento, supondo observações não correlacionadas.
A altura elipsoidal não é calculada. O resultado fica como pré-cálculo para
revisão do responsável técnico e não é marcado como pronto para o SIGEF.
"""
from __future__ import annotations

import math

from pyproj import Transformer

MIN_ANGLE_DEG = 5.0
MAX_EXTRAPOLATION = 100.0


def _finite(*values: float) -> bool:
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in values)


def _epsg(zone: int | None, hemisphere: str | None) -> int:
    if not isinstance(zone, int) or hemisphere not in ("N", "S"):
        raise ValueError("Informe zona UTM e hemisfério do SIRGAS2000.")
    if hemisphere == "N" and 18 <= zone <= 22:
        return 31954 + zone
    if hemisphere == "S" and 18 <= zone <= 25:
        return 31960 + zone
    raise ValueError("Zona/hemisfério fora da faixa SIRGAS2000 suportada.")


def _point(p: dict, label: str) -> tuple[str, float, float, float | None, float | None]:
    name = str(p.get("name") or "").strip()
    if not name:
        raise ValueError(f"{label}: ponto sem identificação.")
    try:
        e, n = float(p["easting_m"]), float(p["northing_m"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{label}: informe E e N em UTM do ponto {name}.") from exc
    if not _finite(e, n):
        raise ValueError(f"{label}: coordenadas não finitas em {name}.")

    def sigma(key: str) -> float | None:
        value = p.get(key)
        if value is None or value == "":
            return None
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) and value >= 0 else None

    return name, e, n, sigma("sigma_e_m"), sigma("sigma_n_m")


def _offset_line(ax, ay, bx, by, offset, side):
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length < 0.01:
        raise ValueError("Alinhamento com comprimento nulo.")
    sign = 1.0 if side == "LEFT" else -1.0
    nx, ny = -sign * dy / length, sign * dx / length
    return ax + nx * offset, ay + ny * offset, dx, dy


def _solve(values: list[float], sides: tuple[str, str]):
    ax, ay, bx, by, cx, cy, dx_, dy_, d1, d2 = values
    p1x, p1y, ux, uy = _offset_line(ax, ay, bx, by, d1, sides[0])
    p2x, p2y, vx, vy = _offset_line(cx, cy, dx_, dy_, d2, sides[1])
    cross = ux * vy - uy * vx
    if cross == 0:
        raise ValueError("Retas paralelas: sem interseção.")
    wx, wy = p2x - p1x, p2y - p1y
    t = (wx * vy - wy * vx) / cross
    u = (wx * uy - wy * ux) / cross
    return p1x + t * ux, p1y + t * uy, t, u, cross, math.hypot(ux, uy), math.hypot(vx, vy)


def intersect_offset_lines(
    lines: list[dict], *,
    method: str,
    utm_zone: int | None = None,
    hemisphere: str | None = None,
    sirgas2000_confirmed: bool = False,
) -> dict:
    if method not in ("PA1", "PA2"):
        raise ValueError("Código de posicionamento: informe PA1 ou PA2, conforme o enquadramento do RT.")
    if not isinstance(lines, list) or len(lines) != 2:
        raise ValueError("Informe exatamente duas retas.")
    values: list[float] = []
    sigmas: list[float | None] = []
    sides: list[str] = []
    names: list[str] = []
    offset_sigmas: list[float | None] = []
    descriptions = []
    for index, line in enumerate(lines, start=1):
        label = f"Reta {index}"
        points = line.get("points") if isinstance(line, dict) else None
        if not isinstance(points, list) or len(points) != 2:
            raise ValueError(f"{label}: informe dois pontos de apoio.")
        a, b = (_point(p, label) for p in points)
        if a[0] == b[0]:
            raise ValueError(f"{label}: os dois pontos devem ser distintos.")
        try:
            offset = float(line.get("offset_m", 0) or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label}: afastamento inválido.") from exc
        if not math.isfinite(offset) or offset < 0:
            raise ValueError(f"{label}: o afastamento deve ser zero ou positivo.")
        side = line.get("side")
        if offset > 0 and side not in ("LEFT", "RIGHT"):
            raise ValueError(f"{label}: indique o lado do afastamento (esquerdo/direito no sentido {a[0]}→{b[0]}).")
        side = side if side in ("LEFT", "RIGHT") else "LEFT"
        raw_sigma = line.get("offset_sigma_m")
        try:
            offset_sigma = float(raw_sigma) if raw_sigma not in (None, "") else (0.0 if offset == 0 else None)
        except (TypeError, ValueError):
            offset_sigma = None
        if offset_sigma is not None and (not math.isfinite(offset_sigma) or offset_sigma < 0):
            offset_sigma = None
        values += [a[1], a[2], b[1], b[2]]
        sigmas += [a[3], a[4], b[3], b[4]]
        sides.append(side)
        offset_sigmas.append(offset_sigma)
        names += [a[0], b[0]]
        descriptions.append({
            "points": [a[0], b[0]], "offset_m": offset,
            "side": side if offset > 0 else None,
            "offset_sigma_m": offset_sigma,
            "length_m": round(math.hypot(b[1] - a[1], b[2] - a[2]), 4),
        })
    offsets = [descriptions[0]["offset_m"], descriptions[1]["offset_m"]]
    all_values = values + offsets
    x, y, t, u, cross, lu, lv = _solve(all_values, (sides[0], sides[1]))
    sin_angle = abs(cross) / (lu * lv)
    if sin_angle < math.sin(math.radians(MIN_ANGLE_DEG)):
        raise ValueError(
            f"Retas quase paralelas (ângulo menor que {MIN_ANGLE_DEG:g}°): interseção mal condicionada."
        )
    if not _finite(x, y):
        raise ValueError("Interseção numericamente inválida.")
    if abs(t) > MAX_EXTRAPOLATION or abs(u) > MAX_EXTRAPOLATION:
        raise ValueError("Interseção muito distante dos pontos de apoio.")

    # Propagação de covariâncias em primeira ordem, com jacobiana numérica.
    all_sigmas = sigmas + offset_sigmas
    sigma_e = sigma_n = None
    missing = [i for i, s in enumerate(all_sigmas) if s is None]
    if not missing:
        var_e = var_n = cov_en = 0.0
        for i, s in enumerate(all_sigmas):
            if s == 0:
                continue
            step = 1e-4
            plus = list(all_values); plus[i] += step
            minus = list(all_values); minus[i] -= step
            xp, yp, *_ = _solve(plus, (sides[0], sides[1]))
            xm, ym, *_ = _solve(minus, (sides[0], sides[1]))
            jx, jy = (xp - xm) / (2 * step), (yp - ym) / (2 * step)
            var_e += (jx * s) ** 2
            var_n += (jy * s) ** 2
            cov_en += jx * jy * s * s
        sigma_e, sigma_n = math.sqrt(var_e), math.sqrt(var_n)
        sigma_hz = math.sqrt(var_e + var_n)
    else:
        sigma_hz = None

    warnings = [
        "Coordenada determinada por geometria analítica (interseção de retas), sem uso de clique no mapa.",
        "A altura elipsoidal h do vértice não é calculada por este procedimento.",
        "O enquadramento como PA1 ou PA2 é declaração do responsável técnico e deve constar do relatório técnico.",
    ]
    if missing:
        warnings.append(
            "Sigmas não propagados: falta desvio-padrão E/N de algum ponto de apoio ou de algum afastamento."
        )
    else:
        warnings.append(
            "Sigmas propagados em primeira ordem supondo observações não correlacionadas entre os pontos de apoio."
        )
    if t < 0 or t > 1 or u < 0 or u > 1:
        warnings.append("A interseção extrapola pelo menos um dos segmentos medidos.")

    longitude = latitude = None
    if sirgas2000_confirmed:
        epsg = _epsg(utm_zone, hemisphere)
        longitude, latitude = Transformer.from_crs(
            f"EPSG:{epsg}", "EPSG:4674", always_xy=True,
        ).transform(x, y)
    else:
        warnings.append("SIRGAS2000 não confirmado: coordenadas geográficas não calculadas.")

    return {
        "status": "DRAFT_REQUIRES_TECHNICAL_REVIEW",
        "method": method,
        "operation": "OFFSET_LINES_INTERSECTION",
        "vertex_type": "V",
        "easting_m": round(x, 4),
        "northing_m": round(y, 4),
        "longitude": longitude,
        "latitude": latitude,
        "height_m": None,
        "sigma_e_m": None if sigma_e is None else round(sigma_e, 4),
        "sigma_n_m": None if sigma_n is None else round(sigma_n, 4),
        "sigma_horizontal_m": None if sigma_hz is None else round(sigma_hz, 4),
        "sigma_h_m": None,
        "sigma_model": None if missing else "FIRST_ORDER_UNCORRELATED",
        "angle_deg_acute": round(math.degrees(math.asin(min(1.0, sin_angle))), 4),
        "line_parameters": {"first_t": round(t, 8), "second_t": round(u, 8)},
        "lines": descriptions,
        "witnesses": names,
        "warnings": warnings,
        "ready_for_sigef": False,
    }
