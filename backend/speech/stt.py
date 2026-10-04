"""Task 3: child speech-to-text through ElevenLabs.

The UI does push-to-talk with the laptop microphone (hold the button or the
space bar), then POSTs the recorded clip to /api/stt. This module sends the clip
to ElevenLabs and returns a ChildUtterance.

Fallback: if the key is a placeholder, the network is down or nothing was heard,
transcribe() raises SttUnavailable and the UI keeps its on-screen question
buttons, which send a ChildUtterance with source="button".
"""

import logging
import re

import httpx

from backend.config import get_settings
from backend.speech.tts import elevenlabs_key
from shared.contracts import ChildUtterance

log = logging.getLogger(__name__)

STT_TIMEOUT_S = 8.0
MAX_CLIP_BYTES = 5 * 1024 * 1024  # ~a minute of opus; questions should be a few seconds


class SttUnavailable(Exception):
    """Speech-to-text could not produce text; the caller should use buttons instead."""


def is_available() -> bool:
    return bool(elevenlabs_key())


def _filename_for(mime: str) -> str:
    ext = {
        "audio/webm": "webm",
        "audio/ogg": "ogg",
        "audio/wav": "wav",
        "audio/x-wav": "wav",
        "audio/mpeg": "mp3",
        "audio/mp4": "m4a",
    }.get(mime.split(";")[0].strip(), "webm")
    return f"question.{ext}"


async def transcribe(audio: bytes, mime: str = "audio/webm") -> ChildUtterance:
    if not is_available():
        raise SttUnavailable("ELEVENLABS_API_KEY is not set")
    if not audio:
        raise SttUnavailable("empty recording")
    if len(audio) > MAX_CLIP_BYTES:
        raise SttUnavailable("recording too long")

    settings = get_settings()
    url = f"{settings.elevenlabs_base_url}/v1/speech-to-text"
    try:
        async with httpx.AsyncClient(timeout=STT_TIMEOUT_S) as client:
            resp = await client.post(
                url,
                headers={"xi-api-key": elevenlabs_key()},
                data={"model_id": settings.elevenlabs_stt_model, "language_code": "en"},
                files={"file": (_filename_for(mime), audio, mime.split(";")[0])},
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("ElevenLabs STT failed: %s", exc)
        raise SttUnavailable(str(exc)) from exc

    text = spoken_words(resp.json().get("text") or "")
    if not text:
        raise SttUnavailable("no speech detected")
    return ChildUtterance(text=text, source="stt")


def spoken_words(text: str) -> str:
    """The transcript without sound notes like "(silence)" or "[background noise]", which
    speech-to-text adds for clips with no real question in them."""
    text = re.sub(r"\([^)]*\)|\[[^\]]*\]", " ", text)
    text = " ".join(text.split())
    return text if re.search(r"[A-Za-z]{2,}", text) else ""


if __name__ == "__main__":
    # Manual check: python -m backend.speech.stt path/to/clip.webm
    import asyncio
    import mimetypes
    import sys

    path = sys.argv[1]
    mime = mimetypes.guess_type(path)[0] or "audio/webm"
    with open(path, "rb") as f:
        print(asyncio.run(transcribe(f.read(), mime)).model_dump_json(indent=2))
