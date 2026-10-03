"""Settings loaded from .env at the repo root.

Combines infrastructure settings (Settings class) with speech/LLM module
constants used by the conversation and speech subsystems.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.contracts import PlantProfile

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

# ---------------------------------------------------------------------------
# Infrastructure settings (database, deployment, Fetch agent)
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)
    database_url: SecretStr = SecretStr("")
    database_required: bool = False
    ingestion_token: SecretStr = SecretStr("")
    viewer_token: SecretStr = SecretStr("")
    deployment_mode: str = "local"
    demo_mode: bool = False
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    profile_path: Path = Path("shared/plant-profile.json")
    retry_buffer_size: int = Field(default=1000, ge=1)
    history_limit: int = Field(default=1000, ge=1)
    dedup_limit: int = Field(default=10000, ge=1)
    future_skew_seconds: float = Field(default=5, ge=0)
    fetch_enabled: bool = False
    fetch_seed: SecretStr = SecretStr("")
    fetch_target: str = ""
    fetch_port: int = 8001
    fetch_endpoint: str = "http://127.0.0.1:8001/submit"

    @model_validator(mode="after")
    def remote_auth(self):
        if self.deployment_mode not in ("local", "remote"):
            raise ValueError("DEPLOYMENT_MODE must be local or remote")
        if self.deployment_mode == "remote":
            if not self.ingestion_token.get_secret_value() or not self.viewer_token.get_secret_value():
                raise ValueError("remote mode requires INGESTION_TOKEN and VIEWER_TOKEN")
            if self.ingestion_token == self.viewer_token:
                raise ValueError("remote mode requires distinct ingestion and viewer tokens")
            if "*" in self.cors_origins:
                raise ValueError("remote mode requires explicit CORS origins")
        if self.fetch_enabled and (not self.fetch_seed.get_secret_value() or not self.fetch_target):
            raise ValueError("FETCH_ENABLED requires FETCH_SEED and FETCH_TARGET")
        return self

    def profile(self):
        if self.profile_path.exists():
            return PlantProfile.model_validate_json(self.profile_path.read_text())
        return PlantProfile()


# ---------------------------------------------------------------------------
# Speech / LLM module-level constants (used by conversation & speech modules)
# ---------------------------------------------------------------------------

PLACEHOLDER_PREFIX = "your-"


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def is_configured(value: str) -> bool:
    return bool(value) and not value.startswith(PLACEHOLDER_PREFIX)


# ElevenLabs (STT and TTS)
ELEVENLABS_API_KEY = _get("ELEVENLABS_API_KEY", "your-elevenlabs-api-key")
ELEVENLABS_BASE_URL = _get("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io")
ELEVENLABS_STT_MODEL = _get("ELEVENLABS_STT_MODEL", "scribe_v1")
ELEVENLABS_VOICE_ID = _get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
ELEVENLABS_TTS_MODEL = _get("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5")

# ASI:One LLM
ASI_API_KEY = _get("ASI_API_KEY", "your-asi-one-api-key")
ASI_BASE_URL = _get("ASI_BASE_URL", "https://api.asi1.ai/v1")
ASI_MODEL = _get("ASI_MODEL", "asi1-mini")
ASI_TIMEOUT_S = float(_get("ASI_TIMEOUT_S", "4"))

# Plant identity used in prompts and scripted lines
PLANT_NAME = _get("PLANT_NAME", "Sprout")
PLANT_SPECIES = _get("PLANT_SPECIES", "pothos")

# UI bridge server
SERVER_HOST = _get("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(_get("SERVER_PORT", "8000"))
