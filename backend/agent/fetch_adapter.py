"""Optional real uAgents outbound adapter; core rules never import uAgents."""

import asyncio
import contextlib
import importlib.util
import multiprocessing
from queue import Empty, Full

from backend.agent.fetch_worker import run_worker


class FetchAdapter:
    def __init__(self, settings):
        self.settings = settings
        self.status = "untested" if settings.fetch_enabled else "disabled"
        self.detail = (
            "Not started" if settings.fetch_enabled else "Local rules need no registration or sponsor key."
        )
        self.queue = None
        self.messages = None
        self.process = None
        self.task = None

    async def start(self):
        if not self.settings.fetch_enabled:
            return
        try:
            if importlib.util.find_spec("uagents") is None:
                raise ImportError("uagents is not installed")
            # uAgents owns its event loop and cancels loop tasks on shutdown. Give it
            # a separate process so registration failure cannot cancel FastAPI tasks.
            ctx = multiprocessing.get_context("spawn")
            self.queue = ctx.Queue(maxsize=100)
            self.messages = ctx.Queue(maxsize=10)
            configuration = {
                "seed": self.settings.fetch_seed.get_secret_value(),
                "target": self.settings.fetch_target,
                "port": self.settings.fetch_port,
                "endpoint": self.settings.fetch_endpoint,
            }
            self.process = ctx.Process(
                target=run_worker, args=(configuration, self.queue, self.messages), daemon=True
            )
            self.process.start()
            self.task = asyncio.create_task(self._monitor())
        except Exception as exc:
            self.detail = f"Optional integration unavailable ({type(exc).__name__}); see docs/deployment.md."

    async def _monitor(self):
        while True:
            try:
                while True:
                    self.status, self.detail = self.messages.get_nowait()
            except Empty:
                pass
            if not self.process.is_alive():
                self.status = "untested"
                self.detail = "uAgents worker exited; local rules remain active."
                return
            await asyncio.sleep(0.5)

    def publish(self, events):
        if self.queue is None or self.process is None or not self.process.is_alive():
            return
        for event in events:
            try:
                self.queue.put_nowait(event.model_dump_json())
            except Full:
                self.detail = "Fetch queue full; latest event dropped. Backend history remains authoritative."

    async def close(self):
        if self.task:
            self.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self.task
        if self.process and self.process.pid:
            if self.process.is_alive():
                self.process.terminate()
            await asyncio.to_thread(self.process.join, 3)
            if self.process.is_alive():
                self.process.kill()
                await asyncio.to_thread(self.process.join, 1)
            self.process.close()
        for queue in (self.queue, self.messages):
            if queue is not None:
                queue.cancel_join_thread()
                queue.close()
