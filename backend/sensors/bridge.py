"""Native macOS bridge. BACKEND_URL points at local Docker or a remote HTTPS backend."""

import argparse
import asyncio
import json
import os
from pathlib import Path
from urllib.parse import urlparse
from uuid import uuid4

import httpx
from dotenv import load_dotenv

from backend.sensors.calibration import Calibration
from backend.sensors.freewili_adapter import (
    FreeWiliAdapter,
    HardwareConfig,
    HardwareSetupError,
    MeasurementUnavailable,
)
from backend.sensors.simulator import SCENARIOS, scenario_reading
from shared.contracts import Light, Moisture, SensorReading, Source, Status, utcnow


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


async def run(args):
    backend_url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
    token = os.getenv("INGESTION_TOKEN", "")
    validate_backend_url(backend_url)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    adapter = None
    if args.mode == "freewili":
        calibration = (
            Calibration.model_validate_json(args.calibration.read_text())
            if args.calibration.exists()
            else None
        )
        adapter = FreeWiliAdapter(
            HardwareConfig(args.device, args.board_version, args.firmware_version, args.sdk_family),
            calibration,
        )
    try:
        async with httpx.AsyncClient(
            base_url=backend_url, headers=headers, timeout=5, follow_redirects=False
        ) as client:
            if args.mode == "replay":
                rows = replay_rows(args.fixture, args.plant_id)
                previous = rows[0].timestamp
                for row in rows:
                    await asyncio.sleep(max(0, (row.timestamp - previous).total_seconds()))
                    previous = row.timestamp
                    # Preserve fixture intervals, rebase to wall time to account for HTTP latency.
                    row.timestamp = utcnow()
                    result = await publish(client, "/api/v1/sensor-readings", row)
                    if result:
                        print(
                            json.dumps(
                                {
                                    "status": result["status"],
                                    "event_id": result["event_id"],
                                    "events": result["events"],
                                }
                            )
                        )
                return
            step = 0
            while args.count == 0 or step < args.count:
                if adapter:
                    try:
                        if adapter.device is None:
                            await asyncio.to_thread(adapter.connect)
                        readings = {}
                        for name, method, model in (
                            ("moisture", adapter.read_moisture, Moisture),
                            ("light", adapter.read_light, Light),
                        ):
                            try:
                                readings[name] = await asyncio.to_thread(method)
                            except MeasurementUnavailable as exc:
                                if step == 0:
                                    print(str(exc))
                                readings[name] = model(status=Status.missing)
                        reading = SensorReading(
                            plant_id=args.plant_id,
                            source=Source.hardware,
                            device_id=args.device or "selected-freewili",
                            **readings,
                        )
                    except HardwareSetupError:
                        raise
                    except Exception as exc:
                        print(
                            f"Hardware disconnected ({type(exc).__name__}); reconnect in {args.reconnect_seconds}s."
                        )
                        try:
                            await asyncio.to_thread(adapter.cleanup)
                        except Exception:
                            pass
                        reading = SensorReading(
                            plant_id=args.plant_id,
                            source=Source.hardware,
                            device_id=args.device or "selected-freewili",
                            moisture=Moisture(status=Status.disconnected),
                            light=Light(status=Status.disconnected),
                        )
                        await publish(client, "/api/v1/sensor-readings", reading)
                        step += 1
                        await asyncio.sleep(args.reconnect_seconds)
                        continue
                else:
                    reading = scenario_reading(args.scenario, step, args.plant_id)
                result = await publish(client, "/api/v1/sensor-readings", reading)
                if result:
                    print(
                        json.dumps(
                            {
                                "status": result["status"],
                                "event_id": result["event_id"],
                                "events": result["events"],
                            }
                        )
                    )
                step += 1
                await asyncio.sleep(args.interval)
    finally:
        if adapter:
            await asyncio.to_thread(adapter.cleanup)


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["mock", "replay", "freewili"], default="mock")
    parser.add_argument("--scenario", choices=SCENARIOS, default="healthy")
    parser.add_argument("--plant-id", default=os.getenv("PLANT_ID", "plant-1"))
    parser.add_argument("--interval", type=float, default=1)
    parser.add_argument("--count", type=int, default=0, help="0 means continuously")
    parser.add_argument("--fixture", type=Path, default=Path("shared/fixtures/dry-to-watered.jsonl"))
    parser.add_argument("--device", default=os.getenv("FREEWILI_DEVICE", ""))
    parser.add_argument("--board-version", default=os.getenv("FREEWILI_BOARD_VERSION", ""))
    parser.add_argument("--firmware-version", default=os.getenv("FREEWILI_FIRMWARE_VERSION", ""))
    parser.add_argument(
        "--sdk-family", choices=["legacy", "onewili"], default=os.getenv("FREEWILI_SDK_FAMILY", "legacy")
    )
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
