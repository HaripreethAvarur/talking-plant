"""All settings, loaded once from the environment and .env at the repo root.

Secrets left blank (or as a "your-..." placeholder) switch that module to its
offline fallback instead of failing.
"""

from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from shared.contracts import PlantProfile

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

PLACEHOLDER_PREFIX = "your-"
SECRETS = (
    "database_url",
    "ingestion_token",
    "viewer_token",
    "fetch_seed",
    "agent_seed",
    "elevenlabs_api_key",
    "asi_api_key",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", hide_input_in_errors=True)

    # Backend server
    host: str = "127.0.0.1"
    port: int = 8000
    deployment_mode: str = "local"
    demo_mode: bool = False
    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:5173"]
    ingestion_token: SecretStr = SecretStr("")
    viewer_token: SecretStr = SecretStr("")

    # Database (Neon in production, SQLite or empty for local work)
    database_url: SecretStr = SecretStr("")
    database_required: bool = False
    profile_path: Path = Path("shared/plant-profile.json")
    retry_buffer_size: int = Field(default=1000, ge=1)
    history_limit: int = Field(default=1000, ge=1)
    dedup_limit: int = Field(default=10000, ge=1)
    future_skew_seconds: float = Field(default=5, ge=0)

    # Touch pad and UI display
    touch_cooldown_seconds: float = Field(default=10, ge=1)
    touch_listen_seconds: float = Field(default=6, ge=1, le=15)
    touch_debounce_seconds: float = Field(default=0.04, ge=0)
    ui_light_raw_max: float = Field(default=1023, gt=0)
    ui_light_lux_max: float = Field(default=1000, gt=0)

    # ElevenLabs: speech-to-text and the plant's voice
    elevenlabs_api_key: SecretStr = SecretStr("")
    elevenlabs_base_url: str = "https://api.elevenlabs.io"
    elevenlabs_stt_model: str = "scribe_v1"
    elevenlabs_voice_id: str = "cgSgspJ2msm6clMCkdW9"  # Jessica: playful, bright, warm (free-plan voice)
    elevenlabs_tts_model: str = "eleven_flash_v2_5"

    # ASI:One LLM: conversation replies
    asi_api_key: SecretStr = SecretStr("")
    asi_base_url: str = "https://api.asi1.ai/v1"
    asi_model: str = "asi1-mini"
    asi_timeout_s: float = Field(default=4, gt=0)

    # Hourly care log (sun, water, air, how the plant looks, ASI mood) and the nightly day label
    log_interval_minutes: float = Field(default=60, gt=0, description="use 1 for demos")
    day_label_time: str = Field(default="23:30", pattern=r"^\d{2}:\d{2}$", description="local time")
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "llama3.2-vision"  # Meta; needs ~8 GB RAM. moondream runs on small laptops.
    ollama_timeout_s: float = Field(default=180, gt=0)
    camera_index: int = 0
    camera_image: Path | None = None  # describe this file instead of the webcam (testing)

    # Plant Care Agent on Agentverse, chat-able from ASI:One (python -m backend.agent.chat_agent)
    agent_name: str = "talking-plant-sprout"
    agent_seed: SecretStr = SecretStr("")
    agent_port: int = 8010
    backend_url: str = "http://127.0.0.1:8000"

    # Optional Fetch.ai uAgents mirror
    fetch_enabled: bool = False
    fetch_seed: SecretStr = SecretStr("")
    fetch_target: str = ""
    fetch_port: int = 8001
    fetch_endpoint: str = "http://127.0.0.1:8001/submit"

    @field_validator(*SECRETS, mode="before")
    @classmethod
    def blank_placeholders(cls, value):
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        return "" if isinstance(raw, str) and raw.strip().startswith(PLACEHOLDER_PREFIX) else value

    @model_validator(mode="after")
    def consistent(self):
        if self.touch_cooldown_seconds < self.touch_listen_seconds:
            raise ValueError("TOUCH_COOLDOWN_SECONDS must cover TOUCH_LISTEN_SECONDS")
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


@lru_cache
def get_settings() -> Settings:
    """The process-wide settings; API keys for speech and the LLM are read from here."""
    return Settings()
