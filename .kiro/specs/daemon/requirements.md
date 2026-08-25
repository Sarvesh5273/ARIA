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
   the EMA math; the Daemon only ticks it). This is unconditional — PAD decays every tick.
2. WHEN a soul tick fires AND output is pending (ACTIVE LOAD), THE Daemon SHALL call
   Needs_System.on_soul_tick() (active-load Energy depletion).
3. WHEN a soul tick fires AND the idle conditions ARE met, THE Daemon SHALL call
   Needs_System.on_idle_recovery() ("soul tick recovers Energy during extended idle", v4).
3a. WHEN a soul tick fires AND she is silent but the 8-minute idle gate has NOT opened yet
   (PRE-IDLE SILENCE), THE Daemon SHALL call NEITHER Energy signal — Energy is HELD
   (Resolution Log item 29: "in rest situation, energy will not consume"). Waiting is not
   work, so Energy at the moment the gate opens is the tiredness the conversation left.
4. WHEN a soul tick fires, THE Daemon SHALL refresh the attentional policy and evaluate
   initiative.
5. THE soul-tick interval SHALL be a build-time tuning placeholder (F-8a), injectable.
6. THE three Energy states SHALL be derived from the two markers idle detection already
   owns (`_last_voice_input_at`, `_output_pending`) and the pinned 8-minute window — no new
   flag, no new number (Resolution Log item 29).

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
   System emits; `neglected` is accepted too and, as of 2026-08-20, IS now emitted
   for Connection/Growth/Purpose — Needs System OQ-1 closed via the two-window
   model. `_highest_pressure_need` already treated both states alike, so this
   requirement is unchanged in behaviour; only the note that `neglected` never
   fires is superseded. OQ-2 still FLAGGED). NO
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
