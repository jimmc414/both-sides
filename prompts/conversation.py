"""NPC conversation system prompts."""
from __future__ import annotations

from typing import TYPE_CHECKING

from config import Faction, FACTION_COLORS, SceneType

if TYPE_CHECKING:
    from models import CharacterProfile, GameState


def _format_memories_section(
    npc_memories: list | None, player_promises: list | None
) -> str:
    """Build the NPC memories and promises section for the system prompt."""
    parts: list[str] = []

    if npc_memories:
        from collections import defaultdict

        by_char: dict[str, list] = defaultdict(list)
        for m in npc_memories:
            by_char[m.character_name].append(m)

        parts.append("\nNPC MEMORIES FROM PREVIOUS ENCOUNTERS:")
        for char_name, memories in by_char.items():
            parts.append(f"\n  {char_name}:")
            for m in memories:
                quote = f' (they said: "{m.player_quote}")' if m.player_quote else ""
                parts.append(
                    f"    - [Ch{m.chapter}, {m.emotional_tag}] {m.memory_text}{quote}"
                )

    if player_promises:
        parts.append("\nPROMISES THE PLAYER HAS MADE TO THIS FACTION:")
        for p in player_promises:
            status = "UNFULFILLED" if not p.get("fulfilled") else "fulfilled"
            parts.append(f"  - Ch{p.get('chapter', '?')}: {p.get('promise', '?')} [{status}]")

    if parts:
        parts.append(
            "\nBEHAVIORAL DIRECTIVE: Characters should naturally reference their memories "
            "when relevant. If a character remembers the player saying something suspicious, "
            "they should probe further. If the player made a promise, the character should "
            "ask about it. Do NOT dump all memories at once — weave them in when the topic "
            "is relevant."
        )

    return "\n".join(parts)


def build_scene_system_prompt(
    scene_type: SceneType,
    characters: list[CharacterProfile],
    game_state: GameState,
    ledger_summary: str,
    intel_to_share: list[str] | None = None,
    is_delivery_scene: bool = False,
    player_report: dict[str, str] | None = None,
    npc_memories: list | None = None,
    player_promises: list | None = None,
    faction_reactions: list | None = None,
) -> str:
    """Build the system prompt for a conversation scene."""
    faction = characters[0].faction if characters else Faction.IRONVEIL
    faction_name = FACTION_COLORS[faction]["name"]

    # Character profiles
    char_section = "\n".join(_format_character(c, game_state) for c in characters)

    # Scene description
    scene_desc = _get_scene_description(scene_type, faction_name)

    # Intel context
    intel_section = ""
    if intel_to_share:
        intel_section = (
            "\n\nINTELLIGENCE TO SHARE WITH PLAYER:\n"
            + "\n".join(f"- {item}" for item in intel_to_share)
            + "\n\nNaturally weave this intelligence into the conversation. "
            "Don't dump it all at once — reveal it through dialogue."
        )

    # Faction reactions context
    reactions_section = ""
    if faction_reactions:
        reaction_lines = []
        for r in faction_reactions:
            line = f"- {r.narrative_for_npcs}"
            if r.outcome_known:
                line += (
                    "\n  [NPC NOTE: This action is now known to have been based on "
                    "false intelligence. Characters should be angry and suspicious.]"
                )
            reaction_lines.append(line)
        reactions_section = (
            "\n\nFACTION ACTIONS BASED ON PREVIOUS INTELLIGENCE:\n"
            "These actions were taken by the faction based on intelligence the player "
            "provided. Characters should naturally reference these actions when "
            "relevant — with pride if successful, with frustration or suspicion if "
            "they failed.\n"
            + "\n".join(reaction_lines)
        )

    # Delivery scene instructions
    delivery_section = ""
    if is_delivery_scene and player_report:
        delivery_section = (
            "\n\nPLAYER IS DELIVERING A REPORT:\n"
            "The player will present intelligence to your characters. "
            "React in character based on trust level and the information given.\n"
            "Player's prepared statements:\n"
            + "\n".join(f"- {k}: {v}" for k, v in player_report.items())
        )

    return f"""\
You are running an interactive scene in a spy strategy game called BOTH SIDES.

SETTING: {scene_desc}

CHARACTERS YOU PLAY (respond as ALL of them, never as the player):
{char_section}

FACTION CONTEXT: {faction_name}
CHAPTER: {game_state.chapter}
{ledger_summary}
{intel_section}
{delivery_section}
{reactions_section}

{_format_memories_section(npc_memories, player_promises)}

RULES:
1. Stay in character at ALL times. Each character speaks with their defined speech pattern.
2. Format dialogue as: **CharacterName:** "Dialogue here" with actions in *italics*.
3. Respond to the player's input naturally — they are a trusted agent (or suspected spy, depending on suspicion levels).
4. If multiple characters are present, they may interact with each other and react to what the player says.
5. Do NOT break character, reference game mechanics, or speak as a narrator unless describing actions.
6. Keep responses to 2-4 paragraphs per turn. Be dramatic but concise.
7. If the player asks about something a character wouldn't know, have them deflect in character.
8. Track what has been said — do not repeat information already shared.
9. Characters with high suspicion toward the player should be guarded, test the player, or ask probing questions.
10. Characters with high trust should be more open, share secrets, and confide.
11. Characters should naturally reference their memories when relevant — do NOT dump all memories at once, weave them in when the topic arises.
12. If a character remembers something suspicious, they should probe further in character.
13. If the player made a promise, the character should ask about it when contextually appropriate.
"""


def _format_character(char: CharacterProfile, game_state: GameState) -> str:
    trust = game_state.character_trust.get(char.name, 50)
    suspicion = game_state.character_suspicion.get(char.name, 15)
    alive = game_state.character_alive.get(char.name, True)

    if not alive:
        return f"[{char.name} — DECEASED, do not include in scene]"

    trust_behavior = ""
    if trust >= 70:
        trust_behavior = "Very open and trusting. May share secrets or personal concerns."
    elif trust >= 50:
        trust_behavior = "Cordial and professional. Standard interactions."
    elif trust >= 30:
        trust_behavior = "Somewhat cool. Brief, measured responses."
    else:
        trust_behavior = "Hostile and dismissive. Minimal engagement."

    suspicion_behavior = ""
    if suspicion >= 60:
        suspicion_behavior = " HIGHLY SUSPICIOUS — asks probing questions, tests loyalty, watches for inconsistencies."
    elif suspicion >= 40:
        suspicion_behavior = " Somewhat suspicious — occasionally probes, slightly guarded."
    elif suspicion >= 25:
        suspicion_behavior = " Mildly watchful but not alarmed."

    return f"""
**{char.name}** — {char.role} ({char.faction.value})
Age: {char.age} | Personality: {', '.join(char.personality)}
Speech: {char.speech_pattern}
Goals: {char.goals}
Trust Level: {trust}/100 — {trust_behavior}
Suspicion: {suspicion}/100{suspicion_behavior}
Notes: {char.behavioral_notes}
"""


def _get_scene_description(scene_type: SceneType, faction_name: str) -> str:
    descriptions = {
        SceneType.WAR_COUNCIL: (
            f"A formal war council in the {faction_name}'s command chamber. "
            "Maps and strategic documents cover the table. The mood is tense and purposeful."
        ),
        SceneType.PRIVATE_MEETING: (
            f"A private meeting in a secured room within the {faction_name}'s headquarters. "
            "The conversation is intimate and candid — what's said here stays here."
        ),
        SceneType.FEAST: (
            f"A grand feast hosted by the {faction_name}. Wine flows, music plays, "
            "but beneath the revelry, secrets are exchanged in whispered asides."
        ),
        SceneType.INTERROGATION: (
            f"An interrogation chamber within the {faction_name}'s intelligence wing. "
            "The atmosphere is cold. You are here to answer questions, not ask them."
        ),
        SceneType.FIELD_VISIT: (
            f"A forward position near the border of Ashenmere, held by the {faction_name}. "
            "Soldiers move in the background. The reality of potential war is palpable."
        ),
    }
    return descriptions.get(scene_type, "A meeting within the faction's territory.")
