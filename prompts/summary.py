"""Post-game ledger reveal and summary prompts."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from models import GameState


SUMMARY_SYSTEM = """\
You are the narrator delivering the final reveal for BOTH SIDES, a spy strategy game.
Write in second person. Be dramatic, reflective, and specific about the consequences of \
the player's choices. Reference specific intel pieces, lies told, and their effects.
"""


def build_ending_prompt(
    political_outcome: str,
    personal_fate: str,
    game_state: GameState,
    ledger_text: str,
) -> tuple[str, str]:
    """Return (system, user) prompts for the ending narration."""
    user_prompt = f"""\
Write the ending narration for BOTH SIDES.

POLITICAL OUTCOME: {political_outcome}
PERSONAL FATE: {personal_fate}

FINAL STATE:
- War Tension: {game_state.war_tension}%
- Ironveil Trust: {game_state.ironveil_trust} | Suspicion: {game_state.ironveil_suspicion}
- Embercrown Trust: {game_state.embercrown_trust} | Suspicion: {game_state.embercrown_suspicion}
- Chapters Completed: {game_state.chapter}

COMPLETE INTELLIGENCE LEDGER:
{ledger_text}

Write a 3-4 paragraph epilogue that reflects on the player's journey. Reference specific \
lies, truths, and pivotal moments from the ledger. End with a final reflection on the nature \
of loyalty and deception.
"""
    return SUMMARY_SYSTEM, user_prompt


def build_ledger_reveal_prompt(
    chapter: int,
    chapter_entries: str,
    game_state: GameState,
) -> tuple[str, str]:
    """Return (system, user) prompts for revealing one chapter of the ledger."""
    user_prompt = f"""\
Write a brief dramatic reveal for Chapter {chapter}'s intelligence activity.

ENTRIES:
{chapter_entries}

WAR TENSION AT THIS POINT: {game_state.war_tension}%

Narrate what the player did this chapter — the truths told, the lies spun, the consequences \
that rippled outward. Be specific and dramatic. 1-2 paragraphs.
"""
    return SUMMARY_SYSTEM, user_prompt
