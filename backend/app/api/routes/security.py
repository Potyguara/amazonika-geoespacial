from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid4
import subprocess

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.models.security import AuthorizedArea
from app.schemas.security import AuthorizedAreaRead, AuthorizedAreaUpdate
from app.services.auth import require_permission


router = APIRouter(
    prefix="/security",
    tags=["Segurança"],
    dependencies=[Depends(require_permission("users.manage"))],
)


@router.get("/authorized-areas", response_model=list[AuthorizedAreaRead])
def list_authorized_areas(db: Session = Depends(get_db)):
    rows = list(
        db.scalars(
            select(AuthorizedArea).order_by(
                AuthorizedArea.is_active.desc(),
                AuthorizedArea.name,
            )
        )
    )

    return [
        {
            "id": str(row.id),
            "name": row.name,
            "description": row.description,
            "original_filename": row.original_filename,
            "is_active": row.is_active,
        }
        for row in rows
    ]


@router.post("/authorized-areas", status_code=201)
def create_authorized_area(
    name: str = Form(...),
    description: str | None = Form(None),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    filename = Path(file.filename or "").name

    if not filename.lower().endswith(".kml"):
        raise HTTPException(422, "Envie um arquivo KML.")

    area_id = uuid4()
    storage = get_settings().storage_dir / "authorized_areas"
    storage.mkdir(parents=True, exist_ok=True)

    source_path = storage / f"{area_id}.kml"
    source_path.write_bytes(file.file.read())

    staging = f"stg_auth_area_{area_id.hex}"

    database_url = get_settings().database_url.replace(
        "postgresql+psycopg://",
        "postgresql://",
    )

    try:
        subprocess.run(
            [
                "ogr2ogr",
                "-f",
                "PostgreSQL",
                f"PG:{database_url}",
                str(source_path),
                "-nln",
                staging,
                "-t_srs",
                "EPSG:4674",
                "-dim",
                "XY",
                "-nlt",
                "PROMOTE_TO_MULTI",
                "-lco",
                "GEOMETRY_NAME=geom",
                "-lco",
                "SPATIAL_INDEX=NONE",
                "-overwrite",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )

        result = db.execute(
            text(
                f"""
                SELECT
                  ST_AsEWKT(
                    ST_Multi(
                      ST_CollectionExtract(
                        ST_MakeValid(
                          ST_UnaryUnion(
                            ST_Collect(geom)
                          )
                        ),
                        3
                      )
                    )
                  ) AS geom_ewkt
                FROM "{staging}"
                WHERE geom IS NOT NULL
                  AND NOT ST_IsEmpty(geom)
                """
            )
        ).scalar_one_or_none()

        if not result:
            raise HTTPException(
                422,
                "O KML não contém polígono válido.",
            )

        db.execute(
            text(
                """
                INSERT INTO authorized_areas (
                  id,
                  name,
                  description,
                  original_filename,
                  is_active,
                  geom
                )
                VALUES (
                  :id,
                  :name,
                  :description,
                  :filename,
                  true,
                  ST_GeomFromEWKT(:geom)
                )
                """
            ),
            {
                "id": area_id,
                "name": name.strip(),
                "description": description,
                "filename": filename,
                "geom": result,
            },
        )

        db.execute(text(f'DROP TABLE IF EXISTS "{staging}"'))
        db.commit()

    except HTTPException:
        db.rollback()
        db.execute(text(f'DROP TABLE IF EXISTS "{staging}"'))
        db.commit()
        raise

    except Exception as exc:
        db.rollback()
        try:
            db.execute(text(f'DROP TABLE IF EXISTS "{staging}"'))
            db.commit()
        except Exception:
            db.rollback()

        raise HTTPException(
            500,
            f"Falha ao processar KML: {str(exc)[:300]}",
        ) from exc

    return {
        "id": str(area_id),
        "name": name.strip(),
        "description": description,
        "original_filename": filename,
        "is_active": True,
    }


@router.patch("/authorized-areas/{area_id}")
def update_authorized_area(
    area_id: UUID,
    payload: AuthorizedAreaUpdate,
    db: Session = Depends(get_db),
):
    area = db.get(AuthorizedArea, area_id)

    if not area:
        raise HTTPException(404, "Área autorizada não encontrada.")

    if payload.name is not None:
        area.name = payload.name.strip()

    if payload.description is not None:
        area.description = payload.description

    if payload.is_active is not None:
        area.is_active = payload.is_active

    db.commit()

    return {
        "id": str(area.id),
        "name": area.name,
        "description": area.description,
        "original_filename": area.original_filename,
        "is_active": area.is_active,
    }
