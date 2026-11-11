"""Smoke test sem banco para o relatório editorial (1, 0 e muitas fontes)."""
from __future__ import annotations

import tempfile
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image, ImageDraw

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
        # Mapa sintético de homologação: testa o recorte real da
        # moldura cartográfica, sem se passar por dado territorial oficial.
        image = Image.new("RGB", (1600, 1050), "#F3F8F5")
        draw = ImageDraw.Draw(image)
        draw.rectangle((55, 135, 1545, 790), fill="#F6F9F7", outline="#B9C9C0", width=3)
        for x in range(200, 1500, 170):
            draw.line((x, 135, x, 790), fill="#D6E3DD", width=2)
        for y in range(200, 780, 125):
            draw.line((55, y, 1545, y), fill="#D6E3DD", width=2)
        draw.polygon([(360, 620), (520, 310), (960, 230), (1250, 460),
                      (1080, 670), (620, 710)],
                     fill="#D8E8DE", outline="#225941", width=10)
        draw.polygon([(820, 280), (1190, 350), (1310, 530), (990, 610),
                      (770, 480)], fill="#EAB4A7", outline="#B72A2B", width=8)
        draw.line([(1460, 290), (1460, 185)], fill="#174C38", width=9)
        draw.polygon([(1460, 169), (1443, 202), (1477, 202)], fill="#174C38")
        draw.text((1444, 146), "N", fill="#174C38")
        draw.line((100, 730, 350, 730), fill="#174C38", width=9)
        for x in (100, 225, 350):
            draw.line((x, 717, x, 745), fill="#174C38", width=5)
        draw.text((100, 748), "0", fill="#174C38")
        draw.text((302, 748), "500 m", fill="#174C38")
        draw.text((620, 150), "MAPA SINTETICO DE TESTE", fill="#60766B")
        image.save(map_path)
        # Impede que o teste volte a usar um painel cartográfico vazio.
        assert len(image.getcolors(maxcolors=1600 * 1050) or []) > 5

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
