"""One-shot map-only CAR production canary; no rerun of paid class-area reduction.

Uses class-area figures previously verified against the same CAR on 2026-11-05.
Calls the official SICAR WFS once to verify shape/area and Earth Engine once
for a thumbnail of actual categorized pixels; produces private PDF v2.

Usage requires explicit opt-in GEE_MAP_CANARY=yes and key env already used
by the earlier production canary. Does not update production API or UI.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path

from app.services.rural_official_car import fetch_car_candidate, resolve_car_candidate
from app.services.rural_mapbiomas import _normalize_statistics
from app.services.rural_mapbiomas_cartography import fetch_mapbiomas_thematic_thumbnail
from app.services.rural_mapbiomas_pdf import mapbiomas_pdf

OUTPUT = Path("/output/amazonika_mapbiomas_mapa_canary_2025.pdf")
REFERENCE_GEOMETRY_HA = 1115.1093
REFERENCE_CLASSES = {
    11: 870.7678, 6: 215.6480, 3: 18.1312,
    9: 8.0247, 33: 1.3431, 21: 1.1622,
}


def main() -> int:
    if (os.getenv("GEE_MAP_CANARY") != "yes"
            or os.getenv("GEE_PRODUCTION_CANARY") != "yes"
            or os.getenv("GEE_ALLOW_REAL_PROPERTY_TEST") != "yes"
            or os.getenv("GEE_ALLOW_LARGE_PROPERTY_TEST") != "yes"):
        print("MAPA_BLOQUEADO: autorização de miniatura real não fornecida.")
        return 2
    code = (os.getenv("CAR_TESTE") or "").strip()
    if not code or OUTPUT.exists():
        print("MAPA_BLOQUEADO: CAR ausente ou documento já existente.")
        return 2
    try:
        candidate = fetch_car_candidate(code)
        if not candidate:
            raise ValueError("CAR não encontrado no SICAR oficial.")
        if abs(candidate["area_hectares"] - REFERENCE_GEOMETRY_HA) > 0.1:
            raise ValueError("Área SICAR mudou desde a verificação de 05/11; não reutilizar estatísticas.")
        verified = resolve_car_candidate(code, candidate["feature_id"])
        # No second reduceRegion: statistics were validated for this same CAR.
        result = _normalize_statistics(
            {"groups": [{"class": k, "sum": v} for k, v in REFERENCE_CLASSES.items()]},
            year=2025, geometric_ha=REFERENCE_GEOMETRY_HA,
        )
        result["method"] += " Estatísticas reutilizadas da execução validada em 05/11/2026."
        thumbnail = fetch_mapbiomas_thematic_thumbnail(
            verified["geometry"], year=2025,
            class_codes=[row["code"] for row in result["classes"]],
        )
        pdf = mapbiomas_pdf(
            property_name="Imóvel rural — CAR validado",
            cadastral_source="SICAR — Serviço Florestal Brasileiro",
            cadastral_code="Código consultado — reservado no teste",
            report=result,
            generated_at=datetime.now(timezone.utc),
            thematic_map=thumbnail,
        )
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(OUTPUT, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(pdf)
        print("MAPBIOMAS_MAPA_CANARY_OK")
        print("CAR conferido no SICAR; pixels espaciais reais da Coleção 11, ano 2025.")
        print("Miniatura (px):", thumbnail.width, "x", thumbnail.height)
        print("Área geométrica (ha):", result["geometry_area_hectares"])
        print("Área classificada validada (ha):", result["classified_area_hectares"])
        print("PDF privado criado:", OUTPUT)
        print("Nenhuma nova redução estatística e nenhum arquivo PNG armazenado.")
        return 0
    except Exception as exc:
        print("MAPA_CANARY_FALHOU:", type(exc).__name__)
        if isinstance(exc, ValueError):
            print(str(exc)[:210])
        else:
            print("Verifique SICAR, ambiente Earth Engine e compatibilidade de miniatura.")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
