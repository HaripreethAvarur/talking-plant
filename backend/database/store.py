"""Sync SQLAlchemy calls are run in worker threads by the service; never log URLs."""

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from backend.database.migrate import migrate
from backend.database.schema import checkpoints, profiles, records


class Store:
    def __init__(self, settings):
        url = settings.database_url.get_secret_value()
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+psycopg://", 1)
        elif url.startswith("postgresql://"):
            url = url.replace("postgresql://", "postgresql+psycopg://", 1)
        options = {"pool_pre_ping": True}
        if url.startswith("postgresql"):
            options["connect_args"] = {"connect_timeout": 3, "options": "-c statement_timeout=3000"}
        elif url.startswith("sqlite"):
            options["connect_args"] = {"check_same_thread": False}
        self.engine = create_engine(url, **options) if url else None

    def _insert(self, table):
        return pg_insert(table) if self.engine.dialect.name == "postgresql" else sqlite_insert(table)

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

    def close(self):
        if self.engine:
            self.engine.dispose()
