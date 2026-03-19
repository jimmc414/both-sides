"""Deterministic consequence engine — orchestrates trust, tension, and game state."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from config import (
    Faction,
    IntelAction,
    SceneType,
    TRUTH_TAX_MIN_SIGNIFICANCE,
    TRUTH_TAX_TENSION_PER_SIGNIFICANCE,
    WAR_TENSION_START,
    WITHHOLD_TENSION_REDUCTION_PER_SIGNIFICANCE,
)
from trust_system import (
    apply_intel_consequence,
    check_suspicion_threshold,
    get_faction_suspicion,
)
from war_tension import apply_war_tension_change

if TYPE_CHECKING:
    from models import (
        CharacterProfile,
        GameState,
        IntelligencePiece,
        ReportAction,
        WorldState,
    )


def initialize_game_state(world: WorldState) -> GameState:
    """Create initial game state from a generated world."""
    from models import GameState

    state = GameState(
        chapter=1,
        war_tension=WAR_TENSION_START,
        scene_a_faction=Faction.IRONVEIL,
    )

    # Initialize character tracking
    for char in world.characters:
        state.character_trust[char.name] = char.starting_trust
        state.character_suspicion[char.name] = char.starting_suspicion
        state.character_alive[char.name] = True

    # Populate chapter 1 intel
    for intel in world.intelligence_pipeline:
        if intel.chapter == 1:
            state.available_intel.append(intel.id)

    return state


def advance_chapter(game_state: GameState, world: WorldState) -> None:
    """Advance to the next chapter: increment, flip factions, load intel."""
    game_state.chapter += 1

    # Flip which faction the player visits first
    game_state.scene_a_faction = (
        Faction.EMBERCROWN
        if game_state.scene_a_faction == Faction.IRONVEIL
        else Faction.IRONVEIL
    )

    # Populate available intel for the new chapter
    for intel in world.intelligence_pipeline:
        if intel.chapter == game_state.chapter:
            if intel.id not in game_state.available_intel:
                game_state.available_intel.append(intel.id)

    # Also load dynamically generated intel (from faction reactions)
    for intel in game_state.dynamic_intel:
        if intel.chapter == game_state.chapter:
            if intel.id not in game_state.available_intel:
                game_state.available_intel.append(intel.id)


def get_scene_b_faction(game_state: GameState) -> Faction:
    """The faction visited second is the opposite of scene_a."""
    return (
        Faction.EMBERCROWN
        if game_state.scene_a_faction == Faction.IRONVEIL
        else Faction.IRONVEIL
    )


def get_scene_type(
    game_state: GameState, world: WorldState, faction: Faction,
    rng: random.Random | None = None,
) -> SceneType:
    """Determine the scene type based on suspicion and chapter progression."""
    rng = rng or random.Random()
    threshold = check_suspicion_threshold(game_state, faction)

    if threshold in ("investigation", "exposed"):  # 81+
        return SceneType.INTERROGATION if rng.random() < 0.80 else SceneType.PRIVATE_MEETING
    if threshold == "confrontation":  # 71-80
        if rng.random() < 0.60:
            return SceneType.INTERROGATION
        # 40% fall through to normal rotation
    elif threshold == "exclusion":  # 51-70
        return SceneType.PRIVATE_MEETING

    # Rotate through normal scene types by chapter
    normal_scenes = [
        SceneType.WAR_COUNCIL,
        SceneType.FEAST,
        SceneType.FIELD_VISIT,
        SceneType.PRIVATE_MEETING,
        SceneType.WAR_COUNCIL,
    ]
    idx = (game_state.chapter - 1) % len(normal_scenes)
    return normal_scenes[idx]


def get_attending_characters(
    game_state: GameState,
    world: WorldState,
    faction: Faction,
    scene_type: SceneType,
) -> list[CharacterProfile]:
    """Get characters present in a scene. Respects alive/dead and exclusion."""
    faction_chars = [c for c in world.characters if c.faction == faction]
    attending = []

    for char in faction_chars:
        # Skip dead characters
        if not game_state.character_alive.get(char.name, True):
            continue
        attending.append(char)

    # For private meetings, limit to 1-2 characters
    if scene_type == SceneType.PRIVATE_MEETING and len(attending) > 2:
        # Prefer characters with highest trust toward player
        attending.sort(
            key=lambda c: game_state.character_trust.get(c.name, 50),
            reverse=True,
        )
        attending = attending[:2]

    # For interrogation, pick the most suspicious character + spymaster type
    if scene_type == SceneType.INTERROGATION and len(attending) > 2:
        attending.sort(
            key=lambda c: game_state.character_suspicion.get(c.name, 0),
            reverse=True,
        )
        attending = attending[:2]

    return attending


def detect_contradictions(
    game_state: GameState, new_entry_intel_id: str
) -> list[str]:
    """Check if a new ledger entry contradicts previous entries.
    Returns list of contradicting intel IDs."""
    contradictions = []
    new_entry = None
    for e in game_state.ledger_entries:
        if e.intel_id == new_entry_intel_id:
            new_entry = e
            break

    if new_entry is None:
        return contradictions

    for entry in game_state.ledger_entries:
        if entry.intel_id == new_entry_intel_id:
            continue

        # Check cross-faction contradiction: told different things about same topic
        if new_entry.told_ironveil and new_entry.told_embercrown:
            if (
                new_entry.told_ironveil != new_entry.told_embercrown
                and new_entry.action_ironveil != IntelAction.WITHHELD
                and new_entry.action_embercrown != IntelAction.WITHHELD
            ):
                # This is intentional (player chose different stories) — not an error
                pass

        # Check if new entry contradicts a previous entry told to the same faction
        for faction_field, action_field in [
            ("told_ironveil", "action_ironveil"),
            ("told_embercrown", "action_embercrown"),
        ]:
            new_told = getattr(new_entry, faction_field)
            new_action = getattr(new_entry, action_field)
            old_told = getattr(entry, faction_field)
            old_action = getattr(entry, action_field)

            if not new_told or not old_told:
                continue

            # If both entries told the same faction something but the actions
            # suggest they might conflict (one truthful, one fabricated)
            if (
                new_action in (IntelAction.FABRICATED, IntelAction.DISTORTED)
                and old_action == IntelAction.TRUTHFUL
            ) or (
                old_action in (IntelAction.FABRICATED, IntelAction.DISTORTED)
                and new_action == IntelAction.TRUTHFUL
            ):
                contradictions.append(entry.intel_id)

    return contradictions


def evaluate_death_conditions(
    game_state: GameState,
    world: WorldState,
    report_actions: list[ReportAction],
) -> list[str]:
    """Check if any character's death conditions have been triggered.

    A character dies if:
    1. They have non-empty death_conditions
    2. Intel with significance >= 4 related to them was truthfully reported to the opposing faction
    3. They are alive and belong to the intel's source faction
    """
    from trust_system import apply_character_death

    from faction_reactions import build_intel_map as _build_intel_map
    narratives: list[str] = []
    intel_map = _build_intel_map(world, game_state)

    for ra in report_actions:
        if ra.action != IntelAction.TRUTHFUL:
            continue
        intel = intel_map.get(ra.intel_id)
        if intel is None or intel.significance < 4:
            continue

        for char in world.characters:
            if not char.death_conditions:
                continue
            if not game_state.character_alive.get(char.name, True):
                continue
            if char.faction != intel.source_faction:
                continue
            if char.name not in intel.related_characters:
                continue

            # This character's faction's high-significance intel was reported truthfully
            # to the other side — check if this triggers their death condition
            death_narr = apply_character_death(
                game_state, char.name,
                caused_by_faction=(
                    Faction.EMBERCROWN if intel.source_faction == Faction.IRONVEIL
                    else Faction.IRONVEIL
                ),
            )
            narratives.extend(death_narr)

    return narratives


def process_chapter_consequences(
    game_state: GameState,
    world: WorldState,
    report_actions: list[ReportAction],
    verification_results: dict[str, tuple[bool, bool]],
) -> list[str]:
    """Process all consequences for a chapter. Returns narrative descriptions."""
    narratives: list[str] = []
    target_faction = get_scene_b_faction(game_state)

    # Find intel objects by ID
    from faction_reactions import build_intel_map
    intel_map = build_intel_map(world, game_state)

    for ra in report_actions:
        intel = intel_map.get(ra.intel_id)
        if intel is None:
            continue

        was_checked, check_passed = verification_results.get(
            ra.intel_id, (False, None)
        )

        # Apply trust/suspicion consequences
        consequence_narr = apply_intel_consequence(
            game_state, intel, ra.action, target_faction,
            was_checked, check_passed,
        )
        narratives.extend(consequence_narr)

        # Apply war tension effect
        tension_key = ra.action.value
        tension_delta = intel.war_tension_effect.get(tension_key, 0)

        # Truth tax: truthful reports of significant intel accelerate war
        if ra.action == IntelAction.TRUTHFUL and intel.significance >= TRUTH_TAX_MIN_SIGNIFICANCE:
            truth_tax = (intel.significance - TRUTH_TAX_MIN_SIGNIFICANCE + 1) * TRUTH_TAX_TENSION_PER_SIGNIFICANCE
            tension_delta += truth_tax

        # Withholding peace bonus: silence de-escalates tension
        if ra.action == IntelAction.WITHHELD:
            tension_delta += intel.significance * WITHHOLD_TENSION_REDUCTION_PER_SIGNIFICANCE

        if tension_delta:
            tension_narr = apply_war_tension_change(
                game_state, tension_delta,
                source=f"Intel '{intel.id}' reported as {ra.action.value}",
            )
            if tension_narr:
                narratives.append(tension_narr)

        # Update ledger entry
        for entry in game_state.ledger_entries:
            if entry.intel_id == ra.intel_id:
                if target_faction == Faction.IRONVEIL:
                    entry.told_ironveil = ra.player_version or intel.true_content
                    entry.action_ironveil = ra.action
                    entry.verified_ironveil = was_checked
                    entry.verification_result_ironveil = check_passed if was_checked else None
                else:
                    entry.told_embercrown = ra.player_version or intel.true_content
                    entry.action_embercrown = ra.action
                    entry.verified_embercrown = was_checked
                    entry.verification_result_embercrown = check_passed if was_checked else None

                if consequence_narr:
                    entry.consequence = "; ".join(consequence_narr)

                # Detect contradictions
                contras = detect_contradictions(game_state, ra.intel_id)
                entry.contradiction_with = contras
                break

    # Evaluate death conditions
    death_narratives = evaluate_death_conditions(game_state, world, report_actions)
    narratives.extend(death_narratives)

    # Generate faction reactions
    from faction_reactions import (
        generate_faction_reactions,
        apply_reaction_effects,
        generate_counter_intel,
    )

    reactions = generate_faction_reactions(game_state, world, report_actions, target_faction)
    for reaction in reactions:
        effect_narrs = apply_reaction_effects(reaction, game_state, world)
        narratives.extend(effect_narrs)
        game_state.faction_reactions.append(reaction)

        counter_intel = generate_counter_intel(reaction, game_state, world)
        if counter_intel:
            reaction.spawned_intel_id = counter_intel.id
            game_state.dynamic_intel.append(counter_intel)

    # Process wild card events
    for event in world.wild_card_events:
        if event.chapter == game_state.chapter:
            if event.war_tension_effect:
                tension_narr = apply_war_tension_change(
                    game_state, event.war_tension_effect,
                    source=f"Wild card: {event.description[:50]}",
                )
                if tension_narr:
                    narratives.append(tension_narr)
            narratives.append(f"[EVENT] {event.description}")

    return narratives
