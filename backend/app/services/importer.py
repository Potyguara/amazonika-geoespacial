import hashlib
import shutil
import subprocess
import tempfile
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request,urlopen
import json
import geopandas as gpd
import pyogrio
from shapely import force_2d
from shapely.ops import transform as shapely_transform
from geoalchemy2.shape import from_shape
from sqlalchemy import insert, update
from sqlalchemy.orm import Session
from app.models.catalog import GeoFeature, Source, SourceVersion

def sync_incra_wfs_bbox(db:Session,source:Source,uf:str,bounds:tuple[float,float,float,float],cache_key:str)->SourceVersion:
    metadata=dict(source.metadata_json or {})
    theme=str(metadata.get("wms_theme") or "").strip()
    available=set(metadata.get("wms_available_ufs") or [])
    uf=uf.lower()
    if not theme or uf not in available: raise ValueError(f"Camada não publicada pelo INCRA para {uf.upper()}.")
    marker=f"INCRA_WFS:{theme}_{uf}:{cache_key}"
    cached=db.query(SourceVersion).filter(SourceVersion.source_id==source.id,SourceVersion.original_filename==marker,SourceVersion.status=="READY").order_by(SourceVersion.imported_at.desc()).first()
    if cached: return cached
    minx,miny,maxx,maxy=bounds
    # O WFS 1.1 do i3Geo usa a ordem de eixos oficial do EPSG:4326 (latitude/longitude).
    bbox=f"{miny},{minx},{maxy},{maxx},EPSG:4326"
    layer=f"{theme}_{uf}"
    url=f"http://acervofundiario.incra.gov.br/i3geo/ogc.php?tema={layer}"
    params=urlencode({"SERVICE":"WFS","VERSION":"1.1.0","REQUEST":"GetFeature","TYPENAME":layer,"SRSNAME":"EPSG:4326","BBOX":bbox,"MAXFEATURES":"50000"})
    version=_create_version(db,source,date.today(),checksum=cache_key,original_filename=marker)
    try:
        request=Request(f"{url}&{params}",headers={"User-Agent":"Mozilla/5.0 Amazonika-Geoespacial/1.0","Accept":"text/xml,application/gml+xml,*/*"})
        with tempfile.TemporaryDirectory(prefix="amazonika_incra_wfs_") as temporary:
            destination=Path(temporary)/"features.gml"
            total=0
            with urlopen(request,timeout=300) as response,destination.open("wb") as target:
                while chunk:=response.read(1024*1024):
                    total+=len(chunk)
                    if total>250*1024*1024: raise ValueError("A consulta retornou mais de 250 MB. Reduza a área analisada.")
                    target.write(chunk)
            frame=gpd.read_file(destination)

            # O WFS 1.1 do i3Geo entrega as coordenadas GML em ordem
            # latitude/longitude. Normalizamos para X=longitude, Y=latitude.
            frame.geometry=frame.geometry.map(
                lambda geom: shapely_transform(
                    lambda x,y,z=None: (y,x) if z is None else (y,x,z),
                    geom,
                )
            )
            frame=frame.set_crs("EPSG:4326",allow_override=True).to_crs(4674)

            return _persist_frame(
                db,
                source,
                version,
                frame,
                activate=False,
            )
    except Exception as exc:
        db.rollback(); failed=db.get(SourceVersion,version.id)
        if failed: failed.status="FAILED"; failed.error_message=str(exc)[:2000]; db.commit()
        raise

def sync_sicar_wfs_bbox(db:Session,source:Source,uf:str,bounds:tuple[float,float,float,float],cache_key:str)->SourceVersion:
    """Materializa somente os imóveis CAR que podem tocar a geometria analisada."""
    uf=uf.lower()
    if len(uf)!=2: raise ValueError("UF inválida para a consulta ao SICAR.")
    layer=f"sicar:sicar_imoveis_{'DF' if uf == 'df' else uf}"
    marker=f"SICAR_WFS:{layer}:{cache_key}"
    cached=db.query(SourceVersion).filter(SourceVersion.source_id==source.id,SourceVersion.original_filename==marker,SourceVersion.status=="READY").order_by(SourceVersion.imported_at.desc()).first()
    if cached: return cached
    minx,miny,maxx,maxy=bounds
    params=urlencode({"SERVICE":"WFS","VERSION":"2.0.0","REQUEST":"GetFeature","TYPENAMES":layer,"SRSNAME":"EPSG:4674","BBOX":f"{minx},{miny},{maxx},{maxy},EPSG:4674","OUTPUTFORMAT":"application/json","COUNT":"50000"})
    endpoint=str(source.service_url or "https://geoserver.car.gov.br/geoserver/sicar/ows")
    version=_create_version(db,source,date.today(),checksum=cache_key,original_filename=marker)
    try:
        with tempfile.TemporaryDirectory(prefix="amazonika_sicar_wfs_") as temporary:
            destination=Path(temporary)/"features.geojson"
            subprocess.run([
                "curl","--fail","--location","--silent","--show-error",
                "--connect-timeout","30","--max-time","300","--max-filesize",str(250*1024*1024),
                "--output",str(destination),f"{endpoint}?{params}",
            ],check=True)
            if destination.stat().st_size < 4096:
                payload=json.loads(destination.read_text(encoding="utf-8"))
                if not payload.get("features"):
                    return _mark_empty_version(db,source,version,activate=False)
            frame=gpd.read_file(destination,engine="pyogrio")
            return _persist_frame(db,source,version,frame,activate=False)
    except Exception as exc:
        db.rollback(); failed=db.get(SourceVersion,version.id)
        if failed: failed.status="FAILED"; failed.error_message=str(exc)[:2000]; db.commit()
        raise

def sync_arcgis_bbox(db:Session,source:Source,bounds:tuple[float,float,float,float],cache_key:str)->SourceVersion:
    """Materializa candidatos de um ArcGIS REST apenas no envelope solicitado.

    A consulta por BBOX reduz tráfego e armazenamento. A interseção exata com a
    geometria do usuário continua sendo feita pelo PostGIS após a materialização.
    """
    if not source.service_url or source.layer_name is None:
        raise ValueError("A fonte ArcGIS precisa de URL e identificador da camada.")
    metadata=dict(source.metadata_json or {})
    marker=f"ARCGIS_BBOX:{source.layer_name}:{cache_key}"
    cached=db.query(SourceVersion).filter(
        SourceVersion.source_id==source.id,
        SourceVersion.original_filename==marker,
        SourceVersion.status=="READY",
    ).order_by(SourceVersion.imported_at.desc()).first()
    if cached: return cached
    minx,miny,maxx,maxy=bounds
    layer_url=f"{source.service_url.rstrip('/')}/{source.layer_name}"
    version=_create_version(db,source,date.today(),checksum=cache_key,original_filename=marker)
    try:
        headers={"User-Agent":"Mozilla/5.0 Amazonika-Geoespacial/1.0","Referer":"https://geo.anm.gov.br/","Accept":"application/geo+json,application/json"}
        spatial={"where":str(metadata.get("arcgis_where") or "1=1"),"geometry":f"{minx},{miny},{maxx},{maxy}","geometryType":"esriGeometryEnvelope","inSR":"4674","spatialRel":"esriSpatialRelIntersects"}
        id_request=Request(f"{layer_url}/query",data=urlencode({**spatial,"returnIdsOnly":"true","f":"json"}).encode(),headers=headers,method="POST")
        with urlopen(id_request,timeout=180) as response: id_payload=json.load(response)
        if "error" in id_payload: raise ValueError(id_payload["error"].get("message","O serviço ArcGIS retornou um erro."))
        object_ids=list(id_payload.get("objectIds") or [])
        if not object_ids: return _mark_empty_version(db,source,version,activate=False)
        if len(object_ids)>50000: raise ValueError("A consulta ArcGIS ultrapassou 50.000 feições. Reduza a área analisada.")
        frames=[]
        for start in range(0,len(object_ids),1000):
            data=urlencode({"objectIds":",".join(str(value) for value in object_ids[start:start+1000]),"outFields":"*","returnGeometry":"true","outSR":"4674","f":"geojson"}).encode()
            request=Request(f"{layer_url}/query",data=data,headers=headers,method="POST")
            with urlopen(request,timeout=180) as response: payload=json.load(response)
            if "error" in payload: raise ValueError(payload["error"].get("message","O serviço ArcGIS retornou um erro."))
            features=payload.get("features",[])
            if features: frames.append(gpd.GeoDataFrame.from_features(features,crs="EPSG:4674"))
        return _persist_frames(db,source,version,frames,activate=False)
    except Exception as exc:
        db.rollback(); failed=db.get(SourceVersion,version.id)
        if failed: failed.status="FAILED"; failed.error_message=str(exc)[:2000]; db.commit()
        raise

def _safe_value(value):
    if value is None: return None
    if hasattr(value,"item"):
        try: return value.item()
        except Exception: pass
    if hasattr(value,"isoformat"): return value.isoformat()
    if isinstance(value,float) and value != value: return None
    return value

def _file_checksum(path:Path)->str:
    digest=hashlib.sha256()
    with path.open("rb") as stream:
        while chunk:=stream.read(1024*1024): digest.update(chunk)
    return digest.hexdigest()

def _create_version(db:Session, source:Source, reference_date:date|None, checksum:str|None=None, original_filename:str|None=None)->SourceVersion:
    version=SourceVersion(source_id=source.id,reference_date=reference_date,checksum=checksum,original_filename=original_filename,status="PROCESSING")
    db.add(version); db.commit(); db.refresh(version)
    return version

def _mark_empty_version(db:Session,source:Source,version:SourceVersion,activate:bool=True)->SourceVersion:
    if activate:
        db.execute(update(SourceVersion).where(SourceVersion.source_id==source.id).values(is_current=False))
    version.feature_count=0
    version.status="READY"
    version.is_current=activate
    version.imported_at=datetime.now(timezone.utc)
    db.commit()
    db.refresh(version)
    return version

def _persist_frames(db:Session, source:Source, version:SourceVersion, frames, activate:bool=True)->SourceVersion:
    batch=[]
    total=0
    seen_external_ids=set()
    for frame in frames:
        if frame.empty: continue
        if frame.crs is None: raise ValueError("A camada não possui sistema de referência definido.")
        frame=frame.to_crs(4674)
        name_fields=[column for column in ("nome","NOME","name","PROCESSO","DSProcesso","nome_uc","nome_proje","nom_pessoa","nm_imovel","denominacao","assentamento","parcela_codigo","codigo") if column in frame.columns]
        id_fields=[column for column in ("id","ID","fid","FID","objectid","OBJECTID","PROCESSO","seq_tad","cd_sipra","codigo","parcela_codigo","gid") if column in frame.columns]
        for idx,row in frame.iterrows():
            if row.geometry is None or row.geometry.is_empty: continue
            geometry=force_2d(row.geometry)
            geometry=geometry if geometry.is_valid else geometry.buffer(0)
            if geometry is None or geometry.is_empty: continue
            props={key:_safe_value(value) for key,value in row.items() if key!="geometry"}
            raw_ext=props.get(id_fields[0]) if id_fields else None
            if raw_ext is None or str(raw_ext).strip().lower() in ("", "none", "nan"):
                base_ext=f"amazonika-{total}-{idx}"
            else:
                base_ext=str(raw_ext)

            ext=base_ext
            if ext in seen_external_ids:
                ext=f"{base_ext}__amazonika_{total}_{idx}"

            seen_external_ids.add(ext)
            if props.get("amazonika_camada_origem"):
                ext=f"{props['amazonika_camada_origem']}:{ext}"
            feature_name=str(props.get(name_fields[0])) if name_fields and props.get(name_fields[0]) is not None else None
            batch.append({"version_id":version.id,"external_id":ext,"name":feature_name,"properties":props,"geom":from_shape(geometry,srid=4674)})
            total+=1
            if len(batch)>=1000:
                db.execute(insert(GeoFeature),batch); batch.clear()
    if batch: db.execute(insert(GeoFeature),batch)
    if total==0: raise ValueError("A fonte não retornou nenhuma feição válida.")
    if activate:
        db.execute(update(SourceVersion).where(SourceVersion.source_id==source.id).values(is_current=False))
    version.feature_count=total
    version.status="READY"
    version.is_current=activate
    version.imported_at=datetime.now(timezone.utc)
    db.commit()
    db.refresh(version)
    return version

def _persist_frame(db:Session, source:Source, version:SourceVersion, frame:gpd.GeoDataFrame, activate:bool=True)->SourceVersion:
    return _persist_frames(db,source,version,[frame],activate=activate)

def import_geopackage(db:Session, source:Source, path:Path, reference_date:date|None, layer_name:str|None=None)->SourceVersion:
    checksum=_file_checksum(path)
    version=_create_version(db,source,reference_date,checksum,path.name)
    try:
        available=pyogrio.list_layers(path)
        selected=layer_name or source.layer_name or str(available[0][0])
        frame=gpd.read_file(path,layer=selected)
        return _persist_frame(db,source,version,frame)
    except Exception as exc:
        db.rollback(); failed=db.get(SourceVersion,version.id)
        if failed:
            failed.status="FAILED"; failed.error_message=str(exc); db.commit()
        raise

def import_vector_file(db:Session, source:Source, path:Path, reference_date:date|None, layer_name:str|None=None, original_filename:str|None=None)->SourceVersion:
    checksum=_file_checksum(path)
    version=_create_version(db,source,reference_date or date.today(),checksum,original_filename or path.name)
    try:
        suffix=path.suffix.lower()
        selected=layer_name
        if suffix==".zip":
            with tempfile.TemporaryDirectory(prefix="amazonika_shapefile_") as temporary:
                root=Path(temporary).resolve()
                with zipfile.ZipFile(path) as archive:
                    for member in archive.infolist():
                        target=(root/member.filename).resolve()
                        if target!=root and root not in target.parents:
                            raise ValueError("O ZIP contém um caminho de arquivo inválido.")
                    archive.extractall(root)
                shapefiles=[
                    item for item in root.rglob("*")
                    if item.is_file() and item.suffix.lower()==".shp"
                    and "__MACOSX" not in item.parts and not item.name.startswith("._")
                ]
                if not shapefiles: raise ValueError("O ZIP não contém um Shapefile (.shp).")
                if selected:
                    normalized=Path(selected).stem.lower()
                    matches=[item for item in shapefiles if item.stem.lower()==normalized]
                    if not matches: raise ValueError(f"A camada '{selected}' não foi encontrada no ZIP.")
                    shapefile=matches[0]
                elif len(shapefiles)==1: shapefile=shapefiles[0]
                else:
                    names=", ".join(sorted(item.stem for item in shapefiles))
                    raise ValueError(f"O ZIP contém várias camadas ({names}). Informe a camada interna desejada.")
                siblings={item.suffix.lower() for item in shapefile.parent.iterdir() if item.is_file() and item.stem.lower()==shapefile.stem.lower()}
                missing=[extension for extension in (".dbf",".shx") if extension not in siblings]
                if missing: raise ValueError(f"Shapefile incompleto: faltando {', '.join(missing)}.")
                frame=gpd.read_file(shapefile)
                return _persist_frame(db,source,version,frame)
        if suffix==".gpkg":
            available=pyogrio.list_layers(path)
            if not len(available): raise ValueError("O arquivo não contém nenhuma camada vetorial.")
            selected=selected or str(available[0][0])
        frame=gpd.read_file(path,layer=selected) if selected else gpd.read_file(path)
        return _persist_frame(db,source,version,frame)
    except Exception as exc:
        db.rollback(); failed=db.get(SourceVersion,version.id)
        if failed:
            failed.status="FAILED"; failed.error_message=str(exc); db.commit()
        raise

def _wfs_frame(source:Source,layer_name:str,metadata:dict):
    version_name=str(metadata.get("wfs_version") or "1.0.0")
    type_key="typeNames" if version_name.startswith("2") else "typeName"
    params=urlencode({"service":"WFS","version":version_name,"request":"GetFeature",type_key:layer_name,"outputFormat":"application/json","srsName":"EPSG:4674"})
    separator="&" if "?" in source.service_url else "?"
    request=Request(f"{source.service_url}{separator}{params}",headers={"User-Agent":"Mozilla/5.0 Amazonika-Geoespacial/1.0","Accept":"application/geo+json,application/json,*/*"})
    with tempfile.TemporaryDirectory(prefix="amazonika_wfs_") as temporary:
        destination=Path(temporary)/"features.geojson"
        with urlopen(request,timeout=300) as response,destination.open("wb") as target:
            shutil.copyfileobj(response,target,1024*1024)
        return gpd.read_file(destination)

def sync_wfs(db:Session, source:Source, reference_date:date|None=None)->SourceVersion:
    if not source.service_url or not source.layer_name: raise ValueError("A fonte WFS precisa de URL e nome da camada.")
    version=_create_version(db,source,reference_date or date.today(),original_filename=f"WFS:{source.layer_name}")
    try:
        metadata=dict(source.metadata_json or {})
        layers=list(metadata.get("wfs_layers") or [source.layer_name])
        frames=[]
        for layer in layers:
            frame=_wfs_frame(source,str(layer),metadata)
            frame["amazonika_camada_origem"]=str(layer)
            frames.append(frame)
        return _persist_frames(db,source,version,frames)
    except Exception as exc:
        db.rollback(); failed=db.get(SourceVersion,version.id)
        if failed:
            failed.status="FAILED"; failed.error_message=str(exc); db.commit()
        raise

def _arcgis_frames(source:Source):
    if not source.service_url or source.layer_name is None: raise ValueError("A fonte ArcGIS precisa de URL e identificador da camada.")
    layer_url=f"{source.service_url.rstrip('/')}/{source.layer_name}"
    metadata_request=Request(f"{layer_url}?f=json",headers={"User-Agent":"Amazonika-Geoespacial/1.0","Accept":"application/json"})
    with urlopen(metadata_request,timeout=60) as response:
        metadata=json.load(response)
    if "error" in metadata: raise ValueError(metadata["error"].get("message","Não foi possível consultar os metadados ArcGIS."))
    object_id_field=metadata.get("objectIdField") or metadata.get("objectIdFieldName")
    base=f"{layer_url}/query"
    page_size=2000
    offset=0
    while True:
        query={"where":"1=1","outFields":"*","returnGeometry":"true","outSR":"4674","f":"geojson","resultOffset":offset,"resultRecordCount":page_size}
        if object_id_field: query["orderByFields"]=object_id_field
        params=urlencode(query)
        request=Request(f"{base}?{params}",headers={"User-Agent":"Amazonika-Geoespacial/1.0","Accept":"application/geo+json,application/json"})
        with urlopen(request,timeout=180) as response:
            payload=json.load(response)
        if "error" in payload: raise ValueError(payload["error"].get("message","O serviço ArcGIS retornou um erro."))
        features=payload.get("features",[])
        if not features: break
        yield gpd.GeoDataFrame.from_features(features,crs="EPSG:4674")
        offset+=len(features)
        if len(features)<page_size and not payload.get("exceededTransferLimit",False): break

def sync_arcgis_feature(db:Session, source:Source, reference_date:date|None=None)->SourceVersion:
    if not source.service_url or source.layer_name is None: raise ValueError("A fonte ArcGIS precisa de URL e identificador da camada.")
    version=_create_version(db,source,reference_date or date.today(),original_filename=f"ARCGIS:{source.layer_name}")
    try:
        return _persist_frames(db,source,version,_arcgis_frames(source))
    except Exception as exc:
        db.rollback(); failed=db.get(SourceVersion,version.id)
        if failed:
            failed.status="FAILED"; failed.error_message=str(exc); db.commit()
        raise

def synchronize_source_data(db:Session, source:Source, reference_date:date|None=None)->SourceVersion:
    if source.kind.value=="WFS": return sync_wfs(db,source,reference_date)
    if source.kind.value=="ARCGIS_FEATURE": return sync_arcgis_feature(db,source,reference_date)
    raise ValueError("A sincronização automática está disponível para fontes WFS e ArcGIS FeatureServer.")
