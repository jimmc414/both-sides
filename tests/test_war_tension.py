"""Tests for war_tension.py — war tension tracking and state checks."""
from __future__ import annotations

import pytest

from config import Faction, WAR_TENSION_PEACE, WAR_TENSION_WAR, IntelAction
from models import GameState, LedgerEntry
from war_tension import (
    apply_war_tension_change,
    check_war_state,
    clamp,
    determine_war_victor,
    get_tension_descriptor,
)


# ---------------------------------------------------------------------------
# clamp (war_tension's own copy)
# ---------------------------------------------------------------------------

class TestWarTensionClamp:
    def test_within_range(self):
        assert clamp(50) == 50

    def test_below_range(self):
        assert clamp(-20) == 0

    def test_above_range(self):
        assert clamp(120) == 100

    def test_boundary_values(self):
        assert clamp(0) == 0
        assert clamp(100) == 100


# ---------------------------------------------------------------------------
# get_tension_descriptor
# ---------------------------------------------------------------------------

class TestGetTensionDescriptor:
    def test_deep_peace(self):
        label, color = get_tension_descriptor(0)
        assert label == "Deep Peace"
        assert color == "green"

    def test_total_war(self):
        label, color = get_tension_descriptor(100)
        assert label == "Total War"
        assert color == "bold red"

    def test_volatile(self):
        label, color = get_tension_descriptor(55)
        assert label == "Volatile"

    def test_out_of_range(self):
        label, color = get_tension_descriptor(-10)
        assert label == "Unknown"
        assert color == "white"


# ---------------------------------------------------------------------------
# apply_war_tension_change
# ---------------------------------------------------------------------------

class TestApplyWarTensionChange:
    def test_positive_delta(self):
        gs = GameState(war_tension=50)
        msg = apply_war_tension_change(gs, 10)
        assert gs.war_tension == 60
        assert "rises" in msg

    def test_negative_delta(self):
        gs = GameState(war_tension=50)
        msg = apply_war_tension_change(gs, -15)
        assert gs.war_tension == 35
        assert "eases" in msg

    def test_zero_delta_returns_empty(self):
        gs = GameState(war_tension=50)
        msg = apply_war_tension_change(gs, 0)
        assert gs.war_tension == 50
        assert msg == ""

    def test_clamps_at_100(self):
        gs = GameState(war_tension=95)
        apply_war_tension_change(gs, 20)
        assert gs.war_tension == 100

    def test_clamps_at_0(self):
        gs = GameState(war_tension=5)
        apply_war_tension_change(gs, -20)
        assert gs.war_tension == 0

    def test_source_included_in_message(self):
        gs = GameState(war_tension=50)
        msg = apply_war_tension_change(gs, 5, source="border skirmish")
        assert "border skirmish" in msg

    def test_label_change_in_message(self):
        gs = GameState(war_tension=50)
        msg = apply_war_tension_change(gs, 5)
        # 50 = "Tense", 55 = "Volatile" — should mention both labels
        assert "Tense" in msg
        assert "Volatile" in msg


# ---------------------------------------------------------------------------
# check_war_state
# ---------------------------------------------------------------------------

class TestCheckWarState:
    def test_war_triggered(self):
        gs = GameState(war_tension=WAR_TENSION_WAR)
        assert check_war_state(gs) == "war"

    def test_peace_triggered(self):
        gs = GameState(war_tension=WAR_TENSION_PEACE, chapter=5)
        assert check_war_state(gs) == "peace"

    def test_peace_requires_chapter_5(self):
        gs = GameState(war_tension=WAR_TENSION_PEACE, chapter=3)
        assert check_war_state(gs) is None

    def test_middle_tension_returns_none(self):
        gs = GameState(war_tension=50, chapter=5)
        assert check_war_state(gs) is None


# ---------------------------------------------------------------------------
# determine_war_victor
# ---------------------------------------------------------------------------

class TestDetermineWarVictor:
    def test_no_victor_if_war_not_started(self):
        gs = GameState(war_started=False)
        assert determine_war_victor(gs) is None

    def test_ironveil_wins(self):
        gs = GameState(war_started=True, ledger_entries=[
            LedgerEntry(intel_id="a", chapter=1, true_content="x", action_ironveil=IntelAction.TRUTHFUL, action_embercrown=IntelAction.FABRICATED),
            LedgerEntry(intel_id="b", chapter=1, true_content="y", action_ironveil=IntelAction.TRUTHFUL, action_embercrown=IntelAction.DISTORTED),
        ])
        # BUG in code: compares to string "truthful" not IntelAction.TRUTHFUL
        # The enum's __eq__ with str works because IntelAction(str, Enum)
        result = determine_war_victor(gs)
        assert result == Faction.IRONVEIL.value

    def test_embercrown_wins(self):
        gs = GameState(war_started=True, ledger_entries=[
            LedgerEntry(intel_id="a", chapter=1, true_content="x", action_ironveil=IntelAction.FABRICATED, action_embercrown=IntelAction.TRUTHFUL),
            LedgerEntry(intel_id="b", chapter=1, true_content="y", action_ironveil=IntelAction.DISTORTED, action_embercrown=IntelAction.TRUTHFUL),
        ])
        result = determine_war_victor(gs)
        assert result == Faction.EMBERCROWN.value

    def test_mutual_destruction_on_tie(self):
        gs = GameState(war_started=True, ledger_entries=[
            LedgerEntry(intel_id="a", chapter=1, true_content="x", action_ironveil=IntelAction.TRUTHFUL, action_embercrown=IntelAction.TRUTHFUL),
        ])
        result = determine_war_victor(gs)
        assert result is None
