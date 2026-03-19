"""Tests for scene_evaluator.apply_analysis and _cap_memories (deterministic paths only)."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from config import ChapterPhase, Faction
from models import GameState, NPCMemory, SceneAnalysis, SlipDetection
from scene_evaluator import SceneEvaluator


# ---------------------------------------------------------------------------
# Local fixture helpers — no imports from conftest
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


def _make_analysis(**kw) -> SceneAnalysis:
    defaults = dict(
        chapter=1,
        phase=ChapterPhase.SCENE_A,
        faction=Faction.IRONVEIL,
        conversation_quality="neutral",
        faction_trust_delta=0,
        faction_suspicion_delta=0,
    )
    defaults.update(kw)
    return SceneAnalysis(**defaults)


def _make_slip(**kw) -> SlipDetection:
    defaults = dict(
        slip_type="cross_faction_knowledge",
        description="Player referenced Embercrown troop movements",
        severity=1,
        detecting_character="TestChar",
        evidence_quote="I heard your border patrols shifted",
    )
    defaults.update(kw)
    return SlipDetection(**defaults)


def _make_memory(**kw) -> NPCMemory:
    defaults = dict(
        character_name="TestChar",
        chapter=1,
        memory_text="Player spoke about supply routes",
        emotional_tag="trusting",
        importance=3,
    )
    defaults.update(kw)
    return NPCMemory(**defaults)


def _evaluator() -> SceneEvaluator:
    return SceneEvaluator(display=MagicMock())


# ---------------------------------------------------------------------------
# apply_analysis tests
# ---------------------------------------------------------------------------


class TestApplyAnalysisQuality:
    """Conversation quality modifiers on faction trust/suspicion."""

    def test_apply_analysis_neutral_quality_no_slips(self):
        ev = _evaluator()
        gs = _make_game_state()
        analysis = _make_analysis(conversation_quality="neutral")

        ev.apply_analysis(analysis, gs)

        assert gs.ironveil_trust == 50
        assert gs.ironveil_suspicion == 15

    def test_apply_analysis_excellent_quality(self):
        ev = _evaluator()
        gs = _make_game_state()
        analysis = _make_analysis(conversation_quality="excellent")

        ev.apply_analysis(analysis, gs)

        # excellent => trust +3, suspicion -2
        assert gs.ironveil_trust == 53
        assert gs.ironveil_suspicion == 13

    def test_apply_analysis_hostile_quality(self):
        ev = _evaluator()
        gs = _make_game_state()
        analysis = _make_analysis(conversation_quality="hostile")

        ev.apply_analysis(analysis, gs)

        # hostile => trust -5, suspicion +3
        assert gs.ironveil_trust == 45
        assert gs.ironveil_suspicion == 18


class TestApplyAnalysisFactionDelta:
    """Explicit faction_trust_delta / faction_suspicion_delta."""

    def test_apply_analysis_with_faction_delta(self):
        ev = _evaluator()
        gs = _make_game_state()
        analysis = _make_analysis(
            faction_trust_delta=5,
            faction_suspicion_delta=-3,
        )

        ev.apply_analysis(analysis, gs)

        # neutral quality adds 0/0, so just the deltas
        assert gs.ironveil_trust == 55
        assert gs.ironveil_suspicion == 12


class TestApplyAnalysisSlips:
    """Slip detection consequences."""

    def test_apply_analysis_slip_severity_1(self):
        ev = _evaluator()
        gs = _make_game_state()
        slip = _make_slip(severity=1)
        analysis = _make_analysis(slips=[slip])

        ev.apply_analysis(analysis, gs)

        # severity 1 => suspicion +2, trust -1
        assert gs.ironveil_trust == 49
        assert gs.ironveil_suspicion == 17

    def test_apply_analysis_slip_severity_5(self):
        ev = _evaluator()
        gs = _make_game_state()
        slip = _make_slip(severity=5)
        analysis = _make_analysis(slips=[slip])

        ev.apply_analysis(analysis, gs)

        # severity 5 => suspicion +18, trust -8
        assert gs.ironveil_trust == 42
        assert gs.ironveil_suspicion == 33

    def test_apply_analysis_multiple_slips_cumulative(self):
        ev = _evaluator()
        gs = _make_game_state()
        slip1 = _make_slip(severity=1)
        slip2 = _make_slip(severity=2, description="Second slip")
        analysis = _make_analysis(slips=[slip1, slip2])

        ev.apply_analysis(analysis, gs)

        # sev1 => susp +2, trust -1; sev2 => susp +5, trust -2
        assert gs.ironveil_trust == 47  # 50 - 1 - 2
        assert gs.ironveil_suspicion == 22  # 15 + 2 + 5

    def test_apply_analysis_returns_slip_narratives(self):
        ev = _evaluator()
        gs = _make_game_state()
        slip = _make_slip(
            slip_type="contradiction",
            description="Player contradicted earlier claim",
        )
        analysis = _make_analysis(slips=[slip])

        narratives = ev.apply_analysis(analysis, gs)

        assert len(narratives) == 1
        assert "[contradiction]" in narratives[0]
        assert "Player contradicted earlier claim" in narratives[0]


class TestApplyAnalysisCharacterAdjustments:
    """Per-character trust/suspicion adjustments."""

    def test_apply_analysis_per_character_adjustments(self):
        ev = _evaluator()
        gs = _make_game_state(
            character_trust={"Alice": 50, "Bob": 60},
            character_suspicion={"Alice": 20, "Bob": 10},
        )
        analysis = _make_analysis(
            trust_adjustments={"Alice": 5, "Bob": -3},
            suspicion_adjustments={"Alice": -2, "Bob": 4},
        )

        ev.apply_analysis(analysis, gs)

        assert gs.character_trust["Alice"] == 55
        assert gs.character_trust["Bob"] == 57
        assert gs.character_suspicion["Alice"] == 18
        assert gs.character_suspicion["Bob"] == 14

    def test_apply_analysis_character_adjustments_clamped(self):
        ev = _evaluator()
        gs = _make_game_state(
            character_trust={"LowTrust": 2, "HighTrust": 98},
            character_suspicion={"LowTrust": 2, "HighTrust": 98},
        )
        analysis = _make_analysis(
            trust_adjustments={"LowTrust": -10, "HighTrust": 10},
            suspicion_adjustments={"LowTrust": -10, "HighTrust": 10},
        )

        ev.apply_analysis(analysis, gs)

        assert gs.character_trust["LowTrust"] == 0
        assert gs.character_trust["HighTrust"] == 100
        assert gs.character_suspicion["LowTrust"] == 0
        assert gs.character_suspicion["HighTrust"] == 100


class TestApplyAnalysisStorage:
    """Memory, promise, and analysis storage."""

    def test_apply_analysis_stores_memories(self):
        ev = _evaluator()
        gs = _make_game_state()
        mem = _make_memory(character_name="Alice")
        analysis = _make_analysis(memories=[mem])

        ev.apply_analysis(analysis, gs)

        assert len(gs.npc_memories) == 1
        assert gs.npc_memories[0].character_name == "Alice"

    def test_apply_analysis_stores_promises(self):
        ev = _evaluator()
        gs = _make_game_state()
        analysis = _make_analysis(
            promises_made=["I will investigate the northern fort"],
        )

        ev.apply_analysis(analysis, gs)

        assert len(gs.player_promises) == 1
        promise = gs.player_promises[0]
        assert promise["promise"] == "I will investigate the northern fort"
        assert promise["faction"] == "ironveil"
        assert promise["chapter"] == 1
        assert promise["fulfilled"] is False

    def test_apply_analysis_stores_analysis(self):
        ev = _evaluator()
        gs = _make_game_state()
        analysis = _make_analysis()

        ev.apply_analysis(analysis, gs)

        assert len(gs.scene_analyses) == 1
        assert gs.scene_analyses[0] is analysis


# ---------------------------------------------------------------------------
# _cap_memories tests
# ---------------------------------------------------------------------------


class TestCapMemories:
    """Memory pruning logic."""

    def test_cap_memories_under_limit(self):
        ev = _evaluator()
        gs = _make_game_state()
        # 3 memories for one character — under the limit of 5
        gs.npc_memories = [
            _make_memory(character_name="Alice", chapter=i, importance=i)
            for i in range(1, 4)
        ]

        ev._cap_memories(gs)

        assert len(gs.npc_memories) == 3

    def test_cap_memories_over_limit_keeps_best(self):
        ev = _evaluator()
        gs = _make_game_state()
        # 7 memories for the same character — should be pruned to 5
        # importance is clamped 1-5, so we vary both importance and chapter
        gs.npc_memories = [
            _make_memory(character_name="Alice", chapter=1, importance=1),
            _make_memory(character_name="Alice", chapter=2, importance=1),
            _make_memory(character_name="Alice", chapter=3, importance=2),
            _make_memory(character_name="Alice", chapter=4, importance=3),
            _make_memory(character_name="Alice", chapter=5, importance=4),
            _make_memory(character_name="Alice", chapter=6, importance=5),
            _make_memory(character_name="Alice", chapter=7, importance=5),
        ]

        ev._cap_memories(gs)

        assert len(gs.npc_memories) == 5
        # Sorted by (importance desc, chapter desc):
        # (5,7), (5,6), (4,5), (3,4), (2,3) — the two importance=1 are dropped
        importances = [m.importance for m in gs.npc_memories]
        assert sorted(importances, reverse=True) == [5, 5, 4, 3, 2]
