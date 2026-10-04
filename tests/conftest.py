from datetime import timedelta

import pytest
from pydantic import SecretStr

from backend.config import Settings, get_settings
from backend.sensors.simulator import scenario_reading
from shared.contracts import utcnow


@pytest.fixture(autouse=True)
def no_paid_apis(monkeypatch):
    """Tests never spend ElevenLabs/ASI:One credit, even with real keys in .env."""
    for key in ("elevenlabs_api_key", "asi_api_key"):
        monkeypatch.setattr(get_settings(), key, SecretStr(""))


@pytest.fixture(autouse=True)
def no_network_lookups(monkeypatch):
    """Air quality, sunrise/sunset, weather and camera/Ollama calls are faked in tests."""
    from backend import air
    from backend.vision import health

    async def nothing(*args, **kwargs):
        return None

    monkeypatch.setattr(air, "us_aqi", nothing)
    monkeypatch.setattr(air, "sun_times", nothing)
    monkeypatch.setattr(air, "weather", nothing)
    monkeypatch.setattr(health, "look", nothing)
    monkeypatch.setattr(health, "identify", nothing)


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, database_url=f"sqlite:///{tmp_path}/plant.db", future_skew_seconds=120)


@pytest.fixture
def reading():
    start = utcnow()

    def make(step, scenario="dry-to-watered", value=None):
        row = scenario_reading(scenario, step, timestamp=start + timedelta(seconds=step))
        if value is not None:
            row.moisture.relative_percent = value
            row.moisture.raw = 1000 - value * 8
        return row

    return make
