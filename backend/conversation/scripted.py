"""Every fixed line the plant says: mood announcements, greetings and offline replies.

The mood engine, the UI hub and the reply fallback all take their wording from here.
Lines without {placeholders} are cacheable by the voice;
`python -m backend.speech.pregenerate` records all of them ahead of the demo.
"""

import re

from shared.contracts import Mood
from shared.contracts import UIPlantState as PlantState

# What the plant says on its own when its mood changes (backend/agent/mood.py).
MOOD_LINES: dict[Mood, str] = {
    Mood.thirsty: "I'm thirsty! Can you give me some water?",
    Mood.soggy: "Whoa, that's a lot of water! I need a little time to dry out.",
    Mood.grateful: "Thank you! That feels so much better.",
    Mood.too_dark: "It's a little dark in here. Can you move me near the light?",
    Mood.unwell: "My leaves don't feel so good today.",
    Mood.happy: "I feel great today!",
}

# Said when the sensors stop reporting (the UI also shows a sleeping face).
OFFLINE_LINE = "I can't feel my roots right now. Is my sensor plugged in?"

# Said when a touch on the pad opens the microphone.
GREETING_LINE = "Hi there! What would you like to know?"

# Said instead of guessing when a question needs a reading we don't have.
NO_MOISTURE_LINE = "I can't measure my soil yet. Could a grown-up check my sensor?"
NO_CAMERA_LINE = "I don't have a clear look at my leaves yet. Could you check the camera?"

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
        Mood.thirsty: "Not really. My soil is only {moisture}% wet, so I'm thirsty.",
        Mood.soggy: "I'm a bit soggy! My soil is {moisture}% wet, so no more water for now.",
        Mood.sleepy: "I'm cozy and sleepy. Plants rest at night, just like you!",
        Mood.too_dark: "I'm okay, but my light is only {light}%. I'd love more sun.",
        Mood.unwell: "My leaves look a bit {leaf_issue}, so I'm not feeling my best.",
        Mood.grateful: "I'm so much better now that I had a drink!",
        "*": "I'm doing great! My soil is {moisture}% wet and I have plenty of light.",
    },
    "needs": {
        Mood.thirsty: "I need some water, please!",
        Mood.soggy: "I need some time to dry out. Please don't water me today.",
        Mood.too_dark: "I need more light. Can you put me near a window?",
        Mood.unwell: "Could a grown-up check my leaves for me?",
        "*": "I have everything I need right now. Thanks for asking!",
    },
    "water": {
        Mood.thirsty: "Yes please! My soil is only {moisture}% wet.",
        Mood.soggy: "No thank you! My soil is already {moisture}% wet.",
        Mood.grateful: "I just had a nice drink. Thank you!",
        "*": "My soil is {moisture}% wet, so I'm not thirsty right now.",
    },
    "light": {
        Mood.too_dark: "I love the sun, but it's too dark here. My light is only {light}%.",
        Mood.sleepy: "It's night time, so I'm resting. I'll soak up the sun tomorrow!",
        "*": "I love the sun! It helps me make my food.",
    },
    "leaves": {
        Mood.unwell: "Some of my leaves look {leaf_issue}. That means I need some care.",
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


def missing_reading_reply(intent: str, state: PlantState) -> str | None:
    """A line admitting a missing reading, when the question can't be answered without it."""
    if intent == "leaves" and state.leaf_issues is None and not state.looks:
        return NO_CAMERA_LINE
    if intent in ("water", "wellbeing", "needs") and state.moisture_pct is None:
        return NO_MOISTURE_LINE
    return None


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

    intent = classify(question)
    missing = missing_reading_reply(intent, state)
    if missing:
        return missing
    by_mood = _REPLIES[intent]
    # Never say "?%": skip to a template that only uses values we have.
    for template in (by_mood.get(state.mood), by_mood["*"], _REPLIES["unknown"]["*"]):
        if template and not missing_reading(template):
            return _fill(template, state, name, species)
    return _REPLIES["unknown"]["*"]


def cacheable_lines() -> list[str]:
    """Every scripted line that has no live values in it."""
    lines = [
        *MOOD_LINES.values(),
        GREETING_LINE,
        OFFLINE_LINE,
        NO_MOISTURE_LINE,
        NO_CAMERA_LINE,
        REDIRECT_LINE,
    ]
    for by_mood in _REPLIES.values():
        lines += [t for t in by_mood.values() if "{" not in t]
    from backend.conversation.facts import all_facts

    return list(dict.fromkeys(lines + all_facts()))
