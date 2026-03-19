"""Verification engine — probability rolls on fabrications and distortions."""
from __future__ import annotations

import random
from typing import TYPE_CHECKING

from config import Faction, IntelAction
from information_ledger import InformationLedger

if TYPE_CHECKING:
    from models import GameState, IntelligencePiece, ReportAction, WorldState
    from trust_system import get_faction_suspicion


def calculate_verification_probability(
    intel: IntelligencePiece,
    action: IntelAction,
    game_state: GameState,
    ledger: InformationLedger,
    target_faction: Faction,
) -> float:
    """Calculate probability that this intel gets checked.

    Returns float in [0.0, 0.95].
    """
    if action == IntelAction.WITHHELD:
        return 0.0  # Nothing to verify

    # Base probability (adjusted by difficulty mode)
    from config import DIFFICULTY_MODES
    diff_cfg = DIFFICULTY_MODES.get(getattr(game_state, 'difficulty', 'standard'), DIFFICULTY_MODES['standard'])
    prob = 0.20 + diff_cfg.get("verification_rate_modifier", 0.0)

    # Verifiability modifier: +0.05 per point above 2
    if intel.verifiability > 2:
        prob += (intel.verifiability - 2) * 0.05

    # Spymaster suspicion modifier
    from trust_system import get_faction_suspicion as _get_susp
    suspicion = _get_susp(game_state, target_faction)
    if suspicion > 30:
        prob += (suspicion - 30) * 0.005  # +0.5% per point above 30

    # Category modifier: military intel is checked more often
    if intel.category.value == "military":
        prob += 0.05
    elif intel.category.value == "personal":
        prob -= 0.05

    # Cumulative risk: unchecked fabrications raise scrutiny
    unchecked = ledger.get_unchecked_fabrications(target_faction)
    prob += len(unchecked) * 0.05

    # Significance modifier
    if intel.significance >= 4:
        prob += 0.10
    elif intel.significance >= 3:
        prob += 0.05

    # Stale intel penalty: +10% per chapter of age
    if intel.chapter < game_state.chapter:
        age = game_state.chapter - intel.chapter
        prob += age * 0.10

    return max(0.0, min(0.95, prob))


def run_verification(
    intel: IntelligencePiece,
    action: IntelAction,
    probability: float,
    rng: random.Random | None = None,
) -> tuple[bool, bool | None]:
    """Roll for verification.

    Returns (was_checked, check_passed).
    check_passed is None if not checked.
    """
    if action == IntelAction.WITHHELD:
        return False, None

    rng = rng or random.Random()

    # Roll to see if it gets checked at all
    was_checked = rng.random() < probability
    if not was_checked:
        return False, None

    # If checked, determine outcome by action type
    if action == IntelAction.TRUTHFUL:
        return True, True  # Truth always passes
    elif action == IntelAction.FABRICATED:
        return True, False  # Fabrication always fails when checked
    elif action == IntelAction.DISTORTED:
        # Catch rate scales with verifiability: 0.3 + (verifiability * 0.1)
        # Low-verifiability distortions (ver 1: 40%) are safer than high (ver 5: 80%)
        catch_rate = 0.3 + (intel.verifiability * 0.1)
        return True, rng.random() >= catch_rate

    return False, None


def run_chapter_verification(
    game_state: GameState,
    world: WorldState,
    ledger: InformationLedger,
    report_actions: list[ReportAction],
    rng: random.Random | None = None,
) -> dict[str, tuple[bool, bool | None]]:
    """Run verification for all report actions in a chapter.

    Returns dict mapping intel_id to (was_checked, check_passed).
    """
    rng = rng or random.Random()
    results: dict[str, tuple[bool, bool | None]] = {}

    # Determine target faction (scene B faction)
    from state_machine import get_scene_b_faction
    target_faction = get_scene_b_faction(game_state)

    from faction_reactions import build_intel_map
    intel_map = build_intel_map(world, game_state)

    for ra in report_actions:
        intel = intel_map.get(ra.intel_id)
        if intel is None:
            results[ra.intel_id] = (False, None)
            continue

        prob = calculate_verification_probability(
            intel, ra.action, game_state, ledger, target_faction
        )
        was_checked, check_passed = run_verification(
            intel, ra.action, prob, rng
        )
        results[ra.intel_id] = (was_checked, check_passed)

    return results
