"""Settings loaded from .env at the repo root.

Every credential has a placeholder default. A module whose key is still a
placeholder reports itself as unavailable and uses its offline fallback.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(REPO_ROOT / ".env")

PLACEHOLDER_PREFIX = "your-"


def _get(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def is_configured(value: str) -> bool:
    return bool(value) and not value.startswith(PLACEHOLDER_PREFIX)


# ElevenLabs (Tasks 3 and 7)
ELEVENLABS_API_KEY = _get("ELEVENLABS_API_KEY", "your-elevenlabs-api-key")
ELEVENLABS_BASE_URL = _get("ELEVENLABS_BASE_URL", "https://api.elevenlabs.io")
ELEVENLABS_STT_MODEL = _get("ELEVENLABS_STT_MODEL", "scribe_v1")
# Default is the ElevenLabs premade "Rachel" voice; swap for the locked plant voice.
ELEVENLABS_VOICE_ID = _get("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
ELEVENLABS_TTS_MODEL = _get("ELEVENLABS_TTS_MODEL", "eleven_flash_v2_5")

# ASI:One LLM (Task 5)
ASI_API_KEY = _get("ASI_API_KEY", "your-asi-one-api-key")
ASI_BASE_URL = _get("ASI_BASE_URL", "https://api.asi1.ai/v1")
ASI_MODEL = _get("ASI_MODEL", "asi1-mini")
ASI_TIMEOUT_S = float(_get("ASI_TIMEOUT_S", "4"))

# Plant identity used in prompts and scripted lines (Task 6 will move this to Neon)
PLANT_NAME = _get("PLANT_NAME", "Sprout")
PLANT_SPECIES = _get("PLANT_SPECIES", "pothos")

# UI bridge server
SERVER_HOST = _get("SERVER_HOST", "127.0.0.1")
SERVER_PORT = int(_get("SERVER_PORT", "8000"))
