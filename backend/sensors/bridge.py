"""Laptop-side sensor bridge: posts readings to the backend at BACKEND_URL.

Modes: mock (simulator scenarios), replay (a recorded fixture), arduino (the real
board over USB) and arduino-mock (simulated hub frames through the same decoder).
"""

import argparse
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from dotenv import load_dotenv

from backend.sensors.simulator import SCENARIOS, scenario_reading
from shared.contracts import SensorReading, Source, utcnow


async def publish(client, path, observation):
    """Three bounded attempts with the SAME event_id. Reject auth/validation errors immediately."""
    for attempt in range(3):
        try:
            response = await client.post(path, json=observation.model_dump(mode="json"))
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code < 500:
                raise RuntimeError(
                    f"Ingestion rejected: HTTP {exc.response.status_code}; check token, plant ID and schema."
                ) from None
        except httpx.TransportError:
            pass
        if attempt < 2:
            await asyncio.sleep(0.5 * (2**attempt))
    print("Backend unreachable after 3 attempts; observation dropped. No durable bridge queue.")
    return None


def replay_rows(path, plant_id, start=None):
    rows = [SensorReading.model_validate_json(line) for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        raise ValueError("Replay fixture is empty")
    if any(b.timestamp <= a.timestamp for a, b in zip(rows, rows[1:])):
        raise ValueError("Replay timestamps must strictly increase")
    start = start or utcnow()
    origin = rows[0].timestamp
    return [
        r.model_copy(
            update={
                "event_id": uuid4(),
                "timestamp": start + (r.timestamp - origin),
                "source": Source.replay,
                "plant_id": plant_id,
                "device_id": "replay-bridge",
            }
        )
        for r in rows
    ]


def validate_backend_url(url):
    parsed = urlparse(url)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("BACKEND_URL must not include credentials, query, or fragment.")
    if not parsed.hostname or (
        parsed.scheme != "https"
        and not (parsed.scheme == "http" and parsed.hostname in ("127.0.0.1", "localhost", "::1"))
    ):
        raise ValueError("Use HTTPS for remote ingestion (or localhost for the local demo).")


def report(result):
    """Print the backend's answer to one posted observation (one JSON line)."""
    if result:
        keys = ("status", "event_id", "events")
        print(json.dumps({key: result[key] for key in keys}), flush=True)


async def run(args):
    backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
    token = os.getenv("INGESTION_TOKEN", "")
    validate_backend_url(backend_url)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(
        base_url=backend_url, headers=headers, timeout=5, follow_redirects=False
    ) as client:
        if args.mode in ("arduino", "arduino-mock"):
            from backend.sensors.arduino import run as run_arduino

            await run_arduino(client, args)
        elif args.mode == "replay":
            rows = replay_rows(args.fixture, args.plant_id)
            previous = rows[0].timestamp
            for row in rows:
                await asyncio.sleep(max(0, (row.timestamp - previous).total_seconds()))
                previous = row.timestamp
                # Preserve fixture intervals, rebase to wall time to account for HTTP latency.
                row.timestamp = utcnow()
                report(await publish(client, "/api/v1/sensor-readings", row))
        else:
            step = 0
            while args.count == 0 or step < args.count:
                reading = scenario_reading(args.scenario, step, args.plant_id)
                report(await publish(client, "/api/v1/sensor-readings", reading))
                step += 1
                await asyncio.sleep(args.interval)


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["mock", "replay", "arduino", "arduino-mock"], default="mock")
    parser.add_argument("--port", default=os.getenv("ARDUINO_PORT", ""))
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--scenario", choices=SCENARIOS, default="healthy")
    parser.add_argument("--plant-id", default=os.getenv("PLANT_ID", "plant-1"))
    parser.add_argument("--interval", type=float, default=1)
    parser.add_argument("--count", type=int, default=0, help="0 means continuously")
    parser.add_argument("--fixture", type=Path, default=Path("shared/fixtures/dry-to-watered.jsonl"))
    parser.add_argument(
        "--calibration", type=Path, default=Path(os.getenv("CALIBRATION_PATH", "config/calibration.json"))
    )
    parser.add_argument("--reconnect-seconds", type=float, default=3)
    args = parser.parse_args()
    if args.interval <= 0 or args.reconnect_seconds <= 0 or args.count < 0:
        parser.error("interval/reconnect must be positive and count nonnegative")
    try:
        asyncio.run(run(args))
    except KeyboardInterrupt:
        pass
    except (RuntimeError, ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from None


if __name__ == "__main__":
    main()
