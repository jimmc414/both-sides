"""World generation prompt templates."""

WORLD_GEN_SYSTEM = """\
You are a master game designer creating a world for a spy strategy game.
You must output ONLY valid JSON matching the schema provided — no markdown, no commentary.
"""

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
- id in format ch{{N}}_{{category}}_{{seq}} (e.g., ch1_military_1)
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


def build_world_gen_prompt() -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for world generation."""
    return WORLD_GEN_SYSTEM, WORLD_GEN_PROMPT


WORLD_GEN_FEEDBACK = """\
The generated world had validation issues. Please fix these problems and regenerate:

{issues}

Return the complete corrected JSON.
"""


def build_feedback_prompt(issues: list[str]) -> str:
    return WORLD_GEN_FEEDBACK.format(issues="\n".join(f"- {i}" for i in issues))
