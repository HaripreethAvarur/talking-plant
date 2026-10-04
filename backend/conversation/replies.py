"""Grounded, kid-safe replies from the ASI:One LLM.

reply() turns the current UIPlantState, recent care history and the child's
question into one or two short sentences in the plant's voice. It never raises:
a missing key, a timeout, a network error or a reply that fails the safety
and grounding checks all fall back to a scripted line.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

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
    comfy_water: tuple[float, float] = (40, 80)  # profile dry_exit and soggy_exit, in %
    kid: str | None = None  # the signed-up child's name
    timezone: str = "America/Detroit"
    watered_seconds_ago: float | None = None  # the latest watering, if any
    water_rise: tuple[float, float] | None = None  # (from %, to %) for a smaller recent drink
    fun_fact: str | None = None  # a plant fact that fits this moment, for teaching


JUST_WATERED_SECONDS = 180


IDEAL_LIGHT_PCT = 60


def _step(gap: float) -> int:
    """A gap rounded to a friendly number: 7 -> 5, 14 -> 15."""
    return max(5, int(5 * round(gap / 5)))


def _asi_key() -> str:
    return get_settings().asi_api_key.get_secret_value()


def is_available() -> bool:
    return bool(_asi_key())


def comfort(state: PlantState, plant: Plant) -> tuple[list[str], list[int]]:
    """How far each reading is from what this plant likes, worked out here so the model
    never does arithmetic. Returns fact lines and the numbers they introduce."""
    lines, numbers = [], []
    just_watered = plant.watered_seconds_ago is not None and plant.watered_seconds_ago <= JUST_WATERED_SECONDS
    low, high = plant.comfy_water
    if plant.water_rise and not just_watered:
        before, after = (round(v) for v in plant.water_rise)
        still_low = after < (low + high) / 2 - 5
        lines.append(
            f"- my water went up from {before}% to {after}% in the last few minutes because the child "
            "gave me a drink: thank them for it"
            + (
                ", AND say I'm still a bit thirsty and a little more would make me even happier"
                if still_low
                else ""
            )
        )
        numbers += [before, after]
    ideal = round((low + high) / 2)
    if state.moisture_pct is not None:
        gap = ideal - state.moisture_pct
        if gap >= 5:
            more = _step(gap)
            lines.append(
                f"- I'd be even happier with about {more}% more water (my perfect level is {ideal}%)"
            )
            numbers += [more, ideal]
        elif gap <= -5:
            lines.append(f"- my soil is wetter than my perfect {ideal}%, so I don't want more water now")
            numbers.append(ideal)
        else:
            lines.append("- my water is just about perfect")
    if state.is_night:
        sunrise = (
            datetime.fromtimestamp(state.sunrise_at, ZoneInfo(plant.timezone)).strftime("%-I:%M %p")
            if state.sunrise_at
            else None
        )
        lines.append(
            "- it's night, so being in the dark is normal: I'm resting and can't wait for the sun "
            + (f"to come up at about {sunrise}" if sunrise else "to come up in the morning")
        )
    elif state.light_pct is not None:
        gap = IDEAL_LIGHT_PCT - state.light_pct
        if gap >= 5:
            more = _step(gap)
            lines.append(f"- about {more}% more sunshine would feel lovely")
            numbers.append(more)
        else:
            lines.append("- the sunshine is just right")
    return lines, numbers


def _clock(state: PlantState, plant: Plant) -> str:
    now = datetime.fromtimestamp(state.ts, ZoneInfo(plant.timezone))
    hour = now.hour
    part = "morning" if 5 <= hour < 12 else "afternoon" if hour < 17 else "evening" if hour < 21 else "night"
    if state.is_night and part in ("morning", "afternoon"):
        part = "early morning, before sunrise"
    return f"- it's {now:%-I:%M %p} on {now:%A} where I live ({part})"


def _facts(state: PlantState, plant: Plant) -> str:
    lines = [_clock(state, plant), f"- mood: {state.mood.value}"]
    ago = plant.watered_seconds_ago
    if ago is not None and ago <= JUST_WATERED_SECONDS:
        when = "just now" if ago < 60 else f"{round(ago / 60)} minute{'s' if ago >= 90 else ''} ago"
        lines.append(f"- the child watered me {when}: say thank you for the water first")
    if state.moisture_pct is not None:
        lines.append(f"- soil moisture: {round(state.moisture_pct)}%")
    if state.light_pct is not None:
        lines.append(f"- light: {round(state.light_pct)}%")
    lines += comfort(state, plant)[0]
    if state.weather and state.outdoor_temp_f is not None:
        humid = f", {round(state.outdoor_humidity)}% humidity" if state.outdoor_humidity is not None else ""
        lines.append(
            f"- outside where I live it's {round(state.outdoor_temp_f)}°F and {state.weather}{humid} "
            "(I live indoors, so outdoor rain doesn't water me)"
        )
    if plant.fun_fact:
        lines.append(f"- a fun plant fact you can teach right now: {plant.fun_fact}")
    if state.looks:
        lines.append(f"- how I look in my latest photo (may be imperfect): {state.looks}")
    elif state.leaf_issues is None:
        lines.append("- nobody has checked my leaves recently")
    elif state.leaf_issues:
        lines.append(f"- my leaves have these problems: {', '.join(state.leaf_issues)}")
    else:
        lines.append("- my leaves look healthy and green")
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


def _article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def build_messages(
    state: PlantState,
    question: str,
    history: list[str],
    plant: Plant,
    hourly: list[HourlyReading] = (),
    turns: list[tuple[str, str]] = (),
) -> list[dict]:
    talking_to = f" You are talking with {plant.kid}." if plant.kid else ""
    system = (
        f"You are {plant.name}, {_article(plant.species)} {plant.species} who lives in a pot and loves chatting with "
        f"kids aged 4 to 8.{talking_to}\n"
        "How you talk:\n"
        "- 1 or 2 short sentences, under 30 words, with words a 5-year-old knows.\n"
        "- Warm, playful and curious, like a cartoon best friend. Describe feelings with a fresh, "
        "fun picture each time (roots, leaves, soil, raindrops, sunbeams, bugs, wind).\n"
        "- Answer the question first, then add ONE of: a little wish from the facts (what would "
        "make you even happier), the fun plant fact below in your own words, or a short question "
        "back to the child. Teach the fun fact in about every other answer.\n"
        "- Don't list readings. Say at most one number, and only when it helps.\n"
        "- Never repeat a sentence or idea from earlier in this chat; say something new.\n"
        "- Use the child's name sometimes, not every time.\n"
        "- Match the time of day: at night talk about resting, stars and the morning sun to come; "
        "never ask for sunshine at night.\n"
        "Truth rules:\n"
        "- Only use the facts below. Any number you say must appear in the facts.\n"
        "- Never claim a problem that is not in the facts. Unless your mood is thirsty, never "
        "say dry or thirsty; say you'd love a little more water instead.\n"
        "- If the question is not about you or plants, gently steer back to plants.\n"
        "- No links, no personal questions, nothing scary or unkind.\n\n"
        f"Facts right now:\n{_facts(state, plant)}"
    )
    if history:
        system += "\n\nRecent care history:\n" + "\n".join(f"- {h}" for h in history[-5:])
    if hourly:
        system += (
            "\n\nMy last hours (use them to compare, e.g. 'drier than this morning'; "
            "only quote numbers from 'Facts right now'):\n" + hourly_table(hourly)
        )
    messages = [{"role": "system", "content": system}]
    for asked, answered in turns:
        messages += [{"role": "user", "content": asked}, {"role": "assistant", "content": answered}]
    if wants_more_after_drink(plant):
        question += (
            "\n\n(In your answer: thank me for the drink, then say you'd still love a little more water.)"
        )
    if turns:
        said = " | ".join(answered for _, answered in turns)
        question += f"\n\n(You already said: {said}. Use new words and a new idea this time.)"
    return messages + [{"role": "user", "content": question}]


def _words(text: str) -> set[str]:
    return set(re.findall(r"[a-z']+", text.lower()))


def repeats(text: str, turns: list[tuple[str, str]], limit: float = 0.5) -> bool:
    """True when the reply shares most of its words with an earlier answer."""
    words = _words(text)
    for _, answered in turns:
        earlier = _words(answered)
        if words and earlier and len(words & earlier) / len(words | earlier) >= limit:
            return True
    return False


async def _ask_llm(messages: list[dict]) -> str:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.asi_timeout_s) as client:
        resp = await client.post(
            f"{settings.asi_base_url}/chat/completions",
            headers={"Authorization": f"Bearer {_asi_key()}"},
            json={
                "model": settings.asi_model,
                "messages": messages,
                "temperature": 0.9,
                "max_tokens": 80,
            },
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip().strip('"')


MORE_WATER_LINE = "A little more water would make me even happier!"
_ASKS_MORE = re.compile(r"\b(more|another|extra|again|bit|sip)\b", re.IGNORECASE)


def wants_more_after_drink(plant: Plant) -> bool:
    """A small drink (not a full watering) that left the soil below its ideal level."""
    if not plant.water_rise:
        return False
    if plant.watered_seconds_ago is not None and plant.watered_seconds_ago <= JUST_WATERED_SECONDS:
        return False
    low, high = plant.comfy_water
    return plant.water_rise[1] < (low + high) / 2 - 5


_THANKS = re.compile(r"\bthank", re.IGNORECASE)
# "How are you / are you okay / do you need water" questions, where a watering matters.
_FEELING_QUESTION = re.compile(
    r"\b(feel|feeling|how are you|okay|ok|alright|better|happy|need|want|water|thirsty|drink)\b",
    re.IGNORECASE,
)


def thanks_due(plant: Plant) -> bool:
    """The child watered the plant a moment ago (a full watering or a small drink)."""
    just = plant.watered_seconds_ago is not None and plant.watered_seconds_ago <= JUST_WATERED_SECONDS
    return just or plant.water_rise is not None


def say_thanks(text: str) -> str:
    """Make sure a reply right after a watering thanks the child."""
    if _THANKS.search(text):
        return text
    first = safety.sentences(text)
    return f"Thank you for the water! {first[0].strip() if first else text.strip()}"


def ask_for_more(text: str) -> str:
    """Make sure a reply after a small drink also asks for a little more water."""
    if _ASKS_MORE.search(text):
        return text
    first = safety.sentences(text)
    return f"{first[0].strip() if first else text.strip()} {MORE_WATER_LINE}"


def drink_reply(question: str, state: PlantState, plant: Plant) -> str | None:
    """Offline line for "how are you" right after a drink, so the child's watering is never ignored."""
    recent = (
        plant.watered_seconds_ago is not None and plant.watered_seconds_ago <= JUST_WATERED_SECONDS
    ) or (plant.water_rise is not None)
    if not recent or state.moisture_pct is None or not _FEELING_QUESTION.search(question):
        return None
    low, high = plant.comfy_water
    more = (low + high) / 2 - state.moisture_pct >= 5
    return f"Thank you for the water! My soil is {round(state.moisture_pct)}% wet now" + (
        ", and a little more would make me even happier." if more else ", and I feel great."
    )


async def reply(
    state: PlantState,
    utterance: ChildUtterance,
    history: list[str] | None = None,
    plant: Plant | None = None,
    hourly: list[HourlyReading] = (),
    turns: list[tuple[str, str]] = (),
) -> Reply:
    """turns: the last few (question, answer) pairs, so the plant doesn't repeat itself."""
    plant = plant or Plant()
    question = utterance.text.strip()

    def scripted(reason: str | None) -> Reply:
        text = drink_reply(question, state, plant) or scripted_reply(
            question, state, plant.name, plant.species
        )
        return Reply(text=text, source="scripted", rejected_reason=reason)

    if safety.question_is_unsafe(question):
        return Reply(text=REDIRECT_LINE, source="redirect")
    # Never let the LLM guess at a reading the sensors don't have.
    if missing_reading_reply(classify(question), state):
        return scripted("reading unavailable")
    if not is_available():
        return scripted("ASI_API_KEY not set")

    messages = build_messages(state, question, history or [], plant, list(hourly), list(turns))
    try:
        text = await _ask_llm(messages)
        if repeats(text, list(turns)):
            # One retry; a near-repeat is still better than a scripted line.
            messages[-1]["content"] += f"\n(Not this again: {text})"
            text = await _ask_llm(messages)
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        log.warning("ASI:One call failed, using scripted reply: %s", exc)
        return scripted(f"llm error: {exc.__class__.__name__}")

    allowed = comfort(state, plant)[1] + (
        [state.outdoor_humidity] if state.outdoor_humidity is not None else []
    )
    if safety.check_reply(text, state, allowed) == "too long":
        # A chatty answer is usually fine once cut to its first two sentences.
        text = " ".join(part.strip() for part in safety.sentences(text)[:2]) or text
    if _FEELING_QUESTION.search(question):
        # After trimming, so the trim can't cut these off.
        if thanks_due(plant):
            text = say_thanks(text)
        if wants_more_after_drink(plant):
            text = ask_for_more(text)
    problem = safety.check_reply(text, state, allowed)
    if problem:
        log.info("Rejected LLM reply (%s): %r", problem, text)
        return scripted(problem)
    return Reply(text=text, source="llm")
