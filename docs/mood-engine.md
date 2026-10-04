# Deterministic rules and persistence

`backend/agent/mood.py` is the only watering detector. Bridge readings are unsmoothed;
the backend uses a configurable median of the latest 3 valid relative moisture samples.
Timing uses observation timestamps; the service timer expires grateful and marks stale
even with no incoming data. Default thresholds are demonstrative, not horticultural advice.
Edit `shared/plant-profile.json` before the initial seed or use the profile command described
in deployment.md and restart the single worker for an existing database.

Priority: **grateful → thirsty → soggy → unwell → too_dark → sleepy → happy**.
Soggy enters when smoothed moisture stays at or above `soggy_enter` for `soggy_seconds`
(default 120 s) and exits below `soggy_exit`. Darkness between `night_start_hour` and
`night_end_hour` in the profile's timezone (21:00–07:00 by default) is `sleepy`, which is
silent; the same darkness during the day is `too_dark`. Registering a plant applies the
moisture bands for its type (succulent 15/22 dry, 60/70 soggy; plant 30/40, 80/90;
tree 25/35, 85/92). Grateful is a live moment only and is never a care-log label. A dry condition enters at
≤30% for 3 seconds and exits at ≥40% for 3 seconds. The hysteresis band retains the latch.
Darkness enters at ≤100 lux for 3 seconds and exits at ≥150 lux for 3 seconds, only when
reading and profile light units match. Raw-unit light requires explicitly chosen raw thresholds.
Leaf color concern requires 2 confirming observations with total yellow/brown ≥0.35;
it clears after 2 observations ≤0.25, and expires after 300 seconds without a usable update.

Watering requires a ≥20-point rise above a recent smoothed baseline, sustained for 2 seconds,
within a 30-second window. Each episode emits exactly one watering event and grateful mood
for 5 seconds. Grateful's mood change has no speech suggestion; the watering event suggests
thanks. After an episode, detection rearms only once persistent dry soil is observed after
the 30-second watering cooldown. This deliberately avoids multiple thanks from plateaus or
successive pours in one episode. Initial continuous observations can detect a rise even if
the original baseline was not thirsty. State transitions have independent per-mood speech
cooldowns (30 seconds), so a valid state can change without repeating a spoken suggestion.

Missing moisture, source/device/calibration changes, stale gaps (>5 seconds), and restarts
reset smoothing and watering continuity. Reconnecting at a wet value cannot compare against
the pre-disconnect dry baseline. Missing data retain existing care latches; they cannot
start dry or watering evidence. This is why a stale thirsty mood may stay thirsty until
fresh data clear it. Health changes are separate silent events. Optional leaf concern
expires; grateful still expires during disconnection. No inference is made from a null value.

Same/older sensor timestamps are ignored; leaf ordering is independent. Older-than-stale
readings are ignored, and timestamps over the permitted future skew are rejected. Replay
rebases historical fixture intervals to current wall time; run only one producer per plant.
The implementation supports one configured seeded plant per process, and rejects other IDs.

Observation IDs deduplicate requests in a bounded 10,000-entry memory cache and database
primary keys. Reuse an ID only for the same payload. Events and observations plus the latest
checkpoint are written in one transaction. Restart restores moods, cooldowns, and last
observation time while discarding continuity windows. Persistent database dedup prevents
retry records across restarts. Unknown old IDs during a DB outage may escape memory dedup
after eviction; out-of-order timestamps still prevent old sensor data changing the engine.

The service writes in a separate worker thread, retrying roughly once per second. Its queue
holds 1,000 observation/timer batches, evicting oldest when full; `/ready` exposes queue size
and drops. At 1 Hz this is roughly 16 minutes, less with more producers. In-memory history
retains the latest 1,000 records (observations and events), not 1,000 seconds. Process death
loses unflushed batches; database outage plus overflow loses evicted records permanently.
An accepted API response is not a durable-write acknowledgement. The bridge retries each
HTTP request three times with the same ID, then drops it and reports the drop; it has no
offline disk spool. Database URLs and exception details are never printed by the backend.

Fetch delivery is optional and best effort; backend history is authoritative. A future
production version should add a durable outbox, shared state/pubsub, per-user auth, and
backpressure. Until then use exactly one worker and one replica.
