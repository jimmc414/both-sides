"""LLM-powered world generation at game start."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    query,
)

from config import MODEL, Faction, IntelCategory
from models import WorldState
from prompts.world_gen import build_feedback_prompt, build_world_gen_prompt


async def generate_world(max_retries: int = 2) -> WorldState:
    """Generate a complete game world using the LLM with structured output."""
    system_prompt, user_prompt = build_world_gen_prompt()
    schema = WorldState.model_json_schema()

    for attempt in range(max_retries + 1):
        raw_text = await _call_llm(system_prompt, user_prompt, schema)
        world = _parse_world(raw_text)

        if world is None:
            if attempt < max_retries:
                user_prompt = build_feedback_prompt(
                    ["Failed to parse JSON output. Ensure output is valid JSON only."]
                )
                continue
            raise RuntimeError("Failed to generate valid world JSON after retries")

        issues = validate_world(world)
        if not issues:
            return world

        if attempt < max_retries:
            user_prompt = build_feedback_prompt(issues)
        else:
            # Accept with warnings on final attempt
            return world

    raise RuntimeError("World generation failed")


async def _call_llm(
    system_prompt: str, user_prompt: str, schema: dict,
    max_rate_limit_retries: int = 3,
) -> str:
    """Single LLM call for world generation with rate limit retry."""
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=MODEL,
        allowed_tools=[],
        permission_mode="bypassPermissions",
        output_format=schema,
    )

    for attempt in range(max_rate_limit_retries + 1):
        text_parts: list[str] = []
        try:
            async for msg in query(prompt=user_prompt, options=options):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)
            return "".join(text_parts)
        except Exception as e:
            if "rate_limit" in str(e).lower() and attempt < max_rate_limit_retries:
                wait = 2 ** attempt * 5  # 5s, 10s, 20s
                await asyncio.sleep(wait)
                continue
            raise

    return ""


def _parse_world(raw: str) -> WorldState | None:
    """Parse LLM output into a WorldState."""
    # Strip markdown fences if present
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # Remove opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)

    try:
        data = json.loads(text)
        return WorldState.model_validate(data)
    except (json.JSONDecodeError, Exception):
        return None


def validate_world(world: WorldState) -> list[str]:
    """Semantic validation of generated world. Returns list of issues."""
    issues: list[str] = []

    # Check character count per faction
    ironveil_chars = [c for c in world.characters if c.faction == Faction.IRONVEIL]
    embercrown_chars = [c for c in world.characters if c.faction == Faction.EMBERCROWN]
    if len(ironveil_chars) < 4:
        issues.append(f"Ironveil has {len(ironveil_chars)} characters, need at least 4")
    if len(embercrown_chars) < 4:
        issues.append(f"Embercrown has {len(embercrown_chars)} characters, need at least 4")

    # Check unique names
    names = [c.name for c in world.characters]
    if len(names) != len(set(names)):
        issues.append("Character names are not unique")

    # Check intel per chapter
    for ch in range(1, 11):
        ch_intel = [i for i in world.intelligence_pipeline if i.chapter == ch]
        if ch <= 3 and len(ch_intel) < 3:
            issues.append(f"Chapter {ch} has {len(ch_intel)} intel pieces, need at least 3")
        elif 4 <= ch <= 6 and len(ch_intel) < 3:
            issues.append(f"Chapter {ch} has {len(ch_intel)} intel pieces, need at least 3")
        elif 7 <= ch <= 9 and len(ch_intel) < 4:
            issues.append(f"Chapter {ch} has {len(ch_intel)} intel pieces, need at least 4")
        elif ch == 10 and len(ch_intel) < 2:
            issues.append(f"Chapter 10 has {len(ch_intel)} intel pieces, need at least 2")

    # Check total intel
    total = len(world.intelligence_pipeline)
    if total < 30:
        issues.append(f"Only {total} intel pieces total, need at least 30")

    # Check category distribution
    categories = {cat: 0 for cat in IntelCategory}
    for intel in world.intelligence_pipeline:
        categories[intel.category] = categories.get(intel.category, 0) + 1
    for cat, count in categories.items():
        if count < 5:
            issues.append(f"Category {cat.value} has only {count} intel pieces, need at least 5")

    # Check intel IDs are unique
    intel_ids = [i.id for i in world.intelligence_pipeline]
    if len(intel_ids) != len(set(intel_ids)):
        issues.append("Intelligence piece IDs are not unique")

    # Check escalating significance
    early_avg = _avg_significance(world, 1, 3)
    late_avg = _avg_significance(world, 7, 10)
    if late_avg <= early_avg:
        issues.append(
            f"Intel significance should escalate: early avg {early_avg:.1f}, late avg {late_avg:.1f}"
        )

    # Check wild card events
    if len(world.wild_card_events) < 3:
        issues.append(f"Only {len(world.wild_card_events)} wild card events, need at least 3")

    # Check inciting incident
    if len(world.inciting_incident) < 50:
        issues.append("Inciting incident is too short")

    return issues


def _avg_significance(world: WorldState, ch_start: int, ch_end: int) -> float:
    pieces = [
        i for i in world.intelligence_pipeline
        if ch_start <= i.chapter <= ch_end
    ]
    if not pieces:
        return 0.0
    return sum(i.significance for i in pieces) / len(pieces)


def save_world(world: WorldState, path: str | Path) -> None:
    """Save world state to JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(world.model_dump_json(indent=2))


def load_world(path: str | Path) -> WorldState:
    """Load world state from JSON file."""
    path = Path(path)
    return WorldState.model_validate_json(path.read_text())
