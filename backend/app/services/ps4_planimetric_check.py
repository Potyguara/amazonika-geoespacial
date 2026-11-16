"""Avaliação externa PS4 por pontos GNSS fotoidentificados de maneira independente.

Pontos GNSS não devem ter sido usados no ajuste da mesma ortoimagem.
Nenhuma estatística é gerada sem pares reais (pixel localizado + GNSS).
"""
from __future__ import annotations

from math import sqrt, isfinite
from pyproj import CRS, Transformer

# Limite de TRIAGEM INTERNA, não quantidade mínima regulamentar do INCRA.
# A suficiência técnica depende também do desenho amostral e da revisão RT.
SCREENING_REFERENCE_COUNT = 20


def evaluate_checkpoints(records: list[dict], raster_metadata: dict) -> dict:
    if not records:
        return {"status": "NO_CHECKPOINTS", "count": 0,
                "rms_e_m": None, "rms_n_m": None, "rms_horizontal_m": None,
                "checkpoints": [], "screening_reference_count": SCREENING_REFERENCE_COUNT,
                "screening_missing_count": SCREENING_REFERENCE_COUNT,
                "max_radial_error_m": None,
                "checkpoints": [], "warnings": ["Sem pontos GNSS independentes fotoidentificados: EMQ indisponível."]}
    crs_code = raster_metadata.get("crs_authority")
    if not crs_code:
        raise ValueError("O raster precisa declarar SRC projetado para calcular resíduos.")
    crs = CRS.from_user_input(crs_code)
    if not crs.is_projected or not crs.axis_info or any(
        abs(a.unit_conversion_factor - 1) > 1e-9 for a in crs.axis_info[:2]
    ):
        raise ValueError("SRC do raster deve utilizar coordenadas planas métricas.")
    transformer = Transformer.from_crs("EPSG:4326", crs, always_xy=True)
    rows = []
    ids = set()
    for point in records:
        name = str(point.get("name") or "").strip()
        if not name or name in ids:
            raise ValueError("Identificador ausente ou repetido em ponto de checagem.")
        ids.add(name)
        if point.get("used_for_orthorectification") is not False:
            raise ValueError(f"{name}: ponto utilizado na ortorretificação não é checagem independente.")
        values = [point[k] for k in (
            "gnss_longitude", "gnss_latitude", "image_longitude", "image_latitude"
        )]
        if not all(isinstance(v, (int, float)) and isfinite(v) for v in values):
            raise ValueError(f"{name}: coordenadas inválidas.")
        if not all(-180 <= values[i] <= 180 for i in (0, 2)) or not all(
            -90 <= values[i] <= 90 for i in (1, 3)
        ):
            raise ValueError(f"{name}: latitude/longitude fora da faixa.")
        gnss_e, gnss_n = transformer.transform(values[0], values[1])
        image_e, image_n = transformer.transform(values[2], values[3])
        de, dn = image_e - gnss_e, image_n - gnss_n
        rows.append({"name": name, "delta_e_m": round(de, 4),
                     "delta_n_m": round(dn, 4),
                     "radial_error_m": round(sqrt(de * de + dn * dn), 4)})
    n = len(rows)
    rms_e = sqrt(sum(r["delta_e_m"] ** 2 for r in rows) / n)
    rms_n = sqrt(sum(r["delta_n_m"] ** 2 for r in rows) / n)
    horizontal = sqrt(rms_e * rms_e + rms_n * rms_n)
    # A amostra reduzida não é representativa da ortoimagem inteira.
    status = "REVIEW_REQUIRED" if n >= SCREENING_REFERENCE_COUNT else "INSUFFICIENT_CHECKPOINTS"
    return {
        "status": status, "count": n, "rms_e_m": round(rms_e, 4),
        "rms_n_m": round(rms_n, 4), "rms_horizontal_m": round(horizontal, 4),
        "screening_reference_count": SCREENING_REFERENCE_COUNT,
        "screening_missing_count": max(0, SCREENING_REFERENCE_COUNT - n),
        "max_radial_error_m": max(r["radial_error_m"] for r in rows),
        "checkpoints": rows,
        "warnings": [
            "Resíduos amostrais não equivalem a sigmas individuais dos vértices V.",
            "20 pontos é referência de triagem interna, não mínimo normativo universal nem aprovação automática.",
            "Não descarte pontos discrepantes somente para reduzir o EMQ: registre a investigação técnica.",
            "Amostra requer distribuição espacial, independência e revisão do RT.",
            "Os resultados não aprovam automaticamente PS4 nem a ODS SIGEF.",
        ],
    }
