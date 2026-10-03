"""Task 3: child speech-to-text through ElevenLabs.

The UI does push-to-talk with the laptop microphone (hold the button or the
space bar), then POSTs the recorded clip to /api/stt. This module sends the clip
to ElevenLabs and returns a ChildUtterance.

Fallback: if the key is a placeholder, the network is down or nothing was heard,
transcribe() raises SttUnavailable and the UI keeps its on-screen question
buttons, which send a ChildUtterance with source="button".
"""

from __future__ import annotations

import logging

import httpx

from backend import config
from shared.contracts import ChildUtterance

log = logging.getLogger(__name__)

STT_TIMEOUT_S = 8.0
MAX_CLIP_BYTES = 5 * 1024 * 1024  # ~a minute of opus; questions should be a few seconds


class SttUnavailable(Exception):
    """Speech-to-text could not produce text; the caller should use buttons instead."""


def is_available() -> bool:
    return config.is_configured(config.ELEVENLABS_API_KEY)


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

    url = f"{config.ELEVENLABS_BASE_URL}/v1/speech-to-text"
    try:
        async with httpx.AsyncClient(timeout=STT_TIMEOUT_S) as client:
            resp = await client.post(
                url,
                headers={"xi-api-key": config.ELEVENLABS_API_KEY},
                data={"model_id": config.ELEVENLABS_STT_MODEL, "language_code": "en"},
                files={"file": (_filename_for(mime), audio, mime.split(";")[0])},
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("ElevenLabs STT failed: %s", exc)
        raise SttUnavailable(str(exc)) from exc

    text = (resp.json().get("text") or "").strip()
    if not text:
        raise SttUnavailable("no speech detected")
    return ChildUtterance(text=text, source="stt")


if __name__ == "__main__":
    # Manual check: python -m backend.speech.stt path/to/clip.webm
    import asyncio
    import mimetypes
    import sys

    path = sys.argv[1]
    mime = mimetypes.guess_type(path)[0] or "audio/webm"
    with open(path, "rb") as f:
        print(asyncio.run(transcribe(f.read(), mime)).model_dump_json(indent=2))
