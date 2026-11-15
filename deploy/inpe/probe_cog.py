"""GEO90B — inspeção não destrutiva de um COG remoto CBERS-4A.

Somente metadados TIFF/geográficos, sem leitura de pixels ou download integral.
Usar exclusivamente numa rede de saída controlada (GEO83 edge).
"""
import json
import os
import sys

import rasterio
from rasterio.env import Env

COG_URL = (
    "https://data.inpe.br/bdc/data/CB4A-WPM-PCA-FUSED/"
    "v001/214/113/2026/10/"
    "CBERS4A_WPM_PCA_RGB321_20261016_214_113.tif"
)

def inspect_cog(url: str = COG_URL) -> dict:
    if url != COG_URL:
        raise ValueError("Somente a cena teste autorizada nesta etapa.")
    with Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
        GDAL_HTTP_MAX_RETRY="1",
        GDAL_HTTP_RETRY_DELAY="1",
        GDAL_HTTP_CONNECTTIMEOUT="10",
        GDAL_HTTP_TIMEOUT="25",
        VSI_CACHE="FALSE",
    ):
        with rasterio.open("/vsicurl/" + url) as src:
            data = {
                "driver": src.driver,
                "width": src.width,
                "height": src.height,
                "count": src.count,
                "crs": src.crs.to_string() if src.crs else None,
                "transform": list(src.transform)[:6],
                "bounds": [src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top],
                "block_shapes": list(src.block_shapes),
                "overviews": {str(i): src.overviews(i) for i in range(1, src.count + 1)},
                "dtypes": list(src.dtypes),
                "nodata": src.nodata,
                "compression": str(src.compression) if src.compression else None,
            }
    return data

if __name__ == "__main__":
    try:
        info = inspect_cog()
        print(json.dumps(info, ensure_ascii=False, indent=2))
        if not info["crs"]:
            print("ALERTA: GeoTIFF sem CRS identificável.", file=sys.stderr)
            sys.exit(2)
        if not any(info["overviews"].values()):
            print("ALERTA: sem pirâmides de resolução; não habilitar tiles ainda.", file=sys.stderr)
            sys.exit(3)
        print("GEO90B: metadados e overviews encontrados. Nenhum pixel foi lido.")
    except Exception as exc:
        print(f"ERRO COG: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
