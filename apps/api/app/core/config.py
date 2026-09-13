"""Application configuration via environment variables (pydantic-settings).

Never hard-code secrets. All values come from environment (see .env.example).
"""
from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "IIC CyberLab API"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    database_url: str = "postgresql+asyncpg://cyberlab:cyberlab@localhost:5432/cyberlab"
    redis_url: str = "redis://localhost:6379/0"

    # Keycloak / OIDC
    oidc_issuer_url: str = "http://localhost:8080/realms/cyberlab"
    oidc_client_id: str = "api"
    oidc_client_secret: str = ""
    oidc_well_known_url: str = ""

    # Security
    app_secret: str = "change-me"
    access_token_cookie_name: str = "cyberlab_refresh"
    cors_origins: str = "http://localhost:3000"

    # Lab / infrastructure (used from Phase 2 onward)
    labs_network_name: str = "cyberlab_labs"
    lab_default_expiry_minutes: int = 60
    lab_max_instances_per_user: int = 2
    lab_image: str = "alpine:3.20"
    lab_docker_socket: str = "/var/run/docker.sock"
    lab_provisioning_timeout_minutes: int = 10

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()