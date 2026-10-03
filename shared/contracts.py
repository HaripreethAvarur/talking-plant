"""Message contracts shared by every module (Task 0).

Every message is a pydantic model that serialises to JSON with a "type" field,
so the WebSocket between the backend and the React UI can route on it.
The TypeScript mirror lives in frontend/src/contracts.ts; keep them in sync.
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field


def now() -> float:
    return time.time()


class Mood(str, Enum):
    HAPPY = "happy"
    THIRSTY = "thirsty"
    TOO_DARK = "too_dark"
    UNWELL = "unwell"
    GRATEFUL = "grateful"


class SensorReading(BaseModel):
    """Published by the sensor reader (Task 1) about once a second."""

    type: Literal["sensor_reading"] = "sensor_reading"
    moisture_pct: float = Field(ge=0, le=100)
    light_pct: float = Field(ge=0, le=100)
    watered: bool = False  # True on the reading where a watering event was detected
    board_connected: bool = True
    ts: float = Field(default_factory=now)


class LeafObservation(BaseModel):
    """Published by the leaf checker (Task 2). Only problems above threshold are listed."""

    type: Literal["leaf_observation"] = "leaf_observation"
    issues: list[Literal["yellowing", "browning", "wilting"]] = []
    confidence: float = Field(default=0.0, ge=0, le=1)
    ts: float = Field(default_factory=now)


class ChildUtterance(BaseModel):
    """Published by speech-to-text (Task 3) or by an on-screen question button."""

    type: Literal["child_utterance"] = "child_utterance"
    text: str
    source: Literal["stt", "button", "typed"] = "stt"
    ts: float = Field(default_factory=now)


class PlantState(BaseModel):
    """Published by the Plant Care Agent (Task 4); drives the UI face and gauges."""

    type: Literal["plant_state"] = "plant_state"
    mood: Mood
    message: Optional[str] = None  # the line the plant is saying, if any
    moisture_pct: Optional[float] = None
    light_pct: Optional[float] = None
    leaf_issues: list[str] = []
    ts: float = Field(default_factory=now)


class SpeechAudio(BaseModel):
    """Produced by the plant voice (Task 7) and played by the UI (Task 8).

    audio_url is None when TTS is unavailable and the line is not cached;
    the UI then falls back to the browser's built-in speech synthesis.
    """

    type: Literal["speech_audio"] = "speech_audio"
    text: str
    audio_url: Optional[str] = None
    mime: str = "audio/mpeg"
    cached: bool = False
    ts: float = Field(default_factory=now)
