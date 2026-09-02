from uuid import UUID
import hashlib
import json
from geoalchemy2 import Geography
from geoalchemy2.shape import from_shape
from shapely import force_2d
from shapely.geometry import shape
from sqlalchemy import cast,func,select,text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from app.models.analysis import Analysis, AnalysisResult
from app.models.catalog import GeoFeature, Source, SourceVersion
from app.services.importer import sync_arcgis_bbox,sync_incra_wfs_bbox,sync_sicar_wfs_bbox
from app.db.session import SessionLocal

def _geography(geometry):
    """Converte a geometria SIRGAS 2000 para geography WGS 84 com SRID explícito."""
    return cast(func.ST_Transform(geometry,4326),Geography(geometry_type="GEOMETRY",srid=4326))

def _analysis_subject(geometry:dict):
    subject=force_2d(shape(geometry))
    if subject.geom_type not in {"Point","Polygon","MultiPolygon"}: raise ValueError("Use uma geometria Point, Polygon ou MultiPolygon.")
    if not subject.is_valid: subject=subject.buffer(0)
    if subject.is_empty: raise ValueError("A geometria informada está vazia ou não pôde ser corrigida.")
    return subject

def _nearest_distance(db:Session,version_id:UUID,db_geom)->float|None:
    """Calcula a distância exata sem transformar/varrer a versão inteira.

    O operador KNN <-> usa o índice GiST para eleger uma única candidata. Só
    essa geometria é convertida para geography no cálculo métrico final.
    """
    nearest_id=db.scalar(
        select(GeoFeature.id)
        .where(GeoFeature.version_id==version_id)
        .order_by(GeoFeature.geom.op("<->")(db_geom))
        .limit(1)
    )
    if nearest_id is None:
        return None
    distance=db.scalar(
        select(func.ST_Distance(_geography(GeoFeature.geom),_geography(db_geom)))
        .where(GeoFeature.id==nearest_id)
    )
    return float(distance) if distance is not None else None

def prepare_analysis(
    db: Session,
    name: str,
    geometry: dict,
    created_by_user_id: UUID | None = None,
) -> Analysis:
    subject=_analysis_subject(geometry)
    db_geom=from_shape(subject,srid=4674)
    area_ha=None if subject.geom_type=="Point" else db.scalar(select(func.ST_Area(_geography(db_geom))/10000.0))
    analysis=Analysis(
        name=name,
        geometry_kind=subject.geom_type.upper(),
        input_geom=db_geom,
        area_hectares=area_ha,
        status="QUEUED",
        warnings_json=[],
        source_status_json=[],
        created_by_user_id=created_by_user_id,
    )
    db.add(analysis); db.commit(); db.refresh(analysis)
    return analysis

def run_analysis(db:Session,name:str,geometry:dict,source_ids:list[UUID]|None=None,incra_uf:str|None=None,analysis_id:UUID|None=None):
    subject=_analysis_subject(geometry)
    db_geom=from_shape(subject,srid=4674)
    area_ha=None if subject.geom_type=="Point" else db.scalar(select(func.ST_Area(_geography(db_geom))/10000.0))
    analysis=db.get(Analysis,analysis_id) if analysis_id else None
    if analysis is None:
        analysis=Analysis(name=name,geometry_kind=subject.geom_type.upper(),input_geom=db_geom,area_hectares=area_ha,status="PROCESSING",warnings_json=[],source_status_json=[])
        db.add(analysis); db.flush()
    else:
        analysis.status="PROCESSING"; analysis.error_message=None; db.commit()
    selected_sources=select(Source).where(Source.is_active.is_(True))
    # None preserva o comportamento da API (todas as fontes ativas); uma lista
    # vazia significa que o usuário desativou todas as camadas no gerenciador.
    if source_ids is not None: selected_sources=selected_sources.where(Source.id.in_(source_ids))
    output=[]
    warnings=[]
    source_statuses=[]

    def persist_source_status(item: dict) -> None:
        source_statuses.append(item)
        current = db.get(Analysis, analysis.id)
        current.source_status_json = list(source_statuses)
        db.commit()

    for source in db.scalars(selected_sources).all():
        metadata=dict(source.metadata_json or {})
        version=None
        access_mode="LOCAL_VECTOR"
        if (metadata.get("wfs_on_demand") and incra_uf) or metadata.get("arcgis_on_demand"):
            minx,miny,maxx,maxy=subject.bounds
            pad=0.002 if subject.geom_type=="Point" else 0.0005
            bounds=(minx-pad,miny-pad,maxx+pad,maxy+pad)
            cache_key=hashlib.sha256(json.dumps({"uf":incra_uf.lower() if incra_uf else None,"bounds":[round(v,6) for v in bounds]},sort_keys=True).encode()).hexdigest()[:24]
            try:
                if metadata.get("arcgis_on_demand"):
                    version=sync_arcgis_bbox(db,source,bounds,cache_key)
                    access_mode="ARCGIS_REST_ON_DEMAND"
                elif source.institution=="SICAR":
                    version=sync_sicar_wfs_bbox(db,source,incra_uf,bounds,cache_key)
                    access_mode="SICAR_WFS_ON_DEMAND"
                else:
                    version=sync_incra_wfs_bbox(db,source,incra_uf,bounds,cache_key)
                    access_mode="INCRA_WFS_ON_DEMAND"
            except Exception as exc:
                message = str(exc)[:240]
                warnings.append(f"{source.name}: {message}")
                persist_source_status({
                    "source_id": str(source.id),
                    "source_name": source.name,
                    "institution": source.institution,
                    "status": "FAILED",
                    "message": message,
                    "access_mode": access_mode,
                    "source_version_id": None,
                    "reference_date": None,
                    "intersects": None,
                    "matched_features": None,
                    "overlap_hectares": None,
                    "overlap_percent": None,
                    "nearest_distance_meters": None,
                })
                continue
        if version is None:
            version=db.scalar(select(SourceVersion).where(SourceVersion.source_id==source.id,SourceVersion.is_current.is_(True),SourceVersion.status=="READY"))
        if version is None:
            message = "Base vetorial ainda não disponível."
            warnings.append(f"{source.name}: {message}")
            persist_source_status({
                "source_id": str(source.id),
                "source_name": source.name,
                "institution": source.institution,
                "status": "UNAVAILABLE",
                "message": message,
                "access_mode": access_mode,
                "source_version_id": None,
                "reference_date": None,
                "intersects": None,
                "matched_features": None,
                "overlap_hectares": None,
                "overlap_percent": None,
                "nearest_distance_meters": None,
            })
            continue
        filter_version=GeoFeature.version_id==version.id
        try:
            # Uma fonte oficial indisponível ou excepcionalmente pesada não
            # pode derrubar o PostgreSQL nem impedir as demais fontes. O
            # savepoint recupera a transação se o limite for atingido.
            with db.begin_nested():
                db.execute(text("SET LOCAL statement_timeout = '20s'"))
                intersects=func.ST_Intersects(GeoFeature.geom,db_geom)
                matched=db.scalar(
                    select(func.count()).select_from(GeoFeature)
                    .where(filter_version,intersects)
                ) or 0
                overlap=0.0
                if subject.geom_type!="Point" and matched:
                    overlap=float(db.scalar(
                        select(func.coalesce(func.sum(
                            func.ST_Area(_geography(func.ST_Intersection(GeoFeature.geom,db_geom)))/10000.0
                        ),0)).where(filter_version,intersects)
                    ) or 0)
                nearest=_nearest_distance(db,version.id,db_geom)
        except SQLAlchemyError as exc:
            message = (
                "Cálculo excedeu o limite seguro ou falhou "
                f"({str(exc).splitlines()[0][:160]})."
            )
            warnings.append(f"{source.name}: {message}")
            persist_source_status({
                "source_id": str(source.id),
                "source_name": source.name,
                "institution": source.institution,
                "status": "FAILED",
                "message": message,
                "access_mode": access_mode,
                "source_version_id": str(version.id),
                "reference_date": version.reference_date.isoformat() if version.reference_date else None,
                "intersects": None,
                "matched_features": None,
                "overlap_hectares": None,
                "overlap_percent": None,
                "nearest_distance_meters": None,
            })
            continue
        percent=(overlap/area_ha*100) if area_ha else 0.0
        result=AnalysisResult(analysis_id=analysis.id,source_id=source.id,source_version_id=version.id,intersects=matched>0,matched_features=matched,overlap_hectares=round(overlap,4),overlap_percent=round(percent,4),nearest_distance_meters=round(float(nearest),2) if nearest is not None else None,details={"access_mode":access_mode,"uf":incra_uf.upper() if incra_uf and metadata.get("wfs_on_demand") else None,"calculation":"POSTGIS_VECTOR"})
        db.add(result)

        analyzed_status = {
            "source_id": str(source.id),
            "source_name": source.name,
            "institution": source.institution,
            "status": "ANALYZED",
            "message": None,
            "access_mode": access_mode,
            "source_version_id": str(version.id),
            "reference_date": version.reference_date.isoformat() if version.reference_date else None,
            "intersects": matched > 0,
            "matched_features": int(matched),
            "overlap_hectares": round(overlap, 4),
            "overlap_percent": round(percent, 4),
            "nearest_distance_meters": result.nearest_distance_meters,
        }

        source_statuses.append(analyzed_status)

        # Persiste resultado e estado de execução a cada fonte.
        analysis.source_status_json = list(source_statuses)
        db.commit()

        output.append({"source_id":source.id,"source_name":source.name,"institution":source.institution,"reference_date":version.reference_date.isoformat() if version.reference_date else None,"intersects":matched>0,"matched_features":matched,"overlap_hectares":round(overlap,4),"overlap_percent":round(percent,4),"nearest_distance_meters":result.nearest_distance_meters,"access_mode":access_mode})
    analysis=db.get(Analysis,analysis.id)
    analysis.status="COMPLETED"
    analysis.warnings_json=warnings
    analysis.source_status_json=list(source_statuses)
    analysis.error_message=None
    db.commit()
    db.refresh(analysis)
    return analysis,output,warnings

def run_analysis_background(analysis_id:UUID,name:str,geometry:dict,source_ids:list[UUID]|None,incra_uf:str|None)->None:
    with SessionLocal() as db:
        try:
            run_analysis(db,name,geometry,source_ids,incra_uf,analysis_id)
        except Exception as exc:
            db.rollback()
            analysis=db.get(Analysis,analysis_id)
            if analysis:
                analysis.status="FAILED"
                analysis.error_message=str(exc)[:1000]
                db.commit()
