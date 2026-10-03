import asyncio
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from starlette.websockets import WebSocketDisconnect

from backend import config
from backend.api import create_app
from backend.sensors.arduino import simulated_frames
from backend.sensors.arduino_adapter import FrameDecoder
from backend.speech import tts
from backend.ui import UIHub
from shared.contracts import SpeechAudio


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(config, "ELEVENLABS_API_KEY", "")
    monkeypatch.setattr(config, "ASI_API_KEY", "")


async def silent_speech(text):
    return SpeechAudio(text=text)


def test_sensor_updates_reach_existing_ui_and_questions_use_live_state(settings, monkeypatch):
    monkeypatch.setattr(tts, "synthesize", silent_speech)
    with TestClient(create_app(settings)) as client:
        with client.websocket_connect("/ws") as ws:
            initial = ws.receive_json()
            assert initial["moisture_pct"] is None
            session = uuid4()
            sensor = FrameDecoder(session).decode(simulated_frames(session, 0))[0]
            client.post("/api/v1/sensor-readings", json=sensor.model_dump(mode="json"))
            update = ws.receive_json()
            assert update["sensor_health"] == "uncalibrated"
            assert update["light_pct"] == pytest.approx(100 * 600 / 1023)
            assert update["light_value"] == 600 and update["light_unit"] == "raw"
            assert update["moisture_pct"] is None
            ws.send_json({"type": "child_utterance", "text": "Do you need water?", "source": "button"})
            assert "calibration" in ws.receive_json()["message"]
            assert ws.receive_json()["type"] == "speech_audio"
            ws.send_json({"type": "child_utterance", "text": "Are your leaves okay?", "source": "button"})
            assert "camera" in ws.receive_json()["message"]
            assert ws.receive_json()["type"] == "speech_audio"
        assert client.post("/api/plant-state", json={"mood": "happy"}).status_code == 404
        assert (
            client.post("/api/stt", content=b"clip", headers={"Content-Type": "audio/webm"}).status_code
            == 503
        )


def test_ui_authentication(settings):
    settings.ingestion_token, settings.viewer_token = SecretStr("write"), SecretStr("read")
    with TestClient(create_app(settings)) as client:
        for path in ("/api/health",):
            assert client.get(path).status_code == 401
        assert client.post("/api/stt", content=b"clip").status_code == 401
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": "wrong"})
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "token": "read"})
            assert ws.receive_json()["type"] == "plant_state"
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws", headers={"Origin": "https://unknown.example"}):
                pass


async def test_speech_failure_does_not_kill_worker(settings, monkeypatch):
    from backend.service import PlantService

    calls = []

    async def flaky(text):
        calls.append(text)
        if len(calls) == 1:
            raise OSError("speaker unavailable")
        return SpeechAudio(text=text)

    monkeypatch.setattr(tts, "synthesize", flaky)
    service = PlantService(settings)
    hub = UIHub(service, settings)
    output = asyncio.Queue()
    hub.clients[object()] = output
    await hub.start()
    try:
        hub.say("one")
        hub.say("two")
        assert (await asyncio.wait_for(output.get(), 1))["text"] == "two"
    finally:
        await hub.close()
        service.store.close()
