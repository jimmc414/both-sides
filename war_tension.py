"""Global war tension tracker."""
from __future__ import annotations

from typing import TYPE_CHECKING

from config import (
    TENSION_DESCRIPTORS,
    WAR_TENSION_PEACE,
    WAR_TENSION_WAR,
    Faction,
    IntelAction,
)

if TYPE_CHECKING:
    from models import GameState, WorldState


def clamp(value: int, lo: int = 0, hi: int = 100) -> int:
    return max(lo, min(hi, value))


def get_tension_descriptor(tension: int) -> tuple[str, str]:
    """Return (label, color) for the current tension level."""
    for lo, hi, label, color in TENSION_DESCRIPTORS:
        if lo <= tension <= hi:
            return label, color
    return "Unknown", "white"


def apply_war_tension_change(
    game_state: GameState, delta: int, source: str = ""
) -> str:
    """Apply a tension change and return a narrative descriptor."""
    old = game_state.war_tension
    game_state.war_tension = clamp(old + delta)
    new = game_state.war_tension

    if delta == 0:
        return ""

    direction = "rises" if delta > 0 else "eases"
    old_label, _ = get_tension_descriptor(old)
    new_label, _ = get_tension_descriptor(new)

    if old_label != new_label:
        msg = f"War tension {direction} from {old_label} to {new_label}"
    else:
        msg = f"War tension {direction} slightly ({new_label})"

    if source:
        msg += f" — {source}"

    return msg


def check_war_state(game_state: GameState) -> str | None:
    """Check if war or peace has been triggered. Returns 'war', 'peace', or None."""
    if game_state.war_tension >= WAR_TENSION_WAR:
        return "war"
    if game_state.war_tension <= WAR_TENSION_PEACE and game_state.chapter >= 5:
        return "peace"
    return None


def determine_war_victor(
    game_state: GameState, world: WorldState | None = None,
) -> str | None:
    """Determine which faction wins the war based on intelligence advantage."""
    if not game_state.war_started:
        return None

    # Build significance lookup
    sig_map: dict[str, int] = {}
    if world:
        for intel in world.intelligence_pipeline:
            sig_map[intel.id] = intel.significance

    ironveil_advantage = 0
    embercrown_advantage = 0

    for entry in game_state.ledger_entries:
        weight = sig_map.get(entry.intel_id, 1)

        if entry.action_ironveil == IntelAction.TRUTHFUL:
            ironveil_advantage += weight
        elif entry.action_ironveil in (IntelAction.FABRICATED, IntelAction.DISTORTED):
            ironveil_advantage -= weight

        if entry.action_embercrown == IntelAction.TRUTHFUL:
            embercrown_advantage += weight
        elif entry.action_embercrown in (IntelAction.FABRICATED, IntelAction.DISTORTED):
            embercrown_advantage -= weight

    if ironveil_advantage > embercrown_advantage:
        return Faction.IRONVEIL.value
    elif embercrown_advantage > ironveil_advantage:
        return Faction.EMBERCROWN.value
    return None  # Mutual destruction
