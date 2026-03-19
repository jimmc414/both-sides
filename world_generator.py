"""LLM-powered world generation at game start."""
from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    TextBlock,
    query,
)

from config import (
    MODEL,
    Faction,
    IntelCategory,
    RATE_LIMIT_BACKOFF_FACTOR,
    RATE_LIMIT_BASE_DELAY,
    RATE_LIMIT_MAX_DELAY,
    RATE_LIMIT_MAX_RETRIES,
    WORLD_GEN_STEP_TIMEOUT,
)
from models import WorldState
from prompts.world_gen import (
    build_feedback_prompt,
    build_step1_prompt,
    build_step2_prompt,
    build_step3_prompt,
    build_world_gen_prompt,
)

if TYPE_CHECKING:
    from display import GameDisplay

CHECKPOINT_DIR = Path("data")
CHECKPOINT_STALE_SECONDS = 3600  # ignore checkpoints older than 1 hour


# ── Checkpoint helpers ──────────────────────────────────────


def _checkpoint_path(step: int) -> Path:
    return CHECKPOINT_DIR / f"_worldgen_step{step}.json"


def _save_checkpoint(step: int, data: dict) -> None:
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    payload = {"step": step, "timestamp": time.time(), "data": data}
    _checkpoint_path(step).write_text(json.dumps(payload, indent=2))


def _load_checkpoint(step: int) -> dict | None:
    path = _checkpoint_path(step)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
        age = time.time() - payload.get("timestamp", 0)
        if age > CHECKPOINT_STALE_SECONDS:
            path.unlink(missing_ok=True)
            return None
        return payload["data"]
    except (json.JSONDecodeError, KeyError):
        path.unlink(missing_ok=True)
        return None


def _clear_checkpoints() -> None:
    for step in (1, 2, 3):
        _checkpoint_path(step).unlink(missing_ok=True)


# ── LLM call with timeout + rate-limit retry ───────────────


async def _collect_query(prompt: str, options: ClaudeAgentOptions) -> str:
    """Run a single SDK query and collect all text blocks."""
    text_parts: list[str] = []
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for block in msg.content:
                if isinstance(block, TextBlock):
                    text_parts.append(block.text)
    return "".join(text_parts)


async def _call_llm(
    system_prompt: str,
    user_prompt: str,
    timeout: float = WORLD_GEN_STEP_TIMEOUT,
    on_status: object | None = None,
) -> str:
    """Single LLM call with timeout and rate-limit retry.

    on_status: optional callback(message: str) for progress updates.
    """
    options = ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=MODEL,
        allowed_tools=[],
        permission_mode="bypassPermissions",
    )

    for attempt in range(RATE_LIMIT_MAX_RETRIES + 1):
        try:
            return await asyncio.wait_for(
                _collect_query(user_prompt, options),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            if attempt < RATE_LIMIT_MAX_RETRIES:
                wait = min(
                    RATE_LIMIT_BASE_DELAY * (RATE_LIMIT_BACKOFF_FACTOR ** attempt),
                    RATE_LIMIT_MAX_DELAY,
                )
                if on_status:
                    on_status(f"Timed out, retrying in {wait:.0f}s (attempt {attempt + 2})...")
                await asyncio.sleep(wait)
                continue
            raise
        except Exception as e:
            if "rate_limit" in str(e).lower() and attempt < RATE_LIMIT_MAX_RETRIES:
                wait = min(
                    RATE_LIMIT_BASE_DELAY * (RATE_LIMIT_BACKOFF_FACTOR ** attempt),
                    RATE_LIMIT_MAX_DELAY,
                )
                if on_status:
                    on_status(f"Rate limited, waiting {wait:.0f}s (attempt {attempt + 2})...")
                await asyncio.sleep(wait)
                continue
            raise

    return ""


# ── JSON parsing ────────────────────────────────────────────


def _strip_fences(raw: str) -> str:
    """Strip markdown code fences if present."""
    text = raw.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]  # Remove opening fence
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text


def _parse_json(raw: str) -> dict | None:
    """Parse raw LLM text into a dict, stripping fences."""
    try:
        return json.loads(_strip_fences(raw))
    except (json.JSONDecodeError, ValueError):
        return None


def _parse_world(raw: str) -> WorldState | None:
    """Parse LLM output into a WorldState."""
    data = _parse_json(raw)
    if data is None:
        return None
    try:
        return WorldState.model_validate(data)
    except Exception:
        return None


# ── Phased world generation (new) ──────────────────────────


async def generate_world_phased(
    display: GameDisplay | None = None,
    max_retries: int = 2,
    on_phase1_complete: object | None = None,
) -> tuple[WorldState, object]:
    """Generate a complete game world in 3 phases with checkpoints.

    Phase 1: Setting & Characters
    Phase 2: Intelligence Pipeline
    Phase 3: Wild Card Events & Assembly

    If *on_phase1_complete* is an async callable, it is called with the partial
    WorldState (setting + characters) after Phase 2 completes.  The returned
    coroutine is run concurrently with Phase 3 so the caller can overlap work
    (e.g. generating the opening narration) with the final generation step.
    """
    schema = WorldState.model_json_schema()

    def status(msg: str) -> None:
        if display:
            display.show_message(f"[dim]  {msg}[/dim]")

    def progress(step: int, desc: str) -> None:
        if display:
            display.render_world_gen_progress(step, 3, desc)

    def step_done(step: int, desc: str, detail: str = "") -> None:
        if display:
            display.render_world_gen_step_complete(step, desc, detail)

    # ── Phase 1: Setting & Characters ──
    step1_data = _load_checkpoint(1)
    if step1_data:
        status("Resuming from checkpoint: characters already generated.")
        step_done(1, "Setting & Characters", "loaded from checkpoint")
    else:
        progress(1, "Creating setting and characters...")
        sys1, usr1 = build_step1_prompt(schema)

        for attempt in range(max_retries + 1):
            raw = await _call_llm(sys1, usr1, on_status=status)
            step1_data = _parse_json(raw)
            if step1_data and "characters" in step1_data and len(step1_data["characters"]) >= 8:
                break
            if attempt < max_retries:
                status(f"Step 1 parse failed, retrying ({attempt + 2}/{max_retries + 1})...")
                step1_data = None
            else:
                raise RuntimeError("Failed to generate characters after retries")

        _save_checkpoint(1, step1_data)
        n_chars = len(step1_data.get("characters", []))
        step_done(1, "Setting & Characters", f"{n_chars} characters created")

    # ── Phase 2: Intelligence Pipeline ──
    step2_data = _load_checkpoint(2)
    if step2_data:
        status("Resuming from checkpoint: intelligence pipeline already generated.")
        step_done(2, "Intelligence Pipeline", "loaded from checkpoint")
    else:
        progress(2, "Building intelligence pipeline...")
        sys2, usr2 = build_step2_prompt(step1_data, schema)

        for attempt in range(max_retries + 1):
            raw = await _call_llm(sys2, usr2, on_status=status)
            step2_data = _parse_json(raw)
            if step2_data and "intelligence_pipeline" in step2_data and len(step2_data["intelligence_pipeline"]) >= 25:
                break
            if attempt < max_retries:
                status(f"Step 2 parse failed, retrying ({attempt + 2}/{max_retries + 1})...")
                step2_data = None
            else:
                raise RuntimeError("Failed to generate intelligence pipeline after retries")

        _save_checkpoint(2, step2_data)
        n_intel = len(step2_data.get("intelligence_pipeline", []))
        step_done(2, "Intelligence Pipeline", f"{n_intel} intel pieces")

    # ── Phase 3: Wild Cards & Assembly ──
    # Optionally run a parallel task (e.g. opening narration) alongside Phase 3.
    # The callback receives a partial WorldState built from Phase 1+2 data.
    parallel_task: asyncio.Task | None = None
    if callable(on_phase1_complete):
        # Build a partial world so the callback can use setting/character fields
        partial = {**step1_data, **step2_data}
        if "ending_conditions" not in partial:
            partial["ending_conditions"] = {}
        if "wild_card_events" not in partial:
            partial["wild_card_events"] = []
        try:
            partial_world = WorldState.model_validate(partial)
            coro = on_phase1_complete(partial_world)
            if coro is not None:
                parallel_task = asyncio.create_task(coro)
        except Exception:
            pass  # partial world build failed — skip parallel task

    progress(3, "Generating wild card events...")
    sys3, usr3 = build_step3_prompt(step1_data, step2_data, schema)

    for attempt in range(max_retries + 1):
        raw = await _call_llm(sys3, usr3, on_status=status)
        step3_data = _parse_json(raw)
        if step3_data and "wild_card_events" in step3_data and len(step3_data["wild_card_events"]) >= 3:
            break
        if attempt < max_retries:
            status(f"Step 3 parse failed, retrying ({attempt + 2}/{max_retries + 1})...")
            step3_data = None
        else:
            raise RuntimeError("Failed to generate wild card events after retries")

    step_done(3, "Wild Card Events", f"{len(step3_data.get('wild_card_events', []))} events")

    # Wait for parallel task if it was started
    parallel_result = None
    if parallel_task is not None:
        try:
            parallel_result = await parallel_task
        except Exception:
            pass  # parallel task failed — caller will generate it normally

    # ── Assembly ──
    combined = {**step1_data, **step2_data, **step3_data}

    # Ensure ending_conditions has defaults
    if "ending_conditions" not in combined:
        combined["ending_conditions"] = {}

    try:
        world = WorldState.model_validate(combined)
    except Exception as e:
        raise RuntimeError(f"Failed to assemble world: {e}")

    issues = validate_world(world)
    if issues and display:
        display.show_message(f"[yellow]World generated with {len(issues)} minor issue(s) — proceeding.[/yellow]")

    _clear_checkpoints()
    return world, parallel_result


# ── Legacy single-call generation (kept as fallback) ───────


async def generate_world(max_retries: int = 2) -> WorldState:
    """Generate a complete game world in a single LLM call (legacy)."""
    system_prompt, user_prompt = build_world_gen_prompt()

    for attempt in range(max_retries + 1):
        raw_text = await _call_llm(system_prompt, user_prompt)
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
            return world

    raise RuntimeError("World generation failed")


# ── Validation ──────────────────────────────────────────────


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
