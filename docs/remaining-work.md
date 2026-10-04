# Remaining work and known limits

## Still needs the real hardware and a browser

Automated tests cover the code paths below with simulated data. None of them used a real
sensor reading, camera frame, microphone clip or paid speech/LLM request.
Follow [Arduino setup](arduino-setup.md):

1. Verify module pins and power distribution; upload `hardware/talking_plant_hub`.
2. Select the USB port and watch genuine touch, light and moisture readings.
3. Measure and save dry/wet calibration; tune the raw light thresholds under demo lighting.
4. Test a held touch, repeated pats, the cooldown, and unplug/replug while held.
5. Open localhost:5173, wake the plant, allow the microphone, pick the right mic, and
   check the listening window and a spoken question and reply.
6. Check permission denial, a hidden tab, connection loss, multiple tabs and offline STT.
7. Choose the camera index and leaf region; check exposure and colour results.
8. Confirm history survives a backend restart with real readings.

## Needs credentials or an external target

- Neon: run against a real `DATABASE_URL` (local PostgreSQL and SQLite are tested).
- ElevenLabs and ASI:One: run `python -m backend.conversation.try_questions` and
  `python -m backend.speech.pregenerate` with real keys.
- Fetch.ai: optional and off by default; registration and delivery need a seed and target.
- Hosting: no remote deployment has been made; see [deployment.md](deployment.md).

## Deliberate limits

- One plant, one backend worker. The database retry queue is bounded and in memory, so an
  accepted observation is not yet a durable commit; `/ready` reports database failures.
- The first connected UI tab is the one that records after a touch.
- Moisture is a calibrated relative scale; raw light is not lux. A floating analog input
  cannot prove a sensor wire is connected.
- Leaf colour proportions are a cropped-image heuristic, not a diagnosis.
- Images and microphone clips are never stored; clips are sent to ElevenLabs for
  transcription. Generated speech is cached locally in `backend/speech/cache/`.
