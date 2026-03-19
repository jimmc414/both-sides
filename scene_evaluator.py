"""Scene Consequence Evaluator — analyzes conversation transcripts for NPC memories, slips, and trust changes."""
from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, TextBlock, query

from config import (
    CONVERSATION_QUALITY_MODIFIERS,
    MAX_MEMORIES_PER_CHARACTER,
    MODEL,
    SCENE_EVAL_TIMEOUT,
    SLIP_SEVERITY_CONSEQUENCES,
    Faction,
)
from display import GameDisplay
from prompts.scene_analysis import build_scene_analysis_prompt
from trust_system import (
    clamp,
    get_faction_suspicion,
    get_faction_trust,
    set_faction_suspicion,
    set_faction_trust,
)

if TYPE_CHECKING:
    from information_ledger import InformationLedger
    from models import (
        CharacterProfile,
        ConversationLog,
        GameState,
        NPCMemory,
        SceneAnalysis,
        WorldState,
    )


def _neutral_analysis(conv_log: "ConversationLog") -> "SceneAnalysis":
    """Return a zero-impact SceneAnalysis as a fallback."""
    from models import SceneAnalysis

    return SceneAnalysis(
        chapter=conv_log.chapter,
        phase=conv_log.phase,
        faction=conv_log.faction,
    )


class SceneEvaluator:
    """Evaluates conversation scenes for consequences, memories, and slip detection."""

    def __init__(self, display: GameDisplay):
        self.display = display

    async def evaluate_scene(
        self,
        conv_log: "ConversationLog",
        game_state: "GameState",
        world: "WorldState",
        ledger: "InformationLedger",
        characters: list["CharacterProfile"],
    ) -> "SceneAnalysis":
        """Analyze a conversation transcript and return structured SceneAnalysis."""
        from models import SceneAnalysis

        # Build context for the prompt
        faction = conv_log.faction
        other_faction = (
            Faction.EMBERCROWN if faction == Faction.IRONVEIL else Faction.IRONVEIL
        )

        ledger_summary = ledger.get_faction_report_summary(faction)

        # What the player legitimately knows from this faction
        known_lines = []
        for intel_id in game_state.known_intel:
            intel_obj = next(
                (i for i in world.intelligence_pipeline if i.id == intel_id), None
            )
            if intel_obj and intel_obj.source_faction == faction:
                known_lines.append(f"- [{intel_obj.id}] {intel_obj.true_content}")
        known_intel_summary = "\n".join(known_lines)

        # Knowledge that implies other-faction access
        cross_faction_intel = []
        for intel_id in game_state.known_intel:
            intel_obj = next(
                (i for i in world.intelligence_pipeline if i.id == intel_id), None
            )
            if intel_obj and intel_obj.source_faction == other_faction:
                cross_faction_intel.append(
                    f"[{intel_obj.id}] {intel_obj.true_content}"
                )

        # Existing memories for characters in this scene
        scene_char_names = {c.name for c in characters}
        existing_memories = [
            m for m in game_state.npc_memories if m.character_name in scene_char_names
        ]

        system_prompt, user_prompt = build_scene_analysis_prompt(
            conv_log=conv_log,
            characters=characters,
            game_state=game_state,
            ledger_summary=ledger_summary,
            known_intel_summary=known_intel_summary,
            cross_faction_intel=cross_faction_intel,
            existing_memories=existing_memories,
        )

        # Embed schema in system prompt since output_format doesn't work with Agent SDK
        schema_json = json.dumps(SceneAnalysis.model_json_schema(), indent=2)
        system_prompt += f"\n\nJSON Schema for your response:\n```json\n{schema_json}\n```"

        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=MODEL,
            allowed_tools=[],
            permission_mode="bypassPermissions",
        )

        async def _collect() -> str:
            parts: list[str] = []
            async for msg in query(prompt=user_prompt, options=options):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            parts.append(block.text)
            return "".join(parts)

        text_parts: list[str] = []
        try:
            raw_text = await asyncio.wait_for(_collect(), timeout=SCENE_EVAL_TIMEOUT)
            # Strip markdown fences
            raw_text = raw_text.strip()
            if raw_text.startswith("```"):
                lines = raw_text.split("\n")
                lines = lines[1:]
                if lines and lines[-1].strip() == "```":
                    lines = lines[:-1]
                raw_text = "\n".join(lines)
        except (asyncio.TimeoutError, Exception):
            return _neutral_analysis(conv_log)

        # Parse JSON response
        try:
            data = json.loads(raw_text)
            analysis = SceneAnalysis.model_validate(data)
        except (json.JSONDecodeError, Exception):
            return _neutral_analysis(conv_log)

        # Post-processing: validate character names
        valid_names = {c.name for c in characters}
        analysis.memories = [
            m for m in analysis.memories if m.character_name in valid_names
        ]
        analysis.slips = [
            s for s in analysis.slips if s.detecting_character in valid_names
        ]
        analysis.trust_adjustments = {
            k: max(-10, min(10, v))
            for k, v in analysis.trust_adjustments.items()
            if k in valid_names
        }
        analysis.suspicion_adjustments = {
            k: max(-10, min(10, v))
            for k, v in analysis.suspicion_adjustments.items()
            if k in valid_names
        }

        # Clamp faction-level deltas
        analysis.faction_trust_delta = max(-10, min(10, analysis.faction_trust_delta))
        analysis.faction_suspicion_delta = max(
            -10, min(10, analysis.faction_suspicion_delta)
        )

        # Ensure chapter/phase/faction match the actual scene
        analysis.chapter = conv_log.chapter
        analysis.phase = conv_log.phase
        analysis.faction = conv_log.faction

        return analysis

    def apply_analysis(
        self, analysis: "SceneAnalysis", game_state: "GameState"
    ) -> list[str]:
        """Apply a SceneAnalysis to game state. Returns narrative descriptions of detected slips."""
        slip_narratives: list[str] = []
        faction = analysis.faction

        # 1. Apply faction-level trust/suspicion from conversation quality
        quality = analysis.conversation_quality.lower() if analysis.conversation_quality else "neutral"
        quality_mod = CONVERSATION_QUALITY_MODIFIERS.get(quality, {"trust": 0, "suspicion": 0})

        total_faction_trust = analysis.faction_trust_delta + quality_mod["trust"]
        total_faction_suspicion = analysis.faction_suspicion_delta + quality_mod["suspicion"]

        # 2. Apply slip consequences
        for slip in analysis.slips:
            severity_mod = SLIP_SEVERITY_CONSEQUENCES.get(
                slip.severity, {"suspicion": 2, "trust": -1}
            )
            total_faction_suspicion += severity_mod["suspicion"]
            total_faction_trust += severity_mod["trust"]
            slip_narratives.append(
                f"[{slip.slip_type}] {slip.description}"
            )

        # Apply faction-level changes
        old_trust = get_faction_trust(game_state, faction)
        old_suspicion = get_faction_suspicion(game_state, faction)
        set_faction_trust(game_state, faction, old_trust + total_faction_trust)
        set_faction_suspicion(
            game_state, faction, old_suspicion + total_faction_suspicion
        )

        # 3. Apply per-character trust/suspicion adjustments
        for char_name, delta in analysis.trust_adjustments.items():
            if char_name in game_state.character_trust:
                old = game_state.character_trust[char_name]
                game_state.character_trust[char_name] = clamp(old + delta)

        for char_name, delta in analysis.suspicion_adjustments.items():
            if char_name in game_state.character_suspicion:
                old = game_state.character_suspicion[char_name]
                game_state.character_suspicion[char_name] = clamp(old + delta)

        # 4. Store memories (with cap per character)
        for memory in analysis.memories:
            memory.chapter = analysis.chapter
            game_state.npc_memories.append(memory)

        # Enforce memory cap per character
        self._cap_memories(game_state)

        # 5. Store promises
        for promise_text in analysis.promises_made:
            game_state.player_promises.append({
                "promise": promise_text,
                "faction": faction.value,
                "chapter": analysis.chapter,
                "fulfilled": False,
            })

        # 5b. Check fulfilled promises
        for fulfilled_text in analysis.promises_fulfilled:
            for promise in game_state.player_promises:
                if promise.get("fulfilled"):
                    continue
                if promise.get("faction") != faction.value:
                    continue
                # Substring match: if the fulfillment text overlaps with the stored promise
                stored = promise.get("promise", "").lower()
                check = fulfilled_text.lower()
                if not stored or not check:
                    continue
                if stored in check or check in stored:
                    promise["fulfilled"] = True
                    break

        # 6. Store the analysis itself
        game_state.scene_analyses.append(analysis)

        return slip_narratives

    def _cap_memories(self, game_state: "GameState") -> None:
        """Ensure no character has more than MAX_MEMORIES_PER_CHARACTER memories."""
        from collections import defaultdict

        by_char: dict[str, list] = defaultdict(list)
        for m in game_state.npc_memories:
            by_char[m.character_name].append(m)

        pruned: list = []
        for char_name, memories in by_char.items():
            if len(memories) <= MAX_MEMORIES_PER_CHARACTER:
                pruned.extend(memories)
            else:
                # Sort by importance (desc), then chapter (desc) to keep best + most recent
                memories.sort(key=lambda m: (m.importance, m.chapter), reverse=True)
                pruned.extend(memories[:MAX_MEMORIES_PER_CHARACTER])

        game_state.npc_memories = pruned
