"""World generation prompt templates."""
import json


WORLD_GEN_SYSTEM = """\
You are a master game designer creating a world for a spy strategy game.
You must output ONLY valid JSON matching the schema provided — no markdown fences, no commentary."""


WORLD_GEN_PROMPT = """\
Generate a complete game world for BOTH SIDES, a spy strategy game.

## Setting
A fantasy world with two rival nations on the brink of war. The player is a double agent \
embedded in both nations. The game spans 10 chapters.

## Nations

**Ironveil Compact** — A disciplined, militaristic nation of cold mountains and iron fortresses. \
Their power comes from industry and organization. They value order, duty, and precision.

**Embercrown Reach** — A passionate, expansionist nation of volcanic highlands and golden cities. \
Their power comes from commerce and charisma. They value ambition, loyalty, and spectacle.

**Ashenmere** — The neutral border territory between them, where much of the espionage takes place.

## Requirements

### Characters (8 total: 4 per faction)
Each faction needs these archetypes:
1. **Leader** — The ruler or supreme commander (age 40-65)
2. **Spymaster** — The intelligence chief who evaluates your reports (age 30-55)
3. **General/Admiral** — Military commander (age 35-60)
4. **Confidant** — Someone who personally trusts the player (age 25-45)

Each character must have:
- Unique name fitting their faction's culture
- Distinct personality (3-5 traits)
- A distinctive speech pattern (formal, blunt, flowery, etc.)
- Personal goals that may conflict with their faction
- A secret the player could discover
- starting_trust between 40-60
- starting_suspicion between 10-30
- relationships dict mapping other character names to relationship description
- knowledge dict mapping chapter numbers (1-10) to list of things they know
- death_conditions: what circumstances could kill this character
- behavioral_notes: how their behavior changes at different trust/suspicion levels

### Intelligence Pipeline (35-50 pieces total)
- Chapters 1-3: 3 pieces each (significance 1-3) — establishing intel
- Chapters 4-6: 4 pieces each (significance 2-4) — escalating stakes
- Chapters 7-9: 5 pieces each (significance 3-5) — critical intel
- Chapter 10: 3 pieces (significance 5) — endgame intel

Each piece needs:
- id in format ch{N}_{category}_{seq} (e.g., ch1_military_1)
- source_faction: which faction this intel comes FROM (alternating by chapter)
- true_content: the actual intelligence
- significance: 1-5 scale
- verifiability: 1-5 scale (how easily the other side can check it)
- category: military, political, economic, or personal
- potential_consequences: dict with keys "truthful", "distorted", "fabricated", "withheld" describing what happens
- related_characters: list of character names involved
- war_tension_effect: dict with keys "truthful", "distorted", "fabricated", "withheld" mapping to integer tension changes (-10 to +10)
- distortion_suggestions: 2-3 ways the player could twist this intel

### Wild Card Events (5-7 events)
Events that happen regardless of player choices, one every 2 chapters approximately.
Each needs: chapter, description, war_tension_effect (-10 to +10), narrative_prompt.

### Inciting Incident
A specific event that has just occurred that makes war seem imminent and justifies the player's \
double agent mission. This should be dramatic and morally ambiguous — neither side is clearly right.

### Balance Constraints
- Intel should alternate source factions by chapter (odd=Ironveil, even=Embercrown)
- Each category (military/political/economic/personal) should appear at least 8 times total
- Later chapters should have higher-significance intel
- Wild card events should not all push tension in the same direction
- Characters should have complex, interconnected relationships

Generate the complete world now as JSON.
"""


# ── Phased generation prompts ─────────────────────────────


STEP1_SYSTEM = """\
You are a master game designer creating characters and setting for a spy strategy game.
You must output ONLY valid JSON — no markdown fences, no commentary, no explanation."""


STEP1_PROMPT = """\
Generate the setting and characters for BOTH SIDES, a spy strategy game.

## Setting
A fantasy world with two rival nations on the brink of war. The player is a double agent \
embedded in both nations. The game spans 10 chapters.

## Nations
**Ironveil Compact** — A disciplined, militaristic nation of cold mountains and iron fortresses. \
Their power comes from industry and organization. They value order, duty, and precision.

**Embercrown Reach** — A passionate, expansionist nation of volcanic highlands and golden cities. \
Their power comes from commerce and charisma. They value ambition, loyalty, and spectacle.

**Ashenmere** — The neutral border territory between them.

## Generate These Fields

### inciting_incident (string)
A dramatic, morally ambiguous event that makes war seem imminent. At least 100 words.

### ironveil_background (string)
Background description for Ironveil Compact. 2-3 sentences.

### embercrown_background (string)
Background description for Embercrown Reach. 2-3 sentences.

### ashenmere_description (string)
Description of the neutral border territory. 2-3 sentences.

### characters (array of 8 objects)
4 per faction. Each faction needs: Leader (age 40-65), Spymaster (age 30-55), \
General/Admiral (age 35-60), Confidant (age 25-45).

Each character object has these fields:
- name (string): unique name fitting faction culture
- age (integer): within archetype range
- role (string): "leader", "spymaster", "general", or "confidant"
- faction (string): "ironveil" or "embercrown"
- personality (array of 3-5 strings): distinct personality traits
- speech_pattern (string): how they talk (formal, blunt, flowery, etc.)
- goals (string): personal goals that may conflict with faction
- secrets (string): a secret the player could discover
- starting_trust (integer): 40-60
- starting_suspicion (integer): 10-30
- relationships (object): maps other character names to relationship descriptions
- knowledge (object): maps chapter number strings ("1"-"10") to arrays of knowledge strings
- death_conditions (string): what could kill them
- behavioral_notes (string): how behavior changes at different trust/suspicion

Characters should have complex, interconnected relationships across factions.

## Output Format
Return a single JSON object with keys: inciting_incident, ironveil_background, \
embercrown_background, ashenmere_description, characters.
"""


STEP2_SYSTEM = """\
You are a master game designer creating an intelligence pipeline for a spy strategy game.
You must output ONLY valid JSON — no markdown fences, no commentary, no explanation."""


STEP2_PROMPT_TEMPLATE = """\
Generate the intelligence pipeline for BOTH SIDES using the characters and setting below.

## Existing Characters
{characters_summary}

## Inciting Incident
{inciting_incident}

## Requirements: intelligence_pipeline (array of 35-50 objects)
- Chapters 1-3: 3 pieces each (significance 1-3)
- Chapters 4-6: 4 pieces each (significance 2-4)
- Chapters 7-9: 5 pieces each (significance 3-5)
- Chapter 10: 3 pieces (significance 5)

Each object has:
- id (string): format "ch{{N}}_{{category}}_{{seq}}" e.g. "ch1_military_1"
- chapter (integer): 1-10
- source_faction (string): "ironveil" or "embercrown" (alternate by chapter: odd=ironveil, even=embercrown)
- true_content (string): the actual intelligence
- significance (integer): 1-5
- verifiability (integer): 1-5
- category (string): "military", "political", "economic", or "personal"
- potential_consequences (object): keys "truthful", "distorted", "fabricated", "withheld" with string values
- related_characters (array of strings): character names involved
- war_tension_effect (object): keys "truthful", "distorted", "fabricated", "withheld" with integer values (-10 to +10)
- distortion_suggestions (array of 2-3 strings): ways to twist this intel

## Balance Rules
- Each category (military/political/economic/personal) must appear at least 8 times
- Intel IDs must be unique
- Later chapters should have higher significance
- Reference actual character names from the roster above

## Output Format
Return a single JSON object with key: intelligence_pipeline
"""


STEP3_SYSTEM = """\
You are a master game designer creating wild card events for a spy strategy game.
You must output ONLY valid JSON — no markdown fences, no commentary, no explanation."""


STEP3_PROMPT_TEMPLATE = """\
Generate wild card events for BOTH SIDES using the world context below.

## Inciting Incident
{inciting_incident}

## Character Names
{character_names}

## Requirements: wild_card_events (array of 5-7 objects)
Events that happen regardless of player choices, roughly one every 2 chapters.

Each object has:
- chapter (integer): which chapter it triggers
- description (string): what happens
- war_tension_effect (integer): -10 to +10
- narrative_prompt (string): atmospheric text for the narrator

## Balance Rules
- Events should not all push tension in the same direction
- Spread across chapters (roughly chapters 2, 4, 5, 7, 9)
- Reference actual characters when appropriate

## Output Format
Return a single JSON object with key: wild_card_events
"""


# ── Builder functions ─────────────────────────────────────


def build_world_gen_prompt() -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for single-call world generation."""
    return WORLD_GEN_SYSTEM, WORLD_GEN_PROMPT


def build_step1_prompt(schema: dict) -> tuple[str, str]:
    """Return (system, user) prompts for Phase 1: Setting & Characters."""
    return STEP1_SYSTEM, STEP1_PROMPT


def build_step2_prompt(step1_data: dict, schema: dict) -> tuple[str, str]:
    """Return (system, user) prompts for Phase 2: Intelligence Pipeline."""
    chars = step1_data.get("characters", [])
    char_lines = []
    for c in chars:
        char_lines.append(
            f"- {c['name']} ({c['faction']}, {c['role']}): {', '.join(c.get('personality', []))}"
        )
    characters_summary = "\n".join(char_lines)
    inciting_incident = step1_data.get("inciting_incident", "")

    user_prompt = STEP2_PROMPT_TEMPLATE.format(
        characters_summary=characters_summary,
        inciting_incident=inciting_incident,
    )
    return STEP2_SYSTEM, user_prompt


def build_step3_prompt(step1_data: dict, step2_data: dict, schema: dict) -> tuple[str, str]:
    """Return (system, user) prompts for Phase 3: Wild Card Events."""
    inciting_incident = step1_data.get("inciting_incident", "")
    chars = step1_data.get("characters", [])
    character_names = ", ".join(c["name"] for c in chars)

    user_prompt = STEP3_PROMPT_TEMPLATE.format(
        inciting_incident=inciting_incident,
        character_names=character_names,
    )
    return STEP3_SYSTEM, user_prompt


WORLD_GEN_FEEDBACK = """\
The generated world had validation issues. Please fix these problems and regenerate:

{issues}

Return the complete corrected JSON.
"""


def build_feedback_prompt(issues: list[str]) -> str:
    return WORLD_GEN_FEEDBACK.format(issues="\n".join(f"- {i}" for i in issues))
