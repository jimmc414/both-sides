"""Player input parsing and action resolution."""
from __future__ import annotations


def parse_player_input(
    text: str, characters: list[str]
) -> tuple[str, str | None]:
    """Parse player input for character targeting and commands.

    Returns (message, target_character).
    target_character is None if no specific target.
    """
    text = text.strip()
    if not text:
        return "", None

    # Check for commands first
    lower = text.lower()
    commands = {"[done]", "done", "[leave]", "leave", "[board]", "board",
                "[save]", "save", "[help]", "help"}
    if lower in commands:
        return text, None

    # Check for character targeting by number: [1], [2], etc.
    target: str | None = None
    message = text

    if text.startswith("[") and "]" in text:
        bracket_end = text.index("]")
        bracket_content = text[1:bracket_end].strip()
        if bracket_content.isdigit():
            idx = int(bracket_content) - 1
            if 0 <= idx < len(characters):
                target = characters[idx]
                message = text[bracket_end + 1:].strip()

    # Check for @Name targeting
    elif text.startswith("@"):
        space_idx = text.find(" ")
        if space_idx == -1:
            name_part = text[1:]
            message = ""
        else:
            name_part = text[1:space_idx]
            message = text[space_idx + 1:].strip()

        # Match by prefix (case-insensitive)
        for char in characters:
            if char.lower().startswith(name_part.lower()):
                target = char
                break

    return message or text, target


def is_command(text: str) -> bool:
    """Check if input is a game command."""
    lower = text.strip().lower()
    return lower in {
        "[done]", "done", "[leave]", "leave",
        "[board]", "board", "[save]", "save",
        "[help]", "help",
    }


def get_command(text: str) -> str | None:
    """Extract command name from input."""
    lower = text.strip().lower().strip("[]")
    valid = {"done", "leave", "board", "save", "help"}
    return lower if lower in valid else None


HELP_TEXT = """\
[bold]BOTH SIDES — Commands[/bold]

During conversations:
  [1]-[4] or @Name  Target a specific character
  [done] / [leave]  End the current scene
  [board]           Open intelligence board
  [save]            Save game
  [help]            Show this help

During report building:
  <intel#> <action#>  Set action for intel piece
    Actions: 1=Truthful, 2=Withhold, 3=Distort, 4=Fabricate
  [C]               Confirm and submit report

Intelligence Board:
  [M] Military  [P] Political  [E] Economic  [S] Social
  [H] History   [R] Relationships  [B] Back
"""
