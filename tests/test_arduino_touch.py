import json
from datetime import timedelta
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from backend.agent.touch import TouchGate
from backend.api import create_app
from backend.sensors.arduino import simulated_frames
from backend.sensors.arduino_adapter import FrameDecoder
from backend.sensors.calibration import Calibration
from shared.contracts import Source, Status, TouchObservation, utcnow


def frame(session, step=0, **changes):
    return json.dumps({**json.loads(simulated_frames(session, step)), **changes})


def touch(at, pressed, session, **changes):
    return TouchObservation(
        timestamp=at,
        source=Source.hardware,
        device_id="arduino-plant-1",
        session_id=session,
        pressed=pressed,
        status=Status.ok,
        **changes,
    )


def test_decoder_raw_calibrated_and_deduplicated():
    session, at = uuid4(), utcnow()
    decoder = FrameDecoder(session)
    sensor, pad = decoder.decode(frame(session), at)
    assert sensor.moisture.raw == 290
    assert sensor.moisture.relative_percent is None
    assert sensor.moisture.status == Status.uncalibrated
    assert sensor.light.unit == "raw"
    assert pad.pressed is False and pad.session_id == session
    assert sensor.event_id != pad.event_id
    assert decoder.decode(frame(session), at) == []
    assert decoder.decode(frame(uuid4(), 1), at) == []
    calibration = Calibration(
        dry_raw=200, wet_raw=800, sensor_model="Grove v1.4", device_id="arduino-plant-1"
    )
    calibrated = FrameDecoder(session, calibration=calibration).decode(frame(session), at)[0]
    assert calibrated.moisture.relative_percent == 15
    calibration.device_id = "another-device"
    assert (
        FrameDecoder(session, calibration=calibration).decode(frame(session), at)[0].moisture.relative_percent
        is None
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"light_raw": 1024},
        {"moisture_raw": -1},
        {"touch": 1},
        {"light_raw": None},
        {"type": "touch"},
        {"unknown": 42},
    ],
)
def test_decoder_rejects_invalid_frames(changes):
    session = uuid4()
    with pytest.raises(ValidationError):
        FrameDecoder(session).decode(frame(session, **changes))


def test_decoder_preserves_capture_age_and_clock_wrap():
    session, at = uuid4(), utcnow()
    decoder = FrameDecoder(session)
    decoder.decode(frame(session, uptime_ms=2**32 - 500), at)
    late = decoder.decode(frame(session, 1, uptime_ms=500), at + timedelta(seconds=20))
    assert late[0].timestamp == at + timedelta(seconds=1)
    with pytest.raises(ValueError, match="clock reset"):
        decoder.decode(frame(session, 2, uptime_ms=100), at)
    with pytest.raises(ValueError, match="1024"):
        decoder.decode(" " * 1025)


def test_touch_release_debounce_cooldown_reconnect_and_staleness():
    gate = TouchGate(10, 0.04, 5)
    at, session = utcnow(), uuid4()

    def observe(seconds, pressed, identity=session):
        now = at + timedelta(seconds=seconds)
        return gate.observe(touch(now, pressed, identity), now)

    assert observe(0, True) == ("accepted", False)  # Already held at connection.
    assert observe(1, False)[1] is False
    assert observe(1.01, True)[1] is False  # Electrical chatter.
    assert observe(2, False)[1] is False
    assert observe(2.1, True)[1] is True
    assert observe(3, True)[1] is False
    assert observe(4, False)[1] is False
    assert observe(5, True)[1] is False  # Cooldown.
    assert observe(6, True, uuid4())[1] is False  # Reconnect while held.
    assert observe(20, True)[1] is False  # Gap loses release continuity.
    assert observe(21, False)[1] is False
    assert observe(22, True)[1] is True
    assert observe(22, True)[0] == "out_of_order"
    assert gate.observe(touch(at, False, session), at + timedelta(seconds=30))[0] == "stale"
    restored = TouchGate(10, 0.04, 5)
    restored.restore(gate.checkpoint())
    restored.observe(touch(at + timedelta(seconds=23), False, session), at + timedelta(seconds=23))
    assert (
        restored.observe(touch(at + timedelta(seconds=24), True, session), at + timedelta(seconds=24))[1]
        is False
    )


def test_api_touch_ui_storage_and_restart(settings):
    at, session = utcnow() - timedelta(seconds=1), uuid4()
    release, press = touch(at, False, session), touch(at + timedelta(seconds=0.1), True, session)
    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/ws") as ws, client.websocket_connect("/ws") as observer:
            assert ws.receive_json()["type"] == "plant_state"
            assert observer.receive_json()["type"] == "plant_state"
            for row in (release, press):
                response = client.post("/api/v1/touch-observations", json=row.model_dump(mode="json"))
                assert response.status_code == 200
                assert ws.receive_json()["type"] == "plant_state"
                assert observer.receive_json()["type"] == "plant_state"
            request = ws.receive_json()
            assert request["type"] == "listen_request"
            assert request["duration_ms"] == 6000
            assert request["event_id"] == response.json()["events"][0]["event_id"]
            assert (
                client.post("/api/v1/touch-observations", json=press.model_dump(mode="json")).json()["status"]
                == "duplicate"
            )
            # Observer receives only state; another release acts as a queue barrier.
            end = touch(at + timedelta(seconds=0.2), False, session)
            client.post("/api/v1/touch-observations", json=end.model_dump(mode="json"))
            assert observer.receive_json()["type"] == "plant_state"
        rows = client.get("/api/v1/plants/plant-1/history").json()["items"]
        assert sum(r["record_type"] == "touch" for r in rows) == 1
    with TestClient(create_app(settings)) as client:
        assert (
            client.post("/api/v1/touch-observations", json=press.model_dump(mode="json")).json()["status"]
            == "duplicate"
        )
        rows = client.get("/api/v1/plants/plant-1/history").json()
        assert rows["storage"] == "database"
        assert sum(r["record_type"] == "touch" for r in rows["items"]) == 1
        with client.websocket_connect("/ws") as ws:
            assert ws.receive_json()["type"] == "plant_state"
            fresh = touch(utcnow(), False, uuid4())
            client.post("/api/v1/touch-observations", json=fresh.model_dump(mode="json"))
            assert ws.receive_json()["type"] == "plant_state"  # No historical listen replay.


def test_real_serial_handshake_and_partial_line_over_pseudoterminal():
    """Exercises pyserial on a local pseudo-port; never opens attached hardware."""
    pytest.importorskip("serial")
    import os
    import select
    import threading
    import time

    from backend.sensors.arduino_adapter import ArduinoSerialAdapter

    master, slave = os.openpty()
    adapter = ArduinoSerialAdapter(os.ttyname(slave))
    errors = []

    def board():
        try:
            pending = b""
            deadline = time.monotonic() + 4
            while b"\n" not in pending and time.monotonic() < deadline:
                if select.select([master], [], [], 0.1)[0]:
                    pending += os.read(master, 1024)
            command = pending.split(b"\n")[0].decode().strip()
            assert command.startswith("START ")
            from uuid import UUID

            session = UUID(command[6:])
            payload = (frame(session) + "\n").encode()
            os.write(master, payload[:20])
            time.sleep(0.15)  # Span pyserial's read timeout, keeping the partial line.
            os.write(master, payload[20:])
        except Exception as exc:
            errors.append(exc)

    thread = threading.Thread(target=board)
    thread.start()
    try:
        adapter.connect()
        sensor, pad = adapter.read_observations()
        assert sensor.source == Source.hardware and sensor.moisture.raw == 290
        assert pad.pressed is False
        disconnected = adapter.disconnected()
        assert disconnected[0].moisture.status == Status.disconnected
        assert disconnected[1].pressed is None
        assert disconnected[1].session_id == pad.session_id
    finally:
        adapter.cleanup()
        thread.join(5)
        os.close(master)
        os.close(slave)
    assert not errors
