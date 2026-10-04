from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from starlette.websockets import WebSocketDisconnect

from backend.api import create_app
from backend.config import Settings
from backend.conversation.scripted import MOOD_LINES
from shared.contracts import LeafObservation, Mood, Source, Status, utcnow


def test_live_contract_websocket_and_retry(settings, reading):
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        with client.websocket_connect("/ws/plants/plant-1") as ws:
            assert ws.receive_json()["type"] == "snapshot"
            events = []
            for step in range(24):
                row = reading(step)
                response = client.post("/api/v1/sensor-readings", json=row.model_dump(mode="json"))
                assert response.status_code == 200
                assert response.json()["status"] == "accepted"
                message = ws.receive_json()
                assert message["type"] == "update"
                events += message["events"]
                retry = client.post("/api/v1/sensor-readings", json=row.model_dump(mode="json"))
                assert retry.json()["status"] == "duplicate"
                assert retry.json()["events"] == []
            assert [e["suggested_text"] for e in events if e["suggested_text"]] == [
                MOOD_LINES[Mood.thirsty],
                MOOD_LINES[Mood.grateful],
            ]
        context = client.get("/api/v1/plants/plant-1/context").json()
        assert context["profile"]["name"] == "Sprout"
        assert client.get("/api/v1/plants/unknown/state").status_code == 404
        assert client.post("/api/v1/demo/scenario", json={"scenario": "dry"}).status_code == 404


def test_validation_and_future_skew(settings, reading):
    with TestClient(create_app(settings)) as client:
        row = reading(0).model_dump(mode="json")
        row["moisture"]["status"] = "disconnected"
        assert client.post("/api/v1/sensor-readings", json=row).status_code == 422
        row = reading(0).model_dump(mode="json")
        row["timestamp"] = "2026-01-01T12:00:00"
        assert client.post("/api/v1/sensor-readings", json=row).status_code == 422
        row["timestamp"] = (utcnow() + timedelta(days=1)).isoformat()
        assert client.post("/api/v1/sensor-readings", json=row).status_code == 422


def test_auth_and_origin(settings, reading):
    settings = settings.model_copy(
        update={
            "ingestion_token": Settings(ingestion_token="write", _env_file=None).ingestion_token,
            "viewer_token": Settings(viewer_token="read", _env_file=None).viewer_token,
        }
    )
    with TestClient(create_app(settings)) as client:
        assert (
            client.post("/api/v1/sensor-readings", json=reading(0).model_dump(mode="json")).status_code == 401
        )
        assert client.get("/api/v1/plants/plant-1/state").status_code == 401
        assert (
            client.get("/api/v1/plants/plant-1/state", headers={"Authorization": "Bearer read"}).status_code
            == 200
        )
        with client.websocket_connect("/ws/plants/plant-1") as ws:
            ws.send_json({"type": "auth", "token": "read"})
            assert ws.receive_json()["type"] == "snapshot"
        with client.websocket_connect("/ws/plants/plant-1") as ws:
            ws.send_json({"type": "auth", "token": "wrong"})
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/ws/plants/plant-1", headers={"Origin": "https://unlisted.example"}
            ):
                pass


def test_remote_config_requires_tokens():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, deployment_mode="remote")


def test_demo_explicitly_enabled(settings):
    settings.demo_mode = True
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/v1/demo/scenario", json={"scenario": "dry"}).status_code == 200
        assert client.post("/api/v1/demo/scenario", json={"scenario": "dry"}).status_code == 409


def test_missing_camera_observation_accepted(settings):
    with TestClient(create_app(settings)) as client:
        observation = LeafObservation(source=Source.hardware, status=Status.error, note="Camera unavailable")
        assert (
            client.post("/api/v1/leaf-observations", json=observation.model_dump(mode="json")).json()[
                "status"
            ]
            == "accepted"
        )
        assert client.get("/health").status_code == 200


def test_database_failure_does_not_block_startup(tmp_path, reading):
    settings = Settings(
        _env_file=None, database_url=f"sqlite:///{tmp_path}/missing/subdirectory/db", database_required=True
    )
    with TestClient(create_app(settings)) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/ready").status_code == 503
        assert (
            client.post("/api/v1/sensor-readings", json=reading(0).model_dump(mode="json")).status_code == 200
        )
