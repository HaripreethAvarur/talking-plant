"""Schema v2: kids' plants, the hourly care log, day labels, the leaderboard and purging."""

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from sqlalchemy import delete, insert, select

from backend.database.migrate import MIGRATIONS, migrate
from backend.database.schema import hourly, metadata, plants, records, versions
from backend.database.store import Store
from shared.contracts import HourlyReading, Mood, PlantRegistration

NOW = datetime(2026, 10, 10, 18, 30, tzinfo=timezone.utc)


@pytest.fixture
def store(settings):
    store = Store(settings)
    migrate(store.engine)
    yield store
    store.close()


def register(store, username, plant_type="plant", name=None):
    plant = PlantRegistration(
        username=username, plant_name=name or f"{username}'s plant", plant_type=plant_type, location="48105"
    )
    store.upsert_plant(plant)
    return plant


def log(store, username, hour, **values):
    store.add_hourly(HourlyReading(username=username, hour=hour, **values))


def test_existing_v1_database_gains_v2_tables(settings):
    store = Store(settings)
    with store.engine.begin() as conn:  # a database created before this change
        versions.create(conn)
        metadata.create_all(conn, tables=MIGRATIONS[1])
        conn.execute(insert(versions).values(version=1))
    migrate(store.engine)
    migrate(store.engine)  # idempotent
    with store.engine.connect() as conn:
        assert sorted(conn.execute(select(versions.c.version)).scalars()) == [1, 2]
        assert conn.execute(select(plants)).all() == []
    store.close()


def test_plant_registration_round_trip_and_update(store):
    first = register(store, "maya", "succulent", "Spike")
    store.upsert_plant(first.model_copy(update={"plant_name": "Captain America", "created_at": NOW}))
    saved = store.get_plant("maya")
    assert saved.plant_name == "Captain America"
    assert saved.plant_type.value == "succulent"
    assert saved.created_at == first.created_at  # registration time is kept
    assert store.get_plant("nobody") is None


@pytest.mark.parametrize(
    "changes",
    [{"location": "Ann Arbor"}, {"plant_type": "cactus"}, {"username": "a b"}, {"plant_name": ""}],
)
def test_registration_validation(changes):
    values = {"username": "maya", "plant_name": "Spike", "plant_type": "plant", "location": "48105"}
    with pytest.raises(ValidationError):
        PlantRegistration(**(values | changes))


def test_hourly_rows_round_to_the_hour_and_replace_on_relog(store):
    register(store, "maya")
    log(store, "maya", NOW, sun_pct=70, water_pct=20, mood=Mood.thirsty, health="Leaves look a bit limp.")
    log(store, "maya", NOW + timedelta(minutes=10), sun_pct=72, water_pct=65, mood=Mood.happy)
    log(store, "maya", NOW - timedelta(hours=1), water_pct=22)
    rows = store.recent_hourly("maya")
    assert [row.hour.hour for row in rows] == [17, 18]  # oldest first, one row per hour
    assert rows[1].water_pct == 65 and rows[1].mood == Mood.happy
    assert rows[1].health is None  # a re-log replaces the whole hour
    assert rows[1].hour == NOW.replace(minute=0)
    assert [r.hour.hour for r in store.recent_hourly("maya", limit=1)] == [18]


def test_hourly_rows_need_a_registered_plant(store):
    with pytest.raises(Exception):
        log(store, "ghost", NOW, water_pct=10)


def test_day_mood_goes_on_the_days_last_row(store):
    register(store, "maya")
    detroit = ZoneInfo("America/Detroit")
    day = datetime(2026, 10, 9, tzinfo=detroit)  # local midnight
    for hour in (8, 13, 23):
        log(store, "maya", day + timedelta(hours=hour), mood=Mood.happy)
    log(store, "maya", day + timedelta(days=1, hours=1), mood=Mood.thirsty)  # next local day
    assert store.set_day_mood("maya", day, Mood.happy)
    labelled = [(row.hour.astimezone(detroit).hour, row.day_mood) for row in store.recent_hourly("maya")]
    assert labelled == [(8, None), (13, None), (23, Mood.happy), (1, None)]
    assert not store.set_day_mood("maya", day - timedelta(days=3), Mood.happy)  # no rows that day


def test_leaderboard_counts_happy_days_in_the_last_week(store):
    for name in ("ana", "ben", "cai", "dev"):
        register(store, name)

    def days(username, moods, start_days_ago=1):
        for offset, mood in enumerate(moods):
            hour = NOW - timedelta(days=start_days_ago + offset)
            log(store, username, hour, mood=mood, day_mood=mood)

    days("ana", [Mood.happy, Mood.grateful, Mood.happy, Mood.thirsty])  # 3 happy days
    days("ben", [Mood.happy, Mood.happy, Mood.happy])  # 3 happy days
    days("cai", [Mood.happy] * 3, start_days_ago=8)  # all older than a week
    log(store, "cai", NOW - timedelta(hours=2), mood=Mood.happy)  # hourly mood alone doesn't count
    board = store.leaderboard(NOW)
    assert [(e.rank, e.username, e.happy_days) for e in board] == [
        (1, "ana", 3),
        (1, "ben", 3),
        (3, "cai", 0),
        (3, "dev", 0),
    ]
    assert board[0].score == pytest.approx(3 / 7)
    assert board[0].plant_type.value == "plant" and board[0].location == "48105"


def test_purge_keeps_thirty_days_and_one_day_of_raw_readings(store):
    register(store, "maya")
    log(store, "maya", NOW - timedelta(days=31), water_pct=10)
    log(store, "maya", NOW - timedelta(days=29), water_pct=20)

    def record(event_id, kind, age):
        return dict(
            event_id=event_id,
            plant_id="plant-1",
            kind=kind,
            timestamp=(NOW - age).isoformat(),
            payload={},
        )

    with store.engine.begin() as conn:
        conn.execute(
            insert(records),
            [
                record("old-sensor", "sensor", timedelta(hours=25)),
                record("new-sensor", "sensor", timedelta(hours=1)),
                record("week-event", "watering", timedelta(days=7)),
                record("old-event", "watering", timedelta(days=31)),
            ],
        )
    assert store.purge(NOW) == {"hourly": 1, "raw": 1, "events": 1}
    assert [row.water_pct for row in store.recent_hourly("maya")] == [20]
    with store.engine.connect() as conn:
        assert set(conn.execute(select(records.c.event_id)).scalars()) == {"new-sensor", "week-event"}


def test_removing_a_plant_removes_its_log(store):
    register(store, "maya")
    log(store, "maya", NOW, water_pct=50)
    with store.engine.begin() as conn:
        conn.execute(delete(plants).where(plants.c.username == "maya"))
    with store.engine.connect() as conn:
        assert conn.execute(select(hourly)).all() == []
