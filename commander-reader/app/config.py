"""
Settings for commander-reader, loaded entirely from environment variables
(see .env.example / docker-compose.yml). No config file, no CLI flags.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    commander_host: str = Field(..., description="Hostname or IP of the Commander unit")
    commander_port: int = 443
    commander_username: str = "MANAGER"
    commander_password: str = Field(..., description="Commander service account password")
    commander_verify_ssl: bool = False

    poll_interval_seconds: int = 60
    session_refresh_minutes: int = 25
    # Circuit breaker — see commander_client.py's is_locked_out. Default 3 is
    # well under the Commander unit's own login-attempt lockout (commonly ~10).
    commander_lockout_threshold: int = 3
    # Optional shared secret guarding POST /config/credentials specifically
    # (the one write endpoint in an otherwise read-only, unauthenticated-by-
    # design service — see README's "No authentication" section). Leave
    # unset to match this service's existing LAN-trust model; set it if
    # anything beyond a tightly firewalled LAN can reach this port.
    config_api_key: str | None = None

    port: int = 8200
    log_level: str = "INFO"
    db_path: str = "/app/data/history.db"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")


def load_settings() -> Settings:
    return Settings()
