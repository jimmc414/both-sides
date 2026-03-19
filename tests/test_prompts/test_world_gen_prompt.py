"""Tests for prompts.world_gen — world generation and feedback prompts."""
from __future__ import annotations

import pytest

from prompts.world_gen import build_feedback_prompt, build_world_gen_prompt


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestBuildWorldGenPrompt:

    def test_build_world_gen_prompt_returns_tuple(self):
        result = build_world_gen_prompt()

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], str)

    def test_system_prompt_mentions_game_designer(self):
        system, _ = build_world_gen_prompt()

        assert "game designer" in system.lower()


class TestBuildFeedbackPrompt:

    def test_feedback_prompt_includes_issues(self):
        issues = [
            "Missing character relationships",
            "Intel ch3_military_1 has invalid significance",
        ]
        result = build_feedback_prompt(issues)

        assert "Missing character relationships" in result
        assert "Intel ch3_military_1 has invalid significance" in result
