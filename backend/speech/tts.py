"""Task 7: the plant's voice through ElevenLabs text-to-speech.

One voice and one set of settings are locked here so the plant always sounds
the same. Every generated clip is cached on disk by a hash of (voice, model,
settings, text), so a line that was spoken once, or pre-generated with
`python -m backend.speech.pregenerate`, plays later with the network off.

Fallback: if the key is a placeholder or the request fails and the line is not
cached, synthesize() returns a SpeechAudio with audio_url=None and the UI speaks
the text with the browser's built-in speech synthesis.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

import httpx

from backend import config
from shared.contracts import SpeechAudio

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).resolve().parent / "cache"
AUDIO_ROUTE = "/audio"  # the server mounts CACHE_DIR here
OUTPUT_FORMAT = "mp3_44100_128"
TTS_TIMEOUT_S = 6.0

# Locked voice settings: warm and steady, a little expressive.
VOICE_SETTINGS = {
    "stability": 0.55,
    "similarity_boost": 0.75,
    "style": 0.35,
    "use_speaker_boost": True,
}


def is_available() -> bool:
    return config.is_configured(config.ELEVENLABS_API_KEY)


def cache_key(text: str) -> str:
    spec = {
        "voice": config.ELEVENLABS_VOICE_ID,
        "model": config.ELEVENLABS_TTS_MODEL,
        "format": OUTPUT_FORMAT,
        "settings": VOICE_SETTINGS,
        "text": text.strip(),
    }
    return hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest()[:24]


def cache_path(text: str) -> Path:
    return CACHE_DIR / f"{cache_key(text)}.mp3"


def _audio(text: str, path: Path, cached: bool) -> SpeechAudio:
    return SpeechAudio(text=text, audio_url=f"{AUDIO_ROUTE}/{path.name}", cached=cached)


async def _request_tts(text: str) -> bytes:
    url = f"{config.ELEVENLABS_BASE_URL}/v1/text-to-speech/{config.ELEVENLABS_VOICE_ID}"
    async with httpx.AsyncClient(timeout=TTS_TIMEOUT_S) as client:
        resp = await client.post(
            url,
            params={"output_format": OUTPUT_FORMAT},
            headers={"xi-api-key": config.ELEVENLABS_API_KEY, "accept": "audio/mpeg"},
            json={
                "text": text,
                "model_id": config.ELEVENLABS_TTS_MODEL,
                "voice_settings": VOICE_SETTINGS,
            },
        )
        resp.raise_for_status()
        return resp.content


async def synthesize(text: str) -> SpeechAudio:
    text = text.strip()
    path = cache_path(text)
    if path.exists():
        return _audio(text, path, cached=True)

    if not is_available():
        return SpeechAudio(text=text)

    try:
        audio = await _request_tts(text)
    except httpx.HTTPError as exc:
        log.warning("ElevenLabs TTS failed, UI will use browser speech: %s", exc)
        return SpeechAudio(text=text)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".part")
    tmp.write_bytes(audio)
    tmp.replace(path)
    return _audio(text, path, cached=False)
