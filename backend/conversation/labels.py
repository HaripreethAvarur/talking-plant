"""ASI:One picks the mood label for each logged hour and for each day.

The model sees the sensor readings, the plant type's thresholds and the vision model's
free-text description, and must answer with one word from a fixed list. Anything
else (no key, a timeout, an unknown word) falls back to a rule.
"""

import logging
import re
from collections import Counter

import httpx

from backend.config import get_settings
from backend.conversation.replies import hourly_table
from shared.contracts import DAY_MOODS, LOG_MOODS, HourlyReading, Mood, Thresholds

log = logging.getLogger(__name__)

MEANINGS = {
    Mood.happy: "no problem",
    Mood.thirsty: "soil too dry",
    Mood.soggy: "soil far too wet",
    Mood.too_dark: "too dark during the day",
    Mood.sleepy: "dark at night, which is normal",
    Mood.unwell: "the leaves look clearly unhealthy (yellow, brown, wilting)",
}


async def _ask(prompt: str, allowed: tuple[Mood, ...]) -> Mood | None:
    settings = get_settings()
    key = settings.asi_api_key.get_secret_value()
    if not key:
        return None
    try:
        async with httpx.AsyncClient(timeout=max(settings.asi_timeout_s, 10)) as client:
            response = await client.post(
                f"{settings.asi_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": settings.asi_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0,
                    "max_tokens": 10,
                },
            )
            response.raise_for_status()
            answer = response.json()["choices"][0]["message"]["content"].lower()
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        log.warning("ASI:One labelling failed: %s", exc)
        return None
    for word in re.findall(r"[a-z_]+", answer):
        if word in {mood.value for mood in allowed}:
            return Mood(word)
    log.info("ASI:One gave no usable label: %r", answer)
    return None


def _options(allowed) -> str:
    return "\n".join(f"- {mood.value}: {MEANINGS[mood]}" for mood in allowed)


async def label_hour(
    *,
    local_time: str,
    plant_type: str,
    thresholds: Thresholds,
    sun_pct: float | None,
    water_pct: float | None,
    air_aqi: float | None,
    health: str | None,
    fallback: Mood,
) -> Mood:
    """The hour's label. fallback is the live rule-based mood (grateful counts as happy)."""

    def show(value, unit=""):
        return "unknown" if value is None else f"{round(value)}{unit}"

    prompt = (
        f"You label how a potted {plant_type} is doing this hour. Local time: {local_time}.\n"
        f"Soil moisture {show(water_pct, '%')} (dry below {round(thresholds.dry_enter)}%, "
        f"too wet above {round(thresholds.soggy_enter)}%). Light {show(sun_pct, '%')}. "
        f"Outdoor air quality (US AQI) {show(air_aqi)}.\n"
        f"Camera description (may be wrong; trust the sensors more): {health or 'no photo this hour'}\n"
        f"The live sensor rules currently say: {fallback.value}.\n\n"
        "If more than one applies: dry soil means thirsty and very wet soil means soggy, even if "
        "leaves droop (watering problems cause drooping). Use unwell only when moisture is fine "
        "and the leaves still look clearly unhealthy.\n"
        f"Answer with exactly one word from this list:\n{_options(LOG_MOODS)}"
    )
    label = await _ask(prompt, LOG_MOODS)
    if label:
        return label
    return Mood.happy if fallback == Mood.grateful else fallback


def _rule_for_day(rows: list[HourlyReading]) -> Mood | None:
    """Most common daytime problem-free or problem label; sleepy hours are ignored."""
    moods = [row.mood for row in rows if row.mood and row.mood in DAY_MOODS]
    return Counter(moods).most_common(1)[0][0] if moods else None


async def label_day(rows: list[HourlyReading], plant_type: str) -> Mood | None:
    """The day's label from its hourly rows; None if there are no rows."""
    if not rows:
        return None
    prompt = (
        f"Here is one day of hourly records for a potted {plant_type} (times in UTC):\n"
        f"{hourly_table(rows)}\n\n"
        "Choose the one label that best describes the plant's day overall. Night-time "
        "darkness ('sleepy') is normal and is not a problem. Answer with exactly one word "
        f"from this list:\n{_options(DAY_MOODS)}"
    )
    return await _ask(prompt, DAY_MOODS) or _rule_for_day(rows) or Mood.happy
