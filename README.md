# Talking Plant

Arduino sensors and a laptop webcam feed a FastAPI backend. The backend decides the
plant's mood, stores care history, and sends live updates to a React character. Patting
the touch pad opens the microphone; the child's question gets a short, grounded reply
in the plant's voice.

## Run locally

Commands are shown with `python`; inside the virtual environment that's
`.venv/Scripts/python` on Windows and `.venv/bin/python` on macOS/Linux.
The `make` targets do the same thing where `make` is available.

```sh
cp .env.example .env                              # keep an existing .env and its keys
python -m venv .venv
.venv/Scripts/python -m pip install --require-hashes -r requirements-dev.txt
npm --prefix frontend install

python -m backend.server                          # terminal 1: backend on :8000  (make native)
npm --prefix frontend run dev                     # terminal 2: open http://localhost:5173
python -m backend.sensors.bridge --mode arduino-mock --count 24   # terminal 3 (make arduino-mock)
```

Click **Tap to wake up** and allow the microphone. The simulated pat arrives after four
seconds and the soil is "watered" after eight. `python -m scripts.touch` sends another pat
(allow ten seconds between pats). With blank speech/LLM keys the plant still works: the
question buttons replace the microphone, replies come from scripted lines, and the
browser's own voice speaks.

Set `DATABASE_URL=sqlite:///./plant.db` in `.env` to keep history between runs, or a Neon
URL for the shared database. Blank keeps a bounded in-memory history.
`docker compose up` (`make local`) runs the backend with a local PostgreSQL instead.

## Real hardware

Follow **[Arduino setup](docs/arduino-setup.md)** for the UNO R4 WiFi, the Grove
touch, light and moisture sensors, and the webcam.

```sh
python -m pip install -r requirements-arduino.txt
python -m backend.sensors.arduino                 # list USB ports
# Upload hardware/talking_plant_hub/talking_plant_hub.ino with Arduino IDE first.
python -m backend.sensors.bridge --mode arduino --port COM3
```

## Plant Care Agent (Agentverse and ASI:One)

```sh
python -m pip install --require-hashes -r requirements-fetch.txt
python -m backend.agent.chat_agent                # with the backend running
```

It answers chat messages as the plant, from its live readings. The first time, open
the "Agent inspector" link it prints, choose **Connect → Mailbox** and sign in to
Agentverse; after that, **Chat with Agent** on Agentverse opens it in ASI:One. Keep it
running while chatting. Its address is fixed by `AGENT_SEED` in `.env`.

## Layout

| Location | Purpose |
|---|---|
| `hardware/talking_plant_hub/` | Arduino sketch: samples sensors, sends one JSON line per second |
| `backend/sensors/` | USB bridge, simulated and replay modes, moisture calibration |
| `backend/vision/` | Webcam capture and the leaf colour baseline |
| `backend/agent/` | Mood rules (`mood.py`), touch gating, the ASI:One chat agent, optional Fetch mirror |
| `backend/service.py` | Runs the mood engine, history, database writes and broadcasts |
| `backend/api.py` | The one FastAPI app: sensor ingestion, state, history, demo controls |
| `backend/ui.py` | The UI's routes: `/ws`, `/api/health`, `/api/stt`, `/audio` |
| `backend/transport.py` | Shared auth, WebSocket handshake and client queues |
| `backend/conversation/` | Replies (ASI:One), safety checks, every scripted line |
| `backend/speech/` | ElevenLabs speech-to-text and voice, with an offline cache |
| `backend/database/` | Tables, migrations and the store (Neon/PostgreSQL or SQLite) |
| `backend/config.py` | Every setting, read from `.env` |
| `frontend/` | React character, gauges, microphone and touch handling |
| `shared/` | Message contracts, generated schemas and samples, plant profile |

Routes and message formats are in [docs/api.md](docs/api.md).

## Checks

```sh
python -m pytest -q                               # make test
python -m ruff check backend shared scripts tests # make lint
python -m scripts.export_contracts                # make schemas (after changing contracts)
python -m backend.conversation.try_questions      # sample replies
python -m scripts.asi_latency                     # ASI:One speed with 24 hourly rows (uses the key)
npm --prefix frontend run build
```

`make lock` regenerates the hashed requirement locks for every platform (needs `uv`).
See [remaining work](docs/remaining-work.md) for what still needs real hardware or keys.
