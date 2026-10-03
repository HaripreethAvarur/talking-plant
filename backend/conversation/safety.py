"""Kid-safety and grounding checks for LLM replies (Task 5).

check_reply() returns a reason string when a reply must be thrown away, or None
when it is fine. The caller then falls back to a scripted line.
"""

from __future__ import annotations

import re

from shared.contracts import Mood, UIPlantState as PlantState

MAX_SENTENCES = 2
MAX_WORDS = 35
PERCENT_TOLERANCE = 3  # a quoted reading may differ from the real one by this much

# Default problem thresholds until Task 6 supplies them from the plant profile.
MOISTURE_LOW_PCT = 30
LIGHT_LOW_PCT = 20

_BLOCKED = re.compile(
    r"\b(kill|killed|die|dying|dead|death|blood|gun|knife|weapon|hate|stupid|idiot|"
    r"sex|sexy|drug|drugs|alcohol|beer|wine|cigarette|poison|suicide|hurt yourself|"
    r"damn|hell|crap|shut up)\b",
    re.IGNORECASE,
)
_PERSONAL_INFO = re.compile(
    r"\b(address|phone number|where do you live|your school|last name|password|"
    r"secret|meet me|send me)\b",
    re.IGNORECASE,
)
_URL = re.compile(r"(https?://|www\.|\.com\b)", re.IGNORECASE)
_PERCENT = re.compile(r"(\d{1,3})\s*(%|percent)", re.IGNORECASE)

# Words that claim a problem; only allowed if that problem is real.
_PROBLEM_WORDS = {
    "thirsty": re.compile(r"\b(thirsty|dry|parched)\b", re.IGNORECASE),
    "dark": re.compile(r"\b(too dark|dark in here|need more light|not enough light)\b", re.IGNORECASE),
    "leaves": re.compile(r"\b(yellow|brown|wilt|wilting|wilted|sick|droopy|disease)\b", re.IGNORECASE),
}


def question_is_unsafe(question: str) -> bool:
    return bool(_BLOCKED.search(question) or _PERSONAL_INFO.search(question))


def _real_problems(state: PlantState) -> set[str]:
    problems: set[str] = set()
    if state.mood == Mood.THIRSTY or (
        state.moisture_pct is not None and state.moisture_pct < MOISTURE_LOW_PCT
    ):
        problems.add("thirsty")
    if state.mood == Mood.TOO_DARK or (
        state.light_pct is not None and state.light_pct < LIGHT_LOW_PCT
    ):
        problems.add("dark")
    if state.mood == Mood.UNWELL or state.leaf_issues:
        problems.add("leaves")
    return problems


def _sentence_count(text: str) -> int:
    return len([s for s in re.split(r"[.!?]+", text) if s.strip()])


def check_reply(reply: str, state: PlantState) -> str | None:
    if not reply.strip():
        return "empty"
    if _BLOCKED.search(reply):
        return "blocked word"
    if _PERSONAL_INFO.search(reply) or _URL.search(reply):
        return "personal info or link"
    if _sentence_count(reply) > MAX_SENTENCES or len(reply.split()) > MAX_WORDS:
        return "too long"

    # Grounding: any percentage quoted must match a real reading.
    readings = [v for v in (state.moisture_pct, state.light_pct) if v is not None]
    for match in _PERCENT.finditer(reply):
        value = int(match.group(1))
        if not any(abs(value - r) <= PERCENT_TOLERANCE for r in readings):
            return f"invented reading {value}%"

    # Grounding: never complain about a problem the sensors and camera don't show.
    real = _real_problems(state)
    for problem, pattern in _PROBLEM_WORDS.items():
        if problem not in real and pattern.search(reply):
            return f"invented problem '{problem}'"
    return None
