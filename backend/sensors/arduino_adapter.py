"""USB reader for hardware/talking_plant_hub: one JSON line per second, plus a mood line back."""

import json
import time
from uuid import uuid4, uuid5

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from shared.contracts import Light, Moisture, Mood, SensorReading, Source, Status, TouchObservation, utcnow

DEVICE_ID = "arduino-plant-1"
MAX_LINE_BYTES = 1024


class HubFrame(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    moisture_raw: int = Field(ge=0, le=1023)
    light_raw: int = Field(ge=0, le=1023)
    touch: int = Field(ge=0, le=1)


class HubFrameDecoder:
    """The hub sends no clock, sequence or identity: receipt time and session IDs come from this host."""

    def __init__(self, session_id, plant_id="plant-1", calibration=None, source=Source.hardware):
        self.session_id, self.plant_id = session_id, plant_id
        self.calibration, self.source = calibration, source
        self.device_id = DEVICE_ID
        self.sequence = 0

    def decode(self, line, received_at=None):
        if len(line) > MAX_LINE_BYTES:
            raise ValueError(f"Arduino frame exceeds {MAX_LINE_BYTES} bytes")
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


class ArduinoSerialAdapter:
    def __init__(self, port, plant_id="plant-1", calibration=None, baud=115200, timeout=5):
        self.port, self.plant_id, self.calibration = port, plant_id, calibration
        self.baud, self.timeout = baud, timeout
        self.serial = None
        self.decoder = None
        self.buffer = b""
        self.last_valid = 0
        self.last_mood = None
        self.pending = []

    @staticmethod
    def candidates():
        try:
            from serial.tools import list_ports
        except ImportError:
            raise RuntimeError("Install requirements-arduino.txt in the laptop environment.") from None
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
            raise RuntimeError(
                "Set ARDUINO_PORT or --port (list ports with python -m backend.sensors.arduino)."
            )
        try:
            import serial
        except ImportError:
            raise RuntimeError("Install requirements-arduino.txt in the laptop environment.") from None
        self.cleanup()
        self.decoder = HubFrameDecoder(uuid4(), self.plant_id, self.calibration)
        self.serial = serial.Serial(self.port, self.baud, timeout=0.1, write_timeout=1, exclusive=True)
        self.serial.reset_input_buffer()
        self.buffer = b""
        self.last_valid = time.monotonic()
        deadline = self.last_valid + 8
        try:
            while time.monotonic() < deadline:
                observations = self._read()
                if observations:
                    self.pending = observations
                    return
            raise OSError("No valid frames. Check the port and close the Arduino Serial Monitor.")
        except Exception:
            self.cleanup()
            raise

    def _read(self):
        self.buffer += self.serial.read_until(b"\n", size=MAX_LINE_BYTES + 1)
        if len(self.buffer) > MAX_LINE_BYTES:
            self.buffer = b""
            raise ValueError("Oversized Arduino line; expected a JSON sensor frame")
        if not self.buffer.endswith(b"\n"):
            return []
        line, self.buffer = self.buffer, b""
        try:
            observations = self.decoder.decode(line)
        except ValidationError:
            # Ignore boot banners/malformed rows, but never refresh the valid-frame timeout.
            return []
        if observations:
            self.last_valid = time.monotonic()
        return observations

    def write_mood(self, mood, text=""):
        """Tell the hub the mood; its LED lights for unhappy moods."""
        mood = Mood(mood).value
        if mood == self.last_mood:
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
            device_id=DEVICE_ID,
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
