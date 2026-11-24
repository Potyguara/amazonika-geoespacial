"""Reutiliza parametros da previa tecnica PB1 somente na geometria e nos rasters originais.

Faz vinculacao de declaracoes e calculos; NAO confirma exatidao nem aprova o RT.
"""
from math import isfinite


def _positive(value):
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and isfinite(value) and value > 0)


def _matching_points(draft, calculated):
    if not draft or len(draft) != len(calculated):
        return False
    rows = {r.get("vertex_id"): r for r in calculated if isinstance(r, dict)}
    if len(rows) != len(draft):
        return False
    for p in draft:
        row = rows.get(p.get("name"))
        if not row:
            return False
        for coord in ("latitude", "longitude"):
            a, b = p.get(coord), row.get(coord)
            if (not isinstance(a, (int, float)) or not isinstance(b, (int, float))
                    or not isfinite(a) or not isfinite(b) or abs(a-b) > 5.1e-10):
                return False
    return True


def bridge_inputs(source, payload, technical, draft, color, dtm):
    """(fonte, parametros, fatores) para process-partial; conserva origem declarada.

    Se a previa tecnica estiver obsoleta/incompativel, retorna os dados originais.
    """
    original_source = dict(source or {})
    original_payload = dict(payload or {})
    empty = (original_source, original_payload, {})
    if not isinstance(technical, dict) or not color or not dtm:
        return empty
    if (technical.get("dtm_sha256") != dtm.get("sha256")
            or technical.get("color_sha256") != color.get("sha256")
            or not _matching_points(draft, technical.get("points") or [])):
        return empty
    meta = technical.get("inputs") or {}
    if not isinstance(meta, dict) or any(
        not str(meta.get(k) or "").strip()
        for k in ("vertical_kind", "vertical_datum", "vertical_reference", "accuracy_reference")
    ):
        return empty
    model = {"NORMAL": "HGEOHNOR2020", "ORTHOMETRIC": "MAPGEO2015",
             "ELLIPSOIDAL": "NONE"}.get(meta.get("vertical_kind"))
    if model is None:
        return empty
    # Nunca sobrescrever metadados divergentes para forcar um READY.
    fields = {"vertical_kind": meta["vertical_kind"],
              "vertical_datum": meta["vertical_datum"],
              "source_model": model,
              "vertical_reference": meta["vertical_reference"],
              "accuracy_reference": meta["accuracy_reference"]}
    for name, value in fields.items():
        old = str(original_source.get(name) or "").strip()
        if old and old.casefold() != str(value).strip().casefold():
            return empty
    # Dados foram explicitamente declarados na previa, nunca inferidos de PEC.
    values = {k: meta.get(k) for k in ("sigma_e_m", "sigma_n_m", "source_sigma_m")}
    if any(not _positive(v) for v in values.values()):
        return empty
    updated_payload = dict(original_payload)
    for name, val in values.items():
        if updated_payload.get(name) is None:
            updated_payload[name] = val
    updated_source = dict(original_source)
    for name, value in fields.items():
        if not str(updated_source.get(name) or "").strip():
            updated_source[name] = value
    factors = {}
    if model != "NONE":
        if not str(meta.get("factor_reference") or "").strip():
            return empty
        raw = meta.get("factors") or {}
        if not isinstance(raw, dict) or set(raw) != {p.get("name") for p in draft}:
            return empty
        for name, pair in raw.items():
            if (not isinstance(pair, (list, tuple)) or len(pair) != 2
                    or not all(isinstance(x, (int, float)) and not isinstance(x, bool)
                               and isfinite(x) for x in pair) or pair[1] < 0):
                return empty
            factors[name] = list(pair)
    return updated_source, updated_payload, factors
