from __future__ import annotations

import hashlib
import os
import subprocess
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import UUID, uuid4

import pyogrio
from sqlalchemy import delete, select, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.catalog import GeoFeature, Source, SourceVersion


ALLOWED_PACKAGE_GROUPS = {
    "ASSENTAMENTOS",
    "SIGEF",
    "SNCI",
}


ProgressCallback = Callable[[dict], None]


def _emit_progress(
    callback: ProgressCallback | None,
    **payload,
) -> None:
    if callback is not None:
        callback(payload)


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        while chunk := stream.read(8 * 1024 * 1024):
            digest.update(chunk)

    return digest.hexdigest()


def _database_ogr_connection() -> tuple[str, dict[str, str]]:
    url = make_url(get_settings().database_url)

    if not url.database:
        raise ValueError("DATABASE_URL não informa o banco PostgreSQL.")

    if not url.username:
        raise ValueError("DATABASE_URL não informa o usuário PostgreSQL.")

    parts = [
        f"dbname='{url.database}'",
        f"user='{url.username}'",
    ]

    if url.host:
        parts.append(f"host='{url.host}'")

    if url.port:
        parts.append(f"port='{url.port}'")

    environment = os.environ.copy()

    if url.password is not None:
        environment["PGPASSWORD"] = url.password

    # A senha não faz parte do argumento do processo.
    return "PG:" + " ".join(parts), environment


def package_sources(
    db: Session,
    group: str,
) -> list[Source]:
    clean_group = group.strip().upper()

    if clean_group not in ALLOWED_PACKAGE_GROUPS:
        raise ValueError(
            "Grupo de pacote inválido. "
            "Use ASSENTAMENTOS, SIGEF ou SNCI."
        )

    rows = list(
        db.scalars(
            select(Source)
            .where(
                Source.is_official.is_(True),
                text(
                    "metadata_json->>'source_group' = :group"
                ),
            )
            .params(group=clean_group)
            .order_by(Source.name)
        )
    )

    if not rows:
        raise ValueError(
            f"Nenhuma fonte configurada para o grupo {clean_group}."
        )

    for source in rows:
        metadata = dict(source.metadata_json or {})

        if not str(metadata.get("source_layer") or "").strip():
            raise ValueError(
                f"A fonte '{source.name}' não possui "
                "source_layer configurada."
            )

        if not str(metadata.get("source_package") or "").strip():
            raise ValueError(
                f"A fonte '{source.name}' não possui "
                "source_package configurado."
            )

    return rows


def inspect_package(
    db: Session,
    group: str,
    path: Path,
) -> dict:
    if not path.exists():
        raise ValueError("Arquivo do pacote não encontrado.")

    if path.suffix.lower() != ".gpkg":
        raise ValueError(
            "Os pacotes compostos devem estar em GeoPackage (.gpkg)."
        )

    sources = package_sources(db, group)

    configured_packages = {
        str(
            (source.metadata_json or {}).get(
                "source_package",
                "",
            )
        ).strip()
        for source in sources
    }

    configured_packages.discard("")

    if len(configured_packages) != 1:
        raise ValueError(
            "As fontes do grupo não apontam para um único pacote."
        )

    expected_package = next(iter(configured_packages))

    available = [
        str(row[0])
        for row in pyogrio.list_layers(path)
    ]

    available_lookup = {
        name.casefold(): name
        for name in available
    }

    mappings = []
    missing = []

    for source in sources:
        metadata = dict(source.metadata_json or {})
        expected_layer = str(
            metadata["source_layer"]
        ).strip()

        actual_layer = available_lookup.get(
            expected_layer.casefold()
        )

        if actual_layer is None:
            missing.append(expected_layer)
            continue

        mappings.append(
            {
                "source_id": source.id,
                "source_name": source.name,
                "expected_layer": expected_layer,
                "actual_layer": actual_layer,
            }
        )

    return {
        "group": group.strip().upper(),
        "expected_package": expected_package,
        "received_package": path.name,
        "available_layers": available,
        "missing_layers": missing,
        "mappings": mappings,
        "valid": not missing,
    }


def _create_processing_version(
    db: Session,
    source: Source,
    reference_date: date,
    checksum: str,
    filename: str,
) -> SourceVersion:
    version = SourceVersion(
        source_id=source.id,
        reference_date=reference_date,
        checksum=checksum,
        original_filename=filename,
        status="PROCESSING",
        is_current=False,
        feature_count=0,
    )

    db.add(version)
    db.commit()
    db.refresh(version)

    return version


def _drop_staging(
    db: Session,
    staging: str,
) -> None:
    db.execute(
        text(
            f'DROP TABLE IF EXISTS "{staging}"'
        )
    )
    db.commit()


def _ogr_to_staging(
    path: Path,
    layer_name: str,
    staging: str,
) -> None:
    pg_connection, environment = _database_ogr_connection()

    command = [
        "ogr2ogr",
        "-f",
        "PostgreSQL",
        pg_connection,
        str(path),
        layer_name,
        "-nln",
        staging,
        "-t_srs",
        "EPSG:4674",
        "-dim",
        "XY",
        "-lco",
        "GEOMETRY_NAME=geom",
        "-lco",
        "SPATIAL_INDEX=NONE",
        "-overwrite",
        "-gt",
        "65536",
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=environment,
    )

    if result.returncode != 0:
        message = (
            result.stderr
            or result.stdout
            or "ogr2ogr retornou erro desconhecido."
        )

        raise ValueError(
            f"Falha GDAL na camada '{layer_name}': "
            f"{message[-2000:]}"
        )


def _staging_columns(
    db: Session,
    staging: str,
) -> set[str]:
    rows = db.execute(
        text(
            """
            SELECT column_name
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = :table_name
            """
        ),
        {
            "table_name": staging,
        },
    ).scalars().all()

    return set(rows)


def _preferred_json_value(
    columns: set[str],
    candidates: tuple[str, ...],
    json_alias: str = "properties",
) -> str:
    expressions = []

    lower_lookup = {
        column.lower(): column
        for column in columns
    }

    for candidate in candidates:
        real = lower_lookup.get(candidate.lower())

        if real:
            escaped = real.replace('"', '""')
            expressions.append(
                f'NULLIF("{escaped}"::text, \'\')'
            )

    if not expressions:
        return "NULL"

    return "COALESCE(" + ", ".join(expressions) + ")"


def _copy_staging_to_features(
    db: Session,
    staging: str,
    version_id: UUID,
    layer_name: str,
) -> int:
    columns = _staging_columns(
        db,
        staging,
    )

    if "geom" not in columns:
        raise ValueError(
            f"A camada '{layer_name}' não gerou coluna geom."
        )

    name_expression = _preferred_json_value(
        columns,
        (
            "nome",
            "name",
            "processo",
            "dsprocesso",
            "nome_uc",
            "nome_proje",
            "nom_pessoa",
            "nm_imovel",
            "denominacao",
            "assentamento",
            "parcela_codigo",
            "codigo",
        ),
    )

    official_id_expression = _preferred_json_value(
        columns,
        (
            "id",
            "fid",
            "objectid",
            "processo",
            "seq_tad",
            "cd_sipra",
            "codigo",
            "parcela_codigo",
            "gid",
        ),
    )

    safe_layer = (
        layer_name
        .replace("\\", "_")
        .replace(":", "_")
    )

    # Importações nacionais podem levar muitos minutos.
    # O timeout é removido somente desta transação de carga,
    # sem alterar o comportamento global do PostgreSQL.
    db.execute(text("SET LOCAL statement_timeout = 0"))

    db.execute(
        text(
            f"""
            WITH prepared AS (
                SELECT
                    s.*,
                    ROW_NUMBER() OVER () AS amazonika_row_number
                FROM "{staging}" s
                WHERE geom IS NOT NULL
                  AND NOT ST_IsEmpty(geom)
            ),
            normalized AS (
                SELECT
                    *,
                    ST_Force2D(
                        CASE
                            WHEN ST_IsValid(geom)
                            THEN geom
                            ELSE ST_MakeValid(geom)
                        END
                    ) AS amazonika_geom
                FROM prepared
            )
            INSERT INTO geo_features (
                id,
                version_id,
                external_id,
                name,
                properties,
                geom
            )
            SELECT
                gen_random_uuid(),
                :version_id,
                LEFT(
                    :layer_prefix
                    || ':'
                    || COALESCE(
                        {official_id_expression},
                        amazonika_row_number::text
                    )
                    || ':'
                    || amazonika_row_number::text,
                    255
                ),
                LEFT(
                    {name_expression},
                    500
                ),
                (
                    to_jsonb(normalized)
                    - 'geom'
                    - 'amazonika_geom'
                    - 'amazonika_row_number'
                )::json,
                amazonika_geom
            FROM normalized
            WHERE amazonika_geom IS NOT NULL
              AND NOT ST_IsEmpty(amazonika_geom)
            """
        ),
        {
            "version_id": version_id,
            "layer_prefix": safe_layer,
        },
    )

    db.commit()

    total = db.scalar(
        text(
            """
            SELECT COUNT(*)
            FROM geo_features
            WHERE version_id = :version_id
            """
        ),
        {
            "version_id": version_id,
        },
    )

    return int(total or 0)


def import_package(
    db: Session,
    group: str,
    path: Path,
    reference_date: date,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    inspection = inspect_package(
        db,
        group,
        path,
    )

    if not inspection["valid"]:
        missing = ", ".join(
            inspection["missing_layers"]
        )

        raise ValueError(
            "O pacote não contém todas as camadas esperadas. "
            f"Faltando: {missing}."
        )

    sources = {
        source.id: source
        for source in package_sources(
            db,
            group,
        )
    }

    _emit_progress(
        progress_callback,
        processing_code="CHECKSUM",
        processing_stage="Calculando integridade do GeoPackage",
        progress_percent=5,
        total_layers=len(inspection["mappings"]),
    )

    checksum = _checksum(path)

    created_versions: list[SourceVersion] = []
    results = []
    staging_tables: list[str] = []

    try:
        total_layers = len(inspection["mappings"])
        completed_layers: list[dict] = []

        for layer_index, mapping in enumerate(
            inspection["mappings"],
            start=1,
        ):
            source = sources[
                mapping["source_id"]
            ]

            layer_name = mapping[
                "actual_layer"
            ]

            layer_span = 80 / max(total_layers, 1)
            layer_base = 8 + ((layer_index - 1) * layer_span)

            try:
                layer_info = pyogrio.read_info(
                    path,
                    layer=layer_name,
                )
                layer_total_features = int(
                    layer_info.get("features") or 0
                )
            except Exception:
                layer_total_features = 0

            _emit_progress(
                progress_callback,
                processing_code="PREPARING_LAYER",
                processing_stage=f"Preparando {source.name}",
                progress_percent=round(layer_base),
                current_layer=layer_name,
                current_source=source.name,
                current_layer_index=layer_index,
                total_layers=total_layers,
                current_layer_total_features=layer_total_features,
                completed_layers=completed_layers,
            )

            version = _create_processing_version(
                db,
                source,
                reference_date,
                checksum,
                path.name,
            )

            created_versions.append(version)

            staging = (
                "stg_pkg_"
                + uuid4().hex
            )

            staging_tables.append(staging)

            _emit_progress(
                progress_callback,
                processing_code="STAGING",
                processing_stage=f"Carregando {source.name} no staging",
                progress_percent=round(layer_base + layer_span * 0.20),
                current_layer=layer_name,
                current_source=source.name,
                current_layer_index=layer_index,
                total_layers=total_layers,
                current_layer_total_features=layer_total_features,
                completed_layers=completed_layers,
            )

            _ogr_to_staging(
                path,
                layer_name,
                staging,
            )

            _emit_progress(
                progress_callback,
                processing_code="NORMALIZING",
                processing_stage=f"Normalizando e gravando {source.name}",
                progress_percent=round(layer_base + layer_span * 0.45),
                current_layer=layer_name,
                current_source=source.name,
                current_layer_index=layer_index,
                total_layers=total_layers,
                current_layer_total_features=layer_total_features,
                completed_layers=completed_layers,
            )

            feature_count = (
                _copy_staging_to_features(
                    db,
                    staging,
                    version.id,
                    layer_name,
                )
            )

            if feature_count <= 0:
                raise ValueError(
                    f"A camada '{layer_name}' não possui "
                    "feições vetoriais válidas."
                )

            _drop_staging(
                db,
                staging,
            )

            staging_tables.remove(staging)

            version.feature_count = feature_count

            result_item = {
                "source_id": str(source.id),
                "source_name": source.name,
                "layer_name": layer_name,
                "version_id": str(version.id),
                "feature_count": feature_count,
            }

            results.append(result_item)
            completed_layers.append(result_item)

            _emit_progress(
                progress_callback,
                processing_code="LAYER_COMPLETE",
                processing_stage=f"{source.name} concluído",
                progress_percent=round(layer_base + layer_span),
                current_layer=layer_name,
                current_source=source.name,
                current_layer_index=layer_index,
                total_layers=total_layers,
                current_layer_total_features=feature_count,
                completed_layers=completed_layers,
            )

        _emit_progress(
            progress_callback,
            processing_code="ACTIVATING",
            processing_stage="Ativando novas versões",
            progress_percent=90,
            total_layers=total_layers,
            completed_layers=completed_layers,
        )

        # -------------------------------------------------
        # ATIVAÇÃO ATÔMICA DO GRUPO
        # -------------------------------------------------

        for version in created_versions:
            db.execute(
                update(SourceVersion)
                .where(
                    SourceVersion.source_id
                    == version.source_id
                )
                .values(
                    is_current=False
                )
            )

        for version in created_versions:
            version.status = "READY"
            version.is_current = True
            version.imported_at = datetime.now(
                timezone.utc
            )
            version.error_message = None

            source = sources[
                version.source_id
            ]

            source.is_active = True

        db.commit()

        _emit_progress(
            progress_callback,
            processing_code="CLEANUP",
            processing_stage="Removendo geometrias de versões anteriores",
            progress_percent=95,
            total_layers=total_layers,
            completed_layers=completed_layers,
        )

        # -------------------------------------------------
        # RETENÇÃO
        # Conserva somente as geometrias das versões atuais.
        # O registro histórico de SourceVersion permanece.
        # -------------------------------------------------

        for version in created_versions:
            old_version_ids = (
                select(SourceVersion.id)
                .where(
                    SourceVersion.source_id == version.source_id,
                    SourceVersion.id != version.id,
                    SourceVersion.is_current.is_(False),
                )
            )

            db.execute(
                delete(GeoFeature).where(
                    GeoFeature.version_id.in_(old_version_ids)
                )
            )

        db.commit()

        return {
            **inspection,
            "checksum": checksum,
            "reference_date": reference_date.isoformat(),
            "status": "READY",
            "results": results,
        }

    except Exception as exc:
        db.rollback()

        for staging in staging_tables:
            try:
                _drop_staging(
                    db,
                    staging,
                )
            except Exception:
                db.rollback()

        # Remove feições que possam ter sido gravadas por uma
        # tentativa parcial antes de marcar a versão como FAILED.
        if created_versions:
            db.execute(
                delete(GeoFeature).where(
                    GeoFeature.version_id.in_(
                        [version.id for version in created_versions]
                    )
                )
            )
            db.commit()

        # Nenhuma versão parcial pode virar current.
        for version in created_versions:
            persisted = db.get(
                SourceVersion,
                version.id,
            )

            if persisted:
                persisted.status = "FAILED"
                persisted.is_current = False
                persisted.error_message = str(
                    exc
                )[:2000]

        db.commit()

        raise
