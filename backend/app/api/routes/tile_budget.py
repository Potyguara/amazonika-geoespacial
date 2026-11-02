"""Administrator-facing provider consumption controls."""
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from app.services.auth import require_permission
from app.services import tile_budget
from app.core.config import get_settings

router = APIRouter(prefix="/tile-budget", tags=["Custos de imagens"],
                   dependencies=[Depends(require_permission("users.manage"))])


class BudgetUpdate(BaseModel):
    enabled: bool
    monthly_limit: int = Field(ge=1, le=tile_budget.MAX_LIMIT)


@router.get("")
def list_budgets():
    cfg = get_settings()
    entries = tile_budget.snapshot()
    for item in entries:
        item["configured"] = bool(
            cfg.google_map_tiles_enabled and cfg.google_maps_api_key
            if item["provider"] == "google" else
            cfg.mapbox_satellite_enabled and cfg.mapbox_access_token
        )
    return entries


@router.put("/{provider}")
def update_budget(provider: str, payload: BudgetUpdate):
    return tile_budget.update(provider, payload.enabled, payload.monthly_limit)
