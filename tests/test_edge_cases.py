import asyncio
import sys
from datetime import timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from backend.agent.fetch_adapter import FetchAdapter
from backend.agent.mood import MoodEngine
from backend.config import Settings
from backend.service import PlantService
from shared.contracts import LeafObservation, PlantProfile, Source, Status, Thresholds


def test_initial_outlier_does_not_become_watering_baseline(reading):
    engine = MoodEngine(PlantProfile())
    events = []
    for step in range(10):
        row = reading(step, value=5 if step == 0 else 60)
        events += engine.sensor(row, row.timestamp)[1]
    assert not any(e.kind == "watering" for e in events)


def test_leaf_error_cannot_extend_stale_color_concern(reading):
    engine = MoodEngine(PlantProfile(thresholds=Thresholds(leaf_stale_seconds=5)))
    for step in (0, 1):
        row = LeafObservation(
            source=Source.image_file,
            timestamp=reading(step).timestamp,
            status=Status.ok,
            yellow_proportion=0.5,
            brown_proportion=0,
        )
        engine.leaf(row, row.timestamp)
    assert engine.unwell
    missing = LeafObservation(source=Source.hardware, timestamp=reading(6).timestamp, status=Status.error)
    engine.leaf(missing, missing.timestamp)
    engine.tick(reading(7).timestamp)
    assert not engine.unwell


def test_dry_debounce_cannot_progress_on_missing_data(reading):
    engine = MoodEngine(PlantProfile())
    row = reading(0, "dry")
    engine.sensor(row, row.timestamp)
    engine.tick(row.timestamp + timedelta(seconds=10))
    assert not engine.dry
    assert engine.state.sensor_health == Status.stale


async def test_same_time_different_id_is_ignored(settings, reading):
    service = PlantService(settings)
    await service.start()
    try:
        row = reading(0)
        await service.ingest(row, row.timestamp)
        copied = row.model_copy(update={"event_id": uuid4()})
        assert (await service.ingest(copied, row.timestamp))["status"] == "out_of_order"
    finally:
        await service.close()


async def test_slow_subscriber_receives_explicit_disconnect(settings, reading):
    service = PlantService(settings)
    queue = asyncio.Queue(maxsize=1)
    service.subscribers.add(queue)
    for step in (0, 1):
        row = reading(step)
        await service.ingest(row, row.timestamp)
    assert await queue.get() is None
    assert queue not in service.subscribers
    await service.close()


async def test_fetch_absent_is_nonfatal_and_reported(monkeypatch):
    monkeypatch.setitem(sys.modules, "uagents", None)
    disabled = FetchAdapter(Settings(_env_file=None))
    await disabled.start()
    assert disabled.status == "disabled"
    adapter = FetchAdapter(
        Settings(_env_file=None, fetch_enabled=True, fetch_seed="test-only", fetch_target="test")
    )
    await adapter.start()
    assert adapter.status == "untested"
    assert "unavailable" in adapter.detail.lower()
    await adapter.close()


def test_config_errors_hide_secrets():
    with pytest.raises(ValidationError) as caught:
        Settings(
            _env_file=None,
            deployment_mode="remote",
            database_url="postgresql://secret-user:secret-password@host/db",
        )
    assert "secret-password" not in str(caught.value)
