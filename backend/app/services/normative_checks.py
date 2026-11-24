"""Verificações normativas de cada vértice antes da ODS SIGEF.

Referências (INCRA):
- NTGIR 3ª ed. 3.3: código = 4 caracteres do credenciado (3 nos códigos
  antigos) + tipo do vértice + sequência.
- NTGIR 4.2 / MTGIR 1.4.2: coordenadas (φ, λ, h) com precisões (σφ, σλ, σh).
- NTGIR 4.3 e 4.4 / MTGIR 1.4.3 e 1.4.4: σP = √(σφ² + σλ²) ≤ 0,50 m em limite
  artificial, ≤ 3,00 m em limite natural, ≤ 7,50 m em limite inacessível.
- MTGIR 2ª ed. Tabela 6: método × tipo de limite; Tabela 7: método × tipo
  de vértice; nota 12: PA3 com σφ, σλ, σh = 0,00 m.
"""
from __future__ import annotations

import math
import re

CODE_RE = re.compile(r"^([A-Z0-9]{3,4})-([MPV])-(\d{1,})$")

VERTEX_TYPES = {  # MTGIR Tabela 7
    **{f"PG{i}": {"M", "P"} for i in (1, 2, 3, 6, 7, 9)},
    "PG4": {"P"}, "PG5": {"P"}, "PG8": {"P"},
    **{f"PT{i}": {"M", "P"} for i in (1, 2, 3, 4, 5, 8, 9)},
    "PT6": {"M", "P", "V"}, "PT7": {"M", "P", "V"},
    **{m: {"V"} for m in ("PA1", "PA2", "PA3", "PS1", "PS2", "PS3", "PS4", "PB1", "PB2")},
}
NATURAL_ONLY = {"PG5", "PG8"}          # Tabela 6
NO_M = {"PS1", "PS2", "PS3", "PS4", "PB1", "PB2"}  # notas 19 e 20
NO_FENCE = {"PS4", "PB2"}              # nota 20: exceto limites por cerca
LIMITS_M = {"ARTIFICIAL": 0.50, "NATURAL": 3.00, "INACCESSIBLE": 7.50}


def _num(value):
    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def _limit_class(boundary_type: str) -> str | None:
    code = (boundary_type or "").strip().upper()
    if code.startswith("LA"):
        return "ARTIFICIAL"
    if code.startswith("LN"):
        return "NATURAL"
    return None


def check_vertices(vertices: list[dict], parcel_label: str) -> tuple[list[str], list[dict], list[str]]:
    """Erros bloqueantes, quadro por vértice (σP, limite, situação) e alertas."""
    errors: list[str] = []
    alerts: list[str] = []
    rows: list[dict] = []
    n = len(vertices)
    for i, v in enumerate(vertices):
        code = str(v.get("sigef_vertex_code") or v.get("code") or "").strip().upper()
        method = str(v.get("sigef_method") or "").strip().upper()
        own = str(v.get("boundary_type") or "").strip().upper()
        prev = str(vertices[i - 1].get("boundary_type") or "").strip().upper() if n > 1 else own
        label = f"{parcel_label}, vértice {code or i + 1}"
        problems: list[str] = []

        m = CODE_RE.match(code)
        vtype = m.group(2) if m else None
        if not m:
            problems.append("código fora do padrão da NTGIR 3.3 (CRED-T-0000, 4 caracteres do credenciado ou 3 nos códigos antigos)")
        if method not in VERTEX_TYPES:
            problems.append("método de posicionamento ausente ou fora da Tabela 6 do MTGIR")
        elif vtype and vtype not in VERTEX_TYPES[method]:
            problems.append(f"{method} não admite vértice tipo {vtype} (MTGIR Tabela 7: {', '.join(sorted(VERTEX_TYPES[method]))})")
        classes = {c for c in (_limit_class(own), _limit_class(prev)) if c}
        if not _limit_class(own):
            problems.append("tipo de limite (LA/LN) não informado")
        if method in NATURAL_ONLY and "ARTIFICIAL" in classes:
            problems.append(f"{method} só se aplica a limite natural (MTGIR Tabela 6)")
        if method in NO_M and vtype == "M":
            problems.append(f"{method} não se aplica a vértice tipo M (MTGIR Tabela 6, notas 19 e 20)")
        if method in NO_FENCE and ("LA1" in (own, prev)):
            problems.append(f"{method} não se aplica a limite por cerca (MTGIR Tabela 6, nota 20)")

        s_lat, s_lon, s_h = _num(v.get("sigma_lat_m")), _num(v.get("sigma_lon_m")), _num(v.get("sigma_h_m"))
        h = _num(v.get("ellipsoidal_height_m"))
        if h is None:
            problems.append("altitude elipsoidal h ausente (NTGIR 4.2)")
        if s_lat is None or s_lon is None or s_h is None:
            problems.append("σφ, σλ e σh são obrigatórios (NTGIR 2.7 e 4.5)")
        sigma_p = math.hypot(s_lat, s_lon) if s_lat is not None and s_lon is not None else None
        own_class = _limit_class(own)
        limit = LIMITS_M[own_class] if own_class else None
        strict = min((LIMITS_M[c] for c in classes), default=None)
        if method == "PA3" and any(s not in (None, 0.0) for s in (s_lat, s_lon, s_h)):
            problems.append("PA3: σφ, σλ e σh devem ser 0,00 m (MTGIR nota 12)")
        if sigma_p is not None and limit is not None and sigma_p > limit + 1e-9:
            problems.append(f"σP = {sigma_p:.3f} m acima do padrão de {limit:.2f} m (NTGIR 4.4)")
        elif sigma_p is not None and strict is not None and sigma_p > strict + 1e-9:
            alerts.append(f"{label}: σP = {sigma_p:.3f} m atende o limite do segmento seguinte, mas o vértice também encerra um limite artificial ({strict:.2f} m, NTGIR 4.4 a). Confirme o enquadramento.")
        rows.append({
            "code": code, "method": method, "vertex_type": vtype, "boundary_types": sorted({own, prev} - {""}),
            "sigma_p_m": None if sigma_p is None else round(sigma_p, 4),
            "precision_limit_m": limit, "ok": not problems, "problems": problems,
        })
        errors += [f"{label}: {p}." for p in problems]
    return errors, rows, alerts
