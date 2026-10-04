"""How the plant looks, in words: one webcam photo described by an Ollama vision model.

The description is free text. Labels (happy, thirsty, ...) are chosen later by ASI:One,
which sees this text next to the sensor readings. Photos are never saved.

    python -m backend.vision.health                 # webcam
    python -m backend.vision.health leaf.jpg        # an image file
"""

import asyncio
import base64
import logging
from pathlib import Path

import httpx

from backend.config import get_settings

log = logging.getLogger(__name__)

PROMPT = (
    "This photo shows a potted plant. In one or two short sentences, describe only what you can "
    "see about its health: leaf colour (green, yellow, brown, spots), whether leaves are upright "
    "or drooping, and whether the soil looks dry or wet. Do not guess a disease. If no plant is "
    "visible, say so."
)
MAX_CHARS = 400


def capture_jpeg(camera_index: int) -> bytes | None:
    """One JPEG from the webcam, after letting auto-exposure settle; None if unavailable."""
    try:
        import cv2
    except ImportError:
        log.warning("OpenCV not installed (pip install -r requirements-vision.txt)")
        return None
    camera = cv2.VideoCapture(camera_index)
    try:
        if not camera.isOpened():
            return None
        ok, image = False, None
        for _ in range(8):
            ok, image = camera.read()
        if not ok or image is None:
            return None
        ok, encoded = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        return encoded.tobytes() if ok else None
    finally:
        camera.release()


async def describe(jpeg: bytes) -> str | None:
    """The vision model's description of one photo; None if Ollama is unavailable."""
    settings = get_settings()
    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout_s) as client:
            response = await client.post(
                f"{settings.ollama_url}/api/generate",
                json={
                    "model": settings.ollama_model,
                    "prompt": PROMPT,
                    "images": [base64.b64encode(jpeg).decode("ascii")],
                    "stream": False,
                    "options": {"temperature": 0.2, "num_predict": 120},
                },
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Ollama vision unavailable: %s", exc)
        return None
    text = " ".join(response.json().get("response", "").split())
    return text[:MAX_CHARS] or None


async def look(image: Path | None = None) -> str | None:
    """Photograph the plant (or read an image file) and describe it."""
    settings = get_settings()
    path = image or settings.camera_image
    if path:
        jpeg = Path(path).read_bytes() if Path(path).is_file() else None
    else:
        jpeg = await asyncio.to_thread(capture_jpeg, settings.camera_index)
    if not jpeg:
        log.warning("No photo available for the health check")
        return None
    return await describe(jpeg)


if __name__ == "__main__":
    import sys
    import time

    started = time.perf_counter()
    text = asyncio.run(look(Path(sys.argv[1]) if len(sys.argv) > 1 else None))
    print(f"[{time.perf_counter() - started:.1f}s] {text}")
