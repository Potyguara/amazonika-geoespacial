from typing import Any, Literal
from uuid import UUID
from pydantic import BaseModel, Field

class AnalysisRequest(BaseModel):
    name:str=Field(min_length=3,max_length=180)
    geometry:dict[str,Any]
    source_ids:list[UUID]|None=None
    incra_uf:str|None=Field(default=None,pattern="^[A-Za-z]{2}$")

class LayerResult(BaseModel):
    source_id:UUID; source_name:str; institution:str; reference_date:str|None
    intersects:bool; matched_features:int; overlap_hectares:float; overlap_percent:float; nearest_distance_meters:float|None
    access_mode:str="LOCAL_VECTOR"

class SourceExecutionStatus(BaseModel):
    source_id: UUID
    source_name: str
    institution: str
    status: Literal["ANALYZED", "UNAVAILABLE", "FAILED"]
    message: str | None = None
    access_mode: str | None = None
    source_version_id: UUID | None = None
    reference_date: str | None = None
    intersects: bool | None = None
    matched_features: int | None = None
    overlap_hectares: float | None = None
    overlap_percent: float | None = None
    nearest_distance_meters: float | None = None


class AnalysisResponse(BaseModel):
    analysis_id:UUID; name:str; geometry_kind:Literal["POINT","POLYGON","MULTIPOLYGON"]
    area_hectares:float|None; results:list[LayerResult]
    warnings:list[str]=Field(default_factory=list)
    source_statuses:list[SourceExecutionStatus]=Field(default_factory=list)
    status:Literal["QUEUED","PROCESSING","COMPLETED","FAILED"]="COMPLETED"
    error_message:str|None=None

class AnalysisAccepted(BaseModel):
    analysis_id:UUID; name:str; geometry_kind:Literal["POINT","POLYGON","MULTIPOLYGON"]
    area_hectares:float|None; status:Literal["QUEUED","PROCESSING"]
