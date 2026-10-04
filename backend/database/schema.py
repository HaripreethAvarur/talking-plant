from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

from shared.contracts import Mood

metadata = MetaData()
versions = Table("schema_migrations", metadata, Column("version", Integer, primary_key=True))

# --- Version 1: live sensor pipeline -------------------------------------------
profiles = Table(
    "plant_profiles",
    metadata,
    Column("plant_id", String(64), primary_key=True),
    Column("payload", JSON, nullable=False),
)
records = Table(
    "care_records",
    metadata,
    Column("event_id", String(36), primary_key=True),
    Column("plant_id", String(64), nullable=False, index=True),
    Column("kind", String(32), nullable=False),
    Column("timestamp", String(40), nullable=False, index=True),
    Column("payload", JSON, nullable=False),
)
checkpoints = Table(
    "plant_checkpoints",
    metadata,
    Column("plant_id", String(64), primary_key=True),
    Column("payload", JSON, nullable=False),
)

# --- Version 2: kids' plants, hourly care log, leaderboard ------------------------
MOODS = tuple(mood.value for mood in Mood)
plants = Table(
    "plants",
    metadata,
    Column("username", String(32), primary_key=True),
    Column("plant_name", String(40), nullable=False),
    Column("plant_type", String(16), nullable=False),
    Column("location", String(5), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    CheckConstraint("plant_type IN ('succulent', 'plant', 'tree')", name="plant_type_known"),
)
hourly = Table(
    "hourly_readings",
    metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("username", String(32), ForeignKey("plants.username", ondelete="CASCADE"), nullable=False),
    Column("hour", DateTime(timezone=True), nullable=False),
    Column("sun_pct", Float),
    Column("water_pct", Float),
    Column("air_aqi", Float),
    Column("health", Text),
    Column("mood", String(16)),
    Column("day_mood", String(16)),
    UniqueConstraint("username", "hour", name="one_row_per_hour"),
    CheckConstraint(f"mood IS NULL OR mood IN {MOODS}", name="mood_known"),
    CheckConstraint(f"day_mood IS NULL OR day_mood IN {MOODS}", name="day_mood_known"),
)
Index("hourly_by_hour", hourly.c.hour)
