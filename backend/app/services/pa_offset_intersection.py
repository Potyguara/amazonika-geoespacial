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


# ---------------------------------------------------------------------------
# Paralela a uma cadeia de pontos P (vários segmentos com o mesmo afastamento)
# ---------------------------------------------------------------------------

MAX_TURN_DEG = 170.0
SPIKE_TURN_DEG = 120.0


def _chain_vertices(values: list[float], n: int, sign: float, end_mode: str):
    """Vértices da paralela a uma poligonal aberta de n pontos.

    values = [E0, N0, ..., E(n-1), N(n-1), d]. Nos pontos internos o vértice é
    a interseção das paralelas aos dois segmentos que chegam ao ponto (fórmula
    da esquadria: P + d·(n1+n2)/(1+n1·n2)). Nas pontas, afastamento
    perpendicular ao segmento extremo (end_mode PERPENDICULAR) ou nenhum
    vértice (end_mode NONE, para ligar a outra reta por interseção).
    """
    d = values[2 * n]
    pts = [(values[2 * i], values[2 * i + 1]) for i in range(n)]
    normals = []
    for i in range(n - 1):
        dx, dy = pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1]
        length = math.hypot(dx, dy)
        if length < 0.01:
            raise ValueError(f"Segmento {i + 1} com comprimento nulo.")
        normals.append((-dy / length * sign, dx / length * sign))
    out = []
    if end_mode == "PERPENDICULAR":
        out.append((0, pts[0][0] + normals[0][0] * d, pts[0][1] + normals[0][1] * d, 0.0, 1.0))
    for k in range(1, n - 1):
        n1, n2 = normals[k - 1], normals[k]
        dot = n1[0] * n2[0] + n1[1] * n2[1]
        denom = 1.0 + dot
        turn = math.degrees(math.acos(max(-1.0, min(1.0, dot))))
        if turn > MAX_TURN_DEG:
            raise ValueError(
                f"Mudança de direção maior que {MAX_TURN_DEG:g}° no ponto {k + 1}: paralela indefinida (retorno)."
            )
        factor = 1.0 / math.cos(math.radians(turn) / 2)
        out.append((k, pts[k][0] + d * (n1[0] + n2[0]) / denom, pts[k][1] + d * (n1[1] + n2[1]) / denom, turn, factor))
    if end_mode == "PERPENDICULAR":
        last = n - 1
        out.append((last, pts[last][0] + normals[-1][0] * d, pts[last][1] + normals[-1][1] * d, 0.0, 1.0))
    return out


def offset_polyline(
    points: list[dict], *,
    method: str,
    offset_m: float,
    side: str | None,
    offset_sigma_m: float | None = None,
    end_mode: str = "PERPENDICULAR",
    utm_zone: int | None = None,
    hemisphere: str | None = None,
    sirgas2000_confirmed: bool = False,
) -> dict:
    """Vértices V de uma paralela à cadeia de pontos P medidos.

    Cada ponto: name, easting_m, northing_m, sigma_e_m, sigma_n_m e,
    opcionalmente, ellipsoidal_height_m e sigma_h_m. A precisão horizontal de
    cada V é propagada em primeira ordem a partir de todos os pontos da cadeia
    e do desvio-padrão do afastamento. A altura elipsoidal de cada V é
    não é calculada: a h do P de apoio é devolvida só como referência.
    """
    if method not in ("PA1", "PA2"):
        raise ValueError("Código de posicionamento: informe PA1 ou PA2, conforme o enquadramento do RT.")
    if end_mode not in ("PERPENDICULAR", "NONE"):
        raise ValueError("Tratamento das pontas inválido.")
    if not isinstance(points, list) or len(points) < 2:
        raise ValueError("Selecione pelo menos dois pontos P em sequência.")
    if end_mode == "NONE" and len(points) < 3:
        raise ValueError("Sem vértices nas pontas, a cadeia precisa de pelo menos três pontos.")
    try:
        d = float(offset_m)
    except (TypeError, ValueError) as exc:
        raise ValueError("Afastamento inválido.") from exc
    if not math.isfinite(d) or d <= 0:
        raise ValueError("Informe um afastamento maior que zero.")
    if side not in ("LEFT", "RIGHT"):
        raise ValueError("Indique o lado da paralela (esquerdo/direito no sentido do caminhamento).")
    sign = 1.0 if side == "LEFT" else -1.0

    parsed = [_point(p, f"Ponto {i + 1}") for i, p in enumerate(points)]
    names = [p[0] for p in parsed]
    if len(set(names)) != len(names):
        raise ValueError("A cadeia repete um ponto: cada ponto P entra uma única vez.")
    heights: list[float | None] = []
    sigma_hs: list[float | None] = []
    for p in points:
        def num(key):
            value = p.get(key)
            if value is None or value == "":
                return None
            try:
                value = float(value)
            except (TypeError, ValueError):
                return None
            return value if math.isfinite(value) else None
        heights.append(num("ellipsoidal_height_m"))
        sh = num("sigma_h_m")
        sigma_hs.append(sh if sh is None or sh >= 0 else None)

    n = len(parsed)
    values: list[float] = []
    sigmas: list[float | None] = []
    for p in parsed:
        values += [p[1], p[2]]
        sigmas += [p[3], p[4]]
    values.append(d)
    od = None
    if offset_sigma_m not in (None, ""):
        try:
            od = float(offset_sigma_m)
        except (TypeError, ValueError):
            od = None
        if od is not None and (not math.isfinite(od) or od < 0):
            od = None
    sigmas.append(od)

    base = _chain_vertices(values, n, sign, end_mode)

    # A paralela não pode inverter o sentido de nenhum segmento (afastamento
    # maior do que a geometria comporta gera laços).
    seq = [(x, y) for _, x, y, _, _ in base]
    support = [k for k, *_ in base]
    for i in range(len(seq) - 1):
        a, b = support[i], support[i + 1]
        ox, oy = parsed[b][1] - parsed[a][1], parsed[b][2] - parsed[a][2]
        vx, vy = seq[i + 1][0] - seq[i][0], seq[i + 1][1] - seq[i][1]
        if ox * vx + oy * vy <= 0:
            raise ValueError(
                f"O afastamento de {d:g} m inverte o trecho {names[a]}→{names[b]}: reduza o afastamento ou retire pontos muito próximos."
            )

    missing = any(s is None for s in sigmas)
    jac: list[list[tuple[float, float]]] = [[(0.0, 0.0)] * len(values) for _ in base]
    if not missing:
        step = 1e-4
        for j, s in enumerate(sigmas):
            if s == 0:
                continue
            plus = list(values); plus[j] += step
            minus = list(values); minus[j] -= step
            vp = _chain_vertices(plus, n, sign, end_mode)
            vm = _chain_vertices(minus, n, sign, end_mode)
            for i in range(len(base)):
                jac[i][j] = ((vp[i][1] - vm[i][1]) / (2 * step), (vp[i][2] - vm[i][2]) / (2 * step))

    transformer = None
    if sirgas2000_confirmed:
        transformer = Transformer.from_crs(f"EPSG:{_epsg(utm_zone, hemisphere)}", "EPSG:4674", always_xy=True)

    vertices = []
    over_limit = []
    spikes = []
    for i, (k, x, y, turn, factor) in enumerate(base):
        if not _finite(x, y):
            raise ValueError("Vértice numericamente inválido.")
        se = sn = shz = None
        if not missing:
            var_e = sum((jac[i][j][0] * s) ** 2 for j, s in enumerate(sigmas) if s)
            var_n = sum((jac[i][j][1] * s) ** 2 for j, s in enumerate(sigmas) if s)
            se, sn, shz = math.sqrt(var_e), math.sqrt(var_n), math.sqrt(var_e + var_n)
            if shz > 0.50:
                over_limit.append(names[k])
        if turn > SPIKE_TURN_DEG:
            spikes.append(names[k])
        lon = lat = None
        if transformer is not None:
            lon, lat = transformer.transform(x, y)
        vertices.append({
            "sequence": i + 1,
            "support_point": names[k],
            "position": "START" if (end_mode == "PERPENDICULAR" and i == 0) else
                        "END" if (end_mode == "PERPENDICULAR" and i == len(base) - 1) else "INTERNAL",
            "easting_m": round(x, 4),
            "northing_m": round(y, 4),
            "longitude": lon,
            "latitude": lat,
            "height_m": None,
            "height_source": None,
            "support_height_m": None if heights[k] is None else round(heights[k], 4),
            "sigma_e_m": None if se is None else round(se, 4),
            "sigma_n_m": None if sn is None else round(sn, 4),
            "sigma_horizontal_m": None if shz is None else round(shz, 4),
            "sigma_h_m": None,
            "support_sigma_h_m": None if sigma_hs[k] is None else round(sigma_hs[k], 4),
            "turn_angle_deg": round(turn, 4),
            "miter_factor": round(factor, 4),
        })

    warnings = [
        "Vértices determinados por geometria analítica: paralela à cadeia de pontos P medidos, com interseção das paralelas de segmentos consecutivos.",
        "Nas pontas, o vértice é o afastamento perpendicular ao segmento extremo." if end_mode == "PERPENDICULAR"
        else "Pontas sem vértice: ligue a paralela a outra reta por interseção.",
        "A altura elipsoidal h dos V não é calculada: informe h e σh obtidos por medição ou outro método declarado pelo RT antes de exportar. A h do ponto P de apoio é mostrada só como referência.",
        "O enquadramento como PA1 ou PA2 é declaração do responsável técnico e deve constar do relatório técnico.",
    ]
    if missing:
        warnings.append("Sigmas não propagados: falta desvio-padrão E/N de algum ponto P ou do afastamento.")
    else:
        warnings.append("Sigmas propagados em primeira ordem supondo observações não correlacionadas entre os pontos P.")
    if over_limit:
        warnings.append("Precisão horizontal acima de 0,50 m (limite para limite artificial) em: " + ", ".join(over_limit) + ".")
    if spikes:
        warnings.append(f"Mudança de direção acima de {SPIKE_TURN_DEG:g}° em {', '.join(spikes)}: o vértice fica distante do ponto P; confira.")
    if not sirgas2000_confirmed:
        warnings.append("SIRGAS2000 não confirmado: coordenadas geográficas não calculadas.")

    return {
        "status": "DRAFT_REQUIRES_TECHNICAL_REVIEW",
        "method": method,
        "operation": "OFFSET_POLYLINE",
        "vertex_type": "V",
        "offset_m": d,
        "side": side,
        "offset_sigma_m": od,
        "end_mode": end_mode,
        "support_points": names,
        "sigma_model": None if missing else "FIRST_ORDER_UNCORRELATED",
        "vertices": vertices,
        "warnings": warnings,
        "ready_for_sigef": False,
    }
