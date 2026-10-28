"""Persistent, conservative monthly provider request budgets.

Counts reservations (not invoices). A provider call reserves before execution,
so failures may over-count: intentional fail-closed protection. Period is UTC.
"""
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import text
from app.db.session import engine

PROVIDERS = {"google": 60000, "mapbox": 600000}
MAX_LIMIT = 10000000


def _period():
    return datetime.now(timezone.utc).strftime("%Y-%m")


def ensure_tables():
    with engine.begin() as db:
        db.execute(text("""
          CREATE TABLE IF NOT EXISTS tile_provider_budget (
            provider TEXT PRIMARY KEY,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            monthly_limit BIGINT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
          )
        """))
        db.execute(text("""
          CREATE TABLE IF NOT EXISTS tile_provider_usage (
            provider TEXT NOT NULL,
            period TEXT NOT NULL,
            requests BIGINT NOT NULL DEFAULT 0,
            PRIMARY KEY (provider, period)
          )
        """))
        for provider, limit in PROVIDERS.items():
            db.execute(text("""
              INSERT INTO tile_provider_budget(provider,monthly_limit)
              VALUES (:provider,:lim) ON CONFLICT(provider) DO NOTHING
            """), {"provider": provider, "lim": limit})


def snapshot(provider: str | None = None):
    ensure_tables()
    with engine.connect() as db:
        rows = db.execute(text("""
          SELECT b.provider, b.enabled, b.monthly_limit,
            COALESCE(u.requests,0) AS requests
          FROM tile_provider_budget b
          LEFT JOIN tile_provider_usage u
            ON u.provider=b.provider AND u.period=:period
          ORDER BY b.provider
        """), {"period": _period()}).mappings().all()
    data = [{
        "provider": row["provider"], "enabled": row["enabled"],
        "limit": row["monthly_limit"], "requests": row["requests"],
        "remaining": max(0, row["monthly_limit"]-row["requests"]),
        "blocked": not row["enabled"] or row["requests"] >= row["monthly_limit"],
        "period": _period(), "period_timezone": "UTC"
    } for row in rows]
    return next((item for item in data if item["provider"] == provider), None) if provider else data


def reserve(provider: str):
    """Atomically reserve one upstream request across all workers/instances."""
    if provider not in PROVIDERS:
        raise HTTPException(422, "Provedor inválido")
    ensure_tables()
    period = _period()
    with engine.begin() as db:
        # Row lock serializes simultaneous requests for each provider.
        row = db.execute(text("""
          SELECT enabled, monthly_limit FROM tile_provider_budget
          WHERE provider=:provider FOR UPDATE
        """), {"provider": provider}).mappings().one()
        if not row["enabled"]:
            raise HTTPException(503, "Serviço desativado pelo administrador.")
        usage = db.execute(text("""
          SELECT requests FROM tile_provider_usage
          WHERE provider=:provider AND period=:period
        """), {"provider": provider, "period": period}).scalar_one_or_none() or 0
        if usage >= row["monthly_limit"]:
            raise HTTPException(429, f"Limite mensal interno de {provider} atingido.")
        db.execute(text("""
          INSERT INTO tile_provider_usage(provider,period,requests)
          VALUES (:provider,:period,1)
          ON CONFLICT(provider,period)
          DO UPDATE SET requests=tile_provider_usage.requests+1
        """), {"provider": provider, "period": period})


def update(provider: str, enabled: bool, limit: int):
    if provider not in PROVIDERS or not 1 <= limit <= MAX_LIMIT:
        raise HTTPException(422, "Provedor ou limite inválido.")
    ensure_tables()
    with engine.begin() as db:
        db.execute(text("""
          UPDATE tile_provider_budget
          SET enabled=:enabled, monthly_limit=:lim, updated_at=now()
          WHERE provider=:provider
        """), {"provider": provider, "enabled": enabled, "lim": limit})
    return snapshot(provider)
