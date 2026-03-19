"""Player's intel management view — interactive board showing all gathered intelligence."""
from __future__ import annotations

from typing import TYPE_CHECKING

from config import Faction, IntelCategory
from display import GameDisplay
from information_ledger import InformationLedger
from trust_system import get_trust_descriptor

if TYPE_CHECKING:
    from models import GameState, WorldState


class IntelligenceBoard:
    """Interactive intelligence board for reviewing gathered intel."""

    def __init__(
        self,
        display: GameDisplay,
        game_state: GameState,
        world: WorldState,
        ledger: InformationLedger,
    ):
        self.display = display
        self.game_state = game_state
        self.world = world
        self.ledger = ledger

    def show(self) -> None:
        """Run the interactive intelligence board."""
        current_filter: IntelCategory | None = None

        while True:
            self.display.render_intel_board_header()
            self._render_entries(current_filter)
            self._render_contradictions()
            self.display.render_intel_board_footer()

            choice = self.display.prompt_input("Board> ").strip().lower()

            if choice in ("b", "back", "[b]"):
                break
            elif choice in ("m", "[m]"):
                current_filter = IntelCategory.MILITARY
            elif choice in ("p", "[p]"):
                current_filter = IntelCategory.POLITICAL
            elif choice in ("e", "[e]"):
                current_filter = IntelCategory.ECONOMIC
            elif choice in ("s", "[s]"):
                current_filter = IntelCategory.PERSONAL
            elif choice in ("h", "[h]"):
                self._show_history()
            elif choice in ("r", "[r]"):
                self._show_relationships()
            elif choice in ("n", "[n]"):
                self._show_npc_memories()
            elif choice == "":
                current_filter = None  # Reset filter
            else:
                self.display.show_error(
                    "Commands: [M]ilitary [P]olitical [E]conomic [S]ocial "
                    "[H]istory [R]elationships [N]PC Memories [B]ack"
                )

    def _render_entries(self, category_filter: IntelCategory | None) -> None:
        """Render intel entries, optionally filtered by category.

        Shows both already-reported ledger entries AND pending (known but
        unreported) intel from game_state.known_intel.
        """
        entries = self.ledger.entries

        # Get intel objects for category info (includes dynamic intel from reactions)
        from faction_reactions import build_intel_map
        intel_map = build_intel_map(self.world, self.game_state)

        # Track which intel IDs already have ledger entries
        ledger_intel_ids = {entry.intel_id for entry in entries}
        has_any = False

        # Render existing ledger entries
        for entry in entries:
            intel = intel_map.get(entry.intel_id)
            if intel is None:
                continue

            if category_filter and intel.category != category_filter:
                continue

            has_any = True
            self.display.render_intel_board_entry(
                intel_id=entry.intel_id,
                chapter=entry.chapter,
                category=intel.category.value,
                true_content=entry.true_content,
                told_ironveil=entry.told_ironveil,
                told_embercrown=entry.told_embercrown,
                action_ironveil=entry.action_ironveil,
                action_embercrown=entry.action_embercrown,
                verified_ironveil=entry.verified_ironveil,
                verified_embercrown=entry.verified_embercrown,
                significance=intel.significance,
                verifiability=intel.verifiability,
            )

        # Render pending intel (known but not yet reported)
        for intel_id in self.game_state.known_intel:
            if intel_id in ledger_intel_ids:
                continue
            intel = intel_map.get(intel_id)
            if intel is None:
                continue
            if category_filter and intel.category != category_filter:
                continue

            has_any = True
            self.display.render_intel_board_entry(
                intel_id=intel.id,
                chapter=intel.chapter,
                category=intel.category.value,
                true_content=f"[PENDING] {intel.true_content}",
                told_ironveil=None,
                told_embercrown=None,
                action_ironveil=None,
                action_embercrown=None,
                verified_ironveil=False,
                verified_embercrown=False,
                significance=intel.significance,
                verifiability=intel.verifiability,
            )

        if not has_any:
            self.display.show_message("[dim]No intelligence gathered yet.[/dim]")

    def _render_contradictions(self) -> None:
        """Show any detected contradictions."""
        contradictions = self.ledger.get_contradictions()
        if not contradictions:
            return

        self.display.console.print("\n[bold red]Contradictions Detected:[/bold red]")
        for id_a, id_b in contradictions:
            self.display.console.print(f"  [red]! {id_a} <-> {id_b}[/red]")

    def _show_history(self) -> None:
        """Show chapter-by-chapter history."""
        self.display.console.print("\n[bold]Intelligence History[/bold]")
        for ch in range(1, self.game_state.chapter + 1):
            entries = self.ledger.get_entries_by_chapter(ch)
            if entries:
                self.display.console.print(f"\n[bold]Chapter {ch}:[/bold]")
                for entry in entries:
                    actions = []
                    if entry.action_ironveil:
                        actions.append(f"IV:{entry.action_ironveil.value}")
                    if entry.action_embercrown:
                        actions.append(f"EC:{entry.action_embercrown.value}")
                    action_str = ", ".join(actions) if actions else "pending"
                    self.display.console.print(
                        f"  {entry.intel_id}: {entry.true_content[:60]}... [{action_str}]"
                    )
        self.display.wait_for_enter()

    def _show_npc_memories(self) -> None:
        """Show what NPCs remember about the player."""
        memories = self.game_state.npc_memories
        if not memories:
            self.display.show_message("[dim]No NPC memories recorded yet.[/dim]")
            self.display.wait_for_enter()
            return

        self.display.console.print("\n[bold]NPC Memories of You[/bold]")
        self.display.console.print("[dim]What characters remember from your conversations.[/dim]\n")

        # Group by character
        by_character: dict[str, list] = {}
        for mem in memories:
            by_character.setdefault(mem.character_name, []).append(mem)

        for char_name, char_mems in by_character.items():
            alive = self.game_state.character_alive.get(char_name, True)
            status = "" if alive else " [DECEASED]"
            self.display.console.print(f"\n[bold]{char_name}{status}[/bold]")
            # Show most recent memories first, up to 5
            for mem in sorted(char_mems, key=lambda m: m.chapter, reverse=True)[:5]:
                tag_color = {
                    "suspicious": "red",
                    "alarmed": "red",
                    "grateful": "green",
                    "trusting": "green",
                    "intrigued": "yellow",
                }.get(mem.emotional_tag, "white")
                self.display.console.print(
                    f"  Ch{mem.chapter} [{tag_color}]{mem.emotional_tag}[/{tag_color}]: "
                    f"{mem.memory_text}"
                )
                if mem.player_quote:
                    self.display.console.print(
                        f"    [dim]You said: \"{mem.player_quote}\"[/dim]"
                    )

        self.display.wait_for_enter()

    def _show_relationships(self) -> None:
        """Show character relationship grid with trust descriptors."""
        self.display.console.print("\n[bold]Character Relationships[/bold]")

        for faction in (Faction.IRONVEIL, Faction.EMBERCROWN):
            color = "#6B8EAF" if faction == Faction.IRONVEIL else "#B87333"
            faction_name = (
                "Ironveil Compact"
                if faction == Faction.IRONVEIL
                else "Embercrown Reach"
            )
            self.display.console.print(f"\n[bold {color}]{faction_name}[/bold {color}]")

            chars = [c for c in self.world.characters if c.faction == faction]
            for char in chars:
                alive = self.game_state.character_alive.get(char.name, True)
                trust = self.game_state.character_trust.get(char.name, 50)
                trust_desc = get_trust_descriptor(trust)
                status = "" if alive else " [DECEASED]"

                self.display.console.print(
                    f"  {char.name} ({char.role}): "
                    f"Trust {trust_desc} ({trust}){status}"
                )

        self.display.wait_for_enter()
