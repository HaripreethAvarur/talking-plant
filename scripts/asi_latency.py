"""How fast does ASI:One answer with 24 hourly rows in the prompt? (needs ASI_API_KEY)

    python -m scripts.asi_latency                       # asi1-mini, 8 calls per variant
    python -m scripts.asi_latency --models asi1-mini asi1 --calls 10

Each call uses the real reply prompt (replies.build_messages) for a thirsty plant,
once without history and once with a synthetic day of 24 rows. Reports latency,
prompt size, and how many replies pass the safety/grounding check.
"""

import argparse
import asyncio
import statistics
import time
from datetime import timedelta

import httpx

from backend.config import get_settings
from backend.conversation import replies, safety
from backend.conversation.try_questions import QUESTIONS
from shared.contracts import HourlyReading, Mood, UIPlantState, utcnow

STATE = UIPlantState(mood=Mood.thirsty, moisture_pct=18, light_pct=64, leaf_issues=[])
LOOKS = [
    "Bright green leaves, standing up straight.",
    "Leaves look healthy and glossy.",
    "Lower leaves are starting to droop a little.",
    "Several leaves droop and the soil surface looks dry.",
]


def synthetic_day(hours: int = 24) -> list[HourlyReading]:
    """A plant drying out over a day: water falls from 62% to 18%, sun follows daylight."""
    start = utcnow() - timedelta(hours=hours)
    rows = []
    for i in range(hours):
        water = 62 - (62 - 18) * i / (hours - 1)
        local_hour = (start + timedelta(hours=i)).hour
        sun = max(0, 80 - abs(local_hour - 13) * 11)
        rows.append(
            HourlyReading(
                username="bench",
                hour=start + timedelta(hours=i),
                sun_pct=sun,
                water_pct=water,
                air_aqi=30 + i % 7,
                health=LOOKS[min(3, i // 6)],
                mood=Mood.thirsty if water < 30 else Mood.happy,
            )
        )
    return rows


async def ask(client, model, messages):
    settings = get_settings()
    started = time.perf_counter()
    response = await client.post(
        f"{settings.asi_base_url}/chat/completions",
        headers={"Authorization": f"Bearer {settings.asi_api_key.get_secret_value()}"},
        json={"model": model, "messages": messages, "temperature": 0.6, "max_tokens": 80},
    )
    seconds = time.perf_counter() - started
    response.raise_for_status()
    body = response.json()
    text = body["choices"][0]["message"]["content"].strip().strip('"')
    return seconds, body.get("usage", {}).get("prompt_tokens"), text


async def run(models, calls):
    variants = {"no history": [], "24 hours": synthetic_day()}
    plant = replies.Plant("Sprout", "pothos")
    async with httpx.AsyncClient(timeout=30) as client:
        for model in models:
            for name, hourly in variants.items():
                times, tokens, passed, samples = [], set(), 0, []
                for i in range(calls):
                    question = QUESTIONS[i % len(QUESTIONS)]
                    messages = replies.build_messages(STATE, question, [], plant, hourly)
                    seconds, prompt_tokens, text = await ask(client, model, messages)
                    times.append(seconds)
                    tokens.add(prompt_tokens)
                    problem = safety.check_reply(text, STATE)
                    passed += problem is None
                    samples.append(
                        f"    Q: {question}\n    A: {text}" + (f"  [rejected: {problem}]" if problem else "")
                    )
                times.sort()
                p90 = times[min(len(times) - 1, int(len(times) * 0.9))]
                print(
                    f"{model:10} {name:11} median {statistics.median(times):.2f}s  p90 {p90:.2f}s  "
                    f"max {times[-1]:.2f}s  prompt tokens {sorted(t for t in tokens if t)}  "
                    f"passed checks {passed}/{calls}"
                )
                print("\n".join(samples[:3]))


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--models", nargs="+", default=[get_settings().asi_model])
    parser.add_argument("--calls", type=int, default=8)
    args = parser.parse_args()
    if not replies.is_available():
        raise SystemExit("Set ASI_API_KEY in .env first.")
    asyncio.run(run(args.models, args.calls))


if __name__ == "__main__":
    main()
