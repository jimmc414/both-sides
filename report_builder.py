"""Structured reporting interface — player decides what to tell each faction."""
from __future__ import annotations

from typing import TYPE_CHECKING

from config import (
    Faction,
    IntelAction,
    TRUTH_TAX_MIN_SIGNIFICANCE,
    TRUTH_TAX_TENSION_PER_SIGNIFICANCE,
    WITHHOLD_TENSION_REDUCTION_PER_SIGNIFICANCE,
)
from display import GameDisplay
from information_ledger import InformationLedger
from intel_leaks import apply_retraction, get_retractable_entries
from models import ReportAction
from verification_engine import calculate_verification_probability

if TYPE_CHECKING:
    from models import GameState, IntelligencePiece, WorldState


class ReportBuilder:
    """Interactive report building — no LLM, pure game mechanics."""

    def __init__(
        self,
        display: GameDisplay,
        game_state: GameState,
        world: WorldState,
        ledger: InformationLedger,
        target_faction: Faction,
    ):
        self.display = display
        self.game_state = game_state
        self.world = world
        self.ledger = ledger
        self.target_faction = target_faction

        # Collect intel pieces available for reporting:
        # - Current chapter intel (fresh)
        # - Previous chapter intel that hasn't been reported to this faction yet
        self.intel_pieces: list[IntelligencePiece] = []
        self.stale_intel_ids: set[str] = set()  # Track stale intel for penalty display
        from faction_reactions import build_intel_map
        _intel_map = build_intel_map(world, game_state)
        for intel_id in game_state.known_intel:
            intel = _intel_map.get(intel_id)
            if intel is None:
                continue

            # Check if already reported to the target faction
            existing_entry = ledger.get_entry_by_intel_id(intel_id)
            faction_action_field = f"action_{target_faction.value}"
            if existing_entry and getattr(existing_entry, faction_action_field) is not None:
                continue  # Already reported to this faction

            self.intel_pieces.append(intel)
            if intel.chapter < game_state.chapter:
                self.stale_intel_ids.add(intel.id)

        self.actions: dict[str, ReportAction] = {}

    def run(self) -> list[ReportAction]:
        """Run the interactive report builder. Returns list of ReportActions."""
        self.display.render_report_header(self.target_faction)

        # Show previously reported intel for consistency tracking
        prev_entries = self.ledger.get_entries_for_faction(self.target_faction)
        if prev_entries:
            previous_data = []
            for entry in prev_entries:
                action_field = f"action_{self.target_faction.value}"
                told_field = f"told_{self.target_faction.value}"
                action = getattr(entry, action_field)
                told = getattr(entry, told_field)
                if action and told:
                    previous_data.append(
                        (entry.intel_id, action.value, told)
                    )
            self.display.render_previous_reports(
                self.target_faction, previous_data
            )

        if not self.intel_pieces:
            self.display.show_message("No intelligence to report this chapter.")
            return []

        # Show each intel piece with action options, verification %, and tension effects
        for idx, intel in enumerate(self.intel_pieces):
            current_action = self.actions.get(intel.id)
            stale_tag = ""
            if intel.id in self.stale_intel_ids:
                age = self.game_state.chapter - intel.chapter
                stale_tag = f" [STALE Ch{intel.chapter}, +{age * 10}% verify risk, {max(1, 100 - age * 50)}% trust]"

            # Calculate verification probability
            verify_prob = calculate_verification_probability(
                intel, IntelAction.TRUTHFUL, self.game_state, self.ledger, self.target_faction,
            )

            # War tension effects
            tension_effects = []
            for act_name, act_val in [("truth", IntelAction.TRUTHFUL), ("distort", IntelAction.DISTORTED),
                                       ("fabricate", IntelAction.FABRICATED), ("withhold", IntelAction.WITHHELD)]:
                t_delta = intel.war_tension_effect.get(act_val.value, 0)
                if act_val == IntelAction.TRUTHFUL and intel.significance >= TRUTH_TAX_MIN_SIGNIFICANCE:
                    t_delta += (intel.significance - TRUTH_TAX_MIN_SIGNIFICANCE + 1) * TRUTH_TAX_TENSION_PER_SIGNIFICANCE
                if act_val == IntelAction.WITHHELD:
                    t_delta += intel.significance * WITHHOLD_TENSION_REDUCTION_PER_SIGNIFICANCE
                if t_delta != 0:
                    sign = "+" if t_delta > 0 else ""
                    tension_effects.append(f"{act_name}:{sign}{t_delta}")

            extra_info = f"\n  Verify: {verify_prob:.0%}"
            if tension_effects:
                extra_info += f"  |  Tension: {', '.join(tension_effects)}"

            self.display.render_intel_for_report(
                idx=idx,
                intel_id=intel.id,
                true_content=intel.true_content + stale_tag + extra_info,
                significance=intel.significance,
                verifiability=intel.verifiability,
                current_action=current_action.action if current_action else None,
            )

        # Show retractable entries hint
        retractable = get_retractable_entries(
            self.game_state, self.ledger, self.target_faction
        )
        if retractable:
            self.display.render_retract_option(len(retractable))

        # Interactive action selection loop
        while True:
            self.display.render_report_actions()
            self.display.show_message(
                "Select intel number then action, [R] to retract a past lie, or [C] to confirm report."
            )

            for idx, intel in enumerate(self.intel_pieces):
                action = self.actions.get(intel.id)
                status = f" -> {action.action.value.upper()}" if action else " -> [not set]"
                self.display.console.print(
                    f"  [{idx+1}] {intel.id}{status}"
                )

            choice = self.display.prompt_input("Report> ").strip().lower()

            if choice in ("r", "retract", "[r]"):
                self._handle_retract()
                continue

            if choice in ("c", "confirm", "[c]"):
                # Check all intel has been assigned an action
                unset = [
                    i for i in self.intel_pieces if i.id not in self.actions
                ]
                if unset:
                    # Default unset to WITHHELD
                    for intel in unset:
                        self.actions[intel.id] = ReportAction(
                            intel_id=intel.id,
                            action=IntelAction.WITHHELD,
                            risk_assessment=self.compute_risk(intel, IntelAction.WITHHELD),
                        )

                # Show overall risk summary before final confirmation
                risk_items = []
                for intel in self.intel_pieces:
                    action = self.actions.get(intel.id)
                    if action:
                        risk_items.append(
                            (intel.id, action.action.value, action.risk_assessment)
                        )
                self.display.render_report_risk_summary(risk_items)

                # Final confirmation after seeing the risk summary
                confirm = self.display.prompt_input(
                    "Submit this report? [Y]es / [N]o > "
                ).strip().lower()
                if confirm in ("n", "no"):
                    continue
                break

            # Parse "1 2" meaning intel 1, action 2 (withhold)
            parts = choice.split()
            if len(parts) == 2:
                try:
                    intel_idx = int(parts[0]) - 1
                    action_num = int(parts[1])
                except ValueError:
                    self.display.show_error(
                        "Enter two numbers separated by a space: <intel#> <action#>. "
                        "Example: '1 3' to distort intel #1. Or [C] to confirm."
                    )
                    continue

                if not (0 <= intel_idx < len(self.intel_pieces)):
                    self.display.show_error(
                        f"Intel number must be between 1 and {len(self.intel_pieces)}."
                    )
                    continue

                intel = self.intel_pieces[intel_idx]
                action = self._num_to_action(action_num)
                if action is None:
                    self.display.show_error("Action: 1=Truthful, 2=Withhold, 3=Distort, 4=Fabricate")
                    continue

                player_version = None
                if action in (IntelAction.DISTORTED, IntelAction.FABRICATED):
                    if action == IntelAction.DISTORTED and intel.distortion_suggestions:
                        self.display.show_message("Distortion suggestions:")
                        for i, sug in enumerate(intel.distortion_suggestions):
                            self.display.console.print(f"  [{i+1}] {sug}")
                        self.display.show_message("Enter your version (or pick a number):")
                    else:
                        self.display.show_message(
                            f"Enter your {'distorted' if action == IntelAction.DISTORTED else 'fabricated'} version:"
                        )
                    player_version = self.display.prompt_input("Version> ").strip()

                    # Check if they picked a suggestion number
                    if (
                        action == IntelAction.DISTORTED
                        and intel.distortion_suggestions
                        and player_version.isdigit()
                    ):
                        sug_idx = int(player_version) - 1
                        if 0 <= sug_idx < len(intel.distortion_suggestions):
                            player_version = intel.distortion_suggestions[sug_idx]

                risk = self.compute_risk(intel, action)
                self.actions[intel.id] = ReportAction(
                    intel_id=intel.id,
                    action=action,
                    player_version=player_version,
                    risk_assessment=risk,
                )

                self.display.render_risk_assessment(risk)

            elif len(parts) == 1 and parts[0].isdigit():
                # Just selected an intel piece — show it
                try:
                    intel_idx = int(parts[0]) - 1
                    if 0 <= intel_idx < len(self.intel_pieces):
                        intel = self.intel_pieces[intel_idx]
                        current = self.actions.get(intel.id)
                        self.display.render_intel_for_report(
                            idx=intel_idx,
                            intel_id=intel.id,
                            true_content=intel.true_content,
                            significance=intel.significance,
                            verifiability=intel.verifiability,
                            current_action=current.action if current else None,
                        )
                        # Show previous entries for contradiction checking
                        prev = self.ledger.get_entries_for_faction(self.target_faction)
                        if prev:
                            self.display.show_message("Previous reports to this faction:")
                            for entry in prev[-3:]:
                                told = getattr(entry, f"told_{self.target_faction.value}")
                                self.display.console.print(f"  [{entry.intel_id}] {told}")
                except ValueError:
                    pass
            else:
                self.display.show_error(
                    "Unrecognized input. Enter '<intel#> <action#>' (e.g. '1 2' to withhold intel #1), "
                    "a single number to inspect intel, or [C] to confirm."
                )

        return list(self.actions.values())

    def compute_risk(self, intel: IntelligencePiece, action: IntelAction) -> str:
        """Compute risk assessment string for an action."""
        if action == IntelAction.TRUTHFUL:
            if intel.id in self.stale_intel_ids:
                age = self.game_state.chapter - intel.chapter
                return f"LOW: Truth is safe but stale (trust reduced {age * 50}%)"
            return "LOW: Truth is always safe"
        if action == IntelAction.WITHHELD:
            return "LOW: Silence de-escalates tension"

        # Base risk from verifiability
        base = intel.verifiability * 15  # 15-75%

        # Fabrication is riskier than distortion
        if action == IntelAction.FABRICATED:
            base += 20

        # Stale intel is riskier to lie about
        if intel.id in self.stale_intel_ids:
            age = self.game_state.chapter - intel.chapter
            base += age * 10

        # Check unchecked fabrications
        unchecked = self.ledger.get_unchecked_fabrications(self.target_faction)
        base += len(unchecked) * 10

        # Suspicion adds risk
        suspicion = (
            self.game_state.ironveil_suspicion
            if self.target_faction == Faction.IRONVEIL
            else self.game_state.embercrown_suspicion
        )
        if suspicion > 30:
            base += (suspicion - 30) // 3

        if base >= 70:
            level = "EXTREME"
        elif base >= 50:
            level = "HIGH"
        elif base >= 30:
            level = "MEDIUM"
        else:
            level = "LOW"

        details = f"Verifiability {intel.verifiability}/5"
        if intel.id in self.stale_intel_ids:
            age = self.game_state.chapter - intel.chapter
            details += f", stale ({age} ch old)"
        if unchecked:
            details += f", {len(unchecked)} unchecked lies"
        if suspicion > 30:
            details += f", suspicion {suspicion}%"

        return f"{level}: {details}"

    def _handle_retract(self) -> None:
        """Let the player retract a past lie."""
        retractable = get_retractable_entries(
            self.game_state, self.ledger, self.target_faction
        )
        if not retractable:
            self.display.show_message(
                "[dim]No lies available to retract for this faction.[/dim]"
            )
            return

        self.display.show_message(
            "\n[bold yellow]RETRACT A PAST LIE[/bold yellow]\n"
            "Admit a past deception. Cost: -5 trust, +5 suspicion. "
            "But the intel is removed from the leak pool permanently.\n"
        )
        for i, entry in enumerate(retractable):
            action_field = f"action_{self.target_faction.value}"
            told_field = f"told_{self.target_faction.value}"
            action = getattr(entry, action_field)
            told = getattr(entry, told_field)
            self.display.console.print(
                f"  [{i+1}] {entry.intel_id} (Ch{entry.chapter}, {action.value}): {told}"
            )

        self.display.show_message("[dim]Enter number to retract, or [B]ack.[/dim]")
        pick = self.display.prompt_input("Retract> ").strip().lower()
        if pick in ("b", "back", "[b]"):
            return

        try:
            idx = int(pick) - 1
            if 0 <= idx < len(retractable):
                entry = retractable[idx]
                narratives = apply_retraction(
                    entry, self.target_faction, self.game_state
                )
                for narr in narratives:
                    self.display.show_message(f"[yellow]{narr}[/yellow]")
            else:
                self.display.show_error(
                    f"Number must be between 1 and {len(retractable)}."
                )
        except ValueError:
            self.display.show_error("Enter a number or [B]ack.")

    @staticmethod
    def _num_to_action(num: int) -> IntelAction | None:
        return {
            1: IntelAction.TRUTHFUL,
            2: IntelAction.WITHHELD,
            3: IntelAction.DISTORTED,
            4: IntelAction.FABRICATED,
        }.get(num)
