from datetime import timedelta

import pytest

from backend.config import Settings
from backend.sensors.simulator import scenario_reading
from shared.contracts import utcnow


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
