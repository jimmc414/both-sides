"""Tests for verification_engine.py — probability calculation and verification rolls."""
from __future__ import annotations

import random

import pytest

from config import Faction, IntelAction, IntelCategory
from information_ledger import InformationLedger
from models import LedgerEntry
from verification_engine import (
    calculate_verification_probability,
    run_verification,
)


# ---------------------------------------------------------------------------
# calculate_verification_probability
# ---------------------------------------------------------------------------

class TestCalculateVerificationProbability:
    def test_withheld_always_zero(self, fresh_game_state, make_intel, populated_ledger):
        intel = make_intel()
        prob = calculate_verification_probability(
            intel, IntelAction.WITHHELD, fresh_game_state, populated_ledger, Faction.IRONVEIL,
        )
        assert prob == 0.0

    def test_base_probability(self, fresh_game_state, make_intel):
        """With minimal modifiers the probability stays near the base of 0.20."""
        intel = make_intel(verifiability=2, significance=2, category=IntelCategory.ECONOMIC)
        ledger = InformationLedger()
        prob = calculate_verification_probability(
            intel, IntelAction.TRUTHFUL, fresh_game_state, ledger, Faction.IRONVEIL,
        )
        assert prob == pytest.approx(0.20, abs=0.001)

    def test_verifiability_increases_probability(self, fresh_game_state, make_intel):
        ledger = InformationLedger()
        intel_low = make_intel(verifiability=1, significance=2, category=IntelCategory.ECONOMIC)
        intel_high = make_intel(verifiability=5, significance=2, category=IntelCategory.ECONOMIC)
        prob_low = calculate_verification_probability(
            intel_low, IntelAction.DISTORTED, fresh_game_state, ledger, Faction.IRONVEIL,
        )
        prob_high = calculate_verification_probability(
            intel_high, IntelAction.DISTORTED, fresh_game_state, ledger, Faction.IRONVEIL,
        )
        assert prob_high > prob_low

    def test_high_suspicion_increases_probability(self, fresh_game_state, make_intel):
        ledger = InformationLedger()
        intel = make_intel(verifiability=2, significance=2, category=IntelCategory.ECONOMIC)

        fresh_game_state.ironveil_suspicion = 15
        prob_low_susp = calculate_verification_probability(
            intel, IntelAction.FABRICATED, fresh_game_state, ledger, Faction.IRONVEIL,
        )
        fresh_game_state.ironveil_suspicion = 80
        prob_high_susp = calculate_verification_probability(
            intel, IntelAction.FABRICATED, fresh_game_state, ledger, Faction.IRONVEIL,
        )
        assert prob_high_susp > prob_low_susp

    def test_military_category_bonus(self, fresh_game_state, make_intel):
        ledger = InformationLedger()
        intel_military = make_intel(category=IntelCategory.MILITARY, verifiability=2, significance=2)
        intel_personal = make_intel(category=IntelCategory.PERSONAL, verifiability=2, significance=2)
        prob_mil = calculate_verification_probability(
            intel_military, IntelAction.TRUTHFUL, fresh_game_state, ledger, Faction.IRONVEIL,
        )
        prob_per = calculate_verification_probability(
            intel_personal, IntelAction.TRUTHFUL, fresh_game_state, ledger, Faction.IRONVEIL,
        )
        assert prob_mil > prob_per

    def test_unchecked_fabrications_raise_probability(self, fresh_game_state, make_intel):
        intel = make_intel(verifiability=2, significance=2, category=IntelCategory.ECONOMIC)
        # Empty ledger
        ledger_empty = InformationLedger()
        prob_no_fab = calculate_verification_probability(
            intel, IntelAction.DISTORTED, fresh_game_state, ledger_empty, Faction.EMBERCROWN,
        )
        # Ledger with unchecked fabrications targeting embercrown
        entries = [
            LedgerEntry(
                intel_id=f"fab_{i}", chapter=1, true_content="fake",
                action_embercrown=IntelAction.FABRICATED, verified_embercrown=False,
            )
            for i in range(3)
        ]
        ledger_fab = InformationLedger(entries)
        prob_fab = calculate_verification_probability(
            intel, IntelAction.DISTORTED, fresh_game_state, ledger_fab, Faction.EMBERCROWN,
        )
        assert prob_fab > prob_no_fab

    def test_significance_modifier(self, fresh_game_state, make_intel):
        ledger = InformationLedger()
        intel_low = make_intel(significance=1, verifiability=2, category=IntelCategory.ECONOMIC)
        intel_high = make_intel(significance=5, verifiability=2, category=IntelCategory.ECONOMIC)
        prob_low = calculate_verification_probability(
            intel_low, IntelAction.TRUTHFUL, fresh_game_state, ledger, Faction.IRONVEIL,
        )
        prob_high = calculate_verification_probability(
            intel_high, IntelAction.TRUTHFUL, fresh_game_state, ledger, Faction.IRONVEIL,
        )
        assert prob_high > prob_low

    def test_probability_capped_at_095(self, fresh_game_state, make_intel):
        """Even with all modifiers maxed, probability must not exceed 0.95."""
        fresh_game_state.ironveil_suspicion = 100
        intel = make_intel(verifiability=5, significance=5, category=IntelCategory.MILITARY)
        # Fill ledger with many unchecked fabrications
        entries = [
            LedgerEntry(
                intel_id=f"fab_{i}", chapter=1, true_content="fake",
                action_ironveil=IntelAction.FABRICATED, verified_ironveil=False,
            )
            for i in range(20)
        ]
        ledger = InformationLedger(entries)
        prob = calculate_verification_probability(
            intel, IntelAction.FABRICATED, fresh_game_state, ledger, Faction.IRONVEIL,
        )
        assert prob <= 0.95

    def test_probability_floored_at_zero(self, fresh_game_state, make_intel):
        """Probability never goes below 0.0 (personal intel, low everything)."""
        intel = make_intel(verifiability=1, significance=1, category=IntelCategory.PERSONAL)
        ledger = InformationLedger()
        prob = calculate_verification_probability(
            intel, IntelAction.TRUTHFUL, fresh_game_state, ledger, Faction.IRONVEIL,
        )
        assert prob >= 0.0


# ---------------------------------------------------------------------------
# run_verification
# ---------------------------------------------------------------------------

class TestRunVerification:
    def test_withheld_always_unchecked(self, make_intel):
        intel = make_intel()
        was_checked, check_passed = run_verification(intel, IntelAction.WITHHELD, 1.0)
        assert was_checked is False
        assert check_passed is None

    def test_truthful_always_passes_when_checked(self, make_intel):
        intel = make_intel()
        rng = random.Random(42)
        was_checked, check_passed = run_verification(intel, IntelAction.TRUTHFUL, 1.0, rng=rng)
        assert was_checked is True
        assert check_passed is True

    def test_fabricated_always_fails_when_checked(self, make_intel):
        intel = make_intel()
        rng = random.Random(42)
        was_checked, check_passed = run_verification(intel, IntelAction.FABRICATED, 1.0, rng=rng)
        assert was_checked is True
        assert check_passed is False

    def test_distorted_verifiability_dependent(self, make_intel):
        """Distortion catch rate scales with verifiability: 0.3 + (ver * 0.1).

        With verifiability=3, catch_rate=0.6, so pass_rate~0.4.
        With verifiability=1, catch_rate=0.4, so pass_rate~0.6.
        """
        # High verifiability (3): ~40% pass rate
        intel_mid = make_intel(verifiability=3)
        passes_mid = 0
        trials = 1000
        rng = random.Random(123)
        for _ in range(trials):
            was_checked, check_passed = run_verification(intel_mid, IntelAction.DISTORTED, 1.0, rng=rng)
            assert was_checked is True
            if check_passed:
                passes_mid += 1
        ratio_mid = passes_mid / trials
        assert 0.30 < ratio_mid < 0.50

        # Low verifiability (1): ~60% pass rate
        intel_low = make_intel(verifiability=1)
        passes_low = 0
        rng = random.Random(123)
        for _ in range(trials):
            was_checked, check_passed = run_verification(intel_low, IntelAction.DISTORTED, 1.0, rng=rng)
            assert was_checked is True
            if check_passed:
                passes_low += 1
        ratio_low = passes_low / trials
        assert 0.50 < ratio_low < 0.70

        # Low verifiability should have higher pass rate
        assert passes_low > passes_mid

    def test_zero_probability_never_checked(self, make_intel):
        intel = make_intel()
        rng = random.Random(42)
        was_checked, check_passed = run_verification(intel, IntelAction.FABRICATED, 0.0, rng=rng)
        assert was_checked is False
        assert check_passed is None

    def test_full_probability_always_checked(self, make_intel):
        intel = make_intel()
        rng = random.Random(42)
        for _ in range(20):
            was_checked, _ = run_verification(intel, IntelAction.TRUTHFUL, 1.0, rng=rng)
            assert was_checked is True

    def test_deterministic_with_seeded_rng(self, make_intel):
        """Same seed produces the same outcome."""
        intel = make_intel()
        rng1 = random.Random(42)
        rng2 = random.Random(42)
        result1 = run_verification(intel, IntelAction.DISTORTED, 0.5, rng=rng1)
        result2 = run_verification(intel, IntelAction.DISTORTED, 0.5, rng=rng2)
        assert result1 == result2

    def test_probability_affects_check_rate(self, make_intel):
        """Higher probability results in more checks over many trials."""
        intel = make_intel()
        checks_low = sum(
            1 for _ in range(500)
            if run_verification(intel, IntelAction.TRUTHFUL, 0.1, rng=random.Random(_ + 1))[0]
        )
        checks_high = sum(
            1 for _ in range(500)
            if run_verification(intel, IntelAction.TRUTHFUL, 0.9, rng=random.Random(_ + 1))[0]
        )
        assert checks_high > checks_low
