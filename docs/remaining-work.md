# Verification and remaining work

Current implementation is on `arduino-backend`. It adds UNO R4 firmware, USB ingestion,
touch persistence, the unified UI adapter, and the explicitly authorized frontend
microphone handler. Existing `backend/conversation/` and `backend/speech/` source was
reused without edits. No physical upload or external deployment is claimed.

## Checked on 2026-10-03

- 47 backend pytest tests passed, including Arduino frame validation, raw/calibrated
  values, sensor identity, delayed timestamps, clock wrap, duplicate suppression,
  touch debounce/cooldown, held-pad/reconnect behavior and persistent restart dedup.
- A real pyserial connection over a local pseudo-terminal exercised the START/session
  handshake and partial JSON lines spanning serial read timeouts. No attached USB board
  was opened for this test. Pyserial is optional for the server and installed by
  `make install-arduino` for the laptop bridge.
- UI WebSocket tests verified state conversion, missing-calibration/camera replies,
  touch routing to a single client, no historical touch replay, viewer authentication,
  origin validation, offline STT behavior and recovery after a TTS exception.
- All 19 existing speech/conversation unittest tests passed offline.
- Ruff lint and format checks passed; shared schemas/examples regenerated deterministically.
- React TypeScript check and Vite production build passed.
- Arduino sketch compiled for `arduino:renesas_uno:unor4wifi` with Arduino CLI 1.5.1
  and Arduino renesas_uno core 1.6.0: 52,944 bytes flash and 6,868 bytes global RAM.
- Docker image built and an isolated backend/PostgreSQL stack became healthy on
  localhost:18081 (`talking-plant-arduino-check`, separate database volume).
- Actual native Arduino mock CLI → HTTP → PostgreSQL → existing `/ws` UI protocol:
  24 sensor readings, 24 touch observations, one listen request, and exactly one
  thirsty/thank-you suggestion each. UI frames carried relative moisture and raw light.
- Backend restart preserved the original sensor/touch event IDs in PostgreSQL.

One upstream Starlette/AnyIO deprecation warning remains. Browser automation reported
no available browser, so microphone permission prompts, actual MediaRecorder behavior,
playback and visible interaction still need the manual check below. Unit/integration
checks do not substitute for that test. The temporary compiler was installed outside
the repository; it did not flash the board.

## Hardware and browser acceptance still needed

Follow [Arduino setup](arduino-setup.md):

1. Verify the printed module pins and jumper power distribution; upload the sketch.
2. Select the actual USB port and observe genuine touch/light/moisture readings.
3. Measure/save real dry/wet endpoints; confirm the saved plant profile uses raw light
   thresholds, then tune them under the demo lighting.
4. Test held touch, repeated pats, cooldown and unplug/replug while held.
5. Open localhost:5173, wake the plant, grant mic permission, select the Logitech mic,
   and check the six-second listening window and child question/reply.
6. Check permission denial, tab hiding, connection loss, multiple tabs and offline STT.
7. Select the Logitech camera index and leaf ROI; validate exposure and color results.
8. Verify stored history after a real reading and backend restart.

No actual sensor measurements, camera frames, microphone clips or live paid speech/LLM
requests were used in these checks. The child can use question buttons without speech
keys; live transcription needs ElevenLabs configuration.

## Deployment and optional integrations

- Local PostgreSQL persistence is tested; live Neon credentials were not used.
- Fetch.ai remains optional and disabled by default. Agent registration/remote delivery
  needs its configured seed and recipient; local sensors/UI do not depend on it.
- FreeWILi remains an optional legacy adapter, with its unfinished physical-reader work
  described in [hardware-bringup.md](hardware-bringup.md). The Arduino path now supplies
  the implemented sensor protocol instead.
- No hosting target, remote CI run, commit or push is claimed for this branch.
- Runtime viewer-token support is present; there is no production login/session UI.

## Deliberate limits

One configured plant, backend worker and replica. The database retry queue is bounded
and in memory; an accepted/buffered observation is not yet a durable commit. Readiness
reports database failures. Use `/history` to recover records after reconnect; historical
touch events are never replayed into microphone requests. The first connected UI is
the listening client, so keep only the intended demo tab connected.

The moisture percentage is a calibrated relative scale; raw light is not lux. A
floating analog input cannot prove a sensor wire is connected. Webcam color proportions
are a cropped-image heuristic, not disease diagnosis. Raw images and child microphone
clips are not persisted by this backend; microphone clips are sent to the configured
speech provider for transcription. Generated plant speech uses the existing local cache.
