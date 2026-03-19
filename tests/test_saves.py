"""Tests for the saves module — JSON persistence via Pydantic."""
from __future__ import annotations

import json

import pytest

from config import Faction, IntelCategory
from models import (
    CharacterProfile,
    GameState,
    IntelligencePiece,
    WorldState,
)
from saves import auto_save, list_saves, load_game, save_game


# ---------------------------------------------------------------------------
# Local helpers
# ---------------------------------------------------------------------------

def _make_char(name="TestChar", faction=Faction.IRONVEIL, **kw):
    defaults = dict(
        age=35,
        role="Spy",
        personality=["cunning"],
        speech_pattern="formal",
        goals="survive",
        secrets="none",
        starting_trust=50,
        starting_suspicion=15,
    )
    defaults.update(kw)
    return CharacterProfile(name=name, faction=faction, **defaults)


def _make_intel(id="ch1_military_1", source_faction=Faction.IRONVEIL, **kw):
    defaults = dict(
        chapter=1,
        true_content="Test intel",
        significance=3,
        verifiability=3,
        category=IntelCategory.MILITARY,
    )
    defaults.update(kw)
    return IntelligencePiece(id=id, source_faction=source_faction, **defaults)


def _make_world():
    chars = [
        _make_char(f"Char{i}", Faction.IRONVEIL if i < 2 else Faction.EMBERCROWN)
        for i in range(4)
    ]
    intel = [_make_intel(f"ch1_mil_{i}") for i in range(2)]
    return WorldState(
        inciting_incident="Test incident",
        ironveil_background="Iron bg",
        embercrown_background="Ember bg",
        ashenmere_description="Neutral zone",
        characters=chars,
        intelligence_pipeline=intel,
        wild_card_events=[],
    )


def _make_game_state(**kw):
    defaults = dict(chapter=3, war_tension=65)
    defaults.update(kw)
    return GameState(**defaults)


@pytest.fixture
def save_dir(tmp_path, monkeypatch):
    """Redirect saves.DATA_DIR to a temporary directory."""
    monkeypatch.setattr("saves.DATA_DIR", tmp_path)
    return tmp_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSaveAndLoad:
    def test_save_and_load_roundtrip(self, save_dir):
        world = _make_world()
        gs = _make_game_state(chapter=5, war_tension=72)
        path = save_game(world, gs, slot=1)
        assert path.exists()

        loaded = load_game(slot=1)
        assert loaded is not None
        assert loaded.game_state.chapter == 5
        assert loaded.game_state.war_tension == 72
        assert loaded.slot == 1
        assert len(loaded.world_state.characters) == len(world.characters)

    def test_load_nonexistent_slot(self, save_dir):
        assert load_game(slot=99) is None

    def test_auto_save_uses_slot_0(self, save_dir):
        world = _make_world()
        gs = _make_game_state()
        path = auto_save(world, gs)
        assert path.name == "save_0.json"
        loaded = load_game(slot=0)
        assert loaded is not None
        assert loaded.slot == 0

    def test_save_overwrites_existing(self, save_dir):
        world = _make_world()
        gs1 = _make_game_state(chapter=2)
        gs2 = _make_game_state(chapter=7)
        save_game(world, gs1, slot=1)
        save_game(world, gs2, slot=1)
        loaded = load_game(slot=1)
        assert loaded is not None
        assert loaded.game_state.chapter == 7

    def test_load_corrupted_file(self, save_dir):
        bad_path = save_dir / "save_1.json"
        bad_path.write_text("{not valid json at all ~~~")
        assert load_game(slot=1) is None

    def test_save_creates_data_dir(self, tmp_path, monkeypatch):
        nested = tmp_path / "sub" / "dir"
        monkeypatch.setattr("saves.DATA_DIR", nested)
        assert not nested.exists()
        world = _make_world()
        gs = _make_game_state()
        save_game(world, gs, slot=1)
        assert nested.exists()


class TestListSaves:
    def test_list_saves_empty(self, save_dir):
        result = list_saves()
        assert result == []

    def test_list_saves_with_data(self, save_dir):
        world = _make_world()
        gs = _make_game_state(chapter=4, war_tension=60)
        save_game(world, gs, slot=1)
        auto_save(world, gs)

        saves = list_saves()
        assert len(saves) == 2

        slots = {s["slot"] for s in saves}
        assert 0 in slots  # auto save
        assert 1 in slots  # manual save

        manual = next(s for s in saves if s["slot"] == 1)
        assert manual["chapter"] == 4
        assert manual["war_tension"] == 60
        assert manual["label"] == "Slot 1"

        auto = next(s for s in saves if s["slot"] == 0)
        assert auto["label"] == "Auto-save"
