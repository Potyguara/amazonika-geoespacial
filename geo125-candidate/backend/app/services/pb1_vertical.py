"""Modelo vertical PB1: preservar datum e impedir conversões implícitas.

Amostragem raster e prova do datum vertical são responsabilidades de outros
estágios. Não converter MDT color RGB em elevação.
"""
from __future__ import annotations

from math import isfinite
from typing import Literal
from pydantic import BaseModel, Field, model_validator

VerticalKind = Literal["ELLIPSOIDAL", "NORMAL", "ORTHOMETRIC", "UNKNOWN"]
ModelKind = Literal["NONE", "HGEOHNOR2020", "MAPGEO2015"]

class PB1VerticalPoint(BaseModel):
    vertex_id: str = Field(min_length=1, max_length=120)
    source_value_m: float
    source_vertical_kind: VerticalKind
    source_vertical_datum: str = Field(min_length=1, max_length=180)
    conversion_model: ModelKind = "NONE"
    conversion_factor_m: float | None = None
    source_sigma_m: float | None = Field(default=None, ge=0)
    factor_sigma_m: float | None = Field(default=None, ge=0)
    raster_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")

    @model_validator(mode="after")
    def check(self):
        values = [self.source_value_m, self.conversion_factor_m,
                  self.source_sigma_m, self.factor_sigma_m]
        if not all(x is None or isfinite(x) for x in values):
            raise ValueError("Valores verticais devem ser finitos.")
        if self.source_vertical_kind == "UNKNOWN":
            raise ValueError("Datum/tipo de altura desconhecido; confirme metadados do MDT.")
        match (self.source_vertical_kind, self.conversion_model):
            case ("ELLIPSOIDAL", "NONE"):
                if self.conversion_factor_m is not None:
                    raise ValueError("Altitude elipsoidal não requer fator de conversão.")
            case ("NORMAL", "HGEOHNOR2020") | ("ORTHOMETRIC", "MAPGEO2015"):
                if self.conversion_factor_m is None:
                    raise ValueError("Informe fator de conversão validado do IBGE.")
            case _:
                raise ValueError("Combinação de altura e modelo inconsistente.")
        return self


def convert_pb1_height(point: PB1VerticalPoint) -> dict:
    """Retorna h e rastreabilidade, sem preencher σh automaticamente."""
    factor = point.conversion_factor_m or 0.0
    h = point.source_value_m + factor
    sigma_h = None
    if point.source_vertical_kind == "ELLIPSOIDAL":
        sigma_h = point.source_sigma_m
    elif point.source_sigma_m is not None and point.factor_sigma_m is not None:
        # Propagação somente sob hipótese de componentes independentes:
        sigma_h = (point.source_sigma_m ** 2 + point.factor_sigma_m ** 2) ** 0.5
    return {
        "vertex_id": point.vertex_id,
        "h_ellipsoidal_m": round(h, 4),
        "sigma_h_m": round(sigma_h, 4) if sigma_h is not None else None,
        "source_value_m": point.source_value_m,
        "source_vertical_kind": point.source_vertical_kind,
        "source_vertical_datum": point.source_vertical_datum,
        "conversion_model": point.conversion_model,
        "conversion_factor_m": point.conversion_factor_m,
        "raster_sha256": point.raster_sha256,
        "status": "PRELIMINARY_RT_REVIEW",
        "note": "Conversão matemática não valida datum, amostra raster ou exatidão do MDT.",
    }
