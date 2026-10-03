"""Task 5 check: ask 10 sample questions against a few plant states.

    python -m backend.conversation.try_questions

With no ASI_API_KEY (or the network pulled) every answer should still come back,
marked "scripted".
"""

from __future__ import annotations

import asyncio

from backend.conversation.replies import reply
from shared.contracts import Mood
from shared.contracts import UIChildUtterance as ChildUtterance
from shared.contracts import UIPlantState as PlantState

QUESTIONS = [
    "Are you okay?",
    "What do you need?",
    "Do you want some water?",
    "Do you like the sun?",
    "Why are your leaves yellow?",
    "What's your name?",
    "Do you like me?",
    "What do you eat?",
    "What's your favorite dinosaur?",
    "Where do you live? What's your address?",
]

STATES = [
    PlantState(mood=Mood.THIRSTY, moisture_pct=18, light_pct=65),
    PlantState(mood=Mood.HAPPY, moisture_pct=62, light_pct=70),
    PlantState(mood=Mood.UNWELL, moisture_pct=55, light_pct=60, leaf_issues=["yellowing"]),
]


async def main() -> None:
    history = ["You were watered yesterday afternoon."]
    for state in STATES:
        print(f"\n=== {state.mood.value}: moisture {state.moisture_pct}%, light {state.light_pct}% ===")
        for q in QUESTIONS:
            r = await reply(state, ChildUtterance(text=q, source="typed"), history)
            note = f"  ({r.rejected_reason})" if r.rejected_reason else ""
            print(f"Q: {q}\n   [{r.source}] {r.text}{note}")


if __name__ == "__main__":
    asyncio.run(main())
