"""Pydantic v2 data models for game state."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from config import ChapterPhase, Faction, IntelAction, IntelCategory, SceneType


# ──────────────────────────────────────────────
# Immutable world models (frozen=True)
# ──────────────────────────────────────────────

class CharacterProfile(BaseModel, frozen=True):
    name: str
    age: int
    role: str
    faction: Faction
    personality: list[str]
    speech_pattern: str
    goals: str
    secrets: str
    starting_trust: int = Field(ge=40, le=60)
    starting_suspicion: int = Field(ge=10, le=30)
    relationships: dict[str, str] = Field(default_factory=dict)
    knowledge: dict[int, list[str]] = Field(default_factory=dict)
    death_conditions: str = ""
    behavioral_notes: str = ""


class IntelligencePiece(BaseModel, frozen=True):
    id: str                    # format: ch{N}_{category}_{seq}
    chapter: int
    source_faction: Faction
    true_content: str
    significance: int = Field(ge=1, le=5)
    verifiability: int = Field(ge=1, le=5)
    category: IntelCategory
    potential_consequences: dict[str, str] = Field(default_factory=dict)
    related_characters: list[str] = Field(default_factory=list)
    war_tension_effect: dict[str, int] = Field(default_factory=dict)
    distortion_suggestions: list[str] = Field(default_factory=list)


class WildCardEvent(BaseModel, frozen=True):
    chapter: int
    description: str
    war_tension_effect: int = 0
    narrative_prompt: str = ""


class EndingConditions(BaseModel, frozen=True):
    peace_tension_max: int = 20
    peace_min_chapter: int = 5
    war_tension_min: int = 90
    architect_min_trust: int = 70
    architect_max_suspicion: int = 30
    ghost_min_trust: int = 40
    ghost_max_suspicion: int = 35
    martyr_min_suspicion_one: int = 60
    martyr_min_trust_other: int = 65
    prisoner_min_suspicion: int = 70


class WorldState(BaseModel, frozen=True):
    inciting_incident: str
    ironveil_background: str
    embercrown_background: str
    ashenmere_description: str
    characters: list[CharacterProfile]
    intelligence_pipeline: list[IntelligencePiece]
    wild_card_events: list[WildCardEvent]
    ending_conditions: EndingConditions = Field(default_factory=EndingConditions)


# ──────────────────────────────────────────────
# Mutable game-state models
# ──────────────────────────────────────────────

class LedgerEntry(BaseModel):
    intel_id: str
    chapter: int
    true_content: str
    told_ironveil: str | None = None
    told_embercrown: str | None = None
    action_ironveil: IntelAction | None = None
    action_embercrown: IntelAction | None = None
    distortion_details: str | None = None
    fabrication_details: str | None = None
    verified_ironveil: bool = False
    verified_embercrown: bool = False
    verification_result_ironveil: bool | None = None
    verification_result_embercrown: bool | None = None
    consequence: str = ""
    contradiction_with: list[str] = Field(default_factory=list)
    leak_discovered_by: list[str] = Field(default_factory=list)
    retracted_for_ironveil: bool = False
    retracted_for_embercrown: bool = False


class FactionReaction(BaseModel):
    id: str                          # "react_ch{N}_{faction}_{seq}"
    chapter_generated: int
    chapter_visible: int             # chapter_generated + 1
    acting_faction: str              # "ironveil" or "embercrown"
    trigger_intel_id: str
    trigger_action: IntelAction      # truthful/distorted/fabricated
    reaction_type: str               # "military_mobilization", "wrongful_arrest", etc.
    reaction_description: str        # narrative text
    mechanical_effects: dict = Field(default_factory=dict)
    based_on_false_intel: bool = False
    outcome_known: bool = False
    retroactive_suspicion_applied: bool = False
    spawned_intel_id: str | None = None
    affected_characters: list[str] = Field(default_factory=list)
    narrative_for_npcs: str = ""


class LeakEvent(BaseModel):
    chapter: int
    intel_id: str
    discovering_faction: str
    probability: float
    is_cascade: bool = False
    cascade_depth: int = 0
    narrative: str = ""


class NPCMemory(BaseModel):
    character_name: str
    chapter: int
    memory_text: str
    emotional_tag: str  # suspicious | grateful | intrigued | alarmed | trusting
    player_quote: str = ""
    importance: int = Field(ge=1, le=5, default=3)


class SlipDetection(BaseModel):
    slip_type: str  # cross_faction_knowledge | contradiction | broken_promise
    description: str
    severity: int = Field(ge=1, le=5)
    detecting_character: str
    evidence_quote: str


class SceneAnalysis(BaseModel):
    chapter: int
    phase: ChapterPhase
    faction: Faction
    memories: list[NPCMemory] = Field(default_factory=list)
    slips: list[SlipDetection] = Field(default_factory=list)
    trust_adjustments: dict[str, int] = Field(default_factory=dict)
    suspicion_adjustments: dict[str, int] = Field(default_factory=dict)
    faction_trust_delta: int = 0
    faction_suspicion_delta: int = 0
    conversation_quality: str = ""
    promises_made: list[str] = Field(default_factory=list)
    promises_fulfilled: list[str] = Field(default_factory=list)


class ConversationLog(BaseModel):
    chapter: int
    phase: ChapterPhase
    faction: Faction
    scene_type: SceneType
    characters_present: list[str]
    exchanges: list[dict] = Field(default_factory=list)
    intel_revealed: list[str] = Field(default_factory=list)
    intel_delivered: list[str] = Field(default_factory=list)


class GameState(BaseModel):
    chapter: int = 1
    phase: ChapterPhase = ChapterPhase.BRIEFING
    ironveil_trust: int = 50
    ironveil_suspicion: int = 15
    embercrown_trust: int = 50
    embercrown_suspicion: int = 15
    first_chapter_hints: bool = True
    difficulty: str = "standard"  # novice, standard, spymaster
    character_trust: dict[str, int] = Field(default_factory=dict)
    character_suspicion: dict[str, int] = Field(default_factory=dict)
    character_alive: dict[str, bool] = Field(default_factory=dict)
    war_tension: int = 50
    war_started: bool = False
    war_victor: str | None = None
    scene_a_faction: Faction = Faction.IRONVEIL
    available_intel: list[str] = Field(default_factory=list)
    known_intel: list[str] = Field(default_factory=list)
    conversations: list[ConversationLog] = Field(default_factory=list)
    ledger_entries: list[LedgerEntry] = Field(default_factory=list)
    npc_memories: list[NPCMemory] = Field(default_factory=list)
    scene_analyses: list[SceneAnalysis] = Field(default_factory=list)
    player_promises: list[dict] = Field(default_factory=list)
    leak_events: list[LeakEvent] = Field(default_factory=list)
    faction_reactions: list[FactionReaction] = Field(default_factory=list)
    dynamic_intel: list[IntelligencePiece] = Field(default_factory=list)


class ReportAction(BaseModel):
    intel_id: str
    action: IntelAction
    player_version: str | None = None
    risk_assessment: str = ""


class SaveData(BaseModel):
    world_state: WorldState
    game_state: GameState
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    slot: int = 0
