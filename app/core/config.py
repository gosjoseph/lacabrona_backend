from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # MongoDB
    mongo_url: str = "mongodb://localhost:27017"
    mongo_db: str = "lacabrona"

    # CORS (comma-separated list, env name kept as CORS_ORIGINS for backwards compat)
    cors_origins_raw: str = Field(
        default="http://localhost:5173,http://localhost:4173,https://localhost:5173",
        alias="CORS_ORIGINS",
    )

    # SuperTokens
    supertokens_core_url: str = "http://supertokens:3567"
    supertokens_api_key: str = ""
    supertokens_app_name: str = "La Cabrona"
    api_domain: str = "https://localhost:8443"
    app_url: str = "https://localhost:5173"

    # Google OAuth (used by SuperTokens ThirdParty recipe)
    google_client_id: str = ""
    google_client_secret: str = ""

    # App
    environment: str = "development"

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def cors_origins(self) -> List[str]:
        return [o.strip() for o in self.cors_origins_raw.split(",") if o.strip()]


settings = Settings()
