"""Tests for prompts.scene_analysis.build_scene_analysis_prompt."""
from __future__ import annotations

import pytest

from config import ChapterPhase, Faction, SceneType
from models import CharacterProfile, ConversationLog, GameState, NPCMemory
from prompts.scene_analysis import build_scene_analysis_prompt


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


def _make_conv_log(**kw) -> ConversationLog:
    defaults = dict(
        chapter=1,
        phase=ChapterPhase.SCENE_A,
        faction=Faction.IRONVEIL,
        scene_type=SceneType.WAR_COUNCIL,
        characters_present=["TestChar"],
        exchanges=[
            {"role": "player", "text": "What news from the border?"},
            {"role": "assistant", "text": "The border is tense, agent."},
        ],
    )
    defaults.update(kw)
    return ConversationLog(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildSceneAnalysisPrompt:

    def test_returns_tuple_of_strings(self):
        chars = [_make_char()]
        gs = _make_game_state()
        conv = _make_conv_log()

        result = build_scene_analysis_prompt(
            conv_log=conv,
            characters=chars,
            game_state=gs,
            ledger_summary="No reports yet.",
            known_intel_summary="",
            cross_faction_intel=[],
            existing_memories=[],
        )

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)

    def test_system_prompt_contains_guidelines(self):
        chars = [_make_char()]
        gs = _make_game_state()
        conv = _make_conv_log()

        system, _ = build_scene_analysis_prompt(
            conv_log=conv,
            characters=chars,
            game_state=gs,
            ledger_summary="",
            known_intel_summary="",
            cross_faction_intel=[],
            existing_memories=[],
        )

        assert "SLIP DETECTION" in system

    def test_user_prompt_contains_chapter(self):
        chars = [_make_char()]
        gs = _make_game_state(chapter=3)
        conv = _make_conv_log(chapter=3)

        _, user = build_scene_analysis_prompt(
            conv_log=conv,
            characters=chars,
            game_state=gs,
            ledger_summary="",
            known_intel_summary="",
            cross_faction_intel=[],
            existing_memories=[],
        )

        assert "Chapter 3" in user

    def test_system_prompt_contains_character_profiles(self):
        chars = [
            _make_char(name="Commander Voss"),
            _make_char(name="Spy Elara"),
        ]
        gs = _make_game_state()
        conv = _make_conv_log()

        system, _ = build_scene_analysis_prompt(
            conv_log=conv,
            characters=chars,
            game_state=gs,
            ledger_summary="",
            known_intel_summary="",
            cross_faction_intel=[],
            existing_memories=[],
        )

        assert "Commander Voss" in system
        assert "Spy Elara" in system

    def test_handles_empty_transcript(self):
        chars = [_make_char()]
        gs = _make_game_state()
        conv = _make_conv_log(exchanges=[])

        # Should not crash
        system, user = build_scene_analysis_prompt(
            conv_log=conv,
            characters=chars,
            game_state=gs,
            ledger_summary="",
            known_intel_summary="",
            cross_faction_intel=[],
            existing_memories=[],
        )

        assert isinstance(system, str)
        assert isinstance(user, str)
