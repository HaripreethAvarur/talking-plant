# Verification and remaining work

Implemented on `person1-backend`. Teammate-owned frontend/conversation/speech files were
left unchanged. No remote deployment or successful external agent registration is claimed.

## Actually run on 2026-10-02 (America/Detroit)

- 33 automated tests passed on Python 3.13.7/macOS, including optional OpenCV tests.
  One upstream Starlette/AnyIO deprecation warning remains; no failing tests.
- Ruff passed. JSON schemas and sample/fixture generation ran successfully.
- Core and development hashed dependency locks installed. Optional FreeWILi/uAgents locks
  resolved; published SDK wheels were inspected to verify methods/signatures used.
- Docker image built successfully on Linux ARM64 through Docker Desktop.
- Isolated Compose backend + PostgreSQL 17.5 stack became healthy on localhost:18080.
  Port 8000 was already occupied and its existing service was left untouched.
- Live native HTTP/WebSocket smoke: snapshot received, all 24 readings accepted, request
  retries deduplicated, exactly one thirsty suggestion and one thank-you suggestion.
- Both test containers were removed/recreated with the named database volume preserved;
  original speech event IDs were found in database history afterward.
- With the actual test PostgreSQL stopped, `/health` stayed 200, `/ready` returned 503,
  ingestion accepted a fresh observation, and live state updated.
  After PostgreSQL restarted, that buffered observation appeared in persistent history.
- Actual native replay CLI: all 24 timestamped fixture rows accepted, producing exactly
  one `I'm thirsty.` and one `Thank you.` suggestion.
- Tests covered noisy readings, isolated spikes, reconnect/gap/calibration reset, ordering,
  stale/missing/future data, gratitude expiry/rearming, restart dedup, DB outage/queue bounds,
  auth, disabled/enabled demo controls, slow subscribers, missing Fetch SDK, and secret redaction.
  The uAgents worker contract was tested with an SDK double; this does not claim network delivery.
- Synthetic yellow image file and invalid/dark/cropped-image tests passed. Missing-camera
  behavior used a test double; an actual camera was not opened. Missing-image CLI returned
  an error observation with null proportions and no crash.
- Hardware diagnostics ran without SDK installed and reported candidate macOS ports plus
  the actionable optional-dependency message. No board or sensor readings were obtained.

Local acceptance uses an isolated Compose project `talking-plant-person1-check`. Its test
volume is separate from the normal `talking-plant` project's care history. The test stack
was stopped after verification; its volume was preserved and port 18080 was released.

## Still requires tomorrow's hardware

Follow [hardware-bringup.md](hardware-bringup.md), including the H1–H6 TODO register:

- Identify board generation/firmware and sensor model; confirm matching SDK family.
- Verify supply/output voltage, physical pins, interface and common ground before connecting.
- Complete the real moisture/light reader methods from verified docs and measurements;
  currently they intentionally report missing rather than supplying fabricated data.
- Measure/save dry and wet endpoints and bind calibration to the actual device identity.
- Establish whether light is raw or lux and tune thresholds in matching units.
- Physically test disconnect/reconnect and noisy dry→watered behavior.
- Grant macOS camera permission, choose index/leaf region and check exposure.

The legacy SDK's device discovery/open/close/button methods are implemented and source-checked,
but remain physically untested. New OneWili firmware requires the H1 adapter update. No
serial JSON stream, baud rate, ADC pin or sensor return format is assumed.

## Still requires credentials or an external target

- Neon: no connection URL/credentials supplied, so no live Neon test ran.
- Fetch.ai: disabled by default. Real documented uAgents adapter and optional lock are
  supplied; registration and target-agent delivery remain untested without a configured
  seed/recipient. `/ready` reports runtime status accurately; local operation is independent.
- Deployment: no hosting target configured. HTTPS/WSS, host probes, secret injection and
  remote bridge round-trip need the deployment smoke test in [deployment.md](deployment.md).
- GitHub CI: workflow is implemented but has not run remotely; this branch has not been pushed.
- Person 2: implement UI, conversation, STT/TTS and animation, consuming the contracts in
  [person2-integration.md](person2-integration.md). No code was added in their owned directories.

## Deliberate limits

One configured plant, worker and replica; state/WS queues are in memory. The 1,000-batch
database retry buffer is bounded and not crash-durable. API acceptance is not a durable
commit. Restart while DB is unreachable cannot restore its checkpoint; it starts from
the seed profile and fresh in-memory state. Readiness reports the outage. Remote read auth
is a shared demo viewer token, not user accounts. Leaf color heuristics are not diagnoses
or wilting detection; validated model work remains behind `LeafModel` / TODO(MODEL).
