"""Ending evaluation and epilogue generation."""
from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from config import Faction, IntelAction
from conversation_engine import ConversationManager
from display import GameDisplay
from information_ledger import InformationLedger
from prompts.summary import build_ending_prompt, build_ledger_reveal_prompt

if TYPE_CHECKING:
    from models import GameState, WorldState


def evaluate_ending(game_state: GameState) -> tuple[str, str]:
    """Evaluate final outcome. Returns (political_outcome, personal_fate)."""
    political = _evaluate_political(game_state)
    personal = _evaluate_personal(game_state)
    return political, personal


def _evaluate_political(game_state: GameState) -> str:
    """Determine the political outcome of the game."""
    if game_state.war_tension <= 20:
        return "Peace — The nations step back from the brink"

    if game_state.war_started and game_state.war_victor:
        if game_state.war_victor == Faction.IRONVEIL.value:
            return "Ironveil Victory — The Compact's armies prevail"
        elif game_state.war_victor == Faction.EMBERCROWN.value:
            return "Embercrown Victory — The Reach's forces triumph"

    if game_state.war_started:
        return "Mutual Destruction — Both nations bleed without end"

    if game_state.war_tension >= 70:
        return "Fragile Standoff — War looms but has not yet broken"

    return "Uncertain Future — The balance holds, for now"


def _evaluate_personal(game_state: GameState) -> str:
    """Determine the player's personal fate."""
    iv_trust = game_state.ironveil_trust
    ec_trust = game_state.embercrown_trust
    iv_susp = game_state.ironveil_suspicion
    ec_susp = game_state.embercrown_suspicion

    # Check each archetype (order matters — most prestigious first)

    # The Architect: masterful double agent, both sides fully trust you
    if iv_trust >= 80 and ec_trust >= 80 and iv_susp <= 20 and ec_susp <= 20:
        return "The Architect — Trusted by all, suspected by none. You shaped the world from the shadows."

    # The Operative: one side's champion, the other's useful asset
    if (iv_trust >= 75 and ec_trust >= 55 and iv_susp <= 35 and ec_susp <= 35):
        return "The Operative — Ironveil's champion, Embercrown's useful asset. You played the great game and won."
    if (ec_trust >= 75 and iv_trust >= 55 and iv_susp <= 35 and ec_susp <= 35):
        return "The Operative — Embercrown's champion, Ironveil's useful asset. You played the great game and won."

    # The Diplomat: genuine bridge between factions
    if iv_trust >= 60 and ec_trust >= 60 and iv_susp <= 35 and ec_susp <= 35:
        return "The Diplomat — Trusted enough to matter, careful enough to survive. You became the bridge between two worlds."

    # The Ghost: low profile, stayed under the radar completely
    if iv_trust >= 45 and ec_trust >= 45 and iv_susp <= 25 and ec_susp <= 25:
        return "The Ghost — You passed through both worlds unseen. No one will remember your name."

    # The Prisoner: exposed and caught
    if (iv_susp >= 70 and ec_susp >= 70) or iv_susp >= 100 or ec_susp >= 100:
        return "The Prisoner — Exposed on all sides. The cell door closes behind you."

    # The Martyr: beloved by one side, condemned by the other
    if (iv_susp >= 60 or ec_susp >= 60) and (iv_trust >= 65 or ec_trust >= 65):
        if iv_susp >= 60 and ec_trust >= 65:
            return "The Martyr — Embercrown's hero, Ironveil's traitor. Your sacrifice will be remembered by one side."
        elif ec_susp >= 60 and iv_trust >= 65:
            return "The Martyr — Ironveil's hero, Embercrown's traitor. Your sacrifice will be remembered by one side."
        return "The Martyr — Beloved by one, condemned by the other."

    # Fallback: leaned toward one side
    if iv_trust > ec_trust:
        return "Ironveil's Agent — In the end, the Compact had more of your loyalty than you realized."
    elif ec_trust > iv_trust:
        return "Embercrown's Agent — In the end, the Reach held your heart more than you admitted."

    return "The Survivor — Neither hero nor villain. You simply endured."


async def run_ending_scene(
    game_state: GameState,
    world: WorldState,
    ledger: InformationLedger,
    display: GameDisplay,
    conversation_mgr: ConversationManager,
) -> None:
    """Generate and display the ending sequence."""
    political, personal = evaluate_ending(game_state)

    # Generate ending narration
    ledger_text = ledger.get_full_history()
    system, user = build_ending_prompt(political, personal, game_state, ledger_text)
    narrative = await conversation_mgr.run_narration(system, user)

    display.render_ending(political, personal, narrative)
    display.wait_for_enter()

    # Post-game stats
    stats = _compute_stats(game_state)
    display.render_stats(stats)
    display.wait_for_enter()


async def show_ledger_reveal(
    game_state: GameState,
    ledger: InformationLedger,
    display: GameDisplay,
    conversation_mgr: ConversationManager,
) -> None:
    """Show chapter-by-chapter ledger reveal with dramatic pacing."""
    display.show_message("\n[bold magenta]— THE TRUTH REVEALED —[/bold magenta]")
    display.show_message("What you did. What they believed. What really happened.\n")
    display.wait_for_enter()

    # Build all chapter texts and prompts upfront
    chapter_data: list[tuple[int, str, str, str]] = []  # (ch, chapter_text, system, user)
    chapters = sorted(set(e.chapter for e in ledger.entries))
    for ch in chapters:
        entries = ledger.get_entries_by_chapter(ch)
        if not entries:
            continue

        # Format entries for this chapter
        entry_lines: list[str] = []
        for entry in entries:
            entry_lines.append(f"Intel: {entry.intel_id}")
            entry_lines.append(f"  Truth: {entry.true_content}")
            if entry.told_ironveil:
                action = entry.action_ironveil.value if entry.action_ironveil else "?"
                entry_lines.append(f"  Told Ironveil ({action}): {entry.told_ironveil}")
            if entry.told_embercrown:
                action = entry.action_embercrown.value if entry.action_embercrown else "?"
                entry_lines.append(f"  Told Embercrown ({action}): {entry.told_embercrown}")
            if entry.consequence:
                entry_lines.append(f"  Result: {entry.consequence}")

        chapter_text = "\n".join(entry_lines)
        system, user = build_ledger_reveal_prompt(ch, chapter_text, game_state)
        chapter_data.append((ch, chapter_text, system, user))

    if not chapter_data:
        return

    # Generate all narrations in parallel
    display.show_message("[dim]Generating reveal narrations...[/dim]")
    narrations = await asyncio.gather(
        *(conversation_mgr.run_narration(system, user)
          for _, _, system, user in chapter_data)
    )

    # Display results sequentially with dramatic pacing
    for (ch, chapter_text, _, _), narration in zip(chapter_data, narrations):
        display.render_ledger_chapter(ch, f"{narration}\n\n{chapter_text}")
        display.wait_for_enter("Press Enter for next chapter...")


def _compute_stats(game_state: GameState) -> dict[str, str]:
    """Compute post-game statistics."""
    truths = 0
    distortions = 0
    fabrications = 0
    withheld = 0

    for entry in game_state.ledger_entries:
        for action in (entry.action_ironveil, entry.action_embercrown):
            if action == IntelAction.TRUTHFUL:
                truths += 1
            elif action == IntelAction.DISTORTED:
                distortions += 1
            elif action == IntelAction.FABRICATED:
                fabrications += 1
            elif action == IntelAction.WITHHELD:
                withheld += 1

    deaths = sum(
        1 for alive in game_state.character_alive.values() if not alive
    )

    # Leak stats
    leak_discoveries = len([
        e for e in game_state.leak_events if not e.is_cascade
    ])
    cascade_discoveries = len([
        e for e in game_state.leak_events if e.is_cascade
    ])
    intel_retracted = sum(
        1 for entry in game_state.ledger_entries
        if entry.retracted_for_ironveil or entry.retracted_for_embercrown
    )

    # Faction reaction stats
    total_reactions = len(game_state.faction_reactions)
    false_reactions = len([
        r for r in game_state.faction_reactions if r.based_on_false_intel
    ])
    discovered_reactions = len([
        r for r in game_state.faction_reactions if r.outcome_known
    ])

    return {
        "Chapters Completed": str(game_state.chapter),
        "Truths Told": str(truths),
        "Distortions Spun": str(distortions),
        "Fabrications Created": str(fabrications),
        "Intel Withheld": str(withheld),
        "Faction Actions Triggered": str(total_reactions),
        "Actions Based on Lies": str(false_reactions),
        "Deceptions Discovered": str(discovered_reactions),
        "Leaks Discovered": str(leak_discoveries),
        "Cascade Discoveries": str(cascade_discoveries),
        "Intel Retracted": str(intel_retracted),
        "Lives Lost": str(deaths),
        "Final War Tension": f"{game_state.war_tension}%",
        "Ironveil Trust": str(game_state.ironveil_trust),
        "Embercrown Trust": str(game_state.embercrown_trust),
    }
