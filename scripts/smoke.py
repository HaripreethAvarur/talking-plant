"""Live HTTP + WebSocket smoke. Use fresh state or wait out the watering cooldown."""

import argparse
import asyncio
import json
import os
from pathlib import Path

import httpx
from dotenv import load_dotenv
from websockets.asyncio.client import connect

from backend.conversation.scripted import MOOD_LINES
from backend.sensors.bridge import publish
from backend.sensors.simulator import scenario_reading
from shared.contracts import Mood


async def run(args):
    url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
    ingestion = os.getenv("INGESTION_TOKEN", "")
    viewer = os.getenv("VIEWER_TOKEN", "")
    async with httpx.AsyncClient(base_url=url, timeout=10) as client:
        assert (await client.get("/health")).status_code == 200
        assert (await client.get("/ready")).status_code == 200
        view_headers = {"Authorization": f"Bearer {viewer}"} if viewer else {}
        if args.verify_events:
            expected = set(json.loads(args.verify_events.read_text()))
            response = await client.get(
                "/api/v1/plants/plant-1/history", params={"limit": 1000}, headers=view_headers
            )
            response.raise_for_status()
            assert response.json()["storage"] == "database"
            ids = {r["event_id"] for r in response.json()["items"]}
            assert expected <= ids, "Events did not survive restart"
            print(f"PASS: {len(expected)} record IDs are present in persistent database history.")
            return
        uri = url.replace("https://", "wss://").replace("http://", "ws://") + "/ws/plants/plant-1"
        async with connect(uri) as ws:
            if viewer:
                await ws.send(json.dumps({"type": "auth", "token": viewer}))
            snapshot = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
            assert snapshot["type"] == "snapshot"
            events = []

            async def receive():
                while True:
                    message = json.loads(await ws.recv())
                    events.extend(message.get("events", []))

            receiver = asyncio.create_task(receive())
            client.headers.update({"Authorization": f"Bearer {ingestion}"} if ingestion else {})
            try:
                for step in range(24):
                    reading = scenario_reading("dry-to-watered", step)
                    result = await publish(client, "/api/v1/sensor-readings", reading)
                    assert result and result["status"] == "accepted"
                    if step in (3, 11):
                        retry = await publish(client, "/api/v1/sensor-readings", reading)
                        assert retry["status"] == "duplicate"
                    await asyncio.sleep(1)
            finally:
                receiver.cancel()
                try:
                    await receiver
                except asyncio.CancelledError:
                    pass
        speech = [e for e in events if e["suggested_text"]]
        assert [e["suggested_text"] for e in speech] == [
            MOOD_LINES[Mood.thirsty],
            MOOD_LINES[Mood.grateful],
        ], speech
        assert len([e for e in events if e["kind"] == "watering"]) == 1
        if args.save_events:
            args.save_events.write_text(json.dumps([e["event_id"] for e in speech]))
        print(
            "PASS: HTTP ingestion, retry deduplication, WebSocket snapshot and one thirsty/thank-you sequence."
        )


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--save-events", type=Path)
    parser.add_argument("--verify-events", type=Path)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
