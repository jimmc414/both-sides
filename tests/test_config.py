"""Tests for config.py — enums, constants, and table integrity."""
from __future__ import annotations

import pytest

from config import (
    CONSEQUENCE_TABLE,
    CONVERSATION_QUALITY_MODIFIERS,
    FACTION_COLORS,
    MAX_CHAPTERS,
    MAX_EXCHANGES_PER_SCENE,
    MAX_MEMORIES_PER_CHARACTER,
    SAVE_SLOTS,
    SLIP_SEVERITY_CONSEQUENCES,
    SUSPICION_THRESHOLDS,
    TENSION_DESCRIPTORS,
    TRUST_DESCRIPTORS,
    WAR_TENSION_PEACE,
    WAR_TENSION_START,
    WAR_TENSION_WAR,
    ChapterPhase,
    Faction,
    IntelAction,
    IntelCategory,
    SceneType,
)


class TestEnums:
    def test_faction_values(self):
        assert Faction.IRONVEIL.value == "ironveil"
        assert Faction.EMBERCROWN.value == "embercrown"

    def test_intel_action_values(self):
        expected = {"truthful", "distorted", "fabricated", "withheld"}
        assert {a.value for a in IntelAction} == expected

    def test_chapter_phase_ordering(self):
        phases = list(ChapterPhase)
        assert phases[0] == ChapterPhase.BRIEFING
        assert phases[-1] == ChapterPhase.FALLOUT


class TestConsequenceTable:
    def test_all_keys_have_required_fields(self):
        for key, value in CONSEQUENCE_TABLE.items():
            assert "trust" in value, f"Missing 'trust' for key {key}"
            assert "suspicion" in value, f"Missing 'suspicion' for key {key}"
            assert "desc" in value, f"Missing 'desc' for key {key}"

    def test_truthful_entries_positive_trust(self):
        for key, value in CONSEQUENCE_TABLE.items():
            action, was_checked, check_passed = key
            if action == IntelAction.TRUTHFUL:
                assert value["trust"] > 0, f"Truthful entry {key} should have positive trust"


class TestDescriptorCoverage:
    def test_trust_descriptors_cover_0_to_100(self):
        """Every integer 0-100 should map to exactly one trust descriptor."""
        for val in range(0, 101):
            matches = [label for lo, hi, label in TRUST_DESCRIPTORS if lo <= val <= hi]
            assert len(matches) == 1, f"Trust value {val} matched {len(matches)} descriptors"

    def test_tension_descriptors_cover_0_to_100(self):
        """Every integer 0-100 should map to exactly one tension descriptor."""
        for val in range(0, 101):
            matches = [label for lo, hi, label, _ in TENSION_DESCRIPTORS if lo <= val <= hi]
            assert len(matches) == 1, f"Tension value {val} matched {len(matches)} descriptors"

    def test_suspicion_thresholds_sorted_ascending(self):
        keys = list(SUSPICION_THRESHOLDS.keys())
        assert keys == sorted(keys)

    def test_slip_severity_keys_1_to_5(self):
        assert set(SLIP_SEVERITY_CONSEQUENCES.keys()) == {1, 2, 3, 4, 5}

    def test_conversation_quality_keys(self):
        expected = {"excellent", "good", "neutral", "poor", "hostile"}
        assert set(CONVERSATION_QUALITY_MODIFIERS.keys()) == expected
