"""Tests for prompts.summary — ending and ledger reveal prompts."""
from __future__ import annotations

import pytest

from models import GameState
from prompts.summary import build_ending_prompt, build_ledger_reveal_prompt


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildEndingPrompt:

    def test_build_ending_prompt_returns_tuple(self):
        gs = _make_game_state(chapter=10)
        result = build_ending_prompt(
            political_outcome="Peace achieved through diplomacy",
            personal_fate="The player escapes with both identities intact",
            game_state=gs,
            ledger_text="Ch1: truthful report on troop movements",
        )

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)

    def test_ending_prompt_contains_outcomes(self):
        gs = _make_game_state(chapter=10)
        _, user = build_ending_prompt(
            political_outcome="War erupted across Ashenmere",
            personal_fate="Exposed and imprisoned by Ironveil",
            game_state=gs,
            ledger_text="",
        )

        assert "War erupted across Ashenmere" in user
        assert "Exposed and imprisoned by Ironveil" in user


class TestBuildLedgerRevealPrompt:

    def test_ledger_reveal_contains_chapter(self):
        gs = _make_game_state(chapter=5)
        _, user = build_ledger_reveal_prompt(
            chapter=5,
            chapter_entries="ch5_military_1: Truthful report on troop positions",
            game_state=gs,
        )

        assert "Chapter 5" in user
