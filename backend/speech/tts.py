"""Task 7: the plant's voice through ElevenLabs text-to-speech.

One voice and one set of settings are locked here so the plant always sounds
the same. Every generated clip is cached on disk by a hash of (voice, model,
settings, text), so a line that was spoken once, or pre-generated with
`python -m backend.speech.pregenerate`, plays later with the network off.

Fallback: if the key is a placeholder or the request fails and the line is not
cached, synthesize() returns a SpeechAudio with audio_url=None and the UI speaks
the text with the browser's built-in speech synthesis.
"""

import hashlib
import json
import logging
from pathlib import Path

import httpx

from backend.config import get_settings
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


def elevenlabs_key() -> str:
    """The ElevenLabs key shared by speech-to-text and the voice; empty when not set."""
    return get_settings().elevenlabs_api_key.get_secret_value()


def is_available() -> bool:
    return bool(elevenlabs_key())


def cache_key(text: str) -> str:
    settings = get_settings()
    spec = {
        "voice": settings.elevenlabs_voice_id,
        "model": settings.elevenlabs_tts_model,
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
    settings = get_settings()
    url = f"{settings.elevenlabs_base_url}/v1/text-to-speech/{settings.elevenlabs_voice_id}"
    async with httpx.AsyncClient(timeout=TTS_TIMEOUT_S) as client:
        resp = await client.post(
            url,
            params={"output_format": OUTPUT_FORMAT},
            headers={"xi-api-key": elevenlabs_key(), "accept": "audio/mpeg"},
            json={
                "text": text,
                "model_id": settings.elevenlabs_tts_model,
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
