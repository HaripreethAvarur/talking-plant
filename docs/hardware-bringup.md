# Native macOS bring-up for tomorrow

The laptop owns USB and camera capture. A remote server cannot access these devices.
Keep `make replay` ready as a fallback. Never substitute mock data inside hardware mode.
No electrical pin assignment, baud rate, ADC command or sensor output format is guessed
by this repository. The currently implemented adapter is the documented **legacy** Python
SDK transport; its soil and light readers intentionally return actionable unavailable errors.

## Procedure

1. Photograph/record the exact board generation, firmware revision shown by the device,
   and both sensor part numbers. Check whether it uses legacy FreeWili firmware or the
   newer OneWili API. Record SDK version from diagnostics. Do not flash firmware solely
   to match this demo; first identify its matching official documentation (H1 below).
2. Before wiring, confirm each sensor's supply voltage, output voltage, current, pinout,
   interface, common ground, and board input limits using its datasheet and the correct
   board pinout. Check actual supply/output with a meter. Record the chosen channel and
   wiring in a local bring-up note. Pin names across generations need explicit verification (H2).
3. `make install`; for the verified legacy family, `make install-hardware`. Run `make devices`.
   It lists candidate macOS ports and SDK devices without running the API. A serial port
   alone does not identify sensor capabilities. Use a unique SDK label as device selector.
4. Fill `FREEWILI_DEVICE`, `FREEWILI_BOARD_VERSION`, `FREEWILI_FIRMWARE_VERSION` in `.env`.
   Use `make devices ARGS='--inspect --device "UNIQUE-LABEL" --board-version "ACTUAL" --firmware-version "ACTUAL"'`.
   The adapter's harmless button read verifies connection; diagnostics explicitly report
   missing moisture/light. For OneWili firmware, complete H1 first; `--sdk-family onewili`
   currently fails with an explanatory setup error rather than trying legacy commands.
5. Complete H2 and implement `FreeWiliAdapter.read_moisture` against the **measured** sensor
   transport. Take multiple stable raw readings in the agreed dry reference and wet/drained
   reference medium, without immersing sensor electronics. Record both endpoints, sensor
   identity and repeatability. Do not use the simulated fixture's ADC values for hardware.
6. Persist measured endpoints:
   `make calibrate ARGS='--dry ACTUAL_DRY --wet ACTUAL_WET --sensor-model ACTUAL_MODEL --device-id ACTUAL_ID'`.
   `config/calibration.json` survives bridge restarts. Use `self.calibration.convert(raw)`
   in the moisture reader after confirming calibration.device_id matches the selected
   device. Return `status=uncalibrated`, raw only, if calibration is absent/mismatched.
   The endpoint direction can increase or decrease. Values are clamped to 0–100 on a
   relative scale; they are not scientific volumetric water content (H3).
7. Complete H4, inspect light uncovered and shaded, and verify whether the SDK supplies lux.
   Keep `unit=raw` if units cannot be established. Choose thresholds in those same units;
   the default lux thresholds deliberately ignore raw readings. Never invent a lux conversion.
8. Run `make local`, then `make freewili ARGS='--count 30'`. Hardware mode attempts reconnect
   every 3 seconds by default; `--reconnect-seconds` changes it. Connection loss sends null
   readings with `disconnected`, not simulated values. Setup errors exit with instructions;
   unimplemented measurements stay missing while the connection is valid.
9. Disconnect/reconnect USB while dry, reconnect at wet, and confirm no thank-you event is
   fabricated. Stop bridge entirely and check health becomes stale after 5 seconds. Then
   establish continuous dry readings, water, and verify exactly one watering event. Record
   raw readings, noise, response latency and any required threshold changes (H5).
10. Camera is independent: `make install-vision`; first run
    `make image ARGS='--image /absolute/path/leaf.jpg --roi 20 20 200 200'` with a leaf-only
    region inside your actual image. Then grant your terminal/IDE camera access under
    macOS System Settings → Privacy & Security → Camera. Run
    `make camera ARGS='--camera-index 0 --roi 20 20 200 200 --publish'`.
    Adjust index and crop to the actual frame. Capture is one-shot; repeat for two confirming
    leaf observations. Failure produces an error observation and does not stop sensors (H6).
11. For remote use, set `BACKEND_URL=https://YOUR-HOST` and the ingestion token in the native
    laptop `.env`. Verify `/ready` and frontend WSS, then run the same bridge commands.

## Hardware TODO register

Every code marker refers to these actionable checks; none indicates verified physical operation.

| ID | Unknown | File/function to update | Evidence that resolves it | Verification afterward |
|---|---|---|---|---|
| H1 | Actual board/firmware and SDK family; new OneWili discovery/selection and transport | `backend/sensors/freewili_adapter.py`: `candidates`, `connect`, `cleanup`; optional hardware lock | Board revision and firmware screen plus matching official SDK docs/source; record exact SDK release/commit | List, select the intended device among multiple candidates, connect, harmless read, close, unplug and reconnect |
| H2 | Sensor model, voltage compatibility, physical pins, ADC/I2C/SPI path and returned raw format | `FreeWiliAdapter.read_moisture` and `HardwareConfig` in the same file | Sensor datasheet, correct board schematic/pinout, meter measurements and documented read output | Confirm safe voltage first; repeat dry/wet raw reads with meaningful change and errors on unplug |
| H3 | Dry/wet endpoints, direction, noise and calibration-to-device identity | `FreeWiliAdapter.read_moisture` calls `backend/sensors/calibration.py:Calibration.convert`; saved config | Repeated bench measurements in agreed reference media for the actual sensor | Reload calibration after restart; dry≈0/wet≈100; mismatched/no calibration gives raw+uncalibrated, never invented percent |
| H4 | Ambient sensor model, SDK event/return format and true units | `FreeWiliAdapter.read_light`, optionally new firmware decoder | Matching firmware docs and captured sensor output; verify any stated scaling from source | Shade/unshade; compare raw or lux units; never label raw as lux; unavailable becomes null |
| H5 | Physical disconnect/reconnect behavior and timing/noise thresholds | `backend/sensors/bridge.py:run`, `shared/plant-profile.json` if measured timing warrants adjustment | USB disconnect trials and raw time series for dry→watered/noise | One thirsty and one watering speech event; none from reconnect; bridge retries without switching mode |
| H6 | Camera index, macOS permission, exposure and usable leaf crop | `backend/vision/observe.py:capture`, CLI camera/ROI settings | Actual permission grant, image inspection and lighting checks | Correct crop, useful color fractions, graceful unavailable camera, no stored raw image |

## Verified documentation (consulted 2026-10-02)

- [Legacy Python examples](https://freewili.github.io/freewili-python/examples.html):
  `FreeWili.find_all()`, `open().expect(...)`, `read_all_buttons().expect(...)`, `close()`.
- [Legacy API reference](https://freewili.github.io/freewili-python/api/fw.html): configurable
  open timeout; no soil-moisture-specific read method established for our unknown sensor.
- [OneWili Python quick start](https://freewili.com/onewili/getting-started/python/): separate
  generated SDK, connection and cleanup. It is not substituted for legacy firmware automatically.
- [OneWili sensor reference](https://freewili.com/onewili/reference/sensors/): sensor streaming
  and `env` events, including a `lux_clux` field. This is firmware-specific evidence, not proof
  that tomorrow's board uses that protocol or that legacy SDK exposes the same values.
- [Board-generation FAQ](https://docs.freewili.com/help/faq/) and
  [current pinout](https://docs.freewili.com/hardware/pinout/): generation/firmware differences
  matter. Confirm your actual revision before wiring; do not treat this runbook as a pin map.

Leaf color thresholds are a development baseline. They do not detect wilting reliably.
The `LeafModel` protocol and TODO(MODEL) in `observe.py` reserve an interface for a model
validated on representative labeled images; no disease or wilting claims are made.
