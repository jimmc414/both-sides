"""Rich terminal UI with dual-faction theming."""
from __future__ import annotations

from typing import TYPE_CHECKING

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text
from rich.theme import Theme
from rich import box

from config import (
    FACTION_COLORS,
    TENSION_DESCRIPTORS,
    Faction,
    IntelAction,
    MAX_CHAPTERS,
)
from trust_system import get_trust_descriptor, get_suspicion_descriptor
from war_tension import get_tension_descriptor

if TYPE_CHECKING:
    from models import GameState


# ──────────────────────────────────────────────
# Theme definitions
# ──────────────────────────────────────────────

IRONVEIL_THEME = Theme({
    "primary": FACTION_COLORS[Faction.IRONVEIL]["primary"],
    "secondary": FACTION_COLORS[Faction.IRONVEIL]["secondary"],
    "faction": "bold " + FACTION_COLORS[Faction.IRONVEIL]["primary"],
})

EMBERCROWN_THEME = Theme({
    "primary": FACTION_COLORS[Faction.EMBERCROWN]["primary"],
    "secondary": FACTION_COLORS[Faction.EMBERCROWN]["secondary"],
    "faction": "bold " + FACTION_COLORS[Faction.EMBERCROWN]["primary"],
})

NEUTRAL_THEME = Theme({
    "primary": "white",
    "secondary": "dim white",
    "faction": "bold white",
})


TITLE_ART = r"""
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║             ██████╗  ██████╗ ████████╗██╗  ██╗           ║
║             ██╔══██╗██╔═══██╗╚══██╔══╝██║  ██║           ║
║             ██████╔╝██║   ██║   ██║   ███████║           ║
║             ██╔══██╗██║   ██║   ██║   ██╔══██║           ║
║             ██████╔╝╚██████╔╝   ██║   ██║  ██║           ║
║             ╚═════╝  ╚═════╝    ╚═╝   ╚═╝  ╚═╝           ║
║                                                          ║
║              ███████╗██╗██████╗ ███████╗███████╗         ║
║              ██╔════╝██║██╔══██╗██╔════╝██╔════╝         ║
║              ███████╗██║██║  ██║█████╗  ███████╗         ║
║              ╚════██║██║██║  ██║██╔══╝  ╚════██║         ║
║              ███████║██║██████╔╝███████╗███████║         ║
║              ╚══════╝╚═╝╚═════╝ ╚══════╝╚══════╝         ║
║                                                          ║
║            A   D O U B L E   A G E N T   G A M E         ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""


class GameDisplay:
    """Rich-based terminal display for the game."""

    def __init__(self):
        self.console = Console()
        self._current_faction: Faction | None = None
        self._logger = None  # Optional GameLogger

    def set_logger(self, logger) -> None:
        """Attach a GameLogger to mirror all output."""
        self._logger = logger

    def set_theme(self, faction: Faction | None) -> None:
        """Switch color palette for the current faction."""
        self._current_faction = faction
        if faction == Faction.IRONVEIL:
            self.console = Console(theme=IRONVEIL_THEME)
        elif faction == Faction.EMBERCROWN:
            self.console = Console(theme=EMBERCROWN_THEME)
        else:
            self.console = Console(theme=NEUTRAL_THEME)

    def _faction_color(self, faction: Faction | None = None) -> str:
        f = faction or self._current_faction
        if f is None:
            return "white"
        return FACTION_COLORS[f]["primary"]

    def _faction_name(self, faction: Faction | None = None) -> str:
        f = faction or self._current_faction
        if f is None:
            return "Neutral"
        return FACTION_COLORS[f]["name"]

    # ── Title Screen ──

    def render_title_screen(self) -> None:
        self.console.clear()
        self.console.print(TITLE_ART, style="bold cyan", justify="center")
        self.console.print()
        self.console.print("[bold][N][/bold] New Game", justify="center")
        self.console.print("[bold][C][/bold] Continue", justify="center")
        self.console.print("[bold][Q][/bold] Quit", justify="center")
        self.console.print()

    # ── HUD ──

    def render_hud(self, game_state: GameState, phase_label: str = "") -> None:
        """Show war tension bar, faction trust/suspicion as descriptors."""
        if self._logger:
            self._logger.log_state(
                chapter=game_state.chapter,
                phase=phase_label,
                war_tension=game_state.war_tension,
                iv_trust=game_state.ironveil_trust,
                iv_susp=game_state.ironveil_suspicion,
                ec_trust=game_state.embercrown_trust,
                ec_susp=game_state.embercrown_suspicion,
            )
        tension_label, tension_color = get_tension_descriptor(game_state.war_tension)

        # Build tension bar
        filled = game_state.war_tension
        bar_text = Text()
        bar_text.append("War Tension: ", style="bold")
        bar_text.append("█" * (filled // 2), style=tension_color)
        bar_text.append("░" * ((100 - filled) // 2), style="dim")
        bar_text.append(f" {filled}% ", style="bold")
        bar_text.append(f"({tension_label})", style=tension_color)

        # Build faction status
        iv_trust = get_trust_descriptor(game_state.ironveil_trust)
        iv_susp = get_suspicion_descriptor(game_state.ironveil_suspicion)
        ec_trust = get_trust_descriptor(game_state.embercrown_trust)
        ec_susp = get_suspicion_descriptor(game_state.embercrown_suspicion)

        # Chapter and phase display
        chapter_text = Text()
        chapter_text.append(f"Chapter {game_state.chapter}/{MAX_CHAPTERS}", style="bold")
        if phase_label:
            chapter_text.append(f" — {phase_label}", style="dim italic")

        # Character death count
        death_count = sum(
            1 for alive in game_state.character_alive.values() if not alive
        )

        table = Table(box=box.SIMPLE, show_header=False, padding=(0, 2))
        table.add_column(justify="left")
        table.add_column(justify="center")
        table.add_column(justify="right")

        table.add_row(
            Text(f"Ironveil: {iv_trust}", style=FACTION_COLORS[Faction.IRONVEIL]["primary"]),
            bar_text,
            Text(f"Embercrown: {ec_trust}", style=FACTION_COLORS[Faction.EMBERCROWN]["primary"]),
        )
        table.add_row(
            Text(f"  Suspicion: {iv_susp}", style="dim"),
            chapter_text,
            Text(f"  Suspicion: {ec_susp}", style="dim"),
        )

        if death_count > 0:
            death_text = Text()
            death_text.append(f"  Deaths: {death_count}", style="bold red")
            table.add_row(
                Text(""),
                death_text,
                Text(""),
            )

        self.console.print()
        self.console.print(Panel(table, border_style="dim"))

    # ── Chapter Briefing ──

    def render_chapter_briefing(self, chapter: int, narrative: str) -> None:
        if self._logger:
            self._logger.section(f"Chapter {chapter} — Briefing")
            self._logger.log(narrative)
        color = self._faction_color()
        self.console.print()
        self.console.print(
            Panel(
                narrative,
                title=f"[bold]Chapter {chapter} — Briefing[/bold]",
                border_style=color,
                padding=(1, 2),
            )
        )

    # ── Conversation ──

    def render_conversation(
        self, speaker: str, text: str, faction: Faction | None = None
    ) -> None:
        if self._logger:
            self._logger.log(f"{speaker}: {text}")
        color = self._faction_color(faction)
        self.console.print()
        self.console.print(f"[bold {color}]{speaker}:[/bold {color}] {text}")

    def render_scene_opening(
        self,
        scene_label: str,
        scene_description: str,
        characters: list[tuple[str, str, str, str, bool]],
        faction: Faction | None = None,
    ) -> None:
        """Show atmospheric scene opening with character standings.

        characters: list of (name, role, trust_desc, suspicion_desc, alive)
        """
        if self._logger:
            self._logger.subsection(scene_label)
            self._logger.log(scene_description)
            self._logger.log("Present:")
            for name, role, trust_desc, susp_desc, alive in characters:
                if alive:
                    self._logger.log(f"  {name} ({role}) — {trust_desc}, {susp_desc}")
            self._logger.blank()

        color = self._faction_color(faction)

        # Character roster with trust/suspicion descriptors
        char_lines = []
        for name, role, trust_desc, susp_desc, alive in characters:
            if not alive:
                continue
            line = f"  [bold]{name}[/bold] ({role}) — {trust_desc}"
            if susp_desc not in ("Unsuspected",):
                line += f", [dim]{susp_desc}[/dim]"
            char_lines.append(line)

        roster = "\n".join(char_lines)

        self.console.print()
        self.console.print(
            Panel(
                f"[italic]{scene_description}[/italic]\n\n"
                f"[bold]Present:[/bold]\n{roster}",
                title=f"[bold]— {scene_label} —[/bold]",
                border_style=color,
                padding=(1, 2),
            )
        )

    def render_conversation_prompt(self, characters_present: list[str]) -> None:
        """Show input prompt with character targeting hints."""
        targets = ", ".join(
            f"[{i+1}] {name}" for i, name in enumerate(characters_present)
        )
        self.console.print()
        self.console.print(
            f"[dim]Address: {targets} | [done] end scene | [board] intel board | [save] | [help][/dim]"
        )

    def render_player_input(self, text: str) -> None:
        if self._logger:
            self._logger.log(f"You: {text}")
        self.console.print(f"\n[bold white]You:[/bold white] {text}")

    # ── Crossover ──

    def render_crossover(self, narrative: str) -> None:
        if self._logger:
            self._logger.subsection("Crossing Over")
            self._logger.log(narrative)
        self.console.print()
        self.console.print(
            Panel(
                narrative,
                title="[bold]— Crossing Over —[/bold]",
                border_style="dim yellow",
                padding=(1, 2),
            )
        )

    # ── Report Builder ──

    def render_report_header(self, target_faction: Faction) -> None:
        name = self._faction_name(target_faction)
        color = FACTION_COLORS[target_faction]["primary"]
        self.console.print()
        self.console.print(
            Panel(
                f"[bold]Preparing your report for {name}[/bold]\n"
                "Decide what to tell them about each piece of intelligence.",
                border_style=color,
            )
        )

    def render_previous_reports(
        self,
        target_faction: Faction,
        previous_entries: list[tuple[str, str, str]],
    ) -> None:
        """Show what was previously told to this faction for consistency tracking.

        previous_entries: list of (intel_id, action_label, told_text)
        """
        if not previous_entries:
            return

        name = self._faction_name(target_faction)
        action_icons = {
            "truthful": "[green]✓[/green]",
            "distorted": "[yellow]⚠[/yellow]",
            "fabricated": "[red]⚠🎲[/red]",
            "withheld": "[dim]—[/dim]",
        }
        lines = []
        for intel_id, action_label, told_text in previous_entries:
            icon = action_icons.get(action_label.lower(), " ")
            lines.append(f"  {icon} [{intel_id}] ({action_label}): {told_text}")

        entries_text = "\n".join(lines)
        self.console.print(
            Panel(
                f"[dim]Previously reported to {name}:[/dim]\n{entries_text}",
                border_style="dim",
                title="[dim]Prior Reports[/dim]",
            )
        )

    def render_intel_for_report(
        self,
        idx: int,
        intel_id: str,
        true_content: str,
        significance: int,
        verifiability: int,
        current_action: IntelAction | None,
    ) -> None:
        sig_bar = "★" * significance + "☆" * (5 - significance)
        ver_bar = "◆" * verifiability + "◇" * (5 - verifiability)

        action_str = f" [{current_action.value.upper()}]" if current_action else ""

        self.console.print(
            Panel(
                f"[bold]{true_content}[/bold]\n\n"
                f"Significance: {sig_bar}  |  Verifiability: {ver_bar}{action_str}",
                title=f"[{idx+1}] {intel_id}",
                border_style="cyan",
            )
        )

    def render_report_actions(self) -> None:
        self.console.print(
            "[dim]  [1] Truthful  [2] Withhold  [3] Distort  [4] Fabricate  [C] Confirm[/dim]"
        )

    def render_risk_assessment(self, risk: str) -> None:
        color = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "red", "EXTREME": "bold red"}.get(
            risk.split(":")[0] if ":" in risk else risk, "white"
        )
        self.console.print(f"  [dim]Risk:[/dim] [{color}]{risk}[/{color}]")

    def render_report_risk_summary(self, actions_with_risk: list[tuple[str, str, str]]) -> None:
        """Show overall risk summary before the player confirms their report.

        actions_with_risk: list of (intel_id, action_label, risk_string)
        """
        self.console.print()
        self.console.print(Panel(
            "[bold]Report Risk Summary[/bold]\n"
            "Review the overall risk of your report before confirming.",
            border_style="yellow",
        ))
        for intel_id, action_label, risk in actions_with_risk:
            risk_level = risk.split(":")[0] if ":" in risk else risk
            color = {"LOW": "green", "MEDIUM": "yellow", "HIGH": "red", "EXTREME": "bold red"}.get(
                risk_level, "white"
            )
            self.console.print(
                f"  {intel_id}: [bold]{action_label}[/bold] — [{color}]{risk}[/{color}]"
            )

    # ── Intelligence Board ──

    def render_intel_board_header(self) -> None:
        self.console.print()
        self.console.print(
            Panel(
                "[bold]Your Intelligence Board[/bold]\n"
                "Review all gathered intelligence and what you've told each side.",
                border_style="cyan",
            )
        )

    def render_intel_board_entry(
        self,
        intel_id: str,
        chapter: int,
        category: str,
        true_content: str,
        told_ironveil: str | None,
        told_embercrown: str | None,
        action_ironveil: IntelAction | None,
        action_embercrown: IntelAction | None,
        verified_ironveil: bool,
        verified_embercrown: bool,
        significance: int = 0,
        verifiability: int = 0,
    ) -> None:
        action_icons = {
            IntelAction.TRUTHFUL: "[green]✓[/green]",
            IntelAction.DISTORTED: "[yellow]⚠[/yellow]",
            IntelAction.FABRICATED: "[red]⚠🎲[/red]",
            IntelAction.WITHHELD: "[dim]—[/dim]",
        }

        iv_icon = action_icons.get(action_ironveil, " ")
        ec_icon = action_icons.get(action_embercrown, " ")

        iv_text = told_ironveil or "[dim]not reported[/dim]"
        ec_text = told_embercrown or "[dim]not reported[/dim]"

        iv_verified = " [bold green]✓V[/bold green]" if verified_ironveil else ""
        ec_verified = " [bold green]✓V[/bold green]" if verified_embercrown else ""

        # Significance and verifiability stars
        rating_line = ""
        if significance > 0 or verifiability > 0:
            sig_bar = "★" * significance + "☆" * (5 - significance)
            ver_bar = "◆" * verifiability + "◇" * (5 - verifiability)
            rating_line = f"  Significance: {sig_bar}  |  Verifiability: {ver_bar}"

        self.console.print(f"\n[bold cyan]{intel_id}[/bold cyan] (Ch{chapter}, {category})")
        self.console.print(f"  [dim]Truth:[/dim] {true_content}")
        if rating_line:
            self.console.print(f"  {rating_line}")
        self.console.print(f"  {iv_icon} Ironveil: {iv_text}{iv_verified}")
        self.console.print(f"  {ec_icon} Embercrown: {ec_text}{ec_verified}")

    def render_intel_board_footer(self) -> None:
        self.console.print()
        self.console.print(
            "[dim]Filters: [M]ilitary [P]olitical [E]conomic [S]ocial/Personal "
            "[H]istory [R]elationships [N]PC Memories [B]ack[/dim]"
        )

    # ── Faction Reactions ──

    def render_faction_reactions(
        self, reactions: list, game_state: GameState
    ) -> None:
        """Show THE WORLD RESPONDS panel with faction actions from previous intel."""
        if self._logger:
            self._logger.subsection("THE WORLD RESPONDS")
            for reaction in reactions:
                self._logger.log(
                    f"  [{reaction.acting_faction.upper()}] "
                    f"{reaction.reaction_description}"
                )
            self._logger.blank()
        lines: list[str] = []
        for reaction in reactions:
            faction_color = self._faction_color(
                Faction.IRONVEIL if reaction.acting_faction == "ironveil"
                else Faction.EMBERCROWN
            )
            faction_label = reaction.acting_faction.upper()
            lines.append(
                f"  [{faction_color}][{faction_label}][/{faction_color}] "
                f"{reaction.reaction_description}"
            )

        body = "\n\n".join(lines)
        self.console.print()
        self.console.print(
            Panel(
                f"[bold cyan]Your intelligence has set events in motion.[/bold cyan]\n\n"
                f"{body}",
                title="[bold cyan]— THE WORLD RESPONDS —[/bold cyan]",
                border_style="bold cyan",
                padding=(1, 2),
            )
        )

    def render_reaction_failure(self, narratives: list[str]) -> None:
        """Show CONSEQUENCES OF DECEPTION panel when false-intel reactions are discovered."""
        if self._logger:
            self._logger.subsection("CONSEQUENCES OF DECEPTION")
            for n in narratives:
                self._logger.log(f"  {n}")
        body = "\n\n".join(f"  {n}" for n in narratives)
        self.console.print()
        self.console.print(
            Panel(
                f"[bold red]Your lies bear bitter fruit.[/bold red]\n\n{body}",
                title="[bold red]— CONSEQUENCES OF DECEPTION —[/bold red]",
                border_style="bold red",
                padding=(1, 2),
            )
        )

    # ── Intel Leaks ──

    def render_leak_discovery(
        self, leak_events: list, game_state: GameState
    ) -> None:
        """Show THE WEB UNRAVELS panel when leaks are discovered."""
        if self._logger:
            self._logger.subsection("THE WEB UNRAVELS")
            for event in leak_events:
                cascade_tag = f" [CASCADE depth {event.cascade_depth}]" if event.is_cascade else ""
                self._logger.log(
                    f"  {event.intel_id} — discovered by "
                    f"{event.discovering_faction} (prob {event.probability:.0%}){cascade_tag}"
                )
        lines: list[str] = []
        for event in leak_events:
            cascade_tag = f" [CASCADE depth {event.cascade_depth}]" if event.is_cascade else ""
            lines.append(
                f"  {event.intel_id} — discovered by {event.discovering_faction}"
                f" (prob {event.probability:.0%}){cascade_tag}"
            )

        body = "\n".join(lines)
        self.console.print()
        self.console.print(
            Panel(
                f"[bold red]Your web of lies begins to unravel.[/bold red]\n\n"
                f"{body}",
                title="[bold red]— THE WEB UNRAVELS —[/bold red]",
                border_style="bold red",
                padding=(1, 2),
            )
        )

    def render_retract_option(self, count: int) -> None:
        """Hint showing how many vulnerable lies could be retracted."""
        self.console.print(
            f"\n[yellow]You have {count} vulnerable lie{'s' if count != 1 else ''} "
            f"that could be retracted. Press [R] during reporting to retract.[/yellow]"
        )

    # ── Chapter Summary ──

    def render_chapter_summary(
        self,
        chapter: int,
        report_actions: list[tuple[str, str, str]],
        trust_deltas: dict[str, tuple[int, int, int]],
        suspicion_deltas: dict[str, tuple[int, int, int]],
        war_tension_before: int,
        war_tension_after: int,
        deaths: list[str],
        leaks: list[str],
    ) -> None:
        """Show end-of-chapter summary with deltas.

        report_actions: list of (intel_id, action_label, target_faction)
        trust_deltas: faction -> (before, after, delta)
        suspicion_deltas: faction -> (before, after, delta)
        deaths: list of character names who died this chapter
        leaks: list of leak descriptions
        """
        if self._logger:
            self._logger.section(f"Chapter {chapter} Summary")
            for intel_id, action_label, target in report_actions:
                self._logger.log(f"  {intel_id} -> {target}: {action_label.upper()}")
            for faction_name, (before, after, delta) in trust_deltas.items():
                sign = "+" if delta >= 0 else ""
                self._logger.log(f"  {faction_name} Trust: {before} -> {after} ({sign}{delta})")
            for faction_name, (before, after, delta) in suspicion_deltas.items():
                sign = "+" if delta >= 0 else ""
                self._logger.log(f"  {faction_name} Suspicion: {before} -> {after} ({sign}{delta})")
            tension_delta = war_tension_after - war_tension_before
            if tension_delta:
                sign = "+" if tension_delta > 0 else ""
                self._logger.log(f"  War Tension: {war_tension_before}% -> {war_tension_after}% ({sign}{tension_delta})")
            for name in deaths:
                self._logger.log(f"  DEATH: {name}")
            for leak in leaks:
                self._logger.log(f"  LEAK: {leak}")

        lines: list[str] = []

        # Intel actions taken
        lines.append("[bold]Intel Actions:[/bold]")
        for intel_id, action_label, target in report_actions:
            action_icons = {
                "truthful": "[green]TRUTH[/green]",
                "distorted": "[yellow]DISTORT[/yellow]",
                "fabricated": "[red]FABRICATE[/red]",
                "withheld": "[dim]WITHHELD[/dim]",
            }
            icon = action_icons.get(action_label.lower(), action_label)
            lines.append(f"  {intel_id} -> {target}: {icon}")

        # Trust/suspicion deltas
        lines.append("\n[bold]Faction Standing:[/bold]")
        for faction_name, (before, after, delta) in trust_deltas.items():
            sign = "+" if delta >= 0 else ""
            color = "green" if delta >= 0 else "red"
            lines.append(
                f"  {faction_name} Trust: {before} -> {after} ([{color}]{sign}{delta}[/{color}])"
            )
        for faction_name, (before, after, delta) in suspicion_deltas.items():
            sign = "+" if delta >= 0 else ""
            color = "red" if delta > 0 else "green"
            lines.append(
                f"  {faction_name} Suspicion: {before} -> {after} ([{color}]{sign}{delta}[/{color}])"
            )

        # War tension
        tension_delta = war_tension_after - war_tension_before
        if tension_delta != 0:
            sign = "+" if tension_delta > 0 else ""
            color = "red" if tension_delta > 0 else "green"
            lines.append(
                f"\n[bold]War Tension:[/bold] {war_tension_before}% -> {war_tension_after}% "
                f"([{color}]{sign}{tension_delta}[/{color}])"
            )

        # Deaths
        if deaths:
            lines.append("\n[bold red]Deaths:[/bold red]")
            for name in deaths:
                lines.append(f"  {name}")

        # Leaks
        if leaks:
            lines.append("\n[bold red]Leaks Discovered:[/bold red]")
            for leak in leaks:
                lines.append(f"  {leak}")

        body = "\n".join(lines)
        self.console.print()
        self.console.print(
            Panel(
                body,
                title=f"[bold]— Chapter {chapter} Summary —[/bold]",
                border_style="cyan",
                padding=(1, 2),
            )
        )

    # ── Fallout ──

    def render_fallout(self, narrative: str) -> None:
        if self._logger:
            self._logger.subsection("Fallout")
            self._logger.log(narrative)
        self.console.print()
        self.console.print(
            Panel(
                narrative,
                title="[bold]— Fallout —[/bold]",
                border_style="red",
                padding=(1, 2),
            )
        )

    # ── Special Sequences ──

    def render_war_outbreak(self) -> None:
        if self._logger:
            self._logger.section("WAR HAS BROKEN OUT")
            self._logger.log(
                "The drums of war echo across Ashenmere. "
                "Armies mobilize on both sides of the border. "
                "Your intelligence — true and false — has shaped this moment."
            )
        self.console.print()
        self.console.print(
            Panel(
                "[bold red]WAR HAS BROKEN OUT[/bold red]\n\n"
                "The drums of war echo across Ashenmere. "
                "Armies mobilize on both sides of the border. "
                "Your intelligence — true and false — has shaped this moment.",
                border_style="bold red",
                padding=(1, 2),
            )
        )

    def render_peace_ceremony(self) -> None:
        if self._logger:
            self._logger.section("PEACE HAS BEEN ACHIEVED")
            self._logger.log(
                "Against all odds, the nations step back from the brink. "
                "Diplomats shake hands in Ashenmere. "
                "Your work in the shadows made this possible — or did it?"
            )
        self.console.print()
        self.console.print(
            Panel(
                "[bold green]PEACE HAS BEEN ACHIEVED[/bold green]\n\n"
                "Against all odds, the nations step back from the brink. "
                "Diplomats shake hands in Ashenmere. "
                "Your work in the shadows made this possible — or did it?",
                border_style="bold green",
                padding=(1, 2),
            )
        )

    # ── Ledger Reveal ──

    def render_ledger_chapter(self, chapter: int, entries_text: str) -> None:
        if self._logger:
            self._logger.subsection(f"Chapter {chapter} — The Truth")
            from game_logger import strip_markup
            self._logger.log(strip_markup(entries_text))
        self.console.print()
        self.console.print(
            Panel(
                entries_text,
                title=f"[bold]Chapter {chapter} — The Truth[/bold]",
                border_style="magenta",
                padding=(1, 2),
            )
        )

    # ── Endings ──

    def render_ending(
        self, political: str, personal: str, narrative: str
    ) -> None:
        if self._logger:
            self._logger.section("EPILOGUE")
            self._logger.log(f"Political Outcome: {political}")
            self._logger.log(f"Personal Fate: {personal}")
            self._logger.blank()
            self._logger.log(narrative)
        self.console.print()
        self.console.print(
            Panel(
                f"[bold]Political Outcome:[/bold] {political}\n"
                f"[bold]Personal Fate:[/bold] {personal}\n\n"
                f"{narrative}",
                title="[bold]— EPILOGUE —[/bold]",
                border_style="bold magenta",
                padding=(1, 2),
            )
        )

    def render_stats(self, stats: dict) -> None:
        """Post-game statistics."""
        if self._logger:
            self._logger.subsection("Your Legacy — Final Statistics")
            for key, val in stats.items():
                self._logger.log(f"  {key}: {val}")
        table = Table(title="Your Legacy", box=box.ROUNDED)
        table.add_column("Stat", style="bold")
        table.add_column("Value", justify="right")
        for key, val in stats.items():
            table.add_row(key, str(val))
        self.console.print()
        self.console.print(table)

    # ── Slip Detection ──

    def render_slip_detected(self, description: str) -> None:
        if self._logger:
            from game_logger import strip_markup
            self._logger.log(f"  [SLIP DETECTED] {strip_markup(description)}")
        self.console.print(
            Panel(
                f"[bold red]Something you said caught attention.[/bold red]\n{description}",
                border_style="red",
                padding=(0, 2),
            )
        )

    # ── Utility ──

    def prompt_input(self, prompt_text: str = "> ") -> str:
        response = self.console.input(f"[bold]{prompt_text}[/bold]")
        if self._logger:
            self._logger.log_player_input(prompt_text, response)
        return response

    def prompt_choice(self, options: list[str]) -> str:
        """Prompt with numbered options, return selected option text."""
        for i, opt in enumerate(options):
            self.console.print(f"  [{i+1}] {opt}")
        while True:
            choice = self.prompt_input()
            try:
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    return options[idx]
            except ValueError:
                # Check if they typed the option text
                for opt in options:
                    if choice.lower() == opt.lower():
                        return opt
            self.console.print("[dim]Invalid choice, try again.[/dim]")

    def show_loading(self, message: str = "Thinking...") -> Progress:
        """Return a Rich Progress context manager with a spinner."""
        return Progress(
            TextColumn(f"[bold cyan]{message}"),
            BarColumn(bar_width=20),
            console=self.console,
            transient=True,
        )

    # ── Tutorial Hints ──

    TUTORIAL_HINTS = {
        "briefing": (
            "[dim italic]HINT: The briefing sets the scene for this chapter. "
            "Pay attention to faction tensions and events — they affect your options.[/dim italic]"
        ),
        "scene_a": (
            "[dim italic]HINT: This is your intel-gathering scene. Talk to NPCs to learn secrets. "
            "What they tell you becomes intel you can report (or distort) to the other side. "
            "Be careful — NPCs remember what you say.[/dim italic]"
        ),
        "crossover": (
            "[dim italic]HINT: Review the Intelligence Board to see what you know. "
            "Then use the Report Builder to decide what to tell the other faction. "
            "Key choices: TRUTH builds trust but can escalate war. "
            "DISTORT gives better rewards but risks detection. "
            "WITHHOLD is safe and reduces war tension. "
            "FABRICATE is high risk, high reward.[/dim italic]"
        ),
        "scene_b": (
            "[dim italic]HINT: You're now delivering your report. "
            "NPCs may question inconsistencies — stay in character.[/dim italic]"
        ),
        "consequences": (
            "[dim italic]HINT: Your reports are now being verified. "
            "If a distortion or fabrication is caught, trust drops and suspicion spikes. "
            "The chapter summary will show exactly what changed.[/dim italic]"
        ),
    }

    def show_tutorial_hint(self, phase: str) -> None:
        """Show a contextual tutorial hint for first-time players."""
        hint = self.TUTORIAL_HINTS.get(phase)
        if hint:
            self.console.print(f"\n{hint}")

    # ── Suspicion Threshold Explanations ──

    THRESHOLD_EXPLANATIONS = {
        "scrutiny": (
            "[yellow]THRESHOLD CROSSED: Scrutiny[/yellow]\n"
            "This faction is watching you more closely. "
            "NPCs will ask probing questions and verify intel more often."
        ),
        "exclusion": (
            "[dark_orange]THRESHOLD CROSSED: Exclusion[/dark_orange]\n"
            "You are excluded from war councils and sensitive meetings. "
            "Only private meetings are available with this faction."
        ),
        "confrontation": (
            "[red]THRESHOLD CROSSED: Confrontation[/red]\n"
            "This faction directly suspects you. "
            "Scenes may become interrogations. Lying is extremely risky."
        ),
        "investigation": (
            "[bold red]THRESHOLD CROSSED: Investigation[/bold red]\n"
            "An active investigation is underway. "
            "Your every word is scrutinized. One more slip and your cover is blown."
        ),
        "exposed": (
            "[bold red]YOUR COVER IS BLOWN[/bold red]\n"
            "This faction has identified you as a double agent. Game over."
        ),
    }

    def render_threshold_crossed(self, threshold_name: str, faction_name: str) -> None:
        """Show explanation when a suspicion threshold is crossed."""
        explanation = self.THRESHOLD_EXPLANATIONS.get(threshold_name)
        if explanation:
            self.console.print()
            self.console.print(
                Panel(
                    explanation,
                    title=f"[bold]{faction_name}[/bold]",
                    border_style="red",
                    padding=(0, 2),
                )
            )

    # ── World Generation Progress ──

    def render_world_gen_progress(self, step: int, total_steps: int, description: str) -> None:
        """Show world generation step progress."""
        bar = "█" * (step * 10 // total_steps) + "░" * (10 - step * 10 // total_steps)
        self.console.print(
            f"\n[bold cyan]World Generation [{step}/{total_steps}][/bold cyan] "
            f"{bar} {description}"
        )

    def render_world_gen_step_complete(self, step: int, description: str, detail: str = "") -> None:
        """Show a completed generation step."""
        suffix = f" — {detail}" if detail else ""
        self.console.print(f"  [green]✓[/green] {description}{suffix}")

    def show_error(self, message: str) -> None:
        self.console.print(f"\n[bold red]Error:[/bold red] {message}")

    def show_message(self, message: str) -> None:
        self.console.print(f"\n{message}")

    def clear(self) -> None:
        self.console.clear()

    def wait_for_enter(self, message: str = "Press Enter to continue...") -> None:
        self.console.input(f"[dim]{message}[/dim]")
