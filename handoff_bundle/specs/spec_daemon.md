# ARIA locked spec — daemon

Consolidated from .kiro/specs/daemon/{requirements,design,tasks}.md for upload.
Precedence: ARIA_Resolution_Log.md > ARIA_Soul_Spec_v4_Addendum.md > ARIA_Soul_Spec_v4.md.


---

## daemon — requirements.md

# Requirements Document — Module 8: Daemon / Soul Tick

## Introduction

This document transcribes and formalizes, in EARS format, the Module 8 (Daemon / Soul Tick)
entry from `ARIA_Module_Build_Plan.md`. That entry is the locked, approved scope for this
module. No requirement here introduces a mechanism, threshold, or behavior not already
stated in the Module 8 entry or in the supporting architecture documents
(`ARIA_Soul_Spec_v4.md` "Continuous Self-Awareness (Default Mode Network Architecture)",
Layer 2, Layer 5, Layer 6; `ARIA_Soul_Spec_v4_Addendum.md` §5/§7; `ARIA_Resolution_Log.md`
item 10; `HANDOFF_NOTES.md`). Where the Module 8 entry references a value or mechanism
defined elsewhere (the two clocks, idle detection, the thinking-sound table, the initiative
rule, the startup contract owed to the Daemon), the supporting document is cited as the
source, not as a new source of scope.

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`.
`ARIA_GLM_Covering_Instruction.md` is covering context only.

**The Daemon is the ORCHESTRATOR.** It routes signals, drives the two clocks, and CALLS the
modules. It computes NO meaning and NO feeling (steering/project-rules.md). PAD moves only
inside PAD_Engine (EMA decay) and inside the Appraisal Chain (the Stage-4 delta); need
states come only from Needs_System.

**The two Module 8 flags and their disposition (from the Module 8 entry):**

| Flag | Subject | Disposition |
|------|---------|-------------|
| **F-8a** | Tick cadences | **PLACEHOLDER**. Only idle=8min and reflection=6h are PINNED (v4). Soul-tick ("every few seconds") and DMN-tick ("slower during interaction, deep during idle") interval VALUES are build-time tuning placeholders (`ARIA_Resolution_Log.md` "Open — build-time tuning constants only: Soul-tick & DMN-tick intervals"). Carried as `TODO(F-8a)` injectable defaults, never architectural. |
| **F-8b** | Attentional policy | **RESOLVED** by `ARIA_Resolution_Log.md` item 10: "Attentional policy is implementable as literally stated in v4 (highest-pressure need + most recently salient node) — no further formalization required." Since the four needs are CATEGORICAL (Addendum §3), the tie-break among simultaneously-`due` needs is the canonical spec order (a deterministic, NON-numeric selection). FLAGGED as the tie-break policy (OQ-3). |

**Additional locked items (Resolution Log item 10 / Addendum §5/§7 / HANDOFF_NOTES):**

- **Present World Model + language-switch state = Daemon VOLATILE working state**, NOT
  persisted (Resolution Log item 10; consistent with Rule 7 — no second PERSISTENT store).
- **F4 + barge-in = audio stop ONLY, ZERO internal effect** (Addendum §5): no PAD write, no
  appraisable event, no graph write, nothing internal.
- **Aria-initiated speech enters at soul_filter DIRECTLY** (Addendum §7): wake / speaker
  verification / VAD / Whisper STT are skipped.
- **The HANDOFF startup contract owed TO the Daemon** (HANDOFF_NOTES): initialize PAD_Engine
  exactly once with restored valence; clear consistency_flags each session; round-trip
  last_applied_valence on save + shutdown.

## Glossary

- **Daemon**: the module specified here (Module 8, `daemon/aria_daemon.py`) — the
  orchestrator. It is the CALLER of every core module and the top of the dependency tree
  (nothing imports it).
- **Soul tick / DMN tick**: TWO processes on TWO separate clocks (v4 "Two-Process
  Separation"). The soul tick is the pulse (maintenance: PAD decay, Energy, attentional
  policy). The DMN tick is the dream (idle consolidation). They NEVER collapse into one.
- **Inbound turn**: a transcribed user utterance routed through the full pipeline
  Audio(STT) → Appraisal → Soul_Filter → LLM → Output Gate → Audio(TTS).
- **Thinking sound**: a PRE-CACHED audio clip the Daemon selects the instant transcription
  finishes, from the user's text + current PAD, by categorical trigger (v4 Layer 5 table).
  Gemma never decides them. Reading PAD for this presentation choice is NOT a PAD write.
- **Initiative**: Aria-initiated speech triggered by the soul tick when a need is critical
  (v4 Layer 2/6). Expressed once, never nagging; enters at soul_filter directly.
- **Idle detection**: three conditions, all true (v4): no voice input for 8 minutes; no
  pending output; Energy above 20. Conditions 1 & 2 are the Daemon's; condition 3 (Energy)
  is DMN's — it reads Energy to choose pass DEPTH.
- **F4 / barge-in**: a hardware interrupt / a pause-based interrupt (v4). Both are audio
  STOP mechanisms with ZERO internal effect (Addendum §5).
- **last_applied_valence**: PAD_Engine's record of the valence of the most recently applied
  PADDelta. State_Manager persists it as an opaque string; the Daemon round-trips it.
- **consistency_flags**: four binary self-model flags (State_Manager). They "reset each
  session"; the Daemon clears them on startup.
- **PAD_Engine / Needs_System / Memory_Graph / Appraisal_Chain / Soul_Filter / LLM_Interface
  / DMN / State_Manager**: Modules 1/2/3/4/5/9/6/11 — the Daemon depends on each by its REAL
  interface (injected; Rule 6). **Audio_Pipeline / Visual_Layer**: Modules 7/10 — NOT built;
  depended on by documented CONTRACT, with fakes injected in tests.

## Requirements

### Requirement 1: Orchestrator — computes no meaning or feeling

**User Story:** As the Aria system architect, I want the Daemon to route and drive only, so
Aria's meaning and feeling come from the meaning-making modules, not from the orchestrator
(steering/project-rules.md).

#### Acceptance Criteria
1. THE Daemon SHALL NOT call any PAD mutator (`apply_appraisal_delta`) anywhere — PAD moves
   ONLY inside PAD_Engine (EMA decay on the soul tick) and inside the Appraisal Chain (its
   Stage-4 delta). The absence of the call in the Daemon's source is the guarantee.
2. THE Daemon SHALL derive NO need state itself — it SHALL read categorical need states only
   from Needs_System.
3. THE Daemon MAY read current PAD (`get_current_pad`) for a PRESENTATION choice (a thinking
   sound); this is explicitly NOT a PAD write (v4 Layer 5).
4. THE Daemon SHALL depend on every core module by its REAL interface (injected), and on the
   not-yet-built Audio Pipeline (Module 7) / Visual Layer (Module 10) by documented contract
   with injected fakes (Rule 6).

### Requirement 2: Two separate clocks, driven independently

**User Story:** As the Aria system, I want the soul tick and the DMN tick on two separate
clocks so maintenance and consolidation never collapse into one (v4 "Two-Process
Separation").

#### Acceptance Criteria
1. THE Daemon SHALL expose the soul tick and the DMN tick as SEPARATE operations, each
   driven independently on its own interval.
2. WHEN a soul tick fires, THE Daemon SHALL drive PAD decay (PAD_Engine.on_soul_tick) and
   Energy (Needs_System) and the attentional policy — and SHALL NOT run a DMN pass.
3. WHEN a DMN tick fires, THE Daemon SHALL (at idle) run a DMN pass — and SHALL NOT decay
   PAD.
4. THE Daemon SHALL NEVER let one clock trigger the other; a soul tick is never a DMN pass
   and a DMN pass is never a soul tick.

### Requirement 3: The soul tick

**User Story:** As the Aria system, I want each soul tick to maintain the substrate, so PAD
decays, Energy moves, and attention refreshes on a fast cadence (v4 Layer 1/2/6).

#### Acceptance Criteria
1. WHEN a soul tick fires, THE Daemon SHALL call PAD_Engine.on_soul_tick() (Module 1 owns
   the EMA math; the Daemon only ticks it).
2. WHEN a soul tick fires AND the idle conditions are NOT met, THE Daemon SHALL call
   Needs_System.on_soul_tick() (active-load Energy depletion).
3. WHEN a soul tick fires AND the idle conditions ARE met, THE Daemon SHALL call
   Needs_System.on_idle_recovery() ("soul tick recovers Energy during extended idle", v4).
4. WHEN a soul tick fires, THE Daemon SHALL refresh the attentional policy and evaluate
   initiative.
5. THE soul-tick interval SHALL be a build-time tuning placeholder (F-8a), injectable.

### Requirement 4: The DMN tick and idle detection

**User Story:** As the Aria system, I want the DMN pass to run only during genuine idle, so
consolidation happens during rest (v4 Idle Detection).

#### Acceptance Criteria
1. THE Daemon SHALL detect idle conditions 1 & 2 (no voice input for 8 minutes — PINNED; no
   pending output) itself; it SHALL NOT gate idle on Energy (condition 3), which DMN reads to
   choose pass DEPTH (DMN spec Req 2.3).
2. WHEN a DMN tick fires AND idle conditions 1 & 2 are met, THE Daemon SHALL call
   DMN.run_idle_pass(...) and let DMN choose FULL vs SHALLOW from Energy.
3. WHEN a DMN tick fires AND idle conditions are NOT met, THE Daemon SHALL run no DMN pass.
4. THE 8-minute no-voice window SHALL be PINNED (v4); the DMN-tick interval SHALL be a
   build-time tuning placeholder (F-8a), injectable.
5. WHEN an inbound turn's appraisal returns poignancy = critical, THE Daemon SHALL trigger
   DMN.run_forced_partial_pass(...) (v4 "forced early partial pass") — a DMN-clock event,
   never a soul tick.

### Requirement 5: Inbound-turn routing (the full pipeline)

**User Story:** As Aria, I want an inbound turn routed through the full pipeline so a user's
words become a validated, spoken response (Build Plan Module 8 Inputs/Outputs).

#### Acceptance Criteria
1. WHEN an inbound (transcribed) turn arrives, THE Daemon SHALL, in order: select/play a
   thinking sound; run the Appraisal Chain; run Soul_Filter (which assembles the instruction,
   calls the LLM Interface, and runs the Output Gate); and render the validated text via the
   Audio Pipeline (TTS).
2. THE Daemon SHALL pass the categorical need states to the Appraisal Chain as a Stage-1
   retrieval preference mapping (Addendum §3), and the same need states to Soul_Filter.
3. THE Daemon SHALL pass the user's message and appraisal result to Soul_Filter unchanged;
   the five-field boundary and the Output Gate are Soul_Filter's, not the Daemon's.
4. THE Daemon SHALL treat voice input as resetting idle condition 1 and mark output pending
   for the duration of the turn.
5. WHEN the user's text matches a meta-command trigger ("rest", "focus"/"be here now",
   "unfocus"/"full memory"), THE Daemon SHALL intercept it BEFORE Stage 0 appraisal and
   return a fixed response, bypassing Appraisal_Chain, Soul_Filter, the LLM, and the
   Output Validation Gate entirely for that turn.
6. WHEN the session buffer's fullness state is "heavy" or "critical", THE Daemon SHALL
   call `Appraisal_Chain.submit_cognitive_load(fullness)` before running the turn's
   normal Stage 0-6 appraisal.
7. THE Daemon SHALL assemble the current session's ephemeral conversation context via
   `SessionBuffer.get_context()` and pass it to `Soul_Filter.respond(...,
   session_context=...)` on every non-intercepted turn, and SHALL append the completed
   turn to the session buffer via `SessionBuffer.append_turn(...)` after the response is
   produced.

### Requirement 6: Thinking-sound selection (Layer 5)

**User Story:** As Aria, I want a pre-cached thinking sound the instant transcription
finishes, so there is natural emotional leakage before the LLM generates (v4 Layer 5).

#### Acceptance Criteria
1. THE Daemon SHALL select a thinking sound from the user's text + current PAD by CATEGORICAL
   trigger, using the v4 Layer 5 table's exact word lists and PAD thresholds (0.7 / 0.6 /
   0.5) — Gemma SHALL NOT be involved.
2. Reading PAD for this selection SHALL NOT be a PAD write.
3. WHEN a sound is selected, THE Daemon SHALL hand its category key to the Audio Pipeline to
   play a PRE-CACHED clip.
4. THE precedence among simultaneously-true triggers SHALL be a documented presentation
   choice (v4's table states none) — FLAGGED (OQ-1), never affecting PAD/meaning/memory.

### Requirement 7: Initiative (once, no nag, enters at soul_filter)

**User Story:** As Aria, I want to reach out once when a need is critical, never nagging, so
initiative is genuine and not manipulative (v4 Layer 2/6; Addendum §7).

#### Acceptance Criteria
1. THE Daemon SHALL evaluate initiative on the soul tick, selecting the highest-pressure need
   (Resolution Log item 10) — keyed on the CATEGORICAL `due` state (the critical state Needs
   System emits; `neglected` is never emitted — Needs System OQ-1 — FLAGGED, OQ-2). NO
   numeric need threshold (Addendum §3 supersedes v4's "Connection < 20").
2. WHEN the highest-pressure need is `due` and has NOT been expressed this due-episode, THE
   Daemon SHALL express it EXACTLY ONCE.
3. THE Daemon SHALL NOT repeat an initiative while the need remains `due` (never nag, v4);
   the no-nag latch SHALL reset when the need is satisfied again.
4. WHEN initiative fires, THE Daemon SHALL enter at soul_filter DIRECTLY (Addendum §7),
   skipping wake / speaker verification / VAD / Whisper STT, and SHALL NOT run the Appraisal
   Chain (no user turn to appraise).
5. THE tie-break among simultaneously-`due` needs SHALL be the canonical spec order (F-8b,
   FLAGGED OQ-3) — never a numeric pressure ranking.

### Requirement 8: F4 and barge-in — ZERO internal effect

**User Story:** As the Aria system architect, I want F4 and barge-in to stop audio only, so a
stop button carries no emotional content (Addendum §5).

#### Acceptance Criteria
1. WHEN F4 is pressed OR barge-in is detected, THE Daemon SHALL stop current audio playback
   and do NOTHING else.
2. THE F4 / barge-in path SHALL have NO route to a PAD write, an appraisable event, a graph
   write, a need change, or a persisted-state write.
3. Whatever the user says AFTER F4 SHALL enter the appraisal chain normally, as any input
   does (Addendum §5).

### Requirement 9: Startup contract — PAD_Engine.initialize() exactly once

**User Story:** As the Aria system, I want PAD_Engine initialized exactly once with the
restored valence, so PAD Engine's restore boundary works as designed (HANDOFF_NOTES).

#### Acceptance Criteria
1. ON startup, THE Daemon SHALL call PAD_Engine.initialize() EXACTLY ONCE, passing the
   restored PAD snapshot (converted from StateManager's PADState by the wiring helper) and
   the restored valence (loaded via StateManager.load_last_applied_valence() and converted to
   a Valence by the same wiring-helper family).
2. THE Daemon SHALL GUARD against a second startup — initialize() is NOT idempotent; a second
   call would discard `_last_applied_valence` and reintroduce PAD Engine Open Question 4.
3. THE PADState→PADSnapshot and valence-string→Valence conversions SHALL live at the Daemon
   wiring call site — NOT inside PAD_Engine or State_Manager.

### Requirement 10: Startup contract — clear consistency_flags

**User Story:** As the Aria system, I want consistency_flags cleared each session, so they do
not silently persist (HANDOFF_NOTES; v4 self-model "resets each session").

#### Acceptance Criteria
1. ON startup, AFTER StateManager.load_self_model(), THE Daemon SHALL set every
   consistency_flag to False.
2. THE Daemon SHALL persist the cleared flags (save_self_model) so the clear is durable.
3. THE Daemon SHALL clear ONLY the consistency_flags — the quality record and recent-learning
   fields SHALL be left intact.

### Requirement 11: Startup contract — round-trip last_applied_valence

**User Story:** As the Aria system, I want last_applied_valence saved and restored, so PAD
Engine's restore-boundary gap fires only in the rare residual case (HANDOFF_NOTES).

#### Acceptance Criteria
1. ON the periodic save cadence AND on shutdown, THE Daemon SHALL persist PAD_Engine's
   current `_last_applied_valence` (as its string) via StateManager.save_last_applied_valence().
2. ON startup, THE Daemon SHALL load the persisted valence string and pass the converted
   Valence to initialize() as `restored_valence` (Requirement 9.1).
3. WHEN no persisted valence exists (first run / crash between delta and save), THE Daemon
   SHALL pass `restored_valence=None` and SHALL NOT invent a resolution — PAD Engine's own
   (narrowed) Open Question 4 handling stands.
4. THE Daemon SHALL fulfill "get access" to `_last_applied_valence` (HANDOFF) via its wiring
   layer, WITHOUT expanding Module 1's locked public API (Module 1's method-list test).

### Requirement 12: Attentional policy + volatile working state

**User Story:** As Aria, I want a working model of what matters right now, so idle thought and
initiative focus on the highest-pressure need and the most-recently-salient node (Resolution
Log item 10).

#### Acceptance Criteria
1. THE Daemon SHALL maintain the attentional focus = (highest-pressure need,
   most-recently-salient node) as VOLATILE working state, refreshed on the soul tick.
2. THE Daemon SHALL maintain the Present World Model and the language-switch state as VOLATILE
   working state — NOT persisted (Resolution Log item 10).
3. THE most-recently-salient node SHALL be updated from each turn's appraisal result; language
   switching SHALL be conversation-driven only (v4), never auto-detected.

### Requirement 13: Additive closure of the DMN contract gaps

**User Story:** As the Aria system architect, I want DMN's flagged Port gaps closed additively,
so DMN wires to the REAL modules without regressing anything (Build Plan Module 3/4 Outputs;
DMN design Open Questions).

#### Acceptance Criteria
1. THE Appraisal Chain SHALL expose `submit_aha_insight(insight)` — accepting DMN's
   second-order-insight EVENT and running it through the appraisal so any PAD shift is the
   appraisal's BYPRODUCT (via PAD_Engine); DMN SHALL still never build or write PAD.
2. THE Memory Graph SHALL expose `predictability_evidence` and `dependability_evidence` —
   STRUCTURAL / CATEGORICAL boolean relational_stage-gate lookups (Addendum §2), never scores.
3. THE Memory Graph SHALL expose a public highest-salience-UNCONNECTED candidate selection
   (Build Plan Module 3 Outputs) — SUBSTRATE selection returning structural facts only; it
   SHALL form no edge and decide no meaning.
4. Each addition SHALL be ADDITIVE (new methods only; no existing signature/behavior changed)
   and doc-anticipated; every existing test SHALL stay green EXCEPT the single DMN gap
   assertion that documented these methods as not-yet-present (updated to reflect closure).

## Open Questions (flagged, NOT resolved by invention)

- **OQ-1 — Thinking-sound trigger precedence.** v4's Layer 5 table lists five categories but
  states no precedence among simultaneously-true triggers. Adopted order (content triggers
  → PAD-mood triggers → contemplation default) is a documented presentation choice; it never
  affects PAD/meaning/memory. Build-time.
- **OQ-2 — Initiative keys on `due`, not `neglected`.** v4 Layer 2 keys initiative on a
  need dropping "below the critical threshold". The Addendum §3 categorical model has three
  states (satisfied/due/neglected) but Needs_System currently NEVER emits `neglected` (its
  OQ-1). Initiative therefore keys on `due` (the critical categorical state Needs_System
  DOES emit). FLAGGED for the architect to revisit if `neglected` is later split out.
- **OQ-3 — Highest-pressure tie-break.** The four needs are categorical, so there is no
  numeric "pressure" to rank simultaneously-`due` needs by (inventing one is forbidden). The
  tie-break is the canonical spec order (Connection, Growth, Purpose, Continuity). Flagged as
  the policy; a finer ordering would require a source not present.
- **OQ-4 — Tick-cadence values (F-8a).** Only idle=8min / reflection=6h are pinned; the
  soul-tick and DMN-tick interval values are build-time tuning placeholders.


---

## daemon — design.md

# Design Document — Module 8: Daemon / Soul Tick

## Overview

The Daemon (`daemon/aria_daemon.py`) is Aria's ORCHESTRATOR. It drives two separate clocks,
routes an inbound turn through the full pipeline, selects pre-cached thinking sounds,
evaluates initiative, detects idle, and honors the HANDOFF startup contract. It is the
CALLER of every core module and the top of the dependency tree — nothing imports it, so it
may import everything without a cycle.

The single most important property is what the Daemon does NOT do: it computes no meaning and
no feeling (steering/project-rules.md). PAD moves only inside PAD_Engine (EMA decay on the
soul tick) and inside the Appraisal Chain (its Stage-4 delta). Need states come only from
Needs_System. The Daemon routes signals and drives clocks; the modules decide.

This design implements requirements.md as written, using only mechanisms already specified
there or in the supporting documents. No new mechanism, formula, or threshold is introduced.
Genuine gaps are carried as flagged Open Questions / build-time placeholders (requirements.md
OQ-1…OQ-4), never resolved by invention.

## Hard Constraints (carried from requirements.md, non-negotiable)

1. **COMPUTES NO FEELING.** The Daemon never calls `apply_appraisal_delta` (grep-clean: the
   call `.apply_appraisal_delta(` never appears in the source). It calls
   `PAD_Engine.on_soul_tick()` (driving the decay clock — the module does the math) and
   `get_current_pad()` (a presentation read), but writes no PAD (Req 1).
2. **TWO SEPARATE CLOCKS.** `soul_tick()` drives PAD + Energy + attention and never runs a
   DMN pass; `dmn_tick()` runs a DMN pass and never decays PAD. Neither triggers the other
   (Req 2).
3. **F4 / BARGE-IN = ZERO INTERNAL EFFECT.** Each interrupt's entire body is one call into
   the Audio Pipeline. No path to PAD, appraisal, graph, needs, or state (Req 8; Addendum §5).
4. **HANDOFF CONTRACT, EXACTLY.** initialize() once (guarded); consistency_flags cleared and
   persisted; last_applied_valence round-tripped on save + shutdown (Req 9/10/11).
5. **INITIATIVE:** highest-pressure `due` need, once, no nag, enters at soul_filter directly;
   no numeric threshold (Req 7; Addendum §7).
6. **NO OTHER CORE MODULE IS MUTATED** except the additive, doc-anticipated DMN-contract-gap
   closures (Req 13), each new-method-only.

## Architecture

```
                                external world
   voice(STT text)  F4 / barge-in   wall-clock          shutdown / cadence
        │                 │             │                       │
        ▼                 ▼             ▼                       ▼
   ┌──────────────────────────── AriaDaemon (Module 8) ────────────────────────────┐
   │ startup()  — HANDOFF: initialize() ONCE (guarded) + restored valence;          │
   │              clear consistency_flags; restore Energy.                          │
   │                                                                                │
   │  CLOCK 1 soul_tick():   PAD_Engine.on_soul_tick()   [Module 1 owns the math]   │
   │      (maintenance)      Needs.on_soul_tick / on_idle_recovery   [Module 2]     │
   │                         refresh attentional policy + evaluate initiative       │
   │                                                                                │
   │  CLOCK 2 dmn_tick():    if idle(1&2) → DMN.run_idle_pass()   [Module 6]         │
   │      (consolidation)    (DMN reads Energy → FULL/SHALLOW depth = condition 3)   │
   │                                                                                │
   │  route_inbound_turn():  thinking sound → Appraisal → Soul_Filter → LLM → gate  │
   │                         → TTS ; (poignancy=critical → DMN.run_forced_partial)  │
   │                                                                                │
   │  on_f4_interrupt()/on_barge_in():  audio.stop_playback()   ← ZERO else         │
   │  _route_initiative():  build minimal appraisal → Soul_Filter → TTS (skip STT)  │
   │  save_periodic()/shutdown():  save PAD + Energy + last_applied_valence          │
   └────────────────────────────────────────────────────────────────────────────────┘
        │            │            │             │            │             │
        ▼            ▼            ▼             ▼            ▼             ▼
   PAD_Engine   Needs_System  Memory_Graph  Appraisal   Soul_Filter   DMN   State_Manager
   [M1 REAL]    [M2 REAL]     [M3 REAL]     [M4 REAL]   [M5 REAL]    [M6]   [M11 REAL]
                                                            │
                                                       LLM_Interface [M9 REAL]
   Audio_Pipeline [M7 CONTRACT — fake]     Visual_Layer [M10 CONTRACT — not wired here]
```

## Startup contract (HANDOFF_NOTES) — the exact sequence

`startup()` runs ONCE (guarded by `_started`; a second call raises — initialize() is not
idempotent, HANDOFF (c)):

1. `pad_state, energy, self_model, valence_str = StateManager.load_all()`.
2. `restored_snapshot = pad_state_to_snapshot(pad_state)` and
   `restored_valence = valence_from_str(valence_str)` — BOTH conversions at the wiring call
   site (HANDOFF: the same wiring helper that converts PADState→PADSnapshot; NOT inside
   PAD_Engine or State_Manager).
3. `PAD_Engine.initialize(restored_snapshot, restored_valence)` — EXACTLY ONCE (HANDOFF (a)/(c)).
4. `Needs_System.initialize(energy)`.
5. CLEAR `consistency_flags` (all → False) and `save_self_model(...)` — HANDOFF (b); the
   quality record and recent-learning fields are untouched.
6. Arm the two clocks and the idle timer at boot.

`save_periodic()` / `shutdown()` persist PAD (snapshot→PADState), Energy, and the
last_applied_valence string (HANDOFF (a)). The valence is read from PAD_Engine's
`_last_applied_valence` via the wiring helper `read_pad_last_valence()` — the HANDOFF's "get
access added for this purpose … Module 1's implementation decides this" is fulfilled by
reading the HANDOFF-NAMED field in the Daemon's wiring layer, WITHOUT expanding Module 1's
locked public API (Req 11.4).

**Round-trip proof (Req 11):** save writes `Valence.value`; a fresh process loads the string,
`valence_from_str` converts it back, and it is passed to `initialize(restored_valence)` — so
PAD_Engine's `_last_applied_valence` is restored, keeping its restore-boundary raise rare.

## The two clocks (Req 2)

Modeled as two independent public methods plus a scheduler:

- `soul_tick(now)`: `PAD_Engine.on_soul_tick()`; then `Needs.on_idle_recovery()` if idle else
  `Needs.on_soul_tick()` ("soul tick recovers Energy during extended idle", v4);
  `_refresh_attentional_policy()`; `_maybe_initiate()`. Never runs a DMN pass.
- `dmn_tick(now)`: if idle conditions 1 & 2 → `DMN.run_idle_pass(...)`. Never decays PAD.
- `run_scheduler_step(now)`: fires each clock when `now - last_fire ≥ interval`, each on its
  OWN interval; neither triggers the other. Intervals are F-8a placeholders (injectable).

The direct `soul_tick`/`dmn_tick` methods are the primary interface (and the test surface
that proves independence): ticking soul N times decays PAD and runs no DMN pass; ticking DMN
at idle runs a pass and leaves PAD identical.

## Idle detection (Req 4)

`_idle_conditions_met(now)` returns `(now - last_voice_input) ≥ 8min AND not output_pending`.
Only conditions 1 & 2 (Daemon-owned). Condition 3 (Energy > 20) is NOT gated here: DMN reads
Energy to choose FULL vs SHALLOW depth (DMN spec Req 2.3). Gating idle on Energy here would
make the shallow pass unreachable — so the split follows the DMN spec's own division of
responsibility. The 8-minute window is PINNED (v4); it is injectable but defaults to 8min.

## Inbound-turn routing (Req 5)

`route_inbound_turn(user_text, session_id, entity_refs, entity_node_id,
active_uncertainty_refs, now)`:

1. Meta-command interception: `self._session_buffer.is_meta_command(user_text)` — if
   "rest"/"focus"/"unfocus" is detected, return `_handle_meta_command(...)` IMMEDIATELY,
   bypassing appraisal, Soul_Filter, the LLM, and the Output Gate entirely. "rest" also
   forces a DMN partial-consolidation pass and clears the session buffer; "focus"/
   "unfocus" toggle `SessionBuffer.set_focus_mode`. Each returns a hardcoded
   `SoulFilterResponse` with `gate_results=()`.
2. Cognitive-load check: if `self._session_buffer.fullness_state()` is "heavy" or
   "critical", call `self._appraisal.submit_cognitive_load(fullness)` — a second-order
   appraisal event distinct from the per-turn Stage 0-6 appraisal below.
3. `_note_voice_input(now)` (reset idle condition 1); `output_pending = True`; update the
   volatile Present World Model (`last_user_text`) — working state, not persisted.
4. Play a pre-cached thinking sound (Layer 5): reads current PAD + the user's text for
   PRESENTATION only; never a PAD write.
5. Appraisal (Module 4): get need states from Needs_System, call
   `Appraisal_Chain.appraise(...)`, then `_track_turn(...)` to update session-entity /
   active-uncertainty / most-recently-salient-node working state. PAD moves here ONLY as
   the appraisal's own byproduct via PAD_Engine — the Daemon writes no PAD.
6. Compute the post-emergency flag: read `_last_turn_was_emergency` (set by the PREVIOUS
   turn) before calling Soul_Filter, then update it to this turn's `appraisal.emergency`
   AFTER appraisal.
7. Soul_Filter (Module 5): assemble `session_context = self._session_buffer.
   get_context()` (the ephemeral 3-tier conversation transcript) and call
   `Soul_Filter.respond(appraisal_result=appraisal, user_message=user_text,
   entity_node_id=..., entity_refs=..., need_states=..., now=now,
   post_emergency=post_emergency_this_turn, session_context=session_context)`. The
   five-field boundary and the Output Gate remain Soul_Filter's; the Daemon passes the
   appraisal, the raw user message, and the session context through unchanged.
8. Audio Pipeline (Module 7 contract): `self._audio.speak(response.text)` (TTS);
   `output_pending = False`.
9. Append the turn to the session buffer: `self._session_buffer.append_turn(user_text,
   response.text)` — ephemeral working memory only, not the graph.
10. Reflection trigger: if `appraisal.poignancy is CRITICAL` and an EventNode was
    written, force an EARLY DMN partial pass (`run_forced_partial_pass`) with a
    single-item buffer. This is a DMN-CLOCK event triggered by content — it does NOT
    decay PAD and does NOT merge the soul-tick and DMN-tick clocks.

## Thinking sounds (Req 6; v4 Layer 5)

`select_thinking_sound(text, pad)` is a pure categorical function using the v4 table's exact
words and PAD thresholds (0.7 / 0.6 / 0.5 — IN-SPEC presentation thresholds, same category as
the emergency coping thresholds). Precedence (a documented presentation choice, OQ-1): content
triggers (Concern: worry/problem/fail/error; Surprise: surprise/unexpected/suddenly) →
PAD-mood (Playfulness: D>0.6 & P>0.5; Warmth: P>0.7) → Contemplation (default). Contentless
input → no sound. Reading PAD is presentation, not a write (Req 6.2).

## Initiative (Req 7; v4 Layer 2/6; Addendum §7)

- `_select_highest_pressure_need(need_states)`: returns the first need in canonical order
  (Connection, Growth, Purpose, Continuity) whose state is `DUE` (or `NEGLECTED`, accepted
  defensively though Needs_System never emits it — OQ-2), else None. CATEGORICAL — no number
  (percentage test holds); canonical order is the tie-break (F-8b, OQ-3).
- `_maybe_initiate()`: fires ONCE per due-episode for the highest-pressure need, latching
  `_initiative_expressed[need]=True`; never repeats while still due (no nag). The latch resets
  to False in `_refresh_attentional_policy` when the need is SATISFIED again — so a LATER drop
  can express once more (v4 "expresses a need exactly once when it drops").
- `_route_initiative(need)`: enters at soul_filter DIRECTLY (Addendum §7). The Appraisal Chain
  is NOT invoked (no user turn). The Daemon selects a PRE-AUTHORED behavioral instruction by
  which need is due (`_INITIATIVE_NOTES`, hardcoded like Soul_Filter's PERSONA_ANCHOR — the
  MEANING that the need is due came from Needs_System) and packages it into a minimal
  `AppraisalResult` (non-emergency, low poignancy, all-clear signals, and an INERT PAD delta
  that Soul_Filter never applies). Soul_Filter renders → LLM → gate → TTS. The Daemon writes
  no PAD (the inert delta is a data placeholder for a frozen contract field).

## F4 / barge-in (Req 8; Addendum §5)

`on_f4_interrupt()` and `on_barge_in()` each have a single-statement body:
`self._audio.stop_playback()`. There is no reference to PAD_Engine, Appraisal, Graph, Needs,
or State — proving structurally there is no path to a PAD write or any state mutation. The
`_output_pending` flag is intentionally NOT touched here: "return to listening" is the Audio
Pipeline's `stop_playback()` responsibility, keeping F4 a pure, zero-internal-effect audio
stop. Whatever the user says AFTER enters appraisal normally, as any input (Addendum §5).

## Volatile working state (Req 12; Resolution Log item 10)

Held in memory, NEVER persisted: `_present_world_model`, `_language` (default "en",
conversation-driven only), `_last_voice_input_at`, `_output_pending`,
`_most_recently_salient_node`, `_highest_pressure_need`, `_attentional_focus`,
`_initiative_expressed`, the self-monitoring buffer, and the tracked active-uncertainty /
session-entity / rupture refs relayed to DMN.

## DMN-contract-gap closures (Req 13) — additive, doc-anticipated

- **`appraisal_chain.submit_aha_insight(insight)`** — accepts DMN's aha EVENT (DUCK-TYPED, to
  avoid the import cycle soul_filter→appraisal_chain→dmn→needs_system→soul_filter), builds a
  small POSITIVE byproduct delta (pleasure/competence up, valence POSITIVE), and applies it
  through the module's only PAD-write path (PAD_Engine). Magnitude is a SUBSTRATE placeholder
  (the `_PAD_STEP` tiers); v4 pins only the SIGN ("small positive"). Complements — does not
  replace — `appraise(aha_insight=<PADDelta>)`.
- **`graph_manager.predictability_evidence(entity_ref)`** — Observing→Engaging (Addendum §2
  "a specific behavioral pattern has recurred"): a specific (q2×q3) profile appears on ≥2
  events for the entity (uncertain profiles excluded). Categorical boolean; the count feeds
  only the ">1" gate, never a magnitude.
- **`graph_manager.dependability_evidence(entity_ref)`** — Engaging→Invested (Addendum §2
  "generalizes across more than one distinct kind of situation"): a specific profile appears
  in ≥2 distinct `session_id`s (session = situation, a structural proxy — finer definitions
  build-time). Categorical boolean.
- **`graph_manager.highest_salience_unconnected_candidates(limit)`** — pairs of the
  highest-salience UNCONNECTED EventNodes (cutoff = the in-spec HIGH floor 0.55; limit is a
  build-time placeholder) with the structural facts DMN's ConnectionCandidate needs
  (already_connected=False, shares_context, both_high_salience, reveals_new_pattern — a
  FLAGGED structural proxy for "explanatory power": a shared entity ACROSS sessions). Substrate
  selection only; forms no edge, decides no meaning. The Daemon maps each record 1:1 to a
  ConnectionCandidate (pure packaging).

The only existing test affected is the single DMN assertion that documented
predictability/dependability as not-yet-present; it is updated to assert closure (Req 13.4).

## Data types / helpers

- `ThinkingSound` (enum: CONTEMPLATION/SURPRISE/CONCERN/WARMTH/PLAYFULNESS).
- `AudioPipelinePort` (Protocol: speak / stop_playback / play_thinking_sound /
  play_reconsideration_sound) — the Module 7 contract.
- Module-level wiring helpers: `pad_state_to_snapshot`, `snapshot_to_pad_state`,
  `valence_from_str`, `valence_to_str`, `read_pad_last_valence`, `need_states_to_mapping`,
  `select_thinking_sound`, `build_initiative_appraisal`.

## Error handling

- `startup()` twice → RuntimeError (initialize() not idempotent).
- Any tick/route before `startup()` → RuntimeError (`_require_started`).
- Unrecognised / missing persisted valence → `valence_from_str` returns None → PAD Engine's
  own residual restore-boundary handling stands (the Daemon invents no resolution).
- Entity refs passed to routing are expected to be resolved EntityNode ids (the entity
  resolution layer's job, upstream), consistent with the DMN stage-evaluation contract.

## Testing strategy

Plain pytest (no hypothesis), matching Modules 1–6. Real core modules + fakes for the
unbuilt Audio Pipeline and the LLM transports; a spy DMN for clock-independence; counting /
tripwire PAD engines for the initialize-once and zero-effect proofs. See test_daemon.py.


---

## daemon — tasks.md

# Implementation Plan — Module 8: Daemon / Soul Tick

This plan implements design.md exactly as written. Each task is small and independently
testable. Precedence: `ARIA_Resolution_Log.md` > `ARIA_Soul_Spec_v4_Addendum.md` >
`ARIA_Soul_Spec_v4.md`. Nothing reopens a locked item (F-8b RESOLVED by item 10; F-8a values
are build-time placeholders). Genuinely-undefined values are `TODO(F-8a)` / OQ placeholders,
never invented. All prior-module edits are ADDITIVE and doc-anticipated (Req 13 / HANDOFF).

- [x] 1. Module scaffold + reuse-not-redefine imports (top of the dependency tree).
  - Create `daemon/aria_daemon.py` with a docstring citing the five constraints, v4
    "Two-Process Separation" / Layer 5 / Layer 2, Addendum §5/§7, HANDOFF_NOTES, and the
    F-8a/F-8b disposition.
  - Import REAL interfaces from every core module (pad_engine, state_manager, needs_system,
    graph_manager, appraisal_chain, soul_filter, dmn). No import cycle (nothing imports the
    Daemon).
  - _Requirements: 1.4_

- [x] 2. Constants — PINNED cadences vs FLAGGED placeholders.
  - `IDLE_NO_VOICE_WINDOW = 8min`, `REFLECTION_INTERVAL = 6h` (PINNED, v4).
  - `DEFAULT_SOUL_TICK_INTERVAL` / `DEFAULT_DMN_TICK_INTERVAL` — `TODO(F-8a)` placeholders.
  - `_NEED_ORDER` (canonical tie-break order, F-8b/OQ-3). `_now()` aware-UTC helper.
  - _Requirements: 3.5, 4.4, 7.5_

- [x] 3. Wiring helpers (the conversions HANDOFF assigns to the Daemon's wiring layer).
  - `pad_state_to_snapshot` / `snapshot_to_pad_state`; `valence_from_str` / `valence_to_str`
    (None/unknown → None, no invented resolution); `read_pad_last_valence` (reads the
    HANDOFF-named field WITHOUT expanding Module 1's locked API); `need_states_to_mapping`.
  - _Requirements: 9.3, 11.1, 11.2, 11.3, 11.4, 5.2_

- [x] 4. Thinking-sound selection (Layer 5).
  - `ThinkingSound` enum + `select_thinking_sound(text, pad)` — v4 table's exact words +
    thresholds; content → PAD-mood → contemplation default; contentless → None. Reading PAD
    is presentation, not a write.
  - _Requirements: 6.1, 6.2, 6.4_

- [x] 5. Initiative constants + minimal appraisal builder.
  - `_INITIATIVE_NOTES` (pre-authored HOW instructions per need, v4 "single gentle reach-out");
    `_INERT_PAD_DELTA` (never applied) + `_NEUTRAL_SOCIAL_SIGNALS`; `build_initiative_appraisal`
    (non-emergency, low poignancy, all-clear signals).
  - _Requirements: 7.4_

- [x] 6. `AudioPipelinePort` Protocol (Module 7 contract; fake in tests).
  - `speak` / `stop_playback` / `play_thinking_sound` / `play_reconsideration_sound`.
  - _Requirements: 1.4, 5.1, 8.1_

- [x] 7. `AriaDaemon.__init__` — inject all modules + volatile working state + two clocks.
  - Inject pad/needs/graph/appraisal/soul_filter/dmn/state/audio + ids + clock + intervals.
  - Init `_started=False`, volatile working state (present world model, language, idle timer,
    output_pending, attentional focus, no-nag latch, DMN-input buffers).
  - _Requirements: 1.4, 12.1, 12.2_

- [x] 8. `startup()` — the HANDOFF contract, EXACTLY ONCE.
  - Guard `_started` (second call raises — initialize() not idempotent, HANDOFF (c)).
  - `load_all()`; `initialize(restored_snapshot, restored_valence)` ONCE; `Needs.initialize`;
    CLEAR consistency_flags + `save_self_model`; arm the clocks/idle timer.
  - _Requirements: 9.1, 9.2, 9.3, 10.1, 10.2, 10.3, 11.2, 11.3_

- [x] 9. `shutdown()` / `save_periodic()` / `_save_state()` — round-trip valence.
  - Save PAD (snapshot→PADState), Energy, and `read_pad_last_valence` → string (HANDOFF (a)).
  - _Requirements: 11.1, 11.4_

- [x] 10. CLOCK 1 — `soul_tick()`.
  - `PAD_Engine.on_soul_tick()`; `Needs.on_idle_recovery()` if idle else `on_soul_tick()`;
    `_refresh_attentional_policy()`; `_maybe_initiate()`. Never runs a DMN pass.
  - _Requirements: 2.2, 3.1, 3.2, 3.3, 3.4_

- [x] 11. CLOCK 2 — `dmn_tick()` + `run_scheduler_step()`.
  - `dmn_tick`: at idle(1&2) → `DMN.run_idle_pass`; else None. Never decays PAD.
  - `run_scheduler_step`: fire each clock on its OWN interval, independently.
  - _Requirements: 2.1, 2.3, 2.4, 4.1, 4.2, 4.3_

- [x] 12. Idle detection — `_idle_conditions_met()` + `_note_voice_input()`.
  - Conditions 1 & 2 only (Daemon-owned); Energy (condition 3) left to DMN's depth choice.
  - _Requirements: 4.1_

- [x] 13. Inbound-turn routing — `route_inbound_turn()`.
  - Thinking sound → Appraisal (need-states mapping) → `_track_turn` → Soul_Filter → TTS;
    poignancy=critical → `run_forced_partial_pass` (DMN clock, not a soul tick).
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 4.5_

- [x] 14. F4 / barge-in — ZERO internal effect.
  - `on_f4_interrupt()` / `on_barge_in()`: single-statement `audio.stop_playback()`. No path
    to PAD/appraisal/graph/needs/state.
  - _Requirements: 8.1, 8.2, 8.3_

- [x] 15. Attentional policy + initiative.
  - `_refresh_attentional_policy` (highest-pressure need + most-recently-salient node, reset
    no-nag latches on satisfied); `_select_highest_pressure_need` (categorical, keyed on
    `due`, canonical tie-break); `_maybe_initiate` (once, no nag); `_route_initiative` (enter
    at soul_filter, skip STT/appraisal, TTS).
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 12.1, 12.3_

- [x] 16. Thinking-sound playback + reconsideration + language state.
  - `_play_thinking_sound` (presentation PAD read); `on_reconsideration` (audio);
    `set_language` / `language` (volatile, conversation-driven).
  - _Requirements: 6.3, 12.2, 12.3_

- [x] 17. DMN-pass input assembly + result consumption + turn tracking.
  - `_assemble_idle_pass_input` (maps graph's `highest_salience_unconnected_candidates` →
    ConnectionCandidate 1:1); `_consume_dmn_result` (clear consumed buffer + ruptures);
    `_track_turn` (buffer + reaction linking + uncertainty/entity/rupture relay).
  - _Requirements: 5.1, 4.5_

- [x] 18. ADDITIVE — `appraisal_chain.submit_aha_insight(insight)`.
  - Duck-typed (no import cycle); small POSITIVE byproduct delta via PAD_Engine; DMN never
    builds/writes PAD. New method only; existing signatures/behavior unchanged.
  - _Requirements: 13.1, 13.4_

- [x] 19. ADDITIVE — `graph_manager.predictability_evidence` / `dependability_evidence`.
  - Structural/categorical booleans (Addendum §2): recurrence of a specific (q2×q3) profile;
    generalization across ≥2 sessions. Never a score. New methods only.
  - _Requirements: 13.2, 13.4_

- [x] 20. ADDITIVE — `graph_manager.highest_salience_unconnected_candidates`.
  - Substrate selection of unconnected high-salience EventNode pairs + structural facts
    (cutoff = in-spec HIGH floor 0.55; `reveals_new_pattern` = flagged cross-session proxy).
    Forms no edge, decides no meaning. New method + `_edge_exists_between` helper only.
  - _Requirements: 13.3, 13.4_

- [x] 21. Update the single DMN gap assertion to reflect closure.
  - `test_dmn.py::test_real_graph_satisfies_the_methods_dmn_calls` — the two `assert not
    hasattr(...)` lines become `assert callable(getattr(...))` (the gap is now closed).
  - _Requirements: 13.4_

- [x] 22. Tests — `tests/test_daemon.py` (plain pytest, NO hypothesis).
  - Two clocks independent; initialize() once + second-startup guard; consistency_flags
    cleared + persisted; last_applied_valence round-trip (shutdown + periodic); F4/barge-in
    zero-effect tripwire; initiative keys on `due`, once, no nag, enters at soul_filter;
    full inbound turn end-to-end with REAL modules; thinking-sound selection; grep-clean "no
    PAD write"; and the additive-closure tests (submit_aha_insight; predictability /
    dependability / unconnected-candidates; DMN wired to the REAL predicate).
  - Verify: `pytest tests/test_daemon.py -q` green, then `pytest -q` — prior 317 stay green.
  - _Requirements: all_

