import argparse
import glob
import json
import os
from dataclasses import asdict
from importlib.metadata import PackageNotFoundError, version

from dotenv import load_dotenv

from backend.sensors.freewili_adapter import FreeWiliAdapter, HardwareConfig


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(
        description="List candidate ports and SDK devices; optionally perform harmless raw reads."
    )
    parser.add_argument("--device", default=os.getenv("FREEWILI_DEVICE", ""))
    parser.add_argument("--board-version", default=os.getenv("FREEWILI_BOARD_VERSION", ""))
    parser.add_argument("--firmware-version", default=os.getenv("FREEWILI_FIRMWARE_VERSION", ""))
    parser.add_argument(
        "--sdk-family", choices=["legacy", "onewili"], default=os.getenv("FREEWILI_SDK_FAMILY", "legacy")
    )
    parser.add_argument("--inspect", action="store_true")
    args = parser.parse_args()
    config = HardwareConfig(args.device, args.board_version, args.firmware_version, args.sdk_family)
    report = {
        "configuration": asdict(config),
        "candidate_ports": sorted(
            glob.glob("/dev/cu.*") + glob.glob("/dev/ttyACM*") + glob.glob("/dev/ttyUSB*")
        ),
        "note": "Ports are candidates only; no pin mapping or plant sensor capability is inferred.",
    }
    try:
        report["freewili_sdk_version"] = version("freewili")
    except PackageNotFoundError:
        report["freewili_sdk_version"] = None
    adapter = FreeWiliAdapter(config)
    try:
        report["sdk_devices"] = [str(d) for d in adapter.candidates()]
        if args.inspect:
            adapter.connect()
            report["raw"] = adapter.inspect_raw()
    except Exception as exc:
        report["status"] = "unavailable"
        report["detail"] = str(exc)
    finally:
        adapter.cleanup()
    print(json.dumps(report, indent=2))
    if args.inspect and report.get("status") == "unavailable":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
