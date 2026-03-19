"""Shared fixtures for the double-agent-war-council test suite."""
from __future__ import annotations

import pytest

from config import (
    ChapterPhase,
    Faction,
    IntelAction,
    IntelCategory,
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
    SceneAnalysis,
    SlipDetection,
    WildCardEvent,
    WorldState,
)
from information_ledger import InformationLedger
from state_machine import initialize_game_state


# ---------------------------------------------------------------------------
# Factory fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def make_character():
    """Factory that builds a CharacterProfile with sensible defaults."""

    def _factory(
        name: str = "Test Char",
        faction: Faction = Faction.IRONVEIL,
        **overrides,
    ) -> CharacterProfile:
        defaults = dict(
            name=name,
            age=35,
            role="Advisor",
            faction=faction,
            personality=["cautious", "loyal"],
            speech_pattern="Formal and measured",
            goals="Survive the war",
            secrets="Secretly doubts the cause",
            starting_trust=50,
            starting_suspicion=15,
            relationships={},
            knowledge={},
            death_conditions="Caught spying",
            behavioral_notes="Tends to test loyalty",
        )
        defaults.update(overrides)
        return CharacterProfile(**defaults)

    return _factory


@pytest.fixture
def make_intel():
    """Factory that builds an IntelligencePiece with sensible defaults."""

    def _factory(
        id: str = "ch1_military_1",
        source_faction: Faction = Faction.IRONVEIL,
        **overrides,
    ) -> IntelligencePiece:
        defaults = dict(
            id=id,
            chapter=1,
            source_faction=source_faction,
            true_content="Ironveil is massing troops on the border",
            significance=3,
            verifiability=3,
            category=IntelCategory.MILITARY,
            potential_consequences={"truthful": "Embercrown prepares defenses"},
            related_characters=["General Thane"],
            war_tension_effect={"truthful": -5, "fabricated": 10},
            distortion_suggestions=["Claim the troops are for a parade"],
        )
        defaults.update(overrides)
        return IntelligencePiece(**defaults)

    return _factory


# ---------------------------------------------------------------------------
# Composite fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_world(make_character, make_intel):
    """A fully populated WorldState with 8 characters, 6+ intel, 2 wild cards."""

    ironveil_chars = [
        make_character(name="General Thane", faction=Faction.IRONVEIL, role="General", starting_trust=45, starting_suspicion=20),
        make_character(name="Lady Selene", faction=Faction.IRONVEIL, role="Spymaster", starting_trust=40, starting_suspicion=25),
        make_character(name="Brother Aldric", faction=Faction.IRONVEIL, role="Priest", starting_trust=55, starting_suspicion=10),
        make_character(name="Captain Voss", faction=Faction.IRONVEIL, role="Captain", starting_trust=50, starting_suspicion=15),
    ]
    embercrown_chars = [
        make_character(name="Queen Isolde", faction=Faction.EMBERCROWN, role="Queen", starting_trust=50, starting_suspicion=20),
        make_character(name="Lord Kaelen", faction=Faction.EMBERCROWN, role="Advisor", starting_trust=55, starting_suspicion=10),
        make_character(name="Seraph Nyx", faction=Faction.EMBERCROWN, role="Assassin", starting_trust=40, starting_suspicion=30),
        make_character(name="Marshal Draven", faction=Faction.EMBERCROWN, role="Marshal", starting_trust=45, starting_suspicion=25),
    ]

    intel_pieces = [
        make_intel(id="ch1_military_1", chapter=1, source_faction=Faction.IRONVEIL, category=IntelCategory.MILITARY, significance=3, verifiability=3),
        make_intel(id="ch1_political_1", chapter=1, source_faction=Faction.EMBERCROWN, category=IntelCategory.POLITICAL, significance=2, verifiability=2, true_content="Embercrown plans a new alliance"),
        make_intel(id="ch2_economic_1", chapter=2, source_faction=Faction.IRONVEIL, category=IntelCategory.ECONOMIC, significance=4, verifiability=4, true_content="Ironveil's treasury is nearly empty"),
        make_intel(id="ch2_personal_1", chapter=2, source_faction=Faction.EMBERCROWN, category=IntelCategory.PERSONAL, significance=1, verifiability=1, true_content="Queen Isolde has a secret lover"),
        make_intel(id="ch3_military_1", chapter=3, source_faction=Faction.IRONVEIL, category=IntelCategory.MILITARY, significance=5, verifiability=5, true_content="Ironveil has a superweapon"),
        make_intel(id="ch3_political_1", chapter=3, source_faction=Faction.EMBERCROWN, category=IntelCategory.POLITICAL, significance=3, verifiability=3, true_content="Embercrown nobles are plotting a coup"),
    ]

    wild_cards = [
        WildCardEvent(chapter=2, description="A plague sweeps through Ashenmere", war_tension_effect=-5, narrative_prompt="Both sides must cooperate"),
        WildCardEvent(chapter=4, description="A border skirmish erupts", war_tension_effect=10, narrative_prompt="Tensions flare from an incident"),
    ]

    return WorldState(
        inciting_incident="A murdered diplomat found at the border",
        ironveil_background="A rigid military state valuing order",
        embercrown_background="A merchant kingdom valuing prosperity",
        ashenmere_description="The contested neutral city between the two factions",
        characters=ironveil_chars + embercrown_chars,
        intelligence_pipeline=intel_pieces,
        wild_card_events=wild_cards,
        ending_conditions=EndingConditions(),
    )


@pytest.fixture
def fresh_game_state(sample_world):
    """A GameState initialized from sample_world via initialize_game_state()."""
    return initialize_game_state(sample_world)


@pytest.fixture
def populated_ledger():
    """An InformationLedger pre-loaded with diverse entries."""
    entries = [
        LedgerEntry(
            intel_id="ch1_military_1",
            chapter=1,
            true_content="Ironveil is massing troops on the border",
            told_ironveil=None,
            told_embercrown="Ironveil is massing troops on the border",
            action_ironveil=None,
            action_embercrown=IntelAction.TRUTHFUL,
            verified_embercrown=True,
            verification_result_embercrown=True,
        ),
        LedgerEntry(
            intel_id="ch1_political_1",
            chapter=1,
            true_content="Embercrown plans a new alliance",
            told_ironveil="Embercrown is planning an invasion",
            told_embercrown=None,
            action_ironveil=IntelAction.FABRICATED,
            action_embercrown=None,
            verified_ironveil=False,
        ),
        LedgerEntry(
            intel_id="ch2_economic_1",
            chapter=2,
            true_content="Ironveil's treasury is nearly empty",
            told_ironveil=None,
            told_embercrown="Ironveil's treasury is somewhat strained",
            action_ironveil=None,
            action_embercrown=IntelAction.DISTORTED,
            distortion_details="Downplayed severity",
        ),
        LedgerEntry(
            intel_id="ch2_personal_1",
            chapter=2,
            true_content="Queen Isolde has a secret lover",
            told_ironveil=None,
            told_embercrown=None,
            action_ironveil=IntelAction.WITHHELD,
            action_embercrown=IntelAction.WITHHELD,
        ),
    ]
    return InformationLedger(entries)


# ---------------------------------------------------------------------------
# Analysis fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_scene_analysis():
    """A SceneAnalysis with memories, slips, and promises."""
    return SceneAnalysis(
        chapter=2,
        phase=ChapterPhase.SCENE_A,
        faction=Faction.IRONVEIL,
        memories=[
            NPCMemory(
                character_name="General Thane",
                chapter=2,
                memory_text="The envoy seemed overly interested in troop movements",
                emotional_tag="suspicious",
                player_quote="How many soldiers guard the eastern pass?",
                importance=4,
            ),
            NPCMemory(
                character_name="Lady Selene",
                chapter=2,
                memory_text="The envoy was charming and cooperative",
                emotional_tag="trusting",
                player_quote="I bring news that serves both our interests",
                importance=3,
            ),
        ],
        slips=[
            SlipDetection(
                slip_type="cross_faction_knowledge",
                description="Referenced Embercrown troop count not shared with Ironveil",
                severity=3,
                detecting_character="Lady Selene",
                evidence_quote="Their eastern garrison has 500 men",
            ),
        ],
        trust_adjustments={"General Thane": -2, "Lady Selene": 3},
        suspicion_adjustments={"General Thane": 4, "Lady Selene": -1},
        faction_trust_delta=1,
        faction_suspicion_delta=2,
        conversation_quality="good",
        promises_made=["Share military intelligence next visit"],
    )


@pytest.fixture
def sample_conversation_log():
    """A ConversationLog with 4 exchanges."""
    return ConversationLog(
        chapter=2,
        phase=ChapterPhase.SCENE_A,
        faction=Faction.IRONVEIL,
        scene_type=SceneType.WAR_COUNCIL,
        characters_present=["General Thane", "Lady Selene", "Brother Aldric"],
        exchanges=[
            {"speaker": "General Thane", "text": "What news from the border?"},
            {"speaker": "player", "text": "The roads are quiet, General."},
            {"speaker": "Lady Selene", "text": "Quiet can be deceptive."},
            {"speaker": "player", "text": "Indeed. I bring word of troop movements."},
        ],
        intel_revealed=["ch1_military_1"],
        intel_delivered=["ch2_economic_1"],
    )
