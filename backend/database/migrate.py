"""Versioned, transactional migrations. Run before serving (also safe on startup)."""

from sqlalchemy import select

from backend.database.schema import checkpoints, metadata, profiles, records, versions


def migrate(engine):
    with engine.begin() as conn:
        versions.create(conn, checkfirst=True)
        applied = set(conn.execute(select(versions.c.version)).scalars())
        if 1 not in applied:
            metadata.create_all(conn, tables=[profiles, records, checkpoints])
            conn.execute(versions.insert().values(version=1))


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
    print("Database schema is at version 1.")


if __name__ == "__main__":
    main()
