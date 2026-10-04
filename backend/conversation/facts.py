"""Kid-sized plant facts, picked to fit what is happening to the plant right now.

The plant shares one after a real moment (a watering, a dark day, unwell leaves) and the
chat gets one that fits the current state. Lines are fixed text, so the speech cache and
`python -m backend.speech.pregenerate` can store them. They avoid the safety filter's
problem words (dry, yellow, too dark, ...) so a fact never reads as an invented complaint.
"""

from collections import deque

from shared.contracts import Mood
from shared.contracts import UIPlantState as PlantState

FACTS: dict[str, list[str]] = {
    "watered": [
        "Did you know? I drink water through my roots, like sipping through a straw!",
        "Fun fact: water travels all the way from my roots up to the tips of my leaves.",
        "Did you know? The water you give me helps me stand up tall and strong.",
    ],
    "thirsty": [
        "Did you know? My roots grow toward water, like they can smell it!",
        "Fun fact: plants are mostly made of water, just like you!",
    ],
    "sunny": [
        "Did you know? I make my own food from sunlight, water and air, and it's called photosynthesis!",
        "Fun fact: my leaves are like little solar panels that catch the sunshine.",
        "Did you know? Plants slowly turn their leaves to face the sun.",
    ],
    "dark_day": [
        "Did you know? Plants need light to make their food, so I love a sunny window.",
        "Fun fact: plants in a shady spot grow long and stretchy, reaching for light.",
    ],
    "night": [
        "Did you know? Plants rest at night and grow a little while you sleep.",
        "Fun fact: some flowers close up at night, like they're going to bed.",
    ],
    "unwell": [
        "Did you know? A plant's leaves change color to tell you it needs help.",
        "Fun fact: good light and the right amount of water keep my leaves happy and green.",
    ],
    "soggy": [
        "Did you know? Roots need air too, so they like soil that isn't full of water.",
        "Fun fact: a pot with holes in the bottom lets extra water drain out.",
    ],
    "rainy": [
        "Did you know? Rain waters plants outside, but indoor plants like me need you to water us!",
        "Fun fact: some plants catch raindrops in their leaves to drink later.",
    ],
    "humid": [
        "Did you know? Humid air has lots of tiny water drops floating in it.",
        "Fun fact: plants let out water through tiny holes in their leaves, a bit like breathing out.",
    ],
    "general": [
        "Did you know? I breathe in the air you breathe out, and give you fresh air back!",
        "Fun fact: there are more than 300,000 kinds of plants in the world.",
        "Did you know? Some trees can live for thousands of years.",
    ],
}

TYPE_FACTS: dict[str, list[str]] = {
    "succulent": [
        "Did you know? I store water in my thick leaves, like a water bottle!",
        "Fun fact: aloe plants come from warm, sunny places with very little rain.",
        "Did you know? The gooey gel inside aloe leaves can soothe a sunburn.",
    ],
    "plant": ["Did you know? Houseplants can help clean the air inside your home."],
    "tree": ["Did you know? You can count a tree's rings to find out how old it is."],
}

# What a real event teaches. Only these moments make the plant teach on its own.
EVENT_MOMENTS = {"watering": "watered", Mood.too_dark: "dark_day", Mood.unwell: "unwell", Mood.soggy: "soggy"}


def moment(state: PlantState, just_watered: bool) -> str:
    """The teaching moment that best fits the plant's current state."""
    if just_watered:
        return "watered"
    if state.mood == Mood.thirsty:
        return "thirsty"
    if state.mood == Mood.soggy:
        return "soggy"
    if state.mood == Mood.unwell:
        return "unwell"
    if state.weather in ("rainy", "drizzly", "stormy"):
        return "rainy"
    if state.is_night:
        return "night"
    if state.mood == Mood.too_dark:
        return "dark_day"
    if state.light_pct is not None and state.light_pct >= 30:
        return "sunny"
    if state.outdoor_humidity is not None and state.outdoor_humidity >= 80:
        return "humid"
    return "general"


class FactPicker:
    """Rotates through facts so the same one isn't shared twice in a row."""

    def __init__(self, memory: int = 8):
        self.recent: deque[str] = deque(maxlen=memory)

    def pick(self, moment_name: str, plant_type: str | None = None, species: str | None = None) -> str:
        pool = FACTS.get(moment_name, []) + (
            TYPE_FACTS.get(plant_type or "", []) if moment_name in ("general", "sunny", "thirsty") else []
        )
        if "aloe" not in (species or "").lower():
            pool = [fact for fact in pool if "aloe" not in fact.lower()]  # don't call a cactus an aloe
        pool = pool or FACTS["general"]
        fresh = [fact for fact in pool if fact not in self.recent] or pool
        fact = fresh[0]
        self.recent.append(fact)
        return fact


def all_facts() -> list[str]:
    lines = [fact for facts in FACTS.values() for fact in facts]
    return lines + [fact for facts in TYPE_FACTS.values() for fact in facts]
