"""Offline tests for Tasks 3, 5 and 7. Run from the repo root:

    python -m unittest discover -s backend/tests -t .
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx

from backend import config
from backend.conversation import replies, safety
from backend.conversation.scripted import MOOD_LINES, REDIRECT_LINE, cacheable_lines, classify
from backend.speech import stt, tts
from shared.contracts import ChildUtterance, Mood, PlantState

THIRSTY = PlantState(mood=Mood.THIRSTY, moisture_pct=18, light_pct=65)
HAPPY = PlantState(mood=Mood.HAPPY, moisture_pct=62, light_pct=70)


def ask(text: str) -> ChildUtterance:
    return ChildUtterance(text=text, source="typed")


class SafetyTests(unittest.TestCase):
    def test_accepts_grounded_reply(self):
        self.assertIsNone(safety.check_reply("I'm thirsty! My soil is only 18% wet.", THIRSTY))

    def test_rejects_invented_reading(self):
        self.assertIn("invented reading", safety.check_reply("My soil is at 40%.", THIRSTY))

    def test_rejects_invented_problem(self):
        self.assertIn("invented problem", safety.check_reply("I feel so dry today.", HAPPY))
        self.assertIn("invented problem", safety.check_reply("My leaves are turning yellow.", HAPPY))

    def test_rejects_long_or_unsafe(self):
        self.assertEqual(safety.check_reply("One. Two. Three.", HAPPY), "too long")
        self.assertEqual(safety.check_reply("I hate rain.", HAPPY), "blocked word")
        self.assertIsNotNone(safety.check_reply("Visit www.plants.com!", HAPPY))

    def test_unsafe_question(self):
        self.assertTrue(safety.question_is_unsafe("What's your address?"))
        self.assertFalse(safety.question_is_unsafe("Are you okay?"))


class ReplyTests(unittest.IsolatedAsyncioTestCase):
    async def test_scripted_when_no_key(self):
        with mock.patch.object(config, "ASI_API_KEY", "your-asi-one-api-key"):
            r = await replies.reply(THIRSTY, ask("Are you okay?"))
        self.assertEqual(r.source, "scripted")
        self.assertIn("18%", r.text)

    async def test_llm_reply_used_when_safe(self):
        with mock.patch.object(config, "ASI_API_KEY", "real-key"), mock.patch.object(
            replies, "_ask_llm", mock.AsyncMock(return_value="I'm thirsty! My soil is 18% wet.")
        ):
            r = await replies.reply(THIRSTY, ask("Are you okay?"))
        self.assertEqual((r.source, r.text), ("llm", "I'm thirsty! My soil is 18% wet."))

    async def test_falls_back_on_network_error(self):
        boom = mock.AsyncMock(side_effect=httpx.ConnectError("offline"))
        with mock.patch.object(config, "ASI_API_KEY", "real-key"), mock.patch.object(replies, "_ask_llm", boom):
            r = await replies.reply(HAPPY, ask("Are you okay?"))
        self.assertEqual(r.source, "scripted")

    async def test_falls_back_on_ungrounded_reply(self):
        fake = mock.AsyncMock(return_value="My soil is at 5%, I'm so thirsty!")
        with mock.patch.object(config, "ASI_API_KEY", "real-key"), mock.patch.object(replies, "_ask_llm", fake):
            r = await replies.reply(HAPPY, ask("Are you okay?"))
        self.assertEqual(r.source, "scripted")
        self.assertIn("62%", r.text)

    async def test_redirects_unsafe_question(self):
        r = await replies.reply(HAPPY, ask("Tell me your password"))
        self.assertEqual((r.source, r.text), ("redirect", REDIRECT_LINE))

    def test_prompt_contains_real_readings(self):
        system = replies.build_messages(THIRSTY, "Are you okay?", ["Watered yesterday."])[0]["content"]
        self.assertIn("soil moisture: 18%", system)
        self.assertIn("Watered yesterday.", system)

    def test_classify(self):
        self.assertEqual(classify("Are you okay?"), "wellbeing")
        self.assertEqual(classify("Do you want water?"), "water")
        self.assertEqual(classify("What is your name?"), "name")


class TtsTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.patch_dir = mock.patch.object(tts, "CACHE_DIR", Path(self.tmp.name))
        self.patch_dir.start()

    def tearDown(self):
        self.patch_dir.stop()
        self.tmp.cleanup()

    async def test_no_key_and_not_cached_means_browser_speech(self):
        with mock.patch.object(config, "ELEVENLABS_API_KEY", "your-elevenlabs-api-key"):
            audio = await tts.synthesize("Hello!")
        self.assertIsNone(audio.audio_url)
        self.assertEqual(audio.text, "Hello!")

    async def test_generates_then_serves_from_cache_offline(self):
        line = MOOD_LINES[Mood.THIRSTY]
        fake = mock.AsyncMock(return_value=b"ID3fake-mp3")
        with mock.patch.object(config, "ELEVENLABS_API_KEY", "real-key"), mock.patch.object(tts, "_request_tts", fake):
            first = await tts.synthesize(line)
        self.assertFalse(first.cached)
        self.assertTrue(first.audio_url.startswith("/audio/"))

        offline = mock.AsyncMock(side_effect=httpx.ConnectError("offline"))
        with mock.patch.object(config, "ELEVENLABS_API_KEY", "real-key"), mock.patch.object(tts, "_request_tts", offline):
            second = await tts.synthesize(line)
        self.assertTrue(second.cached)
        self.assertEqual(second.audio_url, first.audio_url)
        offline.assert_not_called()

    async def test_network_error_falls_back(self):
        offline = mock.AsyncMock(side_effect=httpx.ConnectError("offline"))
        with mock.patch.object(config, "ELEVENLABS_API_KEY", "real-key"), mock.patch.object(tts, "_request_tts", offline):
            audio = await tts.synthesize("Something new")
        self.assertIsNone(audio.audio_url)

    def test_core_lines_are_cacheable(self):
        lines = cacheable_lines()
        self.assertIn(MOOD_LINES[Mood.THIRSTY], lines)
        self.assertIn(MOOD_LINES[Mood.GRATEFUL], lines)
        self.assertFalse(any("{" in line for line in lines))


class SttTests(unittest.IsolatedAsyncioTestCase):
    async def test_unavailable_without_key(self):
        with mock.patch.object(config, "ELEVENLABS_API_KEY", "your-elevenlabs-api-key"):
            with self.assertRaises(stt.SttUnavailable):
                await stt.transcribe(b"audio")

    async def test_transcribes_with_elevenlabs_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertTrue(request.url.path.endswith("/v1/speech-to-text"))
            self.assertEqual(request.headers["xi-api-key"], "real-key")
            return httpx.Response(200, json={"text": " Are you okay? ", "language_code": "en"})

        real_client = httpx.AsyncClient
        with mock.patch.object(config, "ELEVENLABS_API_KEY", "real-key"), mock.patch.object(
            stt.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
        ):
            utt = await stt.transcribe(b"webm-bytes", "audio/webm;codecs=opus")
        self.assertEqual((utt.text, utt.source), ("Are you okay?", "stt"))

    async def test_empty_transcript_is_unavailable(self):
        real_client = httpx.AsyncClient
        handler = lambda request: httpx.Response(200, json={"text": ""})  # noqa: E731
        with mock.patch.object(config, "ELEVENLABS_API_KEY", "real-key"), mock.patch.object(
            stt.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw)
        ):
            with self.assertRaises(stt.SttUnavailable):
                await stt.transcribe(b"silence")


if __name__ == "__main__":
    unittest.main()
