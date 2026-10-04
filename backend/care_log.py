"""The care log: every interval (an hour; a minute for demos) record sun, water, air,
how the plant looks and ASI's mood label; every night label the day and purge old data.

Runs inside the API process. Each input is optional: a missing camera, Ollama, air API
or ASI key leaves that field empty (or falls back to the live rules) instead of losing
the row. Rows go to the database when there is one, and are always kept in memory for
the plant's chat context.
"""

import asyncio
import contextlib
import logging
from collections import deque
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from backend import air
from backend.conversation import labels
from backend.ui import to_ui
from backend.vision import health
from shared.contracts import HourlyReading, Mood, utcnow

log = logging.getLogger(__name__)

CHECK_SECONDS = 15
LOOKS_FRESH_FOR = timedelta(hours=2)


class CareLog:
    def __init__(self, service, settings):
        self.service, self.settings = service, settings
        self.recent: deque[HourlyReading] = deque(maxlen=24)
        self.task = None
        self.last_slot = None
        self.labelled_day: date | None = None
        self.lock = asyncio.Lock()

    @property
    def username(self):
        registration = self.service.registration
        return registration.username if registration else None

    @property
    def zone(self):
        return ZoneInfo(self.service.engine.profile.timezone)

    def _db(self):
        return self.service.store.engine is not None and self.service.db_status == "ok"

    async def start(self):
        await self.reload()
        self.task = asyncio.create_task(self._run())

    async def reload(self):
        """Fill the in-memory window from the database (after start or a new registration)."""
        self.recent.clear()
        if self.username and self._db():
            with contextlib.suppress(Exception):
                self.recent.extend(await asyncio.to_thread(self.service.store.recent_hourly, self.username))

    def latest_looks(self, now=None) -> str | None:
        now = now or utcnow()
        for row in reversed(self.recent):
            if row.health and now - row.hour <= LOOKS_FRESH_FOR:
                return row.health
        return None

    def _slot_start(self, now: datetime) -> datetime:
        seconds = self.settings.log_interval_minutes * 60
        return datetime.fromtimestamp(now.timestamp() // seconds * seconds, tz=now.tzinfo)

    async def log_now(self, now: datetime | None = None) -> HourlyReading | None:
        """Record one row for the current interval. None if no plant is registered."""
        now = now or utcnow()
        username = self.username
        if not username:
            return None
        async with self.lock:
            engine = self.service.engine
            view = to_ui(engine.state, self.settings, leaf_stale_seconds=engine.t.leaf_stale_seconds)
            aqi, looks = await asyncio.gather(air.us_aqi(self.service.registration.location), health.look())
            mood = await labels.label_hour(
                local_time=now.astimezone(self.zone).strftime("%A %H:%M"),
                plant_type=engine.profile.plant_type.value,
                thresholds=engine.t,
                sun_pct=view.light_pct,
                water_pct=view.moisture_pct,
                air_aqi=aqi,
                health=looks,
                fallback=engine.state.mood,
            )
            row = HourlyReading(
                username=username,
                hour=self._slot_start(now),
                sun_pct=view.light_pct,
                water_pct=view.moisture_pct,
                air_aqi=aqi,
                health=looks,
                mood=mood,
            )
            if self._db():
                try:
                    await asyncio.to_thread(self.service.store.add_hourly, row)
                except Exception as exc:
                    log.warning("Could not save the care log row: %s", exc)
            if self.recent and self.recent[-1].hour == row.hour:
                self.recent.pop()
            self.recent.append(row)
            log.info(
                "Logged %s: water %s%%, sun %s%%, mood %s", row.hour, row.water_pct, row.sun_pct, mood.value
            )
            return row

    async def label_day(self, day: date | None = None) -> Mood | None:
        """Give a local day its label (on that day's last row) and purge old data."""
        username = self.username
        if not username:
            return None
        zone = self.zone
        day = day or utcnow().astimezone(zone).date()
        start = datetime.combine(day, time(0), tzinfo=zone)
        end = start + timedelta(days=1)
        if self._db():
            rows = await asyncio.to_thread(self.service.store.hourly_between, username, start, end)
        else:
            rows = [row for row in self.recent if start <= row.hour < end]
        mood = await labels.label_day(rows, self.service.engine.profile.plant_type.value)
        if mood is None:
            return None
        if self._db():
            await asyncio.to_thread(self.service.store.set_day_mood, username, start, mood)
            removed = await asyncio.to_thread(self.service.store.purge, utcnow())
            log.info("Labelled %s as %s; purged %s", day, mood.value, removed)
        last = rows[-1].hour
        for index, row in enumerate(self.recent):
            if row.hour == last:
                self.recent[index] = row.model_copy(update={"day_mood": mood})
        return mood

    def _label_due(self, now: datetime) -> date | None:
        local = now.astimezone(self.zone)
        hour, minute = map(int, self.settings.day_label_time.split(":"))
        if local.time() >= time(hour, minute) and self.labelled_day != local.date():
            return local.date()
        return None

    async def tick(self, now: datetime | None = None):
        now = now or utcnow()
        if not self.username:
            return
        slot = self._slot_start(now)
        if slot != self.last_slot:
            self.last_slot = slot
            await self.log_now(now)
        day = self._label_due(now)
        if day:
            self.labelled_day = day
            await self.label_day(day)

    async def _run(self):
        while True:
            try:
                await self.tick()
            except Exception:
                log.exception("Care log step failed; retrying next check")
            await asyncio.sleep(CHECK_SECONDS)

    async def close(self):
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
