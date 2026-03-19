"""Tests for trust_system.py — trust/suspicion tracking and consequences."""
from __future__ import annotations

import pytest

from config import (
    CONSEQUENCE_TABLE,
    SUSPICION_THRESHOLDS,
    TRUST_DESCRIPTORS,
    Faction,
    IntelAction,
    IntelCategory,
)
from trust_system import (
    apply_character_death,
    apply_intel_consequence,
    check_suspicion_threshold,
    clamp,
    get_faction_suspicion,
    get_faction_trust,
    get_suspicion_descriptor,
    get_trust_descriptor,
    set_faction_suspicion,
    set_faction_trust,
)


# ---------------------------------------------------------------------------
# clamp
# ---------------------------------------------------------------------------

class TestClamp:
    def test_clamp_within_range(self):
        assert clamp(50) == 50

    def test_clamp_at_lower_bound(self):
        assert clamp(0) == 0

    def test_clamp_at_upper_bound(self):
        assert clamp(100) == 100

    def test_clamp_below_lower(self):
        assert clamp(-10) == 0

    def test_clamp_above_upper(self):
        assert clamp(150) == 100

    def test_clamp_custom_range(self):
        assert clamp(5, lo=10, hi=20) == 10
        assert clamp(25, lo=10, hi=20) == 20
        assert clamp(15, lo=10, hi=20) == 15


# ---------------------------------------------------------------------------
# get_trust_descriptor
# ---------------------------------------------------------------------------

class TestGetTrustDescriptor:
    def test_hostile(self):
        assert get_trust_descriptor(0) == "Hostile"
        assert get_trust_descriptor(15) == "Hostile"

    def test_cold(self):
        assert get_trust_descriptor(16) == "Cold"
        assert get_trust_descriptor(30) == "Cold"

    def test_neutral(self):
        assert get_trust_descriptor(50) == "Neutral"

    def test_unshakeable(self):
        assert get_trust_descriptor(91) == "Unshakeable"
        assert get_trust_descriptor(100) == "Unshakeable"

    def test_out_of_range_returns_unknown(self):
        assert get_trust_descriptor(-5) == "Unknown"
        assert get_trust_descriptor(200) == "Unknown"


# ---------------------------------------------------------------------------
# get_suspicion_descriptor
# ---------------------------------------------------------------------------

class TestGetSuspicionDescriptor:
    def test_unsuspected(self):
        assert get_suspicion_descriptor(0) == "Unsuspected"
        assert get_suspicion_descriptor(15) == "Unsuspected"

    def test_watched(self):
        assert get_suspicion_descriptor(16) == "Watched"
        assert get_suspicion_descriptor(30) == "Watched"

    def test_under_scrutiny(self):
        assert get_suspicion_descriptor(31) == "Under Scrutiny"
        assert get_suspicion_descriptor(50) == "Under Scrutiny"

    def test_exposed(self):
        assert get_suspicion_descriptor(86) == "Exposed"
        assert get_suspicion_descriptor(100) == "Exposed"


# ---------------------------------------------------------------------------
# get / set faction trust and suspicion
# ---------------------------------------------------------------------------

class TestFactionGettersSetters:
    def test_get_ironveil_trust(self, fresh_game_state):
        assert get_faction_trust(fresh_game_state, Faction.IRONVEIL) == 50

    def test_get_embercrown_trust(self, fresh_game_state):
        assert get_faction_trust(fresh_game_state, Faction.EMBERCROWN) == 50

    def test_get_ironveil_suspicion(self, fresh_game_state):
        assert get_faction_suspicion(fresh_game_state, Faction.IRONVEIL) == 15

    def test_get_embercrown_suspicion(self, fresh_game_state):
        assert get_faction_suspicion(fresh_game_state, Faction.EMBERCROWN) == 15

    def test_set_ironveil_trust(self, fresh_game_state):
        set_faction_trust(fresh_game_state, Faction.IRONVEIL, 75)
        assert fresh_game_state.ironveil_trust == 75

    def test_set_embercrown_trust(self, fresh_game_state):
        set_faction_trust(fresh_game_state, Faction.EMBERCROWN, 30)
        assert fresh_game_state.embercrown_trust == 30

    def test_set_faction_trust_clamps_high(self, fresh_game_state):
        set_faction_trust(fresh_game_state, Faction.IRONVEIL, 200)
        assert fresh_game_state.ironveil_trust == 100

    def test_set_faction_trust_clamps_low(self, fresh_game_state):
        set_faction_trust(fresh_game_state, Faction.EMBERCROWN, -50)
        assert fresh_game_state.embercrown_trust == 0

    def test_set_faction_suspicion(self, fresh_game_state):
        set_faction_suspicion(fresh_game_state, Faction.IRONVEIL, 60)
        assert fresh_game_state.ironveil_suspicion == 60

    def test_set_faction_suspicion_clamps(self, fresh_game_state):
        set_faction_suspicion(fresh_game_state, Faction.EMBERCROWN, -10)
        assert fresh_game_state.embercrown_suspicion == 0


# ---------------------------------------------------------------------------
# apply_intel_consequence
# ---------------------------------------------------------------------------

class TestApplyIntelConsequence:
    def test_truthful_unchecked(self, fresh_game_state, make_intel):
        intel = make_intel(significance=3)
        old_trust = fresh_game_state.ironveil_trust
        narratives = apply_intel_consequence(
            fresh_game_state, intel, IntelAction.TRUTHFUL, Faction.IRONVEIL,
            was_checked=False, check_passed=None,
        )
        assert len(narratives) >= 1
        assert fresh_game_state.ironveil_trust > old_trust

    def test_fabricated_exposed_severe_penalty(self, fresh_game_state, make_intel):
        intel = make_intel(significance=5)
        old_trust = fresh_game_state.embercrown_trust
        old_suspicion = fresh_game_state.embercrown_suspicion
        narratives = apply_intel_consequence(
            fresh_game_state, intel, IntelAction.FABRICATED, Faction.EMBERCROWN,
            was_checked=True, check_passed=False,
        )
        assert fresh_game_state.embercrown_trust < old_trust
        assert fresh_game_state.embercrown_suspicion > old_suspicion

    def test_significance_scaling(self, fresh_game_state, make_intel):
        """Higher significance = bigger trust/suspicion changes."""
        gs_low = fresh_game_state.model_copy(deep=True)
        gs_high = fresh_game_state.model_copy(deep=True)

        intel_low = make_intel(significance=1)
        intel_high = make_intel(significance=5)

        apply_intel_consequence(gs_low, intel_low, IntelAction.TRUTHFUL, Faction.IRONVEIL, False, None)
        apply_intel_consequence(gs_high, intel_high, IntelAction.TRUTHFUL, Faction.IRONVEIL, False, None)

        trust_delta_low = gs_low.ironveil_trust - 50
        trust_delta_high = gs_high.ironveil_trust - 50
        assert trust_delta_high > trust_delta_low

    def test_character_level_changes(self, fresh_game_state, make_intel):
        intel = make_intel(significance=3)
        char_name = "General Thane"
        old_char_trust = fresh_game_state.character_trust[char_name]
        apply_intel_consequence(
            fresh_game_state, intel, IntelAction.TRUTHFUL, Faction.IRONVEIL,
            was_checked=False, check_passed=None,
            receiving_character=char_name,
        )
        assert fresh_game_state.character_trust[char_name] > old_char_trust

    def test_unknown_key_returns_empty(self, fresh_game_state, make_intel):
        """A key not in CONSEQUENCE_TABLE returns no narratives."""
        intel = make_intel()
        # TRUTHFUL + checked + False is not in the table
        narratives = apply_intel_consequence(
            fresh_game_state, intel, IntelAction.TRUTHFUL, Faction.IRONVEIL,
            was_checked=True, check_passed=False,
        )
        assert narratives == []

    def test_withheld_consequence(self, fresh_game_state, make_intel):
        intel = make_intel(significance=3)
        old_trust = fresh_game_state.ironveil_trust
        narratives = apply_intel_consequence(
            fresh_game_state, intel, IntelAction.WITHHELD, Faction.IRONVEIL,
            was_checked=False, check_passed=None,
        )
        assert len(narratives) >= 1
        assert fresh_game_state.ironveil_trust < old_trust


# ---------------------------------------------------------------------------
# apply_character_death
# ---------------------------------------------------------------------------

class TestApplyCharacterDeath:
    def test_death_marks_character_dead(self, fresh_game_state):
        narratives = apply_character_death(fresh_game_state, "General Thane")
        assert fresh_game_state.character_alive["General Thane"] is False
        assert any("killed" in n.lower() for n in narratives)

    def test_death_already_dead(self, fresh_game_state):
        fresh_game_state.character_alive["General Thane"] = False
        narratives = apply_character_death(fresh_game_state, "General Thane")
        assert narratives == []

    def test_death_unknown_character(self, fresh_game_state):
        narratives = apply_character_death(fresh_game_state, "Nobody")
        assert narratives == []

    def test_death_with_faction_cause(self, fresh_game_state):
        narratives = apply_character_death(
            fresh_game_state, "Queen Isolde", caused_by_faction=Faction.IRONVEIL,
        )
        assert fresh_game_state.character_alive["Queen Isolde"] is False
        assert len(narratives) >= 2


# ---------------------------------------------------------------------------
# check_suspicion_threshold
# ---------------------------------------------------------------------------

class TestCheckSuspicionThreshold:
    def test_below_all_thresholds(self, fresh_game_state):
        set_faction_suspicion(fresh_game_state, Faction.IRONVEIL, 20)
        result = check_suspicion_threshold(fresh_game_state, Faction.IRONVEIL)
        assert result is None

    def test_scrutiny_threshold(self, fresh_game_state):
        set_faction_suspicion(fresh_game_state, Faction.IRONVEIL, 35)
        result = check_suspicion_threshold(fresh_game_state, Faction.IRONVEIL)
        assert result == "scrutiny"

    def test_exposed_threshold(self, fresh_game_state):
        set_faction_suspicion(fresh_game_state, Faction.IRONVEIL, 100)
        result = check_suspicion_threshold(fresh_game_state, Faction.IRONVEIL)
        assert result == "exposed"

    def test_returns_highest_crossed(self, fresh_game_state):
        """When multiple thresholds are crossed, the highest one is returned."""
        set_faction_suspicion(fresh_game_state, Faction.IRONVEIL, 75)
        result = check_suspicion_threshold(fresh_game_state, Faction.IRONVEIL)
        assert result == "confrontation"
