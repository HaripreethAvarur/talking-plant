"""Saying the plant's name opens the mic like a touch; the sign-up can look up a ZIP code."""

from fastapi.testclient import TestClient

from backend import air
from backend.api import create_app


def test_zip_lookup(settings, monkeypatch):
    async def fake_zip(lat, lon):
        return "48104" if lat > 0 else None

    monkeypatch.setattr(air, "zip_for", fake_zip)
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/location/zip", params={"lat": 42.28, "lon": -83.74}).json() == {
            "zip": "48104"
        }
        assert client.get("/api/location/zip", params={"lat": -33.9, "lon": 18.4}).status_code == 404
        assert client.get("/api/location/zip", params={"lat": "here"}).status_code == 422


def test_ui_state_carries_air_and_checkup(settings, monkeypatch):
    from backend.vision import health

    async def aqi(zip_code):
        return 41.0

    async def looks():
        return "Green leaves standing up."

    monkeypatch.setattr(air, "us_aqi", aqi)
    monkeypatch.setattr(health, "look", looks)
    with TestClient(create_app(settings)) as client:
        client.post(
            "/api/plant",
            json={"username": "maya", "plant_name": "Spike", "plant_type": "plant", "location": "48105"},
        )
        client.post("/api/v1/care-log/log-now")
        with client.websocket_connect("/ws") as ws:
            state = ws.receive_json()
    assert state["air_aqi"] == 41.0
    assert state["looks"] == "Green leaves standing up." and state["looks_at"] > 0
    assert state["checkup_mood"] == "happy"
