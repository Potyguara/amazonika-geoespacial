"""Catálogo de referências; metadados declarados não aprovam precisão ou datum de raster."""
from pathlib import Path
from uuid import uuid4
from datetime import datetime, timezone
from tempfile import NamedTemporaryFile
import json
import os
from pydantic import BaseModel, Field
from app.core.config import get_settings

class BaseProfile(BaseModel):
    name: str = Field(min_length=1,max_length=180)
    producer: str = Field(default="",max_length=250)
    distributor: str = Field(default="",max_length=250)
    product: str = Field(default="",max_length=250)
    region: str = Field(default="",max_length=150)
    scale: str = Field(default="",max_length=30)
    horizontal_crs: str = Field(default="",max_length=100)
    vertical_datum: str = Field(default="",max_length=150)
    vertical_kind: str = Field(default="",max_length=100)
    source_model: str = Field(default="",max_length=100)
    pec: str = Field(default="",max_length=50)
    resolution: str = Field(default="",max_length=100)
    format: str = Field(default="",max_length=80)
    edition: str = Field(default="",max_length=100)
    creation_date: str = Field(default="",max_length=100)
    metadata_id: str = Field(default="",max_length=150)
    reference_sheet: str = Field(default="",max_length=150)
    coverage: str = Field(default="",max_length=250)
    url: str = Field(default="",max_length=1000)
    license: str = Field(default="",max_length=500)
    accuracy_reference: str = Field(default="",max_length=2000)
    vertical_reference: str = Field(default="",max_length=2000)
    notes: str = Field(default="",max_length=3000)
    report_credit: str = Field(default="",max_length=1500)
    map_credit: str = Field(default="",max_length=250)

AMAPA = dict(BaseProfile(
    name="Base Cartográfica Digital do Amapá",
    producer="Exército Brasileiro — 4º Centro de Geoinformação",
    distributor="BDGEx",
    region="Amapá", product="SCN Carta Topográfica Matricial (referência do projeto)",
    scale="25000",horizontal_crs="SIRGAS 2000 — EPSG:4674",
    vertical_datum="Imbituba — SC (carta de referência)",
    format="GeoTIFF",edition="2020-05-20",creation_date="2016-01-01",
    metadata_id="02fcfad1-63f2-f677-3cee-feafea430c46",
    reference_sheet="Articulação Sistemática 1:25.000 (Amapá) — preencher MI/INOM da folha efetivamente utilizada",
    coverage="Folha de referência: W -51.25; S 0.5; E -51.125; N 0.625",
    url="https://app-bdgex.eb.mil.br/metadados",
    notes="Metadados de carta matricial fornecidos pelo usuário. Não comprovam datum, modelo ou PEC de MDT/ORIXP nem abrangência de outras folhas. Conferir produto e folha efetivamente utilizados.",
    report_credit="Fonte cartográfica: Base Cartográfica Digital do Amapá, Exército Brasileiro — 4º Centro de Geoinformação; distribuição BDGEx; escala de referência 1:25.000. Produto, folha e qualidade devem ser conferidos nos insumos utilizados.",
    map_credit="Fonte de restituição: Base Cartográfica Digital do Amapá | Exército Brasileiro / 4º CGEO | BDGEx | 1:25.000 (referência)"
).model_dump(),id="amapa-reference",revision=1,builtin=True)

def _path(user_id):
    return get_settings().storage_dir / "cartographic-catalog" / str(user_id) / "profiles.json"

def list_profiles(user_id):
    path=_path(user_id)
    records=json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
    return [AMAPA,*records]

def save_profile(user_id,payload,profile_id=None):
    path=_path(user_id)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    # Lock serializes concurrent read/modify/write within this account.
    import fcntl
    with open(path.parent/"write.lock","a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        records=list_profiles(user_id)[1:]
        old=next((r for r in records if r["id"]==profile_id),None)
        if profile_id and not old:
            raise ValueError("Perfil privado não encontrado; duplique a referência de sistema para editar.")
        data={k:v.strip() for k,v in payload.model_dump().items()}
        if not data["name"]: raise ValueError("Nome obrigatório.")
        if not data["report_credit"]:
            data["report_credit"]="Fonte cartográfica: "+"; ".join(v for v in (data["name"],data["producer"],data["product"],data["edition"]) if v)+"."
        if not data["map_credit"]:
            data["map_credit"]="Fonte de restituição: "+" | ".join(v for v in (data["name"],data["producer"]) if v)
            data["map_credit"]=data["map_credit"][:250]
        if not old and len(records)>=100: raise ValueError("Limite de 100 perfis por conta.")
        result=dict(data,id=profile_id or str(uuid4()),revision=(old["revision"]+1 if old else 1),
                    builtin=False,updated_at=datetime.now(timezone.utc).isoformat())
        records=[r for r in records if r["id"]!=profile_id]+[result]
        with NamedTemporaryFile(dir=path.parent,mode="w",encoding="utf-8",delete=False) as tmp:
            json.dump(records,tmp,ensure_ascii=False)
            tmp.flush();os.fsync(tmp.fileno())
        os.replace(tmp.name,path)
        return result

def delete_profile(user_id, profile_id):
    """Exclui apenas cadastro privado; referências globais são imutáveis."""
    import fcntl
    if profile_id == AMAPA["id"]:
        raise ValueError("A referência de sistema não pode ser excluída.")
    path=_path(user_id)
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with open(path.parent/"write.lock","a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        records=json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        remaining=[r for r in records if r.get("id")!=profile_id]
        if len(remaining)==len(records):
            raise ValueError("Cadastro não encontrado nesta conta.")
        with NamedTemporaryFile(dir=path.parent,mode="w",encoding="utf-8",delete=False) as tmp:
            json.dump(remaining,tmp,ensure_ascii=False)
            tmp.flush();os.fsync(tmp.fileno())
        os.replace(tmp.name,path)
    return {"deleted":profile_id}
