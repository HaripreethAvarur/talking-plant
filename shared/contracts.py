"""Version 1 wire contracts; export with python -m scripts.export_contracts.

The Contract-based models are what sensors, the mood engine and the database
exchange. The models at the bottom are the WebSocket messages for the React UI;
frontend/src/contracts.ts mirrors them.
"""

import time
from datetime import datetime, timezone
from enum import Enum
from typing import Annotated, Literal, Optional
from uuid import UUID, uuid4

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
    happy = "happy"
    thirsty = "thirsty"
    soggy = "soggy"  # soil stayed very wet: too much water
    too_dark = "too_dark"  # dark during the day
    sleepy = "sleepy"  # dark at night: normal, the plant is resting
    unwell = "unwell"
    grateful = "grateful"  # a few seconds after a watering; live face only, never a log label


# Labels ASI:One may give an hour or a day. Grateful is a moment, not a state.
LOG_MOODS = (Mood.happy, Mood.thirsty, Mood.soggy, Mood.too_dark, Mood.sleepy, Mood.unwell)
DAY_MOODS = (Mood.happy, Mood.thirsty, Mood.soggy, Mood.too_dark, Mood.unwell)


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
    session_id: UUID | None = None


class SensorReading(Observation):
    source: Literal[Source.mock, Source.replay, Source.hardware]
    moisture: Moisture = Field(default_factory=Moisture)
    light: Light = Field(default_factory=Light)


class TouchObservation(Observation):
    source: Literal[Source.mock, Source.replay, Source.hardware]
    pressed: bool | None = None
    status: Status = Status.missing

    @model_validator(mode="after")
    def consistent(self):
        if (self.status == Status.ok) != (self.pressed is not None):
            raise ValueError("ok touch requires pressed; unavailable touch requires null")
        return self


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
    # Raw 0-1023 ADC counts from the Arduino light sensor (not lux).
    dark_enter: float = Field(default=200, ge=0)
    dark_exit: float = Field(default=300, ge=0)
    light_unit: Literal["lux", "raw"] = "raw"
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
    soggy_enter: Percent = 90
    soggy_exit: Percent = 80
    soggy_seconds: float = Field(default=120, ge=0, description="how long soil must stay very wet")
    night_start_hour: int = Field(default=21, ge=0, le=23, description="local time; dark is normal from here")
    night_end_hour: int = Field(default=7, ge=0, le=23)

    @model_validator(mode="after")
    def ordered(self):
        if self.dry_exit <= self.dry_enter or self.dark_exit <= self.dark_enter:
            raise ValueError("exit thresholds must exceed enter thresholds")
        if not self.dry_exit < self.soggy_exit < self.soggy_enter:
            raise ValueError("moisture bands must be ordered: dry exit < soggy exit < soggy enter")
        if self.leaf_color_exit >= self.leaf_color_enter:
            raise ValueError("leaf exit must be below enter")
        if self.watering_sustain >= self.watering_window:
            raise ValueError("watering sustain must be shorter than window")
        return self


class PlantType(str, Enum):
    """Moisture needs differ by category; per-species thresholds aren't publicly available."""

    succulent = "succulent"
    plant = "plant"
    tree = "tree"


Username = Annotated[str, Field(pattern=r"^[A-Za-z0-9_.-]{2,32}$")]


# Relative-moisture bands per plant type: (dry_enter, dry_exit, soggy_exit, soggy_enter).
TYPE_MOISTURE = {
    PlantType.succulent: (15, 22, 60, 70),
    PlantType.plant: (30, 40, 80, 90),
    PlantType.tree: (25, 35, 85, 92),
}


class PlantProfile(Contract):
    plant_id: PlantID = "plant-1"
    name: str = "Sprout"
    species: str = "pothos"
    thresholds: Thresholds = Field(default_factory=Thresholds)
    username: Username | None = None  # set when a kid registers this plant
    plant_type: PlantType = PlantType.plant
    timezone: str = "America/Detroit"

    def for_registration(self, registration: "PlantRegistration") -> "PlantProfile":
        """This profile adopted by a registered plant: its name, type and moisture bands."""
        dry_enter, dry_exit, soggy_exit, soggy_enter = TYPE_MOISTURE[registration.plant_type]
        thresholds = self.thresholds.model_copy(
            update=dict(
                dry_enter=dry_enter, dry_exit=dry_exit, soggy_exit=soggy_exit, soggy_enter=soggy_enter
            )
        )
        return self.model_copy(
            update=dict(
                name=registration.plant_name,
                species=registration.plant_type.value,
                plant_type=registration.plant_type,
                username=registration.username,
                thresholds=Thresholds.model_validate(thresholds.model_dump()),
            )
        )


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
    touch: TouchObservation | None = None
    last_event_id: UUID | None = None


class PlantEvent(Contract):
    event_id: UUID = Field(default_factory=uuid4)
    plant_id: PlantID
    timestamp: AwareDatetime
    source: Source
    kind: Literal["mood_changed", "watering", "sensor_health", "touch"]
    mood: Mood
    reason: str
    suggested_text: str | None = None
    observation_id: UUID | None = None


class ConversationContext(Contract):
    plant_id: PlantID
    timestamp: AwareDatetime = Field(default_factory=utcnow)
    source: Source = Source.backend
    profile: PlantProfile
    state: PlantState
    recent_events: list[PlantEvent]
    hourly: list["HourlyReading"] = Field(default_factory=list, description="care log, oldest first")
    guidance: str = "Use event_id to deduplicate speech. Observations are not diagnoses."


class StreamMessage(Contract):
    type: Literal["snapshot", "update"]
    state: PlantState
    events: list[PlantEvent] = Field(default_factory=list)


# ===================================================================
# Kid's plant, hourly care log (rolling 30 days) and weekly leaderboard
# ===================================================================


class PlantRegistration(Contract):
    """One row per kid and plant. No login: the username is the identity."""

    username: Username
    plant_name: str = Field(min_length=1, max_length=40)
    plant_type: PlantType
    location: str = Field(pattern=r"^\d{5}$", description="US ZIP code, used for local air quality")
    created_at: AwareDatetime = Field(default_factory=utcnow)


class HourlyReading(Contract):
    """One row per plant per logging interval (an hour normally; a minute in demos).
    `hour` is the interval's start. mood is ASI's label for it; day_mood is set only on
    the last row of each day, by the nightly job, and feeds the leaderboard."""

    username: Username
    hour: AwareDatetime
    sun_pct: Percent | None = None
    water_pct: Percent | None = None
    air_aqi: Annotated[float, Field(ge=0)] | None = None
    health: str | None = Field(default=None, max_length=1000, description="Ollama's description of the photo")
    mood: Mood | None = None
    day_mood: Mood | None = None

    @field_validator("hour")
    @classmethod
    def whole_minute(cls, value):
        return value.astimezone(timezone.utc).replace(second=0, microsecond=0)


class LeaderboardEntry(Contract):
    rank: int = Field(ge=1)
    username: Username
    plant_name: str
    plant_type: PlantType
    location: str
    happy_days: int = Field(ge=0, le=7)
    score: Proportion = Field(description="happy_days / 7 over the last 7 days")


# ===================================================================
# UI WebSocket messages (backend/ui.py <-> frontend/src/contracts.ts)
# ===================================================================


class UIPlantState(BaseModel):
    """What the plant's face, gauges and speech bubble show; also the input to replies."""

    type: Literal["plant_state"] = "plant_state"
    mood: Mood
    message: Optional[str] = None
    moisture_pct: Optional[float] = None
    light_pct: Optional[float] = None
    # None: the camera has no recent look at the leaves. []: it looked and saw nothing wrong.
    leaf_issues: list[str] | None = None
    looks: str | None = None  # the vision model's latest description, if under 2 hours old
    ts: float = Field(default_factory=now)
    sensor_health: Status = Status.missing
    light_unit: Literal["lux", "raw"] | None = None
    light_value: float | None = None


class ListenRequest(Contract):
    type: Literal["listen_request"] = "listen_request"
    event_id: UUID
    plant_id: PlantID
    timestamp: AwareDatetime
    duration_ms: int = Field(default=6000, ge=1000, le=15000)


class ChildUtterance(BaseModel):
    """A child's question from the UI: transcribed speech or a tapped question button."""

    type: Literal["child_utterance"] = "child_utterance"
    text: str
    source: Literal["stt", "button", "typed"] = "stt"
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


ConversationContext.model_rebuild()
