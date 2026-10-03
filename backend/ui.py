"""UI transport for the canonical service; reuses Person 2's conversation and speech modules."""

import asyncio
import contextlib
import logging
from collections import OrderedDict

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from backend.conversation import replies, safety
from backend.conversation.scripted import QUICK_QUESTIONS, REDIRECT_LINE, classify
from backend.speech import stt, tts
from shared.contracts import (
    ListenRequest,
    PlantEvent,
    PlantState,
    Status,
    UIChildUtterance,
    UIPlantState,
    utcnow,
)


def to_ui(state, settings, message=None, leaf_stale_seconds=300):
    light = state.light
    light_pct = None
    if light.status == Status.ok:
        maximum = settings.ui_light_raw_max if light.unit == "raw" else settings.ui_light_lux_max
        light_pct = min(100, max(0, 100 * light.value / maximum))
    issues = []
    leaf = state.leaf
    if (
        leaf
        and leaf.status == Status.ok
        and (utcnow() - leaf.timestamp).total_seconds() <= leaf_stale_seconds
    ):
        if leaf.yellow_proportion >= 0.25:
            issues.append("yellowing")
        if leaf.brown_proportion >= 0.25:
            issues.append("browning")
    return UIPlantState(
        mood=state.mood,
        message=message,
        moisture_pct=state.moisture.relative_percent,
        light_pct=light_pct,
        light_value=light.value,
        light_unit=light.unit,
        leaf_issues=issues,
        sensor_health=state.sensor_health,
        ts=state.timestamp.timestamp(),
    )


class UIHub:
    def __init__(self, service, settings):
        self.service, self.settings = service, settings
        self.clients = OrderedDict()
        self.speech = asyncio.Queue(maxsize=20)
        self.queue = asyncio.Queue(maxsize=64)
        self.tasks = []
        self.seen = OrderedDict()
        self.silent_until = 0

    def view(self, state, message=None):
        return to_ui(state, self.settings, message, self.service.engine.t.leaf_stale_seconds)

    async def start(self):
        self.service.subscribers.add(self.queue)
        self.tasks = [asyncio.create_task(self._updates()), asyncio.create_task(self._speech())]

    def broadcast(self, payload):
        for ws, queue in tuple(self.clients.items()):
            if queue.full():
                while not queue.empty():
                    queue.get_nowait()
                queue.put_nowait(None)
                self.clients.pop(ws, None)
            else:
                queue.put_nowait(payload)

    def say(self, text):
        if self.clients and not self.speech.full():
            self.speech.put_nowait(text)

    async def _speech(self):
        while True:
            text = await self.speech.get()
            try:
                audio = await tts.synthesize(text)
            except Exception:
                logging.getLogger(__name__).warning("Speech synthesis unavailable", exc_info=False)
                continue
            while asyncio.get_running_loop().time() < self.silent_until:
                await asyncio.sleep(0.1)
            self.broadcast(audio.model_dump(mode="json"))

    async def _updates(self):
        while True:
            update = await self.queue.get()
            if update is None:
                # Recover state but never replay old touch/speech requests.
                self.service.subscribers.add(self.queue)
                self.broadcast(self.view(self.service.engine.state).model_dump(mode="json"))
                continue
            state = PlantState.model_validate(update["state"])
            self.broadcast(self.view(state).model_dump(mode="json"))
            for data in update["events"]:
                event = PlantEvent.model_validate(data)
                key = str(event.event_id)
                if key in self.seen:
                    continue
                self.seen[key] = True
                if len(self.seen) > 10000:
                    self.seen.popitem(last=False)
                if (
                    event.kind == "touch"
                    and self.clients
                    and (utcnow() - event.timestamp).total_seconds() <= 5
                ):
                    # Greet the child before opening the mic.
                    greeting = "Hi there! What would you like to know?"
                    self.broadcast(self.view(state, greeting).model_dump(mode="json"))
                    self.say(greeting)
                    duration = int(self.settings.touch_listen_seconds * 1000)
                    self.silent_until = (
                        asyncio.get_running_loop().time() + self.settings.touch_listen_seconds + 1
                    )
                    request = ListenRequest(
                        event_id=event.event_id,
                        plant_id=event.plant_id,
                        timestamp=event.timestamp,
                        duration_ms=duration,
                    )
                    # One mic per physical plant: only the first connected browser records.
                    queue = next(iter(self.clients.values()))
                    if not queue.full():
                        queue.put_nowait(request.model_dump(mode="json"))
                elif event.suggested_text:
                    self.broadcast(self.view(state, event.suggested_text).model_dump(mode="json"))
                    self.say(event.suggested_text)

    async def answer(self, utterance):
        await self.service.tick()
        state = self.service.engine.state
        view = self.view(state)
        intent = classify(utterance.text)
        # Guard the existing reply module's healthy-leaf default without changing its code.
        if safety.question_is_unsafe(utterance.text):
            text = REDIRECT_LINE
        elif intent == "leaves":
            leaf = state.leaf
            if (
                not leaf
                or leaf.status != Status.ok
                or (utcnow() - leaf.timestamp).total_seconds() > self.service.engine.t.leaf_stale_seconds
            ):
                text = "I don't have a clear look at my leaves yet. Could you check the camera?"
            elif view.leaf_issues:
                text = "Some yellow or brown color is visible on my leaves. Could a grown-up take a look?"
            else:
                text = "The camera hasn't spotted much yellow or brown. A grown-up can help check my leaves."
        elif intent in ("water", "wellbeing", "needs") and view.moisture_pct is None:
            text = "I can't measure my soil moisture yet. Please check my sensor and calibration."
        else:
            history = [event.reason for event in self.service.context().recent_events]
            reply = await replies.reply(view, utterance, history)
            text = reply.text
        self.broadcast(self.view(self.service.engine.state, text).model_dump(mode="json"))
        self.say(text)

    async def close(self):
        self.service.subscribers.discard(self.queue)
        for task in self.tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def install_ui(app, service, settings, viewer_auth, ingestion_auth, authenticate):
    hub = UIHub(service, settings)
    app.state.ui = hub
    router = APIRouter()
    tts.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    app.mount(tts.AUDIO_ROUTE, StaticFiles(directory=tts.CACHE_DIR), name="audio")

    @router.get("/api/health", dependencies=[Depends(viewer_auth)])
    async def health():
        profile = service.engine.profile
        return {
            "stt": stt.is_available(),
            "tts": tts.is_available(),
            "llm": replies.is_available(),
            "plant": {"name": profile.name, "species": profile.species},
            "quick_questions": QUICK_QUESTIONS,
            "touch_listen_seconds": settings.touch_listen_seconds,
        }

    @router.post("/api/stt", dependencies=[Depends(viewer_auth)])
    async def transcribe(request: Request):
        audio = bytearray()
        async for chunk in request.stream():
            audio.extend(chunk)
            if len(audio) > stt.MAX_CLIP_BYTES:
                raise HTTPException(413, "Recording too large")
        try:
            return await stt.transcribe(bytes(audio), request.headers.get("content-type", "audio/webm"))
        except stt.SttUnavailable:
            raise HTTPException(503, "Speech recognition unavailable; use the on-screen questions.") from None

    @router.post("/api/plant-state", dependencies=[Depends(ingestion_auth)])
    async def legacy_demo(state: UIPlantState):
        if not settings.demo_mode:
            raise HTTPException(404, "Direct UI-state override is demo-only; ingest sensor readings instead")
        hub.broadcast(state.model_dump(mode="json"))
        if state.message:
            hub.say(state.message)
        return {"ok": True, "persistence": "none", "demo_only": True}

    @router.websocket("/ws")
    async def websocket(ws: WebSocket):
        origin = ws.headers.get("origin")
        if origin and origin not in settings.cors_origins:
            await ws.close(code=1008)
            return
        await ws.accept()
        if settings.viewer_token.get_secret_value():
            try:
                frame = await asyncio.wait_for(ws.receive_json(), 5)
                if (
                    not isinstance(frame, dict)
                    or frame.get("type") != "auth"
                    or not isinstance(frame.get("token"), str)
                ):
                    raise ValueError("Invalid auth frame")
                authenticate(f"Bearer {frame['token']}", settings.viewer_token.get_secret_value())
            except (ValueError, HTTPException, asyncio.TimeoutError, WebSocketDisconnect):
                await ws.close(code=1008)
                return
        queue = asyncio.Queue(maxsize=64)
        hub.clients[ws] = queue
        queue.put_nowait(hub.view(service.engine.state).model_dump(mode="json"))

        async def sender():
            while True:
                message = await queue.get()
                if message is None:
                    await ws.close(code=1013)
                    return
                await ws.send_json(message)

        async def receiver():
            while True:
                raw = await ws.receive_text()
                if len(raw) > 8000:
                    await ws.close(code=1009)
                    return
                try:
                    utterance = UIChildUtterance.model_validate_json(raw)
                    if not utterance.text.strip() or len(utterance.text) > 4000:
                        continue
                except ValidationError:
                    continue
                await hub.answer(utterance)  # One in-flight answer per client.

        tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            hub.clients.pop(ws, None)
            for task in tasks:
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                    await task

    app.include_router(router)
    return hub
