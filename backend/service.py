import asyncio
import contextlib
from collections import OrderedDict, deque

from backend.agent.fetch_adapter import FetchAdapter
from backend.agent.mood import MoodEngine
from backend.agent.touch import TouchGate
from backend.database.store import Store
from shared.contracts import (
    ConversationContext,
    PlantEvent,
    PlantProfile,
    SensorReading,
    StreamMessage,
    TouchObservation,
    utcnow,
)


def record(payload, kind):
    data = payload.model_dump(mode="json")
    return {
        "event_id": str(payload.event_id),
        "plant_id": payload.plant_id,
        "kind": kind,
        "timestamp": payload.timestamp.isoformat(),
        "payload": {"record_type": kind, **data},
    }


class PlantService:
    def __init__(self, settings):
        self.settings = settings
        self.engine = MoodEngine(settings.profile())
        self.touch = TouchGate(
            settings.touch_cooldown_seconds, settings.touch_debounce_seconds, self.engine.t.stale_seconds
        )
        self.store = Store(settings)
        self.fetch = FetchAdapter(settings)
        self.db_status = "disabled" if self.store.engine is None else "unavailable"
        self.db_initialized = False
        self.pending = deque()
        self.dropped_batches = 0
        self.history = deque(maxlen=settings.history_limit)
        self.events = deque(maxlen=100)
        self.seen = OrderedDict()
        self.lock = asyncio.Lock()
        self.flush_lock = asyncio.Lock()
        self.subscribers = set()
        self.task = None
        self.demo_task = None
        self.stopping = asyncio.Event()

    async def start(self):
        try:
            restored = await asyncio.to_thread(self.store.start, self.engine.profile)
            if restored:
                profile, checkpoint = restored
                self.engine = MoodEngine(PlantProfile.model_validate(profile))
                self.touch.stale = self.engine.t.stale_seconds
                if checkpoint:
                    self.engine.restore(checkpoint)
                    self.touch.restore(checkpoint.get("touch_gate", {}))
                self.db_status = "ok"
                self.db_initialized = True
                rows = await asyncio.to_thread(
                    self.store.history, self.engine.profile.plant_id, self.settings.history_limit
                )
                for row in reversed(rows):
                    self.history.append(row)
                    if row["record_type"] in ("mood_changed", "watering", "sensor_health", "touch"):
                        self.events.append(
                            PlantEvent.model_validate({k: v for k, v in row.items() if k != "record_type"})
                        )
        except Exception:
            self.db_status = "unavailable"
        # Mark restored old measurements stale before the first snapshot.
        self._commit(None, self.engine.tick(utcnow()))
        await self.fetch.start()
        self.task = asyncio.create_task(self._run())

    def _broadcast(self, events):
        message = StreamMessage(type="update", state=self.engine.state, events=events).model_dump(mode="json")
        for queue in tuple(self.subscribers):
            if queue.full():
                # Disconnect slow clients explicitly; they recover missed events via history.
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
                self.subscribers.discard(queue)
            else:
                queue.put_nowait(message)

    def _commit(self, observation, events):
        if observation is None and not events:
            return
        rows = []
        if observation:
            kind = (
                "touch_observation"
                if isinstance(observation, TouchObservation)
                else ("sensor" if isinstance(observation, SensorReading) else "leaf")
            )
            rows.append(record(observation, kind))
        rows += [record(event, event.kind) for event in events]
        self.history.extend(r["payload"] for r in rows)
        self.events.extend(events)
        if self.store.engine is not None:
            if len(self.pending) >= self.settings.retry_buffer_size:
                self.pending.popleft()
                self.dropped_batches += 1
            self.pending.append(
                {
                    "plant_id": self.engine.profile.plant_id,
                    "records": rows,
                    "checkpoint": {**self.engine.checkpoint(), "touch_gate": self.touch.checkpoint()},
                }
            )
        self.fetch.publish(events)
        self._broadcast(events)

    async def ingest(self, observation, now=None):
        now = now or utcnow()
        async with self.lock:
            if observation.plant_id != self.engine.profile.plant_id:
                raise KeyError("Unknown plant")
            if (observation.timestamp - now).total_seconds() > self.settings.future_skew_seconds:
                raise ValueError("timestamp exceeds allowed future clock skew")
            key = str(observation.event_id)
            duplicate = key in self.seen
            if not duplicate and self.db_status == "ok":
                try:
                    duplicate = await asyncio.to_thread(self.store.contains, key)
                except Exception:
                    self.db_status = "unavailable"
            if duplicate:
                return {"status": "duplicate", "event_id": key, "events": []}
            if isinstance(observation, TouchObservation):
                status, triggered = self.touch.observe(observation, now)
                events = []
                if status == "accepted":
                    self.engine.state.touch = observation
                    self.engine.state.timestamp = now
                if triggered:
                    event = PlantEvent(
                        plant_id=observation.plant_id,
                        timestamp=observation.timestamp,
                        source=observation.source,
                        kind="touch",
                        mood=self.engine.state.mood,
                        reason="New touch requests a bounded listening window.",
                        observation_id=observation.event_id,
                    )
                    self.engine.state.last_event_id = event.event_id
                    events = [event]
            else:
                status, events = (
                    self.engine.sensor(observation, now)
                    if isinstance(observation, SensorReading)
                    else self.engine.leaf(observation, now)
                )
            if status == "accepted":
                self.seen[key] = True
                if len(self.seen) > self.settings.dedup_limit:
                    self.seen.popitem(last=False)
                self._commit(observation, events)
            return {
                "status": status,
                "event_id": key,
                "events": [e.model_dump(mode="json") for e in events],
                "persistence": "buffered" if self.pending else self.db_status,
            }

    async def flush(self):
        if self.store.engine is None:
            return
        async with self.flush_lock:
            try:
                if not self.db_initialized:
                    # Do not replace live state with an old checkpoint after an outage.
                    await asyncio.to_thread(self.store.start, self.engine.profile)
                    self.db_initialized = True
                for _ in range(100):
                    if not self.pending:
                        break
                    batch = self.pending[0]
                    await asyncio.to_thread(self.store.save, batch)
                    # The bounded queue may have evicted this item during the write.
                    if self.pending and self.pending[0] is batch:
                        self.pending.popleft()
                if not self.pending:
                    await asyncio.to_thread(self.store.contains, "health-probe")
                self.db_status = "ok"
            except Exception:
                self.db_status = "unavailable"

    async def tick(self, now=None):
        async with self.lock:
            self._commit(None, self.engine.tick(now or utcnow()))

    async def _run(self):
        async def persistence():
            while not self.stopping.is_set():
                await self.flush()
                with contextlib.suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(self.stopping.wait(), timeout=1)

        writer = asyncio.create_task(persistence())
        try:
            while True:
                await self.tick()
                await asyncio.sleep(0.5)
        finally:
            # Let a running DB transaction finish before final flush/disposal. Cancelling
            # to_thread cannot stop the thread and could allow an old checkpoint to win.
            self.stopping.set()
            await writer

    async def get_history(self, limit, offset):
        if self.db_status == "ok" and not self.pending:
            try:
                return await asyncio.to_thread(
                    self.store.history, self.engine.profile.plant_id, limit, offset
                ), "database"
            except Exception:
                self.db_status = "unavailable"
        rows = sorted(self.history, key=lambda r: (r["timestamp"], r["event_id"]), reverse=True)
        return rows[offset : offset + limit], "bounded_memory"

    def context(self):
        return ConversationContext(
            plant_id=self.engine.profile.plant_id,
            profile=self.engine.profile,
            state=self.engine.state,
            recent_events=list(self.events)[-20:],
        )

    async def close(self):
        for task in (self.demo_task, self.task):
            if task:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await task
        await self.flush()
        await self.fetch.close()
        await asyncio.to_thread(self.store.close)
