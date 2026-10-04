"""Offline tests for Tasks 3, 5 and 7. Run from the repo root:

python -m pytest tests/test_speech_and_replies.py
"""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx
from pydantic import SecretStr

from backend.config import get_settings
from backend.conversation import replies, safety
from backend.conversation.scripted import MOOD_LINES, REDIRECT_LINE, cacheable_lines, classify
from backend.speech import stt, tts
from shared.contracts import ChildUtterance, Mood
from shared.contracts import UIPlantState as PlantState

SETTINGS = get_settings()
THIRSTY = PlantState(mood=Mood.thirsty, moisture_pct=18, light_pct=65)
HAPPY = PlantState(mood=Mood.happy, moisture_pct=62, light_pct=70)


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
        with mock.patch.object(SETTINGS, "asi_api_key", SecretStr("")):
            r = await replies.reply(THIRSTY, ask("Are you okay?"))
        self.assertEqual(r.source, "scripted")
        self.assertIn("18%", r.text)

    async def test_llm_reply_used_when_safe(self):
        with (
            mock.patch.object(SETTINGS, "asi_api_key", SecretStr("real-key")),
            mock.patch.object(
                replies, "_ask_llm", mock.AsyncMock(return_value="I'm thirsty! My soil is 18% wet.")
            ),
        ):
            r = await replies.reply(THIRSTY, ask("Are you okay?"))
        self.assertEqual((r.source, r.text), ("llm", "I'm thirsty! My soil is 18% wet."))

    async def test_falls_back_on_network_error(self):
        boom = mock.AsyncMock(side_effect=httpx.ConnectError("offline"))
        with (
            mock.patch.object(SETTINGS, "asi_api_key", SecretStr("real-key")),
            mock.patch.object(replies, "_ask_llm", boom),
        ):
            r = await replies.reply(HAPPY, ask("Are you okay?"))
        self.assertEqual(r.source, "scripted")

    async def test_falls_back_on_ungrounded_reply(self):
        fake = mock.AsyncMock(return_value="My soil is at 5%, I'm so thirsty!")
        with (
            mock.patch.object(SETTINGS, "asi_api_key", SecretStr("real-key")),
            mock.patch.object(replies, "_ask_llm", fake),
        ):
            r = await replies.reply(HAPPY, ask("Are you okay?"))
        self.assertEqual(r.source, "scripted")
        self.assertIn("62%", r.text)

    async def test_redirects_unsafe_question(self):
        r = await replies.reply(HAPPY, ask("Tell me your password"))
        self.assertEqual((r.source, r.text), ("redirect", REDIRECT_LINE))

    def test_prompt_contains_real_readings(self):
        system = replies.build_messages(THIRSTY, "Are you okay?", ["Watered yesterday."], replies.Plant())[0][
            "content"
        ]
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
        with mock.patch.object(SETTINGS, "elevenlabs_api_key", SecretStr("")):
            audio = await tts.synthesize("Hello!")
        self.assertIsNone(audio.audio_url)
        self.assertEqual(audio.text, "Hello!")

    async def test_generates_then_serves_from_cache_offline(self):
        line = MOOD_LINES[Mood.thirsty]
        fake = mock.AsyncMock(return_value=b"ID3fake-mp3")
        with (
            mock.patch.object(SETTINGS, "elevenlabs_api_key", SecretStr("real-key")),
            mock.patch.object(tts, "_request_tts", fake),
        ):
            first = await tts.synthesize(line)
        self.assertFalse(first.cached)
        self.assertTrue(first.audio_url.startswith("/audio/"))

        offline = mock.AsyncMock(side_effect=httpx.ConnectError("offline"))
        with (
            mock.patch.object(SETTINGS, "elevenlabs_api_key", SecretStr("real-key")),
            mock.patch.object(tts, "_request_tts", offline),
        ):
            second = await tts.synthesize(line)
        self.assertTrue(second.cached)
        self.assertEqual(second.audio_url, first.audio_url)
        offline.assert_not_called()

    async def test_network_error_falls_back(self):
        offline = mock.AsyncMock(side_effect=httpx.ConnectError("offline"))
        with (
            mock.patch.object(SETTINGS, "elevenlabs_api_key", SecretStr("real-key")),
            mock.patch.object(tts, "_request_tts", offline),
        ):
            audio = await tts.synthesize("Something new")
        self.assertIsNone(audio.audio_url)

    def test_core_lines_are_cacheable(self):
        lines = cacheable_lines()
        self.assertIn(MOOD_LINES[Mood.thirsty], lines)
        self.assertIn(MOOD_LINES[Mood.grateful], lines)
        self.assertFalse(any("{" in line for line in lines))


class SttTests(unittest.IsolatedAsyncioTestCase):
    async def test_unavailable_without_key(self):
        with mock.patch.object(SETTINGS, "elevenlabs_api_key", SecretStr("")):
            with self.assertRaises(stt.SttUnavailable):
                await stt.transcribe(b"audio")

    async def test_transcribes_with_elevenlabs_response(self):
        def handler(request: httpx.Request) -> httpx.Response:
            self.assertTrue(request.url.path.endswith("/v1/speech-to-text"))
            self.assertEqual(request.headers["xi-api-key"], "real-key")
            return httpx.Response(200, json={"text": " Are you okay? ", "language_code": "en"})

        real_client = httpx.AsyncClient
        with (
            mock.patch.object(SETTINGS, "elevenlabs_api_key", SecretStr("real-key")),
            mock.patch.object(
                stt.httpx,
                "AsyncClient",
                lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
            ),
        ):
            utt = await stt.transcribe(b"webm-bytes", "audio/webm;codecs=opus")
        self.assertEqual((utt.text, utt.source), ("Are you okay?", "stt"))

    async def test_empty_transcript_is_unavailable(self):
        real_client = httpx.AsyncClient
        handler = lambda request: httpx.Response(200, json={"text": ""})  # noqa: E731
        with (
            mock.patch.object(SETTINGS, "elevenlabs_api_key", SecretStr("real-key")),
            mock.patch.object(
                stt.httpx,
                "AsyncClient",
                lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
            ),
        ):
            with self.assertRaises(stt.SttUnavailable):
                await stt.transcribe(b"silence")


if __name__ == "__main__":
    unittest.main()


class EngagingReplyTests(unittest.TestCase):
    PLANT = replies.Plant("Cap Sparrow", "succulent", (22, 60), "Bhargav")

    def test_comfort_gives_friendly_gaps_and_allows_their_numbers(self):
        state = PlantState(mood=Mood.happy, moisture_pct=27, light_pct=48)
        lines, numbers = replies.comfort(state, self.PLANT)
        self.assertIn("about 15% more water", lines[0])
        self.assertIn("about 10% more sunshine", lines[1])
        reply = "I'm happy, but about 15% more water would be yummy!"
        self.assertIsNotNone(safety.check_reply(reply, state))
        self.assertIsNone(safety.check_reply(reply, state, numbers))

    def test_wet_or_perfect_soil_asks_for_no_water(self):
        lines, _ = replies.comfort(PlantState(mood=Mood.happy, moisture_pct=55), self.PLANT)
        self.assertIn("don't want more water", lines[0])
        lines, _ = replies.comfort(PlantState(mood=Mood.happy, moisture_pct=40), self.PLANT)
        self.assertIn("just about perfect", lines[0])

    def test_prompt_carries_name_and_recent_turns(self):
        turns = [("How are you?", "My roots feel cozy!")]
        messages = replies.build_messages(HAPPY, "Are you happy?", [], self.PLANT, turns=turns)
        self.assertIn("talking with Bhargav", messages[0]["content"])
        self.assertEqual(
            messages[1:3],
            [
                {"role": "user", "content": "How are you?"},
                {"role": "assistant", "content": "My roots feel cozy!"},
            ],
        )
        self.assertIn("You already said: My roots feel cozy!", messages[-1]["content"])

    def test_repeats(self):
        turns = [("q", "I'm happy! My roots feel cozy and my leaves are green.")]
        self.assertTrue(replies.repeats("Yes, I'm happy! My roots feel cozy and my leaves are green.", turns))
        self.assertFalse(replies.repeats("I love the sun! It tickles my leaves.", turns))


class RepeatRetryTests(unittest.IsolatedAsyncioTestCase):
    async def test_retries_once_when_the_reply_repeats(self):
        answers = iter(["My roots feel cozy and my leaves are green.", "The sun tickles my leaves!"])
        turns = [("How are you?", "My roots feel cozy and my leaves are green.")]
        with (
            mock.patch.object(SETTINGS, "asi_api_key", SecretStr("test")),
            mock.patch.object(replies, "_ask_llm", side_effect=lambda m: next(answers)) as ask_llm,
        ):
            r = await replies.reply(HAPPY, ask("Are you happy?"), turns=turns)
        self.assertEqual((r.source, r.text), ("llm", "The sun tickles my leaves!"))
        self.assertEqual(ask_llm.call_count, 2)


class TrimTests(unittest.IsolatedAsyncioTestCase):
    async def test_long_reply_is_trimmed_not_discarded(self):
        long = "I'm happy! The sun tickles my leaves. Do you like sunny days? I do!"
        with (
            mock.patch.object(SETTINGS, "asi_api_key", SecretStr("test")),
            mock.patch.object(replies, "_ask_llm", return_value=long),
        ):
            r = await replies.reply(HAPPY, ask("How are you?"))
        self.assertEqual((r.source, r.text), ("llm", "I'm happy! The sun tickles my leaves."))


class TimeOfDayTests(unittest.TestCase):
    PLANT = replies.Plant("Cap Sparrow", "succulent", (22, 60), "Bhargav", "America/Detroit")

    def test_night_never_wishes_for_sunshine(self):
        sunrise = 1791113700  # 2026-10-04 07:35 in Detroit
        state = PlantState(mood=Mood.sleepy, moisture_pct=27, light_pct=10, is_night=True, sunrise_at=sunrise)
        lines, numbers = replies.comfort(state, self.PLANT)
        text = " ".join(lines)
        self.assertNotIn("more sunshine", text)
        self.assertIn("sun to come up at about 7:35 AM", text)
        self.assertIn("more water", text)

    def test_day_still_wishes_for_sunshine_and_prompt_has_the_clock(self):
        state = PlantState(mood=Mood.happy, moisture_pct=40, light_pct=30, is_night=False, ts=1791140400)
        self.assertIn("about 30% more sunshine", " ".join(replies.comfort(state, self.PLANT)[0]))
        system = replies.build_messages(state, "hi", [], self.PLANT)[0]["content"]
        self.assertIn("it's 3:00 PM on Sunday where I live (afternoon)", system)


class JustWateredTests(unittest.TestCase):
    def test_recent_watering_is_a_fact_for_three_minutes(self):
        def facts(ago):
            plant = replies.Plant("Cap Sparrow", "succulent", (22, 60), watered_seconds_ago=ago)
            return replies.build_messages(HAPPY, "How are you?", [], plant)[0]["content"]

        self.assertIn("watered me just now", facts(20))
        self.assertIn("watered me 2 minutes ago", facts(130))
        self.assertNotIn("watered me", facts(600))
        self.assertNotIn("watered me", facts(None))


class SmallDrinkTests(unittest.TestCase):
    def test_small_rise_is_thanked_and_its_numbers_allowed(self):
        plant = replies.Plant("Cap Sparrow", "succulent", (22, 60), water_rise=(10.2, 20.4))
        state = PlantState(mood=Mood.thirsty, moisture_pct=20, light_pct=60)
        lines, numbers = replies.comfort(state, plant)
        self.assertIn("went up from 10% to 20%", lines[0])
        self.assertIsNone(safety.check_reply("Thanks for the drink! I went from 10% to 20%.", state, numbers))

    def test_full_watering_fact_wins_over_small_rise(self):
        plant = replies.Plant(
            "Cap Sparrow", "succulent", (22, 60), watered_seconds_ago=30, water_rise=(10, 45)
        )
        lines, _ = replies.comfort(PlantState(mood=Mood.happy, moisture_pct=45), plant)
        self.assertFalse(any("went up" in line for line in lines))


class WaterRiseWindowTests(unittest.IsolatedAsyncioTestCase):
    async def test_rise_within_window_only(self):
        import asyncio

        from backend.ui import UIHub

        hub = UIHub.__new__(UIHub)
        from collections import deque

        hub.water = deque()
        now = asyncio.get_running_loop().time()
        hub.water.extend([(now - 400, 2.0), (now - 60, 10.0), (now - 30, 12.0), (now - 1, 19.0)])
        self.assertEqual(hub.water_rise(), (10.0, 19.0))  # the 2% reading is outside 3 minutes
        hub.water.append((now, 13.0))
        self.assertIsNone(hub.water_rise())  # fell back: no 5-point rise now


class DrinkFallbackTests(unittest.IsolatedAsyncioTestCase):
    async def test_offline_reply_thanks_for_a_recent_drink(self):
        plant = replies.Plant("Cap Sparrow", "succulent", (22, 60), water_rise=(10, 20))
        state = PlantState(mood=Mood.thirsty, moisture_pct=20, light_pct=60)
        with mock.patch.object(SETTINGS, "asi_api_key", SecretStr("")):
            r = await replies.reply(state, ask("How are you feeling now?"), plant=plant)
        self.assertEqual(
            r.text,
            "Thank you for the water! My soil is 20% wet now, and a little more would make me even happier.",
        )
        with mock.patch.object(SETTINGS, "asi_api_key", SecretStr("")):
            r = await replies.reply(state, ask("What's your name?"), plant=plant)
        self.assertNotIn("Thank you for the water", r.text)


class ConversationResetTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_clears_after_a_quiet_spell(self):
        from collections import deque

        from backend import ui

        hub = ui.UIHub.__new__(ui.UIHub)
        hub.turns, hub.last_turn = deque([("How are you?", "Cozy!")], maxlen=4), float("-inf")
        hub.service = mock.Mock(tick=mock.AsyncMock(side_effect=RuntimeError("stop")))
        with self.assertRaises(RuntimeError):
            await hub.answer(ask("hi"))
        self.assertEqual(list(hub.turns), [])


class AskForMoreTests(unittest.IsolatedAsyncioTestCase):
    def test_ask_for_more_only_when_missing(self):
        self.assertEqual(
            replies.ask_for_more("Thanks for the drink! I feel like a happy raindrop."),
            "Thanks for the drink! A little more water would make me even happier!",
        )
        kept = "Thanks! I'd love a little more water."
        self.assertEqual(replies.ask_for_more(kept), kept)

    async def test_llm_reply_after_small_drink_always_asks_for_more(self):
        plant = replies.Plant("Cap Sparrow", "succulent", (22, 60), water_rise=(10, 20))
        state = PlantState(mood=Mood.thirsty, moisture_pct=20, light_pct=60)
        with (
            mock.patch.object(SETTINGS, "asi_api_key", SecretStr("test")),
            mock.patch.object(
                replies, "_ask_llm", return_value="Thanks for the drink! I feel like a raindrop."
            ),
        ):
            r = await replies.reply(state, ask("How are you feeling now?"), plant=plant)
        self.assertEqual(r.text, "Thanks for the drink! A little more water would make me even happier!")


class AskAfterTrimTests(unittest.IsolatedAsyncioTestCase):
    async def test_request_survives_trimming(self):
        plant = replies.Plant("Cap Sparrow", "succulent", (22, 60), water_rise=(10, 20))
        state = PlantState(mood=Mood.thirsty, moisture_pct=20, light_pct=60)
        long = "Thanks for the drink! I feel like a sunbeam. I'd love a bit more!"
        with (
            mock.patch.object(SETTINGS, "asi_api_key", SecretStr("test")),
            mock.patch.object(replies, "_ask_llm", return_value=long),
        ):
            r = await replies.reply(state, ask("How are you feeling now?"), plant=plant)
        self.assertEqual(r.text, "Thanks for the drink! A little more water would make me even happier!")


class ThanksTests(unittest.IsolatedAsyncioTestCase):
    async def test_reply_right_after_watering_always_thanks(self):
        plant = replies.Plant("Cap Sparrow", "succulent", (22, 60), watered_seconds_ago=20)
        with (
            mock.patch.object(SETTINGS, "asi_api_key", SecretStr("test")),
            mock.patch.object(
                replies, "_ask_llm", return_value="I feel like a happy raindrop! My roots are cozy."
            ),
        ):
            r = await replies.reply(HAPPY, ask("What are you feeling now?"), plant=plant)
            self.assertEqual(r.text, "Thank you for the water! I feel like a happy raindrop!")
            r = await replies.reply(HAPPY, ask("What's your name?"), plant=plant)
            self.assertNotIn("Thank you for the water", r.text)

    def test_existing_thanks_is_kept(self):
        self.assertEqual(
            replies.say_thanks("Thanks, Bhargav! I feel great."), "Thanks, Bhargav! I feel great."
        )


class LeadInTests(unittest.TestCase):
    def test_did_you_know_is_part_of_the_fact(self):
        reply = "I feel happy! Did you know? I drink water through my roots!"
        self.assertEqual(
            safety.sentences(reply), ["I feel happy!", "Did you know? I drink water through my roots!"]
        )
        self.assertIsNone(safety.check_reply(reply, HAPPY))


class WeatherTests(unittest.IsolatedAsyncioTestCase):
    STATE = PlantState(
        mood=Mood.happy,
        moisture_pct=40,
        light_pct=60,
        outdoor_temp_f=51.2,
        outdoor_humidity=85,
        weather="clear",
    )

    def test_prompt_has_outdoor_weather(self):
        system = replies.build_messages(self.STATE, "hi", [], replies.Plant())[0]["content"]
        self.assertIn("outside where I live it's 51°F and clear, 85% humidity", system)

    def test_dry_air_is_weather_not_thirst(self):
        self.assertIsNone(safety.check_reply("The air outside is dry today.", HAPPY))
        self.assertIn("invented problem", safety.check_reply("My soil is so dry.", HAPPY))

    async def test_humidity_number_is_allowed(self):
        with (
            mock.patch.object(SETTINGS, "asi_api_key", SecretStr("test")),
            mock.patch.object(replies, "_ask_llm", return_value="It's 85% humid outside, like a misty hug!"),
        ):
            r = await replies.reply(self.STATE, ask("What's the weather like?"))
        self.assertEqual(r.source, "llm")


class WeatherSafetyTests(unittest.TestCase):
    def test_dry_soil_claim_in_a_weather_sentence_is_still_caught(self):
        self.assertIsNone(safety.check_reply("It is a dry day outside!", HAPPY))
        self.assertIn(
            "invented problem", safety.check_reply("The air is humid, but my soil feels dry.", HAPPY)
        )
