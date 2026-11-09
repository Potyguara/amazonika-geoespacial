from datetime import date,datetime,timezone
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
from uuid import UUID,uuid4
import hashlib
import json
import ssl
import time
from urllib.error import HTTPError,URLError
from urllib.parse import parse_qsl,urlencode,urlsplit,urlunsplit
from urllib.request import HTTPRedirectHandler,HTTPSHandler,Request as UrlRequest,build_opener
from fastapi import APIRouter,Depends,File,Form,HTTPException,Query,Request,Response,UploadFile
from sqlalchemy import func,select,text,update
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.db.session import SessionLocal,get_db
from app.models.catalog import GeoFeature,Source,SourceKind,SourceVersion
from app.models.state_boundary import StateBoundary
from app.schemas.catalog import SourceCreate,SourceRead,SourceUpdate,VersionRead
from app.services.auth import require_permission
from app.services.importer import import_geopackage,import_vector_file,synchronize_source_data,sync_arcgis_bbox,sync_incra_wfs_bbox,sync_sicar_wfs_bbox
from app.services.package_importer import ALLOWED_PACKAGE_GROUPS,import_package,inspect_package,package_sources

router=APIRouter(prefix="/sources",tags=["Fontes"],dependencies=[Depends(require_permission("sources.view"))])
INCRA_UFS={"ac":"Acre","al":"Alagoas","ap":"Amapá","am":"Amazonas","ba":"Bahia","ce":"Ceará","df":"Distrito Federal","es":"Espírito Santo","go":"Goiás","ma":"Maranhão","mt":"Mato Grosso","ms":"Mato Grosso do Sul","mg":"Minas Gerais","pa":"Pará","pb":"Paraíba","pr":"Paraná","pe":"Pernambuco","pi":"Piauí","rj":"Rio de Janeiro","rn":"Rio Grande do Norte","rs":"Rio Grande do Sul","ro":"Rondônia","rr":"Roraima","sc":"Santa Catarina","sp":"São Paulo","se":"Sergipe","to":"Tocantins"}
_health_cache={"expires":0.0,"payload":None}

MAX_LARGE_UPLOAD_BYTES=12*1024*1024*1024
MAX_CHUNK_BYTES=32*1024*1024

def _large_upload_root()->Path:
    root=get_settings().storage_dir/".chunk_uploads"
    root.mkdir(parents=True,exist_ok=True)
    return root

def _large_upload_meta(upload_id:str)->Path:
    return _large_upload_root()/upload_id/"meta.json"

def _read_large_upload(upload_id:str)->dict:
    path=_large_upload_meta(upload_id)
    if not path.exists():
        raise HTTPException(404,"Sessão de upload não encontrada.")
    return json.loads(path.read_text(encoding="utf-8"))

def _write_large_upload(upload_id:str,meta:dict)->None:
    path=_large_upload_meta(upload_id)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(".tmp")
    temporary.write_text(json.dumps(meta,ensure_ascii=False),encoding="utf-8")
    temporary.replace(path)

class OfficialOnlyRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        allowed={"geonodeincra.serpro.gov.br","acervofundiario.incra.gov.br","geoportal-spunet.gestao.gov.br","geoservicos.inde.gov.br","geoserver.car.gov.br","geo.anm.gov.br"}
        if (urlsplit(newurl).hostname or "").lower() not in allowed:
            raise HTTPError(newurl,code,"Redirecionamento externo bloqueado",headers,fp)
        return super().redirect_request(req,fp,code,msg,headers,newurl)
@router.get("",response_model=list[SourceRead])
def list_sources(db:Session=Depends(get_db)): return list(db.scalars(select(Source).order_by(Source.institution,Source.name)))

def _probe_official_source(source:Source)->dict:
    metadata=dict(source.metadata_json or {})
    target=None
    if source.kind.value=="ARCGIS_FEATURE" and source.service_url and source.layer_name is not None:
        target=f"{source.service_url.rstrip('/')}/{source.layer_name}?f=json"
    elif source.kind.value=="WFS" and source.service_url:
        separator="&" if "?" in source.service_url else "?"
        target=f"{source.service_url}{separator}{urlencode({'service':'WFS','request':'GetCapabilities','version':metadata.get('wfs_version','1.0.0')})}"
    elif metadata.get("wms_url"):
        separator="&" if "?" in str(metadata["wms_url"]) else "?"
        target=f"{metadata['wms_url']}{separator}SERVICE=WMS&REQUEST=GetCapabilities"
    if not target:
        return {"source_id":str(source.id),"name":source.name,"institution":source.institution,"status":"NOT_MONITORED","latency_ms":None,"message":"Fonte vetorial local ou manual."}
    started=time.monotonic()
    context=ssl._create_unverified_context() if metadata.get("allow_insecure_tls") else ssl.create_default_context()
    if metadata.get("allow_legacy_tls"): context.set_ciphers("DEFAULT:@SECLEVEL=1")
    request=UrlRequest(target,headers={"User-Agent":"Mozilla/5.0 Amazonika-Geoespacial/1.0","Referer":"https://geo.anm.gov.br/","Accept":"application/json,application/xml,text/xml,*/*"})
    try:
        with build_opener(HTTPSHandler(context=context)).open(request,timeout=10) as response:
            sample=response.read(2048)
            if not sample: raise ValueError("resposta vazia")
        latency=round((time.monotonic()-started)*1000)
        return {"source_id":str(source.id),"name":source.name,"institution":source.institution,"status":"HEALTHY","latency_ms":latency,"message":"Serviço oficial respondeu."}
    except Exception as exc:
        latency=round((time.monotonic()-started)*1000)
        return {"source_id":str(source.id),"name":source.name,"institution":source.institution,"status":"DOWN","latency_ms":latency,"message":str(exc)[:180]}

@router.get("/health-status")
def official_sources_health(force:bool=False,db:Session=Depends(get_db)):
    now=time.monotonic()
    if not force and _health_cache["payload"] is not None and now < _health_cache["expires"]:
        return _health_cache["payload"]
    sources=list(db.scalars(select(Source).where(Source.is_active.is_(True),Source.is_official.is_(True)).order_by(Source.institution,Source.name)))
    results=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures=[pool.submit(_probe_official_source,source) for source in sources]
        for future in as_completed(futures): results.append(future.result())
    results.sort(key=lambda item:(item["status"]=="HEALTHY",item["institution"],item["name"]))
    summary={status:sum(1 for item in results if item["status"]==status) for status in ("HEALTHY","DOWN","NOT_MONITORED")}
    payload={"summary":summary,"sources":results,"cache_seconds":300}
    _health_cache.update({"expires":time.monotonic()+300,"payload":payload})
    return payload

@router.get("/incra/catalog")
def incra_wms_catalog(db:Session=Depends(get_db)):
    sources=list(db.scalars(select(Source).where(Source.institution=="INCRA").order_by(Source.name)))
    themes=[{"source_id":str(source.id),"slug":source.slug,"name":source.name,"theme":(source.metadata_json or {}).get("wms_theme"),"enabled":bool((source.metadata_json or {}).get("wms_enabled"))} for source in sources if (source.metadata_json or {}).get("wms_theme")]
    return {"states":[{"code":code,"name":name} for code,name in INCRA_UFS.items()],"themes":themes,"default_state":"ap"}


# =====================================================================
# PACOTES VETORIAIS COMPOSTOS
# Um único GeoPackage pode alimentar várias fontes oficiais.
# =====================================================================

def _package_upload_folder(upload_id:str)->Path:
    return _large_upload_root()/f"package_{upload_id}"


def _package_upload_meta(upload_id:str)->Path:
    return _package_upload_folder(upload_id)/"meta.json"


def _read_package_upload(upload_id:str)->dict:
    path=_package_upload_meta(upload_id)
    if not path.exists():
        raise HTTPException(404,"Sessão de pacote não encontrada.")
    return json.loads(path.read_text(encoding="utf-8"))


def _write_package_upload(upload_id:str,meta:dict)->None:
    path=_package_upload_meta(upload_id)
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(meta,ensure_ascii=False,default=str),
        encoding="utf-8",
    )
    temporary.replace(path)


def _iter_package_uploads()->list[dict]:
    jobs=[]

    for meta_path in _large_upload_root().glob("package_*/meta.json"):
        try:
            meta=json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        jobs.append(meta)

    jobs.sort(
        key=lambda item: str(
            item.get("queued_at")
            or item.get("created_at")
            or ""
        ),
        reverse=True,
    )

    return jobs


def _active_package_for_group(
    group:str,
    exclude_upload_id:str|None=None,
)->dict|None:
    clean_group=group.strip().upper()

    for meta in _iter_package_uploads():
        if str(meta.get("group") or "").strip().upper()!=clean_group:
            continue

        if exclude_upload_id and meta.get("upload_id")==exclude_upload_id:
            continue

        if meta.get("status") in {"QUEUED","PROCESSING"}:
            return meta

    return None


@router.get(
    "/packages/jobs/current",
    dependencies=[Depends(require_permission("sources.import"))],
)
def current_package_job(
    group:str=Query(...),
):
    clean_group=group.strip().upper()

    if clean_group not in ALLOWED_PACKAGE_GROUPS:
        raise HTTPException(
            422,
            "Grupo inválido. Use ASSENTAMENTOS, SIGEF ou SNCI.",
        )

    candidates=[]

    for meta in _iter_package_uploads():
        if str(meta.get("group") or "").strip().upper()!=clean_group:
            continue

        status=str(meta.get("status") or "")

        if status not in {
            "UPLOADING",
            "UPLOADED",
            "INSPECTED",
            "INVALID",
            "QUEUED",
            "PROCESSING",
            "FAILED",
        }:
            continue

        # Estados que dependem de um GeoPackage finalizado só
        # podem ser retomados enquanto o arquivo físico existir.
        # UPLOADING é diferente: nessa fase os dados estão em upload.part.
        if status in {"FAILED","INVALID","UPLOADED","INSPECTED"}:
            stored_path=Path(str(meta.get("stored_path") or ""))

            if not stored_path.exists():
                continue

        candidates.append(meta)

    if not candidates:
        return {
            "group":clean_group,
            "job":None,
        }

    priority={
        "PROCESSING":0,
        "QUEUED":1,
        "UPLOADING":2,
        "UPLOADED":3,
        "INSPECTED":4,
        "FAILED":5,
        "INVALID":6,
        "READY":7,
    }

    candidates.sort(
        key=lambda meta: (
            priority.get(str(meta.get("status") or ""),99),
            str(
                meta.get("queued_at")
                or meta.get("created_at")
                or ""
            ),
        )
    )

    best_priority=priority.get(
        str(candidates[0].get("status") or ""),
        99,
    )

    same_priority=[
        meta
        for meta in candidates
        if priority.get(str(meta.get("status") or ""),99)
        == best_priority
    ]

    same_priority.sort(
        key=lambda meta: str(
            meta.get("queued_at")
            or meta.get("created_at")
            or ""
        ),
        reverse=True,
    )

    return {
        "group":clean_group,
        "job":same_priority[0],
    }


@router.post(
    "/packages/uploads/start",
    dependencies=[Depends(require_permission("sources.import"))],
)
async def start_package_upload(
    request:Request,
    db:Session=Depends(get_db),
):
    payload=await request.json()

    group=str(payload.get("group") or "").strip().upper()
    filename=Path(str(payload.get("filename") or "")).name
    reference_date_raw=str(payload.get("reference_date") or "").strip()

    try:
        file_size=int(payload.get("file_size") or 0)
    except (TypeError,ValueError):
        file_size=0

    if group not in ALLOWED_PACKAGE_GROUPS:
        raise HTTPException(
            422,
            "Grupo inválido. Use ASSENTAMENTOS, SIGEF ou SNCI.",
        )

    active_job=_active_package_for_group(group)

    if active_job:
        raise HTTPException(
            409,
            {
                "code":"PACKAGE_GROUP_BUSY",
                "message":(
                    f"Já existe um pacote {group} sendo processado."
                ),
                "upload_id":active_job.get("upload_id"),
                "status":active_job.get("status"),
            },
        )

    # Confirma também que todas as fontes do grupo estão cadastradas.
    try:
        configured_sources=package_sources(db,group)
    except ValueError as exc:
        raise HTTPException(422,str(exc)) from exc

    if not filename:
        raise HTTPException(422,"Informe o nome do GeoPackage.")

    if Path(filename).suffix.lower()!=".gpkg":
        raise HTTPException(
            400,
            "Pacotes compostos devem estar em GeoPackage (.gpkg).",
        )

    if file_size<=0:
        raise HTTPException(422,"O tamanho do arquivo é obrigatório.")

    if file_size>MAX_LARGE_UPLOAD_BYTES:
        raise HTTPException(413,"Arquivo ultrapassa o limite de 12 GB.")

    try:
        parsed_reference=date.fromisoformat(reference_date_raw)
    except ValueError as exc:
        raise HTTPException(
            422,
            "Informe uma data de referência válida no formato AAAA-MM-DD.",
        ) from exc

    upload_id=uuid4().hex
    folder=_package_upload_folder(upload_id)
    folder.mkdir(parents=True,exist_ok=False)

    part=folder/"upload.part"
    part.touch()

    meta={
        "upload_id":upload_id,
        "upload_type":"PACKAGE",
        "group":group,
        "filename":filename,
        "file_size":file_size,
        "received_bytes":0,
        "reference_date":parsed_reference.isoformat(),
        "status":"UPLOADING",
        "processing_stage":None,
        "stored_path":None,
        "sources":[
            {
                "id":str(source.id),
                "name":source.name,
                "layer":str(
                    (source.metadata_json or {}).get("source_layer") or ""
                ),
            }
            for source in configured_sources
        ],
        "created_at":datetime.now(timezone.utc).isoformat(),
        "error":None,
    }

    _write_package_upload(upload_id,meta)

    return meta


@router.get(
    "/packages/uploads/{upload_id}/status",
    dependencies=[Depends(require_permission("sources.import"))],
)
def package_upload_status(upload_id:str):
    return _read_package_upload(upload_id)


@router.post(
    "/packages/uploads/{upload_id}/chunk",
    dependencies=[Depends(require_permission("sources.import"))],
)
def upload_package_chunk(
    upload_id:str,
    offset:int=Form(...),
    chunk:UploadFile=File(...),
):
    meta=_read_package_upload(upload_id)

    if meta.get("status")!="UPLOADING":
        raise HTTPException(
            409,
            "Esta sessão de pacote não está recebendo dados.",
        )

    expected=int(meta.get("received_bytes") or 0)

    if offset!=expected:
        raise HTTPException(
            409,
            f"Offset inválido. Esperado: {expected}.",
        )

    part=_package_upload_folder(upload_id)/"upload.part"

    written=0

    with part.open("ab") as target:
        while data:=chunk.file.read(1024*1024):
            written+=len(data)

            if written>MAX_CHUNK_BYTES:
                target.truncate(expected)
                raise HTTPException(
                    413,
                    "Chunk ultrapassa 32 MiB.",
                )

            target.write(data)

    received=expected+written

    if received>int(meta["file_size"]):
        with part.open("r+b") as target:
            target.truncate(expected)

        raise HTTPException(
            422,
            "Dados recebidos ultrapassam o tamanho declarado.",
        )

    meta["received_bytes"]=received
    _write_package_upload(upload_id,meta)

    return {
        "upload_id":upload_id,
        "received_bytes":received,
        "file_size":meta["file_size"],
        "status":meta["status"],
    }


@router.post(
    "/packages/uploads/{upload_id}/complete",
    dependencies=[Depends(require_permission("sources.import"))],
)
def complete_package_upload(upload_id:str):
    meta=_read_package_upload(upload_id)

    if meta.get("status")!="UPLOADING":
        raise HTTPException(
            409,
            "Esta sessão de pacote não está aguardando finalização.",
        )

    expected=int(meta["file_size"])
    received=int(meta.get("received_bytes") or 0)

    if received!=expected:
        raise HTTPException(
            409,
            f"Upload incompleto: {received} de {expected} bytes recebidos.",
        )

    folder=_package_upload_folder(upload_id)
    part=folder/"upload.part"

    if not part.exists() or part.stat().st_size!=expected:
        raise HTTPException(
            409,
            "Arquivo parcial não corresponde ao tamanho esperado.",
        )

    root=get_settings().storage_dir
    root.mkdir(parents=True,exist_ok=True)

    destination=root/f"{upload_id}_{meta['filename']}"

    part.replace(destination)

    meta["status"]="UPLOADED"
    meta["stored_path"]=str(destination)
    meta["received_bytes"]=expected
    meta["uploaded_at"]=datetime.now(timezone.utc).isoformat()

    _write_package_upload(upload_id,meta)

    return meta


@router.post(
    "/packages/uploads/{upload_id}/inspect",
    dependencies=[Depends(require_permission("sources.import"))],
)
def inspect_uploaded_package(
    upload_id:str,
    db:Session=Depends(get_db),
):
    meta=_read_package_upload(upload_id)

    if meta.get("status") not in {"UPLOADED","INSPECTED","FAILED"}:
        raise HTTPException(
            409,
            "Finalize o upload antes de inspecionar o pacote.",
        )

    path=Path(str(meta.get("stored_path") or ""))

    if not path.exists():
        raise HTTPException(
            404,
            "Arquivo armazenado do pacote não encontrado.",
        )

    try:
        inspection=inspect_package(
            db,
            str(meta["group"]),
            path,
        )
    except Exception as exc:
        raise HTTPException(
            422,
            f"Falha ao inspecionar o pacote: {str(exc)[:2000]}",
        ) from exc

    meta["inspection"]=inspection
    meta["status"]="INSPECTED" if inspection.get("valid") else "INVALID"
    meta["error"]=None if inspection.get("valid") else (
        "O GeoPackage não contém todas as camadas configuradas."
    )

    _write_package_upload(upload_id,meta)

    return meta


@router.post(
    "/packages/uploads/{upload_id}/process",
    status_code=202,
    dependencies=[Depends(require_permission("sources.import"))],
)
def process_uploaded_package(upload_id:str):
    meta=_read_package_upload(upload_id)

    active_job=_active_package_for_group(
        str(meta.get("group") or ""),
        exclude_upload_id=upload_id,
    )

    if active_job:
        raise HTTPException(
            409,
            {
                "code":"PACKAGE_GROUP_BUSY",
                "message":"Já existe outro pacote deste grupo em processamento.",
                "upload_id":active_job.get("upload_id"),
                "status":active_job.get("status"),
            },
        )

    if meta.get("status") not in {"UPLOADED","INSPECTED","FAILED"}:
        if meta.get("status") in {"QUEUED","PROCESSING"}:
            raise HTTPException(
                409,
                {
                    "code":"PACKAGE_ALREADY_PROCESSING",
                    "message":"O pacote já está sendo processado.",
                    "upload_id":upload_id,
                    "status":meta.get("status"),
                },
            )

        raise HTTPException(
            409,
            "O pacote precisa estar enviado e válido antes do processamento.",
        )

    if meta.get("status")=="FAILED":
        stored_path=Path(str(meta.get("stored_path") or ""))

        if not stored_path.exists():
            raise HTTPException(
                409,
                {
                    "code":"PACKAGE_FILE_NOT_AVAILABLE",
                    "message":(
                        "O arquivo desta tentativa não está mais disponível. "
                        "Envie o GeoPackage novamente."
                    ),
                },
            )

    if meta.get("status") in {"INSPECTED","FAILED"}:
        inspection=meta.get("inspection") or {}

        if not inspection.get("valid"):
            raise HTTPException(
                409,
                "O pacote não passou pela validação das camadas.",
            )

    meta["status"]="QUEUED"
    meta["processing_code"]="QUEUED"
    meta["processing_stage"]="Aguardando processamento"
    meta["progress_percent"]=0
    meta["queued_at"]=datetime.now(timezone.utc).isoformat()
    meta["processing_started_at"]=None
    meta["processing_finished_at"]=None
    meta["current_layer"]=None
    meta["current_source"]=None
    meta["current_layer_index"]=None
    meta["total_layers"]=None
    meta["current_layer_total_features"]=None
    meta["completed_layers"]=[]
    meta["result"]=None
    meta["error"]=None
    meta["error_code"]=None
    meta["error_title"]=None
    meta["error_detail"]=None
    meta["error_retryable"]=False

    _write_package_upload(upload_id,meta)

    return {
        "upload_id":upload_id,
        "group":meta["group"],
        "status":"QUEUED",
        "message":"O pacote foi enviado para processamento.",
    }


@router.get("/{source_id}/versions",response_model=list[VersionRead])
def list_source_versions(source_id:UUID,db:Session=Depends(get_db)):
    if not db.get(Source,source_id): raise HTTPException(404,"Fonte não encontrada.")
    stmt=select(SourceVersion).where(SourceVersion.source_id==source_id).order_by(SourceVersion.reference_date.desc().nullslast(),SourceVersion.created_at.desc())
    return list(db.scalars(stmt))

@router.post("/{source_id}/versions/{version_id}/activate",response_model=VersionRead,dependencies=[Depends(require_permission("sources.manage"))])
def activate_source_version(source_id:UUID,version_id:UUID,db:Session=Depends(get_db)):
    version=db.scalar(select(SourceVersion).where(SourceVersion.id==version_id,SourceVersion.source_id==source_id))
    if not version: raise HTTPException(404,"Versão não encontrada para esta fonte.")
    if version.status!="READY": raise HTTPException(409,"Somente versões importadas com sucesso podem ser ativadas.")
    db.execute(update(SourceVersion).where(SourceVersion.source_id==source_id).values(is_current=False))
    version.is_current=True
    db.commit(); db.refresh(version)
    return version


@router.get("/{source_id}/extent")
def source_current_extent(source_id:UUID,db:Session=Depends(get_db)):
    """Enquadramento geográfico da versão vetorial ativa (EPSG:4674)."""
    source=db.get(Source,source_id)
    if not source:
        raise HTTPException(404,"Fonte não encontrada.")

    version=db.scalar(
        select(SourceVersion).where(
            SourceVersion.source_id==source_id,
            SourceVersion.is_current.is_(True),
            SourceVersion.status=="READY",
        )
    )
    if not version:
        return {"source_id":str(source_id),"feature_count":0,"bbox":None,"crs":"EPSG:4674"}

    bounds=db.execute(text("""
        WITH bounds AS (
            SELECT ST_Extent(gf.geom)::geometry AS geom
            FROM geo_features gf
            WHERE gf.version_id=:version_id
        )
        SELECT ST_XMin(geom),ST_YMin(geom),ST_XMax(geom),ST_YMax(geom)
        FROM bounds
    """),{"version_id":version.id}).one()

    bbox=[float(value) for value in bounds] if all(value is not None for value in bounds) else None
    return {
        "source_id":str(source_id),
        "feature_count":version.feature_count,
        "bbox":bbox,
        "crs":"EPSG:4674",
    }


@router.get("/{source_id}/tiles/{uf}/{z}/{x}/{y}.pbf")
def source_vector_tile(
    source_id:UUID,
    uf:str,
    z:int,
    x:int,
    y:int,
    db:Session=Depends(get_db),
):
    source=db.get(Source,source_id)
    if not source:
        raise HTTPException(404,"Fonte não encontrada.")

    clean_uf=(uf or "").strip().lower()

    if clean_uf != "all" and clean_uf not in INCRA_UFS:
        raise HTTPException(422,"UF inválida.")

    if z<0 or z>22:
        raise HTTPException(422,"Zoom inválido.")

    max_index=(1 << z)-1
    if x<0 or y<0 or x>max_index or y>max_index:
        raise HTTPException(422,"Coordenada de tile inválida.")

    version=db.scalar(
        select(SourceVersion)
        .where(
            SourceVersion.source_id==source_id,
            SourceVersion.is_current.is_(True),
            SourceVersion.status=="READY",
        )
    )

    if not version:
        db.close()
        return Response(
            content=b"",
            media_type="application/vnd.mapbox-vector-tile",
            headers={"Cache-Control":"public, max-age=300"},
        )

    version_id=version.id
    source_name=source.name
    db.close()

    state_filter = ""
    params = {
        "z":z,
        "x":x,
        "y":y,
        "version_id":version_id,
        "source_id_text":str(source_id),
        "source_name":source_name,
    }

    if clean_uf != "all":
        # A malha de UFs é uma carga estrutural independente dos pacotes.
        # Em ambientes de homologação novos ela pode estar vazia. Nesse caso
        # não ocultamos todos os vetores: mantemos o recorte do próprio tile.
        with db.get_bind().connect() as connection:
            boundary_available=connection.execute(
                text("SELECT EXISTS (SELECT 1 FROM state_boundaries WHERE uf=:uf)"),
                {"uf":clean_uf.upper()},
            ).scalar_one()
        if boundary_available:
            state_filter = """
                  AND EXISTS (
                      SELECT 1
                      FROM state_boundaries sb
                      WHERE sb.uf=:uf
                        AND gf.geom && sb.geom
                        AND ST_Intersects(gf.geom,sb.geom)
                  )
            """
            params["uf"]=clean_uf.upper()

    sql=text(f"""
        WITH tile_bounds AS (
            SELECT
                ST_TileEnvelope(:z,:x,:y) AS geom_3857,
                ST_Transform(ST_TileEnvelope(:z,:x,:y),4674) AS geom_4674
        ),
        selected AS (
            SELECT
                gf.id::text AS feature_id,
                gf.external_id,
                gf.name,
                :source_id_text AS source_id,
                :source_name AS source_name,
                ST_AsMVTGeom(
                    ST_Transform(gf.geom,3857),
                    tb.geom_3857,
                    4096,
                    64,
                    true
                ) AS geom
            FROM geo_features gf
            CROSS JOIN tile_bounds tb
            WHERE gf.version_id=:version_id
              AND gf.geom && tb.geom_4674
              AND ST_Intersects(gf.geom,tb.geom_4674)
              {state_filter}
        )
        SELECT ST_AsMVT(selected,'features',4096,'geom')
        FROM selected
        WHERE geom IS NOT NULL
    """)

    with db.get_bind().connect() as connection:
        tile=connection.execute(sql,params).scalar()

    content=bytes(tile) if tile else b""

    return Response(
        content=content,
        media_type="application/vnd.mapbox-vector-tile",
        headers={
            "Cache-Control":"public, max-age=300",
            "X-Source-Version":str(version_id),
        },
    )


@router.get("/{source_id}/features")
def source_features(source_id:UUID,bbox:str|None=None,uf:str|None=None,zoom:float|None=Query(None,ge=0,le=24),limit:int=Query(1500,ge=1,le=5000),db:Session=Depends(get_db)):
    source=db.get(Source,source_id)
    if not source: raise HTTPException(404,"Fonte não encontrada.")

    clean_uf=(uf or "").strip().lower()
    if clean_uf and clean_uf not in INCRA_UFS:
        raise HTTPException(422,"UF inválida.")

    bounds=None
    if bbox:
        try:
            minx,miny,maxx,maxy=[float(value) for value in bbox.split(",")]
            if minx>=maxx or miny>=maxy: raise ValueError
            bounds=(minx,miny,maxx,maxy)
        except (TypeError,ValueError):
            raise HTTPException(422,"BBOX inválido. Use minx,miny,maxx,maxy em EPSG:4674.")
    metadata=dict(source.metadata_json or {})
    version=None
    materialize=(metadata.get("arcgis_on_demand") and (zoom or 0)>=7) or (metadata.get("wfs_on_demand") and (zoom or 0)>=9)
    if bounds and materialize:
        cache_payload={"uf":clean_uf or None,"bounds":[round(value,5) for value in bounds]}
        cache_key=hashlib.sha256(json.dumps(cache_payload,sort_keys=True).encode()).hexdigest()[:24]
        try:
            if metadata.get("arcgis_on_demand"):
                version=sync_arcgis_bbox(db,source,bounds,cache_key)
            elif clean_uf not in INCRA_UFS:
                raise ValueError("Informe uma UF válida para consultar os vetores oficiais.")
            elif source.institution=="SICAR":
                version=sync_sicar_wfs_bbox(db,source,clean_uf,bounds,cache_key)
            else:
                version=sync_incra_wfs_bbox(db,source,clean_uf,bounds,cache_key)
        except Exception as exc:
            # O WMS continua disponível como referência; a resposta explicita que
            # nenhuma imagem foi convertida em vetor silenciosamente.
            return {"type":"FeatureCollection","features":[],"source_id":str(source_id),"source_name":source.name,"version":None,"vector_error":str(exc)[:400]}
    if version is None:
        version=db.scalar(select(SourceVersion).where(SourceVersion.source_id==source_id,SourceVersion.is_current.is_(True),SourceVersion.status=="READY"))
    if not version: return {"type":"FeatureCollection","features":[],"source_id":str(source_id),"source_name":source.name,"version":None}
    # A listagem usada pelo mapa leva somente os identificadores essenciais.
    # Os atributos completos são consultados apenas quando o usuário identifica a feição.
    tolerance=0.0002 if zoom is not None and zoom<=9 else 0.00008 if zoom is not None and zoom<=11 else 0
    display_geom=func.ST_SimplifyPreserveTopology(GeoFeature.geom,tolerance) if tolerance else GeoFeature.geom

    state_geom=None
    if clean_uf:
        state_geom=(
            select(StateBoundary.geom)
            .where(StateBoundary.uf==clean_uf.upper())
            .scalar_subquery()
        )

        # A UF é usada para selecionar as feições espacialmente.
        # O recorte geométrico em tempo real foi removido da visualização
        # para evitar custo elevado de ST_Intersection a cada movimento do mapa.

    stmt=select(
        GeoFeature.id,
        GeoFeature.external_id,
        GeoFeature.name,
        func.ST_AsGeoJSON(display_geom),
    ).where(GeoFeature.version_id==version.id)

    if bounds:
        minx,miny,maxx,maxy=bounds
        envelope=func.ST_MakeEnvelope(minx,miny,maxx,maxy,4674)
        stmt=stmt.where(func.ST_Intersects(GeoFeature.geom,envelope))

    if state_geom is not None:
        stmt=stmt.where(func.ST_Intersects(GeoFeature.geom,state_geom))

    rows=db.execute(stmt.limit(limit)).all()
    features=[]
    for feature_id,external_id,name,geometry_json in rows:
        attributes={"feature_id":str(feature_id),"external_id":external_id,"name":name,"source_id":str(source_id),"source_name":source.name}
        features.append({"type":"Feature","id":str(feature_id),"geometry":json.loads(geometry_json),"properties":attributes})
    return {"type":"FeatureCollection","features":features,"source_id":str(source_id),"source_name":source.name,"version":str(version.id),"truncated":len(rows)>=limit}


@router.post("/identify")
async def identify_local_features(
    request: Request,
    db: Session = Depends(get_db),
):
    payload = await request.json()

    coordinate = payload.get("coordinate") or []
    raw_source_ids = payload.get("source_ids") or []
    tolerance_m = float(payload.get("tolerance_m") or 3.0)

    if (
        not isinstance(coordinate, list)
        or len(coordinate) != 2
    ):
        raise HTTPException(
            422,
            "Informe a coordenada [longitude, latitude].",
        )

    try:
        longitude = float(coordinate[0])
        latitude = float(coordinate[1])
    except (TypeError, ValueError):
        raise HTTPException(422, "Coordenada inválida.")

    source_ids = []
    for value in raw_source_ids:
        try:
            source_ids.append(UUID(str(value)))
        except (TypeError, ValueError):
            continue

    if not source_ids:
        return {"features": []}

    # No máximo 100 resultados por clique para impedir respostas
    # descontroladas em locais com muitas sobreposições.
    output = []

    for source_id in source_ids:
        source = db.get(Source, source_id)

        if not source or not source.is_active:
            continue

        # SIGEF Brasil usa GeoNode/WMS como referência atual.
        # Nunca identificar a antiga cópia vetorial local.
        if source.slug == "incra-sigef-brasil":
            continue

        version = db.scalar(
            select(SourceVersion).where(
                SourceVersion.source_id == source_id,
                SourceVersion.is_current.is_(True),
                SourceVersion.status == "READY",
            )
        )

        if not version:
            continue

        rows = db.execute(
            text(
                """
                SELECT
                    g.id,
                    g.external_id,
                    g.name,
                    g.properties,
                    ST_AsGeoJSON(ST_Force2D(g.geom)) AS geometry_json
                FROM geo_features g
                WHERE g.version_id = :version_id
                  AND ST_DWithin(
                      ST_Force2D(g.geom)::geography,
                      ST_SetSRID(
                          ST_MakePoint(:longitude, :latitude),
                          4674
                      )::geography,
                      :tolerance_m
                  )
                ORDER BY
                    ST_Distance(
                        ST_Force2D(g.geom)::geography,
                        ST_SetSRID(
                            ST_MakePoint(:longitude, :latitude),
                            4674
                        )::geography
                    )
                LIMIT 10
                """
            ),
            {
                "version_id": version.id,
                "longitude": longitude,
                "latitude": latitude,
                "tolerance_m": tolerance_m,
            },
        ).all()

        for (
            feature_id,
            external_id,
            name,
            properties,
            geometry_json,
        ) in rows:
            attrs = dict(properties or {})
            attrs.update(
                {
                    "feature_id": str(feature_id),
                    "external_id": external_id,
                    "name": name,
                    "source_id": str(source_id),
                    "source_name": source.name,
                }
            )

            output.append(
                {
                    "type": "Feature",
                    "id": str(feature_id),
                    "geometry": json.loads(geometry_json),
                    "properties": attrs,
                    "source_id": str(source_id),
                    "source_name": source.name,
                    "institution": source.institution,
                }
            )

            if len(output) >= 100:
                return {"features": output, "truncated": True}

    return {
        "features": output,
        "truncated": False,
    }


@router.get("/{source_id}/features/{feature_id}")
def source_feature_detail(source_id:UUID,feature_id:UUID,db:Session=Depends(get_db)):
    source=db.get(Source,source_id)
    if not source: raise HTTPException(404,"Fonte não encontrada.")
    row=db.execute(
        select(GeoFeature.id,GeoFeature.external_id,GeoFeature.name,GeoFeature.properties,func.ST_AsGeoJSON(GeoFeature.geom))
        .join(SourceVersion,SourceVersion.id==GeoFeature.version_id)
        .where(GeoFeature.id==feature_id,SourceVersion.source_id==source_id)
    ).one_or_none()
    if not row: raise HTTPException(404,"Feição não encontrada.")
    internal_id,external_id,name,properties,geometry_json=row
    attributes=dict(properties or {})
    attributes.update({"feature_id":str(internal_id),"external_id":external_id,"name":name,"source_id":str(source_id),"source_name":source.name})
    return {"type":"Feature","id":str(internal_id),"geometry":json.loads(geometry_json),"properties":attributes}
@router.post("",response_model=SourceRead,status_code=201,dependencies=[Depends(require_permission("sources.manage"))])
def create_source(payload:SourceCreate,db:Session=Depends(get_db)):
    if db.scalar(select(Source).where(Source.slug==payload.slug)): raise HTTPException(409,"Já existe uma fonte com este identificador.")
    source=Source(**payload.model_dump(mode="json")); db.add(source); db.commit(); db.refresh(source); return source

CUSTOM_CATEGORIES={
    "CAR_SICAR":"Cadastro Ambiental Rural (CAR / SICAR)",
    "SPU":"Patrimônio da União (SPU)",
    "ASSENTAMENTO_ESTADUAL":"Assentamento estadual",
    "ASSENTAMENTO_MUNICIPAL":"Assentamento municipal",
    "UC_ESTADUAL":"Unidade de conservação estadual",
    "UC_MUNICIPAL":"Unidade de conservação municipal",
    "AMBIENTAL_ESTADUAL":"Outra base ambiental estadual",
    "FUNDIARIO_ESTADUAL":"Outra base fundiária estadual",
    "OUTRO":"Outro vetor territorial",
}


@router.post(
    "/custom-vector/register",
    status_code=201,
    dependencies=[Depends(require_permission("sources.manage"))],
)
async def register_custom_vector(
    request: Request,
    db: Session = Depends(get_db),
):
    payload = await request.json()

    clean_name = str(payload.get("name") or "").strip()
    clean_category = str(payload.get("category") or "").strip().upper()
    clean_uf = str(payload.get("uf") or "").strip().lower()
    institution = str(payload.get("institution") or "").strip()
    source_url = str(payload.get("source_url") or "").strip()
    notes = str(payload.get("notes") or "").strip()

    if len(clean_name) < 3:
        raise HTTPException(
            422,
            "Informe um nome com pelo menos 3 caracteres.",
        )

    if clean_category not in CUSTOM_CATEGORIES:
        raise HTTPException(
            422,
            "Categoria de camada adicional inválida.",
        )

    if clean_uf not in INCRA_UFS:
        raise HTTPException(422, "UF inválida.")

    source = Source(
        slug=f"regional-{clean_uf}-{uuid4().hex[:12]}",
        name=clean_name,
        institution=institution or "Fonte regional",
        kind=SourceKind.MANUAL,
        is_official=False,
        is_active=True,
        update_frequency="MANUAL",
        metadata_json={
            "custom_layer": True,
            "scope_uf": clean_uf.upper(),
            "custom_category": clean_category,
            "custom_category_label": CUSTOM_CATEGORIES[clean_category],
            "default_visible": True,
            "crs": "EPSG:4674",
            "service_role": "VECTOR_ANALYSIS",
            "local_vector_primary": clean_category in {"CAR_SICAR", "SPU"},
            "source_url": source_url or None,
            "notes": notes or None,
        },
    )

    db.add(source)
    db.commit()
    db.refresh(source)

    return {
        "source": SourceRead.model_validate(source),
    }


@router.post("/custom-vector",status_code=201,dependencies=[Depends(require_permission("sources.manage"))])
def create_custom_vector(
    name:str=Form(...),category:str=Form(...),uf:str=Form(...),
    institution:str|None=Form(None),reference_date:date|None=Form(None),
    source_url:str|None=Form(None),notes:str|None=Form(None),
    layer_name:str|None=Form(None),file:UploadFile=File(...),db:Session=Depends(get_db),
):
    clean_name=name.strip()
    clean_category=category.strip().upper()
    clean_uf=uf.strip().lower()
    if len(clean_name)<3: raise HTTPException(422,"Informe um nome com pelo menos 3 caracteres.")
    if clean_category not in CUSTOM_CATEGORIES: raise HTTPException(422,"Categoria de camada adicional inválida.")
    if clean_uf not in INCRA_UFS: raise HTTPException(422,"UF inválida.")
    if not file.filename: raise HTTPException(400,"Selecione um arquivo vetorial.")
    suffix=Path(file.filename).suffix.lower()
    if suffix not in {".gpkg",".kml",".geojson",".json",".zip"}:
        raise HTTPException(400,"Formato não aceito. Use GeoPackage, KML, GeoJSON ou Shapefile compactado em ZIP.")
    source=Source(
        slug=f"regional-{clean_uf}-{uuid4().hex[:12]}",name=clean_name,
        institution=(institution or "Fonte regional").strip() or "Fonte regional",
        kind=SourceKind.MANUAL,is_official=False,is_active=True,update_frequency="MANUAL",
        metadata_json={
            "custom_layer":True,
            "scope_uf":clean_uf.upper(),
            "custom_category":clean_category,
            "custom_category_label":CUSTOM_CATEGORIES[clean_category],
            "default_visible":True,
            "crs":"EPSG:4674",
            "service_role":"VECTOR_ANALYSIS",
            "local_vector_primary":clean_category in {"CAR_SICAR","SPU"},
            "source_url":(source_url or "").strip() or None,
            "notes":(notes or "").strip() or None,
        },
    )
    db.add(source); db.commit(); db.refresh(source)
    root=get_settings().storage_dir; root.mkdir(parents=True,exist_ok=True)
    destination=root/f"{uuid4()}_{Path(file.filename).name}"
    with destination.open("wb") as target:
        while chunk:=file.file.read(1024*1024): target.write(chunk)
    try:
        version=import_vector_file(db,source,destination,reference_date,layer_name,Path(file.filename).name)
        return {"source":SourceRead.model_validate(source),"version":VersionRead.model_validate(version)}
    except Exception as exc:
        db.rollback()
        persisted=db.get(Source,source.id)
        if persisted: db.delete(persisted); db.commit()
        raise HTTPException(422,f"Falha ao importar a camada adicional: {str(exc)[:600]}") from exc

@router.patch("/{source_id}",response_model=SourceRead,dependencies=[Depends(require_permission("sources.manage"))])
def update_source(source_id:UUID,payload:SourceUpdate,db:Session=Depends(get_db)):
    source=db.get(Source,source_id)
    if not source: raise HTTPException(404,"Fonte não encontrada.")
    changes=payload.model_dump(exclude_unset=True,mode="json")
    metadata=dict(source.metadata_json or {})
    for field in ("portal_url","requires_auth","access_mode","service_role","wms_url","wms_layer","wms_urls","wms_available_ufs","wms_enabled","allow_insecure_tls","stale_after_days"):
        if field in changes: metadata[field]=changes.pop(field)
    for field,value in changes.items(): setattr(source,field,value)

    # SICAR e SPU oficiais podem manter WMS como referência visual, mas
    # nunca devem acionar WFS/ArcGIS sob demanda nem TLS legado para a
    # operação territorial. O vetor operacional vem das cargas por UF.
    if (
        source.institution.upper() in {"SICAR", "SPU"}
        and metadata.get("service_role") == "WMS_REFERENCE"
    ):
        metadata["wfs_on_demand"] = False
        metadata["arcgis_on_demand"] = False
        metadata["allow_insecure_tls"] = False
        metadata["allow_legacy_tls"] = False
        source.service_url = None
        source.layer_name = None
        source.kind = SourceKind.DOWNLOAD

    source.metadata_json=metadata
    db.commit(); db.refresh(source); return source


SIGEF_UF_IBGE = {
    "ro": 11, "ac": 12, "am": 13, "rr": 14,
    "pa": 15, "ap": 16, "to": 17,
    "ma": 21, "pi": 22, "ce": 23, "rn": 24,
    "pb": 25, "pe": 26, "al": 27, "se": 28,
    "ba": 29, "mg": 31, "es": 32, "rj": 33,
    "sp": 35, "pr": 41, "sc": 42, "rs": 43,
    "ms": 50, "mt": 51, "go": 52, "df": 53,
}

SIGEF_GEONODE_WFS = (
    "https://geonodeincra.serpro.gov.br/"
    "geoserver/geonode/sigef_geo/ows"
)

@router.get("/{source_id}/wms")
def proxy_source_wms(source_id:UUID,request:Request,db:Session=Depends(get_db)):
    source=db.get(Source,source_id)
    if not source:
        raise HTTPException(404,"Fonte não encontrada.")

    # Copia somente os dados necessários e libera imediatamente a conexão
    # com o PostgreSQL. A chamada ao WMS oficial pode levar dezenas de
    # segundos e não deve ocupar uma conexão do pool durante esse período.
    metadata=dict(source.metadata_json or {})
    source_name=source.name
    source_institution=source.institution
    source_slug=source.slug
    db.close()

    if not metadata.get("wms_enabled"):
        raise HTTPException(404,"O WMS não está habilitado para esta fonte.")
    requested_uf=str(request.query_params.get("uf") or metadata.get("wms_state") or "ap").lower()
    if source_slug == "incra-sigef-brasil":
        if requested_uf != "all" and requested_uf not in SIGEF_UF_IBGE:
            raise HTTPException(422, "UF inválida para SIGEF Brasil.")
    elif requested_uf not in INCRA_UFS:
        raise HTTPException(422, "UF inválida para o serviço WMS.")
    theme=str(metadata.get("wms_theme") or "").strip()
    fixed_layer=str(metadata.get("wms_fixed_layer") or "").strip()
    state_urls=dict(metadata.get("wms_urls") or {})
    available_ufs=set(metadata.get("wms_available_ufs") or state_urls.keys())
    if (
        source_slug != "incra-sigef-brasil"
        and available_ufs
        and requested_uf not in available_ufs
    ):
        raise HTTPException(
            404,
            f"A camada {source_name} não está publicada pelo INCRA para {requested_uf.upper()}.",
        )
    incra_url=f"http://acervofundiario.incra.gov.br/i3geo/ogc.php?tema={theme}_{requested_uf}"
    raw_url=str(state_urls.get(requested_uf) or (incra_url if source_institution=="INCRA" and theme and not fixed_layer else metadata.get("wms_url") or ""))
    parsed=urlsplit(raw_url)
    allowed_hosts={"geonodeincra.serpro.gov.br","acervofundiario.incra.gov.br","geoportal-spunet.gestao.gov.br","geoservicos.inde.gov.br","geoserver.car.gov.br","geo.anm.gov.br"}
    if parsed.scheme not in ("http","https") or (parsed.hostname or "").lower() not in allowed_hosts:
        raise HTTPException(400,"O proxy aceita somente os domínios oficiais configurados.")
    incoming=[
        (key,value)
        for key,value in request.query_params.multi_items()
        if key.lower() != "uf"
    ]
    if source_slug == "incra-sigef-brasil":
        # O filtro estadual é gerado internamente, nunca aceito do cliente.
        incoming=[
            (key,value) for key,value in incoming
            if key.lower() != "cql_filter"
        ]
        if requested_uf != "all":
            incoming.append((
                "CQL_FILTER",
                f"uf_id={SIGEF_UF_IBGE[requested_uf]}",
            ))
    query=urlencode(
        [*parse_qsl(parsed.query,keep_blank_values=True),*incoming],
        doseq=True,
    )
    destination=urlunsplit((parsed.scheme,parsed.netloc,parsed.path,query,""))
    context=ssl._create_unverified_context() if metadata.get("allow_insecure_tls") else ssl.create_default_context()
    if metadata.get("allow_legacy_tls"):
        context.set_ciphers("DEFAULT:@SECLEVEL=1")
    upstream=UrlRequest(destination,headers={"User-Agent":"Amazonika-Geoespacial/1.0","Accept":"image/*,application/xml,text/xml,*/*"})
    try:
        opener=build_opener(OfficialOnlyRedirectHandler(),HTTPSHandler(context=context))
        with opener.open(upstream,timeout=45) as result:
            content=result.read(12*1024*1024+1)
            if len(content)>12*1024*1024: raise HTTPException(502,"A resposta WMS ultrapassou o limite de 12 MB.")
            return Response(content=content,media_type=result.headers.get_content_type(),headers={"Cache-Control":"public, max-age=300"})
    except HTTPException: raise
    except (HTTPError,URLError,TimeoutError) as exc:
        raise HTTPException(502,f"O serviço WMS oficial não respondeu: {exc}") from exc

@router.get("/{source_id}/sigef-snap")
def sigef_geonode_snap(
    source_id: UUID,
    bbox: str = Query(min_length=7, max_length=120),
    uf: str = "all",
    limit: int = Query(default=60, ge=1, le=80),
    db: Session = Depends(get_db),
):
    """Geometrias oficiais GeoNode, limitadas para SNAP no OpenLayers."""
    import math

    source = db.get(Source, source_id)
    if not source or not source.is_active:
        raise HTTPException(404, "Fonte SIGEF não encontrada.")
    if source.slug != "incra-sigef-brasil":
        raise HTTPException(404, "Consulta exclusiva do SIGEF Brasil.")

    uf = uf.strip().lower()
    if uf != "all" and uf not in SIGEF_UF_IBGE:
        raise HTTPException(422, "UF inválida.")

    try:
        coords = [float(v.strip()) for v in bbox.split(",")]
    except ValueError as exc:
        raise HTTPException(422, "BBOX inválida.") from exc

    if len(coords) != 4 or not all(math.isfinite(v) for v in coords):
        raise HTTPException(422, "BBOX inválida.")

    west, south, east, north = coords

    if not (
        -75 <= west < east <= -30
        and -35 <= south < north <= 7
        and east - west <= 0.10
        and north - south <= 0.10
    ):
        raise HTTPException(
            422,
            "Aproxime o mapa para carregar o SNAP oficial SIGEF.",
        )

    params = {
        "SERVICE": "WFS",
        "VERSION": "1.1.0",
        "REQUEST": "GetFeature",
        "TYPENAME": "geonode:sigef_geo",
        "OUTPUTFORMAT": "application/json",
        "SRSNAME": "EPSG:4326",
        "BBOX": f"{west},{south},{east},{north},EPSG:4326",
        "MAXFEATURES": str(limit),
    }
    # GeoServer não aceita BBOX e CQL_FILTER simultaneamente.
    # Utilizamos ECQL com CRS explícito para preservar as coordenadas.
    params.pop("BBOX", None)

    spatial_filter = (
        f"BBOX(geometry,{west},{south},{east},{north},'EPSG:4326')"
    )

    if uf != "all":
        params["CQL_FILTER"] = (
            f"{spatial_filter} AND uf_id={SIGEF_UF_IBGE[uf]}"
        )
    else:
        params["CQL_FILTER"] = spatial_filter

    # Não manter uma conexão PostgreSQL ocupada durante a chamada remota.
    db.close()

    destination = SIGEF_GEONODE_WFS + "?" + urlencode(params)

    upstream = UrlRequest(
        destination,
        headers={
            "User-Agent": "Amazonika-Geoespacial/1.0",
            "Accept": "application/json",
        },
    )

    try:
        opener = build_opener(
            OfficialOnlyRedirectHandler(),
            HTTPSHandler(context=ssl.create_default_context()),
        )
        with opener.open(upstream, timeout=20) as response:
            raw = response.read(4 * 1024 * 1024 + 1)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise HTTPException(
            502,
            "O WFS GeoNode não concluiu a consulta.",
        ) from exc

    if len(raw) > 4 * 1024 * 1024:
        raise HTTPException(
            413,
            "Geometrias excessivas para o SNAP nesta região.",
        )

    try:
        payload = json.loads(raw)
    except (ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(
            502,
            "O GeoNode não retornou GeoJSON válido.",
        ) from exc

    if payload.get("type") != "FeatureCollection":
        raise HTTPException(
            502,
            "Resposta WFS incompatível com GeoJSON.",
        )

    features = payload.get("features")
    if not isinstance(features, list):
        raise HTTPException(502, "Resposta GeoNode inválida.")

    # Devolver apenas dados geométricos necessários ao SNAP.
    safe_features = []
    for feature in features[:limit]:
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict):
            continue
        if geometry.get("type") not in ("Polygon", "MultiPolygon"):
            continue
        safe_features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": {},
        })

    return {
        "type": "FeatureCollection",
        "features": safe_features,
        "truncated": len(features) >= limit,
        "source": "GEONODE_SIGEF",
    }


@router.post("/{source_id}/uploads/start",dependencies=[Depends(require_permission("sources.import"))])
async def start_large_upload(source_id:UUID,request:Request,db:Session=Depends(get_db)):
    source=db.get(Source,source_id)
    if not source:
        raise HTTPException(404,"Fonte não encontrada.")

    payload=await request.json()
    filename=Path(str(payload.get("filename") or "")).name
    try:
        file_size=int(payload.get("file_size") or 0)
    except (TypeError,ValueError):
        file_size=0

    if not filename or file_size<=0:
        raise HTTPException(422,"Nome e tamanho do arquivo são obrigatórios.")
    if file_size>MAX_LARGE_UPLOAD_BYTES:
        raise HTTPException(413,"Arquivo ultrapassa o limite de 12 GB.")

    suffix=Path(filename).suffix.lower()
    if suffix not in {".gpkg",".kml",".geojson",".json",".zip"}:
        raise HTTPException(400,"Formato vetorial não aceito.")

    upload_id=uuid4().hex
    folder=_large_upload_root()/upload_id
    folder.mkdir(parents=True,exist_ok=False)
    (folder/"upload.part").touch()

    meta={
        "upload_id":upload_id,
        "source_id":str(source_id),
        "filename":filename,
        "file_size":file_size,
        "received_bytes":0,
        "reference_date":payload.get("reference_date"),
        "layer_name":payload.get("layer_name") or None,
        "status":"UPLOADING",
    }
    _write_large_upload(upload_id,meta)
    return meta

@router.get("/{source_id}/uploads/{upload_id}/status",dependencies=[Depends(require_permission("sources.import"))])
def large_upload_status(source_id:UUID,upload_id:str):
    meta=_read_large_upload(upload_id)
    if meta.get("source_id")!=str(source_id):
        raise HTTPException(404,"Sessão de upload não encontrada para esta fonte.")
    return meta

@router.post("/{source_id}/uploads/{upload_id}/chunk",dependencies=[Depends(require_permission("sources.import"))])
def upload_large_chunk(
    source_id:UUID,
    upload_id:str,
    offset:int=Form(...),
    chunk:UploadFile=File(...),
):
    meta=_read_large_upload(upload_id)

    if meta.get("source_id")!=str(source_id):
        raise HTTPException(404,"Sessão de upload não encontrada para esta fonte.")
    if meta.get("status")!="UPLOADING":
        raise HTTPException(409,"A sessão não está recebendo dados.")

    expected=int(meta.get("received_bytes") or 0)
    if offset!=expected:
        raise HTTPException(409,f"Offset inválido. Esperado: {expected}.")

    part=_large_upload_root()/upload_id/"upload.part"
    written=0

    with part.open("ab") as target:
        while data:=chunk.file.read(1024*1024):
            written+=len(data)
            if written>MAX_CHUNK_BYTES:
                target.truncate(expected)
                raise HTTPException(413,"Chunk ultrapassa 32 MiB.")
            target.write(data)

    received=expected+written
    if received>int(meta["file_size"]):
        with part.open("r+b") as target:
            target.truncate(expected)
        raise HTTPException(422,"Dados recebidos ultrapassam o tamanho declarado.")

    meta["received_bytes"]=received
    _write_large_upload(upload_id,meta)

    return {
        "upload_id":upload_id,
        "received_bytes":received,
        "file_size":meta["file_size"],
        "status":meta["status"],
    }

@router.post("/{source_id}/uploads/{upload_id}/complete",dependencies=[Depends(require_permission("sources.import"))])
def complete_large_upload(source_id:UUID,upload_id:str):
    meta=_read_large_upload(upload_id)

    if meta.get("source_id")!=str(source_id):
        raise HTTPException(404,"Sessão de upload não encontrada para esta fonte.")

    expected=int(meta["file_size"])
    received=int(meta.get("received_bytes") or 0)

    if received!=expected:
        raise HTTPException(
            409,
            f"Upload incompleto: {received} de {expected} bytes recebidos.",
        )

    folder=_large_upload_root()/upload_id
    part=folder/"upload.part"

    if not part.exists() or part.stat().st_size!=expected:
        raise HTTPException(409,"Arquivo parcial não corresponde ao tamanho esperado.")

    root=get_settings().storage_dir
    root.mkdir(parents=True,exist_ok=True)
    destination=root/f"{upload_id}_{meta['filename']}"

    part.replace(destination)

    meta["status"]="QUEUED"
    meta["stored_path"]=str(destination)
    meta["queued_at"]=datetime.now(timezone.utc).isoformat()
    meta["processing_stage"]="Aguardando processamento vetorial"
    meta["processing_code"]="QUEUED"
    meta["progress_percent"]=99
    meta["error"]=None
    meta["error_code"]=None
    meta["error_title"]=None
    meta["error_detail"]=None
    meta["error_retryable"]=False
    _write_large_upload(upload_id,meta)

    return {
        "upload_id":upload_id,
        "filename":meta["filename"],
        "file_size":expected,
        "received_bytes":received,
        "status":"QUEUED",
        "progress_percent":99,
        "processing_stage":"Aguardando processamento vetorial",
    }


@router.post(
    "/{source_id}/uploads/{upload_id}/retry",
    dependencies=[Depends(require_permission("sources.import"))],
)
def retry_large_upload_processing(
    source_id: UUID,
    upload_id: str,
):
    meta = _read_large_upload(upload_id)

    if meta.get("source_id") != str(source_id):
        raise HTTPException(
            404,
            "Sessão de upload não encontrada para esta fonte.",
        )

    stored = Path(str(meta.get("stored_path") or ""))

    if meta.get("status") != "FAILED":
        raise HTTPException(
            409,
            "Somente processamentos com falha podem ser reenviados.",
        )

    if not stored.exists():
        raise HTTPException(
            409,
            "O arquivo original não está mais disponível no servidor.",
        )

    meta.update(
        {
            "status": "QUEUED",
            "queued_at": datetime.now(timezone.utc).isoformat(),
            "processing_stage": "Reprocessamento aguardando worker",
            "processing_code": "QUEUED",
            "progress_percent": 99,
            "error": None,
            "error_code": None,
            "error_title": None,
            "error_detail": None,
            "error_retryable": False,
        }
    )

    _write_large_upload(upload_id, meta)
    return meta


@router.post("/{source_id}/imports/geopackage",response_model=VersionRead,status_code=201,dependencies=[Depends(require_permission("sources.import"))])
def upload_geopackage(source_id:UUID,file:UploadFile=File(...),reference_date:date|None=Form(None),layer_name:str|None=Form(None),db:Session=Depends(get_db)):
    source=db.get(Source,source_id)
    if not source: raise HTTPException(404,"Fonte não encontrada.")
    if not file.filename or not file.filename.lower().endswith(".gpkg"): raise HTTPException(400,"Envie um arquivo GeoPackage (.gpkg).")
    root=get_settings().storage_dir; root.mkdir(parents=True,exist_ok=True)
    destination=root/f"{uuid4()}_{Path(file.filename).name}"
    with destination.open("wb") as target:
        while chunk:=file.file.read(1024*1024): target.write(chunk)
    try: return import_geopackage(db,source,destination,reference_date,layer_name)
    except Exception as exc: raise HTTPException(422,f"Falha ao importar a camada: {exc}") from exc

@router.post("/{source_id}/imports/vector",response_model=VersionRead,status_code=201,dependencies=[Depends(require_permission("sources.import"))])
def upload_vector(source_id:UUID,file:UploadFile=File(...),reference_date:date|None=Form(None),layer_name:str|None=Form(None),db:Session=Depends(get_db)):
    source=db.get(Source,source_id)
    if not source: raise HTTPException(404,"Fonte não encontrada.")
    if not file.filename: raise HTTPException(400,"Selecione um arquivo vetorial.")
    suffix=Path(file.filename).suffix.lower()
    allowed={".gpkg",".kml",".geojson",".json",".zip"}
    if suffix not in allowed: raise HTTPException(400,"Formato não aceito. Use GeoPackage, KML, GeoJSON ou Shapefile compactado em ZIP.")
    root=get_settings().storage_dir; root.mkdir(parents=True,exist_ok=True)
    destination=root/f"{uuid4()}_{Path(file.filename).name}"
    with destination.open("wb") as target:
        while chunk:=file.file.read(1024*1024): target.write(chunk)
    try: return import_vector_file(db,source,destination,reference_date,layer_name,Path(file.filename).name)
    except Exception as exc: raise HTTPException(422,f"Falha ao importar o arquivo vetorial: {exc}") from exc

@router.post("/{source_id}/sync",response_model=VersionRead,status_code=201,dependencies=[Depends(require_permission("sources.manage"))])
def synchronize_source(source_id:UUID,reference_date:date|None=None,db:Session=Depends(get_db)):
    source=db.get(Source,source_id)
    if not source: raise HTTPException(404,"Fonte não encontrada.")
    if source.service_url and "/i3geo/ogc.php" in source.service_url.lower():
        raise HTTPException(400,"O endereço informado pelo Acervo Fundiário é WMS e serve apenas para visualização. Use o acesso assistido ao INCRA e importe o arquivo vetorial para realizar análises.")
    if source.kind.value not in ("WFS","ARCGIS_FEATURE"): raise HTTPException(400,"A fonte não oferece sincronização automática.")
    try: return synchronize_source_data(db,source,reference_date)
    except Exception as exc:
        message=str(exc)
        if "Geometry has Z dimension" in message:
            message="A fonte retornou geometria tridimensional incompatível. Atualize a API e tente novamente."
        elif len(message)>500:
            message=f"{message[:500]}…"
        raise HTTPException(422,f"Falha ao sincronizar a fonte oficial: {message}") from exc
