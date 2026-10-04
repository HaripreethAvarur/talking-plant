from datetime import timedelta

from backend.agent.mood import MoodEngine
from backend.conversation.scripted import MOOD_LINES
from shared.contracts import LeafObservation, Mood, PlantProfile, Source, Status, Thresholds

# No night hours, so "dark" always means too_dark whatever time the tests run.
DAYTIME = PlantProfile(thresholds=Thresholds(night_start_hour=0, night_end_hour=0))


def feed(engine, row):
    return engine.sensor(row, row.timestamp)[1]


def test_dry_watered_exact_speech_and_return(reading):
    engine = MoodEngine(PlantProfile())
    events = [event for step in range(24) for event in feed(engine, reading(step))]
    assert [e.suggested_text for e in events if e.suggested_text] == [
        MOOD_LINES[Mood.thirsty],
        MOOD_LINES[Mood.grateful],
    ]
    assert sum(e.kind == "watering" for e in events) == 1
    assert sum(e.kind == "mood_changed" and e.mood == Mood.grateful for e in events) == 1
    assert engine.state.mood == Mood.happy


def test_noise_does_not_water_or_repeat_thirst(reading):
    engine = MoodEngine(PlantProfile())
    events = [e for step in range(120) for e in feed(engine, reading(step, "noisy"))]
    assert not any(e.kind == "watering" for e in events)
    assert sum(e.suggested_text == MOOD_LINES[Mood.thirsty] for e in events) <= 1


def test_disconnect_reconnect_not_watering(reading):
    engine = MoodEngine(PlantProfile())
    for step in range(6):
        feed(engine, reading(step, "dry"))
    events = feed(engine, reading(6, "disconnected"))
    assert engine.state.moisture.relative_percent is None
    assert engine.state.sensor_health == Status.disconnected
    events += [e for step in range(7, 20) for e in feed(engine, reading(step, "watered"))]
    assert not any(e.kind == "watering" for e in events)


def test_silent_gap_resets_baseline(reading):
    engine = MoodEngine(PlantProfile())
    for step in range(6):
        feed(engine, reading(step, "dry"))
    engine.tick(reading(20).timestamp)
    assert engine.state.sensor_health == Status.stale
    assert engine.state.moisture.raw is None
    events = [e for step in range(21, 30) for e in feed(engine, reading(step, "watered"))]
    assert not any(e.kind == "watering" for e in events)


def test_stale_out_of_order_and_calibration_change(reading):
    engine = MoodEngine(PlantProfile())
    row = reading(0)
    assert engine.sensor(row, row.timestamp + timedelta(seconds=6))[0] == "stale"
    feed(engine, reading(1))
    assert engine.sensor(row, row.timestamp)[0] == "out_of_order"
    for step in range(2, 6):
        feed(engine, reading(step))
    events = []
    for step in range(6, 15):
        row = reading(step, "watered")
        row.moisture.calibration_id = "new-calibration"
        events += feed(engine, row)
    assert not any(e.kind == "watering" for e in events)


def test_isolated_spike_and_sustained_rise(reading):
    engine = MoodEngine(PlantProfile())
    events = []
    for step in range(30):
        value = 80 if step == 6 else 15
        events += feed(engine, reading(step, value=value))
    assert not any(e.kind == "watering" for e in events)


def test_dark_units_priority_and_leaf_confirmation(reading):
    engine = MoodEngine(DAYTIME)
    for step in range(6):
        row = reading(step, "dark")
        row.light.unit = "lux"  # a different unit than the profile's: ignored
        feed(engine, row)
    assert engine.state.mood == Mood.happy
    for step in range(6, 12):
        feed(engine, reading(step, "dark"))
    assert engine.state.mood == Mood.too_dark
    for step in range(12, 14):
        leaf = LeafObservation(
            source=Source.image_file,
            timestamp=reading(step).timestamp,
            status=Status.ok,
            yellow_proportion=0.4,
            brown_proportion=0.1,
        )
        engine.leaf(leaf, leaf.timestamp)
    assert engine.state.mood == Mood.unwell
    for step in range(14, 22):
        feed(engine, reading(step, "dry"))
    assert engine.state.mood == Mood.thirsty


def test_watering_rearms_only_after_dry_and_cooldown(reading):
    engine = MoodEngine(PlantProfile())
    events = []
    for step in range(70):
        value = 15 if step < 8 or 42 <= step < 52 else 75
        events += feed(engine, reading(step, value=value))
    assert sum(e.kind == "watering" for e in events) == 2


def test_restart_preserves_episode_and_cooldown(reading):
    engine = MoodEngine(PlantProfile())
    for step in range(12):
        feed(engine, reading(step))
    restored = MoodEngine(PlantProfile())
    restored.restore(engine.checkpoint())
    events = [e for step in range(12, 24) for e in feed(restored, reading(step))]
    assert not any(e.kind == "watering" for e in events)


def test_pulling_the_probe_out_and_back_in_is_not_watering(reading):
    from backend.sensors.calibration import Calibration

    calibration = Calibration(dry_raw=400, wet_raw=950, sensor_model="t", device_id="arduino-plant-1")

    def raw_reading(step, raw):
        row = reading(step, "dry")
        row.moisture = calibration.convert(raw)
        return row

    engine = MoodEngine(PlantProfile())
    events = [e for step in range(8) for e in feed(engine, raw_reading(step, 640))]  # moist soil, ~44%
    events += [e for step in range(8, 20) for e in feed(engine, raw_reading(step, 5))]  # probe in the air
    events += [e for step in range(20, 32) for e in feed(engine, raw_reading(step, 640))]  # pushed back in
    assert not any(e.kind == "watering" for e in events)
    assert not any(e.suggested_text == MOOD_LINES[Mood.grateful] for e in events)
    assert any(e.suggested_text == MOOD_LINES[Mood.thirsty] for e in events)  # out of the soil: thirsty
    # A real pour from dry soil is still thanked.
    events = [e for step in range(32, 44) for e in feed(engine, raw_reading(step, 420))]
    events += [e for step in range(44, 60) for e in feed(engine, raw_reading(step, 700))]
    assert sum(e.kind == "watering" for e in events) == 1
