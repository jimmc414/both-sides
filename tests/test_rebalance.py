"""Tests for the rebalanced game mechanics.

Covers:
 1. Consequence table rebalancing (distortion > truth when unchecked)
 2. Truth tax on war tension
 3. Withholding reduces war tension
 4. Verification base rate is 20%
 5. Distortion detection is verifiability-dependent
 6. Tightened ending thresholds
 7. Cross-chapter intel reporting (stale intel)
 8. Difficulty modes
 9. Stale intel trust decay
"""
from __future__ import annotations

import random

import pytest

from config import (
    CONSEQUENCE_TABLE,
    DIFFICULTY_MODES,
    Faction,
    IntelAction,
    IntelCategory,
    TRUTH_TAX_MIN_SIGNIFICANCE,
    TRUTH_TAX_TENSION_PER_SIGNIFICANCE,
    WITHHOLD_TENSION_REDUCTION_PER_SIGNIFICANCE,
)
from endings import _evaluate_personal
from information_ledger import InformationLedger
from models import GameState, LedgerEntry, ReportAction
from report_builder import ReportBuilder
from state_machine import process_chapter_consequences
from trust_system import apply_intel_consequence
from verification_engine import (
    calculate_verification_probability,
    run_verification,
)


# ---------------------------------------------------------------------------
# 1. Consequence Table Rebalancing
# ---------------------------------------------------------------------------

class TestConsequenceRebalance:
    def test_distortion_unchecked_exceeds_truthful_unchecked(self):
        """Distortion unchecked trust (+5) should exceed truthful unchecked (+4)."""
        truth_unchecked = CONSEQUENCE_TABLE[(IntelAction.TRUTHFUL, False, None)]
        distort_unchecked = CONSEQUENCE_TABLE[(IntelAction.DISTORTED, False, None)]
        assert distort_unchecked["trust"] > truth_unchecked["trust"]

    def test_withheld_near_neutral(self):
        """Withheld should be near-neutral: -1 trust, +1 suspicion."""
        withheld = CONSEQUENCE_TABLE[(IntelAction.WITHHELD, False, None)]
        assert abs(withheld["trust"]) <= 2
        assert abs(withheld["suspicion"]) <= 2

    def test_truthful_still_positive(self):
        """Truthful entries should still have positive trust."""
        for key, value in CONSEQUENCE_TABLE.items():
            action, _, _ = key
            if action == IntelAction.TRUTHFUL:
                assert value["trust"] > 0

    def test_fabricated_caught_severe(self):
        """Fabrication caught should still be severe."""
        fab_caught = CONSEQUENCE_TABLE[(IntelAction.FABRICATED, True, False)]
        assert fab_caught["trust"] <= -10
        assert fab_caught["suspicion"] >= 15


# ---------------------------------------------------------------------------
# 2. Truth Tax on War Tension
# ---------------------------------------------------------------------------

class TestTruthTax:
    def test_truthful_high_significance_increases_tension(self, make_intel, make_character):
        """Truthful report of significance >= 3 should add extra war tension via truth tax."""
        from models import WorldState, EndingConditions
        from state_machine import initialize_game_state

        intel = make_intel(
            id="test_mil_1",
            significance=4,
            war_tension_effect={},  # No built-in tension effect
        )
        char = make_character(name="TestChar", faction=Faction.IRONVEIL)
        world = WorldState(
            inciting_incident="Test",
            ironveil_background="Test",
            embercrown_background="Test",
            ashenmere_description="Test",
            characters=[char],
            intelligence_pipeline=[intel],
            wild_card_events=[],
            ending_conditions=EndingConditions(),
        )
        gs = initialize_game_state(world)
        gs.ledger_entries.append(
            LedgerEntry(intel_id="test_mil_1", chapter=1, true_content="Test")
        )

        old_tension = gs.war_tension
        ra = ReportAction(intel_id="test_mil_1", action=IntelAction.TRUTHFUL)
        process_chapter_consequences(gs, world, [ra], {"test_mil_1": (False, None)})

        # Truth tax: (4 - 3 + 1) * 1 = 2 extra tension (no other effects)
        assert gs.war_tension > old_tension

    def test_truthful_low_significance_no_extra_tension(self, make_intel, make_character):
        """Truthful report of significance < 3 should NOT add truth tax."""
        from models import WorldState, EndingConditions
        from state_machine import initialize_game_state

        intel = make_intel(
            id="test_pol_1",
            significance=2,
            war_tension_effect={},
        )
        char = make_character(name="TestChar", faction=Faction.IRONVEIL)
        world = WorldState(
            inciting_incident="Test",
            ironveil_background="Test",
            embercrown_background="Test",
            ashenmere_description="Test",
            characters=[char],
            intelligence_pipeline=[intel],
            wild_card_events=[],
            ending_conditions=EndingConditions(),
        )
        gs = initialize_game_state(world)
        gs.ledger_entries.append(
            LedgerEntry(intel_id="test_pol_1", chapter=1, true_content="Test")
        )

        old_tension = gs.war_tension
        ra = ReportAction(intel_id="test_pol_1", action=IntelAction.TRUTHFUL)
        process_chapter_consequences(gs, world, [ra], {"test_pol_1": (False, None)})

        # No truth tax for significance 2
        # Note: faction reactions may add their own tension delta (e.g., +5 for
        # military_mobilization), but no truth tax is applied on top
        truth_tax_tension = 0  # Should be zero for significance < 3
        reaction_tension = sum(
            r.mechanical_effects.get("war_tension_delta", 0)
            for r in gs.faction_reactions
        )
        assert gs.war_tension == old_tension + reaction_tension + truth_tax_tension


# ---------------------------------------------------------------------------
# 3. Withholding Reduces War Tension
# ---------------------------------------------------------------------------

class TestWithholdPeace:
    def test_withhold_reduces_tension(self, make_intel, make_character):
        """Withholding intel should reduce war tension by significance points."""
        from models import WorldState, EndingConditions
        from state_machine import initialize_game_state

        intel = make_intel(
            id="test_mil_1",
            significance=3,
            war_tension_effect={},  # No built-in tension effect
        )
        char = make_character(name="TestChar", faction=Faction.IRONVEIL)
        world = WorldState(
            inciting_incident="Test",
            ironveil_background="Test",
            embercrown_background="Test",
            ashenmere_description="Test",
            characters=[char],
            intelligence_pipeline=[intel],
            wild_card_events=[],
            ending_conditions=EndingConditions(),
        )
        gs = initialize_game_state(world)
        gs.ledger_entries.append(
            LedgerEntry(intel_id="test_mil_1", chapter=1, true_content="Test")
        )

        old_tension = gs.war_tension
        ra = ReportAction(intel_id="test_mil_1", action=IntelAction.WITHHELD)
        process_chapter_consequences(gs, world, [ra], {"test_mil_1": (False, None)})

        # Withhold: -1 per significance = -3
        assert gs.war_tension < old_tension


# ---------------------------------------------------------------------------
# 4. Verification Base Rate
# ---------------------------------------------------------------------------

class TestVerificationBaseRate:
    def test_base_rate_is_20_percent(self, fresh_game_state, make_intel):
        """Standard difficulty base verification rate should be 0.20."""
        intel = make_intel(verifiability=2, significance=2, category=IntelCategory.ECONOMIC)
        ledger = InformationLedger()
        prob = calculate_verification_probability(
            intel, IntelAction.TRUTHFUL, fresh_game_state, ledger, Faction.IRONVEIL,
        )
        assert prob == pytest.approx(0.20, abs=0.001)

    def test_novice_has_lower_base_rate(self, fresh_game_state, make_intel):
        """Novice difficulty should have lower verification rate."""
        fresh_game_state.difficulty = "novice"
        intel = make_intel(verifiability=2, significance=2, category=IntelCategory.ECONOMIC)
        ledger = InformationLedger()
        prob = calculate_verification_probability(
            intel, IntelAction.TRUTHFUL, fresh_game_state, ledger, Faction.IRONVEIL,
        )
        assert prob == pytest.approx(0.10, abs=0.001)

    def test_spymaster_has_higher_base_rate(self, fresh_game_state, make_intel):
        """Spymaster difficulty should have higher verification rate."""
        fresh_game_state.difficulty = "spymaster"
        intel = make_intel(verifiability=2, significance=2, category=IntelCategory.ECONOMIC)
        ledger = InformationLedger()
        prob = calculate_verification_probability(
            intel, IntelAction.TRUTHFUL, fresh_game_state, ledger, Faction.IRONVEIL,
        )
        assert prob == pytest.approx(0.25, abs=0.001)


# ---------------------------------------------------------------------------
# 5. Verifiability-Dependent Distortion Detection
# ---------------------------------------------------------------------------

class TestDistortionVerifiability:
    def test_low_verifiability_harder_to_catch(self, make_intel):
        """Low verifiability distortions should be caught less often."""
        intel_low = make_intel(verifiability=1)
        intel_high = make_intel(verifiability=5)
        trials = 2000

        catches_low = 0
        catches_high = 0
        for seed in range(trials):
            rng = random.Random(seed)
            _, passed = run_verification(intel_low, IntelAction.DISTORTED, 1.0, rng)
            if passed is False:
                catches_low += 1

            rng = random.Random(seed)
            _, passed = run_verification(intel_high, IntelAction.DISTORTED, 1.0, rng)
            if passed is False:
                catches_high += 1

        # High verifiability should be caught much more often
        assert catches_high > catches_low
        # Low ver catch rate ~40%, high ver catch rate ~80%
        assert catches_low / trials < 0.50
        assert catches_high / trials > 0.70


# ---------------------------------------------------------------------------
# 6. Tightened Ending Thresholds
# ---------------------------------------------------------------------------

class TestTightenedEndings:
    def test_architect_requires_80_trust_20_suspicion(self):
        """Architect now requires trust >= 80 and suspicion <= 20."""
        # Should NOT be architect with old thresholds
        gs = GameState(
            ironveil_trust=75, embercrown_trust=75,
            ironveil_suspicion=25, embercrown_suspicion=25,
        )
        assert "architect" not in _evaluate_personal(gs).lower()

        # Should be architect with new thresholds
        gs = GameState(
            ironveil_trust=85, embercrown_trust=85,
            ironveil_suspicion=15, embercrown_suspicion=15,
        )
        assert "architect" in _evaluate_personal(gs).lower()

    def test_ghost_requires_45_trust_25_suspicion(self):
        """Ghost now requires trust >= 45 and suspicion <= 25."""
        # Should NOT be ghost with 30 suspicion (old threshold was 30)
        gs = GameState(
            ironveil_trust=50, embercrown_trust=50,
            ironveil_suspicion=30, embercrown_suspicion=30,
        )
        assert "ghost" not in _evaluate_personal(gs).lower()

        # Should be ghost with 20 suspicion
        gs = GameState(
            ironveil_trust=50, embercrown_trust=50,
            ironveil_suspicion=20, embercrown_suspicion=20,
        )
        assert "ghost" in _evaluate_personal(gs).lower()


# ---------------------------------------------------------------------------
# 7. Cross-Chapter Intel (Stale Intel)
# ---------------------------------------------------------------------------

class TestStaleIntel:
    def test_stale_intel_increases_verification_risk(self, fresh_game_state, make_intel):
        """Intel from previous chapters should have higher verification probability."""
        intel_fresh = make_intel(id="ch1_mil_1", chapter=1, verifiability=2, significance=2, category=IntelCategory.ECONOMIC)
        intel_old = make_intel(id="ch_old_1", chapter=1, verifiability=2, significance=2, category=IntelCategory.ECONOMIC)

        fresh_game_state.chapter = 1
        ledger = InformationLedger()
        prob_fresh = calculate_verification_probability(
            intel_fresh, IntelAction.DISTORTED, fresh_game_state, ledger, Faction.IRONVEIL,
        )

        fresh_game_state.chapter = 4  # 3 chapters old
        prob_stale = calculate_verification_probability(
            intel_old, IntelAction.DISTORTED, fresh_game_state, ledger, Faction.IRONVEIL,
        )

        assert prob_stale > prob_fresh
        # Should be +0.30 higher (3 chapters * 0.10)
        assert prob_stale >= prob_fresh + 0.25

    def test_stale_intel_reduces_trust_gain(self, fresh_game_state, make_intel):
        """Truthful report of stale intel should give reduced trust."""
        intel = make_intel(id="ch1_military_1", significance=3, chapter=1)

        # Fresh intel (chapter matches)
        gs_fresh = fresh_game_state.model_copy(deep=True)
        gs_fresh.chapter = 1
        old_trust = gs_fresh.embercrown_trust
        apply_intel_consequence(
            gs_fresh, intel, IntelAction.TRUTHFUL, Faction.EMBERCROWN, False, None,
        )
        fresh_gain = gs_fresh.embercrown_trust - old_trust

        # Stale intel (3 chapters old)
        gs_stale = fresh_game_state.model_copy(deep=True)
        gs_stale.chapter = 4
        old_trust = gs_stale.embercrown_trust
        apply_intel_consequence(
            gs_stale, intel, IntelAction.TRUTHFUL, Faction.EMBERCROWN, False, None,
        )
        stale_gain = gs_stale.embercrown_trust - old_trust

        assert stale_gain < fresh_gain
        assert stale_gain > 0  # Still some trust gain


# ---------------------------------------------------------------------------
# 8. Difficulty Modes
# ---------------------------------------------------------------------------

class TestDifficultyModes:
    def test_all_modes_defined(self):
        """All three difficulty modes should be defined."""
        assert "novice" in DIFFICULTY_MODES
        assert "standard" in DIFFICULTY_MODES
        assert "spymaster" in DIFFICULTY_MODES

    def test_novice_is_easier(self):
        """Novice should have lower verification and higher starting trust."""
        novice = DIFFICULTY_MODES["novice"]
        standard = DIFFICULTY_MODES["standard"]
        assert novice["verification_rate_modifier"] < standard["verification_rate_modifier"]
        assert novice["starting_trust"] > standard["starting_trust"]
        assert novice["leak_probability_modifier"] < standard["leak_probability_modifier"]

    def test_spymaster_is_harder(self):
        """Spymaster should have higher verification and lower starting trust."""
        spymaster = DIFFICULTY_MODES["spymaster"]
        standard = DIFFICULTY_MODES["standard"]
        assert spymaster["verification_rate_modifier"] > standard["verification_rate_modifier"]
        assert spymaster["starting_trust"] < standard["starting_trust"]
        assert spymaster["leak_probability_modifier"] > standard["leak_probability_modifier"]


# ---------------------------------------------------------------------------
# 9. Strategic Tradeoff Validation
# ---------------------------------------------------------------------------

class TestStrategicTradeoffs:
    """Validate that the rebalanced mechanics create genuine strategic tradeoffs."""

    def test_distortion_ev_competitive_with_truth(self):
        """At base verification rate (20%), distortion EV should be competitive with truth.

        Truth unchecked: +4 trust, -1 suspicion
        Distortion unchecked: +5 trust, -1 suspicion
        Distortion caught (with ver=3, catch_rate=60%): -6 trust, +10 suspicion

        At 20% check rate:
          Truth EV: 0.80 * 4 + 0.20 * 6 = 4.4 trust
          Distort EV: 0.80 * 5 + 0.20 * (0.40 * 5 + 0.60 * (-6)) = 4.0 + 0.20 * (-1.6) = 3.68 trust

        So distortion is slightly worse on trust EV but with higher unchecked reward.
        This creates a genuine risk/reward tradeoff.
        """
        truth_uc = CONSEQUENCE_TABLE[(IntelAction.TRUTHFUL, False, None)]["trust"]
        truth_vc = CONSEQUENCE_TABLE[(IntelAction.TRUTHFUL, True, True)]["trust"]
        dist_uc = CONSEQUENCE_TABLE[(IntelAction.DISTORTED, False, None)]["trust"]
        dist_pass = CONSEQUENCE_TABLE[(IntelAction.DISTORTED, True, True)]["trust"]
        dist_fail = CONSEQUENCE_TABLE[(IntelAction.DISTORTED, True, False)]["trust"]

        # Distortion unchecked reward exceeds truth unchecked
        assert dist_uc > truth_uc

        # But truth has higher EV at 20% check rate (safety premium)
        check_rate = 0.20
        truth_ev = (1 - check_rate) * truth_uc + check_rate * truth_vc
        # With ver=3: catch_rate=0.6, pass_rate=0.4
        dist_ev = (1 - check_rate) * dist_uc + check_rate * (0.4 * dist_pass + 0.6 * dist_fail)

        # Distortion EV should be positive but lower than truth
        # (meaning it's a viable but riskier strategy)
        assert dist_ev > 0, "Distortion should still have positive EV"
        assert truth_ev > dist_ev, "Truth should have slightly higher EV (safety premium)"
