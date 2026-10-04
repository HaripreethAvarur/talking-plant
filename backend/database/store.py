"""Sync SQLAlchemy calls are run in worker threads by the service; never log URLs."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import case, create_engine, delete, event, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.database.migrate import migrate
from backend.database.schema import checkpoints, hourly, plants, profiles, records
from shared.contracts import HourlyReading, LeaderboardEntry, PlantRegistration

HISTORY_DAYS = 30  # hourly rows and care events are kept this long
RAW_HOURS = 24  # per-second sensor/touch/leaf records only need to outlive restart dedup
RAW_KINDS = ("sensor", "touch_observation", "leaf")
HAPPY_DAY_MOODS = ("happy",)
LEADERBOARD_DAYS = 7


def _utc(value: datetime | None) -> datetime | None:
    """SQLite returns naive datetimes; everything here is stored in UTC."""
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class Store:
    def __init__(self, settings):
        url = settings.database_url.get_secret_value()
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        options = {"pool_pre_ping": True}
        if url.startswith("postgresql"):
            # Neon may need a few seconds to wake a suspended database.
            options["connect_args"] = {"connect_timeout": 10}
        elif url.startswith("sqlite"):
            options["connect_args"] = {"check_same_thread": False}
        self.engine = create_engine(url, **options) if url else None
        if self.engine is not None and self.engine.dialect.name == "postgresql":
            # Neon's pooler rejects startup options, so cap query time per transaction instead.
            event.listen(
                self.engine, "begin", lambda conn: conn.exec_driver_sql("SET LOCAL statement_timeout = 3000")
            )
        if self.engine is not None and self.engine.dialect.name == "sqlite":
            # SQLite ignores ON DELETE CASCADE unless asked per connection.
            event.listen(self.engine, "connect", lambda conn, _: conn.execute("PRAGMA foreign_keys=ON"))

    def _insert(self, table):
        return pg_insert(table) if self.engine.dialect.name == "postgresql" else sqlite_insert(table)

    # --- Live sensor pipeline (schema v1) -------------------------------------

    def start(self, profile):
        if self.engine is None:
            return None
        migrate(self.engine)
        with self.engine.begin() as conn:
            conn.execute(
                self._insert(profiles)
                .values(plant_id=profile.plant_id, payload=profile.model_dump(mode="json"))
                .on_conflict_do_nothing()
            )
            profile_data = conn.execute(
                select(profiles.c.payload).where(profiles.c.plant_id == profile.plant_id)
            ).scalar()
            checkpoint = conn.execute(
                select(checkpoints.c.payload).where(checkpoints.c.plant_id == profile.plant_id)
            ).scalar()
            return profile_data, checkpoint

    def contains(self, event_id):
        if self.engine is None:
            return False
        with self.engine.connect() as conn:
            return (
                conn.execute(select(records.c.event_id).where(records.c.event_id == str(event_id))).first()
                is not None
            )

    def update_profile(self, profile):
        with self.engine.begin() as conn:
            stmt = self._insert(profiles).values(
                plant_id=profile.plant_id, payload=profile.model_dump(mode="json")
            )
            conn.execute(
                stmt.on_conflict_do_update(
                    index_elements=[profiles.c.plant_id], set_={"payload": stmt.excluded.payload}
                )
            )

    def save(self, batch):
        if self.engine is None:
            return
        with self.engine.begin() as conn:
            for record in batch["records"]:
                conn.execute(self._insert(records).values(**record).on_conflict_do_nothing())
            stmt = self._insert(checkpoints).values(plant_id=batch["plant_id"], payload=batch["checkpoint"])
            conn.execute(
                stmt.on_conflict_do_update(
                    index_elements=[checkpoints.c.plant_id], set_={"payload": stmt.excluded.payload}
                )
            )

    def history(self, plant_id, limit=100, offset=0):
        if self.engine is None:
            return []
        with self.engine.connect() as conn:
            return list(
                conn.execute(
                    select(records.c.payload)
                    .where(records.c.plant_id == plant_id)
                    .order_by(records.c.timestamp.desc(), records.c.event_id.desc())
                    .limit(limit)
                    .offset(offset)
                ).scalars()
            )

    # --- Kids' plants, hourly log and leaderboard (schema v2) -----------------

    def upsert_plant(self, plant: PlantRegistration) -> None:
        """Register a plant, or update its name/type/location; created_at is kept."""
        values = plant.model_dump(exclude={"schema_version", "species"})  # species lives in the profile
        values["plant_type"] = plant.plant_type.value
        with self.engine.begin() as conn:
            stmt = self._insert(plants).values(**values)
            conn.execute(
                stmt.on_conflict_do_update(
                    index_elements=[plants.c.username],
                    set_={k: stmt.excluded[k] for k in ("plant_name", "plant_type", "location")},
                )
            )

    def get_plant(self, username: str) -> PlantRegistration | None:
        with self.engine.connect() as conn:
            row = conn.execute(select(plants).where(plants.c.username == username)).mappings().first()
        if row is None:
            return None
        return PlantRegistration(**{**row, "created_at": _utc(row["created_at"])})

    def add_hourly(self, reading: HourlyReading) -> None:
        """Insert the hour's row, or replace it if that hour was already logged."""
        values = reading.model_dump(mode="python", exclude={"schema_version"})
        for key in ("mood", "day_mood"):
            values[key] = values[key].value if values[key] else None
        with self.engine.begin() as conn:
            stmt = self._insert(hourly).values(**values)
            fields = ("sun_pct", "water_pct", "air_aqi", "health", "mood", "day_mood")
            conn.execute(
                stmt.on_conflict_do_update(
                    index_elements=[hourly.c.username, hourly.c.hour],
                    set_={k: stmt.excluded[k] for k in fields},
                )
            )

    def recent_hourly(self, username: str, limit: int = 24) -> list[HourlyReading]:
        """The latest rows, oldest first (the order to show an LLM)."""
        with self.engine.connect() as conn:
            rows = (
                conn.execute(
                    select(hourly)
                    .where(hourly.c.username == username)
                    .order_by(hourly.c.hour.desc())
                    .limit(limit)
                )
                .mappings()
                .all()
            )
        return [
            HourlyReading(**{k: v for k, v in row.items() if k != "id"} | {"hour": _utc(row["hour"])})
            for row in reversed(rows)
        ]

    def hourly_between(self, username: str, start: datetime, end: datetime) -> list[HourlyReading]:
        """Rows with start <= hour < end, oldest first."""
        with self.engine.connect() as conn:
            rows = (
                conn.execute(
                    select(hourly)
                    .where(
                        hourly.c.username == username, hourly.c.hour >= _utc(start), hourly.c.hour < _utc(end)
                    )
                    .order_by(hourly.c.hour)
                )
                .mappings()
                .all()
            )
        return [
            HourlyReading(**{k: v for k, v in row.items() if k != "id"} | {"hour": _utc(row["hour"])})
            for row in rows
        ]

    def set_day_mood(self, username: str, day_start: datetime, mood) -> bool:
        """Label a day: write day_mood on that day's last logged row, clearing any earlier label
        so a re-labelled day still counts once. False if the day has no rows."""
        day_start = _utc(day_start)
        day_end = day_start + timedelta(days=1)
        that_day = (hourly.c.username == username, hourly.c.hour >= day_start, hourly.c.hour < day_end)
        with self.engine.begin() as conn:
            last = conn.execute(select(func.max(hourly.c.hour)).where(*that_day)).scalar()
            if last is None:
                return False
            conn.execute(update(hourly).where(*that_day).values(day_mood=None))
            conn.execute(
                update(hourly)
                .where(hourly.c.username == username, hourly.c.hour == last)
                .values(day_mood=getattr(mood, "value", mood))
            )
        return True

    def leaderboard(self, now: datetime, limit: int = 50) -> list[LeaderboardEntry]:
        """Every plant ranked by happy days in the last 7 days (score = happy days / 7).
        Plants with equal scores share a rank."""
        now = _utc(now)
        since = now - timedelta(days=LEADERBOARD_DAYS)
        happy = func.coalesce(
            func.sum(case((hourly.c.day_mood.in_(HAPPY_DAY_MOODS), 1), else_=0)),
            0,
        )
        query = (
            select(plants, happy.label("happy_days"))
            .select_from(
                plants.outerjoin(
                    hourly,
                    (hourly.c.username == plants.c.username)
                    & (hourly.c.hour >= since)
                    & (hourly.c.hour <= now),
                )
            )
            .group_by(*plants.c)
            .order_by(happy.desc(), plants.c.username)
            .limit(limit)
        )
        with self.engine.connect() as conn:
            rows = conn.execute(query).mappings().all()
        entries, rank, previous = [], 0, None
        for position, row in enumerate(rows, start=1):
            days = min(int(row["happy_days"]), LEADERBOARD_DAYS)
            if days != previous:
                rank, previous = position, days
            entries.append(
                LeaderboardEntry(
                    rank=rank,
                    username=row["username"],
                    plant_name=row["plant_name"],
                    plant_type=row["plant_type"],
                    location=row["location"],
                    happy_days=days,
                    score=days / LEADERBOARD_DAYS,
                )
            )
        return entries

    def purge(self, now: datetime) -> dict[str, int]:
        """Drop hourly rows and care events older than 30 days, and raw readings older than a day."""
        now = _utc(now)
        history_cutoff = now - timedelta(days=HISTORY_DAYS)
        raw_cutoff = (now - timedelta(hours=RAW_HOURS)).isoformat()
        with self.engine.begin() as conn:
            hourly_rows = conn.execute(delete(hourly).where(hourly.c.hour < history_cutoff)).rowcount
            raw_rows = conn.execute(
                delete(records).where(records.c.kind.in_(RAW_KINDS), records.c.timestamp < raw_cutoff)
            ).rowcount
            event_rows = conn.execute(
                delete(records).where(records.c.timestamp < history_cutoff.isoformat())
            ).rowcount
        return {"hourly": hourly_rows, "raw": raw_rows, "events": event_rows}

    def close(self):
        if self.engine:
            self.engine.dispose()
