"""Small, manual Google Earth Engine authentication and MapBiomas asset smoke check.

Invoke inside an isolated API image with the private JSON key mounted read-only
and GEE_* variables supplied. Performs asset metadata access only and does NOT
process farm polygons or export imagery. Even metadata API calls may be logged
and metered by Google. Does not display access tokens or key contents.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

ASSET = (
    "projects/mapbiomas-public/assets/brazil/lulc/collection11/"
    "mapbiomas_brazil_collection11_coverage_v3"
)


def main():
    project = os.environ.get("GEE_PROJECT_ID", "").strip()
    email = os.environ.get("GEE_SERVICE_ACCOUNT_EMAIL", "").strip()
    key = Path(os.environ.get("GEE_SERVICE_ACCOUNT_KEY_FILE", ""))
    if not project or not email or not key.is_file():
        print("CONFIG_INCOMPLETA: configure projeto, e-mail e caminho do JSON privado.")
        return 2
    try:
        import ee
    except ImportError:
        print("SDK_AUSENTE: earthengine-api não instalado na imagem.")
        return 3
    try:
        credentials = ee.ServiceAccountCredentials(email, str(key))
        ee.Initialize(credentials, project=project)
        metadata = ee.data.getAsset(ASSET)
        if not isinstance(metadata, dict) or metadata.get("type") != "IMAGE":
            raise ValueError("Asset MapBiomas não retornou imagem reconhecida")
        bands = {band.get("id") for band in metadata.get("bands", [])}
        if "classification_2025" not in bands:
            raise ValueError("Banda classification_2025 não foi encontrada")
    except Exception as exc:
        # Error text can occasionally contain internal project identifiers.
        print("FALHA_GEE:", type(exc).__name__)
        print("Confira API habilitada, IAM, registro comercial, projeto e chave.")
        return 4

    print("OK: autenticação da conta de serviço e asset MapBiomas Coleção 11 acessíveis.")
    print("Projeto:", project)
    print("Banda classification_2025: disponível")
    print("Nenhuma redução, exportação ou download nacional foi iniciado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
