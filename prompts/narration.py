"""Briefing, crossover, and fallout narration prompts."""
from __future__ import annotations

from typing import TYPE_CHECKING

from config import FACTION_COLORS, Faction

if TYPE_CHECKING:
    from models import GameState, WorldState


NARRATION_SYSTEM = """\
You are the narrator for BOTH SIDES, a spy strategy game. Write in second person ("you").
Your prose should be atmospheric, tense, and literary — like a John le Carré novel set in a \
fantasy world. Keep narration to 2-3 paragraphs. No dialogue — just narration and internal \
monologue.
"""


def build_briefing_prompt(
    game_state: GameState,
    world: WorldState,
    consequences: list[str] | None = None,
    visible_reactions: list | None = None,
) -> tuple[str, str]:
    """Return (system, user) prompts for chapter briefing narration."""
    faction_a = game_state.scene_a_faction
    faction_b = (
        Faction.EMBERCROWN
        if faction_a == Faction.IRONVEIL
        else Faction.IRONVEIL
    )
    faction_a_name = FACTION_COLORS[faction_a]["name"]
    faction_b_name = FACTION_COLORS[faction_b]["name"]

    consequence_text = ""
    if consequences:
        consequence_text = (
            "\n\nPREVIOUS CHAPTER CONSEQUENCES:\n"
            + "\n".join(f"- {c}" for c in consequences)
        )

    reaction_text = ""
    if visible_reactions:
        reaction_lines = []
        for r in visible_reactions:
            faction_label = r.acting_faction.upper()
            reaction_lines.append(f"- [{faction_label}] {r.reaction_description}")
        reaction_text = (
            "\n\nFACTION ACTIONS THIS CHAPTER:\n"
            + "\n".join(reaction_lines)
            + "\n\nWeave these actions into the briefing. The player should feel "
            "the weight of seeing their intelligence shaping the world."
        )

    user_prompt = f"""\
Write a briefing narration for Chapter {game_state.chapter}.

SETTING: The player is a double agent serving both the {faction_a_name} and the {faction_b_name}.
They are about to visit the {faction_a_name} first this chapter.

WORLD CONTEXT:
- Inciting incident: {world.inciting_incident}
- War tension: {game_state.war_tension}% ({"rising toward war" if game_state.war_tension > 60 else "tense but manageable" if game_state.war_tension > 35 else "relatively calm"})
- {faction_a_name} trust: {getattr(game_state, faction_a.value + '_trust')}
- {faction_b_name} trust: {getattr(game_state, faction_b.value + '_trust')}
{consequence_text}{reaction_text}

Write the briefing — set the scene, hint at what's to come, build tension.
"""
    return NARRATION_SYSTEM, user_prompt


def build_crossover_prompt(game_state: GameState) -> tuple[str, str]:
    """Return (system, user) prompts for the crossover narration."""
    faction_a = game_state.scene_a_faction
    faction_b = (
        Faction.EMBERCROWN
        if faction_a == Faction.IRONVEIL
        else Faction.IRONVEIL
    )
    faction_a_name = FACTION_COLORS[faction_a]["name"]
    faction_b_name = FACTION_COLORS[faction_b]["name"]

    user_prompt = f"""\
Write a brief crossover narration. The player has just left the {faction_a_name} and is now \
traveling to the {faction_b_name}.

CONTEXT:
- Chapter: {game_state.chapter}
- War tension: {game_state.war_tension}%
- The player carries intelligence that they must decide how to report.

Write a reflective, atmospheric transition — the journey between factions, the weight of \
secrets carried, the danger of the crossing. 2 paragraphs.
"""
    return NARRATION_SYSTEM, user_prompt


def build_fallout_prompt(
    game_state: GameState,
    consequences: list[str],
    chapter_reactions: list | None = None,
) -> tuple[str, str]:
    """Return (system, user) prompts for fallout narration."""
    reaction_text = ""
    if chapter_reactions:
        reaction_lines = []
        for r in chapter_reactions:
            reaction_lines.append(
                f"- {r.acting_faction.upper()}: {r.reaction_description}"
            )
        reaction_text = (
            "\n\nFACTION REACTIONS THIS CHAPTER:\n"
            + "\n".join(reaction_lines)
            + "\n\nInclude the effects of these faction actions in the fallout narration."
        )

    user_prompt = f"""\
Write a fallout narration for the end of Chapter {game_state.chapter}.

CONSEQUENCES THAT OCCURRED:
{chr(10).join(f'- {c}' for c in consequences)}
{reaction_text}

WAR TENSION: {game_state.war_tension}%
IRONVEIL TRUST: {game_state.ironveil_trust} | SUSPICION: {game_state.ironveil_suspicion}
EMBERCROWN TRUST: {game_state.embercrown_trust} | SUSPICION: {game_state.embercrown_suspicion}

Narrate the aftermath — what ripples through the world as a result of the player's choices. \
Be specific about the consequences. Build dramatic tension for the next chapter.
"""
    return NARRATION_SYSTEM, user_prompt


def build_leak_discovery_prompt(
    game_state: GameState,
    leak_descriptions: list[str],
) -> tuple[str, str]:
    """Return (system, user) prompts for atmospheric leak discovery narration."""
    leaks_text = "\n".join(f"- {d}" for d in leak_descriptions)
    user_prompt = f"""\
Write a tense narration for a moment of discovery in Chapter {game_state.chapter}. \
Cross-faction intelligence has leaked — the player's deceptions are being uncovered.

LEAKS DISCOVERED:
{leaks_text}

WAR TENSION: {game_state.war_tension}%
IRONVEIL SUSPICION: {game_state.ironveil_suspicion}
EMBERCROWN SUSPICION: {game_state.embercrown_suspicion}

Narrate the moment of exposure — whispers in corridors, documents compared, a spy's \
world beginning to collapse. Be atmospheric and dreadful. The player should feel the \
walls closing in. 2 paragraphs.
"""
    return NARRATION_SYSTEM, user_prompt


def build_opening_narration_prompt(world: WorldState) -> tuple[str, str]:
    """Return (system, user) prompts for the game opening narration."""
    user_prompt = f"""\
Write the opening narration for BOTH SIDES.

THE INCITING INCIDENT: {world.inciting_incident}

THE WORLD:
- Ironveil Compact: {world.ironveil_background}
- Embercrown Reach: {world.embercrown_background}
- Ashenmere (neutral ground): {world.ashenmere_description}

The player is a spy who has managed to embed themselves in both nations. They serve as a \
trusted agent to each side, but their true loyalties are their own. As war looms, every \
piece of intelligence they carry could tip the balance.

Write a dramatic opening — 3 paragraphs. Set the world, the stakes, and the player's \
impossible position. End by making the reader feel the weight of what's to come.
"""
    return NARRATION_SYSTEM, user_prompt
