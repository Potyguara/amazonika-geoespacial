"""Smoke opcional de recorte real CBERS COG; nunca baixa a cena inteira.

Execute manualmente com PYTHONPATH=backend python scripts/ps4_inpe_live_smoke.py.
Requer GDAL e internet. Gera um recorte de ~40 m para teste e apaga ao sair.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from shapely.geometry import shape

from app.services.inpe_ps4_import import fetch_inpe_item, import_inpe_crop

ID = "CBERS4A_WPM_PCA_RGB321_20260410_196_132"


def main():
    item = fetch_inpe_item(ID)
    point = shape(item["geometry"]).representative_point()
    lat, lon = point.y, point.x
    bbox = (lon - 0.0002, lat - 0.0002, lon + 0.0002, lat + 0.0002)
    with TemporaryDirectory(prefix="ps4-inpe-smoke-") as folder:
        with patch("app.services.ps4_assets.get_settings",
                   return_value=SimpleNamespace(storage_dir=Path(folder))):
            result = import_inpe_crop(item, bbox, uuid4(), uuid4())
        meta = result["asset"]["metadata"]
        print("INPE_SCENE_ID:", result["provenance"]["item_id"])
        print("STORED_SHA256:", result["asset"]["sha256"])
        print("PIXELS:", meta["width"], meta["height"])
        print("SRC:", meta["crs_authority"])
        print("ORTHORECTIFICATION_RMS_AUTOMATICALLY_VERIFIED:", False)
        print("PS4_APPROVED_AUTOMATICALLY:", False)


if __name__ == "__main__":
    main()
