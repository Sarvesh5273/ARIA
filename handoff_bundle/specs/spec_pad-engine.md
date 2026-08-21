# ARIA locked spec — pad-engine

Consolidated from .kiro/specs/pad-engine/{requirements,design,tasks}.md for upload.
Precedence: ARIA_Resolution_Log.md > ARIA_Soul_Spec_v4_Addendum.md > ARIA_Soul_Spec_v4.md.


---

## pad-engine — requirements.md

# Requirements Document — Module 1: PAD Engine

## Introduction

This document transcribes and formalizes, in EARS format, the Module 1 (PAD Engine)
entry from `ARIA_Module_Build_Plan.md`. That entry is the locked, approved scope for
this module. No requirement in this document introduces a mechanism, threshold, or
behavior that is not already stated in the Module 1 entry or in the supporting
architecture documents (`ARIA_Soul_Spec_v4.md`, `ARIA_Soul_Spec_v4_Addendum.md`,
`ARIA_Resolution_Log.md`). Where the Module 1 entry references a value or mechanism
defined elsewhere (e.g. the PAD baseline, the decay coefficients), the supporting
document is cited as the source of that value, not as a new source of scope.

Precedence when documents conflict: `ARIA_Resolution_Log.md` > `ARIA_Soul_Spec_v4_Addendum.md`
> `ARIA_Soul_Spec_v4.md`. `ARIA_GLM_Covering_Instruction.md` provides covering context only.

Per the Module 1 entry: "Flags: None. Baseline [0.55, 0.45, 0.58] and decay 0.6/0.75
are spec-locked." This document does not reopen that entry's scope. Genuinely
undefined items discovered while formalizing the entry are recorded in the
**Open Questions** section at the end, not resolved by invention.

## Glossary

- **PAD_Engine**: The module specified here (Module 1). Owns the live, in-memory
  Pleasure/Arousal/Dominance state values for Aria. The only module permitted to
  mutate PAD.
- **PAD**: The three-dimensional Pleasure-Arousal-Dominance state vector. Three
  continuous values, each bounded to [0.0, 1.0]. No source document states this
  bound explicitly; it is an architect decision (former Open Question 2 —
  RESOLVED, see Open Questions) grounded in physiological homeostasis, and it is
  enforced in `PAD_Engine.apply_appraisal_delta`.
- **Pleasure**: The first continuous dimension of PAD.
- **Arousal**: The second continuous dimension of PAD.
- **Dominance**: The third continuous dimension of PAD.
- **PAD_Baseline**: The fixed resting-state PAD vector [Pleasure=0.55, Arousal=0.45,
  Dominance=0.58], locked in `ARIA_Soul_Spec_v4.md` (Layer 1) and restated in the
  Module 1 entry.
- **PAD_Delta**: The (dP, dA, dD) output of Appraisal Chain Stage 4, representing the
  shift the appraisal chain has computed for the current event. The only external
  input permitted to shift PAD values (aside from EMA decay).
- **Aha_Insight_PAD_Delta**: A PAD_Delta that originates from a second-order
  appraisal event triggered during DMN idle consolidation (an "aha moment"), but
  which — per the Module 1 entry — arrives at PAD_Engine via the Appraisal Chain
  like any other PAD_Delta, not as a separate injection path.
  This document treats it as a case of PAD_Delta, not a second mechanism.
- **Soul_Tick**: The periodic signal from the Daemon (Module 8) that drives PAD_Engine's
  EMA decay computation. Cadence is a build-time tuning flag, not fixed by this
  document (see Open Questions).
- **EMA_Decay**: Exponential moving average decay applied to PAD on every Soul_Tick.
  The coefficient is selected once per Soul_Tick, based on the valence
  (positive/negative/neutral) of the Appraisal_Chain event that produced the
  tick's context: coefficient 0.6 when that valence is negative, coefficient 0.75
  when that valence is positive (`ARIA_Soul_Spec_v4.md`, Layer 1, "Negativity
  Bias — Asymmetric Recovery"). The single selected coefficient is applied
  uniformly to Pleasure, Arousal, and Dominance for that tick — it is not chosen
  independently per PAD dimension based on that dimension's own movement.
  Handling of a neutral-valence originating event is not specified in any source
  document (see Requirement 3).
- **Appraisal_Chain**: Module 4. Produces PAD_Delta at Stage 4 of its per-turn
  processing. PAD_Engine's only source of PAD-shifting input other than EMA_Decay.
- **Daemon**: Module 8. Source of the Soul_Tick signal.
- **Soul_Filter**: Module 5. Consumes current PAD coordinates (Behavioral Register).
- **Visual_Layer**: Module 10. Consumes current PAD coordinates for zone mapping.
- **Audio_Pipeline**: Module 7. Consumes current PAD coordinates for prosody mapping.
- **DMN**: Module 6 (Default Mode Network / Idle Consolidation). Consumes PAD_History
  for EmotionNode crystallization.
- **PAD_History**: The record of the last PAD_HISTORY_LENGTH Soul_Tick values of
  PAD maintained by PAD_Engine and exposed to DMN. PAD_HISTORY_LENGTH is a
  configurable build-time constant (see Build-Time Tuning Constants and
  Requirement 6).
- **State_Manager**: Module 11 (`daemon/state_manager.py`, already approved/built).
  Serializes and restores PAD to/from `aria_state.json`. Per its own module
  documentation and the Resolution Log, State_Manager "owns no meaning" and must
  not compute, decay, or otherwise mutate PAD values — it only reads the
  PAD_Engine-supplied value for writing to disk, and supplies a persisted or
  baseline value back to PAD_Engine on restore.

## Requirements

### Requirement 1: Maintain PAD State

**User Story:** As the Aria system, I want a single owner of the live Pleasure,
Arousal, and Dominance values, so that emotional state is represented consistently
and cannot be corrupted by uncoordinated writes from other modules.

#### Acceptance Criteria

1. THE PAD_Engine SHALL maintain Pleasure, Arousal, and Dominance as three
   continuous values.
2. THE PAD_Engine SHALL be the only module that mutates the Pleasure, Arousal, and
   Dominance values.
3. WHEN PAD_Engine initializes with no prior persisted PAD state available, THE
   PAD_Engine SHALL set Pleasure to 0.55, Arousal to 0.45, and Dominance to 0.58.

### Requirement 2: PAD Shifts Only Through the Appraisal Chain

**User Story:** As the Aria system architect, I want PAD values to change only as a
byproduct of the appraisal chain's output, so that no mechanism can bypass the
appraisal process and directly assign emotional state.

#### Acceptance Criteria

1. WHEN Appraisal_Chain provides a PAD_Delta (dP, dA, dD) to PAD_Engine, THE
   PAD_Engine SHALL apply that PAD_Delta to the current Pleasure, Arousal, and
   Dominance values.
2. THE PAD_Engine SHALL accept the PAD_Delta from Appraisal_Chain, including a
   PAD_Delta whose origin is an Aha_Insight_PAD_Delta, as the only external input
   that shifts Pleasure, Arousal, or Dominance other than EMA_Decay.
3. IF a request to modify Pleasure, Arousal, or Dominance arrives from any source
   other than an Appraisal_Chain PAD_Delta or EMA_Decay, THEN THE PAD_Engine SHALL
   reject that request.

### Requirement 3: Asymmetric EMA Decay on Every Soul-Tick

**User Story:** As the Aria system architect, I want PAD to decay asymmetrically
toward baseline on every soul-tick, so that negative emotional shifts linger longer
than positive ones, consistent with the negativity-bias research grounding the
architecture.

#### Acceptance Criteria

1. WHEN Daemon issues a Soul_Tick signal, THE PAD_Engine SHALL apply EMA_Decay to
   the current Pleasure, Arousal, and Dominance values.
2. WHEN the Appraisal_Chain event that produced the current Soul_Tick's context has
   a negative valence, THE PAD_Engine SHALL select an EMA_Decay coefficient of 0.6
   and apply it uniformly to Pleasure, Arousal, and Dominance for that Soul_Tick.
3. WHEN the Appraisal_Chain event that produced the current Soul_Tick's context has
   a positive valence, THE PAD_Engine SHALL select an EMA_Decay coefficient of 0.75
   and apply it uniformly to Pleasure, Arousal, and Dominance for that Soul_Tick.
4. THE PAD_Engine SHALL apply EMA_Decay as the only mechanism, other than an
   Appraisal_Chain PAD_Delta, permitted to change Pleasure, Arousal, or Dominance.

Note: handling of the case where the Appraisal_Chain event that produced the
current Soul_Tick's context has a neutral valence is not specified in any source
document. This is recorded here, within this requirement, rather than as a
separate open question, since coefficient selection is now specified as a
per-tick, valence-driven decision (see EMA_Decay in the Glossary).

### Requirement 4: Accept Soul-Tick and Appraisal Inputs

**User Story:** As the Aria system, I want PAD_Engine to accept exactly the inputs
the architecture defines for it, so that its behavior is fully determined by the
Daemon and the Appraisal Chain.

#### Acceptance Criteria

1. THE PAD_Engine SHALL accept a PAD_Delta (dP, dA, dD) from Appraisal_Chain Stage 4
   as input.
2. THE PAD_Engine SHALL accept a Soul_Tick signal from Daemon as input.
3. THE PAD_Engine SHALL accept an Aha_Insight_PAD_Delta arriving via Appraisal_Chain
   as input, and SHALL process it identically to any other PAD_Delta from
   Appraisal_Chain.

Note (scope addition): Valence-of-originating-event, carried as a field on
PADDelta per Requirement 3's decay-coefficient resolution, is an addition to the
three inputs named in the Build Plan's Module 1 entry, introduced to make the
Resolution Log's whole-event decay decision implementable. This addition is noted
here for architect visibility, not silently absorbed into the original input list.

### Requirement 5: Expose Current PAD Coordinates to Consumers

**User Story:** As Soul_Filter, Visual_Layer, Audio_Pipeline, Appraisal_Chain, and
Daemon, I want to read the current PAD coordinates, so that I can render behavior,
video zone, prosody, retrieval preference, and thinking-sound selection consistent
with Aria's live emotional state.

#### Acceptance Criteria

1. THE PAD_Engine SHALL output the current Pleasure, Arousal, and Dominance
   coordinates to Soul_Filter for Behavioral Register construction.
2. THE PAD_Engine SHALL output the current Pleasure, Arousal, and Dominance
   coordinates to Visual_Layer for video zone mapping.
3. THE PAD_Engine SHALL output the current Pleasure, Arousal, and Dominance
   coordinates to Audio_Pipeline for prosody mapping.
4. THE PAD_Engine SHALL output the current Pleasure, Arousal, and Dominance
   coordinates to Appraisal_Chain Stage 1 for mood-congruent sign determination and
   coping context.
5. THE PAD_Engine SHALL output the current Pleasure, Arousal, and Dominance
   coordinates to Daemon for thinking-sound selection and zone determination.

### Requirement 6: Expose PAD History to DMN

**User Story:** As DMN, I want access to recent PAD history, so that I can
crystallize an EmotionNode when a PAD state reaches poignancy_category = critical
during idle consolidation.

#### Acceptance Criteria

1. THE PAD_Engine SHALL maintain a PAD_History consisting of the PAD coordinates
   recorded at each of the last PAD_HISTORY_LENGTH Soul_Tick events, where
   PAD_HISTORY_LENGTH is a configurable build-time constant (see Build-Time
   Tuning Constants).
2. THE PAD_Engine SHALL output PAD_History to DMN for EmotionNode crystallization.

### Requirement 7: PAD Purity — No Direct Assignment, No Bypass Formulas

**User Story:** As the Aria system architect, I want it structurally impossible for
any mechanism to write to PAD outside the appraisal-delta-plus-decay chain, so that
Principle 19 ("nothing touches PAD directly") holds for the whole system, not just
by convention.

#### Acceptance Criteria

1. THE PAD_Engine SHALL NOT expose any interface that allows direct assignment of a
   Pleasure, Arousal, or Dominance value.
2. THE PAD_Engine SHALL NOT apply any formula, coefficient, or pathway to Pleasure,
   Arousal, or Dominance other than an Appraisal_Chain PAD_Delta (Requirement 2) or
   EMA_Decay (Requirement 3).
3. IF Needs System (Module 2) needs-pressure information reaches PAD_Engine, THEN
   THE PAD_Engine SHALL reject it as a direct PAD input, because needs pressure is
   defined elsewhere in the architecture as a Stage 1 retrieval-preference context
   shaper that must be appraised through Appraisal_Chain before it can affect PAD,
   never as a direct pull on PAD.
4. IF the F4 interrupt key or barge-in signal reaches PAD_Engine as a request to
   modify PAD, THEN THE PAD_Engine SHALL reject it, because F4 and barge-in are
   defined elsewhere in the architecture as zero-internal-effect audio stop
   mechanisms with no PAD effect.

### Requirement 8: Fixed PAD Baseline

**User Story:** As the Aria system architect, I want the PAD baseline fixed at the
locked value, so that Aria's resting emotional state is consistent across restarts
and matches the design intent (not too happy, not too anxious, not emotionally
null).

#### Acceptance Criteria

1. THE PAD_Engine SHALL use [Pleasure=0.55, Arousal=0.45, Dominance=0.58] as the
   fixed PAD_Baseline.
2. THE PAD_Engine SHALL treat PAD_Baseline as a constant that is not altered at
   runtime, at build time, or through any configuration mechanism exposed by this
   module.

### Requirement 9: Boundary With State Manager (Module 11)

**User Story:** As the Aria system architect, I want a strict ownership boundary
between PAD_Engine and State_Manager, so that persistence plumbing can never become
a second owner of emotional state.

#### Acceptance Criteria

1. THE PAD_Engine SHALL own the live, in-memory Pleasure, Arousal, and Dominance
   values.
2. THE PAD_Engine SHALL treat State_Manager as a serialization-only dependency:
   State_Manager persists the PAD values PAD_Engine supplies to it, and supplies a
   persisted or baseline PAD value back to PAD_Engine on restore.
3. THE PAD_Engine SHALL NOT delegate PAD computation, PAD decay, or PAD_Delta
   application to State_Manager.
4. IF State_Manager returns a value on restore, THEN THE PAD_Engine SHALL treat
   that value as the initial current PAD state, subject to Requirement 1.3 (baseline
   fallback when no prior persisted state is available or the persisted value is
   invalid).

## Open Questions

The following items were genuinely undefined across `ARIA_Soul_Spec_v4.md`, the
Addendum, the Resolution Log, and the Module Build Plan when first identified. Per
the covering instruction's Rule 1 and Rule 2, they were flagged here rather than
resolved by invention. None of them are treated as blocking the transcription
above, since the Module 1 entry itself states "Flags: None" — but they affect the
testability of Requirements 3 and 6. Items 2 and 3 have since been resolved (see
below); item 1 remains an open build-time gap; item 4 has been narrowed (see
below) but not closed.

1. **Soul_Tick cadence.** Per `ARIA_Resolution_Log.md`, this is explicitly listed as
   an open build-time tuning constant ("only idle=8min, reflection=6h pinned"), not
   an architectural gap. Recorded here for completeness; no requirement in this
   document depends on a specific cadence value.

2. **Numeric bounds on PAD dimensions — RESOLVED (architect decision).**
   Pleasure, Arousal and Dominance are bounded to [0.0, 1.0], clamped in
   `PAD_Engine.apply_appraisal_delta`. No source document states the bound, so
   this is an explicit architect ruling rather than a citation: Mehrabian's own
   standardized PAD scales are bounded ([-1, +1]), Russell's circumplex is a
   bounded space, and emotion-regulation research requires bounded intensity for
   adaptive regulation to function. EMA_Decay provides natural recovery from a
   bounded extreme; unbounded PAD would allow a single event to create an
   unrealistically prolonged emotional state (e.g. Pleasure = 50 taking hundreds
   of ticks to decay). v4's baseline (0.55, 0.45, 0.58) and every PAD-zone /
   prosody table in the built system already assume a normalized [0, 1] range,
   which corroborates the bound. Earlier revisions of this spec described the
   resolution as "no clamping code introduced" — that description was factually
   incorrect against the shipped module and is superseded here.

   **Residual, NEW open question (flagged, not resolved):** the clamp is applied
   only in `apply_appraisal_delta`. `initialize()` does not clamp a restored
   snapshot — `_is_valid_snapshot` rejects only NaN, +/-inf, non-numeric and
   bool — so an out-of-range persisted value would be restored as-is. Whether
   `initialize()` should clamp, reject, or continue to accept such a value is
   for the architect to decide.

3. **Decay coefficient for VALENCE_UNCERTAIN originating events — RESOLVED.**
   Requirement 3 / EMA_Decay did not originally specify which decay coefficient
   applies when the originating event's Q2 = VALENCE_UNCERTAIN rather than
   positive/negative/neutral. This is now resolved: VALENCE_UNCERTAIN uses the
   same coefficient as a negative valence (0.6), not a new value. Rationale:
   v4's Emergency Type Detection already establishes "when classification is
   ambiguous, default to the more cautious treatment" (UNCLASSIFIED defaults to
   Type B, the most careful emergency type). VALENCE_UNCERTAIN is a real Q2
   appraisal outcome (the appraisal ran and returned an ambiguous category, not
   missing data), so this precedent applies directly, and the existing negative
   coefficient is reused rather than a third value being invented. See
   design.md's "Open Question 3 (Resolved): VALENCE_UNCERTAIN Decay
   Coefficient" section for full detail.

4. **Decay coefficient on restore, before any same-session delta — NARROWED,
   not resolved.** When PAD_Engine restores a valid, non-baseline PAD from
   State_Manager on startup, and no Appraisal_Chain PAD_Delta has been applied
   yet this session, on_soul_tick has no stored valence to select an EMA_Decay
   coefficient from. This was originally a routine gap, because
   state_manager.py did not persist the valence of the appraisal that produced
   the persisted PAD alongside the PAD value itself. That specific omission is
   now fixed at the data layer: state_manager.py persists a
   `last_applied_valence` field alongside PAD
   (`load_last_applied_valence`/`save_last_applied_valence`), and
   PAD_Engine's `initialize()` gained a `restored_valence` parameter that
   populates its stored valence from that persisted field on a normal restart.
   This means the gap no longer occurs on every restart — only in the residual
   case where no persisted valence exists at all (first-ever run, a
   corrupted/missing field, or a crash between an appraisal delta and the next
   save). No source document specifies which coefficient (if any) applies in
   that residual case, and none is invented here — it is still flagged for
   architect decision, not resolved. This is distinct from (former) Open
   Question 3 (VALENCE_UNCERTAIN as an originating valence value) — this gap is
   a persistence-boundary omission (valence not stored at all, in the residual
   case), not an unresolved valence value. See design.md's "Open Question 4
   (Narrowed): Restore-Boundary Decay Coefficient" and its `initialize()` /
   `on_soul_tick` discussion for full detail.

## Build-Time Tuning Constants

The following values are intentionally left as open placeholders to be tuned once
Soul_Tick cadence is locked, rather than treated as architectural gaps. This is
consistent with how `ARIA_Resolution_Log.md` treats other undetermined cadences
(k_load/k_rest, the soul-tick interval, State Manager write cadence) as build-time
tuning constants.

- **PAD_HISTORY_LENGTH**: The number of most recent Soul_Tick values retained in
  PAD_History (Requirement 6). No source document specifies this value; it is left
  as an open build-time tuning constant to be set once Soul_Tick cadence is locked.


---

## pad-engine — design.md

# Design Document — Module 1: PAD Engine

## Overview

PAD_Engine is the sole owner and mutator of Aria's live, in-memory Pleasure,
Arousal, and Dominance (PAD) state. It is a small, synchronous, in-process
component with exactly two mutation paths — an Appraisal_Chain PAD_Delta
(including an Aha_Insight_PAD_Delta) and EMA_Decay on every Soul_Tick — and a
read-only fan-out to five consumers plus a bounded PAD_History feed to DMN.

This design implements requirements.md as written, using only mechanisms
already specified there or in the supporting documents
(`ARIA_Soul_Spec_v4.md`, `ARIA_Soul_Spec_v4_Addendum.md`,
`ARIA_Resolution_Log.md`, `ARIA_Module_Build_Plan.md` Module 1 entry,
`daemon/state_manager.py`). No new mechanism, formula, or persisted field is
introduced. Where requirements.md leaves something as a build-time tuning
constant or genuinely unspecified (PAD_HISTORY_LENGTH, Soul_Tick cadence,
neutral-valence handling, the residual restore-boundary decay coefficient),
the design carries that placeholder forward rather than resolving it by
invention. PAD numeric bounds are no longer in that list: former Open
Question 2 is RESOLVED by architect decision — PAD is bounded to [0.0, 1.0],
clamped in `apply_appraisal_delta` (see requirements.md Open Question 2 for
the rationale and the residual `initialize()` question). Former Open
Question 3 (VALENCE_UNCERTAIN's decay coefficient) is now resolved — see
"Open Question 3 (Resolved): VALENCE_UNCERTAIN Decay Coefficient" below —
by reuse of an existing locked constant, not by invention of a new one.

## Hard Constraints (carried from requirements.md, non-negotiable)

1. PAD_Engine is the only module that mutates Pleasure, Arousal, Dominance
   (Req 1.2, Req 7.1).
2. The only two mutation paths are an Appraisal_Chain PAD_Delta and EMA_Decay
   (Req 2.2, Req 3.4, Req 7.2).
3. PAD_Baseline is fixed at [Pleasure=0.55, Arousal=0.45, Dominance=0.58] and
   is never altered at runtime, build time, or via configuration (Req 8).
4. State_Manager is serialization-only: it never computes, decays, or applies
   a PAD_Delta. PAD_Engine treats it purely as a restore/persist boundary
   (Req 9).
5. No interface exists for direct assignment of P, A, or D (Req 7.1).
6. Needs-pressure, F4/barge-in signals are rejected as direct PAD inputs if
   they ever reach PAD_Engine (Req 7.3, Req 7.4).

## Architecture

```
                    ┌─────────────────────────────────────────┐
                    │              PAD_Engine                  │
                    │                                           │
  Appraisal_Chain ──┼──▶ apply_appraisal_delta(dP,dA,dD,valence)│
  (incl. Aha        │        │                                  │
   Insight delta)   │        ▼                                  │
                    │   ┌──────────────┐                        │
  Daemon ───────────┼──▶│  Soul_Tick   │                        │
  (Soul_Tick signal, │  │  handler     │                        │
   no valence arg)   │  │ (EMA decay,  │                        │
                    │   │  reads last- │                        │
                    │   │  applied     │                        │
                    │   │  valence     │                        │
                    │   │  internally) │                        │
                    │   └──────┬───────┘                        │
                    │          ▼                                │
                    │   ┌─────────────────────┐                 │
                    │   │  current PAD state   │                │
                    │   │  (P, A, D floats)     │                │
                    │   └─────────┬───────────┘                 │
                    │             │  Soul_Tick outcomes append   │
                    │             ▼   to history                │
                    │   ┌─────────────────────┐                 │
                    │   │  PAD_History          │                │
                    │   │  (bounded ring buffer,│                │
                    │   │  len = PAD_HISTORY_   │                │
                    │   │  LENGTH)              │                │
                    │   └─────────┬───────────┘                 │
                    │             │                              │
                    │   restore/persist via State_Manager        │
                    │   (aria_state.json "pad" key — unchanged)   │
                    └──────┬──────┬──────┬──────┬──────┬─────────┘
                           │      │      │      │      │
                     Soul_Filter Visual Audio Appraisal Daemon
                     (Behavioral  _Layer Pipe- _Chain   (thinking-
                      Register)   (zone) line   Stage 1  sound +
                                         (pros- (mood-   zone)
                                          ody)   congruent
                                                 sign +
                                                 coping)
                                                                DMN
                                                          (PAD_History →
                                                           EmotionNode
                                                           crystallization)
```

PAD_Engine has exactly two inbound mutation entry points and six outbound
read paths (five current-PAD consumers + one PAD_History consumer). Every
other module-facing surface is read-only.

## Components and Interfaces

### PADEngine (class)

Owns the single source of truth for live PAD state and PAD_History. Runs
in-process; no network or IPC boundary is introduced (none is specified).

**State held:**
- `_pleasure: float`, `_arousal: float`, `_dominance: float` — current PAD.
  Unset until `initialize()` is called.
- `_last_applied_valence: Optional[Valence]` — the valence of the most
  recently applied `PADDelta`, set inside `apply_appraisal_delta`; `None`
  until the first `PADDelta` is applied this process lifetime. Read by
  `on_soul_tick` to select the EMA_Decay coefficient, since Daemon
  (Module 8) does not own appraisal valence data per the Build Plan's
  Module 8 entry, and Requirement 4.2 defines Soul_Tick as a signal only —
  so Daemon cannot supply the valence as a parameter.
- `_history: Deque[PADSnapshot]` — bounded to `PAD_HISTORY_LENGTH` entries,
  oldest evicted automatically once full (standard ring-buffer semantics;
  this is an implementation detail of "the last PAD_HISTORY_LENGTH Soul_Tick
  values," not a new mechanism).

`_pleasure`/`_arousal`/`_dominance` are bounded to [0.0, 1.0] — former Open
Question 2 (PAD numeric bounds) is RESOLVED by architect decision, not left
unbounded. The bound is enforced only where PAD changes value:
`apply_appraisal_delta` clamps after adding the delta (see below); `on_soul_tick`
needs no clamp of its own, since EMA_Decay cannot carry an in-range value past
an in-range baseline. See requirements.md's Open Question 2 for the rationale
and the residual `initialize()` question (a restored out-of-range snapshot is
not currently clamped or rejected).

**Mutation methods (the only two ways PAD changes):**

- `apply_appraisal_delta(delta: PADDelta) -> None`
  Implements Req 2.1, 2.2, 4.1, 4.3. Adds `(dP, dA, dD)` to current PAD.
  Accepts a `PADDelta` regardless of whether its origin is a normal
  Appraisal_Chain event or an `Aha_Insight_PAD_Delta` — both are the same
  type at this boundary (per the Aha_Insight_PAD_Delta glossary entry: it
  arrives "via the Appraisal Chain like any other PAD_Delta"). Does not
  branch on `delta.origin` — `"appraisal"` and `"aha_insight"` are
  processed identically (Req 4.3). Does not append to `_history` itself
  (see PAD_History Semantics below — only Soul_Tick outcomes are
  recorded). Stores `delta.valence` into `_last_applied_valence` so that a
  subsequent `on_soul_tick` call can read it without Daemon needing to
  supply it.

- `on_soul_tick() -> None`
  Implements Req 3.1–3.4, Req 4.2. Called once per Soul_Tick signal from
  Daemon, with **no arguments** — per Requirement 4.2, Soul_Tick is a
  signal only, and Daemon does not own appraisal valence data, so it
  cannot be a parameter here. Instead, `on_soul_tick` reads
  `_last_applied_valence` internally. That value is one of `POSITIVE`,
  `NEGATIVE`, `NEUTRAL`, `VALENCE_UNCERTAIN`, or `None` (no `PADDelta`
  applied yet this process lifetime, and no `restored_valence` supplied
  to `initialize()`).

  Selects exactly one coefficient for the whole tick, applied uniformly to
  P, A, and D (never chosen independently per dimension, per the
  Glossary's EMA_Decay definition):

  - `NEGATIVE` → `EMA_COEFFICIENT_NEGATIVE` (0.6), applied uniformly to
    P, A, D. (Req 3.2)
  - `VALENCE_UNCERTAIN` → also `EMA_COEFFICIENT_NEGATIVE` (0.6) — the
    same coefficient as `NEGATIVE`, not a new value. This is the resolved
    former Open Question 3; see "Open Question 3 (Resolved):
    VALENCE_UNCERTAIN Decay Coefficient" below for the rationale.
  - `POSITIVE` → `EMA_COEFFICIENT_POSITIVE` (0.75), applied uniformly to
    P, A, D. (Req 3.3)
  - `NEUTRAL` → unspecified by any source document. Per Requirement 3's
    note, this is **not** an Open Question in requirements.md — it is
    recorded as an in-requirement note only, since "coefficient selection
    is now specified as a per-tick, valence-driven decision." This design
    does not invent a resolution: raises `NotImplementedError`. This case
    is distinct from the residual restore-boundary case below — the two
    are never conflated in this design, in error messages, or in tests.
  - `None`, split into two sub-cases by whether current PAD is exactly at
    `PAD_BASELINE`:
    - PAD **exactly** `PAD_BASELINE` → decay is skipped for that tick
      (no-op). A fresh startup with no `PADDelta` ever applied and PAD
      still at baseline has no originating valence and no non-baseline
      value to decay — decaying baseline toward baseline is a no-op
      regardless of which (unresolved) coefficient would have been
      selected, so skipping resolves nothing by invention. The tick still
      "occurred," so the unchanged baseline snapshot is still appended to
      `_history` (Req 6.1).
    - PAD **not** at `PAD_BASELINE` (a non-baseline value was restored via
      `initialize()` and neither a `PADDelta` nor a `restored_valence`
      has supplied a valence yet this session) → this is the **residual,
      narrowed** Open Question 4 (see "Open Question 4 (Narrowed):
      Restore-Boundary Decay Coefficient" below). `state_manager.py` now
      persists `last_applied_valence` alongside PAD
      (`load_last_applied_valence`/`save_last_applied_valence`), and
      `initialize()`'s `restored_valence` parameter (see Restore/persist
      boundary below) populates `_last_applied_valence` on a normal
      restart, so this raise is now expected to be rare rather than
      routine — it fires only when no persisted valence exists at all
      (first-ever run, a corrupted/missing field, or a crash between an
      appraisal delta and the next save). This design still does not
      invent a default (not 0.6, not 0.75, not "skip decay this once")
      for that remaining case: raises `NotImplementedError`, with a
      message distinct from the `NEUTRAL` case above.

  For the `NEGATIVE`/`VALENCE_UNCERTAIN`/`POSITIVE`/baseline-skip cases,
  decay (or its no-op) is applied toward `PAD_BASELINE` using the standard
  EMA form `new = coefficient * baseline + (1 - coefficient) * current`
  for each of P, A, D independently — this is the "exponential moving
  average decay" the Glossary names; no other formula is introduced. The
  resulting `PADSnapshot` is appended to `_history` after decay is applied
  (this is the Soul_Tick "PAD coordinates recorded" per Req 6.1). No
  history entry is appended when `on_soul_tick` raises (`NEUTRAL` or the
  residual restore-boundary case) — the tick did not complete.

**Read-only accessors (no mutation):**

- `get_current_pad() -> PADSnapshot` — implements Req 5.1–5.5. One method,
  five callers (Soul_Filter, Visual_Layer, Audio_Pipeline, Appraisal_Chain
  Stage 1, Daemon). PAD_Engine does not need to know which caller is asking;
  the requirement is satisfied by all five modules being permitted to call
  the same read accessor.
- `get_pad_history() -> Tuple[PADSnapshot, ...]` — implements Req 6.2.
  Returns an immutable snapshot (tuple copy) of the current history buffer
  to DMN, so DMN cannot mutate PAD_Engine's internal state through the
  returned reference. Unlike `get_current_pad`, `on_soul_tick`, and
  `apply_appraisal_delta`, this method is not gated by the
  pre-`initialize()` guard: `_history` exists and is legitimately empty
  regardless of `initialize()` state, so returning an empty tuple before
  `initialize()` has been called is a truthful answer, not undefined
  behavior.

**Rejection path (Req 7.3, 7.4):**

No method exists on `PADEngine` that accepts a Needs System value, an F4
signal, or a barge-in signal as an argument. This is the primary
enforcement mechanism for Req 7.3/7.4: there is structurally nothing to
call. If a caller nonetheless attempts to route such a value through
`apply_appraisal_delta`, that is a caller-side integration bug, not a case
`PADEngine` needs to detect — the type of `apply_appraisal_delta`'s
parameter is `PADDelta`, sourced only from Appraisal_Chain Stage 4 by
contract with that module. No defensive runtime check against Needs System
or F4/barge-in payloads is added, because no source document specifies what
such a rejection response should look like beyond "reject it" — building a
detection/rejection API surface for inputs that have no defined call path
into PAD_Engine would itself be an invented mechanism.

**Restore / persist boundary (Req 9):**

- `initialize(restored: Optional[PADSnapshot], restored_valence: Optional[Valence] = None) -> None` —
  implements Req 1.3, 9.4. If `restored` is `None` or fails basic validity
  (not three finite floats), sets current PAD to `PAD_BASELINE`. Otherwise
  sets current PAD to `restored` exactly. This is the only role
  State_Manager plays: supplying `restored` (or nothing) at startup, and
  later reading `get_current_pad()` to persist it. `PADEngine` never calls
  into `StateManager` for decay or delta application (Req 9.3) —
  `state_manager.py` already enforces the reverse direction (it does not
  compute PAD; see its module docstring). `initialize()` sets
  `_last_applied_valence` to `restored_valence` (which defaults to
  `None`) — this is the fix for the routine case of the narrowed Open
  Question 4 (see below): on a normal restart, the call-site wiring layer
  loads the persisted `last_applied_valence` string via
  `state_manager.py`'s `load_last_applied_valence()`, converts it to a
  `Valence` via the extended conversion helper (see below), and passes it
  here, so `_last_applied_valence` is no longer `None` and
  `on_soul_tick`'s residual restore-boundary raise does not fire for that
  session. If the caller has no persisted valence (first-ever run, a
  corrupted/missing field, or a crash between an appraisal delta and the
  next save), it passes `None` (the default), and the two distinct
  `None`-valence cases under `on_soul_tick` above (baseline-skip vs.
  residual restore-boundary raise) are handled exactly as before.

  The conversion from `state_manager.py`'s `PADState` (the type
  `StateManager.load_pad()` returns) to this module's `PADSnapshot` (the
  type `initialize()`'s `restored` parameter accepts), and the conversion
  from `state_manager.py`'s persisted `last_applied_valence` string (the
  type `StateManager.load_last_applied_valence()` returns) to this
  module's `Valence` (the type `initialize()`'s `restored_valence`
  parameter accepts), both happen at the call site that wires `PADEngine`
  and `StateManager` together (e.g. Daemon's startup sequence) — not
  inside `PADEngine` and not inside `StateManager`. Neither class is
  modified to know about the other's type; each remains defined only in
  terms of its own dataclass/enum. Both conversions are the
  responsibility of the same single helper function (extended, not
  duplicated) — see "Open Question 4 (Narrowed)" below for the string→
  `Valence` half of that helper's contract.

### Data Types

```python
class Valence(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    VALENCE_UNCERTAIN = "valence_uncertain"

@dataclass(frozen=True)
class PADSnapshot:
    pleasure: float
    arousal: float
    dominance: float

@dataclass(frozen=True)
class PADDelta:
    d_pleasure: float
    d_arousal: float
    d_dominance: float
    # valence of the Appraisal_Chain event that produced this delta.
    # Stored by apply_appraisal_delta into _last_applied_valence, and read
    # by on_soul_tick (which takes no parameter of its own) to select the
    # EMA_Decay coefficient; does not affect how apply_appraisal_delta adds
    # d_pleasure/d_arousal/d_dominance. This field is a scope addition
    # relative to the Build Plan's three named inputs (see requirements.md
    # Requirement 4's note) — introduced to make the Resolution Log's
    # whole-event, per-tick decay decision implementable.
    valence: Valence
    # origin is informational only (e.g. for logging/debugging); it does not
    # change how the delta is applied, since Aha_Insight_PAD_Delta and a
    # normal PAD_Delta are processed identically (Req 4.3).
    origin: Literal["appraisal", "aha_insight"] = "appraisal"
```

`Valence` has exactly four members: `POSITIVE`, `NEGATIVE`, `NEUTRAL`,
`VALENCE_UNCERTAIN`. The fourth member exists because v4's EventNode schema
defines `appraisal_q2` as four-valued, and a partial appraisal can still
produce a real PAD_Delta at Stage 4 with Q2 = VALENCE_UNCERTAIN. Former
Open Question 3 (which coefficient `VALENCE_UNCERTAIN` should use) is now
resolved — it reuses `EMA_COEFFICIENT_NEGATIVE` — see "Open Question 3
(Resolved): VALENCE_UNCERTAIN Decay Coefficient" below.

`PADSnapshot` and `PADDelta` are frozen/immutable so that no consumer
holding a returned snapshot can mutate PAD_Engine's live state — the only
mutation paths remain the two methods above.

### Constants

```python
PAD_BASELINE = PADSnapshot(pleasure=0.55, arousal=0.45, dominance=0.58)  # Req 8, locked

EMA_COEFFICIENT_NEGATIVE = 0.6   # Req 3.2, locked
EMA_COEFFICIENT_POSITIVE = 0.75  # Req 3.3, locked

# Build-time tuning constant (requirements.md "Build-Time Tuning Constants").
# Placeholder default; to be tuned once Soul_Tick cadence is locked (Open
# Question 1). Not an architectural decision — mirrors state_manager.py's
# SAVE_CADENCE_SECONDS and the Resolution Log's k_load/k_rest treatment.
PAD_HISTORY_LENGTH = 50  # placeholder default, tune at build time
```

`PAD_BASELINE` matches `state_manager.py`'s existing `PAD_BASELINE = (0.55,
0.45, 0.58)` constant exactly — this design does not introduce a second
definition of the baseline; PAD_Engine and State_Manager agree on the same
locked value, consistent with Req 8 treating it as a single constant. The
existing `state_manager.py` remains unmodified: it already returns this
baseline as the default when no persisted state exists, which is exactly
the fallback `PADEngine.initialize()` needs.

No coefficient constant is defined for `NEUTRAL` or the residual
restore-boundary case — defining one would silently resolve an
unresolved requirement/Open Question by invention. `VALENCE_UNCERTAIN`
does **not** get a new constant either: former Open Question 3 is
resolved by reusing `EMA_COEFFICIENT_NEGATIVE` (see `on_soul_tick` above
and "Open Question 3 (Resolved)" below), per the Addendum's "reuse before
invent" principle, rather than by inventing a third coefficient value.

## Neutral Valence Handling (Requirement 3's note — NOT an Open Question)

Requirements.md Requirement 3 records that "handling of the case where the
Appraisal_Chain event that produced the current Soul_Tick's context has a
neutral valence is not specified in any source document," deliberately
choosing not to invent behavior, and explicitly recording this as an
in-requirement note rather than a separate Open Question.

- `on_soul_tick` accepts no arguments and internally reads
  `_last_applied_valence`, which may legitimately be `Valence.NEUTRAL` if
  the most recently applied `PADDelta` carried that valence (Daemon itself
  never reports valence; see Components and Interfaces).
- No EMA coefficient is defined for the neutral case in this design. The
  method raises `NotImplementedError` with a message pointing at
  requirements.md Requirement 3's note, rather than silently defaulting to
  0.6, 0.75, or "no decay." Silently picking any of those would resolve an
  explicitly-unresolved requirement without architect sign-off, which
  contradicts the no-invented-mechanism constraint carried through this
  entire spec chain (Module 1 entry "Flags: None" notwithstanding — this
  specific sub-case was never in scope of that flag-free statement).
- This case must never be conflated with the residual restore-boundary
  case (Open Question 4, narrowed — see below) — they are triggered by
  different conditions (`_last_applied_valence is Valence.NEUTRAL` vs.
  `_last_applied_valence is None` and PAD non-baseline), raising the same
  exception type but with different messages and different
  justifications (an unspecified requirement note here, vs. a flagged,
  narrowed Open Question there). `VALENCE_UNCERTAIN` is no longer a
  raising case at all (former Open Question 3, now resolved), so it is
  not part of this comparison.
- This is flagged in Testing Strategy below as a required architect
  decision before this code path can ship; it does not block building and
  testing the positive/negative paths, which are fully specified.

## Open Question 3 (Resolved): VALENCE_UNCERTAIN Decay Coefficient

Former Open Question 3 asked: "Decay coefficient for VALENCE_UNCERTAIN
originating events. Requirement 3 / EMA_Decay do not specify which decay
coefficient applies, if any, when the originating event's Q2 =
VALENCE_UNCERTAIN rather than positive/negative/neutral." This is now
resolved, not carried forward as an open gap.

**Decision:** `VALENCE_UNCERTAIN` uses `EMA_COEFFICIENT_NEGATIVE` (0.6),
not a new coefficient.

**Rationale:** v4's Emergency Type Detection already establishes "when
classification is ambiguous, default to the more cautious treatment"
(UNCLASSIFIED defaults to Type B, the most careful emergency type).
`VALENCE_UNCERTAIN` is a real Q2 appraisal outcome — the appraisal ran and
returned an ambiguous category, it is not missing data — so this
precedent applies directly: an ambiguous appraisal outcome gets the more
cautious (slower-recovery) treatment, the same as an unambiguously
negative one. This design reuses the existing `EMA_COEFFICIENT_NEGATIVE`
constant rather than inventing a third coefficient value, per the
Addendum's "reuse before invent" principle — no new constant is added to
the Constants section for this.

`on_soul_tick`, when `_last_applied_valence` is
`Valence.VALENCE_UNCERTAIN`, selects `EMA_COEFFICIENT_NEGATIVE` and
applies it uniformly to P, A, D exactly as it does for `Valence.NEGATIVE`
— the two cases are handled by the same coefficient value but remain
distinct branches in the implementation (not merged into a single
`NEGATIVE`-or-`VALENCE_UNCERTAIN` check), so that a future re-opening of
this decision does not require re-deriving where `VALENCE_UNCERTAIN` is
handled. This case no longer raises `NotImplementedError` and no longer
needs a distinct exception message, since it no longer raises at all.

This resolution does not touch or reference Open Question 4 (below) —
the two were always distinct gaps (an unresolved *value* here, formerly;
a persistence-boundary *omission* there), and resolving one does not
resolve or narrow the other on its own. Open Question 4 is narrowed by a
separate, unrelated mechanism (persisting `last_applied_valence`), not by
this decision.

## Open Question 4 (Narrowed): Restore-Boundary Decay Coefficient

Open Question 4 asked: "Decay coefficient on restore, before any
same-session delta. When PAD_Engine restores a valid, non-baseline PAD
from State_Manager on startup, and no Appraisal_Chain PAD_Delta has been
applied yet this session, on_soul_tick has no stored valence to select an
EMA_Decay coefficient from — state_manager.py does not persist the
valence of the appraisal that produced the persisted PAD alongside the
PAD value itself."

**This question is narrowed, not resolved.** It is not a
coefficient-selection problem — no coefficient decision has been made
here, and none is being invented. It was, and remains, a missing-data
problem: `on_soul_tick` cannot select a coefficient without a valence,
and if no valence is available, no coefficient is selected — it raises
instead. What has changed is how often that missing-data condition
actually occurs.

**What changed:** `state_manager.py` now persists the value this
question was missing, via `save_last_applied_valence(valence:
Optional[str]) -> None` and `load_last_applied_valence() -> Optional[str]`
(and via the 4th value in `load_all()`/`save_all()`), storing it as an
opaque string — `state_manager.py` "owns no meaning" (ARIA_Resolution_Log
item 4) and does not know this string is a `Valence` member name; it does
not import or reference `Valence`. `PADEngine.initialize()` gained a new
parameter, `restored_valence: Optional[Valence] = None` (see Restore /
persist boundary above). When the call-site wiring layer (a) loads the
persisted string via `load_last_applied_valence()`, (b) converts it to a
`Valence` via the same conversion helper that already converts `PADState`
to `PADSnapshot` (extended, not duplicated, to also handle this
conversion), and (c) passes the result as `restored_valence`, then
`_last_applied_valence` is populated on `initialize()` and the
restore-boundary case in `on_soul_tick` no longer fires for that session
— because `_last_applied_valence` is no longer `None`.

The extended conversion helper's contract for the string→`Valence` half:
given the raw string `load_last_applied_valence()` returns (or `None`),
look up a `Valence` member whose `.value` matches the string; if the
string is `None`, missing, or does not match any known `Valence` value,
the helper returns `None` — it does not guess a member. This mirrors the
existing `PADState`→`PADSnapshot` half's validity handling and keeps the
"do not invent" discipline at the boundary rather than inside `PADEngine`.

**What did not change:** the `on_soul_tick` restore-boundary raise itself
— its trigger condition (`_last_applied_valence is None` AND current PAD
is not exactly `PAD_BASELINE`) and its `NotImplementedError` message are
unchanged. No default coefficient is picked for this case now or before.
This design still does not invent a resolution for "what coefficient
applies when truly no valence is available on restore" — it has only
reduced how often that condition arises. The raise now fires only when no
persisted valence exists at all: a first-ever run (nothing has ever been
saved), a corrupted or missing `last_applied_valence` field on disk, or a
crash between an appraisal delta being applied and the next `save_all()`/
`save_last_applied_valence()` call. This residual case is expected to be
rare rather than routine, but it is not eliminated, and this design does
not claim it is.

This is still distinct from the (now-resolved) former Open Question 3 —
this gap was, and remains, a persistence-boundary matter (a valence that
either is or is not available at restore time), not an unresolved
valence *value* — the two are never merged.

## PAD_History Semantics

- `PAD_HISTORY_LENGTH` (build-time constant, placeholder default above)
  bounds the buffer. When a new Soul_Tick outcome is appended and the
  buffer is already at `PAD_HISTORY_LENGTH` entries, the oldest entry is
  evicted (standard bounded-queue behavior — not a new mechanism, just the
  literal meaning of "the last PAD_HISTORY_LENGTH Soul_Tick values").
  Implemented with `collections.deque(maxlen=PAD_HISTORY_LENGTH)`.
- Only Soul_Tick outcomes that complete (`NEGATIVE`, `POSITIVE`, or the
  baseline-skip no-op) are appended to `PAD_History`. A tick that raises
  (`NEUTRAL`, `VALENCE_UNCERTAIN`, or the restore-boundary case) does not
  append, since it did not complete.
- An `apply_appraisal_delta` call by itself does not append a history
  entry, because Requirement 6 defines PAD_History in terms of
  "Soul_Tick events," not appraisal events. A `PADDelta` applied between
  ticks is reflected in the *next* Soul_Tick's recorded value (that tick's
  EMA decay runs against whatever the current PAD is at the moment the
  tick fires, which already includes any deltas applied since the
  previous tick) — this follows directly from Req 3.1 ("apply EMA_Decay to
  the current... values") and Req 6.1 ("PAD coordinates recorded at each
  of the last... Soul_Tick events") without needing a separate append call
  on delta application.

## Data Models

No graph, database, or new persisted schema is introduced beyond what
`state_manager.py` already implements. The only persisted representation
of PAD remains `aria_state.json`'s existing `"pad"` key
(`PADState.as_dict()` / `StateManager.load_pad()` / `save_pad()`).
`aria_state.json` also now has a `"last_applied_valence"` key
(opaque string or `null`), persisted via `state_manager.py`'s
`load_last_applied_valence()` / `save_last_applied_valence()` — this is
the field whose prior absence created Open Question 4; its addition is
what narrows that Open Question to the residual case described above,
without inventing a coefficient. `state_manager.py` stores this key as a
raw string and does not import or reference `Valence` — "owns no meaning"
(ARIA_Resolution_Log item 4) applies to this field exactly as it does to
`"pad"`. PAD_History is not persisted — no source document requires it to
survive a restart, and `state_manager.py`'s schema has no field for it;
introducing one would be a new persisted mechanism beyond current scope.
PAD_History is rebuilt in-memory from Soul_Tick events as they occur after
each process start, starting empty.

## Error Handling

- **Invalid restored PAD (Req 1.3 fallback, Req 9.4):** any non-finite or
  missing component from `State_Manager` on restore falls back to
  `PAD_BASELINE`, mirroring `state_manager.py`'s own `load_pad()` fallback
  behavior (it already returns `PADState.baseline()` on a corrupt entry).
  PAD_Engine performs its own validation at the boundary rather than
  trusting `State_Manager`'s return value blindly, since Req 9.4 makes
  PAD_Engine — not State_Manager — responsible for this decision.
- **Neutral valence on Soul_Tick:** see "Neutral Valence Handling" above —
  raises `NotImplementedError` rather than guessing. Not an Open Question.
- **VALENCE_UNCERTAIN valence on Soul_Tick:** no longer raises. See "Open
  Question 3 (Resolved)" above — reuses `EMA_COEFFICIENT_NEGATIVE`, the
  same coefficient as `NEGATIVE`.
- **Restored non-baseline PAD, first post-restart Soul_Tick, no valence
  available (neither a same-session delta nor a `restored_valence` was
  supplied to `initialize()`):** see "Open Question 4 (Narrowed)" above —
  raises `NotImplementedError` rather than guessing. This residual case is
  now expected to be rare rather than routine, since
  `state_manager.py`'s `load_last_applied_valence()` plus
  `initialize()`'s `restored_valence` parameter cover the routine restart
  case. Distinct from "invalid restored PAD" above (that case is a
  validity failure handled at `initialize()` time; this case is a valid
  restore followed by an unresolved decay decision at `on_soul_tick()`
  time, now occurring only when no persisted valence exists at all).
- **No direct-assignment surface exists to fail on** (Req 7.1) — there is
  no setter for P, A, or D individually; this is enforced by the class
  simply not exposing one, not by a runtime check.
- **Rejection of out-of-contract inputs (Req 7.3, 7.4):** enforced
  structurally by absent call paths, as described above under "Rejection
  path."
- **Calls before `initialize()`:** `get_current_pad()`, `on_soul_tick()`,
  and `apply_appraisal_delta()` all raise `RuntimeError` if called before
  `initialize()` has been called at least once — since
  `_pleasure`/`_arousal`/`_dominance` are unset until `initialize()` runs,
  none of these methods silently operate on unset or `None` state
  (`apply_appraisal_delta()` would otherwise add its delta components to
  unset values).

## Testing Strategy

Testing follows the acceptance criteria directly; PAD_Engine is a pure,
in-memory, dependency-light component, well suited to property-based
testing for its numeric/decay logic and example-based testing for its
structural/rejection guarantees.

**Property-based tests (behavior varies meaningfully with input, pure
function, low cost):**

1. *EMA decay moves current PAD toward baseline, never past it* (invariant)
   — for any starting PAD and either `POSITIVE` or `NEGATIVE` applied
   delta valence, after one `on_soul_tick` call, each of P/A/D lies
   strictly between its pre-tick value and the corresponding baseline
   value (or is unchanged if already at baseline). Covers Req 3.1–3.3.
2. *Coefficient selection is uniform across dimensions* (invariant) — for a
   given valence, the same coefficient is provably applied to P, A, and D
   (derivable algebraically from the pre/post values and baseline). Covers
   Req 3.2/3.3's "applied uniformly" language directly.
3. *Appraisal delta is a pure addition* (metamorphic) — `apply_appraisal_delta`
   followed by reading current PAD equals starting PAD plus the delta
   components, for any delta magnitude/sign, and for all four `Valence`
   members. Covers Req 2.1.
4. *PAD_History never exceeds PAD_HISTORY_LENGTH and preserves order*
   (invariant) — after any sequence of N completing soul-ticks,
   `len(get_pad_history()) == min(N, PAD_HISTORY_LENGTH)` and the buffer
   holds exactly the most recent ticks in chronological order (oldest
   evicted first). Covers Req 6.1.
5. *Aha_Insight_PAD_Delta and a normal PAD_Delta with identical components
   produce identical resulting PAD* (model-based / equivalence) — asserts
   Req 4.3's "processed identically" claim directly by comparing outcomes
   across the two `origin` values.

**Example-based / integration tests (structural guarantees, not
input-varying, or exercising the State_Manager boundary):**

6. Initialization with no persisted state (or an invalid persisted value)
   yields exactly `PAD_BASELINE` — Req 1.3, Req 9.4.
7. `PADEngine` exposes no public method that sets P, A, or D individually —
   a static/API-surface check (e.g. asserting the class's public method
   list matches the documented set) rather than a runtime behavior test —
   Req 7.1.
8. `get_current_pad()` returns an immutable value type; mutating the
   returned object (where the language allows attempting it) does not
   affect subsequent reads — Req 7.1's spirit, Req 5.*.
9. `get_pad_history()` returns a copy/immutable view; the caller (standing
   in for DMN) cannot alter `PADEngine`'s internal buffer through it — Req
   6.2.
10. Round-trip through `StateManager.save_pad` / `load_pad` preserves the
    PAD values PAD_Engine supplied, unchanged — Req 9.2, integration test
    against the existing `daemon/state_manager.py` (already has its own
    smoke test; this test exercises the two modules together, 1–3
    representative examples, not a property test, since it is verifying
    wiring to an already-tested external module, not PAD_Engine's own
    logic).
11. `on_soul_tick()` (no argument), with `_last_applied_valence` equal to
    `Valence.NEUTRAL` from a prior `apply_appraisal_delta` call, raises
    `NotImplementedError` rather than silently returning a value —
    documents the deliberate gap from requirements.md Requirement 3's
    note (NOT an Open Question) rather than letting it fail silently or
    inconsistently. This test should be revisited (and likely replaced)
    once the architect resolves neutral-valence handling.
12. `on_soul_tick()`, with `_last_applied_valence` equal to
    `Valence.VALENCE_UNCERTAIN` from a prior `apply_appraisal_delta` call,
    decays identically to `Valence.NEGATIVE` given the same starting PAD
    and delta magnitude — for two `PADEngine` instances started from the
    same restored (or baseline) PAD, one given a `NEGATIVE`-valence delta
    and the other a `VALENCE_UNCERTAIN`-valence delta of otherwise
    identical magnitude, `on_soul_tick()` produces identical resulting
    PAD on both. This replaces the former test asserting
    `VALENCE_UNCERTAIN` raises `NotImplementedError` (removed — that
    former Open Question 3 gap is now resolved, not merely re-tested
    around). Covers Req 3.1–3.3 and "Open Question 3 (Resolved)" above.
13. Restore of a non-baseline persisted PAD, followed immediately by an
    `on_soul_tick()` call with no valence available at all (no
    same-session `apply_appraisal_delta` call, and `initialize()` was
    called with `restored_valence=None`, so `_last_applied_valence` is
    `None`), raises `NotImplementedError` with a message distinct from
    test 11's — asserts that this residual path does not silently skip
    decay and does not silently default to 0.6 or 0.75. This is a
    distinct test from 11: it exercises the residual restore-boundary
    valence-loss case (Open Question 4, narrowed), not the neutral-valence
    case, and (unlike before this narrowing) is understood to be the rare
    case, not the routine one. Covers Req 3.1, Req 9.4. This test should
    be revisited only if the architect further resolves the residual
    case; it is unaffected by Open Question 3's resolution.
13b. `initialize()` called with a `restored_valence` (e.g.
    `Valence.NEGATIVE`) alongside a non-baseline `restored` snapshot,
    followed immediately by `on_soul_tick()` with no same-session
    `apply_appraisal_delta` call, does **not** raise — it decays using
    `restored_valence`'s coefficient, exactly as if that valence had been
    supplied via a same-session `apply_appraisal_delta` call. This is the
    routine post-restart case that narrows Open Question 4: it exercises
    exactly the condition that test 13 does NOT cover (a valence IS
    available at restore time, because the call-site wiring supplied
    one), and must not be confused with or merged into test 13. Covers
    Req 3.1, Req 9.4, and "Open Question 4 (Narrowed)" above.
14. Fresh startup with no prior persisted state (`_last_applied_valence` is
    `None` and current PAD is exactly `PAD_BASELINE`), followed by
    `on_soul_tick()` with no `apply_appraisal_delta` call yet made, is a
    no-op: PAD remains exactly `PAD_BASELINE`, no exception is raised, and
    exactly one entry is appended to `_history`. This is a distinct test
    from 13: PAD is at baseline here, so the skip is taken, rather than
    the residual restore-boundary gap being surfaced. Covers Req 3.1
    (decay against baseline is a no-op by construction, so skipping
    resolves nothing by invention).
15. The two remaining `NotImplementedError`-raising paths (tests 11 and
    13) never append to `_history` — a tick that raises did not complete,
    per PAD_History Semantics above. (Test 12 no longer raises, so it is
    not part of this list; its non-raising, decays-like-NEGATIVE behavior
    is covered by test 12 itself.)
16. The extended call-site conversion helper (Restore / persist boundary
    section), given a representative persisted `last_applied_valence`
    string that matches a known `Valence` member's `.value`, returns that
    `Valence` member; given `None`, a missing key, or a string that does
    not match any `Valence` member's `.value`, returns `None` rather than
    guessing a member. Covers the string→`Valence` half of "Open
    Question 4 (Narrowed)" above.

**Explicitly not property-tested:** the fixed numeric values 0.55/0.45/0.58
and 0.6/0.75 are locked constants, not input-varying behavior — asserted
with simple equality checks, not generated inputs (per the PBT decision
guide: no meaningful variation, testing a constant, not logic).

## Known Limitations

- **`initialize()` is not idempotent across repeated calls in the same
  process.** Calling `initialize()` more than once resets
  `_last_applied_valence` to whatever `restored_valence` is passed
  (`None` by default), discarding any valence set by intervening
  `apply_appraisal_delta` calls made between the two `initialize()`
  calls. No current caller does this — `initialize()` is only ever
  invoked once, at startup. But if Module 8 (Daemon) ever calls
  `initialize()` outside of pure startup, this will silently
  reintroduce the residual restore-boundary raise (narrowed Open
  Question 4 above) mid-session. Not fixed: no requirement addresses
  re-initialization semantics, and inventing one (e.g. "ignore a second
  `initialize()` call," or "preserve `_last_applied_valence` across
  re-initialization unless explicitly overridden") would resolve an
  unstated case by invention rather than by architect decision.


---

## pad-engine — tasks.md

# Implementation Plan — Module 1: PAD Engine

This plan implements design.md exactly as written. Each task is small and
independently testable.

## Quoted from design.md (verified against current file content)

**The four members of the `Valence` enum** (Data Types section):
```python
class Valence(Enum):
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    VALENCE_UNCERTAIN = "valence_uncertain"
```

**The five cases handled by `on_soul_tick()`** (Components and Interfaces
section, "Selects exactly one coefficient for the whole tick"):
1. `NEGATIVE` → 0.6, applied uniformly to P, A, D.
2. `VALENCE_UNCERTAIN` → also 0.6 (the same coefficient as `NEGATIVE`,
   reused rather than a new value invented). This is the **resolved**
   former Open Question 3 — see design.md's "Open Question 3 (Resolved):
   VALENCE_UNCERTAIN Decay Coefficient" section. No longer raises.
3. `POSITIVE` → 0.75, applied uniformly to P, A, D.
4. `NEUTRAL` → unspecified by any source document (per Requirement 3's
   note; **not** an Open Question in requirements.md — recorded as an
   in-requirement note only). Raises `NotImplementedError`.
5. `None` — split into two sub-cases:
   - `None` with current PAD exactly at `PAD_BASELINE` → decay is skipped
     for that tick (no-op); the tick still occurred, so an unchanged
     baseline snapshot is still appended to `_history`.
   - `None` with current PAD NOT at `PAD_BASELINE` (the **residual**
     restore-boundary case) → this is the **narrowed** Open Question 4.
     Left unresolved (still raises `NotImplementedError`), but now rare
     rather than routine, since `initialize()`'s new `restored_valence`
     parameter (populated from `state_manager.py`'s newly-persisted
     `last_applied_valence` field, on a normal restart) means
     `_last_applied_valence` is usually not `None` after restore anymore.
     This case is distinct from `NEUTRAL` — it arises from a
     persistence-boundary omission (no valence available at all), not
     from an unresolved valence value.

**The exact mapping of Open Questions 1–4 to their gaps**, per
requirements.md's Open Questions section and design.md's own Open Question
3 (Resolved) / Open Question 4 (Narrowed) sections:
- **Open Question 1** — Soul_Tick cadence: explicitly listed as an open
  build-time tuning constant, not an architectural gap. Carried forward as
  the `PAD_HISTORY_LENGTH`-adjacent placeholder-constant pattern; not
  resolved by this plan.
- **Open Question 2 — RESOLVED (architect decision).** Intentionally clamped
  to [0,1] in `apply_appraisal_delta`. EMA decay provides natural recovery
  from bounded extremes. Unbounded PAD would allow single events to create
  unrealistically prolonged emotional states (e.g., Pleasure = 50 taking
  hundreds of turns to decay). Grounded in Mehrabian's bounded PAD scales,
  Russell's bounded circumplex, and emotion-regulation research requiring
  bounded intensity. The earlier "no clamping code introduced" wording was
  incorrect against the shipped module and is superseded. Covered by
  `test_apply_appraisal_delta_clamps_to_bounds`. Residual NEW open question:
  `initialize()` still does not clamp an out-of-range restored snapshot —
  flagged for the architect, see requirements.md Open Question 2.
- **Open Question 3 — RESOLVED.** Decay coefficient for `VALENCE_UNCERTAIN`
  originating events: resolved to reuse `EMA_COEFFICIENT_NEGATIVE` (0.6),
  not a new coefficient. Implemented in **Task 14** (revised below) as a
  decay branch, not a raise. Rationale: v4's Emergency Type Detection
  precedent ("ambiguous → more cautious treatment") plus the Addendum's
  "reuse before invent" principle.
- **Open Question 4 — NARROWED, not resolved.** Decay coefficient on
  restore, before any same-session delta (the restore-boundary case:
  `_last_applied_valence` is `None` AND current PAD is not at
  `PAD_BASELINE`). Still implemented as a `NotImplementedError` raise in
  **Task 15**, unchanged — but now fixed at the data layer for the
  *routine* case via `state_manager.py`'s new
  `load_last_applied_valence`/`save_last_applied_valence` methods and
  `initialize()`'s new `restored_valence` parameter (**Task 7b**, added
  below), so Task 15's raise now fires only in the residual case (no
  persisted valence exists at all). Not resolved by this plan.

`NEUTRAL` valence handling (design.md's "Neutral Valence Handling" section)
is explicitly **not** an Open Question — it is a Requirement 3
in-requirement note, implemented in **Task 13**, kept distinct from the
now-resolved former Open Question 3 (`VALENCE_UNCERTAIN`, Task 14 — no
longer raises at all) and the narrowed Open Question 4 (residual
restore-boundary, Task 15) throughout this plan, including in each
raising task's own `NotImplementedError` message.

**Design.md additions this plan also implements exactly:**
- **`PADState` → `PADSnapshot` conversion ownership, extended to also
  cover the persisted valence string** (Restore / persist boundary
  section): the conversion happens at the call site that wires
  `PADEngine` and `StateManager` together (e.g. Daemon's startup
  sequence) — not inside `PADEngine`, not inside `StateManager`. Neither
  class is modified to know about the other's type. This single helper
  (Task 8) now converts both `PADState`→`PADSnapshot` and the persisted
  `last_applied_valence` string→`Optional[Valence]`.
- **Pre-`initialize()` error behavior** (Error Handling section):
  `get_current_pad()`, `on_soul_tick()`, and `apply_appraisal_delta()` all
  raise `RuntimeError` if called before `initialize()` has been called at
  least once. Unaffected by this plan's OQ3/OQ4 changes.
- **`initialize()`'s `restored_valence` parameter** (Task 7b): populates
  `_last_applied_valence` from a caller-supplied `Valence` at restore
  time, fixing the routine case of the narrowed Open Question 4.

---

## Tasks

- [x] 1. Set up module scaffold
  - Create the PAD_Engine module file/package structure (no other module's
    files are touched).
  - Add imports needed for `Enum`, `dataclass`, `Optional`, `Deque`,
    `Tuple`, `Literal`, and `collections.deque`.
  - _Requirements: (structural only, no acceptance criteria yet)_

- [x] 2. Implement `Valence` enum with exactly four members
  - Define `Valence` with exactly four members, matching design.md's Data
    Types section verbatim: `POSITIVE = "positive"`, `NEGATIVE =
    "negative"`, `NEUTRAL = "neutral"`, `VALENCE_UNCERTAIN =
    "valence_uncertain"`.
  - Write a unit test asserting the enum has exactly these four members
    (no more, no fewer) with these exact values.
  - _Requirements: 3.2, 3.3 (Glossary: EMA_Decay); former Open Question 3
    (enum member exists to make the case representable; the coefficient
    decision itself — reuse `EMA_COEFFICIENT_NEGATIVE` — is resolved in
    Task 14, not here)_

- [x] 3. Implement `PADSnapshot` frozen dataclass
  - Fields: `pleasure: float`, `arousal: float`, `dominance: float`.
  - Frozen/immutable, per design.md's Data Types rationale (no consumer can
    mutate PAD_Engine's live state through a returned snapshot).
  - _Requirements: 7.1_

- [x] 4. Implement `PADDelta` frozen dataclass
  - Fields: `d_pleasure: float`, `d_arousal: float`, `d_dominance: float`,
    `valence: Valence`, `origin: Literal["appraisal", "aha_insight"] =
    "appraisal"`.
  - Frozen/immutable, matching design.md's Data Types section verbatim.
  - Write a unit test asserting the dataclass is frozen (attempting to set
    an attribute after construction raises).
  - _Requirements: 2.2, 4.1, 4.3_

- [x] 5. Implement module constants
  - `PAD_BASELINE = PADSnapshot(pleasure=0.55, arousal=0.45,
    dominance=0.58)`.
  - `EMA_COEFFICIENT_NEGATIVE = 0.6`, `EMA_COEFFICIENT_POSITIVE = 0.75`.
  - `PAD_HISTORY_LENGTH = 50` — placeholder build-time tuning constant, per
    design.md's Constants section and requirements.md's Build-Time Tuning
    Constants / Open Question 1 (Soul_Tick cadence). Do not tune this value
    or tie it to a cadence decision; leave the placeholder default exactly
    as design.md specifies, with the same comment carried forward
    explaining it is not an architectural decision.
  - Do NOT define any coefficient constant for `NEUTRAL` or the residual
    restore-boundary case — design.md's Constants section explicitly
    states defining one would silently resolve an unresolved
    requirement/Open Question by invention. `VALENCE_UNCERTAIN` also gets
    NO new constant, but for a different reason: it is resolved (Task 14)
    by reusing `EMA_COEFFICIENT_NEGATIVE`, not by inventing a third value.
  - Write a unit test asserting these four constants have exactly the
    locked/placeholder values above (simple equality checks per design.md's
    Testing Strategy "Explicitly not property-tested" note — not a
    property test).
  - _Requirements: 3.2, 3.3, 6.1, 8.1, 8.2; Open Question 1 (carried
    forward, not resolved)_

- [x] 6. Implement `PADEngine.__init__` and state fields
  - `_pleasure`, `_arousal`, `_dominance: float` — uninitialized/unset
    until `initialize()` is called (do not default them to baseline inside
    `__init__` — baseline-or-restored assignment is `initialize()`'s job,
    per design.md's Restore/persist boundary section). Use a sentinel
    (e.g. leave the attributes unset, or use an internal
    `_initialized: bool = False` flag) sufficient to support the
    pre-`initialize()` `RuntimeError` behavior implemented in Task 9.
  - `_last_applied_valence: Optional[Valence] = None`.
  - `_history: Deque[PADSnapshot] = deque(maxlen=PAD_HISTORY_LENGTH)`.
  - No bound-clamping logic belongs on these bare field declarations — the
    [0.0, 1.0] clamp (former Open Question 2, now RESOLVED by architect
    decision) is applied only where PAD actually changes value, in Task 10's
    `apply_appraisal_delta`, not here at `__init__` time.
  - _Requirements: 1.1_

- [x] 7. Implement `initialize(restored)` including the baseline-fallback and
      non-baseline-restore cases
  - If `restored` is `None`, or fails basic validity (not three finite
    floats), set current PAD to `PAD_BASELINE`.
  - Otherwise set current PAD to `restored` exactly.
  - Mark the engine as initialized (e.g. set `_initialized = True`), so
    that Task 9's pre-`initialize()` guard on `get_current_pad()`,
    `on_soul_tick()`, and `apply_appraisal_delta()` (three methods) can
    distinguish "never initialized" from "initialized at baseline."
  - Do not append anything to `_history` from this call (history is only
    appended on Soul_Tick, per design.md's PAD_History Semantics).
  - `_last_applied_valence` is set from `restored_valence` (see Task 7b
    below) — see Task 7b for the parameter that supplies it. This is what
    creates the two distinct `None`-valence cases handled in Tasks 13/15
    (NEUTRAL is unaffected by this — Task 13 is a `Valence.NEUTRAL` case,
    not a `None` case).
  - `initialize()` accepts only `Optional[PADSnapshot]` for `restored` —
    it does not accept, import, or reference `state_manager.py`'s
    `PADState` type. Converting a `PADState` (returned by
    `StateManager.load_pad()`) into a `PADSnapshot` is explicitly out of
    scope for `PADEngine` and is not implemented in this task or anywhere
    in this module — per design.md's Restore/persist boundary section,
    that conversion happens at the call site that wires `PADEngine` and
    `StateManager` together (e.g. Daemon's startup sequence), not inside
    either class. Do not add a `from_pad_state()` classmethod or similar
    helper to `PADEngine` or to `PADSnapshot` — doing so would give
    `PADEngine` (or its own data type) knowledge of `StateManager`'s
    type, which design.md explicitly rules out.
  - Write unit tests:
    - `initialize(None)` → current PAD equals `PAD_BASELINE` exactly.
    - `initialize(invalid_snapshot)` (e.g. a component is `NaN` or
      infinite) → current PAD equals `PAD_BASELINE` exactly.
    - `initialize(valid_non_baseline_snapshot)` → current PAD equals that
      snapshot exactly (not baseline).
  - _Requirements: 1.3, 9.1, 9.2, 9.4_

- [x] 7b. Extend `initialize()` with a `restored_valence` parameter (this
      is the fix for the routine case of the NARROWED Open Question 4)
  - Add `restored_valence: Optional[Valence] = None` as a second parameter
    to `initialize()` (from Task 7).
  - Set `_last_applied_valence = restored_valence` inside `initialize()`.
    Since the default is `None`, a caller that does not supply
    `restored_valence` gets exactly the previous behavior
    (`_last_applied_valence` is `None` after `initialize()`).
  - This exists so that, on a normal restart, the call-site wiring layer
    (Task 8, extended below) can load the persisted `last_applied_valence`
    string via `state_manager.py`'s `load_last_applied_valence()`, convert
    it to a `Valence`, and pass it here — so `_last_applied_valence` is no
    longer `None` after `initialize()`, and Task 15's residual
    restore-boundary raise does not fire for that session.
  - Do NOT change `on_soul_tick`'s restore-boundary trigger condition or
    message (Task 15) — this task only changes how
    `_last_applied_valence` gets populated at `initialize()` time; Task
    15's raise, when it does fire (no persisted valence at all), is
    unchanged.
  - Write unit tests:
    - `initialize(some_non_baseline_snapshot, restored_valence=Valence.NEGATIVE)`
      followed by `on_soul_tick()` does NOT raise, and decays using
      `EMA_COEFFICIENT_NEGATIVE` — i.e. behaves exactly as if
      `Valence.NEGATIVE` had been supplied via a same-session
      `apply_appraisal_delta` call instead.
    - `initialize(some_non_baseline_snapshot)` (no `restored_valence`
      argument, so it defaults to `None`) followed by `on_soul_tick()`
      still raises `NotImplementedError` exactly as before (Task 15's
      test) — confirms the default preserves prior behavior.
  - _Requirements: 3.1, 9.4; narrows (does not resolve) Open Question 4_

- [x] 8. Extend the call-site conversion helper (outside `PADEngine`,
      outside `StateManager`) to also convert the persisted valence
      string
  - In the same integration/wiring code location as before (e.g. a Daemon
    startup module, or a dedicated small wiring function/test harness for
    this spec) — **not** inside the `PADEngine` module file and **not**
    inside `daemon/state_manager.py` — the existing conversion function
    (which takes a `PADState`, as returned by `StateManager.load_pad()`,
    and returns a `PADSnapshot`) is extended to also provide a conversion
    from the persisted `last_applied_valence` string (as returned by
    `StateManager.load_last_applied_valence() -> Optional[str]`) to
    `Optional[Valence]`, for passing into `PADEngine.initialize()`'s new
    `restored_valence` parameter (Task 7b). This is an extension of the
    existing helper's responsibility, not a second helper function.
  - Contract: given the raw string (or `None`) `load_last_applied_valence()`
    returns, look up a `Valence` member whose `.value` matches the string.
    If the string is `None`, missing, or does not match any known
    `Valence` value, return `None` — do not guess a member.
  - Do not modify `daemon/state_manager.py` to import or return `Valence`.
    Do not modify `PADEngine`'s module to import or accept the raw
    persisted string type. Both classes remain defined only in terms of
    their own dataclass/enum, per design.md's Restore/persist boundary
    section.
  - Write unit tests:
    - Given a representative `PADState` instance, the conversion function
      returns a `PADSnapshot` with matching `pleasure`/`arousal`/
      `dominance` values (unchanged from before this extension).
    - Given a string matching a known `Valence` member's `.value` (e.g.
      `"negative"`), the extended helper returns that `Valence` member.
    - Given `None`, returns `None`.
    - Given a string that does not match any `Valence` member's `.value`
      (e.g. a corrupted field), returns `None` rather than guessing.
  - _Requirements: 9.2, 9.4 (call-site wiring, not a PADEngine or
    StateManager requirement per se — but necessary for either to be used
    together correctly); narrows (does not resolve) Open Question 4_

- [x] 9. Implement the pre-`initialize()` guard on `get_current_pad()`,
      `on_soul_tick()`, and `apply_appraisal_delta()`
  - All three methods check the `_initialized`/unset-state sentinel from
    Task 6 before doing anything else, and raise `RuntimeError` if
    `initialize()` has never been called on this instance.
  - This guard must run before any other logic in each method (e.g. before
    `on_soul_tick()` reads `_last_applied_valence` or touches `_history`,
    and before `apply_appraisal_delta()` adds its delta components to
    `_pleasure`/`_arousal`/`_dominance` or sets
    `_last_applied_valence`).
  - Write unit tests:
    - A freshly-constructed `PADEngine` (no `initialize()` call) raises
      `RuntimeError` on `get_current_pad()`.
    - A freshly-constructed `PADEngine` (no `initialize()` call) raises
      `RuntimeError` on `on_soul_tick()`.
    - A freshly-constructed `PADEngine` (no `initialize()` call) raises
      `RuntimeError` on `apply_appraisal_delta()`.
    - After `initialize()` is called (with either `None` or a valid
      snapshot), none of the three methods raises `RuntimeError` for this
      reason anymore.
  - _Requirements: (Error Handling section, "Calls before `initialize()`")_

- [x] 10. Implement `apply_appraisal_delta(delta)`
  - Add `delta.d_pleasure`, `delta.d_arousal`, `delta.d_dominance` to the
    current `_pleasure`, `_arousal`, `_dominance` respectively.
  - Store `delta.valence` into `_last_applied_valence`.
  - Do not branch on `delta.origin` — process `"appraisal"` and
    `"aha_insight"` origins identically (Req 4.3); `origin` is
    informational only.
  - Do not append to `_history` from this method (per design.md: history is
    only appended on Soul_Tick).
  - Write unit tests:
    - Applying a delta is a pure addition: post-call PAD equals pre-call
      PAD plus delta components, for at least one positive-magnitude and
      one negative-magnitude delta case.
    - A `PADDelta` with `origin="aha_insight"` and one with
      `origin="appraisal"` but identical numeric components and valence
      produce identical resulting PAD.
    - After the call, `_last_applied_valence` equals `delta.valence`, for
      each of the four `Valence` members in turn.
  - _Requirements: 2.1, 2.2, 4.1, 4.3_

- [x] 11. Implement `on_soul_tick()` for the `POSITIVE` and `NEGATIVE` cases
      only
  - No arguments (matches design.md's no-parameter signature).
  - Read `_last_applied_valence`.
  - If `NEGATIVE`: select coefficient `EMA_COEFFICIENT_NEGATIVE` (0.6).
  - If `POSITIVE`: select coefficient `EMA_COEFFICIENT_POSITIVE` (0.75).
  - Apply the selected coefficient uniformly to P, A, and D using the EMA
    form `new = coefficient * baseline + (1 - coefficient) * current` for
    each dimension independently (same coefficient, three applications).
  - Append the resulting `PADSnapshot` to `_history` after decay is
    applied.
  - `NEUTRAL`, `VALENCE_UNCERTAIN`, and `None` (both sub-cases) are
    deliberately excluded from this task — `NEUTRAL` and the residual
    `None`-non-baseline case are implemented separately in Tasks 13 and
    15 respectively (both still raise); `VALENCE_UNCERTAIN` is
    implemented separately in Task 14 (resolved — decays like `NEGATIVE`,
    does not raise); the `None`-baseline case is Task 16. Do not add a
    branch for any of these cases here, even though `VALENCE_UNCERTAIN`
    now uses the same coefficient value as `NEGATIVE` — they remain
    distinct branches in the implementation (see Task 14).
  - Write unit tests/property tests:
    - For `NEGATIVE` and `POSITIVE` valence and arbitrary starting PAD,
      each of P/A/D after one tick lies strictly between its pre-tick
      value and the corresponding baseline value (or is unchanged if
      already at baseline).
    - The same coefficient is provably applied to all three dimensions for
      a given valence (derivable algebraically from pre/post values and
      baseline).
    - `_history` gains exactly one new entry equal to the post-decay
      `PADSnapshot`.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.2, 6.1_

- [x] 12. Implement the standard EMA decay helper
  - Extract the EMA form `new = coefficient * baseline + (1 - coefficient)
    * current`, applied independently to each of P, A, D, into a small
    internal helper used by Task 11 (`NEGATIVE`/`POSITIVE`) and also by
    Task 14 (`VALENCE_UNCERTAIN`, which reuses the `NEGATIVE` coefficient
    value through this same helper) — not reused by Tasks 13/15, which
    raise before reaching this helper.
  - Write a unit test verifying the helper's output against hand-computed
    values for at least two coefficient/starting-PAD combinations.
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 13. Implement `on_soul_tick()` `NEUTRAL` case: raise
      `NotImplementedError` (NOT an Open Question)
  - If `_last_applied_valence` is `Valence.NEUTRAL`, raise
    `NotImplementedError`.
  - The exception message must reference requirements.md Requirement 3's
    note (neutral-valence handling is unspecified), making clear this is
    deliberately unresolved pending architect decision. The message must
    NOT refer to this as an Open Question — per requirements.md and
    design.md's "Neutral Valence Handling" section, neutral valence is
    explicitly recorded as an in-requirement note, not an Open Question,
    and must not be conflated with the (now-resolved) former Open
    Question 3 (`VALENCE_UNCERTAIN`, Task 14 — no longer raises at all)
    or the narrowed Open Question 4 (restore-boundary, Task 15).
  - Do NOT pick a default coefficient (not 0.6, not 0.75, not "skip") for
    this case.
  - Do NOT append anything to `_history` when raising.
  - Write a unit test: fresh `PADEngine`, `initialize(None)`, then
    `apply_appraisal_delta` with `valence=Valence.NEUTRAL`, then
    `on_soul_tick()` — asserts `NotImplementedError` is raised, that
    `_history` gained no entry from this call, and that the message text
    differs from the message used in Task 15 (Task 14 no longer raises,
    so there is no longer a message to differ from there).
  - _Requirements: 3.1 (note). NOT an Open Question — do not label this
    task's gap as OQ4 anywhere, including in the exception message._

- [x] 14. Implement `on_soul_tick()` `VALENCE_UNCERTAIN` case: decay using
      `EMA_COEFFICIENT_NEGATIVE` (former Open Question 3, now RESOLVED —
      does NOT raise)
  - If `_last_applied_valence` is `Valence.VALENCE_UNCERTAIN`, select
    `EMA_COEFFICIENT_NEGATIVE` (0.6) — the same coefficient value as the
    `NEGATIVE` case (Task 11), not a new constant — and apply it
    uniformly to P, A, D via the Task 12 EMA helper, appending the
    resulting `PADSnapshot` to `_history`, exactly like the `NEGATIVE`
    and `POSITIVE` cases in Task 11.
  - Rationale (for the code comment at this branch): v4's Emergency Type
    Detection establishes "when classification is ambiguous, default to
    the more cautious treatment" (UNCLASSIFIED defaults to Type B, the
    most careful emergency type). `VALENCE_UNCERTAIN` is a real Q2
    appraisal outcome (appraisal ran and returned an ambiguous category,
    not missing data), so this precedent applies directly. Reuses the
    existing `NEGATIVE` coefficient constant rather than inventing a
    third value (Addendum's "reuse before invent" principle). See
    design.md's "Open Question 3 (Resolved)" section for full detail.
  - Do NOT raise `NotImplementedError` for this case anymore — this task
    supersedes the prior version of this task, which raised. Do NOT
    define a new named constant (e.g. `EMA_COEFFICIENT_UNCERTAIN`) — the
    decision is explicitly to reuse `EMA_COEFFICIENT_NEGATIVE`, not
    invent a third value.
  - Keep this as its own branch in `on_soul_tick`, distinct from the
    `NEGATIVE` branch (Task 11), even though both select the same
    coefficient value — do not merge `VALENCE_UNCERTAIN` into the
    `NEGATIVE` condition (e.g. via an `or`), so that a future re-opening
    of this decision does not require re-deriving where
    `VALENCE_UNCERTAIN` is handled.
  - Write unit tests:
    - For two `PADEngine` instances started from the same restored (or
      baseline) PAD, one given a `NEGATIVE`-valence delta and the other a
      `VALENCE_UNCERTAIN`-valence delta of identical magnitude,
      `on_soul_tick()` produces identical resulting PAD on both.
    - `_history` gains exactly one new entry equal to the post-decay
      `PADSnapshot`, for the `VALENCE_UNCERTAIN` case (mirrors Task 11's
      history-append test, applied to this case).
    - No `NotImplementedError` is raised for this case.
  - _Requirements: 3.1; former Open Question 3 — now RESOLVED, reusing
    `EMA_COEFFICIENT_NEGATIVE`. This task alone resolves it._

- [x] 15. Implement `on_soul_tick()` residual restore-boundary case: raise
      `NotImplementedError` (narrowed Open Question 4 — UNCHANGED
      trigger condition and message)
  - If `_last_applied_valence` is `None` AND current PAD is NOT equal to
    `PAD_BASELINE` (i.e. a non-baseline value was restored via
    `initialize()`, and neither a same-session `PADDelta` nor a
    `restored_valence` argument to `initialize()` — Task 7b — has
    supplied a valence), raise `NotImplementedError`. This trigger
    condition is UNCHANGED from before Task 7b existed — Task 7b makes
    this condition rarer to encounter (only when no persisted valence
    exists at all), it does not change when the condition itself fires.
  - The exception message must reference requirements.md's narrowed Open
    Question 4 and design.md's "Open Question 4 (Narrowed)" section
    (residual restore-boundary valence-loss gap), making clear this is a
    deliberately unresolved case pending architect decision — not a
    bug — and must be distinguishable from the Task 13 (`NEUTRAL`)
    message. (Task 14 no longer raises, so there is no message from Task
    14 to distinguish from anymore.) The message text itself does not
    need to change from before Task 7b existed, since the trigger
    condition and its meaning as "no valence available" are unchanged —
    only the message's framing of how rare this now is may be updated,
    at implementer discretion, without changing the underlying assertion
    that it is unresolved.
  - Do NOT pick a default coefficient (not 0.6, not 0.75, not "skip") for
    this case. Do NOT reuse the Task 16 skip logic here — this is a
    distinct case (non-baseline PAD) from Task 16 (baseline PAD), even
    though both share `_last_applied_valence is None`.
  - Do NOT append anything to `_history` when raising (the tick did not
    complete).
  - Write unit tests:
    - fresh `PADEngine`, `initialize(some_non_baseline_valid_snapshot)`
      (no `restored_valence` argument, so it defaults to `None`), then
      `on_soul_tick()` with no prior `apply_appraisal_delta` call —
      asserts `NotImplementedError` is raised, that the message differs
      from Task 13's, and that current PAD is unchanged (still exactly
      the restored value) and `_history` gained no entry. (This is the
      same test that existed before Task 7b — it must still pass
      unmodified, since Task 7b does not change this trigger condition.)
  - _Requirements: 3.1, 9.4; narrowed Open Question 4 (explicitly not
    resolved — raises rather than guesses; now rare rather than routine,
    per Task 7b). This task alone covers the residual OQ4 case — Task 13
    does not, and Task 14 no longer raises at all._

- [x] 16. Implement `on_soul_tick()` `None`-at-baseline case: no-op skip
  - If `_last_applied_valence` is `None` AND current PAD equals
    `PAD_BASELINE` exactly, skip decay for this tick (no-op): do not change
    P/A/D, but still append the (unchanged, baseline) `PADSnapshot` to
    `_history`, consistent with Req 6.1's "PAD coordinates recorded at each
    ... Soul_Tick" (the tick still occurred; its recorded value is simply
    unchanged baseline).
  - This case must be reached only when both conditions hold. Do not use
    "`_last_applied_valence` is `None`" alone as the skip condition — see
    Task 15 for the non-baseline case, which must NOT be skipped and must
    raise instead.
  - This is not an Open Question — decaying baseline toward baseline is a
    no-op by construction regardless of which (unresolved) coefficient
    would have been chosen, so skipping resolves nothing by invention.
  - Write a unit test: fresh `PADEngine`, `initialize(None)` (baseline, no
    restore), then `on_soul_tick()` with no prior `apply_appraisal_delta`
    call — PAD remains exactly `PAD_BASELINE` after the call, no exception
    is raised, and exactly one entry is appended to `_history`.
  - _Requirements: 3.1 (decay against baseline is a no-op by construction;
    skipping resolves nothing by invention)_

- [x] 17. Implement `get_current_pad()`
  - Returns a `PADSnapshot` of the current `_pleasure`, `_arousal`,
    `_dominance` values. Single method, no caller-identity parameter (per
    design.md: all five consumers call the same accessor). Subject to the
    Task 9 pre-`initialize()` guard.
  - Write a unit test: returned snapshot matches current internal PAD
    values exactly, immediately after both `initialize()` and after a
    decay/delta call.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 18. Implement `get_pad_history()`
  - Returns an immutable `Tuple[PADSnapshot, ...]` copy of `_history`, in
    chronological order (oldest first).
  - Write unit tests:
    - After N `on_soul_tick()` calls that complete (N < `PAD_HISTORY_
      LENGTH`), `len(get_pad_history()) == N`, in chronological order.
    - After N `on_soul_tick()` calls that complete (N > `PAD_HISTORY_
      LENGTH`), `len(get_pad_history()) == PAD_HISTORY_LENGTH`, holding
      exactly the most recent ticks in chronological order (oldest evicted
      first).
    - The returned tuple cannot be used to mutate `PADEngine`'s internal
      `_history` (e.g. mutating the returned tuple/its elements, where the
      language allows attempting it, does not affect subsequent calls to
      `get_pad_history()`).
  - _Requirements: 6.1, 6.2_

- [x] 19. Verify no direct-assignment surface exists, and structural
      rejection of out-of-contract inputs (API-surface tests)
  - Write a static/API-surface test asserting `PADEngine`'s public method
    list is exactly: `initialize`, `apply_appraisal_delta`, `on_soul_tick`,
    `get_current_pad`, `get_pad_history` (plus dunder/private methods as
    needed) — i.e. no `set_pleasure`/`set_arousal`/`set_dominance` or
    similar setter exists.
  - Write a test/assertion confirming there is no method on `PADEngine`
    whose signature accepts a Needs-System-pressure value, an F4 signal, or
    a barge-in signal as an argument.
  - No runtime rejection check is added for either of these — per
    design.md's Rejection path section, the enforcement is the absence of
    the call path/surface itself, not a detection branch.
  - _Requirements: 7.1, 7.3, 7.4_

- [x] 20. Integration test: `StateManager` round-trip boundary, using the
      Task 8 call-site conversion helper (extended by Task 7b/8 to also
      cover `last_applied_valence`)
  - Using the existing, unmodified `daemon/state_manager.py` and the Task 8
    conversion helper (not any conversion logic inside `PADEngine` or
    `StateManager`), write an integration test verifying:
    `PADEngine.get_current_pad()` values, passed to
    `StateManager.save_pad()`, and then re-loaded via
    `StateManager.load_pad()` (returning a `PADState`), converted via the
    Task 8 helper into a `PADSnapshot`, and passed into a new
    `PADEngine.initialize()` call, produce a `PADEngine` whose
    `get_current_pad()` equals the original values exactly. 1–3
    representative examples (not a property test), since this exercises
    wiring to an already-tested external module.
  - Optionally (not required to re-derive Task 7b/8's own tests, but may
    be combined with the above for a fuller round-trip): also round-trip
    `last_applied_valence` through `StateManager.save_last_applied_
    valence()` / `load_last_applied_valence()` and the extended helper,
    into `initialize()`'s `restored_valence` parameter, confirming
    `_last_applied_valence` matches the original `Valence` after the
    round-trip.
  - Do not modify `daemon/state_manager.py`.
  - _Requirements: 9.2_

- [x] 21. Wire together and run full test suite; confirm remaining Open
      Questions stay unresolved in code, and resolved/narrowed ones are
      accurately reflected
  - Ensure all tests from Tasks 3–20 pass together (no shared-state leakage
    between tests; each test constructs its own `PADEngine` instance).
  - Confirm, by inspection and by the tests already written, that:
    - **Open Question 1** (Soul_Tick cadence) is carried forward: only a
      placeholder constant exists (`PAD_HISTORY_LENGTH`'s comment pattern);
      no cadence value is hardcoded as a resolution.
    - **Open Question 2** (PAD numeric bounds) is confirmed RESOLVED by
      architect decision, not carried forward: `apply_appraisal_delta`
      (Task 10) clamps each dimension to [0.0, 1.0] after adding the delta,
      covered by `test_apply_appraisal_delta_clamps_to_bounds`. A NEW,
      residual open question is flagged: `initialize()` (Task 7) does not
      clamp an out-of-range restored snapshot.
    - **Open Question 3** (`VALENCE_UNCERTAIN` decay coefficient) is
      confirmed RESOLVED, not merely carried forward: **Task 14** decays
      using `EMA_COEFFICIENT_NEGATIVE` and does NOT raise
      `NotImplementedError` for this case anymore. No new coefficient
      constant was invented for it.
    - **Open Question 4** (restore-boundary decay coefficient) is
      confirmed NARROWED, not resolved and not silently closed: **Task
      15** still raises `NotImplementedError` for the residual case (no
      persisted valence available at all), unchanged from before Task
      7b/8 — but **Task 7b** (`initialize()`'s `restored_valence`
      parameter) and the **Task 8** extended helper mean this raise no
      longer fires on a routine restart where a valence was persisted.
    - The `NEUTRAL` case (**Task 13**) is confirmed distinct from the
      residual restore-boundary case (**Task 15**) — both still raise
      `NotImplementedError`, but for different, distinguishable reasons
      and with different messages. `VALENCE_UNCERTAIN` (**Task 14**) is
      no longer part of this raising-cases comparison at all, since it no
      longer raises.
    - The `PADState` → `PADSnapshot` conversion, and the (new) persisted
      string → `Valence` conversion, both live outside both `PADEngine`
      and `StateManager` (Task 8, extended), per design.md's
      Restore/persist boundary section — neither module's source imports
      the other's type; `state_manager.py` does not import `Valence`.
    - `get_current_pad()`, `on_soul_tick()`, and `apply_appraisal_delta()`
      raise `RuntimeError` when called before `initialize()` (Task 9),
      confirmed by its own tests, unaffected by Tasks 7b/8/14's changes.
  - _Requirements: all; Open Question 1 (carried forward, not resolved);
    Open Question 2 (RESOLVED via Task 10's clamp, architect decision);
    Open Question 3 (RESOLVED via Task 14 specifically); Open Question 4
    (NARROWED via Tasks 7b/8, residual raise unchanged via Task 15); NEUTRAL
    via Task 13, which is explicitly not either Open Question_

