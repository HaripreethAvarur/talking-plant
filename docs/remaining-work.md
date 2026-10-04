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

## Credentials and external services (checked 2026-10-03)

- Neon (Postgres 18, pooled endpoint): migrations run, upserts and constraints verified in a
  rolled-back transaction. The pooler rejects startup options, so the query timeout is set
  per transaction.
- ElevenLabs (free plan, 10,000 characters a month): only default voices work through the
  API, so the voice is Jessica. Speech took 1.4 s; transcribing it back gave the exact text.
  Run `python -m backend.speech.pregenerate` (about 930 characters) once the wording is final.
- ASI:One: `asi1-mini` answers in about 0.5 s median, 0.7 s slowest, with or without 24
  hourly rows in the prompt (`python -m scripts.asi_latency`); `asi1` is slower and more
  often breaks the length rule.
- Plant Care Agent: starts, publishes the chat protocol and registers on the Almanac API.
  Its mailbox must be connected once from the Agent inspector (needs an Agentverse login).
- Ollama: `moondream` runs on this 8 GB laptop (about 17 s a photo once loaded) but is
  not very accurate, e.g. it calls a golden pothos's natural yellow streaks unhealthy.
  ASI weighs it against the sensors. Use `llama3.2-vision` on a machine with more RAM.
- Air quality: Open-Meteo by ZIP (via zippopotam.us), no key; cached for 30 minutes.
- Fetch event mirror: optional and off by default; it needs a seed and a target agent.
- Hosting: no remote deployment has been made; see [deployment.md](deployment.md).

## Not done

- The hub sketch can light an LED for unhappy moods (`ArduinoSerialAdapter.write_mood`),
  but the bridge doesn't send moods to it yet.
- Night is a fixed window (21:00–07:00 local, set in the profile), not real sunset times.
- Without `DATABASE_URL`, a registration lasts only until the backend restarts.

## Deliberate limits

- One plant, one backend worker. The database retry queue is bounded and in memory, so an
  accepted observation is not yet a durable commit; `/ready` reports database failures.
- The first connected UI tab is the one that records after a touch.
- Moisture is a calibrated relative scale; raw light is not lux. A floating analog input
  cannot prove a sensor wire is connected.
- Leaf colour proportions are a cropped-image heuristic, not a diagnosis.
- Images and microphone clips are never stored; clips are sent to ElevenLabs for
  transcription. Generated speech is cached locally in `backend/speech/cache/`.
