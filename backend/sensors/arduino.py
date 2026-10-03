"""Arduino bridge modes and diagnostic command, independent of server/CV dependencies."""

import argparse
import asyncio
import json
import os
from uuid import uuid4

from dotenv import load_dotenv

from backend.sensors.arduino_adapter import ArduinoSerialAdapter, FrameDecoder
from backend.sensors.calibration import Calibration
from shared.contracts import Source, TouchObservation


async def send(client, observation):
    from backend.sensors.bridge import publish

    path = (
        "/api/v1/touch-observations"
        if isinstance(observation, TouchObservation)
        else "/api/v1/sensor-readings"
    )
    result = await publish(client, path, observation)
    if result:
        print(
            json.dumps(
                {"status": result["status"], "event_id": result["event_id"], "events": result["events"]}
            ),
            flush=True,
        )


def simulated_frames(session, step):
    """Same wire format as firmware. Demo touch at 4 seconds; watering at 8 seconds."""
    return json.dumps(
        {
            "protocol": "talking-plant/1",
            "type": "sensor",
            "device_id": "arduino-plant-1",
            "session_id": str(session),
            "sequence": step,
            "uptime_ms": step * 1000,
            "moisture_raw": 290 if step < 8 else 650,
            "light_raw": 600,
            "touch": step == 4,
        }
    )


async def run(client, args):
    if args.mode == "arduino-mock":
        session = uuid4()
        decoder = FrameDecoder(
            session,
            args.plant_id,
            Calibration(
                dry_raw=200,
                wet_raw=800,
                sensor_model="SIMULATED Grove v1.4",
                device_id="arduino-plant-1",
                calibration_id="arduino-mock-v1",
            ),
            Source.mock,
        )
        step = 0
        while not args.count or step < args.count:
            for observation in decoder.decode(simulated_frames(session, step)):
                await send(client, observation)
            step += 1
            await asyncio.sleep(1)
        return
    calibration = (
        Calibration.model_validate_json(args.calibration.read_text()) if args.calibration.exists() else None
    )
    adapter = ArduinoSerialAdapter(args.port, args.plant_id, calibration, args.baud)
    step = 0
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
