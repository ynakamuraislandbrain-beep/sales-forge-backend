"""Application configuration management."""

from functools import lru_cache
from typing import List, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(..., alias="DATABASE_URL")
    gemini_api_key: str = Field(..., alias="GEMINI_API_KEY")
    neon_jwks_url: str = Field(..., alias="NEON_JWKS_URL")
    neon_jwt_audience: Optional[str] = Field(default=None, alias="NEON_JWT_AUDIENCE")
    neon_jwt_issuer: Optional[str] = Field(default=None, alias="NEON_JWT_ISSUER")
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=False, alias="DEBUG")
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")

    allowed_origins: str | List[str] = Field(
        default=[],
        alias="ALLOWED_ORIGINS",
    )

    live_api_model: str = Field(..., alias="LIVE_API_MODEL")

    analysis_api_model: str = Field(..., alias="ANALYSIS_API_MODEL")

    @field_validator("allowed_origins", mode="before")
    @classmethod
    def parse_origins(cls, v: str | List[str]) -> List[str]:
        """Parse comma-separated origins string into list."""
        if isinstance(v, str):
            return [origin.strip() for origin in v.split(",")]
        return v

    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.app_env == "production"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
