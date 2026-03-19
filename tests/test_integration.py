"""Integration tests — full game loop simulation without LLM calls.

Exercises:
 1. Full chapter loop (3+ chapters)
 2. Save/load roundtrip with all fields
 3. Contradiction cascade across chapters
 4. Suspicion escalation to exposure
 5. War/peace ending paths
 6. Death cascade from high-significance truthful intel
"""
from __future__ import annotations

import random
from copy import deepcopy
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from config import (
    ChapterPhase,
    Faction,
    IntelAction,
    IntelCategory,
    MAX_CHAPTERS,
    SceneType,
    WAR_TENSION_PEACE,
    WAR_TENSION_START,
    WAR_TENSION_WAR,
)
from endings import _compute_stats, _evaluate_personal, _evaluate_political, evaluate_ending
from information_ledger import InformationLedger
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
from saves import load_game, save_game
from scene_evaluator import SceneEvaluator
from state_machine import (
    advance_chapter,
    detect_contradictions,
    evaluate_death_conditions,
    get_attending_characters,
    get_scene_b_faction,
    get_scene_type,
    initialize_game_state,
    process_chapter_consequences,
)
from trust_system import (
    apply_intel_consequence,
    check_suspicion_threshold,
    get_faction_suspicion,
    set_faction_suspicion,
    set_faction_trust,
)
from verification_engine import run_chapter_verification
from war_tension import apply_war_tension_change, check_war_state, determine_war_victor


# ---------------------------------------------------------------------------
# Factory helpers
# ---------------------------------------------------------------------------

def _make_char(
    name: str = "Agent",
    faction: Faction = Faction.IRONVEIL,
    **kw,
) -> CharacterProfile:
    defaults = dict(
        age=35,
        role="Spy",
        personality=["cunning", "loyal"],
        speech_pattern="formal",
        goals="survive",
        secrets="none",
        starting_trust=50,
        starting_suspicion=15,
        death_conditions="",
        behavioral_notes="standard",
    )
    defaults.update(kw)
    return CharacterProfile(name=name, faction=faction, **defaults)


def _make_intel(
    id: str = "ch1_military_1",
    source_faction: Faction = Faction.IRONVEIL,
    **kw,
) -> IntelligencePiece:
    defaults = dict(
        chapter=1,
        true_content="Test intel content",
        significance=3,
        verifiability=3,
        category=IntelCategory.MILITARY,
        war_tension_effect={"truthful": -2, "fabricated": 5, "distorted": 2, "withheld": 0},
        related_characters=[],
        distortion_suggestions=["Half-truth version"],
    )
    defaults.update(kw)
    return IntelligencePiece(id=id, source_faction=source_faction, **defaults)


def _make_world(
    chars: list[CharacterProfile] | None = None,
    intel: list[IntelligencePiece] | None = None,
    wildcards: list[WildCardEvent] | None = None,
) -> WorldState:
    if chars is None:
        chars = [
            _make_char(f"IVChar{i}", Faction.IRONVEIL, starting_trust=50, starting_suspicion=15)
            for i in range(4)
        ] + [
            _make_char(f"ECChar{i}", Faction.EMBERCROWN, starting_trust=50, starting_suspicion=15)
            for i in range(4)
        ]
    if intel is None:
        intel = []
        for ch in range(1, 4):
            intel.append(
                _make_intel(
                    f"ch{ch}_military_1",
                    source_faction=Faction.IRONVEIL if ch % 2 == 1 else Faction.EMBERCROWN,
                    chapter=ch,
                    significance=ch,
                )
            )
            intel.append(
                _make_intel(
                    f"ch{ch}_political_1",
                    source_faction=Faction.EMBERCROWN if ch % 2 == 1 else Faction.IRONVEIL,
                    chapter=ch,
                    significance=ch,
                    category=IntelCategory.POLITICAL,
                    true_content=f"Political intel for chapter {ch}",
                )
            )
    if wildcards is None:
        wildcards = []
    return WorldState(
        inciting_incident="A murdered diplomat found at the border",
        ironveil_background="Rigid military state",
        embercrown_background="Merchant kingdom",
        ashenmere_description="Neutral contested city",
        characters=chars,
        intelligence_pipeline=intel,
        wild_card_events=wildcards,
    )


# ---------------------------------------------------------------------------
# 1. Full game loop simulation (3 chapters)
# ---------------------------------------------------------------------------


class TestFullGameLoop:
    """Simulate 3 chapters of the game loop without LLM calls."""

    def test_three_chapter_loop(self):
        """Run through 3 complete chapters: init -> scene_type -> report ->
        verification -> consequences -> advance; then evaluate ending."""
        rng = random.Random(42)

        # Build world with 3 chapters of intel
        world = _make_world()
        gs = initialize_game_state(world)
        ledger = InformationLedger()

        assert gs.chapter == 1
        assert gs.war_tension == WAR_TENSION_START
        assert gs.scene_a_faction == Faction.IRONVEIL

        for chapter_num in range(1, 4):
            assert gs.chapter == chapter_num

            # Early termination checks
            war_state = check_war_state(gs)
            assert war_state is None, f"Unexpected war state at ch{chapter_num}: {war_state}"
            assert gs.ironveil_suspicion < 100 and gs.embercrown_suspicion < 100

            # Phase 1: scene_a faction selection
            faction_a = gs.scene_a_faction
            faction_b = get_scene_b_faction(gs)
            assert faction_a != faction_b

            scene_type_a = get_scene_type(gs, world, faction_a, rng=rng)
            chars_a = get_attending_characters(gs, world, faction_a, scene_type_a)
            assert len(chars_a) > 0
            assert all(c.faction == faction_a for c in chars_a)

            # Mark available intel as known (simulating scene A conversation)
            for intel_id in list(gs.available_intel):
                intel_obj = next(
                    (i for i in world.intelligence_pipeline if i.id == intel_id), None
                )
                if intel_obj and intel_obj.source_faction == faction_a:
                    if intel_id not in gs.known_intel:
                        gs.known_intel.append(intel_id)

            # Phase 2: scene_b type
            scene_type_b = get_scene_type(gs, world, faction_b, rng=rng)
            chars_b = get_attending_characters(gs, world, faction_b, scene_type_b)
            assert len(chars_b) > 0

            # Phase 3: Build report actions for known intel this chapter
            report_actions: list[ReportAction] = []
            for intel_id in gs.known_intel:
                intel_obj = next(
                    (i for i in world.intelligence_pipeline if i.id == intel_id), None
                )
                if intel_obj and intel_obj.chapter == chapter_num:
                    # Alternate between truthful and distorted
                    action = IntelAction.TRUTHFUL if rng.random() < 0.6 else IntelAction.DISTORTED
                    ra = ReportAction(
                        intel_id=intel_id,
                        action=action,
                        player_version="distorted version" if action == IntelAction.DISTORTED else None,
                    )
                    report_actions.append(ra)

                    # Create ledger entry
                    entry = LedgerEntry(
                        intel_id=intel_id,
                        chapter=chapter_num,
                        true_content=intel_obj.true_content,
                    )
                    if faction_b == Faction.IRONVEIL:
                        entry.told_ironveil = ra.player_version or intel_obj.true_content
                        entry.action_ironveil = ra.action
                    else:
                        entry.told_embercrown = ra.player_version or intel_obj.true_content
                        entry.action_embercrown = ra.action
                    ledger.add_entry(entry)
                    gs.ledger_entries.append(entry)

            # Phase 4: Verification
            verification_results = run_chapter_verification(
                gs, world, ledger, report_actions, rng=rng
            )
            for intel_id, (was_checked, check_passed) in verification_results.items():
                if was_checked:
                    ledger.mark_verified(intel_id, faction_b, check_passed)

            # Phase 5: Consequences
            old_tension = gs.war_tension
            consequences = process_chapter_consequences(
                gs, world, report_actions, verification_results
            )
            assert isinstance(consequences, list)

            # Phase 6: Advance
            if chapter_num < 3:
                advance_chapter(gs, world)

        # Final checks after 3 chapters
        assert gs.chapter == 3
        assert len(gs.ledger_entries) > 0
        assert len(gs.known_intel) > 0

        # Evaluate ending
        political, personal = evaluate_ending(gs)
        assert isinstance(political, str)
        assert isinstance(personal, str)
        assert len(political) > 5
        assert len(personal) > 5

    def test_faction_alternates_each_chapter(self):
        """Scene A faction should flip every chapter."""
        world = _make_world()
        gs = initialize_game_state(world)
        factions = [gs.scene_a_faction]
        for _ in range(4):
            advance_chapter(gs, world)
            factions.append(gs.scene_a_faction)
        # Should alternate: IV, EC, IV, EC, IV
        for i in range(len(factions) - 1):
            assert factions[i] != factions[i + 1]

    def test_available_intel_grows_each_chapter(self):
        """Each advance_chapter should add the new chapter's intel."""
        world = _make_world()
        gs = initialize_game_state(world)
        sizes = [len(gs.available_intel)]
        for _ in range(2):
            advance_chapter(gs, world)
            sizes.append(len(gs.available_intel))
        # Should be non-decreasing
        for i in range(len(sizes) - 1):
            assert sizes[i + 1] >= sizes[i]


# ---------------------------------------------------------------------------
# 2. Save/load roundtrip with full state
# ---------------------------------------------------------------------------


class TestSaveLoadRoundtrip:
    """Verify serialization preserves ALL state fields."""

    def test_full_state_roundtrip(self, tmp_path, monkeypatch):
        """Create a game state with ALL fields populated and verify roundtrip."""
        monkeypatch.setattr("saves.DATA_DIR", tmp_path)

        world = _make_world()
        gs = GameState(
            chapter=5,
            phase=ChapterPhase.CROSSOVER,
            ironveil_trust=72,
            ironveil_suspicion=38,
            embercrown_trust=45,
            embercrown_suspicion=55,
            character_trust={"IVChar0": 60, "ECChar0": 40},
            character_suspicion={"IVChar0": 20, "ECChar0": 50},
            character_alive={"IVChar0": True, "ECChar0": False},
            war_tension=68,
            war_started=False,
            war_victor=None,
            scene_a_faction=Faction.EMBERCROWN,
            available_intel=["ch1_military_1", "ch2_political_1"],
            known_intel=["ch1_military_1"],
            conversations=[
                ConversationLog(
                    chapter=1,
                    phase=ChapterPhase.SCENE_A,
                    faction=Faction.IRONVEIL,
                    scene_type=SceneType.WAR_COUNCIL,
                    characters_present=["IVChar0"],
                    exchanges=[{"role": "player", "text": "Hello"}],
                    intel_revealed=["ch1_military_1"],
                ),
            ],
            ledger_entries=[
                LedgerEntry(
                    intel_id="ch1_military_1",
                    chapter=1,
                    true_content="Troop movements",
                    told_ironveil=None,
                    told_embercrown="Troop movements",
                    action_embercrown=IntelAction.TRUTHFUL,
                    verified_embercrown=True,
                    verification_result_embercrown=True,
                    consequence="Trust boosted",
                    contradiction_with=["ch2_political_1"],
                ),
            ],
            npc_memories=[
                NPCMemory(
                    character_name="IVChar0",
                    chapter=1,
                    memory_text="Player was evasive about border patrols",
                    emotional_tag="suspicious",
                    player_quote="I saw nothing",
                    importance=4,
                ),
            ],
            scene_analyses=[
                SceneAnalysis(
                    chapter=1,
                    phase=ChapterPhase.SCENE_A,
                    faction=Faction.IRONVEIL,
                    memories=[],
                    slips=[],
                    trust_adjustments={"IVChar0": 3},
                    suspicion_adjustments={"IVChar0": -1},
                    faction_trust_delta=2,
                    faction_suspicion_delta=-1,
                    conversation_quality="good",
                    promises_made=["Investigate the northern pass"],
                    promises_fulfilled=[],
                ),
            ],
            player_promises=[
                {
                    "promise": "Investigate the northern pass",
                    "faction": "ironveil",
                    "chapter": 1,
                    "fulfilled": False,
                },
            ],
        )

        # Save
        save_game(world, gs, slot=1)

        # Load
        loaded = load_game(slot=1)
        assert loaded is not None

        lg = loaded.game_state
        lw = loaded.world_state

        # Verify every field
        assert lg.chapter == 5
        assert lg.phase == ChapterPhase.CROSSOVER
        assert lg.ironveil_trust == 72
        assert lg.ironveil_suspicion == 38
        assert lg.embercrown_trust == 45
        assert lg.embercrown_suspicion == 55
        assert lg.character_trust["IVChar0"] == 60
        assert lg.character_suspicion["ECChar0"] == 50
        assert lg.character_alive["ECChar0"] is False
        assert lg.war_tension == 68
        assert lg.war_started is False
        assert lg.war_victor is None
        assert lg.scene_a_faction == Faction.EMBERCROWN
        assert "ch1_military_1" in lg.available_intel
        assert "ch1_military_1" in lg.known_intel

        # Conversations
        assert len(lg.conversations) == 1
        assert lg.conversations[0].chapter == 1
        assert lg.conversations[0].exchanges[0]["text"] == "Hello"

        # Ledger entries
        assert len(lg.ledger_entries) == 1
        le = lg.ledger_entries[0]
        assert le.told_embercrown == "Troop movements"
        assert le.action_embercrown == IntelAction.TRUTHFUL
        assert le.verified_embercrown is True
        assert le.verification_result_embercrown is True
        assert le.consequence == "Trust boosted"
        assert "ch2_political_1" in le.contradiction_with

        # NPC Memories
        assert len(lg.npc_memories) == 1
        assert lg.npc_memories[0].character_name == "IVChar0"
        assert lg.npc_memories[0].importance == 4

        # Scene analyses
        assert len(lg.scene_analyses) == 1
        sa = lg.scene_analyses[0]
        assert sa.conversation_quality == "good"
        assert sa.promises_made == ["Investigate the northern pass"]

        # Player promises
        assert len(lg.player_promises) == 1
        assert lg.player_promises[0]["promise"] == "Investigate the northern pass"
        assert lg.player_promises[0]["fulfilled"] is False

        # World state preserved
        assert len(lw.characters) == len(world.characters)
        assert len(lw.intelligence_pipeline) == len(world.intelligence_pipeline)

    def test_empty_state_roundtrip(self, tmp_path, monkeypatch):
        """A freshly initialized game state should survive roundtrip."""
        monkeypatch.setattr("saves.DATA_DIR", tmp_path)
        world = _make_world()
        gs = initialize_game_state(world)
        save_game(world, gs, slot=2)
        loaded = load_game(slot=2)
        assert loaded is not None
        assert loaded.game_state.chapter == 1
        assert loaded.game_state.war_tension == WAR_TENSION_START


# ---------------------------------------------------------------------------
# 3. Contradiction cascade test
# ---------------------------------------------------------------------------


class TestContradictionCascade:
    """Build multi-chapter scenarios where the player tells different things
    to different factions, and verify contradictions are detected correctly."""

    def test_cross_chapter_contradictions(self):
        """Two entries with conflicting actions to the same faction should
        produce a contradiction."""
        gs = GameState()

        # Chapter 1: tell Ironveil the truth
        entry1 = LedgerEntry(
            intel_id="intel_1",
            chapter=1,
            true_content="Supply lines are secured",
            told_ironveil="Supply lines are secured",
            action_ironveil=IntelAction.TRUTHFUL,
        )
        gs.ledger_entries.append(entry1)

        # Chapter 2: fabricate to Ironveil
        entry2 = LedgerEntry(
            intel_id="intel_2",
            chapter=2,
            true_content="New alliance forming",
            told_ironveil="Embercrown plans total invasion",
            action_ironveil=IntelAction.FABRICATED,
        )
        gs.ledger_entries.append(entry2)

        # Chapter 3: fabricate again to Ironveil
        entry3 = LedgerEntry(
            intel_id="intel_3",
            chapter=3,
            true_content="Trade deal pending",
            told_ironveil="Trade embargo imminent",
            action_ironveil=IntelAction.FABRICATED,
        )
        gs.ledger_entries.append(entry3)

        # Detect contradictions for intel_2 (fab vs truth)
        contras_2 = detect_contradictions(gs, "intel_2")
        assert "intel_1" in contras_2

        # Detect contradictions for intel_3 (fab vs truth)
        contras_3 = detect_contradictions(gs, "intel_3")
        assert "intel_1" in contras_3

    def test_no_contradiction_same_action_types(self):
        """Two truthful entries should never contradict."""
        gs = GameState()
        gs.ledger_entries = [
            LedgerEntry(
                intel_id="a", chapter=1, true_content="X",
                told_ironveil="X", action_ironveil=IntelAction.TRUTHFUL,
            ),
            LedgerEntry(
                intel_id="b", chapter=2, true_content="Y",
                told_ironveil="Y", action_ironveil=IntelAction.TRUTHFUL,
            ),
        ]
        assert detect_contradictions(gs, "b") == []

    def test_cross_faction_different_stories(self):
        """Telling Ironveil the truth and Embercrown a fabrication about the
        same intel should NOT be flagged as a contradiction by detect_contradictions
        (the cross-faction case is intentional player strategy)."""
        gs = GameState()
        entry = LedgerEntry(
            intel_id="intel_1",
            chapter=1,
            true_content="Secret weapon plans",
            told_ironveil="Secret weapon plans",
            told_embercrown="No weapons being developed",
            action_ironveil=IntelAction.TRUTHFUL,
            action_embercrown=IntelAction.FABRICATED,
        )
        gs.ledger_entries.append(entry)

        # No OTHER entries to compare against, so no contradictions
        contras = detect_contradictions(gs, "intel_1")
        assert contras == []

    def test_contradiction_accumulation_across_three_chapters(self):
        """Track that contradictions compound across chapters."""
        gs = GameState()

        # Build 5 entries: truth, fab, truth, fab, fab
        actions = [
            IntelAction.TRUTHFUL,
            IntelAction.FABRICATED,
            IntelAction.TRUTHFUL,
            IntelAction.FABRICATED,
            IntelAction.FABRICATED,
        ]
        for i, action in enumerate(actions, start=1):
            gs.ledger_entries.append(LedgerEntry(
                intel_id=f"intel_{i}",
                chapter=i,
                true_content=f"Content {i}",
                told_embercrown=f"Told EC {i}",
                action_embercrown=action,
            ))

        # intel_4 (fabricated) should contradict intel_1 and intel_3 (truthful)
        contras_4 = detect_contradictions(gs, "intel_4")
        assert "intel_1" in contras_4
        assert "intel_3" in contras_4

        # intel_5 (fabricated) should also contradict intel_1 and intel_3
        contras_5 = detect_contradictions(gs, "intel_5")
        assert "intel_1" in contras_5
        assert "intel_3" in contras_5


# ---------------------------------------------------------------------------
# 4. Suspicion escalation test
# ---------------------------------------------------------------------------


class TestSuspicionEscalation:
    """Simulate repeated lies -> suspicion rises -> scene type changes ->
    exposure ending."""

    def test_suspicion_escalation_to_exposure(self):
        """Repeated fabrication exposure should drive suspicion to 100."""
        world = _make_world()
        gs = initialize_game_state(world)
        rng = random.Random(42)

        # Start with moderate suspicion
        gs.ironveil_suspicion = 40
        initial_threshold = check_suspicion_threshold(gs, Faction.IRONVEIL)
        assert initial_threshold == "scrutiny"

        # Simulate caught fabrications driving suspicion up
        intel = _make_intel(
            "high_sig_intel",
            significance=5,
            verifiability=5,
            category=IntelCategory.MILITARY,
        )

        # Each caught fabrication adds significant suspicion (until clamped at 100)
        for i in range(5):
            old_susp = gs.ironveil_suspicion
            apply_intel_consequence(
                gs, intel, IntelAction.FABRICATED, Faction.IRONVEIL,
                was_checked=True, check_passed=False,
            )
            # Suspicion should increase or stay at 100 (clamped)
            assert gs.ironveil_suspicion >= old_susp, f"Iteration {i}: suspicion decreased"

        # After exposed fabrications of significance 5, suspicion should hit the cap
        assert gs.ironveil_suspicion == 100, f"Expected max suspicion, got {gs.ironveil_suspicion}"

        # Verify scene type changes — at suspicion 100 ("exposed" threshold),
        # get_scene_type should still return INTERROGATION or PRIVATE_MEETING
        scene_type = get_scene_type(gs, world, Faction.IRONVEIL, rng=rng)
        assert scene_type in (SceneType.INTERROGATION, SceneType.PRIVATE_MEETING), (
            f"Expected interrogation/private at suspicion 100, got {scene_type}"
        )

    def test_exposure_threshold_reached(self):
        """Verify that suspicion >= 100 triggers the exposed threshold."""
        gs = GameState(ironveil_suspicion=100)
        threshold = check_suspicion_threshold(gs, Faction.IRONVEIL)
        assert threshold == "exposed"

    def test_scene_type_changes_with_suspicion(self):
        """Scene type selection should vary based on suspicion level."""
        world = _make_world()
        rng = random.Random(42)

        # Low suspicion -> normal rotation
        gs_low = GameState(chapter=1, ironveil_suspicion=10)
        scene_low = get_scene_type(gs_low, world, Faction.IRONVEIL, rng=rng)
        assert scene_low == SceneType.WAR_COUNCIL  # chapter 1 normal rotation

        # Exclusion range (51-70) -> private meeting
        gs_exclusion = GameState(chapter=1, ironveil_suspicion=60)
        scene_excl = get_scene_type(gs_exclusion, world, Faction.IRONVEIL, rng=rng)
        assert scene_excl == SceneType.PRIVATE_MEETING

        # Investigation range (81+) -> mostly interrogation
        gs_invest = GameState(chapter=1, ironveil_suspicion=85)
        # Use a fixed seed to get deterministic result
        scene_invest = get_scene_type(gs_invest, world, Faction.IRONVEIL, rng=random.Random(1))
        assert scene_invest in (SceneType.INTERROGATION, SceneType.PRIVATE_MEETING)


# ---------------------------------------------------------------------------
# 5. War tension endgame
# ---------------------------------------------------------------------------


class TestWarTensionEndgame:
    """Test war/peace ending triggers and war victor calculation."""

    def test_war_ending_trigger(self):
        """War tension >= 90 triggers war state."""
        gs = GameState(war_tension=WAR_TENSION_WAR)
        assert check_war_state(gs) == "war"

    def test_peace_ending_trigger(self):
        """War tension <= 20 and chapter >= 5 triggers peace."""
        gs = GameState(war_tension=WAR_TENSION_PEACE, chapter=5)
        assert check_war_state(gs) == "peace"

    def test_peace_requires_chapter_5(self):
        """Peace ending should not trigger before chapter 5."""
        gs = GameState(war_tension=10, chapter=3)
        assert check_war_state(gs) is None

    def test_war_victor_ironveil(self):
        """Ironveil wins when they got more truthful intel."""
        gs = GameState(war_started=True)
        world = _make_world()

        # Ironveil got truth, Embercrown got lies
        for i in range(3):
            gs.ledger_entries.append(LedgerEntry(
                intel_id=f"intel_{i}",
                chapter=1,
                true_content=f"Content {i}",
                action_ironveil=IntelAction.TRUTHFUL,
                action_embercrown=IntelAction.FABRICATED,
            ))

        victor = determine_war_victor(gs, world)
        assert victor == Faction.IRONVEIL.value

    def test_war_victor_significance_weighting(self):
        """Higher significance intel should carry more weight."""
        # Build world with varying significance
        intel_list = [
            _make_intel("low_sig", significance=1, chapter=1),
            _make_intel("high_sig", significance=5, chapter=1),
        ]
        world = _make_world(intel=intel_list)
        gs = GameState(war_started=True)

        # Ironveil gets the low-sig truth, Embercrown gets high-sig truth
        gs.ledger_entries = [
            LedgerEntry(
                intel_id="low_sig",
                chapter=1,
                true_content="Low sig",
                action_ironveil=IntelAction.TRUTHFUL,
                action_embercrown=IntelAction.FABRICATED,
            ),
            LedgerEntry(
                intel_id="high_sig",
                chapter=1,
                true_content="High sig",
                action_ironveil=IntelAction.FABRICATED,
                action_embercrown=IntelAction.TRUTHFUL,
            ),
        ]

        victor = determine_war_victor(gs, world)
        # Ironveil: +1 (truth low) - 5 (fab high) = -4
        # Embercrown: -1 (fab low) + 5 (truth high) = +4
        assert victor == Faction.EMBERCROWN.value

    def test_war_mutual_destruction(self):
        """Tied advantages result in None (mutual destruction)."""
        gs = GameState(war_started=True)
        gs.ledger_entries = [
            LedgerEntry(
                intel_id="a", chapter=1, true_content="X",
                action_ironveil=IntelAction.TRUTHFUL,
                action_embercrown=IntelAction.TRUTHFUL,
            ),
        ]
        victor = determine_war_victor(gs)
        assert victor is None

    def test_war_tension_escalation_to_war(self):
        """Simulate tension rising through fabricated intel effects until war."""
        gs = GameState(war_tension=70)

        # Each step adds tension
        for i in range(5):
            apply_war_tension_change(gs, 5, source=f"Fabricated intel {i}")

        assert gs.war_tension >= 90
        assert check_war_state(gs) == "war"

    def test_war_tension_deescalation_to_peace(self):
        """Simulate tension falling through truthful intel effects until peace."""
        gs = GameState(war_tension=40, chapter=5)

        for i in range(5):
            apply_war_tension_change(gs, -5, source=f"Truthful intel {i}")

        assert gs.war_tension <= 20
        assert check_war_state(gs) == "peace"


# ---------------------------------------------------------------------------
# 6. Death cascade test
# ---------------------------------------------------------------------------


class TestDeathCascade:
    """Verify character death mechanics and cascading effects."""

    def test_death_from_high_significance_truthful_intel(self):
        """Reporting high-sig intel truthfully to the opposing faction
        should trigger death for related characters with death conditions."""
        chars = [
            _make_char(
                "General Marcus", Faction.IRONVEIL,
                death_conditions="Killed if troop positions exposed to enemy",
            ),
            _make_char("Spy Raven", Faction.IRONVEIL),
            _make_char("Queen Elara", Faction.EMBERCROWN),
            _make_char("Lord Vex", Faction.EMBERCROWN),
        ]

        intel = _make_intel(
            "ch1_military_1",
            source_faction=Faction.IRONVEIL,
            significance=4,
            related_characters=["General Marcus"],
            chapter=1,
        )
        world = _make_world(chars=chars, intel=[intel])
        gs = initialize_game_state(world)

        # Report truthfully to Embercrown (opposing faction)
        ra = ReportAction(intel_id="ch1_military_1", action=IntelAction.TRUTHFUL)

        narratives = evaluate_death_conditions(gs, world, [ra])

        # General Marcus should be dead
        assert gs.character_alive["General Marcus"] is False
        assert any("General Marcus" in n for n in narratives)

    def test_no_death_from_low_significance(self):
        """Significance < 4 should not trigger death."""
        chars = [
            _make_char(
                "Spy Jones", Faction.IRONVEIL,
                death_conditions="Killed if exposed",
            ),
            _make_char("Agent Smith", Faction.EMBERCROWN),
        ]
        intel = _make_intel(
            "ch1_mil_1",
            source_faction=Faction.IRONVEIL,
            significance=2,  # Too low
            related_characters=["Spy Jones"],
            chapter=1,
        )
        world = _make_world(chars=chars, intel=[intel])
        gs = initialize_game_state(world)

        ra = ReportAction(intel_id="ch1_mil_1", action=IntelAction.TRUTHFUL)
        narratives = evaluate_death_conditions(gs, world, [ra])

        assert gs.character_alive["Spy Jones"] is True
        assert len(narratives) == 0

    def test_no_death_from_fabricated_report(self):
        """Fabricated reports should not trigger deaths."""
        chars = [
            _make_char(
                "Commander Vex", Faction.IRONVEIL,
                death_conditions="Killed if exposed",
            ),
            _make_char("Agent Echo", Faction.EMBERCROWN),
        ]
        intel = _make_intel(
            "ch1_mil_1",
            source_faction=Faction.IRONVEIL,
            significance=5,
            related_characters=["Commander Vex"],
            chapter=1,
        )
        world = _make_world(chars=chars, intel=[intel])
        gs = initialize_game_state(world)

        ra = ReportAction(intel_id="ch1_mil_1", action=IntelAction.FABRICATED)
        narratives = evaluate_death_conditions(gs, world, [ra])

        assert gs.character_alive["Commander Vex"] is True

    def test_dead_characters_excluded_from_scenes(self):
        """Dead characters should not appear in subsequent scenes."""
        world = _make_world()
        gs = initialize_game_state(world)

        # Kill first Ironveil character
        first_iv_name = [c.name for c in world.characters if c.faction == Faction.IRONVEIL][0]
        gs.character_alive[first_iv_name] = False

        attending = get_attending_characters(gs, world, Faction.IRONVEIL, SceneType.WAR_COUNCIL)
        names = [c.name for c in attending]
        assert first_iv_name not in names
        assert len(attending) == 3  # 4 - 1 dead

    def test_multiple_deaths_in_one_chapter(self):
        """Multiple characters can die from multiple intel pieces in one chapter."""
        chars = [
            _make_char(
                "Gen Alpha", Faction.IRONVEIL,
                death_conditions="Killed if battle plans exposed",
            ),
            _make_char(
                "Adm Beta", Faction.IRONVEIL,
                death_conditions="Killed if fleet positions exposed",
            ),
            _make_char("Queen Gamma", Faction.EMBERCROWN),
            _make_char("Lord Delta", Faction.EMBERCROWN),
        ]

        intel_list = [
            _make_intel(
                "ch1_military_1",
                source_faction=Faction.IRONVEIL,
                significance=5,
                related_characters=["Gen Alpha"],
                chapter=1,
            ),
            _make_intel(
                "ch1_military_2",
                source_faction=Faction.IRONVEIL,
                significance=4,
                related_characters=["Adm Beta"],
                chapter=1,
            ),
        ]

        world = _make_world(chars=chars, intel=intel_list)
        gs = initialize_game_state(world)

        report_actions = [
            ReportAction(intel_id="ch1_military_1", action=IntelAction.TRUTHFUL),
            ReportAction(intel_id="ch1_military_2", action=IntelAction.TRUTHFUL),
        ]

        narratives = evaluate_death_conditions(gs, world, report_actions)

        assert gs.character_alive["Gen Alpha"] is False
        assert gs.character_alive["Adm Beta"] is False
        assert len(narratives) >= 2


# ---------------------------------------------------------------------------
# 7. Stats computation
# ---------------------------------------------------------------------------


class TestComputeStats:
    """Verify post-game statistics are computed correctly."""

    def test_compute_stats_counts_actions(self):
        gs = GameState(
            chapter=3,
            war_tension=65,
            ironveil_trust=55,
            embercrown_trust=40,
            character_alive={"A": True, "B": False, "C": True},
        )
        gs.ledger_entries = [
            LedgerEntry(
                intel_id="a", chapter=1, true_content="X",
                action_ironveil=IntelAction.TRUTHFUL,
                action_embercrown=IntelAction.FABRICATED,
            ),
            LedgerEntry(
                intel_id="b", chapter=2, true_content="Y",
                action_ironveil=IntelAction.DISTORTED,
                action_embercrown=IntelAction.WITHHELD,
            ),
        ]
        stats = _compute_stats(gs)
        assert stats["Truths Told"] == "1"
        assert stats["Fabrications Created"] == "1"
        assert stats["Distortions Spun"] == "1"
        assert stats["Intel Withheld"] == "1"
        assert stats["Lives Lost"] == "1"
        assert stats["Final War Tension"] == "65%"

    def test_compute_stats_handles_none_actions(self):
        """Entries with None actions should not crash stats computation."""
        gs = GameState(chapter=1, character_alive={})
        gs.ledger_entries = [
            LedgerEntry(
                intel_id="a", chapter=1, true_content="X",
                action_ironveil=None,
                action_embercrown=IntelAction.TRUTHFUL,
            ),
        ]
        stats = _compute_stats(gs)
        assert stats["Truths Told"] == "1"


# ---------------------------------------------------------------------------
# 8. Scene evaluator apply_analysis integration
# ---------------------------------------------------------------------------


class TestSceneEvaluatorIntegration:
    """Verify that SceneEvaluator.apply_analysis integrates trust, suspicion,
    memories, promises, and slips correctly over multiple scenes."""

    def test_multi_scene_cumulative_effects(self):
        """Apply two scene analyses and verify effects are cumulative."""
        ev = SceneEvaluator(display=MagicMock())
        gs = GameState(
            ironveil_trust=50,
            ironveil_suspicion=15,
            character_trust={"Alice": 50},
            character_suspicion={"Alice": 15},
        )

        # Scene 1: good quality, +1 trust, -1 suspicion from quality
        analysis1 = SceneAnalysis(
            chapter=1,
            phase=ChapterPhase.SCENE_A,
            faction=Faction.IRONVEIL,
            conversation_quality="good",
            faction_trust_delta=2,
            faction_suspicion_delta=-1,
            trust_adjustments={"Alice": 3},
            suspicion_adjustments={"Alice": -2},
            memories=[
                NPCMemory(
                    character_name="Alice",
                    chapter=1,
                    memory_text="Player was cooperative",
                    emotional_tag="trusting",
                    importance=3,
                ),
            ],
            promises_made=["Bring intel on eastern pass"],
        )
        ev.apply_analysis(analysis1, gs)

        # good quality: trust +1, suspicion -1
        # faction_trust_delta: +2, faction_suspicion_delta: -1
        # total faction: trust += 3, suspicion -= 2
        assert gs.ironveil_trust == 53
        assert gs.ironveil_suspicion == 13
        assert gs.character_trust["Alice"] == 53
        assert len(gs.npc_memories) == 1
        assert len(gs.player_promises) == 1

        # Scene 2: hostile quality with a slip
        analysis2 = SceneAnalysis(
            chapter=2,
            phase=ChapterPhase.SCENE_A,
            faction=Faction.IRONVEIL,
            conversation_quality="hostile",
            faction_trust_delta=-3,
            faction_suspicion_delta=2,
            slips=[
                SlipDetection(
                    slip_type="cross_faction_knowledge",
                    description="Referenced Embercrown plans",
                    severity=3,
                    detecting_character="Alice",
                    evidence_quote="Your border plan...",
                ),
            ],
            trust_adjustments={"Alice": -4},
            suspicion_adjustments={"Alice": 5},
            promises_fulfilled=["Bring intel on eastern pass"],
        )
        ev.apply_analysis(analysis2, gs)

        # hostile: trust -5, suspicion +3
        # faction_delta: trust -3, suspicion +2
        # slip sev3: trust -3, suspicion +8
        # total: trust -= 11, suspicion += 13
        assert gs.ironveil_trust == 53 - 11  # 42
        assert gs.ironveil_suspicion == 13 + 13  # 26
        assert gs.character_trust["Alice"] == 53 - 4  # 49
        assert len(gs.scene_analyses) == 2

        # Promise should be marked fulfilled
        assert gs.player_promises[0]["fulfilled"] is True


# ---------------------------------------------------------------------------
# 9. Verification engine integration
# ---------------------------------------------------------------------------


class TestVerificationIntegration:
    """Verify the full verification pipeline works correctly."""

    def test_verification_pipeline(self):
        """Run full chapter verification and check results match expectations."""
        rng = random.Random(42)
        world = _make_world()
        gs = initialize_game_state(world)
        ledger = InformationLedger()

        # Set up report actions for chapter 1 intel
        report_actions = []
        for intel_id in gs.available_intel:
            intel_obj = next(
                (i for i in world.intelligence_pipeline if i.id == intel_id), None
            )
            if intel_obj and intel_obj.chapter == 1:
                ra = ReportAction(intel_id=intel_id, action=IntelAction.FABRICATED)
                report_actions.append(ra)

        results = run_chapter_verification(gs, world, ledger, report_actions, rng=rng)

        # All report actions should have results
        for ra in report_actions:
            assert ra.intel_id in results
            was_checked, check_passed = results[ra.intel_id]
            if was_checked:
                # Fabrication always fails when checked
                assert check_passed is False

    def test_withheld_never_verified(self):
        """Withheld intel should never be checked."""
        rng = random.Random(42)
        world = _make_world()
        gs = initialize_game_state(world)
        ledger = InformationLedger()

        report_actions = [
            ReportAction(
                intel_id=gs.available_intel[0],
                action=IntelAction.WITHHELD,
            ),
        ]

        results = run_chapter_verification(gs, world, ledger, report_actions, rng=rng)
        for _, (was_checked, _) in results.items():
            assert was_checked is False


# ---------------------------------------------------------------------------
# 10. Wild card events in consequences
# ---------------------------------------------------------------------------


class TestWildCardEvents:
    """Wild card events should fire at the correct chapter."""

    def test_wild_card_applies_tension(self):
        """Wild card events on the current chapter should change war tension."""
        wc = WildCardEvent(
            chapter=1,
            description="Border skirmish erupts",
            war_tension_effect=10,
        )
        world = _make_world(wildcards=[wc])
        gs = initialize_game_state(world)
        old_tension = gs.war_tension

        narratives = process_chapter_consequences(gs, world, [], {})

        assert gs.war_tension == old_tension + 10
        assert any("[EVENT]" in n for n in narratives)

    def test_wild_card_wrong_chapter_ignored(self):
        """Wild card events on a different chapter should not fire."""
        wc = WildCardEvent(
            chapter=5,
            description="Late game event",
            war_tension_effect=15,
        )
        world = _make_world(wildcards=[wc])
        gs = initialize_game_state(world)
        old_tension = gs.war_tension

        narratives = process_chapter_consequences(gs, world, [], {})

        assert gs.war_tension == old_tension
        assert not any("[EVENT]" in n for n in narratives)

    def test_negative_wild_card(self):
        """Negative tension wild card should decrease tension."""
        wc = WildCardEvent(
            chapter=1,
            description="Peace talks begin",
            war_tension_effect=-10,
        )
        world = _make_world(wildcards=[wc])
        gs = initialize_game_state(world)
        old_tension = gs.war_tension

        process_chapter_consequences(gs, world, [], {})

        assert gs.war_tension == old_tension - 10


# ---------------------------------------------------------------------------
# 11. Ending evaluation coverage
# ---------------------------------------------------------------------------


class TestEndingEvaluation:
    """Verify political and personal ending evaluation paths."""

    def test_all_political_paths(self):
        """Cover all political outcome branches."""
        # Peace
        assert "peace" in _evaluate_political(GameState(war_tension=15)).lower()
        # Ironveil victory
        assert "ironveil" in _evaluate_political(
            GameState(war_started=True, war_victor=Faction.IRONVEIL.value, war_tension=95)
        ).lower()
        # Embercrown victory
        assert "embercrown" in _evaluate_political(
            GameState(war_started=True, war_victor=Faction.EMBERCROWN.value, war_tension=95)
        ).lower()
        # Mutual destruction
        assert "mutual" in _evaluate_political(
            GameState(war_started=True, war_victor=None, war_tension=95)
        ).lower()
        # Fragile standoff
        assert "standoff" in _evaluate_political(
            GameState(war_tension=75, war_started=False)
        ).lower()
        # Uncertain future
        assert "uncertain" in _evaluate_political(
            GameState(war_tension=45, war_started=False)
        ).lower()

    def test_all_personal_paths(self):
        """Cover key personal fate branches."""
        # Architect (tightened thresholds: trust >= 80, suspicion <= 20)
        result = _evaluate_personal(GameState(
            ironveil_trust=85, embercrown_trust=85,
            ironveil_suspicion=15, embercrown_suspicion=15,
        ))
        assert "architect" in result.lower()

        # Ghost (tightened thresholds: trust >= 45, suspicion <= 25)
        result = _evaluate_personal(GameState(
            ironveil_trust=50, embercrown_trust=50,
            ironveil_suspicion=20, embercrown_suspicion=20,
        ))
        assert "ghost" in result.lower()

        # Prisoner
        result = _evaluate_personal(GameState(
            ironveil_trust=30, embercrown_trust=30,
            ironveil_suspicion=75, embercrown_suspicion=80,
        ))
        assert "prisoner" in result.lower()

        # Martyr (Embercrown hero, Ironveil traitor)
        result = _evaluate_personal(GameState(
            ironveil_trust=30, embercrown_trust=75,
            ironveil_suspicion=65, embercrown_suspicion=10,
        ))
        assert "martyr" in result.lower()

        # Survivor (equal trust, moderate suspicion)
        result = _evaluate_personal(GameState(
            ironveil_trust=50, embercrown_trust=50,
            ironveil_suspicion=40, embercrown_suspicion=40,
        ))
        assert "survivor" in result.lower()

        # Ironveil's Agent
        result = _evaluate_personal(GameState(
            ironveil_trust=60, embercrown_trust=35,
            ironveil_suspicion=40, embercrown_suspicion=40,
        ))
        assert "ironveil" in result.lower()

        # Embercrown's Agent
        result = _evaluate_personal(GameState(
            ironveil_trust=35, embercrown_trust=60,
            ironveil_suspicion=40, embercrown_suspicion=40,
        ))
        assert "embercrown" in result.lower()


# ---------------------------------------------------------------------------
# 12. Ledger integration
# ---------------------------------------------------------------------------


class TestLedgerIntegration:
    """Full ledger lifecycle: add, query, verify, report."""

    def test_ledger_lifecycle(self):
        """Add entries, verify, check contradictions, generate summary."""
        ledger = InformationLedger()

        # Chapter 1: truthful report to Ironveil
        e1 = LedgerEntry(
            intel_id="ch1_mil_1", chapter=1, true_content="Border troops",
            told_ironveil="Border troops", action_ironveil=IntelAction.TRUTHFUL,
        )
        ledger.add_entry(e1)

        # Chapter 2: fabricated report to Ironveil (should create contradiction)
        e2 = LedgerEntry(
            intel_id="ch2_mil_1", chapter=2, true_content="Supply lines",
            told_ironveil="Massive army", action_ironveil=IntelAction.FABRICATED,
        )
        warnings = ledger.add_entry(e2)
        assert len(warnings) > 0

        # Verify chapter 1 entry
        ledger.mark_verified("ch1_mil_1", Faction.IRONVEIL, True)
        entry = ledger.get_entry_by_intel_id("ch1_mil_1")
        assert entry.verified_ironveil is True
        assert entry.verification_result_ironveil is True

        # Query by chapter
        ch1_entries = ledger.get_entries_by_chapter(1)
        assert len(ch1_entries) == 1

        # Query by faction
        iv_entries = ledger.get_entries_for_faction(Faction.IRONVEIL)
        assert len(iv_entries) == 2

        # Unchecked fabrications
        unchecked = ledger.get_unchecked_fabrications(Faction.IRONVEIL)
        assert len(unchecked) == 1
        assert unchecked[0].intel_id == "ch2_mil_1"

        # Summary
        summary = ledger.get_faction_report_summary(Faction.IRONVEIL)
        assert "ch1_mil_1" in summary
        assert "ch2_mil_1" in summary

        # Full history
        history = ledger.get_full_history()
        assert "Chapter 1" in history
        assert "Chapter 2" in history
