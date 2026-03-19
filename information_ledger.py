"""Intelligence tracking backbone — manages ledger entries and contradiction detection."""
from __future__ import annotations

from config import Faction, IntelAction
from models import LedgerEntry


class InformationLedger:
    """Wraps a list of LedgerEntry with query and analysis methods."""

    def __init__(self, entries: list[LedgerEntry] | None = None):
        self._entries: list[LedgerEntry] = entries or []

    @property
    def entries(self) -> list[LedgerEntry]:
        return self._entries

    def add_entry(self, entry: LedgerEntry) -> list[str]:
        """Add a ledger entry. Returns list of contradiction warnings."""
        warnings: list[str] = []
        # Check for contradictions before adding
        for existing in self._entries:
            if existing.intel_id == entry.intel_id:
                continue
            # Check if we told the same faction conflicting info
            for faction in ("ironveil", "embercrown"):
                told_field = f"told_{faction}"
                action_field = f"action_{faction}"
                new_told = getattr(entry, told_field)
                old_told = getattr(existing, told_field)
                new_action = getattr(entry, action_field)
                old_action = getattr(existing, action_field)
                if new_told and old_told and new_action and old_action:
                    if (
                        new_action in (IntelAction.FABRICATED, IntelAction.DISTORTED)
                        and old_action == IntelAction.TRUTHFUL
                    ):
                        warnings.append(
                            f"Potential contradiction: {entry.intel_id} conflicts "
                            f"with {existing.intel_id} for {faction}"
                        )
                        entry.contradiction_with.append(existing.intel_id)
        self._entries.append(entry)
        return warnings

    def get_entries_for_faction(self, faction: Faction) -> list[LedgerEntry]:
        """Get all entries where intel was delivered to a faction."""
        field = f"told_{faction.value}"
        return [e for e in self._entries if getattr(e, field) is not None]

    def get_unchecked_fabrications(self, faction: Faction) -> list[LedgerEntry]:
        """Get fabrications not yet verified by a faction."""
        action_field = f"action_{faction.value}"
        verified_field = f"verified_{faction.value}"
        return [
            e for e in self._entries
            if getattr(e, action_field) == IntelAction.FABRICATED
            and not getattr(e, verified_field)
        ]

    def get_entries_by_chapter(self, chapter: int) -> list[LedgerEntry]:
        return [e for e in self._entries if e.chapter == chapter]

    def get_entry_by_intel_id(self, intel_id: str) -> LedgerEntry | None:
        for e in self._entries:
            if e.intel_id == intel_id:
                return e
        return None

    def mark_verified(
        self,
        intel_id: str,
        faction: Faction,
        result: bool,
    ) -> None:
        """Mark an intel piece as verified/failed for a faction."""
        entry = self.get_entry_by_intel_id(intel_id)
        if entry is None:
            return
        if faction == Faction.IRONVEIL:
            entry.verified_ironveil = True
            entry.verification_result_ironveil = result
        else:
            entry.verified_embercrown = True
            entry.verification_result_embercrown = result

    def get_contradictions(self) -> list[tuple[str, str]]:
        """Return list of (intel_id_a, intel_id_b) contradiction pairs."""
        pairs: list[tuple[str, str]] = []
        seen: set[tuple[str, str]] = set()
        for entry in self._entries:
            for contra_id in entry.contradiction_with:
                pair = tuple(sorted([entry.intel_id, contra_id]))
                if pair not in seen:
                    seen.add(pair)
                    pairs.append(pair)
        return pairs

    def get_faction_report_summary(self, faction: Faction) -> str:
        """Build a text summary of what a faction has been told. Used as LLM context."""
        lines: list[str] = []
        entries = self.get_entries_for_faction(faction)
        if not entries:
            return f"No intelligence has been reported to {faction.value} yet."

        lines.append(f"Intelligence reported to {faction.value}:")
        for entry in entries:
            told = getattr(entry, f"told_{faction.value}")
            action = getattr(entry, f"action_{faction.value}")
            verified = getattr(entry, f"verified_{faction.value}")
            result = getattr(entry, f"verification_result_{faction.value}")

            status = ""
            if verified:
                status = " [VERIFIED]" if result else " [EXPOSED]"

            lines.append(
                f"  Ch{entry.chapter} [{entry.intel_id}] ({action.value}){status}: {told}"
            )
        return "\n".join(lines)

    def get_unchecked_nontruthful(self, faction: Faction) -> list[LedgerEntry]:
        """Get entries where the faction was told a non-truthful version and hasn't been
        verified or discovered via leak. Used as cascade targets."""
        action_field = f"action_{faction.value}"
        verified_field = f"verified_{faction.value}"
        retracted_field = f"retracted_for_{faction.value}"
        return [
            e for e in self._entries
            if getattr(e, action_field) in (IntelAction.FABRICATED, IntelAction.DISTORTED)
            and not getattr(e, verified_field)
            and not getattr(e, retracted_field)
            and faction.value not in e.leak_discovered_by
        ]

    def get_cross_faction_discrepancies(self) -> list[LedgerEntry]:
        """Get entries where the player told different things to each faction.
        Both factions must have been told something, and the actions must differ."""
        results: list[LedgerEntry] = []
        for e in self._entries:
            if (
                e.action_ironveil is not None
                and e.action_embercrown is not None
                and e.action_ironveil != IntelAction.WITHHELD
                and e.action_embercrown != IntelAction.WITHHELD
            ):
                # Different actions, or same action but different content
                if e.action_ironveil != e.action_embercrown:
                    results.append(e)
                elif (
                    e.told_ironveil is not None
                    and e.told_embercrown is not None
                    and e.told_ironveil != e.told_embercrown
                ):
                    results.append(e)
        return results

    def get_full_history(self) -> str:
        """Formatted full ledger for reveal sequence."""
        lines: list[str] = []
        chapters = sorted(set(e.chapter for e in self._entries))

        for ch in chapters:
            lines.append(f"\n=== Chapter {ch} ===")
            for entry in self.get_entries_by_chapter(ch):
                lines.append(f"\nIntel: {entry.intel_id}")
                lines.append(f"  Truth: {entry.true_content}")
                if entry.told_ironveil:
                    action_i = entry.action_ironveil.value if entry.action_ironveil else "?"
                    lines.append(f"  Told Ironveil ({action_i}): {entry.told_ironveil}")
                if entry.told_embercrown:
                    action_e = entry.action_embercrown.value if entry.action_embercrown else "?"
                    lines.append(f"  Told Embercrown ({action_e}): {entry.told_embercrown}")
                if entry.consequence:
                    lines.append(f"  Consequence: {entry.consequence}")
                if entry.contradiction_with:
                    lines.append(
                        f"  Contradicts: {', '.join(entry.contradiction_with)}"
                    )

        return "\n".join(lines)
