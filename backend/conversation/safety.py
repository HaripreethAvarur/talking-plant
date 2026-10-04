"""Kid-safety and grounding checks for LLM replies (Task 5).

check_reply() returns a reason string when a reply must be thrown away, or None
when it is fine. The caller then falls back to a scripted line.
"""

import re

from shared.contracts import Mood
from shared.contracts import UIPlantState as PlantState

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
    "wet": re.compile(r"\b(too wet|soggy|too much water|overwatered|drowning)\b", re.IGNORECASE),
    "leaves": re.compile(r"\b(yellow|brown|wilt|wilting|wilted|sick|droopy|disease)\b", re.IGNORECASE),
}


# A sentence about the air or weather ("the air outside is dry") isn't the plant saying it's
# thirsty, unless it also talks about the plant itself ("...but my soil feels dry").
_WEATHER = re.compile(r"\b(air|weather|outside|humid|humidity)\b", re.IGNORECASE)
_SELF = re.compile(r"\b(my|me|i|i'm|soil|roots?|leaves|pot)\b", re.IGNORECASE)


def _without_weather_talk(text: str) -> str:
    return " ".join(
        s for s in re.split(r"(?<=[.!?])\s+", text) if not (_WEATHER.search(s) and not _SELF.search(s))
    )


def question_is_unsafe(question: str) -> bool:
    return bool(_BLOCKED.search(question) or _PERSONAL_INFO.search(question))


def _real_problems(state: PlantState) -> set[str]:
    problems: set[str] = set()
    if state.mood == Mood.thirsty or (
        state.moisture_pct is not None and state.moisture_pct < MOISTURE_LOW_PCT
    ):
        problems.add("thirsty")
    if state.mood == Mood.soggy:
        problems.add("wet")
    if state.mood in (Mood.too_dark, Mood.sleepy) or (
        state.light_pct is not None and state.light_pct < LIGHT_LOW_PCT
    ):
        problems.add("dark")
    if state.mood == Mood.unwell or state.leaf_issues:
        problems.add("leaves")
    if state.looks and _PROBLEM_WORDS["leaves"].search(state.looks):
        problems.add("leaves")  # the camera description mentions it
    return problems


_LEAD_IN = re.compile(r"^(did you know|guess what|you know what|fun fact)\W*$", re.IGNORECASE)


def sentences(text: str) -> list[str]:
    """Split into sentences; a lead-in like "Did you know?" belongs to the sentence after it."""
    parts = [part.strip() for part in re.findall(r"[^.!?]+[.!?]+|[^.!?]+$", text) if part.strip()]
    merged: list[str] = []
    for part in parts:
        if merged and _LEAD_IN.match(merged[-1]):
            merged[-1] = f"{merged[-1]} {part}"
        else:
            merged.append(part)
    return merged


def _sentence_count(text: str) -> int:
    return len(sentences(text))


def check_reply(reply: str, state: PlantState, allowed_numbers=()) -> str | None:
    """allowed_numbers: extra percentages the facts gave the model (e.g. "15% more water")."""
    if not reply.strip():
        return "empty"
    if _BLOCKED.search(reply):
        return "blocked word"
    if _PERSONAL_INFO.search(reply) or _URL.search(reply):
        return "personal info or link"
    if _sentence_count(reply) > MAX_SENTENCES or len(reply.split()) > MAX_WORDS:
        return "too long"

    # Grounding: any percentage quoted must match a real reading or a number from the facts.
    readings = [v for v in (state.moisture_pct, state.light_pct, *allowed_numbers) if v is not None]
    for match in _PERCENT.finditer(reply):
        value = int(match.group(1))
        if not any(abs(value - r) <= PERCENT_TOLERANCE for r in readings):
            return f"invented reading {value}%"

    # Grounding: never complain about a problem the sensors and camera don't show.
    real = _real_problems(state)
    for problem, pattern in _PROBLEM_WORDS.items():
        text = _without_weather_talk(reply) if problem == "thirsty" else reply
        if problem not in real and pattern.search(text):
            return f"invented problem '{problem}'"
    return None
