"""Verified legacy SDK discovery/open/close; sensor transport awaits identified hardware.

Source: https://freewili.github.io/freewili-python/examples.html and api/fw.html.
No pin writes, guessed ADC API, or hand-written serial protocol is used.
"""

from dataclasses import dataclass

from shared.contracts import Light, Moisture, Status


class HardwareSetupError(RuntimeError):
    pass


class MeasurementUnavailable(RuntimeError):
    pass


@dataclass
class HardwareConfig:
    device: str = ""
    board_version: str = ""
    firmware_version: str = ""
    sdk_family: str = "legacy"


class FreeWiliAdapter:
    def __init__(self, config, calibration=None):
        self.config = config
        self.calibration = calibration
        self.device = None

    @staticmethod
    def candidates():
        try:
            from freewili import FreeWili
        except ImportError:
            raise HardwareSetupError(
                "Install requirements-hardware.txt in the native bridge environment."
            ) from None
        return FreeWili.find_all()

    def connect(self):
        if not self.config.board_version or not self.config.firmware_version:
            raise HardwareSetupError(
                "Record --board-version and --firmware-version from the device; see hardware-bringup.md H1."
            )
        if self.config.sdk_family != "legacy":
            # TODO(HARDWARE) H1: unknown board/firmware transport. Update connect/candidates after
            # identifying firmware and matching OneWili docs; verify select/open/close/reconnect on device.
            raise HardwareSetupError(
                "TODO(HARDWARE) H1: OneWili firmware needs its matching adapter; legacy SDK is not interchangeable."
            )
        devices = self.candidates()
        matches = [d for d in devices if self.config.device in str(d)] if self.config.device else devices
        if len(matches) != 1:
            raise ConnectionError(
                "Select exactly one device using --device with a unique label from diagnostics."
            )
        self.device = matches[0]
        try:
            self.device.open(timeout_sec=3).expect("FreeWili open failed")
        except Exception:
            self.cleanup()
            raise

    def read_moisture(self) -> Moisture:
        # TODO(HARDWARE) H2: sensor model, voltage, ADC channel and returned units are unknown.
        # Update this method from the sensor datasheet + matching board SDK after safe bench measurement.
        # Verify raw dry/wet values, saved calibration identity, and unplug behavior; see H2/H3 in bring-up.
        raise MeasurementUnavailable(
            "TODO(HARDWARE) H2/H3: moisture sensor transport and calibration need bench verification."
        )

    def read_light(self) -> Light:
        # TODO(HARDWARE) H4: actual ambient sensor output and firmware decoder are unknown.
        # Update here after capturing documented SDK sensor output; verify shading and units against docs.
        raise MeasurementUnavailable(
            "TODO(HARDWARE) H4: implement verified light read; label raw unless lux is provided."
        )

    def inspect_raw(self):
        if self.device is None:
            raise ConnectionError("Connect before raw diagnostics")
        # A verified, harmless SDK read proves host communication; it is not a plant measurement.
        buttons = self.device.read_all_buttons().expect("Button diagnostic read failed")
        result = {"buttons": {getattr(k, "name", str(k)): v for k, v in buttons.items()}}
        for name, method in (("moisture", self.read_moisture), ("light", self.read_light)):
            try:
                result[name] = method().model_dump(mode="json")
            except MeasurementUnavailable as exc:
                result[name] = {"status": Status.missing.value, "value": None, "detail": str(exc)}
        return result

    def cleanup(self):
        device, self.device = self.device, None
        if device is not None:
            device.close()
