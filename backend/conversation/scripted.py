"""Scripted lines: the plant's fixed announcements and the offline fallback replies.

Lines without {placeholders} are fully cacheable by the voice (Task 7);
`python -m backend.speech.pregenerate` renders all of them ahead of the demo.
"""

from __future__ import annotations

import re

from shared.contracts import Mood
from shared.contracts import UIPlantState as PlantState

# What the plant says on its own when its mood changes (used by the agent, Task 4).
MOOD_LINES: dict[Mood, str] = {
    Mood.THIRSTY: "I'm thirsty! Can you give me some water?",
    Mood.GRATEFUL: "Thank you! That feels so much better.",
    Mood.TOO_DARK: "It's a little dark in here. Can you move me near the light?",
    Mood.UNWELL: "My leaves don't feel so good today.",
    Mood.HAPPY: "I feel great today!",
}

# Questions the UI offers as buttons when speech-to-text is unavailable.
QUICK_QUESTIONS = [
    "Are you okay?",
    "What do you need?",
    "Do you like the sun?",
    "What's your name?",
]

# Keyword intents, checked in order; the first match wins.
_INTENTS: list[tuple[str, re.Pattern[str]]] = [
    ("name", re.compile(r"\b(name|who are you|what are you)\b")),
    ("water", re.compile(r"\b(water|thirsty|drink|wet|dry)\b")),
    ("light", re.compile(r"\b(light|sun|sunny|dark|lamp|window)\b")),
    ("leaves", re.compile(r"\b(leaf|leaves|yellow|brown|droopy|sick)\b")),
    ("needs", re.compile(r"\b(need|want|help|can i)\b")),
    ("love", re.compile(r"\b(like me|love|friend)\b")),
    ("food", re.compile(r"\b(eat|food|hungry)\b")),
    ("wellbeing", re.compile(r"\b(okay|ok|alright|how are you|feel|feeling|happy|sad)\b")),
]

# Fallback replies by intent and mood. "*" is the default for any mood.
_REPLIES: dict[str, dict[str, str]] = {
    "wellbeing": {
        Mood.THIRSTY: "Not really. My soil is only {moisture}% wet, so I'm thirsty.",
        Mood.TOO_DARK: "I'm okay, but my light is only {light}%. I'd love more sun.",
        Mood.UNWELL: "My leaves look a bit {leaf_issue}, so I'm not feeling my best.",
        Mood.GRATEFUL: "I'm so much better now that I had a drink!",
        "*": "I'm doing great! My soil is {moisture}% wet and I have plenty of light.",
    },
    "needs": {
        Mood.THIRSTY: "I need some water, please!",
        Mood.TOO_DARK: "I need more light. Can you put me near a window?",
        Mood.UNWELL: "Could a grown-up check my leaves for me?",
        "*": "I have everything I need right now. Thanks for asking!",
    },
    "water": {
        Mood.THIRSTY: "Yes please! My soil is only {moisture}% wet.",
        Mood.GRATEFUL: "I just had a nice drink. Thank you!",
        "*": "My soil is {moisture}% wet, so I'm not thirsty right now.",
    },
    "light": {
        Mood.TOO_DARK: "I love the sun, but it's too dark here. My light is only {light}%.",
        "*": "I love the sun! It helps me make my food.",
    },
    "leaves": {
        Mood.UNWELL: "Some of my leaves look {leaf_issue}. That means I need some care.",
        "*": "My leaves look nice and green today!",
    },
    "name": {"*": "My name is {name}! I'm a {species} plant."},
    "love": {"*": "I like you too! Thank you for taking care of me."},
    "food": {"*": "I make my own food from sunlight, water and air!"},
    "unknown": {"*": "That's a good question! I'm just a plant, so I mostly think about water and sun."},
}

# Said instead of answering when the child's question trips the safety filter.
REDIRECT_LINE = "Hmm, let's talk about plants! Do you want to know how I drink water?"


def classify(question: str) -> str:
    q = question.lower()
    for intent, pattern in _INTENTS:
        if pattern.search(q):
            return intent
    return "unknown"


# LeafObservation issue names -> words a child would say.
_LEAF_WORDS = {"yellowing": "yellow", "browning": "brown", "wilting": "droopy"}


def _fill(template: str, state: PlantState, name: str, species: str) -> str:
    issue = state.leaf_issues[0] if state.leaf_issues else "tired"
    return template.format(
        moisture=round(state.moisture_pct) if state.moisture_pct is not None else "?",
        light=round(state.light_pct) if state.light_pct is not None else "?",
        leaf_issue=_LEAF_WORDS.get(issue, issue),
        name=name,
        species=species,
    )


def scripted_reply(question: str, state: PlantState, name: str, species: str) -> str:
    def missing_reading(template: str) -> bool:
        return ("{moisture}" in template and state.moisture_pct is None) or (
            "{light}" in template and state.light_pct is None
        )

    by_mood = _REPLIES[classify(question)]
    # Never say "?%": skip to a template that only uses values we have.
    for template in (by_mood.get(state.mood), by_mood["*"], _REPLIES["unknown"]["*"]):
        if template and not missing_reading(template):
            return _fill(template, state, name, species)
    return _REPLIES["unknown"]["*"]


def cacheable_lines() -> list[str]:
    """Every scripted line that has no live values in it."""
    lines = list(MOOD_LINES.values()) + [REDIRECT_LINE]
    for by_mood in _REPLIES.values():
        lines += [t for t in by_mood.values() if "{" not in t]
    return list(dict.fromkeys(lines))
