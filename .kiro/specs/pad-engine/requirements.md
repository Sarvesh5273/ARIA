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
