# Backend API and contracts (schema 1.0)

One backend process (`python -m backend.server`, or `create_app` in `backend/api.py`)
serves the sensor API below and, through `backend/ui.py`, the React frontend's routes.

## React frontend routes

Run Vite on localhost:5173. It proxies `/api`, `/ws`, and `/audio` to `BACKEND_URL`
from the root `.env` (restart Vite after changes). `/ws` sends `plant_state`,
`speech_audio`, and `listen_request` messages. `/api/health` reports speech support;
`/api/stt` accepts a capped audio clip and returns a `ChildUtterance`.
The frontend forwards that transcript on `/ws` for a reply grounded in live state
and recent stored care events. Blank keys preserve on-screen question fallbacks.

After the wake button grants mic permission, `listen_request` opens a six-second
recording window. Its fields are `schema_version`, `type`, `event_id`, `plant_id`,
`timestamp`, and `duration_ms`. The frontend drops duplicate/old events and cancels
recording on hidden pages or disconnection. Only the first connected UI gets touch
requests. A held pad and a reconnect do not automatically reopen the mic.

`POST /api/v1/touch-observations` uses ingestion auth. Touch observations carry
`pressed` (boolean when ok; null when unavailable), `status`, and the usual
observation identity including optional `session_id`. They and derived `touch`
events are persisted in care history. These events have no suggested speech.
Full `/ws/plants/plant-1` messages also include optional `state.touch`.

For a token-protected demo, the UI reads `plantViewerToken` from sessionStorage;
set it at runtime using browser developer tools, then reload. Do not put the ingestion
token in the browser. No login screen is included. Local mode needs no tokens.
The detailed API described below remains available alongside these UI routes.

## Sign-up, care log and leaderboard

| Route | Auth | What it does |
|---|---|---|
| `POST /api/plant` | viewer | Register the kid's plant (`PlantRegistration`); the profile takes its name and moisture bands |
| `GET /api/plant` | viewer | The registration, or 404 before sign-up |
| `GET /api/v1/care-log` | viewer | The last 24 care-log rows (`HourlyReading`), oldest first |
| `POST /api/v1/care-log/log-now` | ingestion | Record a row now (409 before sign-up) |
| `POST /api/v1/care-log/label-day?day=YYYY-MM-DD` | ingestion | Label a local day (default today) and purge old data |
| `GET /api/leaderboard?limit=20` | viewer | `{days, you, entries: LeaderboardEntry[]}`; 503 without a database |

`/api/health` also reports `registered`, `username`, `database`, `demo_mode` and the
plant's `thresholds` (`dry`, `soggy` moisture %). `GET /context` includes `hourly`, the
same rows the chat uses.

## Connections

Local HTTP: `http://127.0.0.1:8000`; WebSocket: `ws://127.0.0.1:8000/ws/plants/plant-1`.
Remote: use the deployed HTTPS origin and WSS equivalent. Configure your frontend API
origin in production; the local Vite proxy and native bridge both read `BACKEND_URL`.
Set backend `CORS_ORIGINS` to a JSON array of exact frontend origins, including port.

Local mode allows empty tokens. Remote mode requires **two distinct secrets**:
`INGESTION_TOKEN` belongs only on the native bridge/server; `VIEWER_TOKEN` is read-only.
For the hackathon, enter the viewer token at runtime and keep it in memory, or use your
server-side session proxy. Do not bundle either secret into compiled frontend assets.
Production per-user sessions/authorization are not implemented.

All read routes use `Authorization: Bearer <VIEWER_TOKEN>` when configured. Ingestion and
demo controls use `Authorization: Bearer <INGESTION_TOKEN>`. Browsers authenticate a
WebSocket with its first JSON frame, within 5 seconds, before any state is sent:
`{"type":"auth","token":"<VIEWER_TOKEN>"}`. No tokens in URLs/logged query strings.
Browser WebSocket origins are checked separately from CORS; absent Origin is permitted
for native clients, but token validation still applies.

## REST

```sh
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/ready
curl -H "Authorization: Bearer $VIEWER_TOKEN" http://127.0.0.1:8000/api/v1/plants/plant-1/state
curl -H "Authorization: Bearer $VIEWER_TOKEN" http://127.0.0.1:8000/api/v1/plants/plant-1/context
curl -H "Authorization: Bearer $VIEWER_TOKEN" 'http://127.0.0.1:8000/api/v1/plants/plant-1/history?limit=100&offset=0'
```

Ingestion example (terminal/native bridge only). Generate a fresh timestamp; checked-in
samples are historical and intentionally rejected as stale when posted unchanged:

```sh
.venv/bin/python -c 'from backend.sensors.simulator import scenario_reading; print(scenario_reading("dry",0).model_dump_json())' > /tmp/plant-reading.json
curl -H "Authorization: Bearer $INGESTION_TOKEN" -H 'Content-Type: application/json' \
  --data-binary @/tmp/plant-reading.json http://127.0.0.1:8000/api/v1/sensor-readings
```

`POST /api/v1/leaf-observations` accepts `LeafObservation`. Replies to either ingestion
route contain `status` (`accepted`, `duplicate`, `stale`, `out_of_order`), `event_id`,
and an `events` array. Accepted is an in-memory acknowledgement; `persistence=buffered`
means the database write is pending. 401 means wrong token, 404 unknown plant, 422 invalid
schema/future timestamp. Retries must reuse the exact observation and event ID.

`/health` is process liveness. `/ready` reports database status, pending/dropped batches,
and Fetch status. It returns 503 only when `DATABASE_REQUIRED=true` and the DB is unavailable.
Demo: `POST /api/v1/demo/scenario` with `{"scenario":"dry-to-watered"}` runs a 24-second
sequence only with `DEMO_MODE=true`; otherwise 404. Concurrent scenarios return 409.
Stop another bridge before using demo controls; concurrent producers are not reconciled.

## WebSocket and speech

On connection, receive `{schema_version:"1.0", type:"snapshot", state:PlantState, events:[]}`.
Every accepted observation and timer-driven state change produces
`{schema_version:"1.0", type:"update", state:PlantState, events:PlantEvent[]}`.
Update messages can have no events; this still updates displayed measurements.

Example integration sketch (you supply `renderPlant` and your speech handler):

```js
const seen = new Set(); // Persist processed IDs across reconnects for the demo session.
const socket = new WebSocket(`${wsOrigin}/ws/plants/plant-1`);
socket.onopen = () => {
  if (viewerToken) socket.send(JSON.stringify({type: "auth", token: viewerToken}));
};
socket.onmessage = ({data}) => {
  const message = JSON.parse(data);
  renderPlant(message.state);
  for (const event of message.events) {
    if (seen.has(event.event_id)) continue;
    seen.add(event.event_id);
    if (event.suggested_text) queuePlantSpeech(event);
  }
};
```

Dry soil produces a `mood_changed` event with mood `thirsty`, a reason, and the thirsty
line from `MOOD_LINES` in `backend/conversation/scripted.py`. A sustained moisture rise
produces a silent `mood_changed` to `grateful` plus one `watering` event carrying the
grateful line. Speak from **events with a non-null
suggested_text**, never directly from repeated mood/state updates. Event IDs are UUIDs,
and `observation_id` links a derived event to the originating reading. Timer events use
`source=backend` and may have no observation ID. All wording lives in `scripted.py`.

Reconnect gets current state, not an automatic backlog. Fetch `/history` (newest first,
limit 1–1000, offset pagination), filter `record_type` to `mood_changed`/`watering`, and
deduplicate using the same IDs. Choose an age limit for speech so old events do not speak
on first launch. History also includes `sensor`, `leaf`, `touch_observation`, `touch`, and `sensor_health` records.
When `storage=bounded_memory`, older history may be unavailable. Slow WebSocket clients
are closed with code 1013 after their 64-message queue fills; reconnect and recover history.

## Exact shared contracts

The authoritative validators are `shared/contracts.py`. Machine-readable Draft 2020-12
JSON schemas are in `shared/schemas/`; exact sample JSON is in `shared/samples/`:

| Contract | Contents |
|---|---|
| SensorReading | UUID event_id, plant_id, timezone-aware timestamp, mock/replay/hardware source, device_id, moisture and light |
| LeafObservation | Observation identity, status, selected region, method, nullable yellow/brown pixel proportions, limitations |
| PlantState | Stable mood, reason, independent sensor_health, nullable readings, smoothed relative moisture, last_sensor_at, last_event_id, optional leaf |
| PlantEvent | UUID, timestamp, plant_id, source, kind, mood, reason, nullable suggested_text and observation_id |
| ConversationContext | Profile, current state, recent 20 events and integration guidance |
| StreamMessage | Snapshot/update envelope with state and events |
| UIPlantState | `/ws` frame for the UI: mood, optional message, moisture/light %, leaf_issues (null when the camera has no recent look), sensor health |
| SpeechAudio | `/ws` frame: text plus a cached `/audio/...` URL, or null for browser speech |
| ChildUtterance | Sent by the UI on `/ws`: question text and source (`stt`, `button`, `typed`) |
| ListenRequest | `/ws` frame asking the first UI to record for `duration_ms` after a touch |
| PlantRegistration | A kid's plant: username (the identity, no login), plant name, type (`succulent`, `plant`, `tree`), US ZIP |
| HourlyReading | One hour of the care log: sun %, water %, air AQI, Ollama's health text, ASI's mood label, and `day_mood` on the day's last row |
| LeaderboardEntry | Rank, plant, and happy days in the last 7 (score = happy days / 7) |

Every sensor-side contract has `schema_version="1.0"`; unknown fields/versions are rejected. Timestamps
must include a timezone. `source` distinguishes mock, replay, hardware, image_file and backend;
sensor and touch observations allow only the first three. Missing measurements are null with a status,
never invented zeroes. Zero is valid only with `status=ok` (e.g. actual zero light).
Moisture includes raw + relative_percent + calibration_id; uncalibrated raw can be kept with
`status=uncalibrated`, relative_percent=null. Light is `{value,unit,status}`, with unit
`lux` only for a verified lux output or an explicitly simulated lux value. `raw` is not lux.

Stable moods: `happy`, `thirsty`, `too_dark`, `unwell`, `grateful`.
Health: `ok`, `missing`, `disconnected`, `stale`, `error`, `uncalibrated`.
The initial happy mood is a neutral display default, not proof of plant health. Display
sensor health alongside mood. Stale/disconnected states null measurements; old latches may
remain. Leaf proportions describe color pixels, not disease diagnoses, wilting, or calibrated
probabilities. Raw images are not accepted/stored. `/api/stt` forwards capped audio
for transcription without storing it in our database.

`GET /context` returns the profile, state and recent events used for replies. `/docs`
provides OpenAPI.

## Database tables

Migration 1 (live pipeline): `plant_profiles`, `care_records` (every observation and
event as JSON) and `plant_checkpoints`. Migration 2 (care log): `plants`, keyed by
username, and `hourly_readings`, one row per plant per hour, unique on
`(username, hour)` and deleted with its plant.

`Store.purge(now)` keeps 30 days of hourly rows and care events, and 24 hours of raw
per-second sensor, touch and leaf records (they only need to outlive restart
de-duplication). The leaderboard counts days whose `day_mood` is `happy`
within the last 7 days; plants with equal counts share a rank.
