from datetime import date, datetime
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from app.models.catalog import SourceKind

class SourceCreate(BaseModel):
    slug:str; name:str; institution:str; kind:SourceKind
    service_url:HttpUrl|None=None; layer_name:str|None=None
    is_official:bool=True; update_frequency:str|None=None; metadata_json:dict=Field(default_factory=dict)

class SourceUpdate(BaseModel):
    kind:SourceKind|None=None
    service_url:HttpUrl|None=None
    layer_name:str|None=None
    update_frequency:str|None=None
    is_active:bool|None=None
    portal_url:HttpUrl|None=None
    requires_auth:bool|None=None
    access_mode:Literal["PUBLIC_SERVICE","PUBLIC_WMS","GOVBR_ASSISTED"]|None=None
    service_role:Literal["VECTOR_ANALYSIS","WMS_REFERENCE","VECTOR_DOWNLOAD","WMS_REFERENCE_WITH_VECTOR_SNAPSHOT"]|None=None
    wms_url:HttpUrl|None=None
    wms_layer:str|None=None
    wms_fixed_layer:str|None=None
    wms_global:bool|None=None
    wms_urls:dict[str,HttpUrl]|None=None
    wms_available_ufs:list[str]|None=None
    wms_enabled:bool|None=None
    allow_insecure_tls:bool|None=None
    stale_after_days:int|None=Field(None,ge=1,le=365)

class SourceRead(BaseModel):
    id:UUID; slug:str; name:str; institution:str; kind:SourceKind; service_url:str|None; layer_name:str|None
    is_official:bool; is_active:bool; update_frequency:str|None; metadata_json:dict
    model_config=ConfigDict(from_attributes=True)

class VersionRead(BaseModel):
    id:UUID; source_id:UUID; reference_date:date|None; imported_at:datetime|None; feature_count:int; status:str; is_current:bool; original_filename:str|None
    checksum:str|None=None; error_message:str|None=None
    model_config=ConfigDict(from_attributes=True)
