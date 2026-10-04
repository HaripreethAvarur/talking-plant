"""Sign-up, the hourly logger, day labels and the leaderboard, through the real API."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.api import create_app
from backend.config import Settings
from backend.sensors.simulator import scenario_reading
from backend.service import PlantService
from backend.vision import health
from shared.contracts import Mood, PlantRegistration, utcnow

MAYA = {"username": "maya", "plant_name": "Spike", "plant_type": "succulent", "location": "48105"}


def post_reading(client, scenario="dry"):
    row = scenario_reading(scenario, 0, timestamp=utcnow())
    assert client.post("/api/v1/sensor-readings", json=row.model_dump(mode="json")).status_code == 200


def test_sign_up_sets_thresholds_and_survives_restart(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["registered"] is False
        assert client.get("/api/plant").status_code == 404
        assert client.post("/api/plant", json=MAYA | {"location": "Ann Arbor"}).status_code == 422
        assert client.post("/api/plant", json=MAYA).status_code == 200
        health_info = client.get("/api/health").json()
        assert health_info["registered"] and health_info["username"] == "maya"
        assert health_info["plant"]["name"] == "Spike"
        assert health_info["thresholds"] == {"dry": 15, "soggy": 70}
    with TestClient(create_app(settings)) as client:  # restored from the database
        assert client.get("/api/plant").json()["plant_name"] == "Spike"
        assert client.get("/api/health").json()["thresholds"]["dry"] == 15


def test_log_now_label_day_and_leaderboard(settings, monkeypatch):
    async def looks(*args, **kwargs):
        return "Green leaves, slightly droopy."

    monkeypatch.setattr(health, "look", looks)
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/v1/care-log/log-now").status_code == 409  # nobody signed up
        client.post("/api/plant", json=MAYA | {"plant_type": "plant"})
        post_reading(client, "healthy")
        row = client.post("/api/v1/care-log/log-now").json()
        assert row["water_pct"] == 60 and row["sun_pct"] == pytest.approx(60)
        assert row["health"] == "Green leaves, slightly droopy."
        assert row["mood"] == "happy"  # no ASI key in tests: the live rule decides
        assert client.get("/api/v1/care-log").json()["items"][-1]["hour"] == row["hour"]
        labelled = client.post("/api/v1/care-log/label-day").json()
        assert labelled["day_mood"] == "happy"
        board = client.get("/api/leaderboard").json()
        assert board["you"] == "maya"
        assert [(e["username"], e["happy_days"]) for e in board["entries"]] == [("maya", 1)]


def test_chat_context_includes_care_log_and_looks(settings, monkeypatch):
    async def looks(*args, **kwargs):
        return "Some leaves are yellow."

    monkeypatch.setattr(health, "look", looks)
    with TestClient(create_app(settings)) as client:
        client.post("/api/plant", json=MAYA)
        client.post("/api/v1/care-log/log-now")
        context = client.get("/api/v1/plants/plant-1/context").json()
        assert context["hourly"][-1]["health"] == "Some leaves are yellow."
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json()["looks"] == "Some leaves are yellow."


def test_leaderboard_needs_a_database(tmp_path):
    with TestClient(create_app(Settings(_env_file=None, database_url=""))) as client:
        assert client.get("/api/leaderboard").status_code == 503


async def test_scheduler_logs_once_per_interval_and_labels_at_night(settings):
    settings.log_interval_minutes = 1
    service = PlantService(settings)
    await service.start()
    try:
        await service.register(PlantRegistration(**MAYA))
        logged, labelled = [], []

        async def fake_log(now=None):
            logged.append(now)

        async def fake_label(day=None):
            labelled.append(day)

        service.care.log_now, service.care.label_day = fake_log, fake_label
        base = datetime(2026, 10, 3, 16, 0, 5, tzinfo=timezone.utc)  # 12:00 in Detroit
        for seconds in (0, 20, 40, 70, 80, 130):
            await service.care.tick(base + timedelta(seconds=seconds))
        assert len(logged) == 3  # one per minute: 16:00, 16:01 and 16:02
        assert labelled == []
        night = datetime(2026, 10, 4, 3, 40, tzinfo=timezone.utc)  # 23:40 in Detroit
        await service.care.tick(night)
        await service.care.tick(night.replace(minute=50))
        assert [str(day) for day in labelled] == ["2026-10-03"]  # once per local day
    finally:
        await service.close()


def test_rule_fallback_never_logs_grateful():
    from backend.conversation import labels

    assert labels._rule_for_day([]) is None
    assert Mood.grateful not in labels.LOG_MOODS
