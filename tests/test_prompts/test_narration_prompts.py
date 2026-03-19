"""Tests for prompts.narration — briefing, crossover, fallout, and opening narration."""
from __future__ import annotations

import pytest

from config import Faction
from models import (
    CharacterProfile,
    EndingConditions,
    GameState,
    IntelligencePiece,
    WildCardEvent,
    WorldState,
)
from prompts.narration import (
    build_briefing_prompt,
    build_crossover_prompt,
    build_fallout_prompt,
    build_opening_narration_prompt,
)


# ---------------------------------------------------------------------------
# Local fixture helpers
# ---------------------------------------------------------------------------

def _make_game_state(**kw) -> GameState:
    defaults = dict(
        chapter=1,
        ironveil_trust=50,
        ironveil_suspicion=15,
        embercrown_trust=50,
        embercrown_suspicion=15,
        war_tension=50,
    )
    defaults.update(kw)
    return GameState(**defaults)


def _make_char(name="TestChar", faction=Faction.IRONVEIL, **kw):
    defaults = dict(
        age=35,
        role="Spy",
        personality=["cunning"],
        speech_pattern="formal",
        goals="survive",
        secrets="none",
        starting_trust=50,
        starting_suspicion=15,
    )
    defaults.update(kw)
    return CharacterProfile(name=name, faction=faction, **defaults)


def _make_world(**kw) -> WorldState:
    defaults = dict(
        inciting_incident="A border skirmish killed a diplomat",
        ironveil_background="A disciplined nation of cold mountains",
        embercrown_background="A passionate nation of volcanic highlands",
        ashenmere_description="The neutral border territory",
        characters=[
            _make_char(name="Voss", faction=Faction.IRONVEIL),
            _make_char(name="Kael", faction=Faction.EMBERCROWN),
        ],
        intelligence_pipeline=[],
        wild_card_events=[],
    )
    defaults.update(kw)
    return WorldState(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBriefingPrompt:

    def test_briefing_prompt_returns_tuple(self):
        gs = _make_game_state()
        world = _make_world()
        result = build_briefing_prompt(gs, world)

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)

    def test_briefing_prompt_contains_chapter(self):
        gs = _make_game_state(chapter=4)
        world = _make_world()
        _, user = build_briefing_prompt(gs, world)

        assert "Chapter 4" in user


class TestCrossoverPrompt:

    def test_crossover_prompt_contains_tension(self):
        gs = _make_game_state(war_tension=72)
        _, user = build_crossover_prompt(gs)

        assert "72" in user


class TestFalloutPrompt:

    def test_fallout_prompt_contains_consequences(self):
        gs = _make_game_state(chapter=3)
        consequences = [
            "Ironveil trust dropped after exposed fabrication",
            "Border patrol increased",
        ]
        _, user = build_fallout_prompt(gs, consequences)

        assert "Ironveil trust dropped after exposed fabrication" in user
        assert "Border patrol increased" in user


class TestOpeningNarration:

    def test_opening_prompt_contains_world_info(self):
        world = _make_world(
            inciting_incident="An assassination attempt on the Ironveil ambassador"
        )
        _, user = build_opening_narration_prompt(world)

        assert "assassination attempt" in user.lower()
