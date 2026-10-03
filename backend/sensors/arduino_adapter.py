"""USB reader for the live M1 hub, with an explicit option for the older session protocol."""

import json
import time
from datetime import timedelta
from typing import Literal
from uuid import UUID, uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from shared.contracts import Light, Moisture, Mood, SensorReading, Source, Status, TouchObservation, utcnow


class HubFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    moisture_raw: int = Field(ge=0, le=1023)
    light_raw: int = Field(ge=0, le=1023)
    touch: int = Field(ge=0, le=1)


class HubFrameDecoder:
    """M1 has no clock/sequence/identity: receipt time and session IDs come from this host."""

    def __init__(self, session_id, plant_id="plant-1", calibration=None, source=Source.hardware):
        self.session_id, self.plant_id = session_id, plant_id
        self.calibration, self.source = calibration, source
        self.device_id = "arduino-plant-1"
        self.sequence = 0

    def decode(self, line, received_at=None):
        if len(line) > 1024:
            raise ValueError("Arduino frame exceeds 1024 bytes")
        frame = HubFrame.model_validate_json(line)
        common = dict(
            plant_id=self.plant_id,
            source=self.source,
            device_id=self.device_id,
            session_id=self.session_id,
            timestamp=received_at or utcnow(),
        )
        calibration = self.calibration
        moisture = (
            calibration.convert(frame.moisture_raw)
            if calibration and calibration.device_id == self.device_id
            else Moisture(raw=frame.moisture_raw, status=Status.uncalibrated)
        )
        observations = [
            SensorReading(
                **common,
                event_id=uuid5(self.session_id, f"sensor:{self.sequence}"),
                moisture=moisture,
                light=Light(value=frame.light_raw, unit="raw", status=Status.ok),
            ),
            TouchObservation(
                **common,
                event_id=uuid5(self.session_id, f"touch:{self.sequence}"),
                pressed=bool(frame.touch),
                status=Status.ok,
            ),
        ]
        self.sequence += 1
        return observations


class ArduinoFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    protocol: Literal["talking-plant/1"]
    type: Literal["sensor", "touch"]
    device_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    session_id: UUID
    sequence: int = Field(ge=0, le=0xFFFFFFFF)
    uptime_ms: int = Field(ge=0, le=0xFFFFFFFF)
    moisture_raw: int | None = Field(default=None, ge=0, le=1023)
    light_raw: int | None = Field(default=None, ge=0, le=1023)
    touch: bool

    @model_validator(mode="after")
    def readings(self):
        if self.type == "sensor" and (self.moisture_raw is None or self.light_raw is None):
            raise ValueError("sensor frames require both ADC values")
        if self.type == "touch" and (self.moisture_raw is not None or self.light_raw is not None):
            raise ValueError("touch frames must not include ADC values")
        return self


class FrameDecoder:
    def __init__(self, session_id, plant_id="plant-1", calibration=None, source=Source.hardware):
        self.session_id, self.plant_id, self.calibration, self.source = (
            session_id,
            plant_id,
            calibration,
            source,
        )
        self.sequence = -1
        self.uptime = None
        self.timestamp = None
        self.device_id = None

    def decode(self, line, received_at=None):
        if len(line) > 1024:
            raise ValueError("Arduino frame exceeds 1024 bytes")
        frame = ArduinoFrame.model_validate_json(line)
        if frame.session_id != self.session_id:
            return []  # Old buffered session, never fresh evidence.
        if frame.sequence <= self.sequence:
            return []
        if self.device_id and self.device_id != frame.device_id:
            raise ValueError("Device identity changed within a session")
        at = received_at or utcnow()
        if self.uptime is not None:
            elapsed = (frame.uptime_ms - self.uptime) % (2**32)
            if elapsed > 2**31:
                raise ValueError("Board clock reset; reconnect for a new session")
            at = self.timestamp + timedelta(milliseconds=elapsed)
        self.sequence, self.uptime, self.timestamp = frame.sequence, frame.uptime_ms, at
        self.device_id = frame.device_id
        common = dict(
            plant_id=self.plant_id,
            source=self.source,
            device_id=frame.device_id,
            session_id=self.session_id,
            timestamp=at,
        )
        observations = []
        if frame.type == "sensor":
            calibration = self.calibration
            moisture = (
                calibration.convert(frame.moisture_raw)
                if calibration and calibration.device_id == frame.device_id
                else Moisture(raw=frame.moisture_raw, status=Status.uncalibrated)
            )
            observations.append(
                SensorReading(
                    **common,
                    event_id=uuid5(self.session_id, f"sensor:{frame.sequence}"),
                    moisture=moisture,
                    light=Light(value=frame.light_raw, unit="raw", status=Status.ok),
                )
            )
        observations.append(
            TouchObservation(
                **common,
                event_id=uuid5(self.session_id, f"touch:{frame.sequence}"),
                status=Status.ok,
                pressed=frame.touch,
            )
        )
        return observations


class ArduinoSerialAdapter:
    def __init__(self, port, plant_id="plant-1", calibration=None, baud=115200, timeout=5, protocol="hub"):
        if protocol not in ("hub", "session-v1"):
            raise ValueError("Arduino protocol must be hub or session-v1")
        self.protocol = protocol
        self.last_mood = None
        self.port, self.plant_id, self.calibration = port, plant_id, calibration
        self.baud, self.timeout = baud, timeout
        self.serial = None
        self.decoder = None
        self.buffer = b""
        self.last_valid = 0
        self.pending = []

    @staticmethod
    def candidates():
        try:
            from serial.tools import list_ports
        except ImportError:
            raise RuntimeError("Run make install-arduino in the native laptop environment.") from None
        return [
            {
                "port": p.device,
                "description": p.description,
                "serial_number": p.serial_number,
                "vid": p.vid,
                "pid": p.pid,
            }
            for p in list_ports.comports()
        ]

    def connect(self):
        if not self.port:
            raise RuntimeError("Set ARDUINO_PORT or --port using make arduino-devices.")
        try:
            import serial
        except ImportError:
            raise RuntimeError("Run make install-arduino in the native laptop environment.") from None
        self.cleanup()
        session = uuid4()
        decoder = HubFrameDecoder if self.protocol == "hub" else FrameDecoder
        self.decoder = decoder(session, self.plant_id, self.calibration)
        self.serial = serial.Serial(self.port, self.baud, timeout=0.1, write_timeout=1, exclusive=True)
        self.serial.reset_input_buffer()
        self.buffer = b""
        self.last_valid = time.monotonic()
        deadline, next_start = self.last_valid + 8, 0
        try:
            while time.monotonic() < deadline:
                if self.protocol == "session-v1" and time.monotonic() >= next_start:
                    self.serial.write(f"START {session}\n".encode("ascii"))
                    next_start = time.monotonic() + 0.5
                observations = self._read()
                if observations:
                    self.pending = observations
                    return
            raise OSError(f"No valid {self.protocol} frames. Check port/protocol and close Serial Monitor.")
        except Exception:
            self.cleanup()
            raise

    def _read(self):
        self.buffer += self.serial.read_until(b"\n", size=1025)
        if len(self.buffer) > 1024:
            self.buffer = b""
            raise ValueError("Oversized Arduino line; expected a JSON sensor frame")
        if not self.buffer.endswith(b"\n"):
            return []
        line, self.buffer = self.buffer, b""
        try:
            observations = self.decoder.decode(line)
        except ValidationError:
            if self.protocol != "hub":
                raise
            # Ignore boot banners/malformed rows, but never refresh the valid-frame timeout.
            return []
        if observations:
            self.last_valid = time.monotonic()
        return observations

    def write_mood(self, mood, text=""):
        mood = Mood(mood).value
        if self.protocol != "hub" or mood == self.last_mood:
            return
        if self.serial is None:
            raise OSError("Arduino is disconnected")
        payload = (json.dumps({"mood": mood, "text": text[:160]}, ensure_ascii=True) + "\n").encode("ascii")
        if self.serial.write(payload) != len(payload):
            raise OSError("Incomplete Arduino mood command")
        self.last_mood = mood

    def read_observations(self):
        if self.pending:
            result, self.pending = self.pending, []
            return result
        if self.serial is None:
            raise OSError("Arduino is disconnected")
        observations = self._read()
        if time.monotonic() - self.last_valid > self.timeout:
            raise OSError("No valid Arduino frames within timeout; reconnecting")
        return observations

    def disconnected(self):
        common = dict(
            plant_id=self.plant_id,
            source=Source.hardware,
            device_id=(self.decoder.device_id or "arduino-plant-1") if self.decoder else "arduino-plant-1",
            session_id=self.decoder.session_id if self.decoder else None,
        )
        return [
            SensorReading(
                **common,
                moisture=Moisture(status=Status.disconnected),
                light=Light(status=Status.disconnected),
            ),
            TouchObservation(**common, status=Status.disconnected),
        ]

    def cleanup(self):
        serial, self.serial = self.serial, None
        self.pending = []
        self.last_mood = None
        if serial:
            serial.close()
