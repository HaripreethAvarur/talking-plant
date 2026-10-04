"""The ASI:One-facing Plant Care Agent answers from the backend's live context."""

from datetime import timedelta

import httpx
from pydantic import SecretStr

from backend.agent import chat_agent
from backend.config import get_settings
from backend.conversation import replies
from backend.conversation.scripted import NO_MOISTURE_LINE
from backend.sensors.simulator import scenario_reading
from shared.contracts import (
    ConversationContext,
    HourlyReading,
    Mood,
    PlantProfile,
    PlantState,
    Status,
    UIPlantState,
    utcnow,
)


def backend_returning(monkeypatch, handler):
    real = httpx.AsyncClient
    monkeypatch.setattr(
        chat_agent.httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw)
    )
    monkeypatch.setattr(get_settings(), "asi_api_key", SecretStr(""))


async def test_answers_from_live_context(monkeypatch):
    reading = scenario_reading("dry", 0)
    state = PlantState(
        plant_id="plant-1",
        mood=Mood.thirsty,
        sensor_health=Status.ok,
        moisture=reading.moisture,
        light=reading.light,
    )
    context = ConversationContext(plant_id="plant-1", profile=PlantProfile(), state=state, recent_events=[])
    seen = []

    def handler(request):
        seen.append(request.url.path)
        return httpx.Response(200, text=context.model_dump_json())

    backend_returning(monkeypatch, handler)
    text = await chat_agent.answer("Are you okay?")
    assert seen == ["/api/v1/plants/plant-1/context"]
    assert "15%" in text and "thirsty" in text  # scripted fallback, grounded in the reading


async def test_backend_down_gives_a_friendly_line(monkeypatch):
    backend_returning(monkeypatch, lambda request: httpx.Response(503))
    assert await chat_agent.answer("Are you okay?") == chat_agent.OFFLINE_LINE


async def test_missing_readings_are_admitted(monkeypatch):
    context = ConversationContext(
        plant_id="plant-1", profile=PlantProfile(), state=PlantState(plant_id="plant-1"), recent_events=[]
    )
    backend_returning(monkeypatch, lambda request: httpx.Response(200, text=context.model_dump_json()))
    assert await chat_agent.answer("Do you need water?") == NO_MOISTURE_LINE


def test_prompt_includes_the_hourly_table():
    start = utcnow().replace(minute=0, second=0, microsecond=0) - timedelta(hours=2)
    rows = [
        HourlyReading(username="maya", hour=start, sun_pct=70.4, water_pct=55, health="Leaves upright."),
        HourlyReading(username="maya", hour=start + timedelta(hours=1), water_pct=20, mood=Mood.thirsty),
    ]
    state = UIPlantState(mood=Mood.thirsty, moisture_pct=18, light_pct=60, leaf_issues=[])
    system = replies.build_messages(state, "Hi", [], replies.Plant(), rows)[0]["content"]
    assert "only quote numbers from 'Facts right now'" in system
    assert f"{start:%a %H:00} | 70 | 55 | - | - | Leaves upright." in system
    assert "| - | 20 | - | thirsty | -" in system
    assert "My last hours" not in replies.build_messages(state, "Hi", [], replies.Plant())[0]["content"]
