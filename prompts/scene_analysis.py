"""Scene analysis prompt — instructs the LLM to evaluate a conversation transcript."""
from __future__ import annotations

from typing import TYPE_CHECKING

from config import Faction, FACTION_COLORS

if TYPE_CHECKING:
    from models import CharacterProfile, ConversationLog, GameState, NPCMemory


def build_scene_analysis_prompt(
    conv_log: ConversationLog,
    characters: list[CharacterProfile],
    game_state: GameState,
    ledger_summary: str,
    known_intel_summary: str,
    cross_faction_intel: list[str],
    existing_memories: list[NPCMemory],
) -> tuple[str, str]:
    """Build (system, user) prompts for scene analysis.

    Returns a tuple of (system_prompt, user_prompt).
    """
    faction = conv_log.faction
    other_faction = (
        Faction.EMBERCROWN if faction == Faction.IRONVEIL else Faction.IRONVEIL
    )
    faction_name = FACTION_COLORS[faction]["name"]
    other_name = FACTION_COLORS[other_faction]["name"]

    # Format character profiles
    char_lines = []
    for c in characters:
        trust = game_state.character_trust.get(c.name, 50)
        suspicion = game_state.character_suspicion.get(c.name, 15)
        char_lines.append(
            f"- {c.name} ({c.role}): trust={trust}, suspicion={suspicion}, "
            f"personality=[{', '.join(c.personality)}]"
        )
    char_section = "\n".join(char_lines)

    # Format existing memories
    mem_lines = []
    for m in existing_memories:
        mem_lines.append(
            f"- [{m.character_name}, Ch{m.chapter}] {m.memory_text} "
            f"(tag: {m.emotional_tag}, importance: {m.importance})"
        )
    mem_section = "\n".join(mem_lines) if mem_lines else "None yet."

    # Format transcript (truncate to last 15 exchanges if long)
    exchanges = conv_log.exchanges
    if len(exchanges) > 15:
        exchanges = exchanges[-15:]
    transcript_lines = []
    for ex in exchanges:
        role = ex.get("role", "?")
        text = ex.get("text", "")
        if role == "player":
            transcript_lines.append(f"PLAYER: {text}")
        elif role == "assistant":
            transcript_lines.append(f"NPCs: {text}")
        elif role == "system":
            continue
    transcript = "\n\n".join(transcript_lines)

    # Cross-faction intel
    cross_section = "\n".join(f"- {item}" for item in cross_faction_intel) if cross_faction_intel else "None identified."

    system_prompt = f"""\
You are an espionage analyst evaluating a conversation transcript from a spy strategy game.

The player is a double agent working for BOTH the {faction_name} and the {other_name}. In this scene, the player was speaking with {faction_name} NPCs.

Your job is to analyze what happened and produce a structured JSON assessment.

CHARACTERS IN THIS SCENE:
{char_section}

EXISTING NPC MEMORIES FROM PRIOR ENCOUNTERS:
{mem_section}

INTEL CONTEXT:
{ledger_summary}

WHAT THE PLAYER LEGITIMATELY KNOWS FROM {faction_name.upper()}:
{known_intel_summary or "Nothing specific yet."}

KNOWLEDGE THAT WOULD IMPLY ACCESS TO {other_name.upper()} (cross-faction):
{cross_section}

ANALYSIS GUIDELINES:
1. MEMORIES: Extract specific, quotable moments NPCs would remember. Be concrete — "Player mentioned troop positions at the northern pass" not "Player discussed military matters." Include the player's actual words when possible.

2. SLIP DETECTION: Be CONSERVATIVE. Only flag clear cross-faction knowledge reveals — where the player referenced information they could ONLY know from the other faction. Ambiguous references are NOT slips. When in doubt, do not flag.
   - "cross_faction_knowledge": Player revealed info only available from {other_name}
   - "contradiction": Player said something contradicting what they previously told this faction
   - "broken_promise": Player failed to follow through on a prior commitment

3. TRUST/SUSPICION ADJUSTMENTS: Small deltas (-5 to +5) per character. Must be justified by specific moments in the conversation.

4. CONVERSATION QUALITY: Rate as "excellent", "good", "neutral", "poor", or "hostile" based on how diplomatically the player handled the scene.

5. PROMISES: Record any commitments the player made ("I'll investigate...", "I'll bring you...", "I'll find out...")

6. PROMISE FULFILLMENT: Check if the player fulfilled any previously made promises listed in NPC memories or promises section. List the text of each promise that was fulfilled in this conversation.

Respond with ONLY valid JSON matching the schema provided."""

    user_prompt = f"""\
Analyze this Chapter {conv_log.chapter} conversation transcript between the player and {faction_name} NPCs.

TRANSCRIPT:
{transcript}

Produce your analysis as JSON."""

    return system_prompt, user_prompt
