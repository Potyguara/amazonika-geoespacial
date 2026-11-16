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
    longitude: float | None = Field(default=None, ge=-180, le=180)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    limit_type: str
    feature_type: str = Field(min_length=1, max_length=80)


class PS4Submission(BaseModel):
    needs_additional_vertices: bool
    evidence: PS4Evidence | None = None
    vertices: list[PS4Vertex] = Field(default_factory=list)


def evaluate_ps4(data: PS4Submission) -> dict:
    """Devolve motivos técnicos sem emitir aprovação ou acurácia fictícia."""
    if not data.needs_additional_vertices:
        if data.vertices:
            return {
                "status": "BLOCKED",
                "blockers": ["Há vértices V cadastrados; não é possível declarar não aplicável."],
                "requires_rt_review": False,
                "message": "Remova os vértices V ou habilite a etapa PS4.",
            }
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
        ids = [vertex.vertex_id.upper() for vertex in data.vertices]
        if len(ids) != len(set(ids)):
            blockers.append("Identificadores de vértice V duplicados.")
        for vertex in data.vertices:
            if vertex.longitude is None or vertex.latitude is None:
                blockers.append(f"{vertex.vertex_id}: coordenadas geográficas ausentes.")
            if vertex.limit_type not in LIMITS_M:
                blockers.append(f"{vertex.vertex_id}: tipo de limite desconhecido.")
                continue
            if vertex.feature_type in PROHIBITED:
                blockers.append(f"{vertex.vertex_id}: PS4 não permitido para esta feição.")
            if e.orthorectification_rms_m > LIMITS_M[vertex.limit_type]:
                blockers.append(
                    f"{vertex.vertex_id}: RMS documental {e.orthorectification_rms_m:g} m "
                    f"excede {LIMITS_M[vertex.limit_type]:g} m."
                )
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


def evaluate_verified_ps4(
    data: PS4Submission,
    assets: dict,
    user_id,
    piece_id,
) -> dict:
    """Acrescenta verificação de arquivos reais à avaliação declaratória.

    Metadados e RMS continuam sujeitos à análise técnica do RT.
    """
    from app.services.ps4_assets import exists_matching

    result = evaluate_ps4(data)
    if not data.needs_additional_vertices:
        return result

    blockers = list(result["blockers"])
    if data.evidence is None:
        return result

    for kind, declared in (
        ("raster", data.evidence.raster_sha256.lower()),
        ("report", data.evidence.report_sha256.lower()),
    ):
        stored = assets.get(kind)
        if not isinstance(stored, dict) or stored.get("sha256") != declared:
            blockers.append(
                f"Arquivo {kind} não corresponde à evidência armazenada nesta peça."
            )
        elif not exists_matching(user_id, piece_id, stored):
            blockers.append(
                f"Integridade do arquivo {kind} não foi comprovada no armazenamento."
            )

    raster = assets.get("raster") or {}
    extent = (raster.get("metadata") or {}).get("wgs84_extent")
    if not isinstance(extent, dict):
        blockers.append(
            "Não foi possível comprovar a cobertura geográfica da ortoimagem."
        )
    else:
        try:
            from shapely.geometry import Point, shape
            footprint = shape(extent)
            if footprint.is_empty or not footprint.is_valid:
                raise ValueError("Cobertura raster inválida.")
            for v in data.vertices:
                if v.longitude is not None and v.latitude is not None:
                    if not footprint.buffer(1e-9).covers(
                        Point(v.longitude, v.latitude)
                    ):
                        blockers.append(
                            f"{v.vertex_id}: vértice fora da cobertura GeoTIFF."
                        )
        except (ValueError, TypeError, KeyError) as exc:
            blockers.append(
                "Metadados de cobertura da imagem orbital são inválidos."
            )

    return {
        **result,
        "status": "BLOCKED" if blockers else "REVIEW_REQUIRED",
        "blockers": blockers,
        "message": (
            "Pendências técnicas impedem o fechamento."
            if blockers else
            "Arquivos armazenados e íntegros. Conferência de RMS, relatório, "
            "identificação da cena, precisão e assinatura do RT ainda obrigatórias."
        ),
    }
