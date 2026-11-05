"""Production-VPS one-shot MapBiomas canary; no public endpoint or deployment.

Requires opt-in environment GEE_ALLOW_REAL_PROPERTY_TEST=yes,
GEE_ALLOW_LARGE_PROPERTY_TEST=yes and GEE_PRODUCTION_CANARY=yes.
The CAR is read from CAR_TESTE in the process environment, not CLI args.
Writes an explicitly preliminary PDF to /output with 0600 permissions,
without saving credentials, geometry GeoJSON or raw raster files.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys

from app.services.rural_mapbiomas_pdf import mapbiomas_pdf
from probe_mapbiomas_real_property import run_property_test

OUTPUT = Path("/output/amazonika_mapbiomas_canary_2025.pdf")


def main() -> int:
    if os.getenv("GEE_PRODUCTION_CANARY") != "yes":
        print("CANARY_BLOQUEADO: autorização específica de produção não configurada.")
        return 2
    if os.getenv("GEE_ALLOW_REAL_PROPERTY_TEST") != "yes" or (
        os.getenv("GEE_ALLOW_LARGE_PROPERTY_TEST") != "yes"
    ):
        print("CANARY_BLOQUEADO: autorizações de processamento não configuradas.")
        return 2
    code = (os.getenv("CAR_TESTE") or "").strip()
    if not code:
        print("CANARY_BLOQUEADO: variável CAR_TESTE ausente.")
        return 2
    if OUTPUT.exists():
        print("CANARY_BLOQUEADO: já existe relatório de teste neste diretório.")
        return 2
    try:
        result = run_property_test(
            car_code=code, latitude=None, longitude=None,
            year=2025, max_hectares=1200,
        )
        pdf = mapbiomas_pdf(
            property_name="Imóvel rural — consulta CAR validada",
            cadastral_source="SICAR — Serviço Florestal Brasileiro",
            cadastral_code="Código consultado — reservado no teste",
            report=result,
            generated_at=datetime.now(timezone.utc),
        )
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(OUTPUT), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(pdf)
        print("CANARY_PRODUCAO_OK")
        print("Fonte: SICAR | MapBiomas Coleção 11 | Ano: 2025")
        print("Área cadastral geométrica (ha):", result["geometry_area_hectares"])
        print("Área classificada (ha):", result["classified_area_hectares"])
        print("Classes classificadas:", len(result["classes"]))
        print("PDF preliminar gerado em /output/amazonika_mapbiomas_canary_2025.pdf")
        print("Sem atualização no banco, exposição de endpoint ou alteração de serviços existentes.")
        return 0
    except Exception as exc:
        print("CANARY_FALHOU:", type(exc).__name__)
        print("Consultar logs locais de infraestrutura. Chave e CAR não serão impressos.")
        return 3


if __name__ == "__main__":
    sys.exit(main())
