"""One controlled real-property MapBiomas validation (no API deployment).

Usage inside a homologation Docker image (credential mounted read-only):

  python scripts/probe_mapbiomas_real_property.py --car-code AP-... --year 2025
  python scripts/probe_mapbiomas_real_property.py --latitude 0.1 --longitude -51.2 --year 2025

Mandatory environment:
  GEE_PROJECT_ID, GEE_SERVICE_ACCOUNT_EMAIL, GEE_SERVICE_ACCOUNT_KEY_FILE
  GEE_ALLOW_REAL_PROPERTY_TEST=yes
Optional:
  GEE_TEST_MAX_HA=100 (must be between 1 and 200)

Security: no keys, CAR code, owner names, individual identifiers or full
geometries are printed. One candidate is required. Runs only one GEE
reduceRegion; no PDF, map tiles, database writes or bulk raster downloads.
A query MAY incur commercial Earth Engine charges.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path


def choose_property(car_code: str | None, lat: float | None, lon: float | None) -> dict:
    if car_code:
        from app.services.rural_official_car import fetch_car_candidate, resolve_car_candidate
        item = fetch_car_candidate(car_code)
        if item is None:
            raise ValueError("O CAR não foi localizado no serviço público; nada será processado.")
        return resolve_car_candidate(item["cadastral_code"], item["feature_id"])
    if lat is None or lon is None:
        raise ValueError("Forneça código CAR ou latitude e longitude.")
    from app.services.rural_official_sigef import locate_official_sigef, resolve_official_sigef
    found = locate_official_sigef(lat, lon)
    candidates = found["candidates"]
    if len(candidates) != 1 or found.get("has_more"):
        raise ValueError(
            "A coordenada não identificou um único imóvel SIGEF. "
            "Escolha outra coordenada ou informe o código CAR."
        )
    return resolve_official_sigef(lat, lon, candidates[0]["feature_id"])


def run_property_test(
    *,
    car_code: str | None,
    latitude: float | None,
    longitude: float | None,
    year: int,
    max_hectares: float,
) -> dict:
    if os.getenv("GEE_ALLOW_REAL_PROPERTY_TEST") != "yes":
        raise ValueError("Teste não autorizado: defina GEE_ALLOW_REAL_PROPERTY_TEST=yes.")
    if os.getenv("GEE_PROJECT_ID") != "amazonika-geoespacial":
        raise ValueError("Projeto Google Earth Engine inesperado.")
    if not (1 <= max_hectares <= 200):
        raise ValueError("Limite de homologação deve ficar entre 1 e 200 hectares.")
    from app.services.rural_mapbiomas import (
        validate_geometry, _initialize_gee,
        _reduce_class_areas, _normalize_statistics, MIN_YEAR, MAX_YEAR,
    )
    if not MIN_YEAR <= year <= MAX_YEAR:
        raise ValueError("Ano fora da cobertura da Coleção 11.")
    chosen = choose_property(car_code, latitude, longitude)
    polygon = validate_geometry(chosen["geometry"])
    from pyproj import Geod
    hectares = abs(Geod(ellps="GRS80").geometry_area_perimeter(polygon)[0]) / 10000
    if not math.isfinite(hectares) or hectares <= 0 or hectares > max_hectares:
        raise ValueError(
            f"Área do perímetro ({hectares:.2f} ha) excede limite "
            f"de homologação ({max_hectares:.2f} ha). "
            "Não houve processamento Earth Engine."
        )
    # Approximate maximum 30 m pixel count, conservatively check before
    # authentication. Geometry area is the limiting factor for this test.
    ee = _initialize_gee()
    raw = _reduce_class_areas(ee, chosen["geometry"], year)
    return _normalize_statistics(raw, year, hectares)


def main() -> int:
    parser = argparse.ArgumentParser(description="Homologação MapBiomas em um imóvel pequeno")
    ids = parser.add_mutually_exclusive_group(required=True)
    ids.add_argument("--car-code", help="CAR público do imóvel (não será exibido)")
    ids.add_argument("--latitude", type=float, help="Latitude de um ponto no imóvel SIGEF")
    parser.add_argument("--longitude", type=float, help="Longitude, obrigatória junto da latitude")
    parser.add_argument("--year", type=int, default=2025)
    parser.add_argument("--max-hectares", type=float, default=100.0)
    args = parser.parse_args()
    if (args.latitude is None) != (args.longitude is None):
        parser.error("Latitude e longitude devem ser informadas juntas.")
    try:
        result = run_property_test(
            car_code=args.car_code, latitude=args.latitude,
            longitude=args.longitude, year=args.year,
            max_hectares=args.max_hectares,
        )
    except Exception as exc:
        # Avoid printing remote exceptions that could include credentials,
        # account identifiers or registered parcel identifiers.
        print("FALHA_HOMOLOGACAO:", type(exc).__name__)
        if isinstance(exc, ValueError):
            print(str(exc)[:300])
        else:
            print("Confira fontes oficiais, limites de área, credenciais e cotas GEE.")
        return 2
    print("MAPBIOMAS_IMOVEL_REAL_OK")
    print("Ano:", result["year"], "Coleção:", result["collection"])
    print("Área geométrica (ha):", result["geometry_area_hectares"])
    print("Área classificada (ha):", result["classified_area_hectares"])
    for item in result["classes"]:
        print(f"Classe {item['code']} - {item['name']}: "
              f"{item['area_hectares']:.4f} ha / {item['percent_classified']:.2f}%")
    print("Nenhuma geometria, identificação CAR, arquivo raster ou chave foi exportada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
