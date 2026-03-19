# Both Sides

A strategy game where you play a double agent feeding intelligence to two rival factions. What you tell each side — truth, lies, or silence — shapes troop movements, diplomatic crises, and political purges. Then the factions act on your intelligence, and the consequences compound.

## The Game

You serve as a trusted agent to both the Ironveil Compact and the Embercrown Reach, two nations on the brink of war. Each chapter, you visit one faction to gather intelligence, then cross over to the other to deliver a report. For every piece of intel, you choose:

- **Truth** — builds trust, but accurate military intel accelerates war
- **Distortion** — twist the facts for better rewards, risk getting caught
- **Fabrication** — invent threats from nothing, high reward if believed, devastating if exposed
- **Withhold** — say nothing, safe but strategically empty

NPCs remember what you've told them. Factions verify your reports. Contradictions between what you told each side can leak across the border. And now, factions take visible action based on your intelligence — mobilizing armies against phantom threats, arresting innocent officials, sending diplomats on fool's errands.

When a fabrication is eventually uncovered, trust craters and suspicion spikes. The lies you told three chapters ago come back to end you.

## Architecture

The game separates deterministic mechanics from LLM-generated narrative:

- **State machine** (`state_machine.py`) — all trust, suspicion, war tension, verification, and consequence logic is deterministic and fully tested
- **Conversation engine** (`conversation_engine.py`) — multi-turn NPC dialogue powered by Claude, with character personalities, memories, and suspicion-driven behavior
- **Faction reactions** (`faction_reactions.py`) — template-driven system where factions take strategic actions based on reported intel, generating counter-intelligence visible to the opposing side
- **Verification engine** (`verification_engine.py`) — probability-based detection of distortions and fabrications, scaling with intel verifiability and faction suspicion
- **Intel leak system** (`intel_leaks.py`) — cross-faction leak detection with cascading discovery chains
- **Rich terminal UI** (`display.py`) — faction-themed panels, war tension bars, chapter summaries

All game state is Pydantic models. Save/load works via JSON serialization. 427 tests cover the mechanical layer.

```
models.py              Data models (GameState, WorldState, FactionReaction, etc.)
config.py              Enums, constants, consequence tables, difficulty modes
state_machine.py       Consequence orchestration, chapter advancement
faction_reactions.py   Reaction templates, counter-intel generation, outcome evaluation
verification_engine.py Deception detection probability and rolls
intel_leaks.py         Cross-faction leak system with cascading discovery
trust_system.py        Trust/suspicion tracking and thresholds
war_tension.py         War tension tracking and win/loss conditions
conversation_engine.py LLM-powered multi-turn NPC dialogue
display.py             Rich terminal UI with faction theming
report_builder.py      Interactive report construction interface
intelligence_board.py  Intel review and filtering UI
information_ledger.py  Tracks what was told to whom
scene_evaluator.py     NPC memory extraction and slip detection
endings.py             8 archetypal endings based on final state
main.py                Chapter loop and game orchestration
prompts/               LLM prompt builders for narration, conversation, analysis
tests/                 427 tests covering all mechanical systems
```

## Requirements

- Python 3.11+
- A Claude subscription (Max or Pro) with `claude` CLI authenticated

## Setup

```bash
git clone https://github.com/jimmc414/both-sides.git
cd both-sides
pip install -r requirements.txt

# Verify Claude authentication
claude doctor

# Play
python main.py
```

The game uses Claude Max OAuth automatically via `~/.claude/.credentials.json`. No API key needed.

## How a Chapter Plays

```
Chapter 3 — Briefing
  War tension: 67% (Volatile)
  Ironveil trust: 58 (Warm) | Embercrown trust: 44 (Cool)

Scene A: Visit Ironveil war council
  > Talk to General Thane and Spymaster Vael
  > Learn: "Embercrown is moving 3,000 troops to the southern pass"

Crossover: Review intel, build your report for Embercrown
  [1] Truthful  [2] Withhold  [3] Distort  [4] Fabricate
  > You fabricate: "Ironveil is planning a preemptive strike through Ashenmere"

Scene B: Deliver report to Embercrown
  > Lord Cassius thanks you for the warning. Forces are scrambled.

Consequences:
  Fabrication accepted (+3 trust, +1 suspicion)
  Embercrown mobilizes forces against a nonexistent threat (+7 war tension)
  Counter-intel generated: Ironveil scouts spot the mobilization

Chapter 5:
  Embercrown discovers the strike never happened.
  Trust: -15. Suspicion: +20. "Your lies bear bitter fruit."
```

## Difficulty Modes

| Mode | Verification | Leak Risk | Starting Trust |
|------|-------------|-----------|---------------|
| Novice | -10% base | Half | 60 |
| Standard | Baseline | Normal | 50 |
| Spymaster | +5% base | Doubled | 40 |

## Endings

Your final trust, suspicion, and war tension determine one of 8 endings:

- **The Architect** — both sides trust you completely, neither suspects
- **The Operative** — one faction's champion, the other's useful asset
- **The Diplomat** — genuine bridge between factions
- **The Ghost** — passed through both worlds unseen
- **The Prisoner** — exposed on all sides
- **The Martyr** — beloved by one, condemned by the other
- **Faction's Agent** — your loyalty was less ambiguous than you thought
- **The Survivor** — neither hero nor villain

After the ending, the game replays your entire ledger chapter by chapter — every truth, every lie, every consequence — with dramatic narration.

## License

MIT
