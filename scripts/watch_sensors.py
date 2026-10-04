"""Print the hub's readings live, one line per second, for calibration at the pot.

python -m scripts.watch_sensors   (close the Arduino Serial Monitor and stop the bridge first)
"""

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from backend.sensors.arduino_adapter import ArduinoSerialAdapter
from backend.sensors.calibration import Calibration


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default=os.getenv("ARDUINO_PORT", ""))
    parser.add_argument(
        "--calibration", type=Path, default=Path(os.getenv("CALIBRATION_PATH", "config/calibration.json"))
    )
    args = parser.parse_args()
    calibration = (
        Calibration.model_validate_json(args.calibration.read_text()) if args.calibration.exists() else None
    )
    print(
        "Saved calibration:",
        f"dry={calibration.dry_raw} wet={calibration.wet_raw}" if calibration else "none",
    )
    adapter = ArduinoSerialAdapter(args.port, calibration=calibration)
    try:
        adapter.connect()
        while True:
            for observation in adapter.read_observations():
                if hasattr(observation, "moisture"):
                    m = observation.moisture
                    percent = f"{m.relative_percent:5.1f}%" if m.relative_percent is not None else "  n/a"
                    print(
                        f"moisture raw {m.raw:6.0f}  {percent}   light raw {observation.light.value:6.0f}",
                        end="  ",
                    )
                else:
                    print("TOUCHED" if observation.pressed else "", flush=True)
    except KeyboardInterrupt:
        pass
    except (RuntimeError, OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from None
    finally:
        adapter.cleanup()


if __name__ == "__main__":
    main()
