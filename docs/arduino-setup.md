# Arduino + Grove + Logitech setup

The selected path is **sensors → UNO R4 WiFi → USB → laptop bridge → backend/database
→ React frontend**. The webcam and microphone connect directly to the laptop.
The WiFi radio, Raspberry Pi, Alexa, buzzer and LCD are not needed for this path.
An optional LED on D4 lights while the plant is thirsty, too dark or unwell.

## 1. Jumper wiring

Disconnect power while wiring. Use the pin labels printed on each Grove module;
standard Grove cable colors are red VCC, black GND, yellow signal and white unused.
With individual jumper wires, color alone does not identify a pin.

| Module | VCC | GND | Signal on UNO R4 |
|---|---|---|---|
| Moisture v1.4 | 5V | GND | A0 |
| Light v1.2 | 5V | GND | A1 |
| Touch v1.1 | 5V | GND | D2 |
| LED (optional, with resistor) | — | GND | D4 |

All three need common ground and a shared 5V supply. A breadboard or suitable power
splitter distributes 5V/GND when no Grove shield is present; don't force several
jumper connectors onto one header pin. Leave each module's unused pin unconnected.
Keep moisture-board electronics above the soil/water; only the probe goes into soil.
The touch module is active-high in its default configuration. Mount its sensing pad
where the child can pat it: touching an arbitrary leaf does not necessarily activate it.

These assignments are set at the top of the sketch. See the manufacturers' documents:
[Touch sensor](https://wiki.seeedstudio.com/Grove-Touch_Sensor/),
[Light sensor, including v1.2](https://wiki.seeedstudio.com/Grove-Light_Sensor/),
[Moisture sensor, including v1.4 schematic](https://wiki.seeedstudio.com/Grove-Moisture_Sensor/),
and [UNO R4 WiFi](https://docs.arduino.cc/tutorials/uno-r4-wifi/cheat-sheet/).
Verify the labels against your actual modules before wiring.

## 2. Upload the sketch

Open `hardware/talking_plant_hub/talking_plant_hub.ino` in Arduino IDE. Install the
Arduino UNO R4 board package, select **Arduino UNO R4 WiFi** and the board's USB port,
then upload. Close Serial Monitor before starting the Python bridge.

```sh
make install-arduino
make arduino-devices                                            # list ports
make arduino-devices ARGS='--inspect --port COM3 --count 10'    # print decoded frames
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
changing it. Calibration must use the device ID `arduino-plant-1`. Without it, readings
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
`python -m scripts.profile shared/plant-profile.json`, then restart the backend.

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

The plant first says "Hi there! What would you like to know?", and the browser starts
recording once that line has played, so the plant's own voice isn't recorded.
The visible “Listening…” prompt is the cue to speak. Holding the pad produces
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

The sketch uses 115200 baud and newline-delimited JSON. It sends one line every second,
and immediately whenever the touch pad changes. Analog values are an average of 8 reads:

```json
{"moisture_raw":290,"light_raw":600,"touch":0}
```

Anything that isn't a valid frame (for example a boot message) is ignored. The board has
no clock or ID, so the laptop timestamps each line on arrival, starts a new session on
every (re)connect, and derives stable observation IDs from that session for retries.
No valid frame for five seconds causes a disconnected observation and reconnect attempts.
A pulled analog lead can float while the board still reports numbers; check wiring
physically.

The laptop can send `{"mood":"thirsty","text":"..."}` back; the sketch lights the D4 LED
for thirsty, too dark or unwell (`ArduinoSerialAdapter.write_mood`).

`care_records` store `sensor`, `touch_observation`, derived `touch`, and `leaf` records
as JSON; checkpoints preserve state and cooldowns. `/ws/plants/plant-1` exposes full
state and events, while `/ws` serves the React frontend.

## Physical acceptance checklist

- Confirm each printed pin label, power distribution and common ground.
- Verify light decreases when covered; save measured dry/wet calibration.
- Pat once, hold, release/repat, unplug/replug while held: expect no duplicate recording.
- Verify permission-denied, hidden-tab, disconnect and missing-STT fallbacks.
- Ask through the Logitech mic and hear a reply on the chosen speaker.
- Choose the leaf crop; confirm camera failures show unavailable data.
- Check `/ready` and history, then restart backend and confirm records survive.
