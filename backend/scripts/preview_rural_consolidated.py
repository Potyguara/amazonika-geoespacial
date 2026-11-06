"""Generate a demonstrative partial consolidated PDF without network or database.

Only SYNTHETIC sample information is permitted here. The output is not a
real property analysis and is NOT the 46-page finished report. The purpose
is checking PDF page design, pagination and text extraction before live
homologation. Exits if output is not an explicitly mounted directory.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
import sys

from app.schemas.rural_consolidated import SectionCode, SectionStatus
from app.services.rural_consolidated import THEMES, render_preliminary_consolidated_pdf


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("Usage: python -m scripts.preview_rural_consolidated /output", file=sys.stderr)
        return 2
    target = Path(argv[1]).resolve()
    if not target.is_dir() or not str(target).startswith("/output"):
        print("Only an existing /output directory is permitted.", file=sys.stderr)
        return 2

    sections = [{
        "code": code.value,
        "title": title,
        "status": (
            SectionStatus.COMPLETE.value
            if code in {SectionCode.IDENTIFICATION, SectionCode.METHODOLOGY}
            else SectionStatus.NOT_RUN.value
        ),
        "message": "Informações demonstrativas, sem consulta a fontes externas.",
    } for code, title in THEMES]
    embargo = next(s for s in sections if s["code"] == SectionCode.ENVIRONMENTAL_ENFORCEMENT.value)
    embargo["status"] = SectionStatus.COMPLETE.value
    embargo["message"] = "Um embargo fictício, apenas para revisão gráfica."
    monitoring = next(s for s in sections if s["code"] == SectionCode.PRODES_DETER.value)
    monitoring["status"] = SectionStatus.COMPLETE.value
    monitoring["message"] = "Uma feição fictícia, apenas para revisão gráfica."

    snapshot = {
        "report_type": "FULL_FARM_CONSOLIDATED",
        "report_stage": "PRELIMINARY_PARTIAL_SAMPLE",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "property": {
            "name": "AMOSTRA SINTÉTICA — NÃO É UMA FAZENDA REAL",
            "area_hectares": 186.6908,
            "geometry_kind": "POLYGON",
            "geometry_crs": "EPSG:4674",
            "geometry_sha256": "0" * 64,
            "cadastral_origin": "Amostra para QA visual",
            "cadastral_code": None,
            "source_analysis_id": "00000000-0000-0000-0000-000000000000",
        },
        "sections": sections,
        "territorial_evidence": {
            "sources": [],
            "analyzed_count": 0,
            "inconclusive_count": 0,
            "sources_with_intersections": 0,
            "unverified_sources": 0,
        },
        "ibama_embargos": {
            "status": "ANALYZED",
            "source": "AMOSTRA SINTÉTICA — IBAMA NÃO CONSULTADO",
            "layer": "amostra", "queried_at": "NÃO CONSULTADO",
            "count": 1, "overlap_hectares": 1.2500,
            "overlap_percent": 0.67,
            "method": "Dados fictícios para revisão de paginação.",
            "warning": "Não utilizar como comprovação de situação ambiental.",
            "features": [{"term": "AMOSTRA-FICTICIA",
                          "process": "AMOSTRA-000",
                          "overlap_hectares": 1.25}],
        },
        "monitoring_result": {
            "status": "ANALYZED",
            "source": "AMOSTRA SINTÉTICA — INPE NÃO CONSULTADO",
            "layer": "amostra", "layer_title": "PRODES — AMOSTRA FICTÍCIA",
            "program": "PRODES", "queried_at": "NÃO CONSULTADO",
            "count": 1, "overlap_hectares": 0.8,
            "method": "Dados fictícios para revisão de paginação.",
            "warning": "Não utilizar como evidência de desmatamento.",
            "features": [{"id": "AMOSTRA-001", "overlap_hectares": 0.8}],
        },
    }
    data = render_preliminary_consolidated_pdf(snapshot)
    if not data.startswith(b"%PDF"):
        raise ValueError("Renderer did not return a PDF.")
    filename = target / "AMAZONIKA_CONSOLIDADO_AMOSTRA_SINTETICA_NAO_OFICIAL.pdf"
    filename.write_bytes(data)
    print("PDF:", filename)
    print("SIZE_BYTES:", len(data))
    print("SHA256:", sha256(data).hexdigest())
    print("NOTICE: Synthetic sample; no official data queried.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
