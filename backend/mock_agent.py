"""Stand-in for the Plant Care Agent (Task 4) so the UI can be built without hardware.

Replays the "dry, then watered" demo sequence into the running server:
    python -m backend.server            # terminal 1
    python -m backend.mock_agent        # terminal 2  (add --loop to repeat)

The real agent replaces this by POSTing PlantState to /api/plant-state.
"""

from __future__ import annotations

import argparse
import time

import httpx

from backend import config
from backend.conversation.scripted import MOOD_LINES
from shared.contracts import Mood
from shared.contracts import UIPlantState as PlantState

URL = f"http://{config.SERVER_HOST}:{config.SERVER_PORT}/api/plant-state"

# (seconds to wait after this step, state)
SEQUENCE: list[tuple[float, PlantState]] = [
    (4, PlantState(mood=Mood.HAPPY, moisture_pct=40, light_pct=70)),
    (2, PlantState(mood=Mood.HAPPY, moisture_pct=31, light_pct=70)),
    (20, PlantState(mood=Mood.THIRSTY, moisture_pct=18, light_pct=68, message=MOOD_LINES[Mood.THIRSTY])),
    (1, PlantState(mood=Mood.THIRSTY, moisture_pct=34, light_pct=68)),
    (6, PlantState(mood=Mood.GRATEFUL, moisture_pct=62, light_pct=68, message=MOOD_LINES[Mood.GRATEFUL])),
    (10, PlantState(mood=Mood.HAPPY, moisture_pct=64, light_pct=69)),
]


def run_once(client: httpx.Client) -> None:
    for wait, state in SEQUENCE:
        print(f"-> {state.mood.value:9} moisture {state.moisture_pct:>3}%  {state.message or ''}")
        client.post(
            URL, content=state.model_dump_json(), headers={"content-type": "application/json"}
        ).raise_for_status()
        time.sleep(wait)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--loop", action="store_true", help="repeat the sequence forever")
    args = parser.parse_args()
    with httpx.Client(timeout=5) as client:
        run_once(client)
        while args.loop:
            run_once(client)


if __name__ == "__main__":
    main()
