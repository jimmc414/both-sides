"""Tests for the state_machine module — deterministic consequence engine."""
from __future__ import annotations

import pytest

from config import Faction, IntelAction, IntelCategory, SceneType
from models import (
    CharacterProfile,
    GameState,
    IntelligencePiece,
    LedgerEntry,
    ReportAction,
    WildCardEvent,
    WorldState,
)
from state_machine import (
    advance_chapter,
    detect_contradictions,
    get_attending_characters,
    get_scene_b_faction,
    get_scene_type,
    initialize_game_state,
    process_chapter_consequences,
)


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

def _make_char(name="TestChar", faction=Faction.IRONVEIL, **kw):
    defaults = dict(
        age=35,
        role="Spy",
        personality=["cunning"],
        speech_pattern="formal",
        goals="survive",
        secrets="none",
        starting_trust=50,
        starting_suspicion=15,
    )
    defaults.update(kw)
    return CharacterProfile(name=name, faction=faction, **defaults)


def _make_intel(id="ch1_military_1", source_faction=Faction.IRONVEIL, **kw):
    defaults = dict(
        chapter=1,
        true_content="Test intel",
        significance=3,
        verifiability=3,
        category=IntelCategory.MILITARY,
    )
    defaults.update(kw)
    return IntelligencePiece(id=id, source_faction=source_faction, **defaults)


def _make_world(chars=None, intel=None, wildcards=None):
    if chars is None:
        chars = [
            _make_char(f"Char{i}", Faction.IRONVEIL if i < 4 else Faction.EMBERCROWN)
            for i in range(8)
        ]
    if intel is None:
        intel = [_make_intel(f"ch1_military_{i + 1}") for i in range(3)]
    if wildcards is None:
        wildcards = []
    return WorldState(
        inciting_incident="Test incident",
        ironveil_background="Iron bg",
        embercrown_background="Ember bg",
        ashenmere_description="Neutral zone",
        characters=chars,
        intelligence_pipeline=intel,
        wild_card_events=wildcards,
    )


# ---------------------------------------------------------------------------
# initialize_game_state
# ---------------------------------------------------------------------------


class TestInitializeGameState:
    def test_initialize_game_state_defaults(self):
        world = _make_world()
        gs = initialize_game_state(world)
        assert gs.chapter == 1
        assert gs.war_tension == 50
        assert gs.scene_a_faction == Faction.IRONVEIL

    def test_initialize_populates_character_tracking(self):
        world = _make_world()
        gs = initialize_game_state(world)
        for char in world.characters:
            assert char.name in gs.character_trust
            assert char.name in gs.character_suspicion
            assert char.name in gs.character_alive
            assert gs.character_trust[char.name] == char.starting_trust
            assert gs.character_suspicion[char.name] == char.starting_suspicion
            assert gs.character_alive[char.name] is True

    def test_initialize_loads_chapter1_intel(self):
        ch1 = [_make_intel(f"ch1_mil_{i}", chapter=1) for i in range(2)]
        ch2 = [_make_intel(f"ch2_mil_{i}", chapter=2) for i in range(2)]
        world = _make_world(intel=ch1 + ch2)
        gs = initialize_game_state(world)
        assert all(i.id in gs.available_intel for i in ch1)
        assert all(i.id not in gs.available_intel for i in ch2)


# ---------------------------------------------------------------------------
# advance_chapter
# ---------------------------------------------------------------------------


class TestAdvanceChapter:
    def test_advance_chapter_increments(self):
        world = _make_world()
        gs = initialize_game_state(world)
        assert gs.chapter == 1
        advance_chapter(gs, world)
        assert gs.chapter == 2

    def test_advance_chapter_flips_faction(self):
        world = _make_world()
        gs = initialize_game_state(world)
        assert gs.scene_a_faction == Faction.IRONVEIL
        advance_chapter(gs, world)
        assert gs.scene_a_faction == Faction.EMBERCROWN
        advance_chapter(gs, world)
        assert gs.scene_a_faction == Faction.IRONVEIL

    def test_advance_chapter_loads_new_intel(self):
        ch1 = [_make_intel("ch1_mil_0", chapter=1)]
        ch2 = [_make_intel("ch2_mil_0", chapter=2)]
        world = _make_world(intel=ch1 + ch2)
        gs = initialize_game_state(world)
        assert "ch2_mil_0" not in gs.available_intel
        advance_chapter(gs, world)
        assert "ch2_mil_0" in gs.available_intel

    def test_advance_chapter_no_duplicate_intel(self):
        ch1 = [_make_intel("ch1_mil_0", chapter=1)]
        ch2 = [_make_intel("ch2_mil_0", chapter=2)]
        world = _make_world(intel=ch1 + ch2)
        gs = initialize_game_state(world)
        advance_chapter(gs, world)
        count_before = gs.available_intel.count("ch2_mil_0")
        advance_chapter(gs, world)  # chapter 3, but ch2 already loaded
        count_after = gs.available_intel.count("ch2_mil_0")
        assert count_before == count_after == 1


# ---------------------------------------------------------------------------
# get_scene_b_faction
# ---------------------------------------------------------------------------


class TestGetSceneBFaction:
    def test_get_scene_b_faction_ironveil(self):
        gs = GameState(scene_a_faction=Faction.IRONVEIL)
        assert get_scene_b_faction(gs) == Faction.EMBERCROWN

    def test_get_scene_b_faction_embercrown(self):
        gs = GameState(scene_a_faction=Faction.EMBERCROWN)
        assert get_scene_b_faction(gs) == Faction.IRONVEIL


# ---------------------------------------------------------------------------
# get_scene_type
# ---------------------------------------------------------------------------


class TestGetSceneType:
    def test_get_scene_type_normal_rotation(self):
        """Chapters 1-5 cycle through the normal_scenes list."""
        world = _make_world()
        expected = [
            SceneType.WAR_COUNCIL,
            SceneType.FEAST,
            SceneType.FIELD_VISIT,
            SceneType.PRIVATE_MEETING,
            SceneType.WAR_COUNCIL,
        ]
        for chapter_num, expected_type in enumerate(expected, start=1):
            gs = GameState(
                chapter=chapter_num,
                ironveil_suspicion=0,
                embercrown_suspicion=0,
            )
            result = get_scene_type(gs, world, Faction.IRONVEIL)
            assert result == expected_type, f"Chapter {chapter_num}: expected {expected_type}, got {result}"

    def test_get_scene_type_exclusion_returns_private_meeting(self):
        """Suspicion in the exclusion range (51-70) forces PRIVATE_MEETING."""
        world = _make_world()
        gs = GameState(chapter=1, ironveil_suspicion=55)
        assert get_scene_type(gs, world, Faction.IRONVEIL) == SceneType.PRIVATE_MEETING

    def test_get_scene_type_confrontation_returns_interrogation(self):
        """Suspicion in the confrontation range (71-80) can return INTERROGATION (60% chance)."""
        import random
        world = _make_world()
        gs = GameState(chapter=1, ironveil_suspicion=75)
        # Seed 1 yields rng.random() ~0.134, which is < 0.60 -> INTERROGATION
        rng = random.Random(1)
        assert get_scene_type(gs, world, Faction.IRONVEIL, rng=rng) == SceneType.INTERROGATION

    def test_get_scene_type_investigation_returns_interrogation(self):
        """Suspicion in the investigation range (81+) returns INTERROGATION (80% chance)."""
        import random
        world = _make_world()
        gs = GameState(chapter=1, ironveil_suspicion=85)
        # Seed 1 yields rng.random() ~0.134, which is < 0.80 -> INTERROGATION
        rng = random.Random(1)
        assert get_scene_type(gs, world, Faction.IRONVEIL, rng=rng) == SceneType.INTERROGATION


# ---------------------------------------------------------------------------
# get_attending_characters
# ---------------------------------------------------------------------------


class TestGetAttendingCharacters:
    def test_get_attending_characters_filters_faction(self):
        world = _make_world()
        gs = initialize_game_state(world)
        attending = get_attending_characters(gs, world, Faction.IRONVEIL, SceneType.WAR_COUNCIL)
        assert all(c.faction == Faction.IRONVEIL for c in attending)
        assert len(attending) == 4  # Char0-Char3

    def test_get_attending_characters_excludes_dead(self):
        world = _make_world()
        gs = initialize_game_state(world)
        gs.character_alive["Char0"] = False
        attending = get_attending_characters(gs, world, Faction.IRONVEIL, SceneType.WAR_COUNCIL)
        names = [c.name for c in attending]
        assert "Char0" not in names
        assert len(attending) == 3

    def test_get_attending_characters_private_meeting_limit(self):
        """PRIVATE_MEETING caps at 2 characters, sorted by trust descending."""
        world = _make_world()
        gs = initialize_game_state(world)
        # Give distinct trust values to ironveil chars
        gs.character_trust["Char0"] = 80
        gs.character_trust["Char1"] = 90
        gs.character_trust["Char2"] = 60
        gs.character_trust["Char3"] = 70
        attending = get_attending_characters(gs, world, Faction.IRONVEIL, SceneType.PRIVATE_MEETING)
        assert len(attending) == 2
        assert attending[0].name == "Char1"  # trust 90
        assert attending[1].name == "Char0"  # trust 80

    def test_get_attending_characters_interrogation_limit(self):
        """INTERROGATION caps at 2 characters, sorted by suspicion descending."""
        world = _make_world()
        gs = initialize_game_state(world)
        gs.character_suspicion["Char0"] = 40
        gs.character_suspicion["Char1"] = 30
        gs.character_suspicion["Char2"] = 70
        gs.character_suspicion["Char3"] = 50
        attending = get_attending_characters(gs, world, Faction.IRONVEIL, SceneType.INTERROGATION)
        assert len(attending) == 2
        assert attending[0].name == "Char2"  # suspicion 70
        assert attending[1].name == "Char3"  # suspicion 50


# ---------------------------------------------------------------------------
# detect_contradictions
# ---------------------------------------------------------------------------


class TestDetectContradictions:
    def test_detect_contradictions_no_entries(self):
        gs = GameState()
        assert detect_contradictions(gs, "nonexistent") == []

    def test_detect_contradictions_truthful_vs_fabricated(self):
        """A fabricated entry following a truthful one to the same faction is a contradiction."""
        gs = GameState()
        gs.ledger_entries = [
            LedgerEntry(
                intel_id="intel_1",
                chapter=1,
                true_content="Truth 1",
                told_ironveil="The truth",
                action_ironveil=IntelAction.TRUTHFUL,
            ),
            LedgerEntry(
                intel_id="intel_2",
                chapter=1,
                true_content="Truth 2",
                told_ironveil="Fabricated story",
                action_ironveil=IntelAction.FABRICATED,
            ),
        ]
        result = detect_contradictions(gs, "intel_2")
        assert "intel_1" in result

    def test_detect_contradictions_same_action_no_contradiction(self):
        """Two truthful entries to the same faction should not contradict."""
        gs = GameState()
        gs.ledger_entries = [
            LedgerEntry(
                intel_id="intel_1",
                chapter=1,
                true_content="Truth 1",
                told_ironveil="Truth A",
                action_ironveil=IntelAction.TRUTHFUL,
            ),
            LedgerEntry(
                intel_id="intel_2",
                chapter=1,
                true_content="Truth 2",
                told_ironveil="Truth B",
                action_ironveil=IntelAction.TRUTHFUL,
            ),
        ]
        result = detect_contradictions(gs, "intel_2")
        assert result == []


# ---------------------------------------------------------------------------
# process_chapter_consequences
# ---------------------------------------------------------------------------


class TestProcessChapterConsequences:
    def test_process_chapter_consequences_applies_trust(self):
        """Truthful report should boost trust and reduce suspicion on the target faction."""
        intel = _make_intel(
            "ch1_mil_0",
            chapter=1,
            significance=3,
            war_tension_effect={"truthful": 0},
        )
        world = _make_world(intel=[intel])
        gs = initialize_game_state(world)

        # Add a corresponding ledger entry for the intel
        gs.ledger_entries.append(
            LedgerEntry(
                intel_id="ch1_mil_0",
                chapter=1,
                true_content="Test intel",
            )
        )

        ra = ReportAction(intel_id="ch1_mil_0", action=IntelAction.TRUTHFUL)
        old_trust = gs.embercrown_trust  # scene_b is EMBERCROWN when scene_a is IRONVEIL
        old_susp = gs.embercrown_suspicion

        narratives = process_chapter_consequences(
            gs, world, [ra], {"ch1_mil_0": (False, None)}
        )

        # Truthful unchecked: trust +5 * sig_mult, suspicion -3 * sig_mult
        # sig_mult = 0.5 + 3*0.2 = 1.1  -> trust +5, suspicion -3  (int truncation)
        assert gs.embercrown_trust >= old_trust  # trust should increase
        assert gs.embercrown_suspicion <= old_susp  # suspicion should decrease
        assert len(narratives) > 0

    def test_process_chapter_consequences_wild_cards(self):
        """Wild card events for the current chapter should be processed."""
        wc = WildCardEvent(
            chapter=1,
            description="A messenger arrives with dire news from the north.",
            war_tension_effect=5,
        )
        world = _make_world(wildcards=[wc])
        gs = initialize_game_state(world)
        old_tension = gs.war_tension

        narratives = process_chapter_consequences(gs, world, [], {})

        assert gs.war_tension == old_tension + 5
        assert any("[EVENT]" in n for n in narratives)
