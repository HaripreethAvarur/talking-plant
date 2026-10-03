# Person 2 integration (schema 1.0)

Your ownership remains `frontend/`, `backend/conversation/`, and `backend/speech/`.
Person 1 supplies state, observations, history and suggested scripts. No microphone, STT,
LLM conversation, TTS or character animation implementation is included.

## Connections

Local HTTP: `http://127.0.0.1:8000`; WebSocket: `ws://127.0.0.1:8000/ws/plants/plant-1`.
Remote: use the deployed HTTPS origin and WSS equivalent. Configure your frontend API
origin independently of `BACKEND_URL`, which configures the native bridge.
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
    if (event.suggested_text) queuePlantSpeech(event); // Person 2 owns wording and voice.
  }
};
```

Dry soil produces a `mood_changed` event with mood `thirsty`, reason, and suggestion
`I'm thirsty.`. A sustained moisture rise produces a silent `mood_changed` to `grateful`
plus one `watering` event suggesting `Thank you.`. Speak from **events with a non-null
suggested_text**, never directly from repeated mood/state updates. Event IDs are UUIDs,
and `observation_id` links a derived event to the originating reading. Timer events use
`source=backend` and may have no observation ID. Final scripts remain your choice.

Reconnect gets current state, not an automatic backlog. Fetch `/history` (newest first,
limit 1–1000, offset pagination), filter `record_type` to `mood_changed`/`watering`, and
deduplicate using the same IDs. Choose an age limit for speech so old events do not speak
on first launch. History also includes `sensor`, `leaf`, and `sensor_health` records.
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
| ChildUtterance | Validated integration-only transcript envelope with identity, source, language and text; no Person 1 endpoint processes it |
| ConversationContext | Profile, current state, recent 20 events and integration guidance |
| StreamMessage | Snapshot/update envelope with state and events |

Every contract has `schema_version="1.0"`; unknown fields/versions are rejected. Timestamps
must include a timezone. `source` distinguishes mock, replay, hardware, image_file and backend;
sensor readings allow only the first three. Missing measurements are null with a status,
never invented zeroes. Zero is valid only with `status=ok` (e.g. actual zero light).
Moisture includes raw + relative_percent + calibration_id; uncalibrated raw can be kept with
`status=uncalibrated`, relative_percent=null. Light is `{value,unit,status}`, with unit
`lux` only for a verified lux output or an explicitly simulated lux value. `raw` is not lux.

Stable moods: `happy`, `thirsty`, `too_dark`, `unwell`, `grateful`.
Health: `ok`, `missing`, `disconnected`, `stale`, `error`, `uncalibrated`.
The initial happy mood is a neutral display default, not proof of plant health. Display
sensor health alongside mood. Stale/disconnected states null measurements; old latches may
remain. Leaf proportions describe color pixels, not disease diagnoses, wilting, or calibrated
probabilities. Raw audio and images are neither accepted nor stored by this backend.

`GET /context` is the context input for your conversation pipeline; `ChildUtterance` is the
agreed transcript shape, not an implementation of that pipeline. `/docs` provides OpenAPI.
