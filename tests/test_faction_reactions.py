"""Tests for the faction_reactions module — faction reaction system."""
from __future__ import annotations

import random

import pytest

from config import Faction, IntelAction, IntelCategory
from models import (
    CharacterProfile,
    FactionReaction,
    GameState,
    IntelligencePiece,
    LedgerEntry,
    ReportAction,
    WildCardEvent,
    WorldState,
)
from faction_reactions import (
    REACTION_TEMPLATES,
    build_intel_map,
    generate_faction_reactions,
    generate_counter_intel,
    evaluate_reaction_outcomes,
    apply_reaction_effects,
    MAX_REACTIONS_PER_CHAPTER,
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
        true_content="Test intel content",
        significance=3,
        verifiability=3,
        category=IntelCategory.MILITARY,
        related_characters=["TestChar"],
    )
    defaults.update(kw)
    return IntelligencePiece(id=id, source_faction=source_faction, **defaults)


def _make_world(chars=None, intel=None):
    if chars is None:
        chars = [
            _make_char(f"Char{i}", Faction.IRONVEIL if i < 4 else Faction.EMBERCROWN)
            for i in range(8)
        ]
    if intel is None:
        intel = [_make_intel(f"ch1_military_{i + 1}") for i in range(3)]
    return WorldState(
        inciting_incident="Test incident",
        ironveil_background="Iron bg",
        embercrown_background="Ember bg",
        ashenmere_description="Neutral zone",
        characters=chars,
        intelligence_pipeline=intel,
        wild_card_events=[],
    )


def _make_game_state(**kw):
    return GameState(**kw)


def _make_report_action(intel_id, action, player_version=None):
    return ReportAction(
        intel_id=intel_id,
        action=action,
        player_version=player_version,
    )


# ---------------------------------------------------------------------------
# Template Coverage Tests
# ---------------------------------------------------------------------------

class TestTemplateCoverage:
    """Every (IntelCategory, non-WITHHELD IntelAction) pair has at least one template."""

    def test_all_category_action_pairs_covered(self):
        for category in IntelCategory:
            for action in IntelAction:
                if action == IntelAction.WITHHELD:
                    continue
                key = (category, action)
                assert key in REACTION_TEMPLATES, (
                    f"Missing template for ({category.value}, {action.value})"
                )
                assert len(REACTION_TEMPLATES[key]) >= 1

    def test_withheld_not_in_templates(self):
        for key in REACTION_TEMPLATES:
            assert key[1] != IntelAction.WITHHELD


# ---------------------------------------------------------------------------
# build_intel_map Tests
# ---------------------------------------------------------------------------

class TestBuildIntelMap:
    def test_includes_world_pipeline(self):
        intel = _make_intel("ch1_mil_1")
        world = _make_world(intel=[intel])
        gs = _make_game_state()
        m = build_intel_map(world, gs)
        assert "ch1_mil_1" in m
        assert m["ch1_mil_1"] is intel

    def test_includes_dynamic_intel(self):
        world = _make_world(intel=[])
        gs = _make_game_state()
        dynamic = _make_intel("ch2_reaction_0", chapter=2)
        gs.dynamic_intel.append(dynamic)
        m = build_intel_map(world, gs)
        assert "ch2_reaction_0" in m

    def test_dynamic_overwrites_world(self):
        """If same ID exists in both, dynamic wins (shouldn't happen, but safe)."""
        world_intel = _make_intel("shared_id", true_content="world version")
        world = _make_world(intel=[world_intel])
        gs = _make_game_state()
        dynamic = _make_intel("shared_id", true_content="dynamic version")
        gs.dynamic_intel.append(dynamic)
        m = build_intel_map(world, gs)
        assert m["shared_id"].true_content == "dynamic version"


# ---------------------------------------------------------------------------
# generate_faction_reactions Tests
# ---------------------------------------------------------------------------

class TestGenerateFactionReactions:
    def test_withheld_produces_no_reaction(self):
        intel = _make_intel("ch1_mil_1")
        world = _make_world(intel=[intel])
        gs = _make_game_state()
        actions = [_make_report_action("ch1_mil_1", IntelAction.WITHHELD)]
        reactions = generate_faction_reactions(gs, world, actions, Faction.EMBERCROWN)
        assert reactions == []

    def test_truthful_produces_reaction(self):
        intel = _make_intel("ch1_mil_1")
        world = _make_world(intel=[intel])
        gs = _make_game_state()
        actions = [_make_report_action("ch1_mil_1", IntelAction.TRUTHFUL)]
        reactions = generate_faction_reactions(gs, world, actions, Faction.EMBERCROWN)
        assert len(reactions) == 1
        r = reactions[0]
        assert r.acting_faction == "embercrown"
        assert r.trigger_intel_id == "ch1_mil_1"
        assert r.trigger_action == IntelAction.TRUTHFUL
        assert r.reaction_type == "military_mobilization"
        assert r.based_on_false_intel is False
        assert r.chapter_generated == 1
        assert r.chapter_visible == 2

    def test_fabricated_marks_false_intel(self):
        intel = _make_intel("ch1_mil_1")
        world = _make_world(intel=[intel])
        gs = _make_game_state()
        actions = [_make_report_action("ch1_mil_1", IntelAction.FABRICATED)]
        reactions = generate_faction_reactions(gs, world, actions, Faction.EMBERCROWN)
        assert len(reactions) == 1
        assert reactions[0].based_on_false_intel is True
        assert reactions[0].reaction_type == "phantom_response"

    def test_distorted_marks_false_intel(self):
        intel = _make_intel("ch1_mil_1")
        world = _make_world(intel=[intel])
        gs = _make_game_state()
        actions = [_make_report_action("ch1_mil_1", IntelAction.DISTORTED)]
        reactions = generate_faction_reactions(gs, world, actions, Faction.EMBERCROWN)
        assert len(reactions) == 1
        assert reactions[0].based_on_false_intel is True

    def test_max_cap_per_chapter(self):
        """At most MAX_REACTIONS_PER_CHAPTER reactions generated."""
        intels = [
            _make_intel(f"ch1_military_{i}", category=IntelCategory.MILITARY)
            for i in range(5)
        ]
        world = _make_world(intel=intels)
        gs = _make_game_state()
        actions = [
            _make_report_action(f"ch1_military_{i}", IntelAction.TRUTHFUL)
            for i in range(5)
        ]
        reactions = generate_faction_reactions(gs, world, actions, Faction.EMBERCROWN)
        assert len(reactions) <= MAX_REACTIONS_PER_CHAPTER

    def test_all_categories_generate_reactions(self):
        """Each category produces a valid reaction."""
        for cat in IntelCategory:
            intel = _make_intel(f"ch1_{cat.value}_1", category=cat)
            world = _make_world(intel=[intel])
            gs = _make_game_state()
            actions = [_make_report_action(f"ch1_{cat.value}_1", IntelAction.TRUTHFUL)]
            reactions = generate_faction_reactions(gs, world, actions, Faction.EMBERCROWN)
            assert len(reactions) == 1, f"No reaction for category {cat.value}"

    def test_counter_intel_loop_prevention(self):
        """Intel with reaction IDs should not generate further counter-intel."""
        intel = _make_intel("ch2_reaction_0", chapter=2)
        world = _make_world(intel=[])
        gs = _make_game_state(chapter=2)
        gs.dynamic_intel.append(intel)
        actions = [_make_report_action("ch2_reaction_0", IntelAction.TRUTHFUL)]
        reactions = generate_faction_reactions(gs, world, actions, Faction.EMBERCROWN)
        assert reactions == []

    def test_reaction_id_format(self):
        intel = _make_intel("ch1_mil_1")
        world = _make_world(intel=[intel])
        gs = _make_game_state()
        actions = [_make_report_action("ch1_mil_1", IntelAction.TRUTHFUL)]
        reactions = generate_faction_reactions(gs, world, actions, Faction.EMBERCROWN)
        assert reactions[0].id == "react_ch1_embercrown_0"

    def test_missing_intel_id_skipped(self):
        """Reports for nonexistent intel produce no reactions."""
        world = _make_world(intel=[])
        gs = _make_game_state()
        actions = [_make_report_action("nonexistent_id", IntelAction.TRUTHFUL)]
        reactions = generate_faction_reactions(gs, world, actions, Faction.EMBERCROWN)
        assert reactions == []

    def test_affected_characters_from_intel(self):
        intel = _make_intel("ch1_mil_1", related_characters=["GeneralKaer"])
        world = _make_world(intel=[intel])
        gs = _make_game_state()
        actions = [_make_report_action("ch1_mil_1", IntelAction.TRUTHFUL)]
        reactions = generate_faction_reactions(gs, world, actions, Faction.IRONVEIL)
        assert reactions[0].affected_characters == ["GeneralKaer"]


# ---------------------------------------------------------------------------
# generate_counter_intel Tests
# ---------------------------------------------------------------------------

class TestGenerateCounterIntel:
    def test_military_truthful_generates_counter_intel(self):
        intel = _make_intel("ch1_mil_1")
        world = _make_world(intel=[intel])
        gs = _make_game_state()
        reaction = FactionReaction(
            id="react_ch1_embercrown_0",
            chapter_generated=1,
            chapter_visible=2,
            acting_faction="embercrown",
            trigger_intel_id="ch1_mil_1",
            trigger_action=IntelAction.TRUTHFUL,
            reaction_type="military_mobilization",
            reaction_description="test",
        )
        ci = generate_counter_intel(reaction, gs, world)
        assert ci is not None
        assert ci.chapter == 2  # Next chapter
        assert ci.source_faction == Faction.IRONVEIL  # Opposing faction observes
        assert ci.verifiability == 4  # Reactions are visible
        assert ci.significance == 2  # Original significance 3 - 1

    def test_personal_truthful_no_counter_intel(self):
        """Personal intel reactions don't generate counter-intel."""
        intel = _make_intel("ch1_personal_1", category=IntelCategory.PERSONAL)
        world = _make_world(intel=[intel])
        gs = _make_game_state()
        reaction = FactionReaction(
            id="react_ch1_embercrown_0",
            chapter_generated=1,
            chapter_visible=2,
            acting_faction="embercrown",
            trigger_intel_id="ch1_personal_1",
            trigger_action=IntelAction.TRUTHFUL,
            reaction_type="internal_investigation",
            reaction_description="test",
        )
        ci = generate_counter_intel(reaction, gs, world)
        assert ci is None

    def test_counter_intel_id_format(self):
        intel = _make_intel("ch1_mil_1")
        world = _make_world(intel=[intel])
        gs = _make_game_state()
        reaction = FactionReaction(
            id="react_ch1_embercrown_0",
            chapter_generated=1,
            chapter_visible=2,
            acting_faction="embercrown",
            trigger_intel_id="ch1_mil_1",
            trigger_action=IntelAction.TRUTHFUL,
            reaction_type="military_mobilization",
            reaction_description="test",
        )
        ci = generate_counter_intel(reaction, gs, world)
        assert ci.id == "ch2_reaction_0"

    def test_significance_floor_at_1(self):
        intel = _make_intel("ch1_mil_1", significance=1)
        world = _make_world(intel=[intel])
        gs = _make_game_state()
        reaction = FactionReaction(
            id="react_ch1_embercrown_0",
            chapter_generated=1,
            chapter_visible=2,
            acting_faction="embercrown",
            trigger_intel_id="ch1_mil_1",
            trigger_action=IntelAction.TRUTHFUL,
            reaction_type="military_mobilization",
            reaction_description="test",
        )
        ci = generate_counter_intel(reaction, gs, world)
        assert ci is not None
        assert ci.significance >= 1


# ---------------------------------------------------------------------------
# evaluate_reaction_outcomes Tests
# ---------------------------------------------------------------------------

class TestEvaluateReactionOutcomes:
    def test_truthful_reactions_never_discovered(self):
        """Reactions based on truthful intel have no failure consequence."""
        intel = _make_intel("ch1_mil_1")
        world = _make_world(intel=[intel])
        gs = _make_game_state(chapter=5)
        reaction = FactionReaction(
            id="react_ch1_embercrown_0",
            chapter_generated=1,
            chapter_visible=2,
            acting_faction="embercrown",
            trigger_intel_id="ch1_mil_1",
            trigger_action=IntelAction.TRUTHFUL,
            reaction_type="military_mobilization",
            reaction_description="test",
            based_on_false_intel=False,
        )
        gs.faction_reactions.append(reaction)
        narratives = evaluate_reaction_outcomes(gs, world)
        assert narratives == []
        assert reaction.outcome_known is False

    def test_already_known_not_rechecked(self):
        intel = _make_intel("ch1_mil_1")
        world = _make_world(intel=[intel])
        gs = _make_game_state(chapter=10)
        reaction = FactionReaction(
            id="react_ch1_embercrown_0",
            chapter_generated=1,
            chapter_visible=2,
            acting_faction="embercrown",
            trigger_intel_id="ch1_mil_1",
            trigger_action=IntelAction.FABRICATED,
            reaction_type="phantom_response",
            reaction_description="test",
            based_on_false_intel=True,
            outcome_known=True,
        )
        gs.faction_reactions.append(reaction)
        narratives = evaluate_reaction_outcomes(gs, world)
        assert narratives == []

    def test_same_chapter_reactions_not_evaluated(self):
        """Reactions from this chapter shouldn't be evaluated yet."""
        intel = _make_intel("ch1_mil_1")
        world = _make_world(intel=[intel])
        gs = _make_game_state(chapter=1)
        reaction = FactionReaction(
            id="react_ch1_embercrown_0",
            chapter_generated=1,
            chapter_visible=2,
            acting_faction="embercrown",
            trigger_intel_id="ch1_mil_1",
            trigger_action=IntelAction.FABRICATED,
            reaction_type="phantom_response",
            reaction_description="test",
            based_on_false_intel=True,
        )
        gs.faction_reactions.append(reaction)
        narratives = evaluate_reaction_outcomes(gs, world)
        assert narratives == []

    def test_discovery_probability_increases_with_time(self):
        """Fabricated reactions should eventually be discovered."""
        intel = _make_intel("ch1_mil_1", significance=5)
        world = _make_world(intel=[intel])

        # Run many times at high chapter count — should discover eventually
        discovered_count = 0
        for trial in range(100):
            gs = _make_game_state(chapter=10, embercrown_trust=50)
            reaction = FactionReaction(
                id=f"react_ch1_embercrown_{trial}",
                chapter_generated=1,
                chapter_visible=2,
                acting_faction="embercrown",
                trigger_intel_id="ch1_mil_1",
                trigger_action=IntelAction.FABRICATED,
                reaction_type="phantom_response",
                reaction_description="test",
                based_on_false_intel=True,
            )
            gs.faction_reactions.append(reaction)
            narratives = evaluate_reaction_outcomes(gs, world)
            if narratives:
                discovered_count += 1

        # With 9 chapters since and high significance, prob = min(0.15*9 + 0.15, 0.90) = 0.90
        # Should discover most of the time
        assert discovered_count > 50, f"Only discovered {discovered_count}/100 times"

    def test_discovery_applies_trust_and_suspicion_penalties(self):
        """When a fabricated military reaction is discovered, trust drops and suspicion rises."""
        intel = _make_intel("ch1_mil_1", significance=3)
        world = _make_world(intel=[intel])
        gs = _make_game_state(chapter=10, embercrown_trust=50, embercrown_suspicion=15)

        # Use a reaction that we know will be discovered (high prob)
        # We need deterministic discovery — run until we find one that triggers
        for trial in range(200):
            gs_copy = _make_game_state(
                chapter=10, embercrown_trust=50, embercrown_suspicion=15
            )
            reaction = FactionReaction(
                id=f"react_ch1_embercrown_{trial}",
                chapter_generated=1,
                chapter_visible=2,
                acting_faction="embercrown",
                trigger_intel_id="ch1_mil_1",
                trigger_action=IntelAction.FABRICATED,
                reaction_type="phantom_response",
                reaction_description="test",
                based_on_false_intel=True,
            )
            gs_copy.faction_reactions.append(reaction)
            narratives = evaluate_reaction_outcomes(gs_copy, world)
            if narratives:
                # Trust should have decreased
                assert gs_copy.embercrown_trust < 50
                # Suspicion should have increased
                assert gs_copy.embercrown_suspicion > 15
                return

        pytest.fail("No discovery occurred in 200 trials — probability too low")


# ---------------------------------------------------------------------------
# apply_reaction_effects Tests
# ---------------------------------------------------------------------------

class TestApplyReactionEffects:
    def test_war_tension_delta_applied(self):
        world = _make_world()
        gs = _make_game_state(war_tension=50)
        reaction = FactionReaction(
            id="react_ch1_embercrown_0",
            chapter_generated=1,
            chapter_visible=2,
            acting_faction="embercrown",
            trigger_intel_id="ch1_mil_1",
            trigger_action=IntelAction.TRUTHFUL,
            reaction_type="military_mobilization",
            reaction_description="test",
            mechanical_effects={"war_tension_delta": 5},
        )
        narratives = apply_reaction_effects(reaction, gs, world)
        assert gs.war_tension == 55

    def test_no_effect_when_zero_delta(self):
        world = _make_world()
        gs = _make_game_state(war_tension=50)
        reaction = FactionReaction(
            id="react_ch1_embercrown_0",
            chapter_generated=1,
            chapter_visible=2,
            acting_faction="embercrown",
            trigger_intel_id="ch1_personal_1",
            trigger_action=IntelAction.TRUTHFUL,
            reaction_type="internal_investigation",
            reaction_description="test",
            mechanical_effects={"war_tension_delta": 0},
        )
        narratives = apply_reaction_effects(reaction, gs, world)
        assert gs.war_tension == 50
        assert narratives == []


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestIntegration:
    def test_full_reaction_flow(self):
        """Report intel → generate reaction → generate counter-intel → verify flow."""
        intel = _make_intel("ch1_mil_1", significance=3)
        world = _make_world(intel=[intel])
        gs = _make_game_state(chapter=1, war_tension=50)

        # Player reports military intel truthfully to Embercrown
        actions = [_make_report_action("ch1_mil_1", IntelAction.TRUTHFUL)]
        reactions = generate_faction_reactions(gs, world, actions, Faction.EMBERCROWN)
        assert len(reactions) == 1

        reaction = reactions[0]
        assert reaction.acting_faction == "embercrown"

        # Apply effects
        apply_reaction_effects(reaction, gs, world)
        assert gs.war_tension == 55  # +5 from military mobilization

        # Generate counter-intel
        ci = generate_counter_intel(reaction, gs, world)
        assert ci is not None
        assert ci.source_faction == Faction.IRONVEIL

        # Add to game state
        gs.faction_reactions.append(reaction)
        gs.dynamic_intel.append(ci)

        # Counter-intel should be in unified map
        m = build_intel_map(world, gs)
        assert ci.id in m

    def test_fabricated_reaction_eventually_discovered(self):
        """Fabricated reactions should be discoverable in later chapters."""
        intel = _make_intel("ch1_mil_1", significance=4)
        world = _make_world(intel=[intel])
        gs = _make_game_state(chapter=1, war_tension=50, embercrown_trust=50)

        # Generate fabricated reaction
        actions = [_make_report_action("ch1_mil_1", IntelAction.FABRICATED)]
        reactions = generate_faction_reactions(gs, world, actions, Faction.EMBERCROWN)
        gs.faction_reactions.extend(reactions)

        # Advance time
        gs.chapter = 5

        # Evaluate — should discover with high probability
        found = False
        for _ in range(50):
            gs_trial = _make_game_state(
                chapter=5, embercrown_trust=50, embercrown_suspicion=15
            )
            gs_trial.faction_reactions = [
                FactionReaction(
                    id=reactions[0].id,
                    chapter_generated=reactions[0].chapter_generated,
                    chapter_visible=reactions[0].chapter_visible,
                    acting_faction=reactions[0].acting_faction,
                    trigger_intel_id=reactions[0].trigger_intel_id,
                    trigger_action=reactions[0].trigger_action,
                    reaction_type=reactions[0].reaction_type,
                    reaction_description=reactions[0].reaction_description,
                    mechanical_effects=reactions[0].mechanical_effects,
                    based_on_false_intel=True,
                )
            ]
            narratives = evaluate_reaction_outcomes(gs_trial, world)
            if narratives:
                found = True
                break

        assert found, "Fabricated reaction was never discovered"

    def test_political_categories(self):
        """Political intel generates diplomatic reactions."""
        intel = _make_intel("ch1_pol_1", category=IntelCategory.POLITICAL)
        world = _make_world(intel=[intel])
        gs = _make_game_state()
        actions = [_make_report_action("ch1_pol_1", IntelAction.TRUTHFUL)]
        reactions = generate_faction_reactions(gs, world, actions, Faction.EMBERCROWN)
        assert len(reactions) == 1
        assert reactions[0].reaction_type == "diplomatic_overture"
        assert reactions[0].mechanical_effects.get("war_tension_delta") == -3

    def test_economic_categories(self):
        intel = _make_intel("ch1_econ_1", category=IntelCategory.ECONOMIC)
        world = _make_world(intel=[intel])
        gs = _make_game_state()
        actions = [_make_report_action("ch1_econ_1", IntelAction.DISTORTED)]
        reactions = generate_faction_reactions(gs, world, actions, Faction.IRONVEIL)
        assert len(reactions) == 1
        assert reactions[0].reaction_type == "resource_misallocation"

    def test_personal_categories(self):
        intel = _make_intel("ch1_pers_1", category=IntelCategory.PERSONAL)
        world = _make_world(intel=[intel])
        gs = _make_game_state()
        actions = [_make_report_action("ch1_pers_1", IntelAction.FABRICATED)]
        reactions = generate_faction_reactions(gs, world, actions, Faction.EMBERCROWN)
        assert len(reactions) == 1
        assert reactions[0].reaction_type == "character_assassination"
