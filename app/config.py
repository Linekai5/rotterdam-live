"""Application configuration using Pydantic Settings."""
from typing import List, Union
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
import json


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General Project Info
    PROJECT_NAME: str = "Rotterdam Live Unified Data Engine"
    ENVIRONMENT: str = "production"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    # CORS
    CORS_ORIGINS: Union[List[str], str] = [
        "https://rotterdamlive.nl",
        "https://www.rotterdamlive.nl",
        "http://localhost:5173",
        "http://localhost:3000",
    ]

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def assemble_cors_origins(cls, v: Union[str, List[str]]) -> List[str]:
        if isinstance(v, str):
            if v.startswith("[") and v.endswith("]"):
                try:
                    return json.loads(v)
                except Exception:
                    pass
            return [i.strip() for i in v.split(",") if i.strip()]
        return v

    # PostgreSQL & PostGIS
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "rotterdamlive_secret_2026"
    POSTGRES_DB: str = "rotterdamlive"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = (
        "postgresql+asyncpg://postgres:rotterdamlive_secret_2026@db:5432/rotterdamlive"
    )
    DATABASE_URL_SYNC: str = (
        "postgresql://postgres:rotterdamlive_secret_2026@db:5432/rotterdamlive"
    )

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Ingestion Schedule Frequencies (seconds)
    P2000_POLL_INTERVAL_SECONDS: int = 45
    MOBILITY_POLL_INTERVAL_SECONDS: int = 60
    BRIDGES_POLL_INTERVAL_SECONDS: int = 120
    TRANSIT_POLL_INTERVAL_SECONDS: int = 30
    NEWS_POLL_INTERVAL_SECONDS: int = 300
    WEATHER_POLL_INTERVAL_SECONDS: int = 600
    AIR_QUALITY_POLL_INTERVAL_SECONDS: int = 900
    SPATIAL_BASELINE_SYNC_HOURS: int = 24

    # Low-Frequency & Municipal Ingestion Frequencies
    AMENITIES_SYNC_HOURS: int = 24
    ROADWORKS_POLL_INTERVAL_SECONDS: int = 900
    WATERWAYS_POLL_INTERVAL_SECONDS: int = 600
    POWER_OUTAGE_POLL_INTERVAL_SECONDS: int = 900

    # Optional External API Keys & Utility Credentials
    PDOK_API_KEY: str = ""
    OPEN_DATA_SOFT_KEY: str = ""
    OPENOV_API_KEY: str = ""
    ENERGIEONDERBREKINGEN_API_KEY: str = ""

    # Geospatial Constants
    ROTTERDAM_MIN_LON: float = 4.25
    ROTTERDAM_MIN_LAT: float = 51.80
    ROTTERDAM_MAX_LON: float = 4.70
    ROTTERDAM_MAX_LAT: float = 52.05
    ROTTERDAM_CENTER_LON: float = 4.4777
    ROTTERDAM_CENTER_LAT: float = 51.9244


settings = Settings()
