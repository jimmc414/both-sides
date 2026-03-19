"""Save/load game state — JSON persistence via Pydantic."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from models import GameState, SaveData, WorldState

DATA_DIR = Path(__file__).parent / "data"


def _ensure_data_dir() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def save_game(
    world_state: WorldState,
    game_state: GameState,
    slot: int,
) -> Path:
    """Save game to a numbered slot. Returns save file path."""
    _ensure_data_dir()
    save_data = SaveData(
        world_state=world_state,
        game_state=game_state,
        timestamp=datetime.now().isoformat(),
        slot=slot,
    )
    path = DATA_DIR / f"save_{slot}.json"
    path.write_text(save_data.model_dump_json(indent=2))
    return path


def load_game(slot: int) -> SaveData | None:
    """Load game from a numbered slot. Returns None if not found or corrupted.

    Returns None with a descriptive message printed to stderr if the save
    file exists but cannot be parsed.
    """
    path = DATA_DIR / f"save_{slot}.json"
    if not path.exists():
        return None
    try:
        return SaveData.model_validate_json(path.read_text())
    except Exception as e:
        import sys
        print(
            f"Warning: Save file '{path}' exists but could not be loaded "
            f"({type(e).__name__}: {e}). "
            "The file may be corrupted. You can start a new game or try "
            "another save slot.",
            file=sys.stderr,
        )
        return None


def auto_save(
    world_state: WorldState,
    game_state: GameState,
) -> Path:
    """Auto-save to slot 0."""
    return save_game(world_state, game_state, slot=0)


def list_saves() -> list[dict]:
    """List available saves with metadata."""
    _ensure_data_dir()
    saves = []
    for slot in range(4):  # 0=auto, 1-3=manual
        path = DATA_DIR / f"save_{slot}.json"
        if path.exists():
            try:
                data = SaveData.model_validate_json(path.read_text())
                label = "Auto-save" if slot == 0 else f"Slot {slot}"
                saves.append({
                    "slot": slot,
                    "label": label,
                    "chapter": data.game_state.chapter,
                    "timestamp": data.timestamp,
                    "war_tension": data.game_state.war_tension,
                })
            except Exception:
                continue
    return saves
