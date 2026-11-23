"""Declinação magnética da prancha, calculada no vértice mais ao norte.

WMM2025 (NOAA/NCEI), época de 2025.0 a antes de 2030.0.
A fonte e a data integram os metadados técnicos do mapa.
"""
from __future__ import annotations
from calendar import isleap
from datetime import date
import math


def resolve_magnetic_declination(parcels, reference_date: date,
                                 *, enabled: bool, manual_degrees=None):
    if not enabled:
        return None, "Não solicitado"
    if manual_degrees is not None:
        value=float(manual_degrees)
        if not math.isfinite(value) or not -180 <= value <= 180:
            raise ValueError("Declinação magnética manual inválida.")
        return value, "Informada pelo responsável técnico"
    all_vertices=[point for parcel in parcels for point in parcel.points]
    if not all_vertices:
        raise ValueError("Não há vértices para cálculo de declinação magnética.")
    lon,lat=max(all_vertices,key=lambda xy:xy[1])
    days=366 if isleap(reference_date.year) else 365
    decimal_year=reference_date.year+(reference_date.timetuple().tm_yday-1)/days
    if not 2025 <= decimal_year < 2030:
        raise ValueError("Modelo WMM2025 exige data de referência entre 2025 e 2029.")
    from pygeomag import GeoMag
    result=GeoMag(coefficients_file="wmm/WMM_2025.COF").calculate(
        glat=lat,glon=lon,alt=0,time=decimal_year
    )
    declination=float(result.d)
    if not math.isfinite(declination):
        raise ValueError("O WMM2025 não retornou declinação magnética válida.")
    return declination, f"WMM2025 · {reference_date.strftime('%d/%m/%Y')} · h=0 km"
