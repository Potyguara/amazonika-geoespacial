"""Data contract for the NEW full-farm consolidated report.

Not the pre-existing 3-page territorial overlay report. This module performs
no network calls and does not yet generate a PDF. Every section must record
its own upstream evidence and distinguish unavailable from zero findings.
"""
from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SectionStatus(str, Enum):
    NOT_RUN = "NOT_RUN"
    RUNNING = "RUNNING"
    COMPLETE = "COMPLETE"
    NO_OCCURRENCE = "NO_OCCURRENCE"
    UNAVAILABLE = "UNAVAILABLE"
    ERROR = "ERROR"
    SKIPPED_BUDGET = "SKIPPED_BUDGET"


class SectionCode(str, Enum):
    IDENTIFICATION = "IDENTIFICATION"
    TERRITORIAL_OVERLAYS = "TERRITORIAL_OVERLAYS"
    ENVIRONMENTAL_ENFORCEMENT = "ENVIRONMENTAL_ENFORCEMENT"
    DEFORESTATION_ALERTS = "DEFORESTATION_ALERTS"
    PRODES_DETER = "PRODES_DETER"
    FIRE_SCARS = "FIRE_SCARS"
    MINING_ANM = "MINING_ANM"
    LAND_COVER_MAPBIOMAS = "LAND_COVER_MAPBIOMAS"
    LAND_USE_APTITUDE = "LAND_USE_APTITUDE"
    WATER_RESOURCES = "WATER_RESOURCES"
    CULTURAL_HERITAGE_IPHAN = "CULTURAL_HERITAGE_IPHAN"
    PUBLIC_FORESTS = "PUBLIC_FORESTS"
    INFRASTRUCTURE_LOGISTICS = "INFRASTRUCTURE_LOGISTICS"
    TOPOGRAPHY_SLOPE = "TOPOGRAPHY_SLOPE"
    SOILS = "SOILS"
    PASTURE = "PASTURE"
    CLIMATE = "CLIMATE"
    METHODOLOGY = "METHODOLOGY"


class SourceEvidence(BaseModel):
    source_name: str = Field(min_length=1, max_length=180)
    institution: str = Field(min_length=1, max_length=180)
    source_version: str | None = Field(default=None, max_length=180)
    queried_at: datetime
    query_completed: bool
    result_count: int | None = Field(default=None, ge=0)
    service_reference: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def check_result_provenance(self):
        if not self.query_completed and self.result_count is not None:
            raise ValueError("Consulta inconclusiva não pode declarar contagem de resultados.")
        if self.query_completed and self.result_count is None:
            raise ValueError("Consulta concluída exige contagem explícita de registros.")
        return self


class ConsolidatedSection(BaseModel):
    code: SectionCode
    status: SectionStatus = SectionStatus.NOT_RUN
    evidence: list[SourceEvidence] = Field(default_factory=list)
    # A verified section can still show results from SOME sources and warnings
    # for others. A status COMPLETED means all required sources completed;
    # partial source coverage must be described explicitly.
    summary: str | None = Field(default=None, max_length=3000)
    warnings: list[str] = Field(default_factory=list)
    metrics: dict[str, float | int | str | None] = Field(default_factory=dict)

    @model_validator(mode="after")
    def guard_negative_conclusions(self):
        confirmed = [item for item in self.evidence if item.query_completed]
        if self.status in {SectionStatus.COMPLETE, SectionStatus.NO_OCCURRENCE} and not confirmed:
            raise ValueError("Seção concluída exige pelo menos uma consulta comprovada.")
        if self.status == SectionStatus.NO_OCCURRENCE and any(item.result_count != 0 for item in confirmed):
            raise ValueError("Sem ocorrências somente quando todas as consultas concluídas retornam zero.")
        if self.status == SectionStatus.COMPLETE and any(not item.query_completed for item in self.evidence):
            raise ValueError("Seção completa não pode ocultar fontes inconclusivas.")
        if self.status == SectionStatus.NO_OCCURRENCE and any(not item.query_completed for item in self.evidence):
            raise ValueError("Não é possível concluir ausência de ocorrência com fonte inconclusiva.")
        if self.status not in {SectionStatus.COMPLETE, SectionStatus.NO_OCCURRENCE} and self.metrics:
            raise ValueError("Indicadores quantitativos exigem seção concluída; usar dados por fonte em rascunhos.")
        return self


class PropertySnapshot(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    geometry_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    geometry_crs: Literal["EPSG:4674", "EPSG:4326"]
    area_hectares: float = Field(gt=0)
    cadastral_origin: str = Field(min_length=1, max_length=120)
    cadastral_code: str | None = Field(default=None, max_length=100)
    captured_at: datetime


class ConsolidatedReportSnapshot(BaseModel):
    property: PropertySnapshot
    sections: list[ConsolidatedSection] = Field(min_length=1)
    created_at: datetime
    report_type: Literal["FULL_FARM_CONSOLIDATED"] = "FULL_FARM_CONSOLIDATED"

    @model_validator(mode="after")
    def unique_sections(self):
        codes = [item.code for item in self.sections]
        if len(codes) != len(set(codes)):
            raise ValueError("Tema duplicado no relatório consolidado.")
        return self


def status_label(status: SectionStatus) -> str:
    return {
        SectionStatus.NOT_RUN: "Não executada",
        SectionStatus.RUNNING: "Em processamento",
        SectionStatus.COMPLETE: "Analisada",
        SectionStatus.NO_OCCURRENCE: "Consulta concluída sem ocorrências",
        SectionStatus.UNAVAILABLE: "Fonte indisponível",
        SectionStatus.ERROR: "Falha de análise",
        SectionStatus.SKIPPED_BUDGET: "Não executada por limite de cota",
    }[status]
