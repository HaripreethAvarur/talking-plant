"""Deterministic fixtures. Values in this module are explicitly simulated."""

from shared.contracts import Light, Moisture, SensorReading, Source, Status, utcnow

SCENARIOS = ("healthy", "dry", "watered", "dark", "noisy", "disconnected", "dry-to-watered")


def scenario_reading(scenario, step, plant_id="plant-1", timestamp=None):
    if scenario not in SCENARIOS:
        raise ValueError("Unknown scenario")
    if scenario == "disconnected":
        moisture, light = Moisture(status=Status.disconnected), Light(status=Status.disconnected)
    else:
        value = {
            "healthy": 60,
            "dry": 15,
            "watered": 75,
            "dark": 60,
            "noisy": (29, 31, 30, 32, 28, 31)[step % 6],
            "dry-to-watered": 15 if step < 8 else 75,
        }[scenario]
        moisture = Moisture(
            raw=1000 - value * 8,
            relative_percent=value,
            status=Status.ok,
            calibration_id="mock-dry1000-wet200-v1",
        )
        # Raw ADC counts, like the Arduino light sensor.
        light = Light(value=20 if scenario == "dark" else 600, unit="raw", status=Status.ok)
    return SensorReading(
        plant_id=plant_id,
        timestamp=timestamp or utcnow(),
        source=Source.mock,
        device_id="mock-bridge",
        moisture=moisture,
        light=light,
    )
