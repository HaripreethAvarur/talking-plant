"""Task 5: grounded, kid-safe replies from the ASI:One LLM.

reply() turns the current PlantState, recent care history and the child's
question into one or two short sentences in the plant's voice. It never raises:
a placeholder key, a timeout, a network error or a reply that fails the safety
and grounding checks all fall back to a scripted line.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

import httpx

from backend import config
from backend.conversation import safety
from backend.conversation.scripted import REDIRECT_LINE, scripted_reply
from shared.contracts import ChildUtterance, PlantState

log = logging.getLogger(__name__)


@dataclass
class Reply:
    text: str
    source: Literal["llm", "scripted", "redirect"]
    rejected_reason: str | None = None  # why an LLM reply was thrown away, for logs


def is_available() -> bool:
    return config.is_configured(config.ASI_API_KEY)


def _facts(state: PlantState) -> str:
    lines = [f"- mood: {state.mood.value}"]
    if state.moisture_pct is not None:
        lines.append(f"- soil moisture: {round(state.moisture_pct)}%")
    if state.light_pct is not None:
        lines.append(f"- light: {round(state.light_pct)}%")
    if state.leaf_issues:
        lines.append(f"- the camera sees these leaf problems: {', '.join(state.leaf_issues)}")
    else:
        lines.append("- the camera sees healthy green leaves")
    return "\n".join(lines)


def build_messages(state: PlantState, question: str, history: list[str]) -> list[dict]:
    system = (
        f"You are {config.PLANT_NAME}, a friendly {config.PLANT_SPECIES} plant talking to a "
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
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": question},
    ]


async def _ask_llm(messages: list[dict]) -> str:
    async with httpx.AsyncClient(timeout=config.ASI_TIMEOUT_S) as client:
        resp = await client.post(
            f"{config.ASI_BASE_URL}/chat/completions",
            headers={"Authorization": f"Bearer {config.ASI_API_KEY}"},
            json={
                "model": config.ASI_MODEL,
                "messages": messages,
                "temperature": 0.6,
                "max_tokens": 80,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip().strip('"')


def _scripted(question: str, state: PlantState, reason: str | None) -> Reply:
    text = scripted_reply(question, state, config.PLANT_NAME, config.PLANT_SPECIES)
    return Reply(text=text, source="scripted", rejected_reason=reason)


async def reply(
    state: PlantState,
    utterance: ChildUtterance,
    history: list[str] | None = None,
) -> Reply:
    question = utterance.text.strip()
    if safety.question_is_unsafe(question):
        return Reply(text=REDIRECT_LINE, source="redirect")

    if not is_available():
        return _scripted(question, state, "ASI_API_KEY not set")

    try:
        text = await _ask_llm(build_messages(state, question, history or []))
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        log.warning("ASI:One call failed, using scripted reply: %s", exc)
        return _scripted(question, state, f"llm error: {exc.__class__.__name__}")

    problem = safety.check_reply(text, state)
    if problem:
        log.info("Rejected LLM reply (%s): %r", problem, text)
        return _scripted(question, state, problem)
    return Reply(text=text, source="llm")
