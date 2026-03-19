"""Faction reaction system — factions take visible actions based on player intel."""
from __future__ import annotations

import hashlib
import random
from typing import TYPE_CHECKING

from config import Faction, IntelAction, IntelCategory

if TYPE_CHECKING:
    from models import FactionReaction, GameState, IntelligencePiece, ReportAction, WorldState


# ──────────────────────────────────────────────
# Reaction Template Table
# ──────────────────────────────────────────────
# Maps (IntelCategory, IntelAction) → list of templates.
# Each template: reaction_type, description, effects, npc_summary,
#   counter_intel_template (or None), failure_consequence.

REACTION_TEMPLATES: dict[tuple[IntelCategory, IntelAction], list[dict]] = {
    # ── MILITARY ──
    (IntelCategory.MILITARY, IntelAction.TRUTHFUL): [
        {
            "reaction_type": "military_mobilization",
            "description": (
                "{acting_faction_name} has mobilized forces along the border in response "
                "to confirmed intelligence about {other_faction_name}'s military activities."
            ),
            "effects": {"war_tension_delta": 5},
            "npc_summary": "We mobilized forces to the border based on your report.",
            "counter_intel_template": (
                "{other_faction_name} scouts report unusual troop movements by "
                "{acting_faction_name} along the southern border."
            ),
            "failure_consequence": None,
        },
    ],
    (IntelCategory.MILITARY, IntelAction.DISTORTED): [
        {
            "reaction_type": "misdirected_deployment",
            "description": (
                "{acting_faction_name} has redeployed forces to an unexpected sector, "
                "acting on intelligence about {other_faction_name}'s military movements — "
                "intelligence that was not entirely accurate."
            ),
            "effects": {"war_tension_delta": 3},
            "npc_summary": "We redeployed forces based on your intelligence about their movements.",
            "counter_intel_template": (
                "{other_faction_name} observers note confusing troop movements by "
                "{acting_faction_name} — forces repositioning to an unexpected location."
            ),
            "failure_consequence": {"trust_delta": -8, "suspicion_delta": 12},
        },
    ],
    (IntelCategory.MILITARY, IntelAction.FABRICATED): [
        {
            "reaction_type": "phantom_response",
            "description": (
                "{acting_faction_name} has scrambled a significant force to counter "
                "a reported {other_faction_name} military buildup — a buildup that "
                "does not exist."
            ),
            "effects": {"war_tension_delta": 7},
            "npc_summary": "We mobilized a full response to the threat you reported.",
            "counter_intel_template": (
                "{other_faction_name} intelligence is alarmed — {acting_faction_name} "
                "has mobilized forces for no apparent reason."
            ),
            "failure_consequence": {"trust_delta": -15, "suspicion_delta": 20},
        },
    ],

    # ── POLITICAL ──
    (IntelCategory.POLITICAL, IntelAction.TRUTHFUL): [
        {
            "reaction_type": "diplomatic_overture",
            "description": (
                "{acting_faction_name} has dispatched diplomatic envoys, acting on "
                "accurate intelligence about {other_faction_name}'s political situation."
            ),
            "effects": {"war_tension_delta": -3},
            "npc_summary": "We sent envoys to Ashenmere based on your political intelligence.",
            "counter_intel_template": (
                "{other_faction_name} observers have spotted {acting_faction_name} "
                "envoys traveling through Ashenmere."
            ),
            "failure_consequence": None,
        },
    ],
    (IntelCategory.POLITICAL, IntelAction.DISTORTED): [
        {
            "reaction_type": "diplomatic_miscalculation",
            "description": (
                "{acting_faction_name} has taken a diplomatic position based on "
                "intelligence about {other_faction_name}'s political stance — "
                "a position that may prove embarrassingly wrong."
            ),
            "effects": {"war_tension_delta": 2},
            "npc_summary": "We adjusted our diplomatic approach based on your report.",
            "counter_intel_template": (
                "{other_faction_name} diplomats are puzzled by {acting_faction_name}'s "
                "recent overtures — their assumptions seem oddly misaligned."
            ),
            "failure_consequence": {"trust_delta": -6, "suspicion_delta": 10},
        },
    ],
    (IntelCategory.POLITICAL, IntelAction.FABRICATED): [
        {
            "reaction_type": "wrongful_arrest",
            "description": (
                "{acting_faction_name} has arrested suspected {other_faction_name} "
                "sympathizers within their ranks, acting on fabricated intelligence "
                "about a political conspiracy."
            ),
            "effects": {"war_tension_delta": 0},
            "npc_summary": "We purged the suspected conspirators you warned us about.",
            "counter_intel_template": (
                "{other_faction_name} intelligence notes an internal purge within "
                "{acting_faction_name}'s government — arrests without clear cause."
            ),
            "failure_consequence": {"trust_delta": -12, "suspicion_delta": 18},
        },
    ],

    # ── ECONOMIC ──
    (IntelCategory.ECONOMIC, IntelAction.TRUTHFUL): [
        {
            "reaction_type": "trade_adjustment",
            "description": (
                "{acting_faction_name} has adjusted trade routes and supply chains "
                "in response to confirmed economic intelligence about {other_faction_name}."
            ),
            "effects": {"war_tension_delta": 1},
            "npc_summary": "We restructured supply lines based on your economic intelligence.",
            "counter_intel_template": (
                "{other_faction_name} merchants report disruptions — {acting_faction_name} "
                "has altered its trade patterns."
            ),
            "failure_consequence": None,
        },
    ],
    (IntelCategory.ECONOMIC, IntelAction.DISTORTED): [
        {
            "reaction_type": "resource_misallocation",
            "description": (
                "{acting_faction_name} has redirected resources to the wrong areas, "
                "misled by distorted economic intelligence about {other_faction_name}."
            ),
            "effects": {"war_tension_delta": 1},
            "npc_summary": "We redirected stockpiles based on your intelligence.",
            "counter_intel_template": (
                "{other_faction_name} traders notice {acting_faction_name} stockpiling "
                "resources in unexpected locations."
            ),
            "failure_consequence": {"trust_delta": -5, "suspicion_delta": 8},
        },
    ],
    (IntelCategory.ECONOMIC, IntelAction.FABRICATED): [
        {
            "reaction_type": "economic_sabotage",
            "description": (
                "{acting_faction_name} has launched economic countermeasures against "
                "a nonexistent {other_faction_name} trade scheme, wasting precious "
                "resources on a phantom threat."
            ),
            "effects": {"war_tension_delta": 3},
            "npc_summary": "We acted on your warning about their economic schemes.",
            "counter_intel_template": (
                "{other_faction_name} is bewildered by {acting_faction_name}'s sudden "
                "trade embargo on goods that were flowing normally."
            ),
            "failure_consequence": {"trust_delta": -10, "suspicion_delta": 15},
        },
    ],

    # ── PERSONAL ──
    (IntelCategory.PERSONAL, IntelAction.TRUTHFUL): [
        {
            "reaction_type": "internal_investigation",
            "description": (
                "{acting_faction_name} has quietly opened an internal investigation "
                "based on personal intelligence you provided."
            ),
            "effects": {"war_tension_delta": 0},
            "npc_summary": "We looked into the personal matter you reported.",
            "counter_intel_template": None,
            "failure_consequence": None,
        },
    ],
    (IntelCategory.PERSONAL, IntelAction.DISTORTED): [
        {
            "reaction_type": "misplaced_suspicion",
            "description": (
                "{acting_faction_name} has begun watching one of their own more closely, "
                "based on a distorted account of personal dealings."
            ),
            "effects": {"war_tension_delta": 0},
            "npc_summary": "We've been keeping a closer eye on certain individuals, thanks to your tip.",
            "counter_intel_template": None,
            "failure_consequence": {"trust_delta": -4, "suspicion_delta": 6},
        },
    ],
    (IntelCategory.PERSONAL, IntelAction.FABRICATED): [
        {
            "reaction_type": "character_assassination",
            "description": (
                "{acting_faction_name} has moved against one of their own, acting on "
                "fabricated personal intelligence that branded them a liability."
            ),
            "effects": {"war_tension_delta": 0},
            "npc_summary": "We dealt with the individual you warned us about.",
            "counter_intel_template": None,
            "failure_consequence": {"trust_delta": -10, "suspicion_delta": 14},
        },
    ],
}

# Cap reactions per chapter to avoid overwhelming the player
MAX_REACTIONS_PER_CHAPTER = 3


# ──────────────────────────────────────────────
# Intel Lookup Unification
# ──────────────────────────────────────────────

def build_intel_map(
    world: WorldState, game_state: GameState
) -> dict[str, IntelligencePiece]:
    """Build unified intel map from world pipeline + dynamic intel."""
    m = {i.id: i for i in world.intelligence_pipeline}
    for i in game_state.dynamic_intel:
        m[i.id] = i
    return m


# ──────────────────────────────────────────────
# Faction name helpers
# ──────────────────────────────────────────────

_FACTION_DISPLAY = {
    "ironveil": "The Ironveil Compact",
    "embercrown": "The Embercrown Reach",
}

def _other_faction(faction_value: str) -> str:
    return "embercrown" if faction_value == "ironveil" else "ironveil"


# ──────────────────────────────────────────────
# Core functions
# ──────────────────────────────────────────────

def generate_faction_reactions(
    game_state: GameState,
    world: WorldState,
    report_actions: list[ReportAction],
    target_faction: Faction,
) -> list[FactionReaction]:
    """Generate faction reactions based on what the player reported.

    The target_faction is the faction that received the report (scene B faction).
    They will react to the intel they were given.
    """
    from models import FactionReaction

    intel_map = build_intel_map(world, game_state)
    reactions: list[FactionReaction] = []
    seq = 0

    for ra in report_actions:
        if ra.action == IntelAction.WITHHELD:
            continue

        intel = intel_map.get(ra.intel_id)
        if intel is None:
            continue

        # Don't generate reactions from counter-intel to avoid feedback loops
        if ra.intel_id.startswith("ch") and "_reaction_" in ra.intel_id:
            continue

        key = (intel.category, ra.action)
        templates = REACTION_TEMPLATES.get(key)
        if not templates:
            continue

        # Select template — higher significance picks last (stronger) template
        template_idx = min(intel.significance - 1, len(templates) - 1)
        template = templates[max(0, template_idx)]

        acting_faction = target_faction.value
        other_faction = _other_faction(acting_faction)
        acting_name = _FACTION_DISPLAY.get(acting_faction, acting_faction)
        other_name = _FACTION_DISPLAY.get(other_faction, other_faction)

        # Pick an affected character from related_characters if available
        affected_char = ""
        affected_chars_list: list[str] = []
        if intel.related_characters:
            affected_char = intel.related_characters[0]
            affected_chars_list = list(intel.related_characters)

        description = template["description"].format(
            acting_faction_name=acting_name,
            other_faction_name=other_name,
            intel_summary=intel.true_content[:80],
            affected_character=affected_char,
        )

        npc_summary = template["npc_summary"]
        based_on_false = ra.action in (IntelAction.DISTORTED, IntelAction.FABRICATED)

        reaction = FactionReaction(
            id=f"react_ch{game_state.chapter}_{acting_faction}_{seq}",
            chapter_generated=game_state.chapter,
            chapter_visible=game_state.chapter + 1,
            acting_faction=acting_faction,
            trigger_intel_id=ra.intel_id,
            trigger_action=ra.action,
            reaction_type=template["reaction_type"],
            reaction_description=description,
            mechanical_effects=dict(template.get("effects", {})),
            based_on_false_intel=based_on_false,
            affected_characters=affected_chars_list,
            narrative_for_npcs=npc_summary,
        )
        reactions.append(reaction)
        seq += 1

        if len(reactions) >= MAX_REACTIONS_PER_CHAPTER:
            break

    return reactions


def generate_counter_intel(
    reaction: FactionReaction,
    game_state: GameState,
    world: WorldState,
) -> IntelligencePiece | None:
    """Generate a new intel piece visible to the opposing faction from a reaction.

    The opposing faction observes the reaction and generates new intel.
    """
    from models import IntelligencePiece

    intel_map = build_intel_map(world, game_state)
    original = intel_map.get(reaction.trigger_intel_id)
    if original is None:
        return None

    # Look up the template for the counter_intel_template
    key = (original.category, reaction.trigger_action)
    templates = REACTION_TEMPLATES.get(key)
    if not templates:
        return None

    template_idx = min(original.significance - 1, len(templates) - 1)
    template = templates[max(0, template_idx)]

    counter_template = template.get("counter_intel_template")
    if not counter_template:
        return None

    acting_name = _FACTION_DISPLAY.get(reaction.acting_faction, reaction.acting_faction)
    other_faction = _other_faction(reaction.acting_faction)
    other_name = _FACTION_DISPLAY.get(other_faction, other_faction)

    counter_text = counter_template.format(
        acting_faction_name=acting_name,
        other_faction_name=other_name,
    )

    # Count existing dynamic intel to generate unique seq
    existing_reaction_intel = [
        i for i in game_state.dynamic_intel
        if i.id.startswith(f"ch{game_state.chapter + 1}_reaction_")
    ]
    seq = len(existing_reaction_intel)

    new_significance = max(1, original.significance - 1)
    source_faction = (
        Faction.EMBERCROWN if reaction.acting_faction == "ironveil" else Faction.IRONVEIL
    )

    counter_intel = IntelligencePiece(
        id=f"ch{game_state.chapter + 1}_reaction_{seq}",
        chapter=game_state.chapter + 1,
        source_faction=source_faction,
        true_content=counter_text,
        significance=new_significance,
        verifiability=4,  # reactions are visible
        category=original.category,
        war_tension_effect={
            "truthful": 1,
            "distorted": 0,
            "fabricated": 0,
            "withheld": -1,
        },
    )
    return counter_intel


def evaluate_reaction_outcomes(
    game_state: GameState,
    world: WorldState,
) -> list[str]:
    """Check past false-intel reactions for discovery.

    Each chapter, reactions based on false intel have an increasing
    chance of being discovered. Uses deterministic RNG seeded by
    reaction.id + chapter for reproducibility.
    """
    from trust_system import (
        get_faction_trust,
        get_faction_suspicion,
        set_faction_trust,
        set_faction_suspicion,
    )

    narratives: list[str] = []
    intel_map = build_intel_map(world, game_state)

    for reaction in game_state.faction_reactions:
        if not reaction.based_on_false_intel:
            continue
        if reaction.outcome_known:
            continue
        if reaction.retroactive_suspicion_applied:
            continue

        chapters_since = game_state.chapter - reaction.chapter_generated
        if chapters_since < 1:
            continue

        # Base discovery probability: 15% per chapter since generation
        discovery_prob = 0.15 * chapters_since

        # Bonus for high-significance intel
        original = intel_map.get(reaction.trigger_intel_id)
        if original and original.significance >= 4:
            discovery_prob += 0.15

        discovery_prob = min(discovery_prob, 0.90)

        # Deterministic RNG for reproducibility
        seed = hashlib.sha256(
            f"{reaction.id}:{game_state.chapter}".encode()
        ).hexdigest()
        rng = random.Random(seed)

        if rng.random() < discovery_prob:
            reaction.outcome_known = True
            reaction.retroactive_suspicion_applied = True

            # Look up failure consequences from template
            if original:
                key = (original.category, reaction.trigger_action)
                templates = REACTION_TEMPLATES.get(key, [])
                if templates:
                    template_idx = min(original.significance - 1, len(templates) - 1)
                    template = templates[max(0, template_idx)]
                    failure = template.get("failure_consequence")
                    if failure:
                        faction = Faction(reaction.acting_faction)
                        trust_delta = failure.get("trust_delta", 0)
                        susp_delta = failure.get("suspicion_delta", 0)

                        if trust_delta:
                            old = get_faction_trust(game_state, faction)
                            set_faction_trust(game_state, faction, old + trust_delta)
                        if susp_delta:
                            old = get_faction_suspicion(game_state, faction)
                            set_faction_suspicion(game_state, faction, old + susp_delta)

            acting_name = _FACTION_DISPLAY.get(
                reaction.acting_faction, reaction.acting_faction
            )
            narratives.append(
                f"{acting_name} has discovered that their response "
                f"'{reaction.reaction_type.replace('_', ' ')}' was based on "
                f"{'fabricated' if reaction.trigger_action == IntelAction.FABRICATED else 'distorted'} "
                f"intelligence. Trust has been severely damaged."
            )

    return narratives


def apply_reaction_effects(
    reaction: FactionReaction,
    game_state: GameState,
    world: WorldState,
) -> list[str]:
    """Apply mechanical effects from a reaction (war tension changes, etc.)."""
    from war_tension import apply_war_tension_change

    narratives: list[str] = []
    effects = reaction.mechanical_effects

    tension_delta = effects.get("war_tension_delta", 0)
    if tension_delta:
        narr = apply_war_tension_change(
            game_state, tension_delta,
            source=f"Faction reaction: {reaction.reaction_type}",
        )
        if narr:
            narratives.append(narr)

    return narratives
