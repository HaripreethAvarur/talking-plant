from sqlalchemy import JSON, Column, Integer, MetaData, String, Table

metadata = MetaData()
versions = Table("schema_migrations", metadata, Column("version", Integer, primary_key=True))
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
