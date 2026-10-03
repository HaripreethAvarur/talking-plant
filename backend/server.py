"""UI bridge: the WebSocket the React character (Task 8) talks to.

    python -m backend.server

Inbound
  - POST /api/plant-state   PlantState from the Plant Care Agent (Task 4). If it
                            carries a message, the plant speaks it (Task 7).
  - POST /api/stt           raw audio from push-to-talk -> ChildUtterance (Task 3)
  - WS   /ws                {"type": "child_utterance", ...} from the UI; the plant
                            answers with a grounded reply (Task 5) and speaks it.
Outbound on /ws
  - plant_state, speech_audio (see shared/contracts.py)
Static
  - /audio/<hash>.mp3       cached TTS clips
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from backend import config
from backend.conversation import replies
from backend.conversation.scripted import QUICK_QUESTIONS
from backend.speech import stt, tts
from shared.contracts import UIChildUtterance as ChildUtterance, Mood, UIPlantState as PlantState

log = logging.getLogger("talking_plant.server")


class Hub:
    """Holds the latest plant state and fans messages out to every open UI."""

    def __init__(self) -> None:
        self.clients: set[WebSocket] = set()
        self.state = PlantState(mood=Mood.HAPPY)
        # In-memory care history until Task 6 stores it in Neon.
        self.history: deque[str] = deque(maxlen=20)

    async def broadcast(self, payload: str) -> None:
        for ws in list(self.clients):
            try:
                await ws.send_text(payload)
            except Exception:
                self.clients.discard(ws)

    async def publish(self, state: PlantState) -> None:
        if state.mood != self.state.mood:
            self.history.append(f"At {time.strftime('%H:%M')} you felt {state.mood.value}.")
        self.state = state
        await self.broadcast(state.model_dump_json())
        if state.message:
            await self.speak(state.message)

    async def speak(self, text: str) -> None:
        audio = await tts.synthesize(text)
        await self.broadcast(audio.model_dump_json())

    async def answer(self, utterance: ChildUtterance) -> None:
        r = await replies.reply(self.state, utterance, list(self.history))
        log.info("Q %r -> [%s] %r", utterance.text, r.source, r.text)
        self.history.append(f'A child asked "{utterance.text}" and you said "{r.text}"')
        await self.publish(self.state.model_copy(update={"message": r.text, "ts": time.time()}))


hub = Hub()
app = FastAPI(title="Talking Plant UI bridge")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

tts.CACHE_DIR.mkdir(parents=True, exist_ok=True)
app.mount(tts.AUDIO_ROUTE, StaticFiles(directory=tts.CACHE_DIR), name="audio")


@app.get("/api/health")
async def health() -> dict:
    return {
        "stt": stt.is_available(),
        "tts": tts.is_available(),
        "llm": replies.is_available(),
        "plant": {"name": config.PLANT_NAME, "species": config.PLANT_SPECIES},
        "quick_questions": QUICK_QUESTIONS,
    }


@app.post("/api/plant-state")
async def post_plant_state(state: PlantState) -> dict:
    asyncio.create_task(hub.publish(state))
    return {"ok": True}


@app.post("/api/stt")
async def post_stt(request: Request) -> dict:
    audio = await request.body()
    mime = request.headers.get("content-type", "audio/webm")
    try:
        utterance = await stt.transcribe(audio, mime)
    except stt.SttUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return utterance.model_dump()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    hub.clients.add(ws)
    await ws.send_text(hub.state.model_copy(update={"message": None}).model_dump_json())
    try:
        while True:
            try:
                utterance = ChildUtterance.model_validate_json(await ws.receive_text())
            except ValidationError as exc:
                log.warning("Ignoring bad message from UI: %s", exc.errors()[:1])
                continue
            asyncio.create_task(hub.answer(utterance))
    except WebSocketDisconnect:
        pass
    finally:
        hub.clients.discard(ws)


if __name__ == "__main__":
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    log.info(
        "STT %s | TTS %s | LLM %s",
        *("on" if ok else "fallback" for ok in (stt.is_available(), tts.is_available(), replies.is_available())),
    )
    uvicorn.run(app, host=config.SERVER_HOST, port=config.SERVER_PORT)
