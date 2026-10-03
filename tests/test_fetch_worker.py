import asyncio
import json
import sys
from queue import Queue
from types import SimpleNamespace

from pydantic import BaseModel

from backend.agent.fetch_worker import run_worker


def test_uagents_worker_contract_without_external_registration(monkeypatch):
    sent = []
    outgoing, messages = Queue(), Queue()
    outgoing.put(json.dumps({"event_id": "sample-event", "kind": "watering"}))

    class Context:
        async def send(self, destination, message):
            sent.append((destination, message.model_dump()))

    class Agent:
        def __init__(self, **configuration):
            self.handlers = {}

        def on_event(self, name):
            def register(function):
                self.handlers[name] = function
                return function

            return register

        def on_interval(self, period):
            assert period == 1.0
            return self.on_event("interval")

        def run(self):
            async def exercise():
                await self.handlers["startup"](Context())
                await self.handlers["interval"](Context())
                await self.handlers["interval"](Context())

            asyncio.run(exercise())

    monkeypatch.setitem(
        sys.modules, "uagents", SimpleNamespace(Agent=Agent, Context=Context, Model=BaseModel)
    )
    run_worker(
        {"seed": "test-only", "target": "recipient", "port": 8001, "endpoint": "http://localhost/submit"},
        outgoing,
        messages,
    )
    assert messages.get_nowait()[0] == "enabled"
    assert len(sent) == 1
    assert sent[0][0] == "recipient"
    assert sent[0][1]["schema_version"] == "1.0"
    assert json.loads(sent[0][1]["event_json"])["kind"] == "watering"
