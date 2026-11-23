"""Vértices V por geometria analítica (PA1 paralela, PA2 interseção de retas).

Base normativa (INCRA):
- MTGIR 2ª ed., 3.8 b: na geometria analítica as coordenadas de referência
  obtidas por GNSS são convertidas para o Sistema Geodésico Local (SGL), com
  origem na média das coordenadas geocêntricas dos vértices de referência; o
  cálculo é feito nessas coordenadas locais e o resultado volta para
  geocêntricas/geodésicas pela mesma origem (3.8.1 e 3.8.2).
- MTGIR 2ª ed., 3.3 e 3.3.2: cada vértice obtido por geometria analítica deve
  receber altitude; na impossibilidade de obtê-la, atribui-se a altitude média
  dos vértices utilizados como referência (ou a extraída de modelo de terreno).
- NTGIR 3ª ed., 2.8 / MTGIR 1.2.8: precisão posicional absoluta com propagação
  das covariâncias a partir dos vértices de referência; 4.3 / 1.4.3:
  σP = √(σφ² + σλ²), sem σh; 4.4 / 1.4.4: limites 0,50 / 3,00 / 7,50 m.

A precisão horizontal é propagada em primeira ordem a partir dos desvios-padrão
e/n de cada vértice de referência e do desvio-padrão do afastamento, supondo
observações não correlacionadas. O σh do V é o da média adotada:
σh = √(Σσh²)/n. O resultado é pré-cálculo para revisão do responsável técnico.
"""
from __future__ import annotations

import math

from pyproj import Transformer

MIN_ANGLE_DEG = 5.0
MAX_EXTRAPOLATION = 100.0
PRECISION_LIMITS_M = {"ARTIFICIAL": 0.50, "NATURAL": 3.00, "INACCESSIBLE": 7.50}
FRAME = "SGL_GRS80"
NORMATIVE_BASIS = [
    "MTGIR 2ª ed., 3.8 b: cálculo em coordenadas cartesianas locais (SGL), origem na média geocêntrica dos vértices de referência.",
    "MTGIR 2ª ed., 3.8.1 e 3.8.2: conversões geocêntricas ↔ locais.",
    "MTGIR 2ª ed., 3.3 e 3.3.2: altitude do V = média das altitudes dos vértices de referência, quando não obtida de outra forma.",
    "NTGIR 3ª ed., 2.8 e 4.3: precisão posicional absoluta por propagação de covariâncias; σP = √(σφ²+σλ²).",
]

_TO_XYZ = Transformer.from_crs("EPSG:4989", "EPSG:4988", always_xy=True)
_TO_LLH = Transformer.from_crs("EPSG:4988", "EPSG:4989", always_xy=True)


def _finite(*values: float) -> bool:
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)


def _epsg(zone: int | None, hemisphere: str | None) -> int:
    if not isinstance(zone, int) or hemisphere not in ("N", "S"):
        raise ValueError("Informe zona UTM e hemisfério do SIRGAS2000.")
    if hemisphere == "N" and 18 <= zone <= 22:
        return 31954 + zone
    if hemisphere == "S" and 18 <= zone <= 25:
        return 31960 + zone
    raise ValueError("Zona/hemisfério fora da faixa SIRGAS2000 suportada.")


def _num(p: dict, *keys: str) -> float | None:
    for key in keys:
        value = p.get(key)
        if value is None or value == "":
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(value):
            return value
    return None


def _sigma(p: dict, *keys: str) -> float | None:
    value = _num(p, *keys)
    return value if value is not None and value >= 0 else None


class LocalFrame:
    """Sistema Geodésico Local com origem na média geocêntrica dos pontos."""

    def __init__(self, llh: list[tuple[float, float, float]]):
        xyz = [_TO_XYZ.transform(lon, lat, h, errcheck=True) for lon, lat, h in llh]
        self.origin = tuple(math.fsum(p[k] for p in xyz) / len(xyz) for k in range(3))
        lon0, lat0, h0 = _TO_LLH.transform(*self.origin, errcheck=True)
        self.origin_llh = (lon0, lat0, h0)
        l, p = math.radians(lon0), math.radians(lat0)
        self.rot = (
            (-math.sin(l), math.cos(l), 0.0),
            (-math.sin(p) * math.cos(l), -math.sin(p) * math.sin(l), math.cos(p)),
            (math.cos(p) * math.cos(l), math.cos(p) * math.sin(l), math.sin(p)),
        )

    def to_local(self, lon: float, lat: float, h: float) -> tuple[float, float, float]:
        X, Y, Z = _TO_XYZ.transform(lon, lat, h, errcheck=True)
        d = (X - self.origin[0], Y - self.origin[1], Z - self.origin[2])
        return tuple(sum(r[k] * d[k] for k in range(3)) for r in self.rot)  # type: ignore[return-value]

    def to_geodetic(self, e: float, n: float, u: float) -> tuple[float, float, float]:
        local = (e, n, u)
        X = [self.origin[k] + sum(self.rot[i][k] * local[i] for i in range(3)) for k in range(3)]
        return _TO_LLH.transform(*X, errcheck=True)

    def geodetic_at_height(self, e: float, n: float, h: float) -> tuple[float, float]:
        """Latitude/longitude do ponto (e, n) do plano local na altitude h."""
        u = h - self.origin_llh[2]
        for _ in range(4):
            lon, lat, hh = self.to_geodetic(e, n, u)
            u += h - hh
        lon, lat, _ = self.to_geodetic(e, n, u)
        return lon, lat


def _reference_points(points: list[dict], label: str, *, utm_zone, hemisphere, sirgas2000_confirmed) -> list[dict]:
    if not sirgas2000_confirmed:
        raise ValueError(
            "Confirme que os pontos estão em SIRGAS2000: o cálculo é feito no SGL (MTGIR 3.8 b) a partir das coordenadas geodésicas."
        )
    utm = None
    out = []
    for i, p in enumerate(points, start=1):
        if not isinstance(p, dict):
            raise ValueError(f"{label}: ponto {i} inválido.")
        name = str(p.get("name") or "").strip()
        if not name:
            raise ValueError(f"{label}: ponto sem identificação.")
        lat, lon = _num(p, "latitude"), _num(p, "longitude")
        if lat is None or lon is None:
            e, n = _num(p, "easting_m"), _num(p, "northing_m")
            if e is None or n is None:
                raise ValueError(f"{label}: informe as coordenadas do ponto {name}.")
            if utm is None:
                utm = Transformer.from_crs(f"EPSG:{_epsg(utm_zone, hemisphere)}", "EPSG:4674", always_xy=True)
            lon, lat = utm.transform(e, n)
        if not (-90 < lat < 90 and -180 <= lon <= 180):
            raise ValueError(f"{label}: coordenadas geodésicas inválidas em {name}.")
        h = _num(p, "ellipsoidal_height_m", "height_m")
        if h is None:
            raise ValueError(
                f"{label}: o ponto {name} não tem altitude elipsoidal h; ela é necessária para o cálculo no SGL (MTGIR 3.8 b) e para a altitude do V (MTGIR 3.3)."
            )
        out.append({
            "name": name, "lon": lon, "lat": lat, "h": h,
            "sigma_e": _sigma(p, "sigma_e_m", "sigma_lon_m"),
            "sigma_n": _sigma(p, "sigma_n_m", "sigma_lat_m"),
            "sigma_h": _sigma(p, "sigma_h_m", "sigma_u_m"),
        })
    return out


def _mean_height(refs: list[dict]) -> tuple[float, float | None]:
    h = math.fsum(r["h"] for r in refs) / len(refs)
    if any(r["sigma_h"] is None for r in refs):
        return h, None
    return h, math.sqrt(math.fsum(r["sigma_h"] ** 2 for r in refs)) / len(refs)


def _output_coords(frame: LocalFrame, e: float, n: float, h: float, utm) -> dict:
    lon, lat = frame.geodetic_at_height(e, n, h)
    out = {"longitude": lon, "latitude": lat, "local_e_m": round(e, 4), "local_n_m": round(n, 4)}
    if utm is not None:
        E, N = utm.transform(lon, lat)
        out.update(easting_m=round(E, 4), northing_m=round(N, 4))
    else:
        out.update(easting_m=None, northing_m=None)
    return out


def _utm_forward(utm_zone, hemisphere):
    try:
        return Transformer.from_crs("EPSG:4674", f"EPSG:{_epsg(utm_zone, hemisphere)}", always_xy=True)
    except ValueError:
        return None


def _frame_info(frame: LocalFrame) -> dict:
    lon, lat, h = frame.origin_llh
    return {"frame": FRAME, "origin_latitude": lat, "origin_longitude": lon, "origin_height_m": round(h, 4)}


# ---------------------------------------------------------------------------
# PA2 – interseção de duas retas (paralelas ou não aos alinhamentos medidos)
# ---------------------------------------------------------------------------

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


def _offset_sigma(line: dict, offset: float) -> float | None:
    raw = line.get("offset_sigma_m")
    try:
        value = float(raw) if raw not in (None, "") else (0.0 if offset == 0 else None)
    except (TypeError, ValueError):
        return None
    return value if value is not None and math.isfinite(value) and value >= 0 else None


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
    refs: list[dict] = []
    sides: list[str] = []
    offsets: list[float] = []
    offset_sigmas: list[float | None] = []
    descriptions = []
    for index, line in enumerate(lines, start=1):
        label = f"Reta {index}"
        points = line.get("points") if isinstance(line, dict) else None
        if not isinstance(points, list) or len(points) != 2:
            raise ValueError(f"{label}: informe dois pontos de apoio.")
        a, b = _reference_points(points, label, utm_zone=utm_zone, hemisphere=hemisphere,
                                 sirgas2000_confirmed=sirgas2000_confirmed)
        if a["name"] == b["name"]:
            raise ValueError(f"{label}: os dois pontos devem ser distintos.")
        try:
            offset = float(line.get("offset_m", 0) or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{label}: afastamento inválido.") from exc
        if not math.isfinite(offset) or offset < 0:
            raise ValueError(f"{label}: o afastamento deve ser zero ou positivo.")
        side = line.get("side")
        if offset > 0 and side not in ("LEFT", "RIGHT"):
            raise ValueError(f"{label}: indique o lado do afastamento (esquerdo/direito no sentido {a['name']}→{b['name']}).")
        side = side if side in ("LEFT", "RIGHT") else "LEFT"
        refs += [a, b]
        sides.append(side)
        offsets.append(offset)
        offset_sigmas.append(_offset_sigma(line, offset))
        descriptions.append({"points": [a["name"], b["name"]], "offset_m": offset,
                             "side": side if offset > 0 else None, "offset_sigma_m": offset_sigmas[-1]})

    frame = LocalFrame([(r["lon"], r["lat"], r["h"]) for r in refs])
    local = [frame.to_local(r["lon"], r["lat"], r["h"]) for r in refs]
    for i, d in enumerate(descriptions):
        a, b = local[2 * i], local[2 * i + 1]
        d["length_m"] = round(math.hypot(b[0] - a[0], b[1] - a[1]), 4)
    values = [c for p in local for c in p[:2]] + offsets
    x, y, t, u, cross, lu, lv = _solve(values, (sides[0], sides[1]))
    sin_angle = abs(cross) / (lu * lv)
    if sin_angle < math.sin(math.radians(MIN_ANGLE_DEG)):
        raise ValueError(
            f"Retas quase paralelas (ângulo menor que {MIN_ANGLE_DEG:g}°): interseção mal condicionada."
        )
    if not _finite(x, y):
        raise ValueError("Interseção numericamente inválida.")
    if abs(t) > MAX_EXTRAPOLATION or abs(u) > MAX_EXTRAPOLATION:
        raise ValueError("Interseção muito distante dos pontos de apoio.")

    sigmas = [s for r in refs for s in (r["sigma_e"], r["sigma_n"])] + offset_sigmas
    missing = any(s is None for s in sigmas)
    sigma_e = sigma_n = sigma_hz = None
    if not missing:
        var_e = var_n = 0.0
        for i, s in enumerate(sigmas):
            if s == 0:
                continue
            step = 1e-4
            plus = list(values); plus[i] += step
            minus = list(values); minus[i] -= step
            xp, yp, *_ = _solve(plus, (sides[0], sides[1]))
            xm, ym, *_ = _solve(minus, (sides[0], sides[1]))
            jx, jy = (xp - xm) / (2 * step), (yp - ym) / (2 * step)
            var_e += (jx * s) ** 2
            var_n += (jy * s) ** 2
        sigma_e, sigma_n = math.sqrt(var_e), math.sqrt(var_n)
        sigma_hz = math.sqrt(var_e + var_n)

    h, sigma_h = _mean_height(refs)
    coords = _output_coords(frame, x, y, h, _utm_forward(utm_zone, hemisphere))

    warnings = [
        "Coordenada determinada por geometria analítica no SGL (MTGIR 3.8 b), sem uso de clique no mapa.",
        "Altitude elipsoidal do V = média das altitudes dos 4 vértices de referência (MTGIR 3.3.2). Se houver medição ou modelo de terreno, prefira esse valor.",
        "O enquadramento como PA1 ou PA2 é declaração do responsável técnico e deve constar do relatório técnico.",
    ]
    if missing:
        warnings.append("Sigmas não propagados: falta desvio-padrão e/n de algum ponto de apoio ou de algum afastamento.")
    else:
        warnings.append("Sigmas propagados em primeira ordem supondo observações não correlacionadas entre os pontos de apoio.")
    if sigma_h is None:
        warnings.append("σh não calculado: falta desvio-padrão da altitude de algum vértice de referência.")
    if t < 0 or t > 1 or u < 0 or u > 1:
        warnings.append("A interseção extrapola pelo menos um dos segmentos medidos.")

    return {
        "status": "DRAFT_REQUIRES_TECHNICAL_REVIEW",
        "method": method,
        "operation": "OFFSET_LINES_INTERSECTION",
        "vertex_type": "V",
        **coords,
        "height_m": round(h, 4),
        "height_source": "MEAN_OF_REFERENCE_VERTICES",
        "sigma_e_m": None if sigma_e is None else round(sigma_e, 4),
        "sigma_n_m": None if sigma_n is None else round(sigma_n, 4),
        "sigma_horizontal_m": None if sigma_hz is None else round(sigma_hz, 4),
        "sigma_h_m": None if sigma_h is None else round(sigma_h, 4),
        "sigma_model": None if missing else "FIRST_ORDER_UNCORRELATED",
        "angle_deg_acute": round(math.degrees(math.asin(min(1.0, sin_angle))), 4),
        "line_parameters": {"first_t": round(t, 8), "second_t": round(u, 8)},
        "lines": descriptions,
        "witnesses": [r["name"] for r in refs],
        "calculation_frame": _frame_info(frame),
        "normative_basis": NORMATIVE_BASIS,
        "warnings": warnings,
        "ready_for_sigef": False,
    }


# ---------------------------------------------------------------------------
# PA1 – paralela a uma cadeia de pontos medidos (vários segmentos)
# ---------------------------------------------------------------------------

MAX_TURN_DEG = 170.0
SPIKE_TURN_DEG = 120.0


def _chain_vertices(values: list[float], n: int, sign: float, end_mode: str):
    """Vértices da paralela a uma poligonal aberta de n pontos (plano do SGL).

    values = [e0, n0, ..., e(n-1), n(n-1), d]. Nos pontos internos o vértice é
    a interseção das paralelas aos dois segmentos que chegam ao ponto (fórmula
    da esquadria: P + d·(n1+n2)/(1+n1·n2)). Nas pontas, afastamento
    perpendicular ao segmento extremo (PERPENDICULAR) ou nenhum vértice (NONE).
    Devolve (índice do apoio, e, n, deflexão, fator, índices de referência).
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
        out.append((0, pts[0][0] + normals[0][0] * d, pts[0][1] + normals[0][1] * d, 0.0, 1.0, (0, 1)))
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
        out.append((k, pts[k][0] + d * (n1[0] + n2[0]) / denom, pts[k][1] + d * (n1[1] + n2[1]) / denom,
                    turn, factor, (k - 1, k, k + 1)))
    if end_mode == "PERPENDICULAR":
        last = n - 1
        out.append((last, pts[last][0] + normals[-1][0] * d, pts[last][1] + normals[-1][1] * d, 0.0, 1.0,
                    (last - 1, last)))
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
    """Vértices V de uma paralela à cadeia de pontos medidos (MTGIR 3.3.1).

    Cada ponto: name, latitude/longitude (ou E/N UTM), ellipsoidal_height_m,
    sigma_e_m, sigma_n_m e sigma_h_m. Cálculo no SGL com origem na média
    geocêntrica dos pontos da cadeia; altitude de cada V = média das altitudes
    dos vértices de referência dos segmentos que o definem (MTGIR 3.3).
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

    refs = _reference_points(points, "Cadeia", utm_zone=utm_zone, hemisphere=hemisphere,
                             sirgas2000_confirmed=sirgas2000_confirmed)
    names = [r["name"] for r in refs]
    if len(set(names)) != len(names):
        raise ValueError("A cadeia repete um ponto: cada ponto P entra uma única vez.")
    n = len(refs)
    frame = LocalFrame([(r["lon"], r["lat"], r["h"]) for r in refs])
    local = [frame.to_local(r["lon"], r["lat"], r["h"]) for r in refs]

    values: list[float] = [c for p in local for c in p[:2]] + [d]
    od = None
    if offset_sigma_m not in (None, ""):
        try:
            od = float(offset_sigma_m)
        except (TypeError, ValueError):
            od = None
        if od is not None and (not math.isfinite(od) or od < 0):
            od = None
    sigmas = [s for r in refs for s in (r["sigma_e"], r["sigma_n"])] + [od]

    base = _chain_vertices(values, n, sign, end_mode)

    # A paralela não pode inverter o sentido de nenhum trecho.
    for i in range(len(base) - 1):
        a, b = base[i][0], base[i + 1][0]
        ox, oy = local[b][0] - local[a][0], local[b][1] - local[a][1]
        vx, vy = base[i + 1][1] - base[i][1], base[i + 1][2] - base[i][2]
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

    utm = _utm_forward(utm_zone, hemisphere)
    vertices = []
    over_limit = []
    spikes = []
    no_sigma_h = []
    for i, (k, x, y, turn, factor, ref_idx) in enumerate(base):
        if not _finite(x, y):
            raise ValueError("Vértice numericamente inválido.")
        se = sn = shz = None
        if not missing:
            var_e = math.fsum((jac[i][j][0] * s) ** 2 for j, s in enumerate(sigmas) if s)
            var_n = math.fsum((jac[i][j][1] * s) ** 2 for j, s in enumerate(sigmas) if s)
            se, sn, shz = math.sqrt(var_e), math.sqrt(var_n), math.sqrt(var_e + var_n)
            if shz > PRECISION_LIMITS_M["ARTIFICIAL"]:
                over_limit.append(names[k])
        if turn > SPIKE_TURN_DEG:
            spikes.append(names[k])
        used = [refs[j] for j in ref_idx]
        h, sh = _mean_height(used)
        if sh is None:
            no_sigma_h.append(names[k])
        vertices.append({
            "sequence": i + 1,
            "support_point": names[k],
            "reference_points": [r["name"] for r in used],
            "position": "START" if (end_mode == "PERPENDICULAR" and i == 0) else
                        "END" if (end_mode == "PERPENDICULAR" and i == len(base) - 1) else "INTERNAL",
            **_output_coords(frame, x, y, h, utm),
            "height_m": round(h, 4),
            "height_source": "MEAN_OF_REFERENCE_VERTICES",
            "sigma_e_m": None if se is None else round(se, 4),
            "sigma_n_m": None if sn is None else round(sn, 4),
            "sigma_horizontal_m": None if shz is None else round(shz, 4),
            "sigma_h_m": None if sh is None else round(sh, 4),
            "turn_angle_deg": round(turn, 4),
            "miter_factor": round(factor, 4),
        })

    warnings = [
        "Vértices determinados por geometria analítica no SGL (MTGIR 3.8 b): paralela à cadeia de pontos medidos (MTGIR 3.3.1), com interseção das paralelas de segmentos consecutivos.",
        "Nas pontas, o vértice é o afastamento perpendicular ao segmento extremo." if end_mode == "PERPENDICULAR"
        else "Pontas sem vértice: ligue a paralela a outra reta por interseção.",
        "Altitude elipsoidal de cada V = média das altitudes dos vértices de referência dos segmentos que o definem (MTGIR 3.3). Se houver medição ou modelo de terreno, prefira esse valor.",
        "O enquadramento como PA1 ou PA2 é declaração do responsável técnico e deve constar do relatório técnico.",
    ]
    if missing:
        warnings.append("Sigmas não propagados: falta desvio-padrão e/n de algum ponto ou do afastamento.")
    else:
        warnings.append("Sigmas propagados em primeira ordem supondo observações não correlacionadas entre os pontos.")
    if no_sigma_h:
        warnings.append("σh não calculado em " + ", ".join(no_sigma_h) + ": falta desvio-padrão da altitude de algum vértice de referência.")
    if over_limit:
        warnings.append("Precisão posicional acima de 0,50 m (limite artificial, NTGIR 4.4 a) em: " + ", ".join(over_limit) + ".")
    if spikes:
        warnings.append(f"Mudança de direção acima de {SPIKE_TURN_DEG:g}° em {', '.join(spikes)}: o vértice fica distante do ponto; confira.")

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
        "calculation_frame": _frame_info(frame),
        "normative_basis": NORMATIVE_BASIS,
        "vertices": vertices,
        "warnings": warnings,
        "ready_for_sigef": False,
    }
