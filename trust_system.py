"""Trust and suspicion tracking system."""
from __future__ import annotations

from typing import TYPE_CHECKING

from config import (
    CONSEQUENCE_TABLE,
    SUSPICION_THRESHOLDS,
    TRUST_DESCRIPTORS,
    Faction,
    IntelAction,
)

if TYPE_CHECKING:
    from models import CharacterProfile, GameState, IntelligencePiece


def clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, value))


def get_trust_descriptor(trust: int) -> str:
    for lo, hi, label in TRUST_DESCRIPTORS:
        if lo <= trust <= hi:
            return label
    return "Unknown"


def get_suspicion_descriptor(suspicion: int) -> str:
    if suspicion <= 15:
        return "Unsuspected"
    elif suspicion <= 30:
        return "Watched"
    elif suspicion <= 50:
        return "Under Scrutiny"
    elif suspicion <= 70:
        return "Suspected"
    elif suspicion <= 85:
        return "Investigated"
    else:
        return "Exposed"


def get_faction_trust(game_state: GameState, faction: Faction) -> int:
    if faction == Faction.IRONVEIL:
        return game_state.ironveil_trust
    return game_state.embercrown_trust


def get_faction_suspicion(game_state: GameState, faction: Faction) -> int:
    if faction == Faction.IRONVEIL:
        return game_state.ironveil_suspicion
    return game_state.embercrown_suspicion


def set_faction_trust(game_state: GameState, faction: Faction, value: int) -> None:
    value = clamp(value)
    if faction == Faction.IRONVEIL:
        game_state.ironveil_trust = value
    else:
        game_state.embercrown_trust = value


def set_faction_suspicion(game_state: GameState, faction: Faction, value: int) -> None:
    value = clamp(value)
    if faction == Faction.IRONVEIL:
        game_state.ironveil_suspicion = value
    else:
        game_state.embercrown_suspicion = value


def apply_intel_consequence(
    game_state: GameState,
    intel: IntelligencePiece,
    action: IntelAction,
    target_faction: Faction,
    was_checked: bool,
    check_passed: bool | None,
    receiving_character: str | None = None,
) -> list[str]:
    """Apply consequences of an intel action. Returns narrative descriptions."""
    narratives: list[str] = []

    # Look up consequence in table
    if was_checked:
        key = (action, True, check_passed)
    else:
        key = (action, False, None)

    consequence = CONSEQUENCE_TABLE.get(key)
    if consequence is None:
        return narratives

    trust_delta = consequence["trust"]
    suspicion_delta = consequence["suspicion"]
    desc = consequence["desc"]

    # Scale by significance
    sig_multiplier = 0.5 + (intel.significance * 0.2)  # 0.7 to 1.5
    trust_delta = int(trust_delta * sig_multiplier)
    suspicion_delta = int(suspicion_delta * sig_multiplier)

    # Stale intel penalty: trust gains reduced by 50% per chapter of delay
    if intel.chapter < game_state.chapter and trust_delta > 0:
        age = game_state.chapter - intel.chapter
        decay = max(0.1, 1.0 - (age * 0.5))  # Floor at 10% of original value
        trust_delta = max(1, int(trust_delta * decay))
        if age >= 1:
            desc += f" (intel {age} chapter{'s' if age > 1 else ''} old — reduced impact)"

    # Apply faction-level changes
    old_trust = get_faction_trust(game_state, target_faction)
    old_suspicion = get_faction_suspicion(game_state, target_faction)
    set_faction_trust(game_state, target_faction, old_trust + trust_delta)
    set_faction_suspicion(game_state, target_faction, old_suspicion + suspicion_delta)

    narratives.append(desc)

    # Apply character-level changes if a specific character received the intel
    if receiving_character and receiving_character in game_state.character_trust:
        old_char_trust = game_state.character_trust[receiving_character]
        old_char_suspicion = game_state.character_suspicion[receiving_character]
        game_state.character_trust[receiving_character] = clamp(
            old_char_trust + trust_delta
        )
        game_state.character_suspicion[receiving_character] = clamp(
            old_char_suspicion + suspicion_delta
        )

    # Check for threshold events
    threshold_event = check_suspicion_threshold(game_state, target_faction)
    if threshold_event:
        narratives.append(f"[THRESHOLD] {target_faction.value}: {threshold_event}")

    return narratives


def apply_character_death(
    game_state: GameState,
    character_name: str,
    caused_by_faction: Faction | None = None,
) -> list[str]:
    """Mark a character as dead and generate narrative + mechanical consequences."""
    narratives: list[str] = []

    if character_name not in game_state.character_alive:
        return narratives

    if not game_state.character_alive[character_name]:
        return narratives  # Already dead

    game_state.character_alive[character_name] = False
    narratives.append(f"{character_name} has been killed.")

    if caused_by_faction:
        # The victim's faction is the OTHER one (enemy kills them)
        victim_faction = (
            Faction.EMBERCROWN
            if caused_by_faction == Faction.IRONVEIL
            else Faction.IRONVEIL
        )
        narratives.append(f"Killed by {caused_by_faction.value} agents.")

        # War tension rises from the death
        from war_tension import apply_war_tension_change
        tension_narr = apply_war_tension_change(
            game_state, +7,
            source=f"Death of {character_name}",
        )
        if tension_narr:
            narratives.append(tension_narr)

        # Victim's faction becomes more suspicious of everyone (including player)
        old_susp = get_faction_suspicion(game_state, victim_faction)
        if old_susp >= 40:
            set_faction_suspicion(game_state, victim_faction, old_susp + 5)
            narratives.append(
                f"The {victim_faction.value} tighten security after the loss."
            )

        # If the player was close to the dead character, trust drops
        char_trust = game_state.character_trust.get(character_name, 50)
        if char_trust >= 60:
            old_faction_trust = get_faction_trust(game_state, victim_faction)
            set_faction_trust(game_state, victim_faction, old_faction_trust - 3)
            narratives.append(
                f"The {victim_faction.value} mourn — your closeness to the deceased is noted."
            )

    return narratives


def check_suspicion_threshold(
    game_state: GameState, faction: Faction
) -> str | None:
    """Check if suspicion has crossed a threshold. Returns event name or None."""
    suspicion = get_faction_suspicion(game_state, faction)

    # Return the highest threshold crossed
    result = None
    for threshold, event_name in sorted(SUSPICION_THRESHOLDS.items()):
        if suspicion >= threshold:
            result = event_name
    return result
