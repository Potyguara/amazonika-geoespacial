"""Minimal authorized MapBiomas Earth Engine reduction (homologation only).

Only a fixed ~5 ha test envelope is analyzed with at most 5000 pixels at
30 m. No other sources are queried and no raster exports/downloads occur.
Do not run repeatedly: an Earth Engine compute request may be billed.
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

PROJECT = "amazonika-geoespacial"
ASSET = "projects/mapbiomas-public/assets/brazil/lulc/collection11/mapbiomas_brazil_collection11_coverage_v3"
YEAR = 2025
# Fixed synthetic test window near Macapa, AP, not a registered rural property.
BOUNDS = [-51.120, 0.030, -51.118, 0.032]

def main() -> int:
    if os.getenv("GEE_ALLOW_SAMPLE_REDUCTION") != "yes":
        print("BLOQUEADO: defina GEE_ALLOW_SAMPLE_REDUCTION=yes para autorizar UMA reducao de teste.")
        return 2
    if os.getenv("GEE_PROJECT_ID") != PROJECT:
        print("Projeto GEE incorreto.")
        return 2
    email = os.getenv("GEE_SERVICE_ACCOUNT_EMAIL")
    key = os.getenv("GEE_SERVICE_ACCOUNT_KEY_FILE")
    if not email or not key or not Path(key).is_file():
        print("Credenciais incompletas.")
        return 2
    try:
        import ee
        credentials = ee.ServiceAccountCredentials(email, key)
        ee.Initialize(credentials, project=PROJECT)
        rectangle = ee.Geometry.Rectangle(BOUNDS, proj="EPSG:4326", geodesic=False)
        classes = ee.Image(ASSET).select("classification_2025").rename("class")
        pixels = ee.Image.pixelArea().divide(10000).rename("ha")
        reducer = ee.Reducer.sum().group(groupField=1, groupName="class")
        result = pixels.addBands(classes).reduceRegion(
            reducer=reducer,
            geometry=rectangle,
            scale=30,
            maxPixels=5000,
            bestEffort=False,
            tileScale=4,
        ).getInfo()
        if not isinstance(result, dict) or not isinstance(result.get("groups"), list):
            print("SEM_RESULTADO: verifique cobertura do asset e dados da banda.")
            return 3
        groups = result["groups"]
        if not groups:
            print("SEM_PIXELS_CLASSIFICADOS: teste em outra area, sem inferir ausencia de uso.")
            return 3
        total = sum(float(group["sum"]) for group in groups)
        print("AMOSTRA_MAPBIOMAS_OK")
        print(f"Projeto: {PROJECT} | Colecao 11 | Ano {YEAR} | Resolucao 30 m")
        print("Janela de teste (graus):", ",".join(map(str, BOUNDS)))
        print(f"Area classificada aproximada: {total:.4f} ha")
        for group in sorted(groups, key=lambda g: -float(g["sum"])):
            print(f"Classe {int(group['class'])}: {float(group['sum']):.4f} ha")
        print("Nenhuma imagem raster foi exportada ou armazenada.")
        return 0
    except Exception as exc:
        print("FALHA_REDUCAO:", type(exc).__name__)
        print("Confira permissao, quota e acesso ao processamento Earth Engine.")
        return 4

if __name__ == "__main__":
    sys.exit(main())
