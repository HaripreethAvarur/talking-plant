# Talking Plant

Arduino sensors and a laptop webcam feed a FastAPI backend. The backend stores
observations and care events, decides the plant's mood, and sends live updates to
the React frontend. A touch starts a six-second microphone window; the existing
speech and conversation modules handle the child's question and the plant's reply.

## Run locally

```sh
# First setup only; keep an existing .env and its keys.
cp .env.example .env
make install
make local                       # Docker backend + persistent local PostgreSQL
npm --prefix frontend install
npm --prefix frontend run dev    # second terminal: http://localhost:5173
make arduino-mock                # third terminal: 24-second sensor + touch demo
```

Click **Tap to wake up** and grant microphone permission before starting the demo.
The simulated pat arrives after four seconds. `make touch` sends another simulated
pat (allow ten seconds between pats). One connected browser records; keep the demo
tab in front. Blank speech keys allow sensor testing and question buttons; actual
voice transcription requires an ElevenLabs key. ASI replies have a scripted fallback.

`PORT` controls the Docker backend port, and `BACKEND_URL` in `.env` must point to it.
For example, with `PORT=18080`, set `BACKEND_URL=http://127.0.0.1:18080`.
The frontend reads that URL when Vite starts. Restart Vite after changing it.
The backend root `/` is not a webpage: use `/docs`, `/health`, or `/ready` there;
the plant UI is on port **5173**.

For native backend development, run `make native` (default port 8000; override with
`PORT=18080 make native`). Set `DATABASE_URL=sqlite:///./plant.db` in `.env` for native
persistence, or use a PostgreSQL URL. An empty URL uses bounded in-memory history.
`python -m backend.server` is a compatibility entrypoint to the same backend,
using `SERVER_PORT`. Run only one backend process for a given plant/database.

## Real hardware

Follow **[Arduino wiring and setup](docs/arduino-setup.md)** for the UNO R4 WiFi,
Grove touch v1.1, light v1.2, moisture v1.4, and Logitech webcam.
The supplied sketch defines the USB serial protocol; no WiFi setup is needed.
Moisture percentage remains unknown until you save real calibration measurements.

```sh
make install-arduino
make arduino-devices
# Upload firmware/talking_plant/talking_plant.ino with Arduino IDE first.
make arduino ARGS='--port /dev/cu.usbmodemYOUR_PORT'
```

## Main files and interfaces

| Location | Purpose |
|---|---|
| `firmware/talking_plant/` | Arduino sampling, touch debounce, USB JSON protocol |
| `backend/sensors/` | Arduino reader, mock/replay modes, calibration, optional legacy FreeWILi adapter |
| `backend/vision/` | Webcam capture and leaf color baseline |
| `backend/api.py`, `backend/ui.py` | Unified REST/WebSocket backend and UI adapter |
| `backend/agent/`, `backend/database/` | Mood decisions, touch gating, persistent history |
| `backend/conversation/`, `backend/speech/` | Existing replies, STT, TTS and offline fallbacks |
| `frontend/` | React plant, live gauges, microphone/touch handler |
| `shared/` | Validated contracts, schemas, examples and plant profile |

The UI uses `/ws`, `/api/health`, `/api/stt` and `/audio`. Native bridges post to
`/api/v1/sensor-readings`, `/api/v1/touch-observations`, and `/api/v1/leaf-observations`.
Detailed state/history remain at `/api/v1/plants/plant-1/...` and `/ws/plants/plant-1`.
See [integration contracts](docs/person2-integration.md).
The old `/api/plant-state` mock override requires `DEMO_MODE=true` and is not persisted;
use `make arduino-mock` to exercise the complete pipeline.

## Checks

```sh
make test
make lint
make schemas
.venv/bin/python -m unittest discover -s backend/tests -t .
npm --prefix frontend run build
```

See [verification and remaining work](docs/remaining-work.md) for what has actually
been checked and what still needs physical hardware, microphone permission or keys.
