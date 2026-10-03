# Backend deployment and local fallback

Prepared container artifacts are provided; no remote target is configured or claimed live.
Use **one worker and one replica**: state, dedup cache, retry buffer and WebSocket queues
live in memory. PostgreSQL checkpoints/history persist, but are not inter-worker pubsub.
The host bridge stays native on macOS and talks HTTP(S) to the backend.

## Local tonight

Python 3.13.7 is the tested runtime. From the repository root:

```sh
cp -n .env.example .env
make install
make local
make replay
```

`make local` builds the backend and starts PostgreSQL with health checks. It binds only
`127.0.0.1:8000`; PostgreSQL has no published host port. Its named `plant-data` volume
survives `make stop` / `docker compose down`. Do not use `down -v` to retain care history.
Local-only DB password defaults to `local-demo-only`; `.env` secret fields are empty.
If overriding the local password, use URL-safe characters because Compose assembles the URL.

`make mock ARGS='--scenario dry-to-watered --count 24'` supplies the same demo without a
fixture. Other scenarios: healthy, dry, watered, dark, noisy, disconnected. `--count 0`
(default) streams at roughly one Hz until Ctrl-C. Run only one bridge/demo producer at a time.
For a repeat demo, wait at least the 30-second watering cooldown before the dry phase.

`make smoke ARGS='--save-events /tmp/plant-events.json'` validates the live sequence and
WebSocket delivery. Start from an idle/rearmed state. Then:

```sh
docker compose restart backend
docker compose up -d --wait
make smoke ARGS='--verify-events /tmp/plant-events.json'
```

Without Docker: `DATABASE_URL=sqlite:///./plant-demo.db make native` provides durable local
fallback; or `make native` with empty DATABASE_URL gives explicitly nonpersistent memory
mode. SQLite is for development tests/fallback, not the deployed configuration.
In a second terminal run `make replay`. Core operation never requires CV, sensors or sponsor keys.

## Migrations and profiles

Versioned migrations live in `backend/database/migrate.py` and table definitions in
`schema.py`; version 1 creates `plant_profiles`, `care_records`, and `plant_checkpoints`.
The `schema_migrations` table records applied versions. Migrations run transactionally
on service startup and retry after DB recovery. Startup DB failure degrades readiness
while leaving the core engine alive. You can run migrations explicitly before a rollout:

```sh
make migrate                                      # uses DATABASE_URL from .env
docker compose run --rm backend python -m backend.database.migrate
```

The seed profile is `shared/plant-profile.json` with configurable care, smoothing, debounce,
staleness and cooldown thresholds. It is inserted only when absent; deployment does not
overwrite existing profiles. To change an existing profile, validate/write it through:

```sh
.venv/bin/python -m scripts.profile /path/to/profile.json
# For the local Compose DB: copy profile into the container then apply it there.
docker compose cp shared/plant-profile.json backend:/tmp/profile.json
docker compose exec backend python -m scripts.profile /tmp/profile.json
docker compose restart backend
```

The first command needs a reachable DATABASE_URL; do not run it against a different DB
accidentally. Use the appropriate native or Compose variant. New processes restore latches
and cooldowns, but discard sensor continuity to prevent false watering on restart. See
`mood-engine.md` for queue bounds, history limits and acknowledged-but-unflushed data risks.

## Neon without a local PostgreSQL service

Put the actual Neon URL in `.env` as `DATABASE_URL`, retaining `sslmode=require`. Normal
`postgres://`, `postgresql://`, and `postgresql+psycopg://` forms are supported. Secrets stay
in `.env` or your host's secret manager. Then `make neon` uses **only** `compose.neon.yaml`;
do not combine it with `compose.yaml`. Stop the local stack first if using the same port.
This variant starts no local PostgreSQL service. Neon connectivity needs credentials and
network and is separately marked untested until an actual connection succeeds.

## Remote container host

1. `make build`; publish the image to your chosen host/registry using your normal release
   process. No target or registry is assumed here. Use the Dockerfile's start command:
   `uvicorn backend.api:create_app --factory --host 0.0.0.0 --port "$PORT" --workers 1`.
   Docker defaults PORT to 8000; the shell command expands host-injected PORT.
2. Set `DEPLOYMENT_MODE=remote`, two distinct `INGESTION_TOKEN` and `VIEWER_TOKEN` secrets,
   `DATABASE_URL` with TLS, `DATABASE_REQUIRED=true`, `DEMO_MODE=false`, and explicit
   `CORS_ORIGINS='["https://YOUR-FRONTEND"]'`. The app refuses remote configuration without
   both tokens. Enable demo controls only intentionally and keep the write token private.
3. Run migrations as a release command if the host supports it; the single worker also
   applies idempotent migrations on startup. Start just one replica.
4. Terminate HTTPS at the host's proxy/load balancer and enable WebSocket Upgrade forwarding.
   WSS uses the same origin/path. Set idle timeouts comfortably above quiet demo periods
   (e.g. 120 seconds); reconnect clients with history recovery. Do not expose the container's
   plain HTTP port directly. Keep the DB private and do not log environment dumps/DB URLs.
5. Liveness probe: `GET /health` (200 while process runs). Readiness: `GET /ready` (503 when
   required DB is down). Route traffic only after readiness, but do not restart the process
   just because a DB outage occurs or the in-memory retry buffer will be lost.
6. On the laptop set `BACKEND_URL=https://YOUR-HOST`, matching `INGESTION_TOKEN`, and run
   `make replay` / `make freewili`. Set frontend API/WSS origins and the separate viewer
   authentication. Smoke-test `/ready`, one full dry→watered cycle, WSS and a restart before
   calling the deployment successful.

If venue internet fails: `make stop` for any conflicting local service, `make local`, set
`BACKEND_URL=http://127.0.0.1:8000`, point frontend to local HTTP/WS, and run `make replay`.
Prebuild the image and cache dependencies before leaving. Native SQLite fallback avoids
Docker if needed. Remote and local care histories remain separate; no automatic merge exists.

## Optional Fetch.ai/uAgents

`backend/agent/fetch_adapter.py` uses documented `Agent`, `Model`, `on_event("startup")`,
`on_interval`, `Context.send` and `run`. The SDK runs in a spawned child process, because
its shutdown owns/cancels its event-loop tasks; it cannot cancel FastAPI's tasks. These APIs were checked against the
[official handlers guide](https://uagents.fetch.ai/docs/guides/handlers) and
[Agent reference](https://uagents.fetch.ai/refs/api/agent) on 2026-10-02.

Run `make install-fetch` to install the optional hashed lock into the native environment, then
set `FETCH_ENABLED=true`, a private `FETCH_SEED`, actual `FETCH_TARGET` agent address,
`FETCH_PORT`, and reachable `FETCH_ENDPOINT` for your deployment. If packaging into the
container, make an explicit derived image that installs this optional lock; default images
do not include sponsor/hardware SDKs. Enable only when external agent operation is intended.

The outbound uAgents model is `PlantSignal(schema_version="1.0", event_json=<PlantEvent JSON>)`.
It forwards structured events to the configured recipient. The core engine never depends
on registration/delivery. `/ready` reports `disabled` by default, `untested` if enabled but
missing/unstarted/failed, and `enabled` after runtime startup. Enabled does not prove remote
delivery. Queue length is 100, new events are dropped when full; sends are best effort, not a
durable outbox. External registration and end-to-end target delivery require a separate
real smoke test; no such test is claimed without configured credentials/recipient.

## Dependency updates and CI

Core/dev requirements are fully pinned with hashes; optional SDK locks are separate.
Python 3.13.7, PostgreSQL 17.5 and base image version tags are specified. For releases,
pin image digests in your deployment as well. Regenerate locks using pip 24.3.1 and
pip-tools 7.4.1 (`pip-compile --generate-hashes`); explicit greenlet makes Mac/Linux
SQLAlchemy dependencies consistent. CI runs backend tests, schema drift checks, image build,
PostgreSQL HTTP/WebSocket smoke and restart persistence. The workflow is prepared locally;
remote GitHub CI runs only after pushing this branch.
