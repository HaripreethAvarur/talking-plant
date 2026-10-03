# Arduino + Grove + Logitech setup

The selected path is **sensors → UNO R4 WiFi → USB → laptop bridge → backend/database
→ React frontend**. The webcam and microphone connect directly to the laptop.
The WiFi radio, FreeWILi, Raspberry Pi, Alexa, buzzer and LCD are not needed for this path.

## 1. Jumper wiring

Disconnect power while wiring. Use the pin labels printed on each Grove module;
standard Grove cable colors are red VCC, black GND, yellow signal and white unused.
With individual jumper wires, color alone does not identify a pin.

| Module | VCC | GND | Signal on UNO R4 |
|---|---|---|---|
| Moisture v1.4 | 5V | GND | A0 |
| Light v1.2 | 5V | GND | A1 |
| Touch v1.1 | 5V | GND | D2 |

All three need common ground and a shared 5V supply. A breadboard or suitable power
splitter distributes 5V/GND when no Grove shield is present; don't force several
jumper connectors onto one header pin. Leave each module's unused pin unconnected.
Keep moisture-board electronics above the soil/water; only the probe goes into soil.
The touch module is active-high in its default configuration. Mount its sensing pad
where the child can pat it: touching an arbitrary leaf does not necessarily activate it.

These assignments are our firmware configuration. See the manufacturers' documents:
[Touch sensor](https://wiki.seeedstudio.com/Grove-Touch_Sensor/),
[Light sensor, including v1.2](https://wiki.seeedstudio.com/Grove-Light_Sensor/),
[Moisture sensor, including v1.4 schematic](https://wiki.seeedstudio.com/Grove-Moisture_Sensor/),
and [UNO R4 WiFi](https://docs.arduino.cc/tutorials/uno-r4-wifi/cheat-sheet/).
Verify the labels against your actual modules before wiring.

## 2. Upload the firmware

Open `firmware/talking_plant/talking_plant.ino` in Arduino IDE. Install the Arduino
UNO R4 board package, select **Arduino UNO R4 WiFi** and the board's USB port, then
upload. Close Serial Monitor before starting the Python bridge.
The sketch was compile-checked with Arduino CLI 1.5.1 and `arduino:renesas_uno` 1.6.0
for `arduino:renesas_uno:unor4wifi`; it has not been flashed or physically tested here.

```sh
make install-arduino
make arduino-devices
make arduino-devices ARGS='--inspect --port /dev/cu.usbmodemYOUR_PORT --count 10'
```

Use your enumerated port, not the example string. Windows uses a COM port; Linux
usually uses `/dev/ttyACM...`. The bridge runs **natively on the laptop**, including
when the backend runs in Docker; it owns USB access. Set `ARDUINO_PORT` in `.env` to
avoid repeating `--port`. Only one process can read the port at a time.

## 3. Calibrate the moisture probe

The inspect command prints raw values (0–1023). Measure stable readings in your
chosen dry and wet soil conditions, with the same insertion depth. Save those
actual numbers:

```sh
# Replace DRY_VALUE and WET_VALUE with your measurements.
make calibrate ARGS='--dry DRY_VALUE --wet WET_VALUE --sensor-model "Grove moisture v1.4" --device-id arduino-plant-1'
```

This writes ignored `config/calibration.json`. Restart the Arduino bridge after
changing it. Calibration must match the firmware's device ID. Without it, readings
are stored as `uncalibrated`, raw values remain available, and the UI water gauge
is unknown. The resulting percentage is a relative dry-to-wet scale, not volumetric
soil water content. Mock mode uses its own clearly simulated calibration.

Light is a **raw ADC count, not lux**. The UI sunlight gauge normalizes 0–1023 for
display. The seed profile uses provisional raw thresholds: below 200 for dark,
above 300 to recover, with a sustained-reading requirement. Measure shade and
normal demo lighting, then adjust `shared/plant-profile.json` appropriately.

Existing databases retain their saved profile, even when this file changes. Check
`GET /api/v1/plants/plant-1/context`: its profile must have `light_unit: "raw"` for
Arduino darkness detection. To intentionally apply the edited profile with Docker:

```sh
docker compose exec backend python -m scripts.profile shared/plant-profile.json
docker compose restart backend
```

This replaces the saved profile, including its name and other thresholds, so edit
those fields first if customized. It preserves care history. For native use:
`.venv/bin/python -m scripts.profile shared/plant-profile.json`, then restart backend.

## 4. Start the pipeline

```sh
make local                       # backend + database; reads PORT from .env
npm --prefix frontend run dev    # separate terminal; open localhost:5173
make arduino                     # separate terminal; reads ARDUINO_PORT from .env
```

Stop mock/replay producers before using real sensors. `BACKEND_URL` in `.env` must
match the backend port (e.g. `http://127.0.0.1:18080`). The browser UI still uses 5173.
Open `/docs` on the backend port to inspect state, raw readings and database history.
`/ready` exposes persistence status; acceptance can mean buffered while the DB is down.

Click **Tap to wake up** once, allow the microphone, and select the Logitech mic as
the browser/OS input. Set your JBL speaker as the output if desired. Touch the pad:

1. The backend records the touch and emits one `listen_request` with an event ID.
2. The first connected frontend tab stops plant speech and records for six seconds.
3. It stops the microphone tracks and submits the clip to the existing `/api/stt`.
4. The transcript goes through the existing conversation and TTS flow.

There is no spoken greeting before recording, to avoid recording the plant's own
voice. The visible “Listening…” prompt is the cue to speak. Holding the pad produces
one trigger; a new pat needs a release and the default ten-second cooldown. Hidden
or disconnected tabs cancel recording. Reloading requires the wake action again.
Keep only the intended listening tab connected: the server routes touch to its first
connected browser, even if a different tab is currently visible.

Without an ElevenLabs key, the microphone flow reaches an offline fallback and
question buttons remain usable. There is no automatic browser speech-recognition
fallback. Raw child audio is forwarded for transcription, not saved in our database.
Use localhost, or HTTPS for remote browser microphone access.

## 5. Webcam leaf observations

```sh
make install-vision
# Example ROI only: replace with X Y WIDTH HEIGHT around your visible leaf.
make camera ARGS='--camera-index 0 --roi 100 100 200 200 --publish --loop --interval 10'
```

Grant camera permission to the terminal/Python process on macOS. Try the appropriate
index for the Logitech camera; 0 can be the built-in laptop camera. The ROI must
contain the plant's leaves and fit the frame. Only observation metadata and color
proportions are uploaded/stored; image frames are not saved. This baseline detects
yellow/brown pixels in the selected region; it is not a disease diagnosis, and
background/lighting can mislead it. It reports unavailable/error when capture fails.

## USB protocol and storage

Our firmware uses 115200 baud and newline-delimited JSON. It waits for the host's
`START <uuid>` command; the serial adapter sends that automatically. To inspect via
Serial Monitor instead, select newline termination and send e.g.
`START 11111111-1111-4111-8111-111111111111` (then close Monitor before the bridge).

A sensor heartbeat is sent every second; debounced touch edges are sent immediately:

```json
{"protocol":"talking-plant/1","type":"sensor","device_id":"arduino-plant-1","session_id":"11111111-1111-4111-8111-111111111111","sequence":0,"uptime_ms":1234,"moisture_raw":290,"light_raw":600,"touch":false}
```

A `type: "touch"` frame has the same identity/timing/touch fields and omits both ADC
fields. Firmware debounce is 40 ms. The adapter reconstructs capture timestamps
from board uptime, rejects old sessions/duplicate sequences, and generates stable
observation IDs for retries. On reconnect it creates a new session, and an initially
held pad must be released before it can trigger. No frames for five seconds causes
a disconnected observation and reconnect attempts. A pulled analog sensor lead can
float while the board still reports numbers; this cannot prove individual wiring
health and must be checked physically.

Existing `care_records` store `sensor`, `touch_observation`, derived `touch`, and
`leaf` records as JSON; checkpoints preserve state and cooldown. No database column
migration is needed. `/ws/plants/plant-1` exposes full state/events, while `/ws`
serves the current frontend. The existing speech/conversation source was reused.

## Physical acceptance checklist

- Confirm each printed pin label, power distribution and common ground.
- Verify light decreases when covered; save measured dry/wet calibration.
- Pat once, hold, release/repat, unplug/replug while held: expect no duplicate recording.
- Verify permission-denied, hidden-tab, disconnect and missing-STT fallbacks.
- Ask through the Logitech mic and hear a reply on the chosen speaker.
- Choose the leaf crop; confirm camera failures show unavailable data.
- Check `/ready` and history, then restart backend and confirm records survive.
