"""Arduino bridge modes (real board and simulated) and a port-listing/inspect command."""

import argparse
import asyncio
import json
import os
from uuid import uuid4

import httpx
from dotenv import load_dotenv

from backend.sensors.arduino_adapter import DEVICE_ID, ArduinoSerialAdapter, HubFrameDecoder
from backend.sensors.calibration import Calibration
from shared.contracts import Source, TouchObservation


async def send(client, observation):
    from backend.sensors.bridge import publish, report

    path = (
        "/api/v1/touch-observations"
        if isinstance(observation, TouchObservation)
        else "/api/v1/sensor-readings"
    )
    report(await publish(client, path, observation))


async def sync_mood(client, adapter, plant_id, last_error=None):
    """Send the backend's current mood to the hub so its LED follows every mood source
    (sensors, camera, demo controls). write_mood only writes when the mood changes.
    Returns the error text, so a repeated failure is printed once."""
    token = os.getenv("VIEWER_TOKEN", "")
    headers = {"Authorization": f"Bearer {token}"} if token else None
    try:
        response = await client.get(f"/api/v1/plants/{plant_id}/state", headers=headers)
        response.raise_for_status()
        await asyncio.to_thread(adapter.write_mood, response.json()["mood"])
    except (httpx.HTTPError, KeyError, ValueError, OSError) as exc:
        error = f"{type(exc).__name__}: {exc}"
        if error != last_error:
            print(f"Mood not sent to the Arduino LED ({error})", flush=True)
        return error
    return None


def simulated_frame(step):
    """Same wire format as the hub sketch. Touch at 4 seconds (released at 5); watering at 8."""
    return json.dumps({"moisture_raw": 290 if step < 8 else 650, "light_raw": 600, "touch": int(step == 4)})


async def run(client, args):
    if args.mode == "arduino-mock":
        decoder = HubFrameDecoder(
            uuid4(),
            args.plant_id,
            Calibration(
                dry_raw=200,
                wet_raw=800,
                sensor_model="SIMULATED Grove v1.4",
                device_id=DEVICE_ID,
                calibration_id="arduino-mock-v1",
            ),
            Source.mock,
        )
        step = 0
        while not args.count or step < args.count:
            for observation in decoder.decode(simulated_frame(step)):
                await send(client, observation)
            step += 1
            await asyncio.sleep(1)
        return
    calibration = (
        Calibration.model_validate_json(args.calibration.read_text()) if args.calibration.exists() else None
    )
    adapter = ArduinoSerialAdapter(args.port, args.plant_id, calibration, args.baud)
    step = 0
    mood_error = None
    try:
        while not args.count or step < args.count:
            try:
                if adapter.serial is None:
                    await asyncio.to_thread(adapter.connect)
                observations = await asyncio.to_thread(adapter.read_observations)
            except (OSError, ValueError) as exc:
                print(f"Arduino unavailable ({type(exc).__name__}): {exc}", flush=True)
                observations = adapter.disconnected()
                await asyncio.to_thread(adapter.cleanup)
                for observation in observations:
                    await send(client, observation)
                await asyncio.sleep(args.reconnect_seconds)
                continue
            for observation in observations:
                await send(client, observation)
            if observations:
                mood_error = await sync_mood(client, adapter, args.plant_id, mood_error)
                step += 1
    finally:
        await asyncio.to_thread(adapter.cleanup)


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="List candidate USB ports or inspect our Arduino's raw frames."
    )
    parser.add_argument("--port", default=os.getenv("ARDUINO_PORT", ""))
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--count", type=int, default=5)
    args = parser.parse_args()
    if args.count < 1:
        parser.error("count must be positive")
    try:
        print(json.dumps(ArduinoSerialAdapter.candidates(), indent=2))
        if args.inspect:
            adapter = ArduinoSerialAdapter(args.port)
            try:
                adapter.connect()
                count = 0
                while count < args.count:
                    for observation in adapter.read_observations():
                        print(observation.model_dump_json())
                        count += 1
            finally:
                adapter.cleanup()
    except (RuntimeError, OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
