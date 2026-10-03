"""Send one explicitly simulated pat through the real authenticated ingestion API."""

import asyncio
import os
from uuid import uuid4

import httpx
from dotenv import load_dotenv

from backend.sensors.arduino import send
from backend.sensors.bridge import validate_backend_url
from shared.contracts import Source, Status, TouchObservation


async def main():
    load_dotenv()
    url = os.getenv("BACKEND_URL", "http://127.0.0.1:8000")
    validate_backend_url(url)
    token = os.getenv("INGESTION_TOKEN", "")
    session = uuid4()
    async with httpx.AsyncClient(
        base_url=url, timeout=5, headers={"Authorization": f"Bearer {token}"} if token else {}
    ) as client:
        for pressed in (False, True, False):
            await send(
                client,
                TouchObservation(
                    source=Source.mock,
                    device_id="mock-touch",
                    session_id=session,
                    plant_id=os.getenv("PLANT_ID", "plant-1"),
                    pressed=pressed,
                    status=Status.ok,
                ),
            )
            await asyncio.sleep(0.08)


if __name__ == "__main__":
    asyncio.run(main())
