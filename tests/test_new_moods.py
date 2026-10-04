"""Sleepy at night, soggy when overwatered, and moisture bands per plant type."""

from datetime import datetime, timedelta, timezone

from backend.agent.mood import MoodEngine
from backend.conversation.scripted import MOOD_LINES
from backend.sensors.simulator import scenario_reading
from shared.contracts import PlantProfile, PlantRegistration, Thresholds

UTC_PROFILE = PlantProfile(timezone="UTC")


def run(engine, scenario, start, seconds, value=None):
    events = []
    for step in range(seconds):
        row = scenario_reading(scenario, step, timestamp=start + timedelta(seconds=step))
        if value is not None:
            row.moisture.relative_percent = value
        events += engine.sensor(row, row.timestamp)[1]
    return events


def test_dark_is_sleepy_at_night_and_too_dark_by_day():
    night = MoodEngine(UTC_PROFILE)
    events = run(night, "dark", datetime(2026, 10, 3, 23, tzinfo=timezone.utc), 6)
    assert night.state.mood.value == "sleepy"
    assert not [e for e in events if e.suggested_text]  # resting quietly
    day = MoodEngine(UTC_PROFILE)
    run(day, "dark", datetime(2026, 10, 3, 13, tzinfo=timezone.utc), 6)
    assert day.state.mood.value == "too_dark"


def test_morning_turns_sleepy_into_too_dark_without_new_readings():
    engine = MoodEngine(UTC_PROFILE)
    start = datetime(2026, 10, 4, 6, 59, 50, tzinfo=timezone.utc)
    run(engine, "dark", start, 6)
    assert engine.state.mood.value == "sleepy"
    engine.state.last_sensor_at = None  # keep the tick from marking the sensor stale
    engine.tick(start + timedelta(seconds=20))
    assert engine.state.mood.value == "too_dark"


def test_soggy_after_staying_very_wet_then_recovers():
    profile = UTC_PROFILE.model_copy(update={"thresholds": Thresholds(soggy_seconds=5)})
    engine = MoodEngine(profile)
    start = datetime(2026, 10, 3, 13, tzinfo=timezone.utc)
    events = run(engine, "healthy", start, 4, value=95)
    assert engine.state.mood.value == "happy"  # not soggy yet: must stay wet a while
    events += run(engine, "healthy", start + timedelta(seconds=4), 4, value=95)
    assert engine.state.mood.value == "soggy"
    assert [e.suggested_text for e in events if e.suggested_text] == [MOOD_LINES[engine.state.mood]]
    run(engine, "healthy", start + timedelta(seconds=8), 4, value=85)
    assert engine.state.mood.value == "soggy"  # still above the exit band
    run(engine, "healthy", start + timedelta(seconds=12), 10, value=70)
    assert engine.state.mood.value == "happy"


def test_plant_type_sets_the_moisture_bands():
    def adopt(plant_type):
        registration = PlantRegistration(
            username="maya", plant_name="Spike", plant_type=plant_type, location="48105"
        )
        return MoodEngine(UTC_PROFILE.for_registration(registration))

    start = datetime(2026, 10, 3, 13, tzinfo=timezone.utc)
    succulent, fern = adopt("succulent"), adopt("plant")
    run(succulent, "healthy", start, 6, value=20)
    run(fern, "healthy", start, 6, value=20)
    assert succulent.state.mood.value == "happy"  # 20% is fine for a succulent
    assert fern.state.mood.value == "thirsty"
    assert succulent.profile.username == "maya" and succulent.profile.name == "Spike"
