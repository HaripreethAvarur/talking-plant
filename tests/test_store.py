from backend.service import PlantService


async def test_persist_restart_and_dedup(settings, reading):
    service = PlantService(settings)
    await service.start()
    row = reading(0)
    await service.ingest(row, row.timestamp)
    await service.close()
    restored = PlantService(settings)
    await restored.start()
    try:
        rows, storage = await restored.get_history(100, 0)
        assert storage == "database"
        assert str(row.event_id) in {r["event_id"] for r in rows}
        assert (await restored.ingest(row, row.timestamp))["status"] == "duplicate"
        assert restored.engine.state.last_sensor_at == row.timestamp
    finally:
        await restored.close()


async def test_outage_bounded_buffer_recovers(settings, reading, monkeypatch):
    settings.retry_buffer_size = 2
    service = PlantService(settings)
    await service.start()
    original_save = service.store.save

    def fail(batch):
        raise ConnectionError("unavailable")

    monkeypatch.setattr(service.store, "save", fail)
    for step in range(6):
        row = reading(step)
        await service.ingest(row, row.timestamp)
    await service.flush()
    assert service.db_status == "unavailable"
    assert len(service.pending) == 2
    assert service.dropped_batches >= 4
    assert service.engine.state.mood.value == "thirsty"
    monkeypatch.setattr(service.store, "save", original_save)
    await service.flush()
    assert service.db_status == "ok"
    assert not service.pending
    await service.close()
