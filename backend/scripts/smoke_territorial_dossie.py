"""Smoke test sem banco para o relatório editorial (1, 0 e muitas fontes)."""
from __future__ import annotations

import tempfile
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from app.services.territorial_report import build_report_pdf


def snapshot(count, warnings=False):
    results = []
    for i in range(count):
        results.append({
            "source_id": str(i),
            "source_name": "Parcelas SIGEF mensais" if i == 0 else f"Fonte territorial {i + 1}",
            "institution": "Amazônika" if i == 0 else "Órgão territorial",
            "source_version_id": str(i),
            "reference_date": "2026-06-01",
            "intersects": i % 2 == 0,
            "matched_features": 2,
            "overlap_hectares": 124.8164 if i % 2 == 0 else 0,
            "overlap_percent": 100 if i % 2 == 0 else 0,
            "nearest_distance_meters": 0,
            "access_mode": "LOCAL_VECTOR",
        })
    return {
        "tracking_code": f"AG-2026-TESTE{count:02d}",
        "system": "Amazonika Geoespacial",
        "analysis_name": "Fazenda Shinzo",
        "geometry_kind": "POLYGON",
        "area_hectares": 124.8164,
        "perimeter_meters": 4975.19,
        "analysis_created_at": datetime(2026, 11, 10, 21, 47, 9, tzinfo=timezone.utc).isoformat(),
        "issued_at": datetime(2026, 11, 10, 21, 47, 15, tzinfo=timezone.utc).isoformat(),
        "executor": {"name": "RESPONSÁVEL PELO LEVANTAMENTO"},
        "issuer": {"name": "RESPONSÁVEL PELA EMISSÃO"},
        "results": results,
        "source_statuses": [],
        "warnings": ["Aviso de homologação: fonte sem resposta."] if warnings else [],
    }


def main():
    with tempfile.TemporaryDirectory(prefix="amazonika-dossie-") as tmp:
        root = Path(tmp)
        map_path = root / "mapa.png"
        Image.new("RGB", (1600, 1050), "#F3F8F5").save(map_path)

        for count, warnings in [(1, False), (0, False), (10, True)]:
            path = root / f"dossie-{count}.pdf"
            build_report_pdf(
                snapshot(count, warnings),
                map_path,
                path,
                "https://geo.amazonikaengenharia.com.br/api/v1/reports/verify/TESTE",
            )
            data = path.read_bytes()
            assert data.startswith(b"%PDF-"), "PDF inválido"
            assert len(data) > 8_000, "Arquivo PDF inesperadamente pequeno"
            preview = os.environ.get("PDF_PREVIEW_DIR")
            if preview:
                out = Path(preview)
                out.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, out / path.name)
            print(f"OK fontes={count} avisos={warnings} tamanho={len(data)} bytes")
        print("SMOKE TEST DO DOSSIÊ CONCLUÍDO")


if __name__ == "__main__":
    main()
