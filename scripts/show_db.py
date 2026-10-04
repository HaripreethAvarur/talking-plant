"""Print what's in the database (DATABASE_URL from .env): read-only.

python -m scripts.show_db              # summary + latest rows
python -m scripts.show_db --rows 20
"""

import argparse
from collections import Counter

from sqlalchemy import func, select

from backend.config import get_settings
from backend.database.schema import checkpoints, hourly, plants, profiles, records, versions
from backend.database.store import Store


def table(title, headers, rows):
    print(f"\n=== {title} ===")
    if not rows:
        print("(none)")
        return
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    line = " | ".join(f"{{:<{w}}}" for w in widths)
    print(line.format(*headers))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(line.format(*(str(v) for v in row)))


def short(value, size=60):
    text = "" if value is None else str(value)
    return text if len(text) <= size else text[: size - 1] + "…"


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--rows", type=int, default=10)
    args = parser.parse_args()
    settings = get_settings()
    store = Store(settings)
    if store.engine is None:
        raise SystemExit("DATABASE_URL is empty.")
    url = settings.database_url.get_secret_value()
    print(
        f"Database: {store.engine.dialect.name} at {url.split('@')[-1].split('/')[0] if '@' in url else url}"
    )
    with store.engine.connect() as conn:
        print("Schema versions:", sorted(conn.execute(select(versions.c.version)).scalars()))
        counts = [
            (t.name, conn.execute(select(func.count()).select_from(t)).scalar())
            for t in (plants, hourly, records, profiles, checkpoints)
        ]
        table("Row counts", ["table", "rows"], counts)

        table(
            "plants (sign-ups)",
            ["username", "plant_name", "plant_type", "zip", "created_at (UTC)"],
            [
                (r.username, r.plant_name, r.plant_type, r.location, str(r.created_at)[:19])
                for r in conn.execute(select(plants).order_by(plants.c.created_at))
            ],
        )

        latest = conn.execute(select(hourly).order_by(hourly.c.hour.desc()).limit(args.rows)).all()
        table(
            f"hourly_readings (latest {args.rows})",
            ["user", "hour (UTC)", "water%", "sun%", "AQI", "mood", "day_mood", "health (Ollama)"],
            [
                (
                    r.username,
                    str(r.hour)[:16],
                    "-" if r.water_pct is None else round(r.water_pct),
                    "-" if r.sun_pct is None else round(r.sun_pct),
                    "-" if r.air_aqi is None else round(r.air_aqi),
                    r.mood or "-",
                    r.day_mood or "-",
                    short(r.health, 55),
                )
                for r in latest
            ],
        )

        kinds = Counter(
            dict(conn.execute(select(records.c.kind, func.count()).group_by(records.c.kind)).all())
        )
        table("care_records by kind", ["kind", "rows"], sorted(kinds.items()))

        events = conn.execute(
            select(records.c.timestamp, records.c.kind, records.c.payload)
            .where(records.c.kind.in_(("mood_changed", "watering", "touch", "sensor_health")))
            .order_by(records.c.timestamp.desc())
            .limit(args.rows)
        ).all()
        table(
            f"care events (latest {args.rows})",
            ["time (UTC)", "kind", "mood", "said"],
            [(t[:19], k, p.get("mood"), short(p.get("suggested_text"), 50)) for t, k, p in events],
        )

        sensor = conn.execute(
            select(records.c.timestamp, records.c.payload)
            .where(records.c.kind == "sensor")
            .order_by(records.c.timestamp.desc())
            .limit(3)
        ).all()
        table(
            "latest raw sensor readings",
            ["time (UTC)", "source", "device", "moisture raw", "moisture %", "light raw"],
            [
                (
                    t[:19],
                    p["source"],
                    p["device_id"],
                    p["moisture"].get("raw"),
                    p["moisture"].get("relative_percent"),
                    p["light"].get("value"),
                )
                for t, p in sensor
            ],
        )

        profile = conn.execute(select(profiles.c.payload)).scalars().first()
        if profile:
            t = profile["thresholds"]
            print(
                f"\nProfile: {profile['name']} ({profile.get('plant_type')}), user {profile.get('username')}, "
                f"dry <= {t['dry_enter']}%, soggy >= {t.get('soggy_enter')}%, timezone {profile.get('timezone')}"
            )
    store.close()


if __name__ == "__main__":
    main()
