from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "Amazônika Geoespacial API"
    database_url: str = "postgresql+psycopg://amazonika:amazonika_local@localhost:5432/amazonika_geo"
    cors_origins: str = "http://localhost:3000,http://localhost:4173"
    storage_dir: Path = Path("./storage/uploads")
    public_base_url: str = "http://localhost:3000"
    google_maps_api_key: str | None = None
    mapbox_access_token: str | None = None
    mapbox_satellite_enabled: bool = False
    google_map_tiles_enabled: bool = False
    gee_enabled: bool = False
    gee_browser_preview_enabled: bool = False
    gee_internal_pilot_enabled: bool = False
    gee_project_id: str | None = None
    gee_service_account_email: str | None = None
    gee_service_account_key_file: str | None = None
    openai_api_key: str | None = None
    openai_model: str = "gpt-5-mini"
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

@lru_cache
def get_settings() -> Settings:
    return Settings()
