import asyncio
from unittest import mock

from backend.conversation import facts, safety
from shared.contracts import Mood
from shared.contracts import UIPlantState as PlantState

HAPPY = PlantState(mood=Mood.happy, moisture_pct=45, light_pct=60, leaf_issues=[])


def test_every_fact_is_safe_and_claims_no_problem():
    for fact in facts.all_facts():
        assert safety.check_reply(fact, HAPPY) is None, fact


def test_moment_follows_the_plant():
    assert facts.moment(HAPPY, just_watered=True) == "watered"
    assert facts.moment(HAPPY.model_copy(update={"mood": Mood.thirsty}), False) == "thirsty"
    assert facts.moment(HAPPY.model_copy(update={"is_night": True}), False) == "night"
    assert facts.moment(HAPPY.model_copy(update={"mood": Mood.too_dark, "light_pct": 5}), False) == "dark_day"
    assert facts.moment(HAPPY, False) == "sunny"


def test_picker_rotates_and_adds_type_facts():
    picker = facts.FactPicker()
    first, second = picker.pick("watered"), picker.pick("watered")
    assert first != second
    succulent = {picker.pick("general", "succulent") for _ in range(6)}
    assert any("aloe" in fact or "thick leaves" in fact for fact in succulent)


def test_teach_shares_one_fact_then_waits():
    from backend import ui

    async def run():
        hub = ui.UIHub.__new__(ui.UIHub)
        hub.facts, hub.last_fact = facts.FactPicker(), float("-inf")
        hub.service = mock.Mock()
        hub.service.engine.profile.plant_type.value = "succulent"
        hub.service.engine.profile.species = "Aloe vera"
        hub.show, hub.say = mock.Mock(), mock.Mock()
        hub.teach(HAPPY, "watered")
        hub.teach(HAPPY, "watered")
        return hub.say.call_args_list

    calls = asyncio.run(run())
    assert len(calls) == 1 and "roots" in calls[0].args[0]


def test_weather_words_and_rainy_moment():
    from backend.air import condition

    assert [condition(c) for c in (0, 2, 3, 61, 81, 95, 73)] == [
        "clear",
        "partly cloudy",
        "cloudy",
        "rainy",
        "rainy",
        "stormy",
        "snowy",
    ]
    rainy = HAPPY.model_copy(update={"weather": "rainy"})
    assert facts.moment(rainy, False) == "rainy"
    assert facts.moment(HAPPY.model_copy(update={"light_pct": 10, "outdoor_humidity": 85}), False) == "humid"
