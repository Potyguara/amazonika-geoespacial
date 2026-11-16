"""Validação preliminar PS4 — não substitui conferência e aprovação do RT.

Somente imagens orbitais com relatório de ortorretificação podem fundamentar
vértices V pelo método PS4. Os dados informados são declarações do operador:
um resultado tecnicamente consistente ainda exige conferência documental.
"""
from __future__ import annotations

from math import isfinite
from pydantic import BaseModel, Field, model_validator

LIMITS_M = {"natural": 3.0, "artificial": 0.5, "inaccessible": 7.5}
PROHIBITED = {"fence", "confrontation_change", "marker_m"}


class PS4Evidence(BaseModel):
    scene_id: str = Field(min_length=1, max_length=200)
    raster_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    report_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    report_scene_id: str = Field(min_length=1, max_length=200)
    orthorectification_rms_m: float = Field(ge=0)
    horizontal_positional_precision_m: float = Field(ge=0)
    gsd_m: float = Field(gt=0)
    scene_crs: str = Field(min_length=3, max_length=100)
    feature_identifiable: bool = False

    @model_validator(mode="after")
    def validate_finite(self):
        if not all(isfinite(v) for v in (
            self.orthorectification_rms_m,
            self.horizontal_positional_precision_m,
            self.gsd_m,
        )):
            raise ValueError("Valores numéricos devem ser finitos.")
        return self


class PS4Vertex(BaseModel):
    vertex_id: str = Field(min_length=1, max_length=120)
    limit_type: str
    feature_type: str = Field(min_length=1, max_length=80)


class PS4Submission(BaseModel):
    needs_additional_vertices: bool
    evidence: PS4Evidence | None = None
    vertices: list[PS4Vertex] = Field(default_factory=list)


def evaluate_ps4(data: PS4Submission) -> dict:
    """Devolve motivos técnicos sem emitir aprovação ou acurácia fictícia."""
    if not data.needs_additional_vertices:
        return {
            "status": "NOT_APPLICABLE", "blockers": [],
            "requires_rt_review": False,
            "message": "Não há vértices adicionais tipo V previstos nesta etapa.",
        }

    blockers: list[str] = []
    if not data.vertices:
        blockers.append("Inclua ao menos um vértice V.")
    e = data.evidence
    if e is None:
        blockers.append("Imagem orbital e relatório de ortorretificação obrigatórios.")
    else:
        if e.scene_id.strip() != e.report_scene_id.strip():
            blockers.append("A cena informada difere da identificação no relatório.")
        if not e.feature_identifiable:
            blockers.append("A feição do limite não está identificada inequivocamente.")
        # Este serviço não tem acesso ao conteúdo dos arquivos para conferir hashes,
        # autenticidade, dados RMS ou metadados; esses itens ficam sujeitos ao RT.
        for vertex in data.vertices:
            if vertex.limit_type not in LIMITS_M:
                blockers.append(f"{vertex.vertex_id}: tipo de limite desconhecido.")
                continue
            if vertex.feature_type in PROHIBITED:
                blockers.append(f"{vertex.vertex_id}: PS4 não permitido para esta feição.")
            if e.horizontal_positional_precision_m > LIMITS_M[vertex.limit_type]:
                blockers.append(
                    f"{vertex.vertex_id}: precisão {e.horizontal_positional_precision_m:g} m "
                    f"excede {LIMITS_M[vertex.limit_type]:g} m."
                )
    return {
        "status": "BLOCKED" if blockers else "REVIEW_REQUIRED",
        "blockers": blockers,
        "requires_rt_review": True,
        "message": (
            "Pendências técnicas impedem o fechamento."
            if blockers else
            "Critérios declarados compatíveis; conferir arquivos, ortorretificação, "
            "resolução, método de cálculo e parecer do RT antes da aprovação."
        ),
    }
