"""Tests for actions.py — player input parsing and command detection."""
from __future__ import annotations

import pytest

from actions import get_command, is_command, parse_player_input, HELP_TEXT


CHARACTERS = ["General Thane", "Lady Selene", "Brother Aldric", "Captain Voss"]


# ---------------------------------------------------------------------------
# parse_player_input
# ---------------------------------------------------------------------------

class TestParsePlayerInput:
    def test_empty_input(self):
        msg, target = parse_player_input("", CHARACTERS)
        assert msg == ""
        assert target is None

    def test_plain_text_no_target(self):
        msg, target = parse_player_input("Hello everyone", CHARACTERS)
        assert msg == "Hello everyone"
        assert target is None

    def test_bracket_targeting(self):
        msg, target = parse_player_input("[1] What news?", CHARACTERS)
        assert target == "General Thane"
        assert msg == "What news?"

    def test_bracket_targeting_second_character(self):
        msg, target = parse_player_input("[2] Stay alert.", CHARACTERS)
        assert target == "Lady Selene"
        assert msg == "Stay alert."

    def test_bracket_out_of_range(self):
        msg, target = parse_player_input("[9] Hello", CHARACTERS)
        assert target is None
        assert msg == "[9] Hello"

    def test_at_name_targeting(self):
        msg, target = parse_player_input("@General How goes the war?", CHARACTERS)
        assert target == "General Thane"
        assert msg == "How goes the war?"

    def test_at_name_prefix_match(self):
        msg, target = parse_player_input("@Lady I need your counsel.", CHARACTERS)
        assert target == "Lady Selene"
        assert msg == "I need your counsel."

    def test_at_name_no_message(self):
        msg, target = parse_player_input("@Brother", CHARACTERS)
        assert target == "Brother Aldric"
        # When message is empty, falls through to `message or text`
        assert msg == "@Brother"

    def test_command_returns_no_target(self):
        msg, target = parse_player_input("[done]", CHARACTERS)
        assert target is None


# ---------------------------------------------------------------------------
# is_command
# ---------------------------------------------------------------------------

class TestIsCommand:
    @pytest.mark.parametrize("text", [
        "[done]", "done", "[leave]", "leave",
        "[board]", "board", "[save]", "save",
        "[help]", "help",
    ])
    def test_valid_commands(self, text):
        assert is_command(text) is True

    def test_non_command(self):
        assert is_command("hello") is False

    def test_whitespace_handling(self):
        assert is_command("  done  ") is True


# ---------------------------------------------------------------------------
# get_command
# ---------------------------------------------------------------------------

class TestGetCommand:
    def test_extracts_done(self):
        assert get_command("[done]") == "done"

    def test_extracts_help(self):
        assert get_command("help") == "help"

    def test_invalid_returns_none(self):
        assert get_command("attack") is None

    def test_strips_brackets(self):
        assert get_command("[board]") == "board"

    def test_help_text_exists(self):
        assert "BOTH SIDES" in HELP_TEXT
        assert "[done]" in HELP_TEXT or "done" in HELP_TEXT.lower()
