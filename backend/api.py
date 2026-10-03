import asyncio
import contextlib
import secrets
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.config import Settings
from backend.service import PlantService
from shared.contracts import LeafObservation, SensorReading, StreamMessage, TouchObservation


def create_app(settings=None):
    settings = settings or Settings()
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

    app = FastAPI(title="Talking Plant — Person 1", version="1.0.0", lifespan=lifespan)
    app.state.service = service
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
    )

    def authenticate(header, expected):
        if expected and not secrets.compare_digest(header or "", f"Bearer {expected}"):
            raise HTTPException(401, "Invalid bearer token")

    def ingestion_auth(authorization: str | None = Header(default=None)):
        authenticate(authorization, settings.ingestion_token.get_secret_value())

    def viewer_auth(authorization: str | None = Header(default=None)):
        authenticate(authorization, settings.viewer_token.get_secret_value())

    from backend.ui import install_ui

    install_ui(app, service, settings, viewer_auth, ingestion_auth, authenticate)

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

    @app.get("/api/v1/plants/{plant_id}/state", dependencies=[Depends(viewer_auth)])
    async def state(plant_id: str):
        plant(plant_id)
        await service.tick()
        return service.engine.state

    @app.get("/api/v1/plants/{plant_id}/context", dependencies=[Depends(viewer_auth)])
    async def context(plant_id: str):
        plant(plant_id)
        await service.tick()
        return service.context()

    @app.get("/api/v1/plants/{plant_id}/history", dependencies=[Depends(viewer_auth)])
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

    @app.post("/api/v1/sensor-readings", dependencies=[Depends(ingestion_auth)])
    async def sensors(reading: SensorReading):
        return await ingest(reading)

    @app.post("/api/v1/leaf-observations", dependencies=[Depends(ingestion_auth)])
    async def leaves(observation: LeafObservation):
        return await ingest(observation)

    @app.post("/api/v1/touch-observations", dependencies=[Depends(ingestion_auth)])
    async def touch(observation: TouchObservation):
        return await ingest(observation)

    @app.websocket("/ws/plants/{plant_id}")
    async def websocket(ws: WebSocket, plant_id: str):
        if plant_id != service.engine.profile.plant_id:
            await ws.close(code=1008)
            return
        origin = ws.headers.get("origin")
        if origin and origin not in settings.cors_origins:
            await ws.close(code=1008)
            return
        await ws.accept()
        expected = settings.viewer_token.get_secret_value()
        if expected:
            try:
                auth = await asyncio.wait_for(ws.receive_json(), timeout=5)
                if (
                    not isinstance(auth, dict)
                    or auth.get("type") != "auth"
                    or not isinstance(auth.get("token"), str)
                ):
                    raise ValueError("Invalid auth frame")
                if not secrets.compare_digest(auth["token"], expected):
                    raise ValueError("Invalid token")
            except (ValueError, asyncio.TimeoutError, WebSocketDisconnect):
                await ws.close(code=1008)
                return
        queue = asyncio.Queue(maxsize=64)
        async with service.lock:
            service.subscribers.add(queue)
            snapshot = StreamMessage(type="snapshot", state=service.engine.state).model_dump(mode="json")

        async def sender():
            await ws.send_json(snapshot)
            while True:
                message = await queue.get()
                if message is None:
                    await ws.close(code=1013, reason="Slow consumer; reconnect and recover history")
                    return
                await ws.send_json(message)

        async def receiver():
            while True:
                await ws.receive_text()

        tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            service.subscribers.discard(queue)
            for task in tasks:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                    await task

    class DemoRequest(BaseModel):
        scenario: Literal["healthy", "dry", "watered", "dark", "noisy", "disconnected", "dry-to-watered"]

    @app.post("/api/v1/demo/scenario", dependencies=[Depends(ingestion_auth)])
    async def demo(request: DemoRequest):
        if not settings.demo_mode:
            raise HTTPException(404, "Demo controls disabled")
        if service.demo_task and not service.demo_task.done():
            raise HTTPException(409, "A scenario is already running")
        from backend.sensors.simulator import scenario_reading

        async def run():
            for step in range(24):
                await service.ingest(
                    scenario_reading(request.scenario, step, plant_id=service.engine.profile.plant_id)
                )
                await asyncio.sleep(1)

        service.demo_task = asyncio.create_task(run())
        return {"status": "started", "scenario": request.scenario, "duration_seconds": 24}

    return app
