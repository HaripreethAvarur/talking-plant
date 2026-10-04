"""HTTP and WebSocket plumbing shared by the sensor API and the UI: bearer tokens,
the viewer WebSocket handshake, and bounded per-client queues."""

import asyncio
import contextlib
import secrets

from fastapi import Header, HTTPException, WebSocket, WebSocketDisconnect

QUEUE_SIZE = 64
MAX_FRAME_CHARS = 8000


def check_bearer(header: str | None, expected: str) -> None:
    if expected and not secrets.compare_digest(header or "", f"Bearer {expected}"):
        raise HTTPException(401, "Invalid bearer token")


def bearer(settings, field: str):
    """FastAPI dependency requiring the token in settings.<field> (no-op when it is blank)."""

    def dependency(authorization: str | None = Header(default=None)):
        check_bearer(authorization, getattr(settings, field).get_secret_value())

    return dependency


async def accept_viewer(ws: WebSocket, settings) -> bool:
    """Check the browser origin, accept, and require an auth frame when a viewer token is set."""
    origin = ws.headers.get("origin")
    if origin and origin not in settings.cors_origins:
        await ws.close(code=1008)
        return False
    await ws.accept()
    expected = settings.viewer_token.get_secret_value()
    if not expected:
        return True
    try:
        frame = await asyncio.wait_for(ws.receive_json(), timeout=5)
        token = frame.get("token") if isinstance(frame, dict) and frame.get("type") == "auth" else None
        if not isinstance(token, str) or not secrets.compare_digest(token, expected):
            raise ValueError("Invalid auth frame")
    except (ValueError, asyncio.TimeoutError, WebSocketDisconnect):
        await ws.close(code=1008)
        return False
    return True


def offer(queue: asyncio.Queue, payload) -> bool:
    """Queue a message for one client. A full queue is emptied and given a None marker,
    which disconnects that slow client; returns False in that case."""
    if queue.full():
        while not queue.empty():
            queue.get_nowait()
        queue.put_nowait(None)
        return False
    queue.put_nowait(payload)
    return True


async def serve(ws: WebSocket, queue: asyncio.Queue, on_text=None) -> None:
    """Send queued messages and pass received text frames to on_text, until either side stops."""

    async def sender():
        while True:
            message = await queue.get()
            if message is None:
                await ws.close(code=1013, reason="Slow consumer; reconnect")
                return
            await ws.send_json(message)

    async def receiver():
        while True:
            raw = await ws.receive_text()
            if len(raw) > MAX_FRAME_CHARS:
                await ws.close(code=1009)
                return
            if on_text:
                await on_text(raw)

    tasks = [asyncio.create_task(sender()), asyncio.create_task(receiver())]
    try:
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    finally:
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, WebSocketDisconnect, RuntimeError):
                await task
