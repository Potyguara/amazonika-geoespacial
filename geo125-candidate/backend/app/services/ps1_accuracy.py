"""PS1: cálculo de precisão de checagem independente, em metros.

O resultado numérico não certifica PEC-PCD nem substitui análise do RT.
"""
from math import hypot, isfinite, sqrt

LIMITS = {"ARTIFICIAL": 0.5, "NATURAL": 3.0, "INACCESSIBLE": 7.5}


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
        raise ValueError("Valor numérico finito obrigatório.")
    return float(value)


def evaluate_ps1_checkpoints(rows, category):
    if category not in LIMITS:
        raise ValueError("Categoria de limite inválida.")
    if not rows:
        raise ValueError("Importe pontos independentes de checagem.")
    names = set()
    errors = []
    for row in rows:
        name = str(row.get("id") or "").strip()
        if not name or name in names or row.get("used_for_control") is not False:
            raise ValueError("Ponto repetido, sem identificação ou não independente.")
        names.add(name)
        errors.append(tuple(_number(row.get(k)) for k in ("delta_e_m", "delta_n_m", "delta_h_m")))
    rms = [sqrt(sum(row[i] ** 2 for row in errors) / len(errors)) for i in range(3)]
    horizontal = hypot(*rms[:2])
    return {"count": len(errors), "sigma_e_m": rms[0], "sigma_n_m": rms[1],
            "sigma_h_m": rms[2], "horizontal_rms_m": horizontal,
            "limit_m": LIMITS[category], "within_horizontal_limit": horizontal <= LIMITS[category],
            "ready_for_sigef": False}


def ps1_height(source_h, source_sigma, *, kind, factor=None, factor_sigma=None):
    """Converter HN documentada em h; componentes independentes."""
    height, sigma = _number(source_h), _number(source_sigma)
    if sigma <= 0:
        raise ValueError("Sigma vertical positivo e documentado obrigatório.")
    if kind == "ELLIPSOIDAL":
        if factor is not None or factor_sigma is not None:
            raise ValueError("Altura elipsoidal não requer conversão.")
        return {"ellipsoidal_height_m": height, "sigma_h_m": sigma}
    if kind != "NORMAL":
        raise ValueError("Referencial vertical não suportado ou não confirmado.")
    f, fs = _number(factor), _number(factor_sigma)
    if fs < 0:
        raise ValueError("Sigma do fator inválido.")
    return {"ellipsoidal_height_m": height + f, "sigma_h_m": hypot(sigma, fs),
            "normal_height_m": height}
