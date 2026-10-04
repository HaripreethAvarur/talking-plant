"""The one backend app: sensor ingestion, plant state/history, and (via backend/ui.py) the UI."""

import asyncio
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Query, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.config import get_settings
from backend.sensors.simulator import SCENARIOS, scenario_reading
from backend.service import PlantService
from backend.transport import QUEUE_SIZE, accept_viewer, bearer, serve
from backend.ui import install_ui
from shared.contracts import LeafObservation, SensorReading, StreamMessage, TouchObservation


class DemoRequest(BaseModel):
    scenario: Literal[SCENARIOS]


def create_app(settings=None):
    settings = settings or get_settings()
    service = PlantService(settings)

    @asynccontextmanager
    async def lifespan(app):
        await service.start()
        await app.state.ui.start()
        try:
            yield
        finally:
            await app.state.ui.close()
            await service.close()

    app = FastAPI(title="Talking Plant", version="1.0.0", lifespan=lifespan)
    app.state.service = service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )
    viewer = [Depends(bearer(settings, "viewer_token"))]
    ingestion = [Depends(bearer(settings, "ingestion_token"))]
    install_ui(app, service, settings, viewer)

    def plant(plant_id):
        if plant_id != service.engine.profile.plant_id:
            raise HTTPException(404, "Unknown plant")

    @app.get("/health")
    async def health():
        return {"status": "ok", "schema_version": "1.0"}

    @app.get("/ready")
    async def ready():
        ok = not settings.database_required or service.db_status == "ok"
        return JSONResponse(
            status_code=200 if ok else 503,
            content={
                "status": "ready" if ok else "degraded",
                "database": service.db_status,
                "pending_batches": len(service.pending),
                "dropped_batches": service.dropped_batches,
                "fetch": service.fetch.status,
                "fetch_detail": service.fetch.detail,
            },
        )

    @app.get("/api/v1/plants/{plant_id}/state", dependencies=viewer)
    async def state(plant_id: str):
        plant(plant_id)
        await service.tick()
        return service.engine.state

    @app.get("/api/v1/plants/{plant_id}/context", dependencies=viewer)
    async def context(plant_id: str):
        plant(plant_id)
        await service.tick()
        return service.context()

    @app.get("/api/v1/plants/{plant_id}/history", dependencies=viewer)
    async def history(plant_id: str, limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        plant(plant_id)
        rows, storage = await service.get_history(limit, offset)
        return {
            "schema_version": "1.0",
            "plant_id": plant_id,
            "items": rows,
            "limit": limit,
            "offset": offset,
            "storage": storage,
        }

    async def ingest(observation):
        try:
            return await service.ingest(observation)
        except KeyError:
            raise HTTPException(404, "Unknown plant") from None
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None

    @app.post("/api/v1/sensor-readings", dependencies=ingestion)
    async def sensors(reading: SensorReading):
        return await ingest(reading)

    @app.post("/api/v1/leaf-observations", dependencies=ingestion)
    async def leaves(observation: LeafObservation):
        return await ingest(observation)

    @app.post("/api/v1/touch-observations", dependencies=ingestion)
    async def touch(observation: TouchObservation):
        return await ingest(observation)

    @app.websocket("/ws/plants/{plant_id}")
    async def websocket(ws: WebSocket, plant_id: str):
        if plant_id != service.engine.profile.plant_id:
            await ws.close(code=1008)
            return
        if not await accept_viewer(ws, settings):
            return
        queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        async with service.lock:
            service.subscribers.add(queue)
            queue.put_nowait(
                StreamMessage(type="snapshot", state=service.engine.state).model_dump(mode="json")
            )
        try:
            await serve(ws, queue)
        finally:
            service.subscribers.discard(queue)

    @app.post("/api/v1/demo/scenario", dependencies=ingestion)
    async def demo(request: DemoRequest):
        if not settings.demo_mode:
            raise HTTPException(404, "Demo controls disabled")
        if service.demo_task and not service.demo_task.done():
            raise HTTPException(409, "A scenario is already running")

        async def run():
            for step in range(24):
                await service.ingest(
                    scenario_reading(request.scenario, step, plant_id=service.engine.profile.plant_id)
                )
                await asyncio.sleep(1)

        service.demo_task = asyncio.create_task(run())
        return {"status": "started", "scenario": request.scenario, "duration_seconds": 24}

    return app
