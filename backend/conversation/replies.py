"""Grounded, kid-safe replies from the ASI:One LLM.

reply() turns the current UIPlantState, recent care history and the child's
question into one or two short sentences in the plant's voice. It never raises:
a missing key, a timeout, a network error or a reply that fails the safety
and grounding checks all fall back to a scripted line.
"""

import logging
from dataclasses import dataclass
from typing import Literal

import httpx

from backend.config import get_settings
from backend.conversation import safety
from backend.conversation.scripted import REDIRECT_LINE, classify, missing_reading_reply, scripted_reply
from shared.contracts import ChildUtterance, HourlyReading
from shared.contracts import UIPlantState as PlantState

log = logging.getLogger(__name__)


@dataclass
class Reply:
    text: str
    source: Literal["llm", "scripted", "redirect"]
    rejected_reason: str | None = None  # why an LLM reply was thrown away, for logs


@dataclass
class Plant:
    name: str = "Sprout"
    species: str = "pothos"


def _asi_key() -> str:
    return get_settings().asi_api_key.get_secret_value()


def is_available() -> bool:
    return bool(_asi_key())


def _facts(state: PlantState) -> str:
    lines = [f"- mood: {state.mood.value}"]
    if state.moisture_pct is not None:
        lines.append(f"- soil moisture: {round(state.moisture_pct)}%")
    if state.light_pct is not None:
        lines.append(f"- light: {round(state.light_pct)}%")
    if state.leaf_issues is None:
        lines.append("- the camera has not looked at the leaves recently")
    elif state.leaf_issues:
        lines.append(f"- the camera sees these leaf problems: {', '.join(state.leaf_issues)}")
    else:
        lines.append("- the camera sees healthy green leaves")
    return "\n".join(lines)


def _value(number: float | None) -> str:
    return "-" if number is None else str(round(number))


def hourly_table(rows: list[HourlyReading]) -> str:
    """The care log as a compact table, oldest first (about 25 tokens a row with health text)."""
    lines = ["hour (UTC) | sun % | water % | air AQI | mood | how I looked"]
    for row in rows:
        mood = row.mood.value if row.mood else "-"
        cells = (_value(row.sun_pct), _value(row.water_pct), _value(row.air_aqi), mood, row.health or "-")
        lines.append(f"{row.hour:%a %H:00} | " + " | ".join(cells))
    return "\n".join(lines)


def build_messages(
    state: PlantState,
    question: str,
    history: list[str],
    plant: Plant,
    hourly: list[HourlyReading] = (),
) -> list[dict]:
    system = (
        f"You are {plant.name}, a friendly {plant.species} plant talking to a "
        "young child (age 4 to 8) at a science fair.\n"
        "Rules:\n"
        "- Answer in 1 or 2 short sentences, at most 25 words, with simple words.\n"
        "- Speak as the plant, in the first person, warm and cheerful.\n"
        "- Only use the facts below. If you mention a number, use the exact number given.\n"
        "- Never say you have a problem that is not in the facts.\n"
        "- If the question is not about you or plants, gently steer back to plants.\n"
        "- No links, no personal questions, nothing scary or unkind.\n\n"
        f"Facts right now:\n{_facts(state)}"
    )
    if history:
        system += "\n\nRecent care history:\n" + "\n".join(f"- {h}" for h in history[-5:])
    if hourly:
        system += (
            "\n\nMy last hours (use them to compare, e.g. 'drier than this morning'; "
            "only quote numbers from 'Facts right now'):\n" + hourly_table(hourly)
        )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


async def _ask_llm(messages: list[dict]) -> str:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.asi_timeout_s) as client:
        resp = await client.post(
            f"{settings.asi_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {_asi_key()}"},
            json={
                "model": settings.asi_model,
                "messages": messages,
                "temperature": 0.6,
                "max_tokens": 80,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip().strip('"')


async def reply(
    state: PlantState,
    utterance: ChildUtterance,
    history: list[str] | None = None,
    plant: Plant | None = None,
) -> Reply:
    plant = plant or Plant()
    question = utterance.text.strip()

    def scripted(reason: str | None) -> Reply:
        text = scripted_reply(question, state, plant.name, plant.species)
        return Reply(text=text, source="scripted", rejected_reason=reason)

    if safety.question_is_unsafe(question):
        return Reply(text=REDIRECT_LINE, source="redirect")
    # Never let the LLM guess at a reading the sensors don't have.
    if missing_reading_reply(classify(question), state):
        return scripted("reading unavailable")
    if not is_available():
        return scripted("ASI_API_KEY not set")

    try:
        text = await _ask_llm(build_messages(state, question, history or [], plant))
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        log.warning("ASI:One call failed, using scripted reply: %s", exc)
        return scripted(f"llm error: {exc.__class__.__name__}")

    problem = safety.check_reply(text, state)
    if problem:
        log.info("Rejected LLM reply (%s): %r", problem, text)
        return scripted(problem)
    return Reply(text=text, source="llm")
