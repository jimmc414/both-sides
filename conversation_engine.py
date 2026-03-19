"""LLM-powered NPC dialogue — multi-turn conversation scenes."""
from __future__ import annotations

import asyncio
from typing import Callable, TYPE_CHECKING

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
    query,
)

from actions import HELP_TEXT
from config import (
    MODEL,
    Faction,
    IntelAction,
    MAX_EXCHANGES_PER_SCENE,
    NARRATION_TIMEOUT,
    RATE_LIMIT_BACKOFF_FACTOR,
    RATE_LIMIT_BASE_DELAY,
    RATE_LIMIT_MAX_DELAY,
    RATE_LIMIT_MAX_RETRIES,
    SceneType,
)
from display import GameDisplay
from information_ledger import InformationLedger
from models import ConversationLog
from prompts.conversation import build_scene_system_prompt, _get_scene_description
from prompts.narration import (
    build_briefing_prompt,
    build_crossover_prompt,
    build_fallout_prompt,
    build_opening_narration_prompt,
)
from trust_system import get_trust_descriptor, get_suspicion_descriptor

if TYPE_CHECKING:
    from models import CharacterProfile, GameState, ReportAction, WorldState


class ConversationManager:
    """Manages LLM-powered conversation scenes and narration."""

    def __init__(self, display: GameDisplay):
        self.display = display

    async def run_narration(
        self, system_prompt: str, user_prompt: str,
    ) -> str:
        """One-shot narration via query() with timeout and rate limit retry."""
        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=MODEL,
            allowed_tools=[],
            permission_mode="bypassPermissions",
        )

        async def _collect() -> str:
            text_parts: list[str] = []
            async for msg in query(prompt=user_prompt, options=options):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)
            return "".join(text_parts)

        for attempt in range(RATE_LIMIT_MAX_RETRIES + 1):
            try:
                return await asyncio.wait_for(_collect(), timeout=NARRATION_TIMEOUT)
            except asyncio.TimeoutError:
                if attempt < RATE_LIMIT_MAX_RETRIES:
                    wait = min(
                        RATE_LIMIT_BASE_DELAY * (RATE_LIMIT_BACKOFF_FACTOR ** attempt),
                        RATE_LIMIT_MAX_DELAY,
                    )
                    self.display.show_message(f"[dim]Narration timed out, retrying in {wait:.0f}s...[/dim]")
                    await asyncio.sleep(wait)
                    continue
                return "[The narrator falls silent. The story continues regardless...]"
            except Exception as e:
                if "rate_limit" in str(e).lower() and attempt < RATE_LIMIT_MAX_RETRIES:
                    wait = min(
                        RATE_LIMIT_BASE_DELAY * (RATE_LIMIT_BACKOFF_FACTOR ** attempt),
                        RATE_LIMIT_MAX_DELAY,
                    )
                    self.display.show_message(f"[dim]Rate limited, waiting {wait:.0f}s...[/dim]")
                    await asyncio.sleep(wait)
                    continue
                return (
                    f"[The narrator falls silent. ({type(e).__name__}: {e}) "
                    "The story continues regardless...]"
                )

        return "[The narrator falls silent. The story continues regardless...]"

    async def run_opening(self, world: WorldState) -> str:
        """Generate and display the opening narration."""
        system, user = build_opening_narration_prompt(world)
        return await self.run_narration(system, user)

    async def run_briefing(
        self,
        game_state: GameState,
        world: WorldState,
        consequences: list[str] | None = None,
        visible_reactions: list | None = None,
    ) -> str:
        """Generate chapter briefing narration."""
        system, user = build_briefing_prompt(
            game_state, world, consequences, visible_reactions
        )
        return await self.run_narration(system, user)

    async def run_crossover(self, game_state: GameState) -> str:
        """Generate crossover narration."""
        system, user = build_crossover_prompt(game_state)
        return await self.run_narration(system, user)

    async def run_fallout(
        self, game_state: GameState, consequences: list[str],
        chapter_reactions: list | None = None,
    ) -> str:
        """Generate fallout narration."""
        system, user = build_fallout_prompt(
            game_state, consequences, chapter_reactions
        )
        return await self.run_narration(system, user)

    async def run_scene(
        self,
        scene_type: SceneType,
        characters: list[CharacterProfile],
        game_state: GameState,
        world: WorldState,
        ledger: InformationLedger,
        is_delivery_scene: bool = False,
        player_report: dict[str, str] | None = None,
        on_save: Callable[[], None] | None = None,
    ) -> ConversationLog:
        """Run an interactive multi-turn conversation scene.

        Returns a ConversationLog with all exchanges.
        """
        faction = characters[0].faction

        # Build intel to share (for Scene A / receiving scene)
        intel_to_share: list[str] | None = None
        if not is_delivery_scene:
            intel_to_share = []
            for intel_id in game_state.available_intel:
                intel_obj = next(
                    (i for i in world.intelligence_pipeline if i.id == intel_id),
                    None,
                )
                if intel_obj and intel_obj.source_faction == faction:
                    intel_to_share.append(
                        f"[{intel_obj.id}] {intel_obj.true_content}"
                    )

        # Build system prompt with memory injection
        ledger_summary = ledger.get_faction_report_summary(faction)
        scene_char_names = {c.name for c in characters}
        relevant_memories = [
            m for m in game_state.npc_memories if m.character_name in scene_char_names
        ]
        relevant_promises = [
            p for p in game_state.player_promises
            if p.get("faction") == faction.value
        ]
        # Filter faction reactions relevant to this faction
        relevant_reactions = [
            r for r in game_state.faction_reactions
            if r.acting_faction == faction.value
            and r.chapter_visible <= game_state.chapter
        ]
        system_prompt = build_scene_system_prompt(
            scene_type=scene_type,
            characters=characters,
            game_state=game_state,
            ledger_summary=ledger_summary,
            intel_to_share=intel_to_share,
            is_delivery_scene=is_delivery_scene,
            player_report=player_report,
            npc_memories=relevant_memories,
            player_promises=relevant_promises,
            faction_reactions=relevant_reactions,
        )

        # Initialize conversation log
        conv_log = ConversationLog(
            chapter=game_state.chapter,
            phase=game_state.phase,
            faction=faction,
            scene_type=scene_type,
            characters_present=[c.name for c in characters],
        )

        # Scene opening message with flavor text and character standings
        from config import FACTION_COLORS
        scene_labels = {
            SceneType.WAR_COUNCIL: "War Council",
            SceneType.PRIVATE_MEETING: "Private Meeting",
            SceneType.FEAST: "Feast",
            SceneType.INTERROGATION: "Interrogation",
            SceneType.FIELD_VISIT: "Field Visit",
        }
        scene_label = scene_labels.get(scene_type, "Meeting")
        faction_name = FACTION_COLORS[faction]["name"]
        scene_description = _get_scene_description(scene_type, faction_name)

        # Build character roster with trust/suspicion descriptors
        char_info = []
        for c in characters:
            trust = game_state.character_trust.get(c.name, 50)
            suspicion = game_state.character_suspicion.get(c.name, 15)
            trust_desc = get_trust_descriptor(trust)
            susp_desc = get_suspicion_descriptor(suspicion)
            alive = game_state.character_alive.get(c.name, True)
            char_info.append((c.name, c.role, trust_desc, susp_desc, alive))

        self.display.render_scene_opening(
            scene_label=scene_label,
            scene_description=scene_description,
            characters=char_info,
            faction=faction,
        )

        char_names = ", ".join(c.name for c in characters)
        opening_msg = (
            f"You enter the {scene_label}. Present: {char_names}. "
            f"The atmosphere is charged with unspoken tensions."
        )

        # Run multi-turn conversation
        options = ClaudeAgentOptions(
            system_prompt=system_prompt,
            model=MODEL,
            allowed_tools=[],
            permission_mode="bypassPermissions",
        )

        exchange_count = 0
        try:
            async with ClaudeSDKClient(options=options) as client:
                # Initial scene opening
                await client.query(opening_msg)
                response_text = await self._collect_response(client)

                self.display.render_conversation("Scene", response_text, faction)
                conv_log.exchanges.append(
                    {"role": "assistant", "text": response_text}
                )
                exchange_count += 1

                # Conversation loop
                while exchange_count < MAX_EXCHANGES_PER_SCENE:
                    self.display.render_conversation_prompt(
                        [c.name for c in characters]
                    )
                    player_input = self.display.prompt_input("> ")

                    # Check for exit commands
                    lower = player_input.strip().lower()
                    if lower in ("[done]", "done", "[leave]", "leave"):
                        break
                    if lower in ("[board]", "board"):
                        # Signal to caller that board was requested
                        conv_log.exchanges.append(
                            {"role": "system", "text": "[BOARD_REQUESTED]"}
                        )
                        continue
                    if lower in ("[save]", "save"):
                        if on_save:
                            try:
                                on_save()
                                self.display.show_message("[green]Game saved.[/green]")
                            except Exception:
                                self.display.show_error(
                                    "Could not save right now. Your progress is safe "
                                    "— the game auto-saves between chapters."
                                )
                        else:
                            self.display.show_message(
                                "[dim]Save is not available during this scene. "
                                "The game auto-saves between chapters.[/dim]"
                            )
                        continue
                    if lower in ("[help]", "help"):
                        self.display.show_message(HELP_TEXT)
                        continue

                    self.display.render_player_input(player_input)
                    conv_log.exchanges.append(
                        {"role": "player", "text": player_input}
                    )

                    # Send to LLM and get response
                    await client.query(player_input)
                    response_text = await self._collect_response(client)

                    self.display.render_conversation(
                        "Scene", response_text, faction
                    )
                    conv_log.exchanges.append(
                        {"role": "assistant", "text": response_text}
                    )
                    exchange_count += 1

        except Exception as e:
            self.display.show_error(
                f"The conversation was interrupted ({type(e).__name__}: {e}). "
                "Your progress in this scene has been preserved. "
                "The scene will end, but any intel already revealed is saved."
            )

        # For Scene A (receiving), mark all faction intel as known
        if not is_delivery_scene:
            for intel_id in game_state.available_intel:
                intel_obj = next(
                    (i for i in world.intelligence_pipeline if i.id == intel_id),
                    None,
                )
                if intel_obj and intel_obj.source_faction == faction:
                    if intel_id not in game_state.known_intel:
                        game_state.known_intel.append(intel_id)
                        conv_log.intel_revealed.append(intel_id)

        return conv_log

    async def _collect_response(self, client: ClaudeSDKClient) -> str:
        """Collect text from a client response."""
        parts: list[str] = []
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        parts.append(block.text)
        return "".join(parts) or "[No response]"
