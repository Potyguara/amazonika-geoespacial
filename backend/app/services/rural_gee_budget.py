"""Admin-controlled fail-closed daily budget for restricted Earth Engine pilot.

This is an internal number of *attempts*, not Google EECU, invoices, or
external billing. Never grant paid access merely by enabling this budget:
the GEE_ENABLED and GEE_INTERNAL_PILOT_ENABLED flags remain necessary.
"""
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import text

from app.db.session import engine

MAX_DAILY_ATTEMPTS = 5
MIN_DAILY_ATTEMPTS = 1


def ensure_tables():
    with engine.begin() as con:
        con.execute(text("""
            CREATE TABLE IF NOT EXISTS rural_gee_budget (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                enabled BOOLEAN NOT NULL DEFAULT FALSE,
                daily_limit INTEGER NOT NULL DEFAULT 5 CHECK (daily_limit BETWEEN 1 AND 5),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        con.execute(text("""
            INSERT INTO rural_gee_budget (id, enabled, daily_limit)
            VALUES (1, FALSE, 5)
            ON CONFLICT (id) DO NOTHING
        """))


def snapshot() -> dict:
    with engine.connect() as con:
        row = con.execute(text("""
            SELECT enabled, daily_limit, updated_at
            FROM rural_gee_budget WHERE id = 1
        """)).mappings().one()
    return {
        "enabled": bool(row["enabled"]),
        "daily_limit": int(row["daily_limit"]),
        "updated_at": row["updated_at"].isoformat(),
        "usage_basis": "internal_attempt_reservations_utc",
        "external_eecu_usage_available": False,
    }


def update(enabled: bool, daily_limit: int) -> dict:
    if not isinstance(daily_limit, int) or not MIN_DAILY_ATTEMPTS <= daily_limit <= MAX_DAILY_ATTEMPTS:
        raise HTTPException(422, "Limite diário de tentativas deve ser de 1 a 5.")
    with engine.begin() as con:
        result = con.execute(text("""
            UPDATE rural_gee_budget
            SET enabled = :enabled, daily_limit = :daily_limit, updated_at = NOW()
            WHERE id = 1
        """), {"enabled": bool(enabled), "daily_limit": daily_limit})
        if result.rowcount != 1:
            raise HTTPException(503, "Orçamento GEE ainda não foi inicializado.")
    return snapshot()
