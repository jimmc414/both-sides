"""Tests for the InformationLedger class — intel tracking and contradiction detection."""
from __future__ import annotations

import pytest

from config import Faction, IntelAction, IntelCategory
from information_ledger import InformationLedger
from models import LedgerEntry


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

def _make_entry(
    intel_id="intel_1",
    chapter=1,
    true_content="Secret troop movements",
    **kw,
):
    defaults = dict(
        told_ironveil=None,
        told_embercrown=None,
        action_ironveil=None,
        action_embercrown=None,
    )
    defaults.update(kw)
    return LedgerEntry(
        intel_id=intel_id,
        chapter=chapter,
        true_content=true_content,
        **defaults,
    )


# ---------------------------------------------------------------------------
# Basic operations
# ---------------------------------------------------------------------------


class TestLedgerBasics:
    def test_empty_ledger(self):
        ledger = InformationLedger()
        assert ledger.entries == []

    def test_add_entry(self):
        ledger = InformationLedger()
        entry = _make_entry()
        ledger.add_entry(entry)
        assert len(ledger.entries) == 1
        assert ledger.entries[0] is entry

    def test_add_entry_contradiction_warning(self):
        """Adding a fabricated entry after a truthful one to the same faction raises a warning."""
        ledger = InformationLedger()
        truthful = _make_entry(
            intel_id="intel_1",
            told_ironveil="True report",
            action_ironveil=IntelAction.TRUTHFUL,
        )
        fabricated = _make_entry(
            intel_id="intel_2",
            told_ironveil="Fake report",
            action_ironveil=IntelAction.FABRICATED,
        )
        ledger.add_entry(truthful)
        warnings = ledger.add_entry(fabricated)
        assert len(warnings) > 0
        assert "contradiction" in warnings[0].lower()


# ---------------------------------------------------------------------------
# Faction queries
# ---------------------------------------------------------------------------


class TestFactionQueries:
    def test_get_entries_for_faction_ironveil(self):
        ledger = InformationLedger()
        entry_iv = _make_entry(intel_id="a", told_ironveil="Some info", action_ironveil=IntelAction.TRUTHFUL)
        entry_ec = _make_entry(intel_id="b", told_embercrown="Other info", action_embercrown=IntelAction.TRUTHFUL)
        ledger.add_entry(entry_iv)
        ledger.add_entry(entry_ec)
        result = ledger.get_entries_for_faction(Faction.IRONVEIL)
        assert len(result) == 1
        assert result[0].intel_id == "a"

    def test_get_entries_for_faction_embercrown(self):
        ledger = InformationLedger()
        entry = _make_entry(intel_id="x", told_embercrown="EC info", action_embercrown=IntelAction.DISTORTED)
        ledger.add_entry(entry)
        result = ledger.get_entries_for_faction(Faction.EMBERCROWN)
        assert len(result) == 1
        assert result[0].intel_id == "x"

    def test_get_entries_for_faction_empty(self):
        ledger = InformationLedger()
        entry = _make_entry(told_ironveil="Only ironveil", action_ironveil=IntelAction.TRUTHFUL)
        ledger.add_entry(entry)
        result = ledger.get_entries_for_faction(Faction.EMBERCROWN)
        assert result == []


# ---------------------------------------------------------------------------
# Unchecked fabrications
# ---------------------------------------------------------------------------


class TestUncheckedFabrications:
    def test_get_unchecked_fabrications(self):
        ledger = InformationLedger()
        fab = _make_entry(
            intel_id="fab_1",
            told_ironveil="Lies",
            action_ironveil=IntelAction.FABRICATED,
            verified_ironveil=False,
        )
        truth = _make_entry(
            intel_id="truth_1",
            told_ironveil="Facts",
            action_ironveil=IntelAction.TRUTHFUL,
        )
        ledger.add_entry(fab)
        ledger.add_entry(truth)
        result = ledger.get_unchecked_fabrications(Faction.IRONVEIL)
        assert len(result) == 1
        assert result[0].intel_id == "fab_1"

    def test_get_unchecked_fabrications_verified_excluded(self):
        ledger = InformationLedger()
        fab = _make_entry(
            intel_id="fab_1",
            told_ironveil="Lies",
            action_ironveil=IntelAction.FABRICATED,
            verified_ironveil=True,
        )
        ledger.add_entry(fab)
        result = ledger.get_unchecked_fabrications(Faction.IRONVEIL)
        assert result == []


# ---------------------------------------------------------------------------
# Chapter / intel_id queries
# ---------------------------------------------------------------------------


class TestEntryQueries:
    def test_get_entries_by_chapter(self):
        ledger = InformationLedger()
        e1 = _make_entry(intel_id="a", chapter=1)
        e2 = _make_entry(intel_id="b", chapter=2)
        e3 = _make_entry(intel_id="c", chapter=1)
        for e in (e1, e2, e3):
            ledger.add_entry(e)
        result = ledger.get_entries_by_chapter(1)
        assert len(result) == 2
        assert all(e.chapter == 1 for e in result)

    def test_get_entry_by_intel_id_found(self):
        ledger = InformationLedger()
        entry = _make_entry(intel_id="target_id")
        ledger.add_entry(entry)
        assert ledger.get_entry_by_intel_id("target_id") is entry

    def test_get_entry_by_intel_id_not_found(self):
        ledger = InformationLedger()
        assert ledger.get_entry_by_intel_id("missing") is None


# ---------------------------------------------------------------------------
# mark_verified
# ---------------------------------------------------------------------------


class TestMarkVerified:
    def test_mark_verified_ironveil(self):
        ledger = InformationLedger()
        entry = _make_entry(intel_id="v1")
        ledger.add_entry(entry)
        ledger.mark_verified("v1", Faction.IRONVEIL, True)
        assert entry.verified_ironveil is True
        assert entry.verification_result_ironveil is True

    def test_mark_verified_embercrown(self):
        ledger = InformationLedger()
        entry = _make_entry(intel_id="v2")
        ledger.add_entry(entry)
        ledger.mark_verified("v2", Faction.EMBERCROWN, False)
        assert entry.verified_embercrown is True
        assert entry.verification_result_embercrown is False


# ---------------------------------------------------------------------------
# Contradictions
# ---------------------------------------------------------------------------


class TestContradictions:
    def test_get_contradictions_deduplicates(self):
        """If A contradicts B, we should only get the pair once, not (A,B) and (B,A)."""
        e1 = _make_entry(
            intel_id="a",
            told_ironveil="Truth",
            action_ironveil=IntelAction.TRUTHFUL,
        )
        e2 = _make_entry(
            intel_id="b",
            told_ironveil="Fabrication",
            action_ironveil=IntelAction.FABRICATED,
        )
        ledger = InformationLedger()
        ledger.add_entry(e1)
        ledger.add_entry(e2)  # This should register contradiction with "a"

        # Also manually set the reverse to test deduplication
        e1.contradiction_with.append("b")

        pairs = ledger.get_contradictions()
        # Should appear exactly once as a sorted tuple
        assert len(pairs) == 1
        assert pairs[0] == ("a", "b")


# ---------------------------------------------------------------------------
# Summaries and formatting
# ---------------------------------------------------------------------------


class TestSummaries:
    def test_get_faction_report_summary_with_entries(self):
        ledger = InformationLedger()
        entry = _make_entry(
            intel_id="ch1_mil_1",
            chapter=1,
            told_ironveil="Troop positions on the eastern front",
            action_ironveil=IntelAction.TRUTHFUL,
        )
        ledger.add_entry(entry)
        summary = ledger.get_faction_report_summary(Faction.IRONVEIL)
        assert "ironveil" in summary.lower()
        assert "ch1_mil_1" in summary
        assert "truthful" in summary.lower()

    def test_get_faction_report_summary_empty(self):
        ledger = InformationLedger()
        summary = ledger.get_faction_report_summary(Faction.IRONVEIL)
        assert "no intelligence" in summary.lower()

    def test_get_full_history_format(self):
        ledger = InformationLedger()
        e1 = _make_entry(
            intel_id="ch1_mil_1",
            chapter=1,
            true_content="Secret plans",
            told_ironveil="The plans",
            action_ironveil=IntelAction.TRUTHFUL,
        )
        e2 = _make_entry(
            intel_id="ch2_pol_1",
            chapter=2,
            true_content="Alliance details",
            told_embercrown="Alliance info",
            action_embercrown=IntelAction.DISTORTED,
        )
        ledger.add_entry(e1)
        ledger.add_entry(e2)
        history = ledger.get_full_history()
        assert "=== Chapter 1 ===" in history
        assert "=== Chapter 2 ===" in history
        assert "ch1_mil_1" in history
        assert "ch2_pol_1" in history
