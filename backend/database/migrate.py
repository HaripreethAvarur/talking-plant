"""Versioned, transactional migrations. Run before serving (also safe on startup)."""

from sqlalchemy import select

from backend.database.schema import checkpoints, hourly, metadata, plants, profiles, records, versions

MIGRATIONS = {
    1: [profiles, records, checkpoints],
    2: [plants, hourly],
}


def migrate(engine):
    with engine.begin() as conn:
        versions.create(conn, checkfirst=True)
        applied = set(conn.execute(select(versions.c.version)).scalars())
        for version, tables in sorted(MIGRATIONS.items()):
            if version not in applied:
                metadata.create_all(conn, tables=tables)
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
