import argparse
from pathlib import Path
from uuid import uuid4

from pydantic import Field, model_validator

from shared.contracts import Contract, Moisture, Status


class Calibration(Contract):
    calibration_id: str = Field(default_factory=lambda: str(uuid4()))
    dry_raw: float
    wet_raw: float
    sensor_model: str = Field(min_length=1)
    device_id: str = Field(min_length=1)
    notes: str = "Relative calibrated scale, not volumetric water content."

    @model_validator(mode="after")
    def endpoints(self):
        if abs(self.wet_raw - self.dry_raw) < 1e-6:
            raise ValueError("Dry and wet readings must differ")
        return self

    def convert(self, raw):
        relative = 100 * (raw - self.dry_raw) / (self.wet_raw - self.dry_raw)
        return Moisture(
            raw=raw,
            relative_percent=max(0, min(100, relative)),
            status=Status.ok,
            calibration_id=self.calibration_id,
        )

    def save(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(self.model_dump_json(indent=2) + "\n")
        temporary.replace(path)


def main():
    parser = argparse.ArgumentParser(
        description="Persist measured dry/wet endpoints; never guesses hardware values."
    )
    parser.add_argument("--dry", type=float, required=True)
    parser.add_argument("--wet", type=float, required=True)
    parser.add_argument("--sensor-model", required=True)
    parser.add_argument("--device-id", required=True)
    parser.add_argument("--output", type=Path, default=Path("config/calibration.json"))
    args = parser.parse_args()
    try:
        calibration = Calibration(
            dry_raw=args.dry, wet_raw=args.wet, sensor_model=args.sensor_model, device_id=args.device_id
        )
        calibration.save(args.output)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Saved relative moisture calibration to {args.output}")


if __name__ == "__main__":
    main()
