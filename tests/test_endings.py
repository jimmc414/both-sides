"""Tests for the endings module — political outcomes and personal fates."""
from __future__ import annotations

import pytest

from config import Faction
from endings import _evaluate_personal, _evaluate_political, evaluate_ending
from models import GameState


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

def _gs(**kw):
    """Shortcut to build a GameState with custom overrides."""
    return GameState(**kw)


# ---------------------------------------------------------------------------
# Political outcomes  (_evaluate_political)
# ---------------------------------------------------------------------------


class TestPoliticalOutcome:
    def test_peace_outcome(self):
        gs = _gs(war_tension=15)
        result = _evaluate_political(gs)
        assert "peace" in result.lower()

    def test_peace_at_boundary(self):
        gs = _gs(war_tension=20)
        result = _evaluate_political(gs)
        assert "peace" in result.lower()

    def test_ironveil_victory(self):
        gs = _gs(war_started=True, war_victor=Faction.IRONVEIL.value, war_tension=95)
        result = _evaluate_political(gs)
        assert "ironveil victory" in result.lower()

    def test_embercrown_victory(self):
        gs = _gs(war_started=True, war_victor=Faction.EMBERCROWN.value, war_tension=95)
        result = _evaluate_political(gs)
        assert "embercrown victory" in result.lower()

    def test_mutual_destruction(self):
        gs = _gs(war_started=True, war_victor=None, war_tension=95)
        result = _evaluate_political(gs)
        assert "mutual destruction" in result.lower()

    def test_fragile_standoff(self):
        gs = _gs(war_tension=75, war_started=False)
        result = _evaluate_political(gs)
        assert "fragile standoff" in result.lower()

    def test_uncertain_future(self):
        gs = _gs(war_tension=45, war_started=False)
        result = _evaluate_political(gs)
        assert "uncertain future" in result.lower()


# ---------------------------------------------------------------------------
# Personal fates  (_evaluate_personal)
# ---------------------------------------------------------------------------


class TestPersonalFate:
    def test_architect_fate(self):
        gs = _gs(
            ironveil_trust=85,
            embercrown_trust=85,
            ironveil_suspicion=15,
            embercrown_suspicion=15,
        )
        result = _evaluate_personal(gs)
        assert "architect" in result.lower()

    def test_ghost_fate(self):
        gs = _gs(
            ironveil_trust=50,
            embercrown_trust=50,
            ironveil_suspicion=20,
            embercrown_suspicion=20,
        )
        result = _evaluate_personal(gs)
        assert "ghost" in result.lower()

    def test_prisoner_fate(self):
        gs = _gs(
            ironveil_trust=30,
            embercrown_trust=30,
            ironveil_suspicion=75,
            embercrown_suspicion=80,
        )
        result = _evaluate_personal(gs)
        assert "prisoner" in result.lower()

    def test_prisoner_fate_single_side_100(self):
        """A single faction reaching 100 suspicion should trigger prisoner."""
        gs = _gs(
            ironveil_trust=50,
            embercrown_trust=50,
            ironveil_suspicion=100,
            embercrown_suspicion=20,
        )
        result = _evaluate_personal(gs)
        assert "prisoner" in result.lower()

    def test_martyr_fate(self):
        gs = _gs(
            ironveil_trust=30,
            embercrown_trust=75,
            ironveil_suspicion=65,
            embercrown_suspicion=10,
        )
        result = _evaluate_personal(gs)
        assert "martyr" in result.lower()


# ---------------------------------------------------------------------------
# evaluate_ending (integration of both)
# ---------------------------------------------------------------------------


class TestEvaluateEnding:
    def test_returns_two_strings(self):
        gs = _gs(war_tension=50)
        political, personal = evaluate_ending(gs)
        assert isinstance(political, str)
        assert isinstance(personal, str)

    def test_survivor_fallback(self):
        """Equal trust, moderate suspicion should produce The Survivor."""
        gs = _gs(
            ironveil_trust=50,
            embercrown_trust=50,
            ironveil_suspicion=40,
            embercrown_suspicion=40,
        )
        result = _evaluate_personal(gs)
        assert "survivor" in result.lower()
