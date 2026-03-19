"""Tests for prompts.conversation.build_scene_system_prompt."""
from __future__ import annotations

import pytest

from config import Faction, SceneType
from models import CharacterProfile, GameState
from prompts.conversation import build_scene_system_prompt


# ---------------------------------------------------------------------------
# Local fixture helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildSceneSystemPrompt:

    def test_contains_faction_name(self):
        chars = [_make_char(faction=Faction.IRONVEIL)]
        gs = _make_game_state()
        result = build_scene_system_prompt(
            scene_type=SceneType.WAR_COUNCIL,
            characters=chars,
            game_state=gs,
            ledger_summary="",
        )
        assert "Ironveil Compact" in result

    def test_contains_character_names(self):
        chars = [
            _make_char(name="Commander Voss", faction=Faction.IRONVEIL),
            _make_char(name="Agent Meryl", faction=Faction.IRONVEIL),
        ]
        gs = _make_game_state()
        result = build_scene_system_prompt(
            scene_type=SceneType.PRIVATE_MEETING,
            characters=chars,
            game_state=gs,
            ledger_summary="",
        )
        assert "Commander Voss" in result
        assert "Agent Meryl" in result

    def test_scene_description(self):
        chars = [_make_char(faction=Faction.EMBERCROWN)]
        gs = _make_game_state()
        result = build_scene_system_prompt(
            scene_type=SceneType.FEAST,
            characters=chars,
            game_state=gs,
            ledger_summary="",
        )
        # Feast description mentions wine and revelry
        assert "feast" in result.lower() or "revelry" in result.lower()

    def test_delivery_section(self):
        chars = [_make_char()]
        gs = _make_game_state()
        report = {"military_movement": "Troops heading north"}
        result = build_scene_system_prompt(
            scene_type=SceneType.WAR_COUNCIL,
            characters=chars,
            game_state=gs,
            ledger_summary="",
            is_delivery_scene=True,
            player_report=report,
        )
        assert "DELIVERING A REPORT" in result
        assert "Troops heading north" in result

    def test_intel_section(self):
        chars = [_make_char()]
        gs = _make_game_state()
        intel = ["Border garrison reduced to 500 troops", "Supply convoy delayed"]
        result = build_scene_system_prompt(
            scene_type=SceneType.PRIVATE_MEETING,
            characters=chars,
            game_state=gs,
            ledger_summary="",
            intel_to_share=intel,
        )
        assert "Border garrison reduced to 500 troops" in result
        assert "Supply convoy delayed" in result

    def test_memories_section(self):
        from models import NPCMemory

        chars = [_make_char(name="Alice")]
        gs = _make_game_state()
        memories = [
            NPCMemory(
                character_name="Alice",
                chapter=1,
                memory_text="Player mentioned troop counts",
                emotional_tag="suspicious",
                importance=3,
            )
        ]
        result = build_scene_system_prompt(
            scene_type=SceneType.WAR_COUNCIL,
            characters=chars,
            game_state=gs,
            ledger_summary="",
            npc_memories=memories,
        )
        assert "Player mentioned troop counts" in result
        assert "MEMORIES" in result.upper()

    def test_promises_section(self):
        chars = [_make_char()]
        gs = _make_game_state()
        promises = [
            {"promise": "Investigate the northern fort", "chapter": 1, "fulfilled": False}
        ]
        result = build_scene_system_prompt(
            scene_type=SceneType.WAR_COUNCIL,
            characters=chars,
            game_state=gs,
            ledger_summary="",
            player_promises=promises,
        )
        assert "Investigate the northern fort" in result
        assert "PROMISES" in result.upper()
