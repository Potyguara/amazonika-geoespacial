"""Restricted admin-only cartographic PDF pilot with durable usage reservations.

All billable requests must pass a PostgreSQL cross-process advisory mutex and
a committed quota record *before* network work. One attempt per admin/UTC day,
up to five attempts platform-wide per day; failures count, with no auto retry.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from hashlib import sha256
from uuid import UUID

from fastapi import HTTPException
from pyproj import Geod
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from shapely.geometry import shape

from app.core.config import get_settings
from app.db.session import engine
from app.services.rural_gee_budget import snapshot as gee_budget_snapshot
from app.models.rural_mapbiomas_pilot import RuralMapBiomasPilotRun
from app.services.rural_official_car import (
    OfficialCarQueryError, fetch_car_candidate, normalize_car, resolve_car_candidate,
)
from app.services.rural_mapbiomas import (
    MapBiomasError, _initialize_gee, _reduce_class_areas, _normalize_statistics,
    validate_geometry,
)
from app.services.rural_mapbiomas_cartography import fetch_mapbiomas_thematic_thumbnail
from app.services.rural_mapbiomas_pdf import mapbiomas_pdf

MAX_AREA_HA = 1200
MAX_REMOTE_PIXELS = 30000
MAX_PLATFORM_ATTEMPTS_DAY = 5
ADVISORY_KEY = 6704261105
GEOD = Geod(ellps="GRS80")


def verify_pilot_enabled() -> None:
    settings = get_settings()
    if not (settings.gee_internal_pilot_enabled and settings.gee_enabled):
        raise HTTPException(503, "Piloto cartográfico interno desabilitado.")


@contextmanager
def reserve_platform_slot(db: Session, *, user_id: UUID, car_code: str):
    """Global PG session mutex held through the external GEE work.

    Locks and quota decisions are enforced across API worker processes.
    The audit record is committed before the first remote request.
    """
    with engine.connect() as lock_connection:
        acquired = lock_connection.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": ADVISORY_KEY},
        )
        if not acquired:
            raise HTTPException(429, "Já existe processamento cartográfico em andamento.")
        # advisory lock is session scoped, so commit does not release it.
        lock_connection.commit()
        try:
            today = datetime.now(timezone.utc).date()
            existing = db.scalar(select(RuralMapBiomasPilotRun.id).where(
                RuralMapBiomasPilotRun.user_id == user_id,
                RuralMapBiomasPilotRun.quota_day == today,
            ))
            if existing is not None:
                raise HTTPException(429, "Limite: uma tentativa de mapa por administrador a cada dia UTC.")
            budget = gee_budget_snapshot()
            if not budget["enabled"]:
                raise HTTPException(503, "Orçamento interno do Earth Engine desativado pelo administrador.")
            total = db.scalar(select(func.count()).select_from(RuralMapBiomasPilotRun).where(
                RuralMapBiomasPilotRun.quota_day == today,
            )) or 0
            if total >= min(MAX_PLATFORM_ATTEMPTS_DAY, budget["daily_limit"]):
                raise HTTPException(429, "Cota diária de homologação MapBiomas esgotada.")
            record = RuralMapBiomasPilotRun(
                user_id=user_id,
                quota_day=today,
                year=2025,
                subject_hash=sha256(car_code.encode("ascii")).hexdigest(),
                status="RESERVED",
            )
            db.add(record)
            try:
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise HTTPException(429, "A consulta deste administrador já foi reservada hoje.") from exc
            db.refresh(record)
            try:
                yield record
            except BaseException as exc:
                db.rollback()
                record.status = "FAILED"
                record.error_category = type(exc).__name__[:60]
                record.finished_at = datetime.now(timezone.utc)
                db.add(record)
                db.commit()
                raise
        finally:
            lock_connection.execute(
                text("SELECT pg_advisory_unlock(:key)"), {"key": ADVISORY_KEY},
            )
            lock_connection.commit()


def build_restricted_mapbiomas_pdf(*, db: Session, user_id: UUID,
                                   car_code: str) -> bytes:
    verify_pilot_enabled()
    try:
        normalized = normalize_car(car_code)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc

    with reserve_platform_slot(db, user_id=user_id, car_code=normalized) as record:
        try:
            candidate = fetch_car_candidate(normalized)
            if not candidate:
                raise HTTPException(404, "CAR não encontrado na consulta oficial atual.")
            selected = resolve_car_candidate(normalized, candidate["feature_id"])
            geometry = selected["geometry"]
            polygon = validate_geometry(geometry)
            area = abs(GEOD.geometry_area_perimeter(polygon)[0]) / 10000
            if not 0 < area <= MAX_AREA_HA:
                raise HTTPException(
                    422, f"Piloto limitado a imóveis com até {MAX_AREA_HA} hectares.",
                )
            ee = _initialize_gee()
            raw = _reduce_class_areas(
                ee, geometry, 2025, max_pixels=MAX_REMOTE_PIXELS,
            )
            report = _normalize_statistics(raw, 2025, area)
            thumbnail = fetch_mapbiomas_thematic_thumbnail(
                geometry, year=2025,
                class_codes=[item["code"] for item in report["classes"]],
            )
            pdf = mapbiomas_pdf(
                property_name=selected.get("name") or "Imóvel rural",
                cadastral_source=selected.get("source_name") or "SICAR (WFS oficial)",
                cadastral_code=normalized,
                report=report,
                generated_at=datetime.now(timezone.utc),
                thematic_map=thumbnail,
            )
            if len(pdf) > 8 * 1024 * 1024 or not pdf.startswith(b"%PDF"):
                raise ValueError("Relatório cartográfico fora dos limites de exportação.")
        except HTTPException:
            raise
        except ValueError as exc:
            raise HTTPException(422, str(exc)[:180]) from exc
        except (OfficialCarQueryError, MapBiomasError) as exc:
            raise HTTPException(
                503, "Fonte oficial ou serviço Earth Engine indisponível para o diagnóstico.",
            ) from exc
        except Exception as exc:
            raise HTTPException(
                503, "Não foi possível concluir o diagnóstico cartográfico nesta tentativa.",
            ) from exc

        record.status = "COMPLETED"
        record.pdf_bytes = len(pdf)
        record.finished_at = datetime.now(timezone.utc)
        db.add(record)
        db.commit()
        return pdf
