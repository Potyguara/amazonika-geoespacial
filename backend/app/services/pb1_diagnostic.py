"""Local altimetric comparison; never infer a vertical datum or certify accuracy."""
from math import isfinite, sqrt
from statistics import mean, stdev


def summarize_residuals(values):
    if not values or not all(isfinite(v) for v in values):
        return None
    return {"count": len(values), "mean_m": mean(values),
            "rmse_m": sqrt(mean(v*v for v in values)),
            "sample_std_m": stdev(values) if len(values)>1 else None,
            "max_abs_m": max(abs(v) for v in values)}


def compare_mdt_controls(boundary, vertical_calculated, sample):
    normals = {p["name"]: p for p in (vertical_calculated or []) if isinstance(p,dict) and "name" in p}
    rows = []
    for p in boundary:
        code = p.get("sigef_vertex_code") or p.get("name") or ""
        if "-M-" not in code.upper() or p.get("derived_calculation"):
            continue
        if len(rows)>=100:
            raise ValueError("Limite de 100 marcos.")
        row = {"name":code,"latitude":p.get("latitude"),"longitude":p.get("longitude")}
        h = p.get("ellipsoidal_height_m") if p.get("height_reference_confirmed") is True else None
        hn = normals.get(p.get("name"),{}).get("normal_height_m")
        row.update(h_gnss_m=h, hn_ibge_m=hn, mdt_m=None, residual_h_m=None, residual_hn_m=None)
        try:
            if not all(isinstance(row[k],(int,float)) and isfinite(row[k]) for k in ("longitude","latitude")):
                raise ValueError("Coordenadas indisponíveis.")
            z=sample(row["longitude"],row["latitude"])
            if not isfinite(z): raise ValueError("Cota inválida.")
            row["mdt_m"]=z
            for key, value in (("residual_h_m",h),("residual_hn_m",hn)):
                if isinstance(value,(float,int)) and isfinite(value):
                    row[key]=z-value
        except (ValueError,RuntimeError) as exc:
            row["error"]=str(exc)
        rows.append(row)
    return {"rows":rows,
        "vs_h":summarize_residuals([r["residual_h_m"] for r in rows if r["residual_h_m"] is not None]),
        "vs_hn":summarize_residuals([r["residual_hn_m"] for r in rows if r["residual_hn_m"] is not None]),
        "status":"DIAGNOSTIC_ONLY",
        "notice":"Resíduos MDT menos referência. Comparação local não comprova datum, exatidão ou independência dos controles."}
