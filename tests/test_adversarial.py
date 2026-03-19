"""Adversarial tests — edge cases, boundary conditions, and pathological inputs.

Targets:
  1. detect_contradictions       (state_machine.py)
  2. _cap_memories                (scene_evaluator.py)
  3. process_chapter_consequences (state_machine.py)
  4. evaluate_death_conditions    (state_machine.py)
  5. determine_war_victor         (war_tension.py)
  6. get_scene_type               (state_machine.py)
  7. Save/load roundtrip          (saves.py)
  8. Promise fulfillment matching (scene_evaluator.py)
"""
from __future__ import annotations

import random
from unittest.mock import MagicMock

import pytest

from config import (
    ChapterPhase,
    Faction,
    IntelAction,
    IntelCategory,
    MAX_MEMORIES_PER_CHARACTER,
    SceneType,
)
from models import (
    CharacterProfile,
    ConversationLog,
    EndingConditions,
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
)
from state_machine import (
    detect_contradictions,
    evaluate_death_conditions,
    get_scene_type,
    initialize_game_state,
    process_chapter_consequences,
)
from war_tension import determine_war_victor
from scene_evaluator import SceneEvaluator
from saves import load_game, save_game


# ---------------------------------------------------------------------------
# Shared factory helpers
# ---------------------------------------------------------------------------

def _char(
    name: str = "X",
    faction: Faction = Faction.IRONVEIL,
    death_conditions: str = "",
    **kw,
) -> CharacterProfile:
    defaults = dict(
        age=30,
        role="spy",
        personality=["smart"],
        speech_pattern="flat",
        goals="survive",
        secrets="none",
        starting_trust=50,
        starting_suspicion=15,
        death_conditions=death_conditions,
    )
    defaults.update(kw)
    return CharacterProfile(name=name, faction=faction, **defaults)


def _intel(
    id: str = "ch1_m_1",
    faction: Faction = Faction.IRONVEIL,
    significance: int = 3,
    **kw,
) -> IntelligencePiece:
    defaults = dict(
        chapter=1,
        true_content="some info",
        significance=significance,
        verifiability=3,
        category=IntelCategory.MILITARY,
        source_faction=faction,
    )
    defaults.update(kw)
    return IntelligencePiece(id=id, **defaults)


def _world(chars=None, intel=None, wildcards=None) -> WorldState:
    chars = chars or [_char("Alpha", Faction.IRONVEIL), _char("Beta", Faction.EMBERCROWN)]
    intel = intel or [_intel()]
    wildcards = wildcards or []
    return WorldState(
        inciting_incident="Test",
        ironveil_background="Iron",
        embercrown_background="Ember",
        ashenmere_description="Neutral",
        characters=chars,
        intelligence_pipeline=intel,
        wild_card_events=wildcards,
        ending_conditions=EndingConditions(),
    )


def _memory(
    name: str = "Alice",
    importance: int = 3,
    chapter: int = 1,
) -> NPCMemory:
    return NPCMemory(
        character_name=name,
        chapter=chapter,
        memory_text="something happened",
        emotional_tag="trusting",
        importance=importance,
    )


def _evaluator() -> SceneEvaluator:
    return SceneEvaluator(display=MagicMock())


# ===========================================================================
# 1. detect_contradictions — adversarial edge cases
# ===========================================================================


class TestDetectContradictionsAdversarial:

    def test_empty_ledger_returns_empty_list(self):
        """No crash and empty result when ledger has no entries."""
        gs = GameState()
        result = detect_contradictions(gs, "nonexistent_id")
        assert result == []

    def test_intel_id_not_in_ledger_returns_empty(self):
        """Non-existent intel_id returns [] without touching other entries."""
        gs = GameState()
        gs.ledger_entries = [
            LedgerEntry(
                intel_id="real_intel",
                chapter=1,
                true_content="truth",
                told_ironveil="something",
                action_ironveil=IntelAction.TRUTHFUL,
            )
        ]
        result = detect_contradictions(gs, "ghost_intel")
        assert result == []

    def test_single_entry_never_contradicts_itself(self):
        """A lone entry in the ledger cannot contradict itself."""
        gs = GameState()
        gs.ledger_entries = [
            LedgerEntry(
                intel_id="solo",
                chapter=1,
                true_content="truth",
                told_ironveil="thing",
                action_ironveil=IntelAction.FABRICATED,
            )
        ]
        result = detect_contradictions(gs, "solo")
        assert result == []

    def test_none_told_fields_skip_comparison(self):
        """Entries with None told_* fields must be skipped — no false positives."""
        gs = GameState()
        gs.ledger_entries = [
            LedgerEntry(
                intel_id="intel_a",
                chapter=1,
                true_content="truth A",
                told_ironveil=None,          # not told to ironveil
                action_ironveil=IntelAction.TRUTHFUL,
            ),
            LedgerEntry(
                intel_id="intel_b",
                chapter=1,
                true_content="truth B",
                told_ironveil=None,          # also not told to ironveil
                action_ironveil=IntelAction.FABRICATED,
            ),
        ]
        result = detect_contradictions(gs, "intel_b")
        assert result == []

    def test_none_action_field_skips_comparison(self):
        """An entry with action=None but a told value should not crash."""
        gs = GameState()
        gs.ledger_entries = [
            LedgerEntry(
                intel_id="intel_a",
                chapter=1,
                true_content="truth A",
                told_ironveil="told something",
                action_ironveil=None,           # action not yet set
            ),
            LedgerEntry(
                intel_id="intel_b",
                chapter=1,
                true_content="truth B",
                told_ironveil="told fabrication",
                action_ironveil=IntelAction.FABRICATED,
            ),
        ]
        # Should not raise; the None action means no match in the contradiction check
        result = detect_contradictions(gs, "intel_b")
        # intel_a has None action — it shouldn't be flagged as TRUTHFUL
        assert "intel_a" not in result

    def test_duplicate_intel_id_entries_only_first_used_as_new_entry(self):
        """If multiple ledger entries share the same intel_id, the function
        uses the first match as new_entry and skips all others with the same
        id in the comparison loop — duplicate entries should not self-contradict."""
        gs = GameState()
        gs.ledger_entries = [
            LedgerEntry(
                intel_id="dup",
                chapter=1,
                true_content="truth",
                told_ironveil="truth text",
                action_ironveil=IntelAction.TRUTHFUL,
            ),
            LedgerEntry(
                intel_id="dup",     # same id — second occurrence
                chapter=1,
                true_content="truth",
                told_ironveil="fabricated text",
                action_ironveil=IntelAction.FABRICATED,
            ),
        ]
        # Should not crash and should not report "dup" contradicting itself
        result = detect_contradictions(gs, "dup")
        assert "dup" not in result

    def test_distorted_entry_also_triggers_contradiction(self):
        """DISTORTED (not just FABRICATED) vs a prior TRUTHFUL is a contradiction."""
        gs = GameState()
        gs.ledger_entries = [
            LedgerEntry(
                intel_id="intel_old",
                chapter=1,
                true_content="old truth",
                told_embercrown="old truth text",
                action_embercrown=IntelAction.TRUTHFUL,
            ),
            LedgerEntry(
                intel_id="intel_new",
                chapter=2,
                true_content="new truth",
                told_embercrown="distorted text",
                action_embercrown=IntelAction.DISTORTED,
            ),
        ]
        result = detect_contradictions(gs, "intel_new")
        assert "intel_old" in result

    def test_both_fabricated_no_contradiction(self):
        """Two FABRICATED entries to the same faction do not contradict each other."""
        gs = GameState()
        gs.ledger_entries = [
            LedgerEntry(
                intel_id="fab_a",
                chapter=1,
                true_content="truth a",
                told_ironveil="lie a",
                action_ironveil=IntelAction.FABRICATED,
            ),
            LedgerEntry(
                intel_id="fab_b",
                chapter=1,
                true_content="truth b",
                told_ironveil="lie b",
                action_ironveil=IntelAction.FABRICATED,
            ),
        ]
        result = detect_contradictions(gs, "fab_b")
        assert result == []

    def test_withheld_vs_truthful_no_contradiction(self):
        """WITHHELD and TRUTHFUL to the same faction should not be a contradiction."""
        gs = GameState()
        gs.ledger_entries = [
            LedgerEntry(
                intel_id="early",
                chapter=1,
                true_content="truth",
                told_ironveil="truth",
                action_ironveil=IntelAction.TRUTHFUL,
            ),
            LedgerEntry(
                intel_id="later",
                chapter=2,
                true_content="other",
                told_ironveil="other",
                action_ironveil=IntelAction.WITHHELD,
            ),
        ]
        result = detect_contradictions(gs, "later")
        assert result == []

    def test_cross_faction_contradiction_independent_per_faction(self):
        """Contradiction is detected per-faction independently; giving different stories
        to DIFFERENT factions is by design (not flagged), but telling one faction two
        conflicting things IS flagged."""
        gs = GameState()
        gs.ledger_entries = [
            # told IRONVEIL the truth about intel_a
            LedgerEntry(
                intel_id="intel_a",
                chapter=1,
                true_content="truth a",
                told_ironveil="truth a",
                action_ironveil=IntelAction.TRUTHFUL,
                told_embercrown=None,
                action_embercrown=None,
            ),
            # told IRONVEIL a fabrication about intel_b (contradicts intel_a for ironveil)
            LedgerEntry(
                intel_id="intel_b",
                chapter=2,
                true_content="truth b",
                told_ironveil="fabricated b",
                action_ironveil=IntelAction.FABRICATED,
                # told EMBERCROWN the truth — no contradiction there
                told_embercrown="truth b",
                action_embercrown=IntelAction.TRUTHFUL,
            ),
        ]
        result = detect_contradictions(gs, "intel_b")
        # ironveil faction: TRUTHFUL vs FABRICATED => contradiction
        assert "intel_a" in result


# ===========================================================================
# 2. _cap_memories — pathological inputs
# ===========================================================================


class TestCapMemoriesAdversarial:

    def test_100_memories_same_importance_pruned_to_cap(self):
        """100 memories of the same importance for one character must be pruned
        to MAX_MEMORIES_PER_CHARACTER, keeping the most recent (highest chapter)."""
        ev = _evaluator()
        gs = GameState()
        gs.npc_memories = [
            _memory(name="Berserk", importance=3, chapter=ch)
            for ch in range(1, 101)
        ]
        ev._cap_memories(gs)
        assert len(gs.npc_memories) == MAX_MEMORIES_PER_CHARACTER
        # All same importance → sorted by chapter desc → keeps highest chapters
        kept_chapters = {m.chapter for m in gs.npc_memories}
        assert max(kept_chapters) == 100

    def test_same_importance_keeps_most_recent_chapters(self):
        """With all memories at the same importance, the most recent chapters survive."""
        ev = _evaluator()
        gs = GameState()
        cap = MAX_MEMORIES_PER_CHARACTER
        total = cap + 3
        gs.npc_memories = [
            _memory(name="Same", importance=2, chapter=ch)
            for ch in range(1, total + 1)
        ]
        ev._cap_memories(gs)
        kept_chapters = sorted(m.chapter for m in gs.npc_memories)
        # Should keep the 'cap' highest chapter numbers
        expected = list(range(total - cap + 1, total + 1))
        assert kept_chapters == expected

    def test_empty_character_name_memories_are_capped_normally(self):
        """Memories with an empty string character_name should be grouped and capped
        without raising an exception."""
        ev = _evaluator()
        gs = GameState()
        cap = MAX_MEMORIES_PER_CHARACTER
        # 8 memories for the empty-string character name
        gs.npc_memories = [
            _memory(name="", importance=3, chapter=ch)
            for ch in range(1, 9)
        ]
        ev._cap_memories(gs)
        assert len(gs.npc_memories) == cap

    def test_mixed_characters_each_individually_capped(self):
        """Each character's memories are pruned independently; one bloated character
        does not evict another character's memories."""
        ev = _evaluator()
        gs = GameState()
        cap = MAX_MEMORIES_PER_CHARACTER
        # 100 memories for "Bloat", 3 for "Lean"
        gs.npc_memories = (
            [_memory(name="Bloat", importance=3, chapter=ch) for ch in range(1, 101)]
            + [_memory(name="Lean", importance=5, chapter=ch) for ch in range(1, 4)]
        )
        ev._cap_memories(gs)
        bloat_mems = [m for m in gs.npc_memories if m.character_name == "Bloat"]
        lean_mems = [m for m in gs.npc_memories if m.character_name == "Lean"]
        assert len(bloat_mems) == cap
        assert len(lean_mems) == 3   # under cap — all preserved

    def test_importance_tie_broken_by_chapter_descending(self):
        """When two memories have equal importance, higher chapter wins."""
        ev = _evaluator()
        gs = GameState()
        cap = MAX_MEMORIES_PER_CHARACTER
        # cap+1 memories all at importance=5, chapters 1..cap+1
        gs.npc_memories = [
            _memory(name="Tie", importance=5, chapter=ch)
            for ch in range(1, cap + 2)
        ]
        ev._cap_memories(gs)
        kept_chapters = {m.chapter for m in gs.npc_memories}
        # Chapter 1 (the oldest) should be dropped
        assert 1 not in kept_chapters
        assert cap + 1 in kept_chapters

    def test_zero_memories_no_crash(self):
        """Empty npc_memories list must not raise."""
        ev = _evaluator()
        gs = GameState()
        gs.npc_memories = []
        ev._cap_memories(gs)
        assert gs.npc_memories == []


# ===========================================================================
# 3. process_chapter_consequences — stress tests
# ===========================================================================


class TestProcessChapterConsequencesAdversarial:

    def _base_world_with_ledger(self, intel_id="ch1_m_1", significance=3):
        """Helper: world + game_state with a matching ledger entry."""
        piece = _intel(id=intel_id, significance=significance)
        world = _world(intel=[piece])
        gs = initialize_game_state(world)
        gs.ledger_entries.append(
            LedgerEntry(intel_id=intel_id, chapter=1, true_content="truth")
        )
        return world, gs

    def test_no_report_actions_returns_empty_narratives(self):
        """Empty report_actions list should produce no narrative output
        (unless wild cards are present)."""
        world, gs = self._base_world_with_ledger()
        narratives = process_chapter_consequences(gs, world, [], {})
        # No wild cards in base world, so result should be empty
        assert narratives == []

    def test_all_actions_withheld_applies_penalty_narratives(self):
        """Withheld intel should still produce trust-penalty narratives."""
        piece = _intel(id="ch1_m_w", significance=3, war_tension_effect={})
        world = _world(intel=[piece])
        gs = initialize_game_state(world)
        gs.ledger_entries.append(
            LedgerEntry(intel_id="ch1_m_w", chapter=1, true_content="truth")
        )
        ra = ReportAction(intel_id="ch1_m_w", action=IntelAction.WITHHELD)
        narratives = process_chapter_consequences(gs, world, [ra], {})
        # WITHHELD consequence: "No report on this matter — mild concern"
        assert any("No report" in n or "mild concern" in n or n for n in narratives)

    def test_missing_intel_id_silently_skipped(self):
        """A ReportAction referencing a non-existent intel ID must not crash."""
        world = _world()
        gs = initialize_game_state(world)
        ra = ReportAction(intel_id="does_not_exist_id", action=IntelAction.TRUTHFUL)
        # Should complete without raising, returning an empty or partial list
        narratives = process_chapter_consequences(gs, world, [ra], {})
        assert isinstance(narratives, list)

    def test_multiple_missing_intel_ids_no_crash(self):
        """Multiple phantom intel IDs in report_actions must all be skipped."""
        world = _world()
        gs = initialize_game_state(world)
        actions = [
            ReportAction(intel_id=f"ghost_{i}", action=IntelAction.TRUTHFUL)
            for i in range(10)
        ]
        narratives = process_chapter_consequences(gs, world, actions, {})
        assert isinstance(narratives, list)

    def test_wild_card_events_only_current_chapter(self):
        """Wild card events for other chapters are not processed."""
        wc_now = WildCardEvent(chapter=1, description="Now event", war_tension_effect=5)
        wc_later = WildCardEvent(chapter=3, description="Future event", war_tension_effect=10)
        world = _world(wildcards=[wc_now, wc_later])
        gs = initialize_game_state(world)
        old_tension = gs.war_tension

        narratives = process_chapter_consequences(gs, world, [], {})

        # Only chapter 1 wild card should fire (+5 tension)
        assert gs.war_tension == old_tension + 5
        assert any("Now event" in n for n in narratives)
        assert not any("Future event" in n for n in narratives)

    def test_verification_results_applied_when_present(self):
        """Passing a verification result should update ledger entry fields."""
        piece = _intel(id="ch1_m_vr", significance=2, war_tension_effect={})
        world = _world(intel=[piece])
        gs = initialize_game_state(world)
        gs.ledger_entries.append(
            LedgerEntry(intel_id="ch1_m_vr", chapter=1, true_content="truth")
        )
        ra = ReportAction(intel_id="ch1_m_vr", action=IntelAction.TRUTHFUL)
        # was_checked=True, check_passed=True
        process_chapter_consequences(gs, world, [ra], {"ch1_m_vr": (True, True)})

        entry = next(e for e in gs.ledger_entries if e.intel_id == "ch1_m_vr")
        # scene_b is EMBERCROWN (scene_a_faction defaults to IRONVEIL)
        assert entry.verified_embercrown is True
        assert entry.verification_result_embercrown is True

    def test_ledger_entry_contradiction_field_updated(self):
        """After processing, contradiction_with should be populated when
        a contradiction exists."""
        world = _world(intel=[
            _intel(id="ch1_m_first", significance=2),
            _intel(id="ch1_m_second", significance=2),
        ])
        gs = initialize_game_state(world)
        gs.ledger_entries = [
            LedgerEntry(
                intel_id="ch1_m_first",
                chapter=1,
                true_content="truth first",
                told_embercrown="truth first",
                action_embercrown=IntelAction.TRUTHFUL,
            ),
            LedgerEntry(
                intel_id="ch1_m_second",
                chapter=1,
                true_content="truth second",
            ),
        ]
        ra = ReportAction(intel_id="ch1_m_second", action=IntelAction.FABRICATED)
        process_chapter_consequences(gs, world, [ra], {})

        second_entry = next(e for e in gs.ledger_entries if e.intel_id == "ch1_m_second")
        assert "ch1_m_first" in second_entry.contradiction_with


# ===========================================================================
# 4. evaluate_death_conditions — edge cases
# ===========================================================================


class TestEvaluateDeathConditionsAdversarial:

    def _make_death_world_and_state(
        self,
        char_name="Doomed",
        char_faction=Faction.IRONVEIL,
        death_conditions="Caught spying",
        intel_id="ch1_m_kill",
        intel_faction=Faction.IRONVEIL,
        significance=4,
        related=None,
    ):
        related = related if related is not None else [char_name]
        char = _char(
            name=char_name,
            faction=char_faction,
            death_conditions=death_conditions,
        )
        piece = _intel(
            id=intel_id,
            faction=intel_faction,
            significance=significance,
            related_characters=related,
        )
        world = _world(chars=[char], intel=[piece])
        gs = initialize_game_state(world)
        return world, gs

    def test_dead_character_does_not_die_again(self):
        """A character already marked dead should not appear in death narratives."""
        world, gs = self._make_death_world_and_state()
        gs.character_alive["Doomed"] = False  # already dead

        ra = ReportAction(intel_id="ch1_m_kill", action=IntelAction.TRUTHFUL)
        narratives = evaluate_death_conditions(gs, world, [ra])

        # No death narrative for already-dead character
        assert not any("Doomed" in n for n in narratives)

    def test_character_without_death_conditions_survives_high_significance(self):
        """Characters with empty death_conditions must not die even when high-sig
        intel about them is reported truthfully."""
        char = _char(name="Safe", faction=Faction.IRONVEIL, death_conditions="")
        piece = _intel(
            id="ch1_m_safe",
            faction=Faction.IRONVEIL,
            significance=5,
            related_characters=["Safe"],
        )
        world = _world(chars=[char], intel=[piece])
        gs = initialize_game_state(world)

        ra = ReportAction(intel_id="ch1_m_safe", action=IntelAction.TRUTHFUL)
        narratives = evaluate_death_conditions(gs, world, [ra])

        assert not any("Safe" in n for n in narratives)
        assert gs.character_alive.get("Safe", True) is True

    def test_significance_exactly_4_triggers_death(self):
        """significance=4 is AT the threshold (>= 4); character should die."""
        world, gs = self._make_death_world_and_state(significance=4)

        ra = ReportAction(intel_id="ch1_m_kill", action=IntelAction.TRUTHFUL)
        narratives = evaluate_death_conditions(gs, world, [ra])

        assert any("Doomed" in n for n in narratives)
        assert gs.character_alive.get("Doomed") is False

    def test_significance_3_does_not_trigger_death(self):
        """significance=3 is BELOW the threshold (< 4); character must survive."""
        world, gs = self._make_death_world_and_state(significance=3)

        ra = ReportAction(intel_id="ch1_m_kill", action=IntelAction.TRUTHFUL)
        narratives = evaluate_death_conditions(gs, world, [ra])

        assert not any("Doomed" in n for n in narratives)
        assert gs.character_alive.get("Doomed") is True

    def test_non_truthful_action_does_not_kill(self):
        """Only TRUTHFUL actions can trigger death conditions; FABRICATED must not."""
        world, gs = self._make_death_world_and_state(significance=5)

        ra = ReportAction(intel_id="ch1_m_kill", action=IntelAction.FABRICATED)
        narratives = evaluate_death_conditions(gs, world, [ra])

        assert gs.character_alive.get("Doomed") is True
        assert not any("Doomed" in n for n in narratives)

    def test_character_not_in_related_characters_survives(self):
        """A character with death_conditions but not in related_characters is safe."""
        world, gs = self._make_death_world_and_state(
            related=["SomeoneElse"]  # "Doomed" not listed
        )

        ra = ReportAction(intel_id="ch1_m_kill", action=IntelAction.TRUTHFUL)
        narratives = evaluate_death_conditions(gs, world, [ra])

        assert gs.character_alive.get("Doomed") is True

    def test_wrong_faction_intel_does_not_kill(self):
        """Intel from EMBERCROWN cannot kill an IRONVEIL character via their
        own death condition trigger (the check is source_faction == char.faction)."""
        char = _char(name="IVChar", faction=Faction.IRONVEIL, death_conditions="Exposed")
        piece = _intel(
            id="ch1_m_ec",
            faction=Faction.EMBERCROWN,   # source is EMBERCROWN
            significance=5,
            related_characters=["IVChar"],
        )
        world = _world(chars=[char], intel=[piece])
        gs = initialize_game_state(world)

        ra = ReportAction(intel_id="ch1_m_ec", action=IntelAction.TRUTHFUL)
        narratives = evaluate_death_conditions(gs, world, [ra])

        # char.faction (IRONVEIL) != intel.source_faction (EMBERCROWN) → no death
        assert gs.character_alive.get("IVChar") is True

    def test_missing_intel_id_in_report_action_no_crash(self):
        """A ReportAction with an intel_id not in world.intelligence_pipeline
        must not crash evaluate_death_conditions."""
        world = _world()
        gs = initialize_game_state(world)

        ra = ReportAction(intel_id="phantom_intel", action=IntelAction.TRUTHFUL)
        narratives = evaluate_death_conditions(gs, world, [ra])

        assert isinstance(narratives, list)

    def test_empty_report_actions_returns_empty(self):
        """No report actions → no death narratives."""
        world, gs = self._make_death_world_and_state(significance=5)
        narratives = evaluate_death_conditions(gs, world, [])
        assert narratives == []

    def test_character_dies_at_most_once_with_multiple_qualifying_intel(self):
        """If two qualifying intel pieces both reference the same character,
        the character should die exactly once (apply_character_death is idempotent)."""
        char = _char(name="DoubleTarget", faction=Faction.IRONVEIL, death_conditions="Exposed")
        piece1 = _intel(
            id="ch1_m_k1",
            faction=Faction.IRONVEIL,
            significance=4,
            related_characters=["DoubleTarget"],
        )
        piece2 = _intel(
            id="ch1_m_k2",
            faction=Faction.IRONVEIL,
            significance=5,
            related_characters=["DoubleTarget"],
        )
        world = _world(chars=[char], intel=[piece1, piece2])
        gs = initialize_game_state(world)

        actions = [
            ReportAction(intel_id="ch1_m_k1", action=IntelAction.TRUTHFUL),
            ReportAction(intel_id="ch1_m_k2", action=IntelAction.TRUTHFUL),
        ]
        narratives = evaluate_death_conditions(gs, world, actions)

        # "DoubleTarget has been killed." should appear at most once
        kill_mentions = [n for n in narratives if "DoubleTarget has been killed" in n]
        assert len(kill_mentions) == 1


# ===========================================================================
# 5. determine_war_victor — adversarial tests
# ===========================================================================


class TestDetermineWarVictorAdversarial:

    def test_world_none_fallback_weight_1(self):
        """With world=None, each entry has weight 1. Victor is still determined."""
        gs = GameState(
            war_started=True,
            ledger_entries=[
                LedgerEntry(
                    intel_id="a",
                    chapter=1,
                    true_content="x",
                    action_ironveil=IntelAction.TRUTHFUL,
                    action_embercrown=IntelAction.WITHHELD,
                ),
                LedgerEntry(
                    intel_id="b",
                    chapter=1,
                    true_content="y",
                    action_ironveil=IntelAction.TRUTHFUL,
                    action_embercrown=IntelAction.WITHHELD,
                ),
            ],
        )
        result = determine_war_victor(gs, world=None)
        assert result == Faction.IRONVEIL.value

    def test_empty_ledger_war_started_returns_none(self):
        """No ledger entries → both advantages are 0 → mutual destruction (None)."""
        gs = GameState(war_started=True, ledger_entries=[])
        assert determine_war_victor(gs) is None

    def test_entries_with_none_actions_do_not_crash(self):
        """Entries where action_ironveil or action_embercrown is None should not raise."""
        gs = GameState(
            war_started=True,
            ledger_entries=[
                LedgerEntry(
                    intel_id="null_action",
                    chapter=1,
                    true_content="x",
                    action_ironveil=None,
                    action_embercrown=None,
                ),
            ],
        )
        result = determine_war_victor(gs)
        # Neither side gets advantage → None (mutual destruction / tie)
        assert result is None

    def test_none_actions_not_counted_as_truthful(self):
        """A None action must never be interpreted as TRUTHFUL or otherwise
        award advantage to either side."""
        gs = GameState(
            war_started=True,
            ledger_entries=[
                LedgerEntry(
                    intel_id="a",
                    chapter=1,
                    true_content="x",
                    action_ironveil=None,         # should give ironveil 0 advantage
                    action_embercrown=IntelAction.TRUTHFUL,  # embercrown +weight
                ),
            ],
        )
        result = determine_war_victor(gs)
        assert result == Faction.EMBERCROWN.value

    def test_significance_weighting_applied_correctly(self):
        """Higher-significance intel should give a proportionally larger advantage.
        One high-sig truthful should outweigh two low-sig truthfuls for the opponent."""
        high_sig = _intel(id="big", significance=5)
        low_sig_1 = _intel(id="small1", significance=2)
        low_sig_2 = _intel(id="small2", significance=2)
        world = _world(intel=[high_sig, low_sig_1, low_sig_2])

        gs = GameState(
            war_started=True,
            ledger_entries=[
                # IRONVEIL gets one sig=5 truthful
                LedgerEntry(
                    intel_id="big",
                    chapter=1,
                    true_content="x",
                    action_ironveil=IntelAction.TRUTHFUL,
                    action_embercrown=None,
                ),
                # EMBERCROWN gets two sig=2 truthfuls (total 4)
                LedgerEntry(
                    intel_id="small1",
                    chapter=1,
                    true_content="y",
                    action_ironveil=None,
                    action_embercrown=IntelAction.TRUTHFUL,
                ),
                LedgerEntry(
                    intel_id="small2",
                    chapter=1,
                    true_content="z",
                    action_ironveil=None,
                    action_embercrown=IntelAction.TRUTHFUL,
                ),
            ],
        )
        result = determine_war_victor(gs, world=world)
        # Ironveil: 5, Embercrown: 2+2=4 → Ironveil wins
        assert result == Faction.IRONVEIL.value

    def test_fabricated_reduces_advantage(self):
        """A faction that fabricates intel should have that weight subtracted
        from their advantage."""
        piece = _intel(id="fab_intel", significance=3)
        world = _world(intel=[piece])

        gs = GameState(
            war_started=True,
            ledger_entries=[
                LedgerEntry(
                    intel_id="fab_intel",
                    chapter=1,
                    true_content="x",
                    action_ironveil=IntelAction.FABRICATED,  # ironveil -3
                    action_embercrown=IntelAction.TRUTHFUL,   # embercrown +3
                ),
            ],
        )
        result = determine_war_victor(gs, world=world)
        assert result == Faction.EMBERCROWN.value

    def test_war_not_started_always_none(self):
        """war_started=False must short-circuit regardless of ledger contents."""
        gs = GameState(
            war_started=False,
            ledger_entries=[
                LedgerEntry(
                    intel_id="x",
                    chapter=1,
                    true_content="x",
                    action_ironveil=IntelAction.TRUTHFUL,
                    action_embercrown=IntelAction.WITHHELD,
                ),
            ],
        )
        assert determine_war_victor(gs, world=None) is None


# ===========================================================================
# 6. get_scene_type — probability distribution and boundary values
# ===========================================================================


class TestGetSceneTypeAdversarial:

    def _gs(self, suspicion: int, chapter: int = 1, faction: Faction = Faction.IRONVEIL) -> GameState:
        kw = {
            "chapter": chapter,
            "ironveil_suspicion": suspicion if faction == Faction.IRONVEIL else 0,
            "embercrown_suspicion": suspicion if faction == Faction.EMBERCROWN else 0,
        }
        return GameState(**kw)

    # --- Boundary tests ---

    def test_suspicion_70_is_exclusion_returns_private_meeting(self):
        """Suspicion=70 is the top of the 'exclusion' range (51-70).
        check_suspicion_threshold returns 'exclusion' → PRIVATE_MEETING."""
        world = _world()
        gs = self._gs(suspicion=70)
        result = get_scene_type(gs, world, Faction.IRONVEIL)
        assert result == SceneType.PRIVATE_MEETING

    def test_suspicion_71_is_confrontation_stochastic(self):
        """Suspicion=71 is the bottom of 'confrontation' (71-80).
        With RNG always < 0.60, result is INTERROGATION."""
        world = _world()
        gs = self._gs(suspicion=71)
        rng = random.Random(0)
        # Seed 0 gives first value ≈ 0.844 which is NOT < 0.60
        # Find a seed where first value < 0.60
        for seed in range(100):
            rng = random.Random(seed)
            val = rng.random()
            if val < 0.60:
                rng = random.Random(seed)
                result = get_scene_type(gs, world, Faction.IRONVEIL, rng=rng)
                assert result == SceneType.INTERROGATION
                break

    def test_suspicion_71_confrontation_fallthrough_to_normal(self):
        """Suspicion=71, with RNG >= 0.60, falls through to normal rotation."""
        world = _world()
        gs = self._gs(suspicion=71, chapter=1)
        # Find a seed where first random() >= 0.60
        for seed in range(100):
            rng_probe = random.Random(seed)
            if rng_probe.random() >= 0.60:
                rng = random.Random(seed)
                result = get_scene_type(gs, world, Faction.IRONVEIL, rng=rng)
                # Chapter 1 normal: WAR_COUNCIL
                assert result == SceneType.WAR_COUNCIL
                break

    def test_suspicion_80_is_confrontation_not_investigation(self):
        """Suspicion=80 is still 'confrontation' (71-80), not 'investigation'."""
        world = _world()
        gs = self._gs(suspicion=80)
        # Use a seed that forces the confrontation path (rng < 0.60 → INTERROGATION)
        for seed in range(100):
            rng_probe = random.Random(seed)
            if rng_probe.random() < 0.60:
                rng = random.Random(seed)
                result = get_scene_type(gs, world, Faction.IRONVEIL, rng=rng)
                assert result == SceneType.INTERROGATION
                break

    def test_suspicion_81_is_investigation_returns_interrogation(self):
        """Suspicion=81 enters 'investigation' (81+). With rng < 0.80 → INTERROGATION."""
        world = _world()
        gs = self._gs(suspicion=81)
        for seed in range(100):
            rng_probe = random.Random(seed)
            if rng_probe.random() < 0.80:
                rng = random.Random(seed)
                result = get_scene_type(gs, world, Faction.IRONVEIL, rng=rng)
                assert result == SceneType.INTERROGATION
                break

    def test_suspicion_81_investigation_minority_private_meeting(self):
        """Suspicion=81, with rng >= 0.80, returns PRIVATE_MEETING (20% branch)."""
        world = _world()
        gs = self._gs(suspicion=81)
        for seed in range(1000):
            rng_probe = random.Random(seed)
            if rng_probe.random() >= 0.80:
                rng = random.Random(seed)
                result = get_scene_type(gs, world, Faction.IRONVEIL, rng=rng)
                assert result == SceneType.PRIVATE_MEETING
                break
        else:
            pytest.skip("Could not find a seed yielding rng >= 0.80 in 1000 tries")

    def test_normal_rotation_wraps_with_modulo(self):
        """Chapter 6 wraps around: (6-1)%5 = 0 → WAR_COUNCIL (same as chapter 1)."""
        world = _world()
        gs = self._gs(suspicion=0, chapter=6)
        result = get_scene_type(gs, world, Faction.IRONVEIL)
        assert result == SceneType.WAR_COUNCIL

    def test_statistical_investigation_distribution(self):
        """Over 1000 trials at suspicion=85, ~80% should be INTERROGATION, ~20% PRIVATE."""
        world = _world()
        gs = self._gs(suspicion=85)
        counts = {SceneType.INTERROGATION: 0, SceneType.PRIVATE_MEETING: 0}
        rng = random.Random(42)
        trials = 1000
        for _ in range(trials):
            result = get_scene_type(gs, world, Faction.IRONVEIL, rng=rng)
            counts[result] = counts.get(result, 0) + 1
        ratio = counts[SceneType.INTERROGATION] / trials
        # Allow 5% tolerance around expected 0.80
        assert 0.75 <= ratio <= 0.85, f"Expected ~0.80, got {ratio:.3f}"

    def test_suspicion_50_is_exclusion_boundary(self):
        """Suspicion=50 is within scrutiny (31-50) range, NOT exclusion (51+).
        Should fall through to normal rotation."""
        world = _world()
        gs = self._gs(suspicion=50, chapter=1)
        result = get_scene_type(gs, world, Faction.IRONVEIL)
        # Normal rotation, chapter 1 → WAR_COUNCIL
        assert result == SceneType.WAR_COUNCIL

    def test_suspicion_51_is_exclusion_returns_private_meeting(self):
        """Suspicion=51 is the first value in exclusion range (51-70)."""
        world = _world()
        gs = self._gs(suspicion=51)
        result = get_scene_type(gs, world, Faction.IRONVEIL)
        assert result == SceneType.PRIVATE_MEETING


# ===========================================================================
# 7. Save/load roundtrip — new model fields serialization
# ===========================================================================


class TestSaveLoadRoundtrip:

    def _make_full_world(self):
        chars = [
            _char("Aria", Faction.IRONVEIL),
            _char("Boris", Faction.EMBERCROWN),
        ]
        pieces = [_intel("ch1_m_1", Faction.IRONVEIL)]
        return _world(chars=chars, intel=pieces)

    def test_roundtrip_npc_memories(self, tmp_path, monkeypatch):
        """npc_memories should serialize and deserialize correctly."""
        monkeypatch.setattr("saves.DATA_DIR", tmp_path)
        world = self._make_full_world()
        gs = GameState(
            chapter=2,
            npc_memories=[
                NPCMemory(
                    character_name="Aria",
                    chapter=2,
                    memory_text="The envoy was suspicious",
                    emotional_tag="suspicious",
                    importance=4,
                ),
                NPCMemory(
                    character_name="Boris",
                    chapter=2,
                    memory_text="Seemed trustworthy",
                    emotional_tag="trusting",
                    importance=2,
                ),
            ],
        )
        save_game(world, gs, slot=1)
        loaded = load_game(slot=1)
        assert loaded is not None
        assert len(loaded.game_state.npc_memories) == 2
        aria_mem = next(m for m in loaded.game_state.npc_memories if m.character_name == "Aria")
        assert aria_mem.memory_text == "The envoy was suspicious"
        assert aria_mem.importance == 4

    def test_roundtrip_scene_analyses(self, tmp_path, monkeypatch):
        """scene_analyses should serialize and deserialize correctly."""
        monkeypatch.setattr("saves.DATA_DIR", tmp_path)
        world = self._make_full_world()
        analysis = SceneAnalysis(
            chapter=1,
            phase=ChapterPhase.SCENE_A,
            faction=Faction.IRONVEIL,
            conversation_quality="good",
            faction_trust_delta=2,
            faction_suspicion_delta=-1,
        )
        gs = GameState(chapter=1, scene_analyses=[analysis])
        save_game(world, gs, slot=2)
        loaded = load_game(slot=2)
        assert loaded is not None
        assert len(loaded.game_state.scene_analyses) == 1
        loaded_analysis = loaded.game_state.scene_analyses[0]
        assert loaded_analysis.conversation_quality == "good"
        assert loaded_analysis.faction_trust_delta == 2
        assert loaded_analysis.faction == Faction.IRONVEIL

    def test_roundtrip_player_promises(self, tmp_path, monkeypatch):
        """player_promises (list of dicts) should round-trip correctly."""
        monkeypatch.setattr("saves.DATA_DIR", tmp_path)
        world = self._make_full_world()
        gs = GameState(
            chapter=3,
            player_promises=[
                {"promise": "Bring news of troop movements", "faction": "ironveil", "chapter": 1, "fulfilled": False},
                {"promise": "Deliver the cipher", "faction": "embercrown", "chapter": 2, "fulfilled": True},
            ],
        )
        save_game(world, gs, slot=3)
        loaded = load_game(slot=3)
        assert loaded is not None
        promises = loaded.game_state.player_promises
        assert len(promises) == 2
        assert promises[0]["promise"] == "Bring news of troop movements"
        assert promises[0]["fulfilled"] is False
        assert promises[1]["fulfilled"] is True

    def test_roundtrip_promises_fulfilled_field(self, tmp_path, monkeypatch):
        """promises_fulfilled field inside SceneAnalysis should survive roundtrip."""
        monkeypatch.setattr("saves.DATA_DIR", tmp_path)
        world = self._make_full_world()
        analysis = SceneAnalysis(
            chapter=2,
            phase=ChapterPhase.SCENE_B,
            faction=Faction.EMBERCROWN,
            promises_made=["Deliver cipher next visit"],
            promises_fulfilled=["I delivered the cipher as promised"],
        )
        gs = GameState(chapter=2, scene_analyses=[analysis])
        save_game(world, gs, slot=1)
        loaded = load_game(slot=1)
        assert loaded is not None
        la = loaded.game_state.scene_analyses[0]
        assert la.promises_made == ["Deliver cipher next visit"]
        assert la.promises_fulfilled == ["I delivered the cipher as promised"]

    def test_roundtrip_populated_ledger_and_memories_together(self, tmp_path, monkeypatch):
        """A fully-populated GameState survives a save/load cycle."""
        monkeypatch.setattr("saves.DATA_DIR", tmp_path)
        world = self._make_full_world()
        gs = GameState(
            chapter=4,
            war_tension=70,
            war_started=True,
            ironveil_trust=60,
            ironveil_suspicion=35,
            embercrown_trust=45,
            embercrown_suspicion=55,
            character_trust={"Aria": 65, "Boris": 40},
            character_suspicion={"Aria": 20, "Boris": 60},
            character_alive={"Aria": True, "Boris": False},
            ledger_entries=[
                LedgerEntry(
                    intel_id="ch1_m_1",
                    chapter=1,
                    true_content="troops massing",
                    told_ironveil="troops massing",
                    action_ironveil=IntelAction.TRUTHFUL,
                    told_embercrown="inflated troop count",
                    action_embercrown=IntelAction.DISTORTED,
                    consequence="Trust boosted",
                    contradiction_with=[],
                ),
            ],
            npc_memories=[
                NPCMemory(
                    character_name="Aria",
                    chapter=3,
                    memory_text="Player seemed nervous",
                    emotional_tag="suspicious",
                    importance=5,
                ),
            ],
            player_promises=[
                {"promise": "I will return with intel", "faction": "ironveil", "chapter": 2, "fulfilled": False},
            ],
        )
        save_game(world, gs, slot=1)
        loaded = load_game(slot=1)
        assert loaded is not None
        lgs = loaded.game_state
        assert lgs.war_started is True
        assert lgs.character_alive["Boris"] is False
        assert lgs.ledger_entries[0].action_ironveil == IntelAction.TRUTHFUL
        assert lgs.ledger_entries[0].action_embercrown == IntelAction.DISTORTED
        assert lgs.npc_memories[0].importance == 5
        assert lgs.player_promises[0]["fulfilled"] is False


# ===========================================================================
# 8. Promise fulfillment matching — edge cases
# ===========================================================================


class TestPromiseFulfillmentAdversarial:

    def _analysis(self, faction=Faction.IRONVEIL, promises_made=None, promises_fulfilled=None) -> SceneAnalysis:
        return SceneAnalysis(
            chapter=1,
            phase=ChapterPhase.SCENE_A,
            faction=faction,
            promises_made=promises_made or [],
            promises_fulfilled=promises_fulfilled or [],
        )

    def test_empty_fulfillment_text_does_not_match(self):
        """An empty fulfilled string must NOT match any promise (guarded)."""
        ev = _evaluator()
        gs = GameState()
        # First store a promise
        make_analysis = self._analysis(promises_made=["Deliver the cipher"])
        ev.apply_analysis(make_analysis, gs)
        assert gs.player_promises[0]["fulfilled"] is False

        # Now try to fulfill with an empty string
        fulfill_analysis = self._analysis(promises_fulfilled=[""])
        ev.apply_analysis(fulfill_analysis, gs)

        # Empty string is guarded — promise stays unfulfilled
        assert gs.player_promises[0]["fulfilled"] is False

    def test_already_fulfilled_promise_not_matched_again(self):
        """A promise marked fulfilled=True must be skipped in matching."""
        ev = _evaluator()
        gs = GameState()
        # Pre-load a fulfilled promise
        gs.player_promises = [
            {"promise": "deliver intel", "faction": "ironveil", "chapter": 1, "fulfilled": True}
        ]
        # Second promise that is unfulfilled
        gs.player_promises.append(
            {"promise": "report back tomorrow", "faction": "ironveil", "chapter": 1, "fulfilled": False}
        )
        analysis = self._analysis(promises_fulfilled=["deliver intel"])
        ev.apply_analysis(analysis, gs)

        # The already-fulfilled one stays True (not a problem), but the second
        # one should NOT be inadvertently marked fulfilled
        assert gs.player_promises[1]["fulfilled"] is False

    def test_cross_faction_fulfillment_does_not_match(self):
        """A fulfillment text in an EMBERCROWN scene should not mark
        an IRONVEIL faction promise as fulfilled."""
        ev = _evaluator()
        gs = GameState()
        # Store an IRONVEIL promise
        make_analysis = self._analysis(
            faction=Faction.IRONVEIL,
            promises_made=["bring troop numbers"],
        )
        ev.apply_analysis(make_analysis, gs)
        assert gs.player_promises[0]["faction"] == "ironveil"
        assert gs.player_promises[0]["fulfilled"] is False

        # Try to fulfill it from an EMBERCROWN scene
        fulfill_analysis = self._analysis(
            faction=Faction.EMBERCROWN,
            promises_fulfilled=["bring troop numbers"],
        )
        ev.apply_analysis(fulfill_analysis, gs)

        # Cross-faction: faction check 'promise.get("faction") != faction.value'
        # ironveil promise vs embercrown scene → no match
        assert gs.player_promises[0]["fulfilled"] is False

    def test_partial_substring_match_fulfills(self):
        """If the stored promise text is a substring of the fulfillment text,
        it should be marked fulfilled."""
        ev = _evaluator()
        gs = GameState()
        make_analysis = self._analysis(promises_made=["deliver intel"])
        ev.apply_analysis(make_analysis, gs)

        # Fulfillment text contains the stored promise as substring
        fulfill_analysis = self._analysis(
            promises_fulfilled=["I have managed to deliver intel successfully"]
        )
        ev.apply_analysis(fulfill_analysis, gs)

        assert gs.player_promises[0]["fulfilled"] is True

    def test_case_insensitive_matching(self):
        """The matching is lowercase on both sides — 'DELIVER INTEL' should match
        'deliver intel'."""
        ev = _evaluator()
        gs = GameState()
        make_analysis = self._analysis(promises_made=["deliver intel"])
        ev.apply_analysis(make_analysis, gs)

        fulfill_analysis = self._analysis(promises_fulfilled=["DELIVER INTEL"])
        ev.apply_analysis(fulfill_analysis, gs)

        assert gs.player_promises[0]["fulfilled"] is True

    def test_no_promises_stored_fulfillment_no_crash(self):
        """Trying to fulfill promises when none are stored must not raise."""
        ev = _evaluator()
        gs = GameState()
        analysis = self._analysis(promises_fulfilled=["something"])
        ev.apply_analysis(analysis, gs)  # should not raise
        assert gs.player_promises == []

    def test_multiple_similar_promises_only_first_fulfilled(self):
        """When two identical promises exist, only the first is matched per
        fulfillment event (the loop breaks after the first match)."""
        ev = _evaluator()
        gs = GameState()
        gs.player_promises = [
            {"promise": "bring intel", "faction": "ironveil", "chapter": 1, "fulfilled": False},
            {"promise": "bring intel", "faction": "ironveil", "chapter": 2, "fulfilled": False},
        ]
        analysis = self._analysis(promises_fulfilled=["bring intel"])
        ev.apply_analysis(analysis, gs)

        # Only the first matching promise should be fulfilled
        assert gs.player_promises[0]["fulfilled"] is True
        assert gs.player_promises[1]["fulfilled"] is False

    def test_unrelated_fulfillment_text_no_match(self):
        """A fulfillment text with no overlap with any stored promise does not
        mark anything as fulfilled."""
        ev = _evaluator()
        gs = GameState()
        gs.player_promises = [
            {"promise": "deliver cipher", "faction": "ironveil", "chapter": 1, "fulfilled": False},
        ]
        analysis = self._analysis(promises_fulfilled=["completely unrelated statement"])
        ev.apply_analysis(analysis, gs)

        assert gs.player_promises[0]["fulfilled"] is False
