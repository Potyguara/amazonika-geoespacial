"""Validação local PB1. Não certifica o imóvel nem comprova documentos por si."""
from math import hypot, isfinite
import re

def validate_pb1_vertices(vertices, draft, preview, prefix, category, inaccessible_reason=""):
    if preview.get("sigma_origin") != "DECLARED":
        raise ValueError("PB1 exige sigmas documentados; estimativa PEC não confirmada não é suficiente.")
    rows = {p["vertex_id"]: p for p in preview.get("points", [])}
    source = {p["name"]: p for p in draft}
    selected = [v for v in vertices if v.get("sigef_method") == "PB1"]
    if not selected or len(selected) != len(source) or len(rows) != len(source):
        raise ValueError("PB1: quantidade de vértices divergente do cálculo servidor.")
    if not re.fullmatch(r"[A-Z0-9]{3,12}", prefix):
        raise ValueError("Código do credenciado inválido.")
    approved = []
    seen = set()
    for v in selected:
        code = v.get("sigef_vertex_code", "")
        name = v.get("name", "")
        if not re.fullmatch(re.escape(prefix)+r"-V-[0-9]{1,12}", code):
            raise ValueError("PB1 exige código V do credenciado.")
        if name in seen or name not in rows or name not in source:
            raise ValueError("PB1: vértice não vinculado ao cálculo.")
        seen.add(name)
        row = rows[name]
        for k in ("latitude", "longitude"):
            if not isinstance(v.get(k), (int,float)) or not isfinite(v[k]) or abs(v[k]-row[k]) > 5.1e-10 or abs(v[k]-source[name][k]) > 5.1e-10:
                raise ValueError("PB1: coordenada alterada.")
        if row.get("status") != "DECLARED_REFERENCE":
            raise ValueError("PB1: referencial vertical pendente.")
        for target, field in (("ellipsoidal_height_m","h_ellipsoidal_m"),("sigma_lon_m","sigma_e_m"),("sigma_lat_m","sigma_n_m"),("sigma_h_m","sigma_h_m")):
            value = row.get(field)
            if not isinstance(value,(int,float)) or isinstance(value,bool) or not isfinite(value) or (target.startswith("sigma") and value<=0):
                raise ValueError("PB1: altura ou sigma documentado ausente.")
            if v.get(target) != value:
                raise ValueError("PB1: atributo diferente do cálculo servidor: "+target)
        if v.get("height_reference_confirmed") is not True:
            raise ValueError("PB1: confirme o referencial.")
        boundary = str(v.get("boundary_type",""))
        if not boundary.startswith(("LA","LN")):
            raise ValueError("PB1: tipo de limite inválido.")
        if category not in ("ARTIFICIAL","NATURAL","INACCESSIBLE"):
            raise ValueError("Classifique a categoria do limite.")
        if category == "INACCESSIBLE" and len(inaccessible_reason.strip()) < 20:
            raise ValueError("Justifique a inacessibilidade.")
        limit = .5 if boundary.startswith("LA") or category=="ARTIFICIAL" else 7.5 if category=="INACCESSIBLE" else 3.
        if hypot(row["sigma_e_m"],row["sigma_n_m"]) > limit:
            raise ValueError("PB1: precisão incompatível com a categoria do limite.")
        approved.append({**v, "derived_calculation":{"method":"PB1","accuracy_verified":True,"status":"APPROVED_BY_RT"}})
    return approved
