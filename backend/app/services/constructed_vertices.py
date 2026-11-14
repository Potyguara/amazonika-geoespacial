"""Pré-cálculo de posicionamento geométrico PA1 e PT8.

PA1: afastamento perpendicular assinado de um alinhamento de dois marcos.
PT8: alinhamento e distância medida a partir do primeiro testemunho.
Um clique sobre uma ortofoto apenas escolhe a solução/lado; não determina
coordenada métrica para fins de certificação.
"""
from __future__ import annotations
import math
from pyproj import Transformer


def _utm_to_geographic(e: float, n: float, zone: int | None,
                       hemisphere: str | None, confirmed: bool):
    if not confirmed:
        return None, None
    if not isinstance(zone, int) or hemisphere not in ("N", "S"):
        raise ValueError("Informe zona e hemisfério UTM e confirme o SIRGAS2000.")
    if hemisphere == "N" and 18 <= zone <= 22:
        epsg = 31954 + zone
    elif hemisphere == "S" and 18 <= zone <= 25:
        epsg = 31960 + zone
    else:
        raise ValueError("Zona/hemisfério UTM incompatível com faixa suportada.")
    lon, lat = Transformer.from_crs(
        f"EPSG:{epsg}", "EPSG:4674", always_xy=True,
    ).transform(e, n)
    return lon, lat


def calculate_constructed_vertex(method: str, witnesses: list[dict],
                                 distance_m: float | None = None,
                                 side: str | None = None,
                                 utm_zone: int | None = None,
                                 hemisphere: str | None = None,
                                 sirgas2000_confirmed: bool = False,
                                 hint_longitude: float | None = None,
                                 hint_latitude: float | None = None) -> dict:
    if method not in ("PA1", "PT8"):
        raise ValueError("Método admitido nesta rota: PA1 ou PT8.")
    if len(witnesses) != 2:
        raise ValueError("PA1 e PT8 exigem dois marcos de apoio diferentes.")
    names = [str(p.get("name") or "").strip() for p in witnesses]
    if not all(names) or len(set(names)) != 2:
        raise ValueError("Os dois marcos de apoio devem ser distintos.")
    try:
        (ax, ay), (bx, by) = [
            (float(p["easting_m"]), float(p["northing_m"])) for p in witnesses
        ]
        distance = float(distance_m)
    except (KeyError, ValueError, TypeError) as exc:
        raise ValueError("Informe coordenadas UTM e distância medida em metros.") from exc
    if not all(math.isfinite(v) for v in (ax, ay, bx, by, distance)):
        raise ValueError("Coordenadas ou distância não finitas.")
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length < 0.01:
        raise ValueError("Os marcos não definem alinhamento válido.")
    if method == "PA1":
        if distance <= 0:
            raise ValueError("O afastamento perpendicular deve ser positivo.")
        if side not in ("LEFT", "RIGHT"):
            raise ValueError("Indique o lado da paralela (esquerdo/direito de A para B).")
        sign = 1 if side == "LEFT" else -1
        e = ax - sign * dy / length * distance
        n = ay + sign * dx / length * distance
        # A posição visual escolhe o ponto ao longo da paralela.
        # A coordenada de clique é projetada no alinhamento deslocado,
        # nunca utilizada diretamente como vértice certificado.
        if hint_longitude is not None and hint_latitude is not None:
            if not sirgas2000_confirmed or hemisphere not in ("N", "S") or not isinstance(utm_zone, int):
                raise ValueError("Confirme SIRGAS2000 para orientar a paralela com clique.")
            if hemisphere == "N" and 18 <= utm_zone <= 22:
                epsg = 31954 + utm_zone
            elif hemisphere == "S" and 18 <= utm_zone <= 25:
                epsg = 31960 + utm_zone
            else:
                raise ValueError("Zona UTM não admitida.")
            he, hn = Transformer.from_crs(
                "EPSG:4674", f"EPSG:{epsg}", always_xy=True,
            ).transform(hint_longitude, hint_latitude)
            if not all(math.isfinite(v) for v in (he, hn)):
                raise ValueError("Clique fora da faixa de coordenadas suportadas.")
            along = ((he - e) * dx + (hn - n) * dy) / (length * length)
            if abs(along) > 100:
                raise ValueError("Clique distante demais dos marcos de referência.")
            e += along * dx
            n += along * dy
        line_end = [
            bx - sign * dy / length * distance,
            by + sign * dx / length * distance,
        ]
        detail = "PA1 determina linha paralela, não toda a divisa sem demais referências."
    else:
        if distance < 0:
            raise ValueError("A distância medida PT8 não pode ser negativa.")
        if side not in ("FORWARD", "BACKWARD"):
            raise ValueError("Defina o sentido a partir do marco inicial.")
        sign = 1 if side == "FORWARD" else -1
        e = ax + sign * dx / length * distance
        n = ay + sign * dy / length * distance
        line_end = None
        detail = ("PT8 é compatível com vértices M/P na tabela de métodos do Manual "
                  "Técnico INCRA 2ª edição; não classificá-lo como V automaticamente.")
    longitude, latitude = _utm_to_geographic(
        e, n, utm_zone, hemisphere, sirgas2000_confirmed,
    )
    return {
        "status": "DRAFT_REQUIRES_TECHNICAL_REVIEW",
        "method": method,
        "vertex_type": "V" if method == "PA1" else "P",
        "easting_m": round(e, 4), "northing_m": round(n, 4),
        "longitude": longitude, "latitude": latitude,
        "line_end_utm": line_end,
        "height_m": None,
        "sigma_e_m": None, "sigma_n_m": None, "sigma_h_m": None,
        "witnesses": names,
        "warnings": [
            detail,
            "PA1: clique projetado na reta paralela como referência visual preliminar." if method == "PA1" and hint_longitude is not None else "Coordenada obtida por geometria analítica.",
            "O clique visual não é observação topográfica nem define precisão posicional.",
            "h e precisões finais requerem procedimento documentado e validação do responsável técnico.",
        ],
        "ready_for_sigef": False,
    }
