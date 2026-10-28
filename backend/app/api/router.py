from fastapi import APIRouter
from app.api.routes.auth import router as auth_router
from app.api.routes.analyses import router as analyses_router
from app.api.routes.reports import router as reports_router
from app.api.routes.sources import router as sources_router
from app.api.routes.security import router as security_router
from app.api.routes.users import router as users_router
from app.api.routes.tools import router as tools_router
from app.api.routes.technical_pieces import router as technical_pieces_router
from app.api.routes.google_tiles import router as google_tiles_router
from app.api.routes.mapbox_satellite import router as mapbox_satellite_router
api_router=APIRouter(prefix="/api/v1")
api_router.include_router(auth_router); api_router.include_router(security_router); api_router.include_router(users_router); api_router.include_router(sources_router); api_router.include_router(analyses_router); api_router.include_router(reports_router); api_router.include_router(tools_router); api_router.include_router(technical_pieces_router); api_router.include_router(google_tiles_router); api_router.include_router(mapbox_satellite_router)
