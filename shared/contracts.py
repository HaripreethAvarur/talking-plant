"""Version 1 wire contracts; export with python -m scripts.export_contracts.

The detailed models (Contract-based) are the canonical backend representations.
The simpler UI models at the bottom are used by the WebSocket server and
conversation modules to communicate with the React frontend.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal, Optional
from uuid import UUID, uuid4

import time

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def now() -> float:
    return time.time()


# ===================================================================
# Core backend contracts
# ===================================================================

class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: Literal["1.0"] = "1.0"

    @field_validator("timestamp", "last_sensor_at", check_fields=False)
    @classmethod
    def normalize_timestamp(cls, value):
        return value.astimezone(timezone.utc) if value is not None else None


class Source(str, Enum):
    mock = "mock"
    replay = "replay"
    hardware = "hardware"
    image_file = "image_file"
    backend = "backend"


class Status(str, Enum):
    ok = "ok"
    missing = "missing"
    disconnected = "disconnected"
    stale = "stale"
    error = "error"
    uncalibrated = "uncalibrated"


class Mood(str, Enum):
    HAPPY = "happy"
    THIRSTY = "thirsty"
    TOO_DARK = "too_dark"
    UNWELL = "unwell"
    GRATEFUL = "grateful"
    # lowercase aliases for backend code
    happy = "happy"
    thirsty = "thirsty"
    too_dark = "too_dark"
    unwell = "unwell"
    grateful = "grateful"


Percent = Annotated[float, Field(ge=0, le=100)]
Proportion = Annotated[float, Field(ge=0, le=1)]
PlantID = Annotated[str, Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")]


class Moisture(Contract):
    raw: float | None = None
    relative_percent: Percent | None = None
    status: Status = Status.missing
    calibration_id: str | None = None

    @model_validator(mode="after")
    def consistent(self):
        if self.status == Status.ok and (
            self.raw is None or self.relative_percent is None or not self.calibration_id
        ):
            raise ValueError("ok moisture requires raw, relative_percent, calibration_id")
        if self.status == Status.uncalibrated:
            if self.raw is None or self.relative_percent is not None:
                raise ValueError("uncalibrated requires raw and null relative_percent")
        elif self.status != Status.ok and (self.raw is not None or self.relative_percent is not None):
            raise ValueError("unavailable moisture values must be null")
        return self


class Light(Contract):
    value: Annotated[float, Field(ge=0)] | None = None
    unit: Literal["lux", "raw"] | None = None
    status: Status = Status.missing

    @model_validator(mode="after")
    def consistent(self):
        if self.status == Status.ok and (self.value is None or self.unit is None):
            raise ValueError("ok light requires value and unit")
        if self.status != Status.ok and self.value is not None:
            raise ValueError("unavailable light must be null")
        return self


class Observation(Contract):
    event_id: UUID = Field(default_factory=uuid4)
    plant_id: PlantID = "plant-1"
    timestamp: AwareDatetime = Field(default_factory=utcnow)
    source: Source
    device_id: str = Field(default="simulator", min_length=1, max_length=128)


class SensorReading(Observation):
    source: Literal[Source.mock, Source.replay, Source.hardware]
    moisture: Moisture = Field(default_factory=Moisture)
    light: Light = Field(default_factory=Light)


class LeafObservation(Observation):
    source: Literal[Source.mock, Source.replay, Source.hardware, Source.image_file]
    status: Status
    yellow_proportion: Proportion | None = None
    brown_proportion: Proportion | None = None
    method: str = "hsv-color-v1"
    region: tuple[int, int, int, int] | None = None
    note: str = Field(default="Color observation only; not a diagnosis or probability.", max_length=1000)

    @model_validator(mode="after")
    def consistent(self):
        values = (self.yellow_proportion, self.brown_proportion)
        if self.status == Status.ok and any(v is None for v in values):
            raise ValueError("ok leaf observation requires both proportions")
        if self.status != Status.ok and any(v is not None for v in values):
            raise ValueError("unavailable proportions must be null")
        if all(v is not None for v in values) and sum(values) > 1.000001:
            raise ValueError("nonoverlapping color proportions cannot sum above 1")
        return self


class Thresholds(Contract):
    dry_enter: Percent = 30
    dry_exit: Percent = 40
    dry_seconds: float = Field(default=3, ge=0)
    dark_enter: float = Field(default=100, ge=0)
    dark_exit: float = Field(default=150, ge=0)
    light_unit: Literal["lux", "raw"] = "lux"
    dark_seconds: float = Field(default=3, ge=0)
    watering_rise: float = Field(default=20, gt=0, le=100)
    watering_window: float = Field(default=30, gt=0)
    watering_sustain: float = Field(default=2, ge=0)
    watering_cooldown: float = Field(default=30, ge=0)
    grateful_seconds: float = Field(default=5, gt=0)
    speech_cooldown: float = Field(default=30, ge=0)
    stale_seconds: float = Field(default=5, gt=0)
    smoothing_samples: int = Field(default=3, ge=1, le=60)
    leaf_color_enter: Proportion = 0.35
    leaf_color_exit: Proportion = 0.25
    leaf_confirmations: int = Field(default=2, ge=1)
    leaf_stale_seconds: float = Field(default=300, gt=0)

    @model_validator(mode="after")
    def ordered(self):
        if self.dry_exit <= self.dry_enter or self.dark_exit <= self.dark_enter:
            raise ValueError("exit thresholds must exceed enter thresholds")
        if self.leaf_color_exit >= self.leaf_color_enter:
            raise ValueError("leaf exit must be below enter")
        if self.watering_sustain >= self.watering_window:
            raise ValueError("watering sustain must be shorter than window")
        return self


class PlantProfile(Contract):
    plant_id: PlantID = "plant-1"
    name: str = "Sprout"
    species: str = "Unspecified demo plant"
    thresholds: Thresholds = Field(default_factory=Thresholds)


class PlantState(Contract):
    plant_id: PlantID
    timestamp: AwareDatetime = Field(default_factory=utcnow)
    source: Source = Source.backend
    mood: Mood = Mood.happy
    reason: str = "Waiting for observations; happy is a neutral display default."
    sensor_health: Status = Status.missing
    moisture: Moisture = Field(default_factory=Moisture)
    light: Light = Field(default_factory=Light)
    smoothed_moisture_percent: Percent | None = None
    last_sensor_at: AwareDatetime | None = None
    leaf: LeafObservation | None = None
    last_event_id: UUID | None = None


class PlantEvent(Contract):
    event_id: UUID = Field(default_factory=uuid4)
    plant_id: PlantID
    timestamp: AwareDatetime
    source: Source
    kind: Literal["mood_changed", "watering", "sensor_health"]
    mood: Mood
    reason: str
    suggested_text: str | None = None
    observation_id: UUID | None = None


class ChildUtterance(Observation):
    source: Literal[Source.hardware, Source.mock, Source.replay]
    text: str = Field(min_length=1, max_length=4000)
    language: str = "en"


class ConversationContext(Contract):
    plant_id: PlantID
    timestamp: AwareDatetime = Field(default_factory=utcnow)
    source: Source = Source.backend
    profile: PlantProfile
    state: PlantState
    recent_events: list[PlantEvent]
    guidance: str = (
        "Use event_id to deduplicate speech. Observations are not diagnoses. Person 2 owns final wording."
    )


class StreamMessage(Contract):
    type: Literal["snapshot", "update"]
    state: PlantState
    events: list[PlantEvent] = Field(default_factory=list)


# ===================================================================
# UI-facing contracts (used by WebSocket server, conversation, speech)
# ===================================================================

class UIPlantState(BaseModel):
    """Simplified plant state sent over WebSocket to the React UI."""
    type: Literal["plant_state"] = "plant_state"
    mood: Mood
    message: Optional[str] = None
    moisture_pct: Optional[float] = None
    light_pct: Optional[float] = None
    leaf_issues: list[str] = []
    ts: float = Field(default_factory=now)


class UIChildUtterance(BaseModel):
    """Simplified utterance from the UI (speech-to-text or button)."""
    type: Literal["child_utterance"] = "child_utterance"
    text: str
    source: Literal["stt", "button", "typed"] = "stt"
    ts: float = Field(default_factory=now)


class UISensorReading(BaseModel):
    """Simplified sensor reading for the UI."""
    type: Literal["sensor_reading"] = "sensor_reading"
    moisture_pct: float = Field(ge=0, le=100)
    light_pct: float = Field(ge=0, le=100)
    watered: bool = False
    board_connected: bool = True
    ts: float = Field(default_factory=now)


class UILeafObservation(BaseModel):
    """Simplified leaf observation for the UI."""
    type: Literal["leaf_observation"] = "leaf_observation"
    issues: list[Literal["yellowing", "browning", "wilting"]] = []
    confidence: float = Field(default=0.0, ge=0, le=1)
    ts: float = Field(default_factory=now)


class SpeechAudio(BaseModel):
    """Produced by the plant voice (TTS) and played by the UI.

    audio_url is None when TTS is unavailable and the line is not cached;
    the UI then falls back to the browser's built-in speech synthesis.
    """
    type: Literal["speech_audio"] = "speech_audio"
    text: str
    audio_url: Optional[str] = None
    mime: str = "audio/mpeg"
    cached: bool = False
    ts: float = Field(default_factory=now)
