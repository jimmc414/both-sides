"""Tests for models.py — Pydantic model construction and validation."""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from config import ChapterPhase, Faction, IntelAction, IntelCategory, SceneType
from models import (
    CharacterProfile,
    ConversationLog,
    GameState,
    IntelligencePiece,
    LedgerEntry,
    NPCMemory,
    ReportAction,
    SaveData,
    SceneAnalysis,
    SlipDetection,
    WildCardEvent,
    WorldState,
    EndingConditions,
)


# ---------------------------------------------------------------------------
# CharacterProfile
# ---------------------------------------------------------------------------

class TestCharacterProfile:
    def test_valid_construction(self, make_character):
        char = make_character()
        assert char.name == "Test Char"
        assert char.faction == Faction.IRONVEIL

    def test_frozen(self, make_character):
        char = make_character()
        with pytest.raises(ValidationError):
            char.name = "Changed"

    def test_starting_trust_bounds(self, make_character):
        with pytest.raises(ValidationError):
            make_character(starting_trust=39)
        with pytest.raises(ValidationError):
            make_character(starting_trust=61)

    def test_starting_suspicion_bounds(self, make_character):
        with pytest.raises(ValidationError):
            make_character(starting_suspicion=9)
        with pytest.raises(ValidationError):
            make_character(starting_suspicion=31)

    def test_edge_trust_values(self, make_character):
        char_low = make_character(starting_trust=40)
        char_high = make_character(starting_trust=60)
        assert char_low.starting_trust == 40
        assert char_high.starting_trust == 60


# ---------------------------------------------------------------------------
# IntelligencePiece
# ---------------------------------------------------------------------------

class TestIntelligencePiece:
    def test_valid_construction(self, make_intel):
        intel = make_intel()
        assert intel.id == "ch1_military_1"
        assert intel.category == IntelCategory.MILITARY

    def test_frozen(self, make_intel):
        intel = make_intel()
        with pytest.raises(ValidationError):
            intel.significance = 1

    def test_significance_bounds(self, make_intel):
        with pytest.raises(ValidationError):
            make_intel(significance=0)
        with pytest.raises(ValidationError):
            make_intel(significance=6)

    def test_verifiability_bounds(self, make_intel):
        with pytest.raises(ValidationError):
            make_intel(verifiability=0)
        with pytest.raises(ValidationError):
            make_intel(verifiability=6)


# ---------------------------------------------------------------------------
# GameState defaults
# ---------------------------------------------------------------------------

class TestGameState:
    def test_defaults(self):
        gs = GameState()
        assert gs.chapter == 1
        assert gs.phase == ChapterPhase.BRIEFING
        assert gs.ironveil_trust == 50
        assert gs.embercrown_trust == 50
        assert gs.war_tension == 50
        assert gs.war_started is False

    def test_mutable(self):
        gs = GameState()
        gs.ironveil_trust = 75
        assert gs.ironveil_trust == 75


# ---------------------------------------------------------------------------
# LedgerEntry
# ---------------------------------------------------------------------------

class TestLedgerEntry:
    def test_defaults(self):
        entry = LedgerEntry(intel_id="test", chapter=1, true_content="content")
        assert entry.told_ironveil is None
        assert entry.told_embercrown is None
        assert entry.verified_ironveil is False
        assert entry.contradiction_with == []

    def test_actions_accept_enum(self):
        entry = LedgerEntry(
            intel_id="test", chapter=1, true_content="c",
            action_ironveil=IntelAction.TRUTHFUL,
            action_embercrown=IntelAction.FABRICATED,
        )
        assert entry.action_ironveil == IntelAction.TRUTHFUL
        assert entry.action_embercrown == IntelAction.FABRICATED


# ---------------------------------------------------------------------------
# SlipDetection and NPCMemory
# ---------------------------------------------------------------------------

class TestSlipDetection:
    def test_severity_bounds(self):
        with pytest.raises(ValidationError):
            SlipDetection(
                slip_type="contradiction", description="d", severity=0,
                detecting_character="c", evidence_quote="e",
            )
        with pytest.raises(ValidationError):
            SlipDetection(
                slip_type="contradiction", description="d", severity=6,
                detecting_character="c", evidence_quote="e",
            )

    def test_valid_severity(self):
        slip = SlipDetection(
            slip_type="contradiction", description="d", severity=3,
            detecting_character="c", evidence_quote="e",
        )
        assert slip.severity == 3


class TestNPCMemory:
    def test_importance_bounds(self):
        with pytest.raises(ValidationError):
            NPCMemory(character_name="a", chapter=1, memory_text="m", emotional_tag="suspicious", importance=0)
        with pytest.raises(ValidationError):
            NPCMemory(character_name="a", chapter=1, memory_text="m", emotional_tag="suspicious", importance=6)

    def test_default_importance(self):
        mem = NPCMemory(character_name="a", chapter=1, memory_text="m", emotional_tag="trusting")
        assert mem.importance == 3
