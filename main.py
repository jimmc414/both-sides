"""BOTH SIDES — A Double Agent Strategy Game.

Entry point and chapter loop.
"""
from __future__ import annotations

import asyncio
import signal
import sys
from pathlib import Path

# SDK auth guard
import os
if "ANTHROPIC_API_KEY" in os.environ:
    del os.environ["ANTHROPIC_API_KEY"]

from config import ChapterPhase, DIFFICULTY_MODES, Faction, FACTION_COLORS, IntelAction, MAX_CHAPTERS
from conversation_engine import ConversationManager
from display import GameDisplay
from game_logger import GameLogger
from endings import evaluate_ending, run_ending_scene, show_ledger_reveal
from information_ledger import InformationLedger
from intelligence_board import IntelligenceBoard
from models import GameState, LedgerEntry
from report_builder import ReportBuilder
from saves import auto_save, list_saves, load_game, save_game
from state_machine import (
    advance_chapter,
    get_attending_characters,
    get_scene_b_faction,
    get_scene_type,
    initialize_game_state,
    process_chapter_consequences,
)
from scene_evaluator import SceneEvaluator
from intel_leaks import evaluate_intel_leaks
from verification_engine import run_chapter_verification
from war_tension import check_war_state
from world_generator import generate_world, load_world, save_world

# Globals for signal handler
_display: GameDisplay | None = None
_save_pending: tuple | None = None
_logger: GameLogger | None = None


def _signal_handler(sig, frame):
    """Handle Ctrl+C — offer save before quit."""
    if _logger:
        try:
            _logger.section("SESSION INTERRUPTED (Ctrl+C)")
            _logger.close()
        except Exception:
            pass
    if _display:
        _display.console.print("\n\n[bold yellow]Interrupted![/bold yellow]")
        if _save_pending:
            world, state = _save_pending
            try:
                _display.console.print("[dim]Saving game...[/dim]")
                auto_save(world, state)
                _display.console.print("[green]Game saved.[/green]")
            except Exception:
                pass
        _display.console.print("[dim]Goodbye.[/dim]")
    sys.exit(0)


async def main():
    global _display, _save_pending, _logger

    display = GameDisplay()
    _display = display
    signal.signal(signal.SIGINT, _signal_handler)

    logger = GameLogger()
    _logger = logger
    display.set_logger(logger)
    display.show_message(f"[dim]Session log: {logger.path}[/dim]")

    conversation_mgr = ConversationManager(display)
    scene_evaluator = SceneEvaluator(display)

    # ── Title Screen ──
    world = None
    game_state = None
    ledger = None

    while True:
        display.render_title_screen()
        choice = display.prompt_input("Choose> ").strip().lower()

        if choice in ("n", "1", "new"):
            # Difficulty selection
            display.show_message("\n[bold]Select Difficulty:[/bold]")
            for i, (mode_name, mode_cfg) in enumerate(DIFFICULTY_MODES.items()):
                display.console.print(f"  [{i+1}] {mode_name.title()} — {mode_cfg['description']}")
            diff_choice = display.prompt_input("Difficulty> ").strip().lower()
            difficulty_map = {"1": "novice", "novice": "novice",
                              "2": "standard", "standard": "standard", "": "standard",
                              "3": "spymaster", "spymaster": "spymaster"}
            selected_difficulty = difficulty_map.get(diff_choice, "standard")

            # New game — generate world
            display.show_message("\n[bold]Generating world...[/bold]")
            display.show_message("[dim]This may take a moment while the LLM creates your unique world.[/dim]")

            try:
                world = await generate_world()
                save_world(world, Path("data/world.json"))
                game_state = initialize_game_state(world)
                ledger = InformationLedger()

                # Apply difficulty settings
                diff_cfg = DIFFICULTY_MODES[selected_difficulty]
                game_state.difficulty = selected_difficulty
                game_state.ironveil_trust = diff_cfg["starting_trust"]
                game_state.embercrown_trust = diff_cfg["starting_trust"]
                game_state.ironveil_suspicion = diff_cfg["starting_suspicion"]
                game_state.embercrown_suspicion = diff_cfg["starting_suspicion"]
                game_state.first_chapter_hints = diff_cfg["hints"]

                display.show_message(f"[green]World generated successfully! Difficulty: {selected_difficulty.title()}[/green]")
                logger.section(f"New Game — Difficulty: {selected_difficulty.title()}")
                logger.log(f"Inciting Incident: {world.inciting_incident}")
                logger.log(f"Characters: {', '.join(c.name for c in world.characters)}")
            except Exception as e:
                display.show_error(
                    f"World generation failed: {type(e).__name__}: {e}\n"
                    "[dim]This usually means the LLM service is unavailable or returned "
                    "an unexpected response. Check your connection and try again.\n"
                    "If the problem persists, run 'claude doctor' to verify your "
                    "authentication is working.[/dim]"
                )
                continue

            # Opening narration
            display.show_message("\n[dim]Generating opening narration...[/dim]")
            opening = await conversation_mgr.run_opening(world)
            display.render_chapter_briefing(0, opening)
            display.wait_for_enter()
            break

        elif choice in ("c", "2", "continue"):
            # Load game
            saves = list_saves()
            if not saves:
                display.show_error(
                    "No save files found. Start a new game with [N]."
                )
                continue

            display.show_message("\n[bold]Available Saves:[/bold]")
            for s in saves:
                display.console.print(
                    f"  [{s['slot']}] {s['label']} — Chapter {s['chapter']}, "
                    f"Tension {s['war_tension']}% ({s['timestamp'][:16]})"
                )

            slot_str = display.prompt_input("Load slot> ").strip()
            try:
                slot = int(slot_str)
            except ValueError:
                display.show_error(
                    f"'{slot_str}' is not a valid slot number. "
                    "Enter a number from the list above (e.g., 0 for auto-save)."
                )
                continue

            save_data = load_game(slot)
            if save_data is None:
                display.show_error(
                    f"Could not load slot {slot}. The save file may be missing or "
                    "corrupted. Try a different slot, or start a new game."
                )
                continue

            world = save_data.world_state
            game_state = save_data.game_state
            # Rebuild ledger from game state
            ledger = InformationLedger(list(game_state.ledger_entries))
            display.show_message(
                f"[green]Loaded: Chapter {game_state.chapter}, "
                f"Tension {game_state.war_tension}%[/green]"
            )
            logger.section(f"Loaded Save — Chapter {game_state.chapter}")
            break

        elif choice in ("q", "3", "quit"):
            display.show_message("[dim]Goodbye.[/dim]")
            return
        else:
            display.show_error(
                f"'{choice}' is not a recognized option. "
                "Enter [N] for New Game, [C] to Continue, or [Q] to Quit."
            )
            continue

    # ── Chapter Loop ──
    _save_pending = (world, game_state)
    previous_consequences: list[str] = []

    while game_state.chapter <= MAX_CHAPTERS:
        chapter = game_state.chapter

        # ── Early Termination Checks ──
        war_state = check_war_state(game_state)
        if war_state == "war":
            game_state.war_started = True
            from war_tension import determine_war_victor
            game_state.war_victor = determine_war_victor(game_state, world)
            display.render_war_outbreak()
            display.wait_for_enter()
            break

        if war_state == "peace":
            display.render_peace_ceremony()
            display.wait_for_enter()
            break

        # Check exposure
        if (game_state.ironveil_suspicion >= 100 or
                game_state.embercrown_suspicion >= 100):
            exposed_by = (
                "Ironveil" if game_state.ironveil_suspicion >= 100
                else "Embercrown"
            )
            display.show_message(
                f"\n[bold red]YOUR COVER HAS BEEN BLOWN![/bold red]\n"
                f"The {exposed_by} have discovered your true nature."
            )
            display.wait_for_enter()
            break

        # ── Phase 1: BRIEFING ──
        game_state.phase = ChapterPhase.BRIEFING
        display.set_theme(None)
        display.render_hud(game_state, phase_label="Briefing")

        if game_state.first_chapter_hints:
            display.show_tutorial_hint("briefing")

        # Gather visible faction reactions for this chapter
        visible_reactions = [
            r for r in game_state.faction_reactions
            if r.chapter_visible == game_state.chapter
        ]

        display.show_message(f"\n[dim]Generating Chapter {chapter} briefing...[/dim]")
        briefing = await conversation_mgr.run_briefing(
            game_state, world, previous_consequences, visible_reactions
        )
        display.render_chapter_briefing(chapter, briefing)
        display.wait_for_enter()

        # Show THE WORLD RESPONDS panel if factions took action
        if visible_reactions:
            display.render_faction_reactions(visible_reactions, game_state)
            display.wait_for_enter()

        # ── Faction Visit Order Choice ──
        default_a = game_state.scene_a_faction
        default_b = (
            Faction.EMBERCROWN if default_a == Faction.IRONVEIL else Faction.IRONVEIL
        )
        default_a_name = FACTION_COLORS[default_a]["name"]
        default_b_name = FACTION_COLORS[default_b]["name"]
        display.show_message(
            f"\n[bold]Choose which faction to visit first:[/bold]\n"
            f"  [1] {default_a_name} (default)\n"
            f"  [2] {default_b_name}"
        )
        faction_choice = display.prompt_input("Visit> ").strip()
        if faction_choice == "2":
            game_state.scene_a_faction = default_b

        # ── Phase 2: SCENE A (receive intel) ──
        game_state.phase = ChapterPhase.SCENE_A
        faction_a = game_state.scene_a_faction
        faction_a_name = FACTION_COLORS[faction_a]["name"]
        display.set_theme(faction_a)
        display.render_hud(game_state, phase_label=f"Meeting {faction_a_name}")

        if game_state.first_chapter_hints:
            display.show_tutorial_hint("scene_a")

        scene_type_a = get_scene_type(game_state, world, faction_a)
        characters_a = get_attending_characters(
            game_state, world, faction_a, scene_type_a
        )

        if characters_a:
            display.show_message(f"\n[dim]Entering {faction_a.value} scene...[/dim]")
            conv_log_a = await conversation_mgr.run_scene(
                scene_type=scene_type_a,
                characters=characters_a,
                game_state=game_state,
                world=world,
                ledger=ledger,
                is_delivery_scene=False,
                on_save=lambda: auto_save(world, game_state),
            )
            game_state.conversations.append(conv_log_a)

            # Evaluate scene for memories, slips, and trust changes
            if conv_log_a.exchanges:
                display.show_message("[dim]Analyzing conversation...[/dim]")
                analysis_a = await scene_evaluator.evaluate_scene(
                    conv_log_a, game_state, world, ledger, characters_a
                )
                slip_narratives = scene_evaluator.apply_analysis(analysis_a, game_state)
                for slip in slip_narratives:
                    display.render_slip_detected(slip)
        else:
            display.show_message(
                f"\n[dim]No {faction_a.value} characters available for this scene.[/dim]"
            )
            # Still mark intel as known
            from faction_reactions import build_intel_map as _bim
            _imap = _bim(world, game_state)
            for intel_id in list(game_state.available_intel):
                intel_obj = _imap.get(intel_id)
                if intel_obj and intel_obj.source_faction == faction_a:
                    if intel_id not in game_state.known_intel:
                        game_state.known_intel.append(intel_id)

        # ── Phase 3: CROSSOVER (intel board + report builder) ──
        game_state.phase = ChapterPhase.CROSSOVER
        display.set_theme(None)

        if game_state.first_chapter_hints:
            display.show_tutorial_hint("crossover")

        # Crossover narration
        display.show_message("\n[dim]Generating crossover narration...[/dim]")
        crossover_text = await conversation_mgr.run_crossover(game_state)
        display.render_crossover(crossover_text)
        display.wait_for_enter()

        # Intel board access
        faction_b = get_scene_b_faction(game_state)
        board = IntelligenceBoard(display, game_state, world, ledger)
        display.show_message(
            "\n[bold]Review your intelligence before reporting.[/bold]"
        )
        display.show_message("[dim]Press Enter to open the Intelligence Board, or 'skip' to proceed.[/dim]")
        board_choice = display.prompt_input("> ").strip().lower()
        if board_choice != "skip":
            board.show()

        # Report builder
        display.set_theme(faction_b)
        report_builder = ReportBuilder(
            display=display,
            game_state=game_state,
            world=world,
            ledger=ledger,
            target_faction=faction_b,
        )
        report_actions = report_builder.run()

        # Create ledger entries for each report action
        from faction_reactions import build_intel_map as _build_imap
        _report_imap = _build_imap(world, game_state)
        for ra in report_actions:
            intel_obj = _report_imap.get(ra.intel_id)
            if intel_obj is None:
                continue

            # Check if entry already exists
            existing = ledger.get_entry_by_intel_id(ra.intel_id)
            if existing:
                # Update existing entry for faction B
                if faction_b == Faction.IRONVEIL:
                    existing.told_ironveil = ra.player_version or intel_obj.true_content
                    existing.action_ironveil = ra.action
                else:
                    existing.told_embercrown = ra.player_version or intel_obj.true_content
                    existing.action_embercrown = ra.action

                # Also update distortion/fabrication details on existing entry
                if ra.action == IntelAction.DISTORTED:
                    existing.distortion_details = ra.player_version
                elif ra.action == IntelAction.FABRICATED:
                    existing.fabrication_details = ra.player_version
            else:
                # Create new entry
                entry = LedgerEntry(
                    intel_id=ra.intel_id,
                    chapter=chapter,
                    true_content=intel_obj.true_content,
                )
                if faction_b == Faction.IRONVEIL:
                    entry.told_ironveil = ra.player_version or intel_obj.true_content
                    entry.action_ironveil = ra.action
                else:
                    entry.told_embercrown = ra.player_version or intel_obj.true_content
                    entry.action_embercrown = ra.action

                if ra.action == IntelAction.DISTORTED:
                    entry.distortion_details = ra.player_version
                elif ra.action == IntelAction.FABRICATED:
                    entry.fabrication_details = ra.player_version

                warnings = ledger.add_entry(entry)
                for w in warnings:
                    display.show_message(f"[yellow]Warning: {w}[/yellow]")

                # Also track in game_state
                game_state.ledger_entries.append(entry)

        # ── Phase 4: SCENE B (deliver report) ──
        game_state.phase = ChapterPhase.SCENE_B
        faction_b_name = FACTION_COLORS[faction_b]["name"]
        display.set_theme(faction_b)
        display.render_hud(game_state, phase_label=f"Reporting to {faction_b_name}")

        scene_type_b = get_scene_type(game_state, world, faction_b)
        characters_b = get_attending_characters(
            game_state, world, faction_b, scene_type_b
        )

        if characters_b:
            # Build player report dict for LLM context
            player_report = {}
            for ra in report_actions:
                if ra.action == IntelAction.WITHHELD:
                    continue
                intel_obj = _report_imap.get(ra.intel_id)
                if intel_obj:
                    report_text = ra.player_version or intel_obj.true_content
                    player_report[ra.intel_id] = (
                        f"({ra.action.value}) {report_text}"
                    )

            display.show_message(
                f"\n[dim]Entering {faction_b.value} scene to deliver report...[/dim]"
            )
            conv_log_b = await conversation_mgr.run_scene(
                scene_type=scene_type_b,
                characters=characters_b,
                game_state=game_state,
                world=world,
                ledger=ledger,
                is_delivery_scene=True,
                player_report=player_report,
                on_save=lambda: auto_save(world, game_state),
            )
            game_state.conversations.append(conv_log_b)

            # Evaluate scene for memories, slips, and trust changes
            if conv_log_b.exchanges:
                display.show_message("[dim]Analyzing conversation...[/dim]")
                analysis_b = await scene_evaluator.evaluate_scene(
                    conv_log_b, game_state, world, ledger, characters_b
                )
                slip_narratives = scene_evaluator.apply_analysis(analysis_b, game_state)
                for slip in slip_narratives:
                    display.render_slip_detected(slip)

        # ── Phase 5: CONSEQUENCES ──
        game_state.phase = ChapterPhase.CONSEQUENCES

        # Capture before-state for chapter summary
        iv_trust_before = game_state.ironveil_trust
        ec_trust_before = game_state.embercrown_trust
        iv_susp_before = game_state.ironveil_suspicion
        ec_susp_before = game_state.embercrown_suspicion
        tension_before = game_state.war_tension

        # Run verification
        verification_results = run_chapter_verification(
            game_state, world, ledger, report_actions
        )

        # Mark verified in ledger
        for intel_id, (was_checked, check_passed) in verification_results.items():
            if was_checked:
                ledger.mark_verified(intel_id, faction_b, check_passed)

        # Process consequences
        consequences = process_chapter_consequences(
            game_state, world, report_actions, verification_results
        )

        # ── Evaluate past faction reaction outcomes ──
        from faction_reactions import evaluate_reaction_outcomes
        reaction_outcome_narratives = evaluate_reaction_outcomes(game_state, world)
        if reaction_outcome_narratives:
            display.render_reaction_failure(reaction_outcome_narratives)
            display.wait_for_enter()
        consequences.extend(reaction_outcome_narratives)

        # ── Intel Leak Evaluation (between consequences and fallout) ──
        leak_narratives, leak_events = evaluate_intel_leaks(
            game_state, world, ledger
        )
        consequences.extend(leak_narratives)
        game_state.leak_events.extend(leak_events)

        if leak_events:
            display.render_leak_discovery(leak_events, game_state)
            display.wait_for_enter()

        previous_consequences = consequences

        # ── Phase 6: FALLOUT ──
        game_state.phase = ChapterPhase.FALLOUT
        display.set_theme(None)

        # Collect reactions generated this chapter for fallout context
        chapter_reactions = [
            r for r in game_state.faction_reactions
            if r.chapter_generated == game_state.chapter
        ]

        if consequences:
            display.show_message("\n[dim]Generating fallout...[/dim]")
            fallout_text = await conversation_mgr.run_fallout(
                game_state, consequences, chapter_reactions
            )
            display.render_fallout(fallout_text)

            # Show consequence summary
            display.show_message("\n[bold]Chapter Consequences:[/bold]")
            for c in consequences:
                display.console.print(f"  - {c}")
            display.wait_for_enter()
        else:
            display.show_message("\n[dim]The chapter passes without incident.[/dim]")
            display.wait_for_enter()

        # ── Chapter Summary ──
        summary_actions = []
        for ra in report_actions:
            summary_actions.append((ra.intel_id, ra.action.value, FACTION_COLORS[faction_b]["name"]))

        chapter_deaths = [
            name for name, alive in game_state.character_alive.items()
            if not alive and name not in [
                n for n, a in getattr(game_state, '_prev_alive', {}).items() if not a
            ]
        ]

        chapter_leak_descs = [
            f"{e.intel_id} discovered by {e.discovering_faction}"
            for e in leak_events
        ]

        display.render_chapter_summary(
            chapter=chapter,
            report_actions=summary_actions,
            trust_deltas={
                "Ironveil": (iv_trust_before, game_state.ironveil_trust, game_state.ironveil_trust - iv_trust_before),
                "Embercrown": (ec_trust_before, game_state.embercrown_trust, game_state.embercrown_trust - ec_trust_before),
            },
            suspicion_deltas={
                "Ironveil": (iv_susp_before, game_state.ironveil_suspicion, game_state.ironveil_suspicion - iv_susp_before),
                "Embercrown": (ec_susp_before, game_state.embercrown_suspicion, game_state.embercrown_suspicion - ec_susp_before),
            },
            war_tension_before=tension_before,
            war_tension_after=game_state.war_tension,
            deaths=chapter_deaths,
            leaks=chapter_leak_descs,
        )
        display.wait_for_enter()

        # ── Auto-save between chapters ──
        auto_save(world, game_state)
        display.show_message("[dim]Game auto-saved.[/dim]")

        # Disable tutorial hints after first chapter
        if game_state.first_chapter_hints:
            game_state.first_chapter_hints = False

        # ── Advance to next chapter ──
        if game_state.chapter < MAX_CHAPTERS:
            advance_chapter(game_state, world)
        else:
            break

    # ── Post-Game ──
    display.set_theme(None)
    display.show_message("\n[bold magenta]The game has ended.[/bold magenta]")
    display.wait_for_enter()

    # Ledger reveal
    display.show_message("[dim]Preparing the final reveal...[/dim]")
    await show_ledger_reveal(game_state, ledger, display, conversation_mgr)

    # Ending scene
    await run_ending_scene(game_state, world, ledger, display, conversation_mgr)

    display.show_message("\n[bold]Thank you for playing BOTH SIDES.[/bold]")
    display.show_message("[dim]Your choices mattered. Every one of them.[/dim]\n")

    logger.close()
    display.show_message(f"[dim]Full session log saved to: {logger.path}[/dim]")


if __name__ == "__main__":
    asyncio.run(main())
