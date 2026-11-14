"""Conversão altimétrica rastreável para levantamentos GNSS.

SIGEF exige altitude elipsoidal (h); altitude normal é informação complementar.
hgeoHNOR2020: HN = h - eta; MAPGEO: H ortométrica = h - N.
Não é uma API oficial IBGE; os fatores devem ser obtidos do modelo e
registrados com sua proveniência, sem arredondamentos intermediários.
"""
from __future__ import annotations

import math
from typing import Any

MAX_POINTS = 5000
MODEL_NORMAL = "hgeoHNOR2020"
MODEL_ORTHOMETRIC = "MAPGEO2015"


def _number(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{field}: número inválido.")
    try:
        parsed = float(str(value).strip().replace(",", "."))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{field}: valor obrigatório e numérico.") from exc
    if not math.isfinite(parsed):
        raise ValueError(f"{field}: valor não finito.")
    return parsed


def convert_altitudes(points: list[dict], *, model: str) -> dict:
    """Calcula HN/H a partir de h e fator comprovado, sem modificar entradas."""
    if model not in (MODEL_NORMAL, MODEL_ORTHOMETRIC):
        raise ValueError("Modelo desconhecido: selecione hgeoHNOR2020 ou MAPGEO2015.")
    if not isinstance(points, list) or not 1 <= len(points) <= MAX_POINTS:
        raise ValueError("Informe entre 1 e 5.000 pontos.")
    results = []
    errors = []
    for index, point in enumerate(points, 1):
        if not isinstance(point, dict):
            errors.append(f"Ponto {index}: registro inválido.")
            continue
        ident = str(point.get("name") or f"Ponto {index}").strip()
        try:
            h = _number(point.get("ellipsoidal_height_m"), f"{ident}: altura geométrica (h)")
            factor = _number(point.get("conversion_factor_m"), f"{ident}: fator de conversão")
            lat = _number(point.get("latitude"), f"{ident}: latitude")
            lon = _number(point.get("longitude"), f"{ident}: longitude")
            if not (-35 <= lat <= 7 and -75 <= lon <= -30):
                raise ValueError(f"{ident}: latitude/longitude fora da abrangência brasileira.")
            # Origem é obrigatória para permitir auditoria dos valores manuais ou oficiais.
            origin = str(point.get("factor_origin") or "").strip()
            if not origin:
                raise ValueError(f"{ident}: informe a origem do fator (IBGE ou manual conferido).")
            if len(origin) > 250:
                raise ValueError(f"{ident}: descrição de origem muito longa.")
            confirmed = point.get("height_reference_confirmed") is True
            if not confirmed:
                raise ValueError(
                    f"{ident}: confirme que o valor h é altura elipsoidal em SIRGAS2000; "
                    "a elevação genérica do Topcon não deve ser utilizada."
                )
            physical = h - factor
            if model == MODEL_NORMAL:
                physical_name = "normal_height_m"
                factor_name = "eta_m"
            else:
                physical_name = "orthometric_height_m"
                factor_name = "geoid_undulation_m"
            result = {
                "name": ident, "latitude": lat, "longitude": lon,
                "ellipsoidal_height_m": h,
                factor_name: factor, physical_name: round(physical, 4),
                "model": model, "factor_origin": origin,
                "sigef_h_m": h,
                "sigef_height_type": "ELLIPSOIDAL",
                "input_coordinates_modified": False,
            }
            # Sigma h não pode ser convertido automaticamente em sigma H
            # sem incerteza do modelo e covariância.
            if point.get("sigma_h_m") is not None:
                sigma = _number(point["sigma_h_m"], f"{ident}: sigma h")
                if sigma < 0:
                    raise ValueError(f"{ident}: sigma h deve ser >= 0.")
                result["sigma_h_m"] = sigma
            if point.get("factor_uncertainty_m") is not None:
                unc = _number(point["factor_uncertainty_m"], f"{ident}: incerteza do fator")
                if unc < 0:
                    raise ValueError(f"{ident}: incerteza do modelo deve ser >= 0.")
                result["factor_uncertainty_m"] = unc
            results.append(result)
        except ValueError as exc:
            errors.append(str(exc))
    return {
        "model": model,
        "status": "READY" if not errors else "INCOMPLETE",
        "points": results,
        "errors": errors,
        "warnings": [
            "A coluna h da ODS SIGEF exige altitude elipsoidal, não altitude normal.",
            "O cálculo físico não altera os valores GNSS. Confirme referenciais e incertezas.",
            "Fonte do fator não foi consultada automaticamente pelo Amazonika.",
        ],
    }
