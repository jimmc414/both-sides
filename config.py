"""Game configuration constants and enums."""
import os
from enum import Enum
from types import MappingProxyType

# SDK auth guard — ensure Max OAuth is used, not API key billing
if "ANTHROPIC_API_KEY" in os.environ:
    del os.environ["ANTHROPIC_API_KEY"]

MODEL = "claude-sonnet-4-20250514"


# --- Enums ---

class Faction(str, Enum):
    IRONVEIL = "ironveil"
    EMBERCROWN = "embercrown"


class ChapterPhase(str, Enum):
    BRIEFING = "briefing"
    SCENE_A = "scene_a"
    CROSSOVER = "crossover"
    SCENE_B = "scene_b"
    CONSEQUENCES = "consequences"
    FALLOUT = "fallout"


class IntelAction(str, Enum):
    TRUTHFUL = "truthful"
    DISTORTED = "distorted"
    FABRICATED = "fabricated"
    WITHHELD = "withheld"


class SceneType(str, Enum):
    WAR_COUNCIL = "war_council"
    PRIVATE_MEETING = "private_meeting"
    FEAST = "feast"
    INTERROGATION = "interrogation"
    FIELD_VISIT = "field_visit"


class IntelCategory(str, Enum):
    MILITARY = "military"
    POLITICAL = "political"
    ECONOMIC = "economic"
    PERSONAL = "personal"


# --- Faction Colors ---

FACTION_COLORS = MappingProxyType({
    Faction.IRONVEIL: {
        "primary": "#6B8EAF",
        "secondary": "#E8EEF2",
        "name": "Ironveil Compact",
    },
    Faction.EMBERCROWN: {
        "primary": "#B87333",
        "secondary": "#DAA520",
        "name": "Embercrown Reach",
    },
})


# --- Consequence Table ---
# Keys: (IntelAction, was_checked: bool, check_passed: bool | None)
# Values: trust_delta, suspicion_delta, description

CONSEQUENCE_TABLE = MappingProxyType({
    # Truthful: safe play, but modest gains — truth alone won't win the game
    (IntelAction.TRUTHFUL, False, None):  {"trust": +4,  "suspicion": -1,  "desc": "Accurate report accepted — your reliability noted"},
    (IntelAction.TRUTHFUL, True,  True):  {"trust": +6,  "suspicion": -2,  "desc": "Report verified as accurate — trust boosted"},

    # Withheld: near-neutral — silence is safe but unrewarding
    (IntelAction.WITHHELD, False, None):  {"trust": -1,  "suspicion": +1,  "desc": "No report on this matter — a raised eyebrow, nothing more"},

    # Distorted: higher unchecked reward than truth to compensate for downside risk
    (IntelAction.DISTORTED, False, None): {"trust": +5,  "suspicion": -1,  "desc": "Twisted report accepted at face value"},
    (IntelAction.DISTORTED, True,  True): {"trust": +5,  "suspicion": -1,  "desc": "Report checked — distortion not caught"},
    (IntelAction.DISTORTED, True,  False):{"trust": -6,  "suspicion": +10, "desc": "Distortion detected — trust damaged"},

    # Fabricated: moderate unchecked reward, severe when caught
    (IntelAction.FABRICATED, False, None):{"trust": +3,  "suspicion": +1,  "desc": "Fabrication accepted — but something feels off"},
    (IntelAction.FABRICATED, True,  False):{"trust": -12, "suspicion": +16, "desc": "Fabrication exposed — severe consequences"},
})


# --- Suspicion Thresholds ---

SUSPICION_THRESHOLDS = MappingProxyType({
    31:  "scrutiny",       # Increased questioning
    51:  "exclusion",      # Excluded from sensitive meetings
    71:  "confrontation",  # Direct accusation scenes
    81:  "investigation",  # Active investigation
    100: "exposed",        # Game over — cover blown
})


# --- War Tension ---

WAR_TENSION_START = 50
WAR_TENSION_PEACE = 20    # tension <= this triggers peace ending (chapter >= 5)
WAR_TENSION_WAR = 90      # tension >= this triggers war

# Truth tax: truthful reports of high-significance intel accelerate war
TRUTH_TAX_MIN_SIGNIFICANCE = 3       # Only applies to significance >= this
TRUTH_TAX_TENSION_PER_SIGNIFICANCE = 1  # +1 per significance point above threshold

# Withholding peace bonus: silence de-escalates tension
WITHHOLD_TENSION_REDUCTION_PER_SIGNIFICANCE = -1  # -1 per significance point

TENSION_DESCRIPTORS = (
    (0,  10,  "Deep Peace",    "green"),
    (11, 20,  "Stable",        "green"),
    (21, 35,  "Uneasy",        "yellow"),
    (36, 50,  "Tense",         "yellow"),
    (51, 65,  "Volatile",      "dark_orange"),
    (66, 80,  "Brink of War",  "red"),
    (81, 90,  "Mobilizing",    "red"),
    (91, 100, "Total War",     "bold red"),
)


# --- Trust Descriptors ---

TRUST_DESCRIPTORS = (
    (0,  15,  "Hostile"),
    (16, 30,  "Cold"),
    (31, 45,  "Cool"),
    (46, 55,  "Neutral"),
    (56, 65,  "Warm"),
    (66, 80,  "Friendly"),
    (81, 90,  "Devoted"),
    (91, 100, "Unshakeable"),
)


# --- NPC Memory & Scene Analysis ---

MAX_MEMORIES_PER_CHARACTER = 5

SLIP_SEVERITY_CONSEQUENCES = MappingProxyType({
    1: {"suspicion": 2,  "trust": -1},
    2: {"suspicion": 5,  "trust": -2},
    3: {"suspicion": 8,  "trust": -3},
    4: {"suspicion": 12, "trust": -5},
    5: {"suspicion": 18, "trust": -8},
})

CONVERSATION_QUALITY_MODIFIERS = MappingProxyType({
    "excellent": {"trust": 3, "suspicion": -2},
    "good":      {"trust": 1, "suspicion": -1},
    "neutral":   {"trust": 0, "suspicion": 0},
    "poor":      {"trust": -2, "suspicion": 1},
    "hostile":   {"trust": -5, "suspicion": 3},
})


# --- Intel Leak System ---

LEAK_BASE_PROBABILITY_PER_CHAPTER = 0.03
LEAK_HIGH_TENSION_BONUS = 0.05
LEAK_CONTRADICTION_BONUS = 0.03
LEAK_HIGH_SIGNIFICANCE_BONUS = 0.02
LEAK_TRUTH_ONE_SIDE_PENALTY = -0.05
LEAK_PROBABILITY_CAP = 0.25
CASCADE_BASE_PROBABILITY = 0.30
CASCADE_ESCALATION_BONUS = 0.10
CASCADE_MAX_DISCOVERIES = 3
LEAK_BETRAYAL_TRUST_PENALTY = -5
LEAK_BETRAYAL_SUSPICION_BONUS = 8
LEAK_WAR_TENSION_PER_DISCOVERY = 3
RETRACT_TRUST_COST = -5
RETRACT_SUSPICION_COST = 5


# --- Difficulty Modes ---

DIFFICULTY_MODES = MappingProxyType({
    "novice": {
        "verification_rate_modifier": -0.10,  # -10% base verification
        "leak_probability_modifier": 0.5,     # halved leak chance
        "starting_trust": 60,
        "starting_suspicion": 10,
        "hints": True,
        "description": "Forgiving verification, lower leak risk, higher starting trust",
    },
    "standard": {
        "verification_rate_modifier": 0.0,
        "leak_probability_modifier": 1.0,
        "starting_trust": 50,
        "starting_suspicion": 15,
        "hints": True,
        "description": "Balanced risk and reward — the intended experience",
    },
    "spymaster": {
        "verification_rate_modifier": +0.05,  # +5% base verification
        "leak_probability_modifier": 2.0,     # doubled leak chance
        "starting_trust": 40,
        "starting_suspicion": 25,
        "hints": False,
        "description": "Aggressive verification, doubled leak risk, lower starting trust",
    },
})


# --- Game Limits ---

MAX_EXCHANGES_PER_SCENE = 20
MAX_CHAPTERS = 10
SAVE_SLOTS = 3
