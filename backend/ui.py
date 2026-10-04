"""The React UI's side of the backend: /ws, /api/health, /api/stt and /audio.

UIHub turns mood-engine updates into UIPlantState messages, speaks events that
carry suggested_text, opens the microphone on a touch, and answers questions.
"""

import asyncio
import contextlib
import logging
from collections import OrderedDict
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, WebSocket
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from backend import air
from backend.conversation import replies
from backend.conversation.scripted import GREETING_LINE, QUICK_QUESTIONS
from backend.speech import stt, tts
from backend.transport import QUEUE_SIZE, accept_viewer, offer, serve
from shared.contracts import (
    ChildUtterance,
    ListenRequest,
    PlantEvent,
    PlantRegistration,
    PlantState,
    Status,
    UIPlantState,
    utcnow,
)

log = logging.getLogger(__name__)

LEAF_COLOR_ISSUE = 0.25  # share of yellow or brown pixels that counts as an issue


def to_ui(state, settings, message=None, leaf_stale_seconds=300):
    light = state.light
    light_pct = None
    if light.status == Status.ok:
        maximum = settings.ui_light_raw_max if light.unit == "raw" else settings.ui_light_lux_max
        light_pct = min(100, max(0, 100 * light.value / maximum))
    leaf = state.leaf
    issues = None  # the camera has no recent look
    if (
        leaf
        and leaf.status == Status.ok
        and (utcnow() - leaf.timestamp).total_seconds() <= leaf_stale_seconds
    ):
        issues = [
            name
            for name, share in (("yellowing", leaf.yellow_proportion), ("browning", leaf.brown_proportion))
            if share >= LEAF_COLOR_ISSUE
        ]
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
        self.clients = OrderedDict()  # websocket -> its outgoing queue
        self.speech = asyncio.Queue(maxsize=20)
        self.queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        self.tasks = []
        self.seen = OrderedDict()
        self.silent_until = 0
        self.last_listen = float("-inf")

    def view(self, state, message=None):
        view = to_ui(state, self.settings, message, self.service.engine.t.leaf_stale_seconds)
        care = self.service.care
        looks = care.latest_looks()
        latest = care.recent[-1] if care.recent else None
        return view.model_copy(
            update={
                "looks": looks.health if looks else None,
                "looks_at": looks.hour.timestamp() if looks else None,
                "air_aqi": care.air_aqi if care.air_aqi is not None else (latest.air_aqi if latest else None),
                "checkup_mood": latest.mood if latest else None,
            }
        )

    async def start(self):
        self.service.subscribers.add(self.queue)
        self.service.care.on_change = lambda: self.show(self.service.engine.state)
        self.tasks = [asyncio.create_task(self._updates()), asyncio.create_task(self._speech())]

    def broadcast(self, payload):
        for ws, queue in tuple(self.clients.items()):
            if not offer(queue, payload):
                self.clients.pop(ws, None)

    def show(self, state, message=None):
        self.broadcast(self.view(state, message).model_dump(mode="json"))

    def say(self, text):
        if self.clients and not self.speech.full():
            self.speech.put_nowait(text)

    async def _speech(self):
        while True:
            text = await self.speech.get()
            try:
                audio = await tts.synthesize(text)
            except Exception:
                log.warning("Speech synthesis unavailable")
                continue
            while asyncio.get_running_loop().time() < self.silent_until:
                await asyncio.sleep(0.1)
            self.broadcast(audio.model_dump(mode="json"))

    def _listen(self, event_id, plant_id, timestamp, state):
        """Greet the child, then ask the first browser to record for the listening window."""
        self.last_listen = asyncio.get_running_loop().time()
        self.show(state, GREETING_LINE)
        self.say(GREETING_LINE)
        seconds = self.settings.touch_listen_seconds
        self.silent_until = asyncio.get_running_loop().time() + seconds + 1
        request = ListenRequest(
            event_id=event_id,
            plant_id=plant_id,
            timestamp=timestamp,
            duration_ms=int(seconds * 1000),
        )
        # One mic per physical plant: only the first connected browser records.
        queue = next(iter(self.clients.values()))
        if not queue.full():
            queue.put_nowait(request.model_dump(mode="json"))

    async def _updates(self):
        while True:
            update = await self.queue.get()
            if update is None:
                # Dropped as a slow subscriber: resubscribe and resend current state, never old speech.
                self.service.subscribers.add(self.queue)
                self.show(self.service.engine.state)
                continue
            state = PlantState.model_validate(update["state"])
            self.show(state)
            for data in update["events"]:
                event = PlantEvent.model_validate(data)
                key = str(event.event_id)
                if key in self.seen:
                    continue
                self.seen[key] = True
                if len(self.seen) > 10000:
                    self.seen.popitem(last=False)
                fresh = (utcnow() - event.timestamp).total_seconds() <= 5
                if event.kind == "touch" and self.clients and fresh:
                    self._listen(event.event_id, event.plant_id, event.timestamp, state)
                elif event.suggested_text:
                    self.show(state, event.suggested_text)
                    self.say(event.suggested_text)

    def wake(self) -> bool:
        """The child said "Hi <plant name>": same as a pat on the touch sensor."""
        now = asyncio.get_running_loop().time()
        if not self.clients or now - self.last_listen < self.settings.touch_cooldown_seconds:
            return False
        self._listen(uuid4(), self.service.engine.profile.plant_id, utcnow(), self.service.engine.state)
        return True

    async def answer(self, utterance):
        await self.service.tick()
        profile = self.service.engine.profile
        history = [event.reason for event in self.service.context().recent_events]
        reply = await replies.reply(
            self.view(self.service.engine.state),
            utterance,
            history,
            replies.Plant(profile.name, profile.species),
            list(self.service.care.recent),
        )
        self.show(self.service.engine.state, reply.text)
        self.say(reply.text)

    async def close(self):
        self.service.subscribers.discard(self.queue)
        for task in self.tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


def install_ui(app, service, settings, viewer):
    hub = UIHub(service, settings)
    app.state.ui = hub
    router = APIRouter()
    tts.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    app.mount(tts.AUDIO_ROUTE, StaticFiles(directory=tts.CACHE_DIR), name="audio")

    @router.get("/api/health", dependencies=viewer)
    async def health():
        profile = service.engine.profile
        registration = service.registration
        return {
            "stt": stt.is_available(),
            "tts": tts.is_available(),
            "llm": replies.is_available(),
            "plant": {"name": profile.name, "species": profile.species},
            "registered": registration is not None,
            "username": registration.username if registration else None,
            "database": service.store.engine is not None,
            "thresholds": {"dry": profile.thresholds.dry_enter, "soggy": profile.thresholds.soggy_enter},
            "quick_questions": QUICK_QUESTIONS,
            "touch_listen_seconds": settings.touch_listen_seconds,
            "demo_mode": settings.demo_mode,
        }

    @router.get("/api/plant", dependencies=viewer)
    async def get_plant():
        if service.registration is None:
            raise HTTPException(404, "No plant registered yet")
        return service.registration

    @router.post("/api/plant", dependencies=viewer)
    async def register(registration: PlantRegistration):
        try:
            saved = await service.register(registration)
        except Exception:
            log.warning("Plant registration could not be saved", exc_info=True)
            raise HTTPException(503, "Couldn't save the plant right now; please try again.") from None
        hub.show(service.engine.state, f"Hi {registration.username}! I'm {registration.plant_name}.")
        return saved

    @router.post("/api/wake", dependencies=viewer)
    async def wake():
        """Called by the UI when it hears its wake phrase."""
        return {"listening": hub.wake()}

    @router.get("/api/location/zip", dependencies=viewer)
    async def zip_for_location(lat: float, lon: float):
        zip_code = await air.zip_for(lat, lon)
        if zip_code is None:
            raise HTTPException(404, "Couldn't find a US ZIP code for this location")
        return {"zip": zip_code}

    @router.post("/api/stt", dependencies=viewer)
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

    @router.websocket("/ws")
    async def websocket(ws: WebSocket):
        if not await accept_viewer(ws, settings):
            return
        queue = asyncio.Queue(maxsize=QUEUE_SIZE)
        hub.clients[ws] = queue
        queue.put_nowait(hub.view(service.engine.state).model_dump(mode="json"))

        async def on_text(raw):
            try:
                utterance = ChildUtterance.model_validate_json(raw)
            except ValidationError:
                return
            if utterance.text.strip() and len(utterance.text) <= 4000:
                await hub.answer(utterance)  # One in-flight answer per client.

        try:
            await serve(ws, queue, on_text)
        finally:
            hub.clients.pop(ws, None)

    app.include_router(router)
    return hub
