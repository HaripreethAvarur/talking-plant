"""Versioned, transactional migrations. Run before serving (also safe on startup)."""

from sqlalchemy import select, text

from backend.database.schema import (
    MOODS,
    checkpoints,
    hourly,
    metadata,
    plants,
    profiles,
    records,
    versions,
)


def _widen_mood_checks(conn):
    """Version 3: allow the soggy and sleepy moods in hourly_readings."""
    allowed = ", ".join(f"'{mood}'" for mood in MOODS)
    if conn.dialect.name == "postgresql":
        for column, name in (("mood", "mood_known"), ("day_mood", "day_mood_known")):
            conn.execute(text(f"ALTER TABLE hourly_readings DROP CONSTRAINT IF EXISTS {name}"))
            conn.execute(
                text(
                    f"ALTER TABLE hourly_readings ADD CONSTRAINT {name} "
                    f"CHECK ({column} IS NULL OR {column} IN ({allowed}))"
                )
            )
        return
    # SQLite can't alter a CHECK constraint: rebuild the table with the current definition.
    conn.execute(text("DROP INDEX IF EXISTS hourly_by_hour"))
    conn.execute(text("ALTER TABLE hourly_readings RENAME TO hourly_readings_old"))
    hourly.create(conn)
    columns = ", ".join(column.name for column in hourly.columns)
    conn.execute(text(f"INSERT INTO hourly_readings ({columns}) SELECT {columns} FROM hourly_readings_old"))
    conn.execute(text("DROP TABLE hourly_readings_old"))


MIGRATIONS = {
    1: [profiles, records, checkpoints],
    2: [plants, hourly],
    3: _widen_mood_checks,
}


def migrate(engine):
    with engine.begin() as conn:
        versions.create(conn, checkfirst=True)
        applied = set(conn.execute(select(versions.c.version)).scalars())
        for version, step in sorted(MIGRATIONS.items()):
            if version in applied:
                continue
            if callable(step):
                step(conn)
            else:
                metadata.create_all(conn, tables=step)
            conn.execute(versions.insert().values(version=version))


def main():
    from backend.config import Settings
    from backend.database.store import Store

    store = Store(Settings())
    if store.engine is None:
        raise SystemExit("Set DATABASE_URL before running migrations.")
    try:
        migrate(store.engine)
    except Exception as exc:
        raise SystemExit(
            f"Migration failed ({type(exc).__name__}); check connectivity/configuration."
        ) from None
    finally:
        store.close()
    print(f"Database schema is at version {max(MIGRATIONS)}.")


if __name__ == "__main__":
    main()
