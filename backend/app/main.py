from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from app.api.router import api_router
from app.core.config import get_settings
from app.db.base import Base
from app.db.session import engine
import app.models

@asynccontextmanager
async def lifespan(_:FastAPI):
    with engine.begin() as connection: connection.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    Base.metadata.create_all(bind=engine)
    # Migração compatível com instalações locais e futuras implantações no VPS.
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS professional_profile_json JSONB NOT NULL DEFAULT '{}'::jsonb"))
        connection.execute(text("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS warnings_json JSONB NOT NULL DEFAULT '[]'::jsonb"))
        connection.execute(text("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS source_status_json JSONB NOT NULL DEFAULT '[]'::jsonb"))
        connection.execute(text("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS subject_json JSONB NOT NULL DEFAULT '{}'::jsonb"))
        connection.execute(text("ALTER TABLE analyses ADD COLUMN IF NOT EXISTS error_message TEXT"))
    yield

settings=get_settings(); app=FastAPI(title=settings.app_name,version="0.1.0",lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    # O painel é aberto pelo IP local do Mac em celulares e outros computadores.
    # Requisições POST/JSON fazem preflight e precisam aceitar explicitamente a LAN.
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|192\.168\.\d{1,3}\.\d{1,3})(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router)
@app.get("/health",tags=["Sistema"])
def health(): return {"status":"ok","service":settings.app_name}

@app.get("/ready",tags=["Sistema"])
def readiness():
    """Readiness real: confirma também a conexão com o PostGIS."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503,detail="PostGIS indisponível") from exc
    return {"status":"ready","service":settings.app_name,"database":"ok"}
