"""Cascading cross-faction intel leak system.

Every lie the player tells is a ticking time bomb. Each chapter, there's a chance
that one faction discovers what the player told the OTHER faction — and if they do,
they re-examine everything, potentially unraveling the player's entire web of deception.
"""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from config import (
    CASCADE_BASE_PROBABILITY,
    CASCADE_ESCALATION_BONUS,
    CASCADE_MAX_DISCOVERIES,
    Faction,
    IntelAction,
    LEAK_BASE_PROBABILITY_PER_CHAPTER,
    LEAK_BETRAYAL_SUSPICION_BONUS,
    LEAK_BETRAYAL_TRUST_PENALTY,
    LEAK_CONTRADICTION_BONUS,
    LEAK_HIGH_SIGNIFICANCE_BONUS,
    LEAK_HIGH_TENSION_BONUS,
    LEAK_PROBABILITY_CAP,
    LEAK_TRUTH_ONE_SIDE_PENALTY,
    LEAK_WAR_TENSION_PER_DISCOVERY,
    RETRACT_SUSPICION_COST,
    RETRACT_TRUST_COST,
)
from trust_system import (
    apply_intel_consequence,
    get_faction_suspicion,
    get_faction_trust,
    set_faction_suspicion,
    set_faction_trust,
)
from war_tension import apply_war_tension_change

if TYPE_CHECKING:
    from information_ledger import InformationLedger
    from models import GameState, IntelligencePiece, LeakEvent, LedgerEntry, WorldState


def get_leakable_entries(
    game_state: GameState,
    ledger: InformationLedger,
) -> list[LedgerEntry]:
    """Find entries where the player told different things to each faction and
    at least one side received a non-truthful version, excluding entries from the
    current chapter, already fully discovered entries, and retracted entries."""
    candidates: list[LedgerEntry] = []
    for entry in ledger.get_cross_faction_discrepancies():
        # Skip current-chapter intel (too fresh to leak)
        if entry.chapter >= game_state.chapter:
            continue

        # Skip if both factions have already discovered the leak
        if (
            Faction.IRONVEIL.value in entry.leak_discovered_by
            and Faction.EMBERCROWN.value in entry.leak_discovered_by
        ):
            continue

        # At least one side must have received a non-truthful version
        has_nontruthful = (
            entry.action_ironveil in (IntelAction.FABRICATED, IntelAction.DISTORTED)
            or entry.action_embercrown in (IntelAction.FABRICATED, IntelAction.DISTORTED)
        )
        if not has_nontruthful:
            continue

        # Skip if retracted for all non-truthful sides
        iv_retracted = (
            entry.retracted_for_ironveil
            if entry.action_ironveil in (IntelAction.FABRICATED, IntelAction.DISTORTED)
            else True  # truthful side doesn't need retraction
        )
        ec_retracted = (
            entry.retracted_for_embercrown
            if entry.action_embercrown in (IntelAction.FABRICATED, IntelAction.DISTORTED)
            else True
        )
        if iv_retracted and ec_retracted:
            continue

        candidates.append(entry)
    return candidates


def calculate_leak_probability(
    entry: LedgerEntry,
    intel: IntelligencePiece | None,
    game_state: GameState,
    ledger: InformationLedger,
) -> float:
    """Compute the leak probability for a single entry this chapter."""
    chapters_since = game_state.chapter - entry.chapter
    probability = LEAK_BASE_PROBABILITY_PER_CHAPTER * chapters_since

    # High war tension bonus
    if game_state.war_tension > 70:
        probability += LEAK_HIGH_TENSION_BONUS

    # Contradiction bonus
    probability += len(entry.contradiction_with) * LEAK_CONTRADICTION_BONUS

    # High significance bonus
    if intel and intel.significance >= 4:
        probability += LEAK_HIGH_SIGNIFICANCE_BONUS

    # Truth on one side penalty (harder to detect when one version is accurate)
    if (
        entry.action_ironveil == IntelAction.TRUTHFUL
        or entry.action_embercrown == IntelAction.TRUTHFUL
    ):
        probability += LEAK_TRUTH_ONE_SIDE_PENALTY

    # Apply difficulty modifier
    from config import DIFFICULTY_MODES
    diff_cfg = DIFFICULTY_MODES.get(getattr(game_state, 'difficulty', 'standard'), DIFFICULTY_MODES['standard'])
    probability *= diff_cfg.get("leak_probability_modifier", 1.0)

    # Clamp to [0, cap]
    return max(0.0, min(probability, LEAK_PROBABILITY_CAP))


def determine_discovering_factions(entry: LedgerEntry) -> list[str]:
    """Determine which faction(s) discover the discrepancy.
    The faction that received the non-truthful version is the one that discovers it.
    If BOTH received non-truthful versions, BOTH discover it."""
    factions: list[str] = []

    if (
        entry.action_ironveil in (IntelAction.FABRICATED, IntelAction.DISTORTED)
        and not entry.retracted_for_ironveil
        and Faction.IRONVEIL.value not in entry.leak_discovered_by
    ):
        factions.append(Faction.IRONVEIL.value)

    if (
        entry.action_embercrown in (IntelAction.FABRICATED, IntelAction.DISTORTED)
        and not entry.retracted_for_embercrown
        and Faction.EMBERCROWN.value not in entry.leak_discovered_by
    ):
        factions.append(Faction.EMBERCROWN.value)

    return factions


def run_leak_roll(
    entry: LedgerEntry,
    intel: IntelligencePiece | None,
    game_state: GameState,
    ledger: InformationLedger,
    rng: random.Random | None = None,
) -> tuple[bool, float, list[str]]:
    """Roll for one entry. Returns (leaked, probability, discovering_factions)."""
    if rng is None:
        rng = random.Random()

    probability = calculate_leak_probability(entry, intel, game_state, ledger)
    if probability <= 0:
        return False, probability, []

    leaked = rng.random() < probability
    if leaked:
        factions = determine_discovering_factions(entry)
        return True, probability, factions

    return False, probability, []


def run_cascade(
    faction: str,
    game_state: GameState,
    world: WorldState,
    ledger: InformationLedger,
    rng: random.Random | None = None,
) -> list[tuple[LedgerEntry, IntelligencePiece | None]]:
    """Re-examine all unchecked non-truthful intel after a discovery.
    Returns list of (entry, intel) pairs that were additionally discovered."""
    if rng is None:
        rng = random.Random()

    faction_enum = Faction(faction)
    candidates = ledger.get_unchecked_nontruthful(faction_enum)

    discoveries: list[tuple[LedgerEntry, IntelligencePiece | None]] = []
    for entry in candidates:
        if len(discoveries) >= CASCADE_MAX_DISCOVERIES:
            break

        cascade_prob = CASCADE_BASE_PROBABILITY + (
            CASCADE_ESCALATION_BONUS * len(discoveries)
        )
        if rng.random() < cascade_prob:
            intel = _find_intel(entry.intel_id, world, game_state)
            discoveries.append((entry, intel))

    return discoveries


def apply_leak_consequences(
    entry: LedgerEntry,
    intel: IntelligencePiece | None,
    faction: str,
    game_state: GameState,
) -> list[str]:
    """Apply mechanical consequences for a leak discovery."""
    narratives: list[str] = []
    faction_enum = Faction(faction)

    # Standard caught-lying consequence
    action_field = f"action_{faction}"
    action = getattr(entry, action_field)
    if intel and action:
        narrs = apply_intel_consequence(
            game_state=game_state,
            intel=intel,
            action=action,
            target_faction=faction_enum,
            was_checked=True,
            check_passed=False,
        )
        narratives.extend(narrs)

    # Additional betrayal modifier (on top of normal consequence)
    old_trust = get_faction_trust(game_state, faction_enum)
    old_suspicion = get_faction_suspicion(game_state, faction_enum)
    set_faction_trust(game_state, faction_enum, old_trust + LEAK_BETRAYAL_TRUST_PENALTY)
    set_faction_suspicion(
        game_state, faction_enum, old_suspicion + LEAK_BETRAYAL_SUSPICION_BONUS
    )
    narratives.append(
        f"The {faction} feel deeply betrayed — trust and confidence shattered."
    )

    # War tension increase
    tension_narr = apply_war_tension_change(
        game_state,
        LEAK_WAR_TENSION_PER_DISCOVERY,
        source=f"Intel leak discovered by {faction}",
    )
    if tension_narr:
        narratives.append(tension_narr)

    # Mark as discovered
    if faction not in entry.leak_discovered_by:
        entry.leak_discovered_by.append(faction)

    return narratives


def evaluate_intel_leaks(
    game_state: GameState,
    world: WorldState,
    ledger: InformationLedger,
    rng: random.Random | None = None,
) -> tuple[list[str], list[LeakEvent]]:
    """Main entry point — run leak rolls and cascades for the current chapter.
    Returns (narratives, leak_events)."""
    from models import LeakEvent

    if rng is None:
        rng = random.Random()

    narratives: list[str] = []
    leak_events: list[LeakEvent] = []

    # Phase 1 & 2: Leak rolls
    leakable = get_leakable_entries(game_state, ledger)
    initial_discoveries: list[tuple[LedgerEntry, IntelligencePiece | None, str]] = []

    for entry in leakable:
        intel = _find_intel(entry.intel_id, world, game_state)
        leaked, probability, factions = run_leak_roll(
            entry, intel, game_state, ledger, rng
        )
        if leaked:
            for faction in factions:
                initial_discoveries.append((entry, intel, faction))
                leak_events.append(
                    LeakEvent(
                        chapter=game_state.chapter,
                        intel_id=entry.intel_id,
                        discovering_faction=faction,
                        probability=probability,
                        is_cascade=False,
                        cascade_depth=0,
                    )
                )

    # Phase 3: Cascade for each discovering faction
    cascade_factions: set[str] = set()
    for _, _, faction in initial_discoveries:
        cascade_factions.add(faction)

    for faction in cascade_factions:
        cascade_discoveries = run_cascade(faction, game_state, world, ledger, rng)
        for c_entry, c_intel in cascade_discoveries:
            depth = 1 + cascade_discoveries.index((c_entry, c_intel))
            leak_events.append(
                LeakEvent(
                    chapter=game_state.chapter,
                    intel_id=c_entry.intel_id,
                    discovering_faction=faction,
                    probability=CASCADE_BASE_PROBABILITY,
                    is_cascade=True,
                    cascade_depth=depth,
                )
            )
            initial_discoveries.append((c_entry, c_intel, faction))

    # Phase 4: Consequences
    for entry, intel, faction in initial_discoveries:
        narrs = apply_leak_consequences(entry, intel, faction, game_state)
        narratives.extend(narrs)

    return narratives, leak_events


def apply_retraction(
    entry: LedgerEntry,
    target_faction: Faction,
    game_state: GameState,
) -> list[str]:
    """Handle voluntary retraction of a past lie. Returns narrative descriptions."""
    narratives: list[str] = []

    action_field = f"action_{target_faction.value}"
    action = getattr(entry, action_field)

    # Can only retract non-truthful, non-withheld, non-already-retracted, non-discovered
    if action not in (IntelAction.FABRICATED, IntelAction.DISTORTED):
        return narratives

    retracted_field = f"retracted_for_{target_faction.value}"
    if getattr(entry, retracted_field):
        return narratives

    if target_faction.value in entry.leak_discovered_by:
        return narratives

    # Apply retraction cost
    old_trust = get_faction_trust(game_state, target_faction)
    old_suspicion = get_faction_suspicion(game_state, target_faction)
    set_faction_trust(game_state, target_faction, old_trust + RETRACT_TRUST_COST)
    set_faction_suspicion(game_state, target_faction, old_suspicion + RETRACT_SUSPICION_COST)

    # Mark as retracted
    setattr(entry, retracted_field, True)

    narratives.append(
        f"You admit to {target_faction.value} that your earlier report on "
        f"{entry.intel_id} was... not entirely accurate. "
        f"Trust suffers, but the ticking bomb is defused."
    )
    return narratives


def get_retractable_entries(
    game_state: GameState,
    ledger: InformationLedger,
    target_faction: Faction,
) -> list[LedgerEntry]:
    """Find entries the player can retract for a given faction."""
    action_field = f"action_{target_faction.value}"
    retracted_field = f"retracted_for_{target_faction.value}"
    results: list[LedgerEntry] = []
    for entry in ledger.entries:
        action = getattr(entry, action_field)
        if action not in (IntelAction.FABRICATED, IntelAction.DISTORTED):
            continue
        if getattr(entry, retracted_field):
            continue
        if target_faction.value in entry.leak_discovered_by:
            continue
        results.append(entry)
    return results


def _find_intel(
    intel_id: str, world: WorldState, game_state: GameState | None = None,
) -> IntelligencePiece | None:
    """Look up an intel piece by ID from the world's pipeline + dynamic intel."""
    for i in world.intelligence_pipeline:
        if i.id == intel_id:
            return i
    if game_state is not None:
        for i in game_state.dynamic_intel:
            if i.id == intel_id:
                return i
    return None
