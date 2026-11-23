"""Estimativa local h = Z + média(h GNSS - Z).

Não identifica o datum original, não classifica PEC e não aprova a ODS.
Validação cruzada leave-one-out não equivale a ensaio independente.
"""
from math import isfinite, sqrt
from statistics import mean, stdev
from pyproj import Geod

GEOD = Geod(ellps="GRS80")

def _finite(value):
    return isinstance(value,(float,int)) and not isinstance(value,bool) and isfinite(value)

def fit_local_height(rows):
    valid = [r for r in rows if all(_finite(r.get(k)) for k in
             ("h_gnss_m","mdt_m","latitude","longitude"))]
    if len(valid)<4:
        raise ValueError("Ajuste exploratório: necessários ao menos quatro marcos GNSS com h confirmada e cota MDT.")
    if len({(r["longitude"],r["latitude"]) for r in valid})!=len(valid):
        raise ValueError("Controles com coordenadas duplicadas.")
    corrections=[r["h_gnss_m"]-r["mdt_m"] for r in valid]
    bias=mean(corrections)
    loo=[v-mean(corrections[:i]+corrections[i+1:]) for i,v in enumerate(corrections)]
    return {"method":"LOCAL_MEAN_OFFSET","status":"EXPLORATORY_ONLY",
            "count":len(valid),"offset_m":bias,"sample_std_m":stdev(corrections),
            "rmse_loo_m":sqrt(mean(v*v for v in loo)),
            "controls":[{**r,"correction_m":c,"loo_residual_m":e}
                        for r,c,e in zip(valid,corrections,loo)],
            "notice":"Ajuste empírico local; sem datum original identificado ou validação externa independente."}

def estimate_local_height(row, model, factor=None):
    z=row.get("source_value_m")
    if not _finite(z):
        raise ValueError("Cota MDT inválida.")
    h=z+model["offset_m"]
    controls=model["controls"]
    nearest=min(GEOD.inv(row["longitude"],row["latitude"],r["longitude"],r["latitude"])[2]
                for r in controls)
    from shapely.geometry import MultiPoint, Point
    hull=MultiPoint([(r["longitude"],r["latitude"]) for r in controls]).convex_hull
    outside=not hull.covers(Point(row["longitude"],row["latitude"]))
    result={**row,"h_ellipsoidal_m":h,"source_vertical_kind":"UNKNOWN_LOCAL_ADJUSTED",
            "status":"LOCAL_ESTIMATE_UNVALIDATED","sigma_h_m":None,
            "local_height_rmse_loo_m":model["rmse_loo_m"],
            "nearest_control_m":nearest,"outside_control_hull":outside,
            "normal_height_m":h-factor[0] if factor is not None else None}
    result["pending_reasons"]=[
        p for p in row.get("pending_reasons",[])
        if "Precisão planimétrica" in p
    ]
    result["pending_reasons"]+=["Altura h estimada por ajuste local; falta validação externa e sigma h fundamentado."]
    if outside:
        result["pending_reasons"].append("V fora do envoltório dos controles: extrapolação.")
    return result
