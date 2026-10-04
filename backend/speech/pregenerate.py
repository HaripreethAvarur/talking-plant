"""Pre-generate and cache every fixed line so the demo can speak offline (Task 7).

Run once with a real ELEVENLABS_API_KEY, before going on stage:
    python -m backend.speech.pregenerate
"""

import asyncio
import sys

from backend.conversation.scripted import cacheable_lines
from backend.speech import tts


async def main() -> int:
    if not tts.is_available():
        print("ELEVENLABS_API_KEY is not set in .env; nothing to generate.")
        return 1
    failed = 0
    for line in cacheable_lines():
        audio = await tts.synthesize(line)
        status = "cached " if audio.cached else ("new    " if audio.audio_url else "FAILED ")
        failed += audio.audio_url is None
        print(f"{status} {line}")
    print(f"\n{len(cacheable_lines()) - failed} lines ready in {tts.CACHE_DIR}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
