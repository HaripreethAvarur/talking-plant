"""Regenerate checked-in JSON schemas, sample messages, profile and timestamped fixture."""

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

from backend.conversation.scripted import MOOD_LINES
from backend.sensors.simulator import scenario_reading
from shared.contracts import (
    ChildUtterance,
    ConversationContext,
    LeafObservation,
    ListenRequest,
    Mood,
    PlantEvent,
    PlantProfile,
    PlantState,
    Source,
    SpeechAudio,
    Status,
    StreamMessage,
    TouchObservation,
    UIPlantState,
)


def main():
    root = Path("shared")
    for directory in ("schemas", "samples", "fixtures"):
        (root / directory).mkdir(exist_ok=True)
    at = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
    profile = PlantProfile()
    sensor = scenario_reading("dry", 0, timestamp=at)
    sensor.event_id = UUID(int=1)
    state = PlantState(
        plant_id="plant-1",
        timestamp=at,
        mood=Mood.thirsty,
        sensor_health=Status.ok,
        moisture=sensor.moisture,
        light=sensor.light,
        last_sensor_at=at,
        reason="Persistent dry soil.",
        smoothed_moisture_percent=15,
    )
    event = PlantEvent(
        event_id=UUID(int=2),
        plant_id="plant-1",
        timestamp=at,
        source=Source.mock,
        kind="mood_changed",
        mood=Mood.thirsty,
        reason="Persistent dry soil.",
        suggested_text=MOOD_LINES[Mood.thirsty],
        observation_id=sensor.event_id,
    )
    leaf = LeafObservation(
        event_id=UUID(int=3),
        plant_id="plant-1",
        timestamp=at,
        source=Source.image_file,
        status=Status.ok,
        yellow_proportion=0.1,
        brown_proportion=0.02,
        region=(0, 0, 100, 100),
    )
    ts = at.timestamp()
    utterance = ChildUtterance(text="Do you need water?", source="button", ts=ts)
    context = ConversationContext(
        plant_id="plant-1", timestamp=at, profile=profile, state=state, recent_events=[event]
    )
    samples = [
        sensor,
        leaf,
        state,
        event,
        utterance,
        context,
        StreamMessage(type="snapshot", state=state),
        profile,
        TouchObservation(
            event_id=UUID(int=6),
            plant_id="plant-1",
            timestamp=at,
            source=Source.mock,
            pressed=True,
            status=Status.ok,
            device_id="arduino-plant-1",
            session_id=UUID(int=7),
        ),
        ListenRequest(event_id=UUID(int=8), plant_id="plant-1", timestamp=at),
        UIPlantState(
            mood=Mood.thirsty,
            message=MOOD_LINES[Mood.thirsty],
            moisture_pct=15,
            light_pct=58.7,
            leaf_issues=[],
            sensor_health=Status.ok,
            light_unit="raw",
            light_value=600,
            ts=ts,
        ),
        SpeechAudio(text=MOOD_LINES[Mood.thirsty], audio_url="/audio/0123456789abcdef01234567.mp3", ts=ts),
    ]
    for obj in samples:
        name = type(obj).__name__
        (root / "schemas" / f"{name}.schema.json").write_text(
            json.dumps(type(obj).model_json_schema(), indent=2) + "\n"
        )
        (root / "samples" / f"{name}.json").write_text(obj.model_dump_json(indent=2) + "\n")
    watering = event.model_copy(
        update={
            "event_id": UUID(int=5),
            "kind": "watering",
            "mood": Mood.grateful,
            "reason": "Sustained moisture rise indicates watering.",
            "suggested_text": MOOD_LINES[Mood.grateful],
        }
    )
    (root / "samples" / "WateringEvent.json").write_text(watering.model_dump_json(indent=2) + "\n")
    update = StreamMessage(type="update", state=state, events=[event])
    (root / "samples" / "StreamUpdate.json").write_text(update.model_dump_json(indent=2) + "\n")
    if not (root / "plant-profile.json").exists():
        (root / "plant-profile.json").write_text(profile.model_dump_json(indent=2) + "\n")
    rows = []
    for step in range(24):
        reading = scenario_reading("dry-to-watered", step, timestamp=at + timedelta(seconds=step))
        reading.source = Source.replay
        reading.event_id = UUID(int=100 + step)
        rows.append(reading.model_dump_json())
    (root / "fixtures" / "dry-to-watered.jsonl").write_text("\n".join(rows) + "\n")


if __name__ == "__main__":
    main()
