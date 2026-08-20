# ARIA locked spec — needs-system

Consolidated from .kiro/specs/needs-system/{requirements,design,tasks}.md for upload.
Precedence: ARIA_Resolution_Log.md > ARIA_Soul_Spec_v4_Addendum.md > ARIA_Soul_Spec_v4.md.


---

## needs-system — requirements.md

# Requirements Document — Module 2: Needs System

## Introduction

This document transcribes and formalizes, in EARS format, the Module 2 (Needs System)
entry from `ARIA_Module_Build_Plan.md`. That entry is the locked, approved scope for
this module. No requirement here introduces a mechanism, threshold, or behavior that
is not already stated in the Module 2 entry or in the supporting architecture
documents (`ARIA_Soul_Spec_v4.md`, `ARIA_Soul_Spec_v4_Addendum.md`,
`ARIA_Resolution_Log.md`). Where the Module 2 entry references a value or mechanism
defined elsewhere (the recency windows, the Energy EMA math, the four needs' evidence
types), the supporting document is cited as the source of that value, not as a new
source of scope.

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`.
`ARIA_GLM_Covering_Instruction.md` is covering context only.

**The four Module 2 flags and their disposition (from the Module 2 entry):**

| Flag | Subject | Disposition |
|------|---------|-------------|
| **F-2a** | Energy decay rate (k_load) | **Mechanism RESOLVED** by Resolution Log item 6 (single-rate EMA decay during active load, one constant `k_load`). The *value* of `k_load` is an open build-time tuning constant (Resolution Log "Open — build-time tuning constants only"). Carried as a clearly-marked `TODO(build-time)` placeholder. |
| **F-2b** | Energy refill mechanism (k_rest) | **Mechanism RESOLVED** by Resolution Log item 6 (drift-to-baseline recovery during idle, one constant `k_rest` — *not* discrete increments). The *value* of `k_rest` is an open build-time tuning constant. Carried as a `TODO(build-time)` placeholder. |
| **F-2c** | Need→window mapping | **RESOLVED** by Resolution Log item 7: Connection→72h, Growth→14d, Purpose→14d, Continuity→60d — reusing the three precision-decay windows. No new window. |
| **F-2d** | One module or two | **RESOLVED** by Resolution Log item 11: SINGLE module, internally two separated components (energy tracker + needs evaluator). |

The one item this document genuinely cannot close by transcription — the categorical
basis distinguishing **due** from **neglected** — is recorded in **Open Questions**
(OQ-1) and is *not* resolved by inventing a numeric cutoff (steering "percentage
test"; the CRITICAL-CARE constraint on this module). The requirements below implement
the most defensible categorical reading and flag the rest.

## Glossary

- **Needs_System**: The module specified here (Module 2). A single module
  (Resolution Log item 11) with two internal, separated components — the
  **Energy_Tracker** and the **Needs_Evaluator**.
- **Energy_Tracker**: The Needs_System component that owns Energy. A resource /
  battery model.
- **Needs_Evaluator**: The Needs_System component that derives the four categorical
  need states from Memory_Graph evidence.
- **Energy**: A single continuous value on a 0–100 scale representing Aria's
  cognitive / processing headroom (v4 Layer 2). SANCTIONED SUBSTRATE — the only
  numeric value this module owns (steering "No invented numbers": "Continuous numeric
  values exist in exactly two places: PAD and Energy"). Modeled like PAD, not like a
  need (Addendum §3). The 0–100 scale is the scale the in-spec thresholds already live
  on (<30, <20 — v4 Layer 2) and the scale the `NeedStates` contract already defaults
  to (`energy = 100.0` — `daemon/soul_filter.py`).
- **Energy_Baseline**: The "full battery" resting value of Energy, 100.0 — the
  drift-to-baseline target during idle recovery. Matches the `NeedStates` contract
  default.
- **Energy_Min**: The "empty battery" value of Energy, 0.0 — the decay target during
  active load. The natural lower bound of the 0–100 battery scale.
- **EMA**: Exponential moving average — the standard blend `new = k * target +
  (1 - k) * current`. The same EMA-style math already locked for PAD (Addendum §3;
  Resolution Log item 6), applied here per-tick (discrete, no wall-clock dt), exactly
  as PAD_Engine applies it per Soul_Tick.
- **k_load**: The EMA coefficient applied during active load (decay toward Energy_Min).
  Build-time tuning constant, value unspecified (F-2a; Resolution Log). One of exactly
  two Energy constants (Resolution Log item 6: "Two constants, not four").
- **k_rest**: The EMA coefficient applied during idle recovery (drift toward
  Energy_Baseline). Build-time tuning constant, value unspecified (F-2b).
- **Energy_Low_Threshold**: 30. The in-spec operational threshold below which
  reasoning degrades (v4 Layer 2 "Cognitive Load Affecting Reasoning": "When Energy
  drops below 30"). Reused from `daemon/soul_filter.py` (`ENERGY_LOW = 30.0`) — single
  source of truth, not a second definition.
- **Energy_Critical_Threshold**: 20. The in-spec operational threshold for the DMN
  shallow-pass gate (Module Build Plan note: "Shallow DMN pass (Energy < 20)"; v4
  Layer 2 "Energy critically low (below 20)"). Reused from `daemon/soul_filter.py`
  (`ENERGY_CRITICAL = 20.0`).
- **Soul_Tick**: The periodic signal from the Daemon (Module 8) that, in this module,
  drives Energy decay under active load. Cadence is a build-time tuning constant
  (Resolution Log). Module 2 is the *callee*: it EXPOSES `on_soul_tick()`; the Daemon
  calls it (mirrors PAD_Engine, Module 1).
- **Idle_Recovery**: The Daemon's "Energy refill signal — from Daemon (idle)" (Module 2
  entry Inputs). Drives drift-to-baseline recovery (Resolution Log item 6). Module 2
  EXPOSES `on_idle_recovery()`; the Daemon calls it during extended idle.
- **NeedState**: The categorical state of one need — one of `satisfied` / `due` /
  `neglected` (Addendum §3). NOT a number. Defined by the `NeedStates` contract in
  `daemon/soul_filter.py`.
- **NeedStates**: The output contract Module 2 produces and Soul_Filter (Module 5)
  consumes. Four `NeedState` fields (connection, growth, purpose, continuity) plus a
  single continuous `energy: float`. Declared in `daemon/soul_filter.py` while Module 2
  was unbuilt; Module 2 PRODUCES that exact shape so Soul_Filter consumes it unchanged.
- **The four needs**: Connection, Growth, Purpose, Continuity — categorical
  psychological needs (Addendum §3). Distinct in kind from Energy (a resource).
- **Qualifying evidence**: The graph fact whose presence within a need's recency
  window makes that need `satisfied` (Addendum §3 evidence table). Queried through
  Memory_Graph, never re-derived here.
- **Recency window**: The lookback window governing a need (F-2c / Resolution Log
  item 7): Connection 72h, Growth 14d, Purpose 14d, Continuity 60d.
- **Memory_Graph**: Module 3 (`daemon/graph_manager.py`, already built). Exposes
  `connection_evidence`, `growth_evidence`, `purpose_evidence`, `continuity_evidence`
  (each returns a `bool`) — the ONLY source of need evidence. Module 2 calls these;
  it does not reimplement them (Memory_Graph Req 11.5: these queries are "structural
  only; NEVER compute a need state").
- **Daemon**: Module 8 (NOT built). Source of Soul_Tick and Idle_Recovery. Depended on
  by its documented contract (the method calls it will make into Module 2); a fake
  drives them in tests.
- **PAD_Engine**: Module 1 (`daemon/pad_engine.py`). The sole owner/mutator of PAD.
  Module 2 has NO reference to it and never calls its mutator — needs and Energy never
  write PAD (Addendum §3; steering PAD-purity / protected chain).

## Requirements

### Requirement 1: Single Module, Two Internal Components

**User Story:** As the Aria system architect, I want Energy and the four needs in one
module but as two separated components, so that the distinct-mechanisms distinction is
preserved without a module split (Resolution Log item 11 / F-2d).

#### Acceptance Criteria

1. THE Needs_System SHALL be a single module (Resolution Log item 11).
2. THE Needs_System SHALL implement Energy and the four categorical needs as two
   internally separated components: an Energy_Tracker and a Needs_Evaluator.
3. THE Energy_Tracker SHALL NOT depend on the Needs_Evaluator, and THE Needs_Evaluator
   SHALL NOT depend on the Energy_Tracker (the two mechanisms are independent; their
   only shared surface is the module's combined `NeedStates` output).

### Requirement 2: Maintain Energy as a Continuous Substrate Resource

**User Story:** As the Aria system, I want a single owner of the live Energy value, so
that cognitive-load headroom is represented consistently (v4 Layer 2; Addendum §3).

#### Acceptance Criteria

1. THE Energy_Tracker SHALL maintain Energy as one continuous value on a 0–100 scale.
2. WHEN the Energy_Tracker initializes with no prior persisted Energy available, THE
   Energy_Tracker SHALL set Energy to Energy_Baseline (100.0), matching the
   `NeedStates` contract default.
3. WHEN the Energy_Tracker initializes with a valid restored Energy value, THE
   Energy_Tracker SHALL set Energy to that restored value (State_Manager, Module 11,
   is the serialization boundary — Energy is listed among the values it persists).
4. THE Energy_Tracker SHALL treat Energy as substrate (a depletion resource), NOT as a
   feeling or an appraised meaning (Resolution Log item 6: the no-invented-formula rule
   "protects appraised meaning ... not a depletion resource").

### Requirement 3: Energy Decays via EMA Under Active Load (k_load)

**User Story:** As the Aria system architect, I want Energy to deplete under sustained
load using single-rate EMA decay, so that cognitive headroom falls the way a battery
drains (Resolution Log item 6 / F-2a).

#### Acceptance Criteria

1. WHEN the Daemon issues a Soul_Tick under active load, THE Energy_Tracker SHALL apply
   one EMA step toward Energy_Min (0.0) using the single coefficient k_load.
2. THE Energy_Tracker SHALL use exactly one coefficient (k_load) for active-load decay
   — no positive/negative asymmetry, because Energy has no valence (Resolution Log
   item 6: "Two constants, not four").
3. THE Energy_Tracker SHALL treat the value of k_load as a build-time tuning constant
   (F-2a), carried as a clearly-marked placeholder, NOT resolved by this module.
4. WHILE Energy is above Energy_Min, repeated active-load Soul_Ticks SHALL move Energy
   monotonically toward Energy_Min without overshooting below it.

### Requirement 4: Energy Recovers via Drift-to-Baseline During Idle (k_rest)

**User Story:** As the Aria system architect, I want Energy to recover during idle by
drifting toward baseline (not by discrete refills), so recovery matches the locked
battery model (Resolution Log item 6 / F-2b).

#### Acceptance Criteria

1. WHEN the Daemon issues an Idle_Recovery signal, THE Energy_Tracker SHALL apply one
   EMA step toward Energy_Baseline (100.0) using the single coefficient k_rest.
2. THE Energy_Tracker SHALL implement recovery as drift-to-baseline (Resolution Log
   item 6), NOT as a discrete increment (the discrete-vs-drift ambiguity in F-2b is
   resolved to drift by Resolution Log item 6).
3. THE Energy_Tracker SHALL treat the value of k_rest as a build-time tuning constant
   (F-2b), carried as a clearly-marked placeholder, NOT resolved by this module.
4. WHILE Energy is below Energy_Baseline, repeated Idle_Recovery signals SHALL move
   Energy monotonically toward Energy_Baseline without overshooting above it.

### Requirement 5: Expose Energy as Context to Consumers

**User Story:** As Soul_Filter, Appraisal_Chain, and DMN, I want to read Energy and its
in-spec operational bands, so that I can apply the cognitive-load, constraint, and
shallow-pass gates the architecture already defines (Module 2 entry Outputs).

#### Acceptance Criteria

1. THE Energy_Tracker SHALL expose the current Energy value to consumers.
2. THE Energy_Tracker SHALL expose a categorical Energy band derived from the in-spec
   thresholds only: NORMAL (Energy ≥ 30), LOW (20 ≤ Energy < 30), CRITICAL (Energy < 20),
   reusing Energy_Low_Threshold and Energy_Critical_Threshold from `soul_filter.py`.
3. THE Needs_System SHALL surface Energy for: Appraisal_Chain Stage 2 (<30
   cognitive-load modifier), Soul_Filter Constraints (<30 / <20), and DMN (<20
   shallow-pass gate) — as context those consumers read, not as an action this module
   takes on them.
4. THE Needs_System SHALL carry the raw Energy value into the `NeedStates.energy`
   field so Soul_Filter can apply its own `< ENERGY_LOW` gate unchanged.

### Requirement 6: Energy Never Writes PAD

**User Story:** As the Aria system architect, I want it structurally impossible for
Energy to change PAD, so that the protected chain holds (steering PAD-purity;
Addendum §5's F4 precedent; Resolution Log item 6 keeps Energy as substrate, not
feeling).

#### Acceptance Criteria

1. THE Needs_System SHALL NOT hold a reference to PAD_Engine and SHALL NOT call any
   PAD mutator (`apply_appraisal_delta` or any PAD-writing method).
2. THE Energy_Tracker SHALL NOT compute, return, or emit any PAD value or PAD delta.
3. THE Needs_System SHALL expose Energy ONLY as a read value / categorical band for
   other modules to consume — never as an input to a PAD computation performed here.

### Requirement 7: The Four Needs Are Strictly Categorical

**User Story:** As the Aria system architect, I want the four needs represented as
categories, not numbers, so that they pass the percentage test (Addendum §3; steering
"percentage test" and "No invented numbers").

#### Acceptance Criteria

1. THE Needs_Evaluator SHALL represent each of Connection, Growth, Purpose, and
   Continuity as a `NeedState` (satisfied / due / neglected) — a category, never a
   number.
2. THE Needs_System SHALL expose NO numeric score, percentage, 0–100 value, "pressure"
   value, or "level" for any of the four needs, on any interface, at any time.
3. THE only numeric value the Needs_System SHALL expose is Energy (Requirement 5) —
   the sanctioned substrate.
4. IF a choice about a need can be phrased as "what percentage of the way there is
   this?", THEN THE Needs_System SHALL NOT implement it as a number (steering
   percentage test).

### Requirement 8: Need States Set by Qualifying Graph Evidence

**User Story:** As the Needs_Evaluator, I want each need's state determined by whether
qualifying evidence exists in the graph within its window, so that need satisfaction
reflects what actually happened, measured through the graph (Addendum §3).

#### Acceptance Criteria

1. THE Needs_Evaluator SHALL determine each need's state by calling the corresponding
   Memory_Graph evidence query (`connection_evidence`, `growth_evidence`,
   `purpose_evidence`, `continuity_evidence`).
2. THE Needs_Evaluator SHALL NOT reimplement, duplicate, or bypass those queries — it
   calls the real Memory_Graph methods (Memory_Graph owns "whether evidence exists";
   Needs_System owns "what that means for the need state").
3. WHEN a need's evidence query returns True (qualifying evidence exists within the
   window), THE Needs_Evaluator SHALL set that need to `satisfied`.
4. WHEN a need's evidence query returns False (no qualifying evidence within the
   window), THE Needs_Evaluator SHALL set that need to a non-satisfied state per
   Requirement 12.

### Requirement 9: Need → Recency-Window Mapping (F-2c, RESOLVED)

**User Story:** As the Needs_Evaluator, I want each need governed by its locked recency
window, so that evidence ages out on the correct schedule (Resolution Log item 7).

#### Acceptance Criteria

1. THE Needs_Evaluator SHALL govern Connection by a 72h window, Growth by 14d, Purpose
   by 14d, and Continuity by 60d (Resolution Log item 7).
2. THE Needs_Evaluator SHALL reuse the window each Memory_Graph evidence query already
   applies by default (Memory_Graph defines `WINDOW_CONNECTION`/`WINDOW_GROWTH`/
   `WINDOW_PURPOSE`/`WINDOW_CONTINUITY` as exactly these values) rather than
   introducing its own window constants.

### Requirement 10: Need → Evidence-Type Mapping

**User Story:** As the Needs_Evaluator, I want each need bound to its research-grounded
evidence type, so that satisfaction means the right thing (Addendum §3 evidence table).

#### Acceptance Criteria

1. THE Needs_Evaluator SHALL treat Connection as satisfied by Relatedness evidence — an
   interaction the appraisal chain already scored Q1 medium-or-above (as
   `connection_evidence` queries).
2. THE Needs_Evaluator SHALL treat Growth as satisfied by Competence evidence — an
   UncertaintyNode actually resolved (confirmed/inferred, not abandoned) through
   engagement (as `growth_evidence` queries).
3. THE Needs_Evaluator SHALL treat Purpose as satisfied by Beneficence evidence — user
   follow-through / explicit positive feedback (as `purpose_evidence` queries), and
   SHALL record that Addendum §3 flags Purpose as the weakest, lowest-confidence signal
   (see OQ-3).
4. THE Needs_Evaluator SHALL treat Continuity as satisfied by narrative-coherence
   evidence — the self-continuity narrative extended within window (as
   `continuity_evidence` queries against the self-referential EntityNode).

### Requirement 11: States Revert on Their Own as Evidence Ages Out

**User Story:** As the Aria system architect, I want need states to revert purely
because evidence ages out of the window, with nothing actively subtracting, so the
mechanic matches the diary/experience-sampling grounding (Addendum §3).

#### Acceptance Criteria

1. WHEN the qualifying evidence for a need falls outside that need's recency window as
   time advances, THE Needs_Evaluator SHALL report that need as non-satisfied on the
   next evaluation — without any active decrement, subtraction, or countdown.
2. THE Needs_Evaluator SHALL be stateless with respect to need states: each evaluation
   is a fresh function of (current time, graph contents), so the transition
   satisfied→non-satisfied is driven ENTIRELY by the passage of time relative to the
   window, never by mutating a stored need value.
3. THE Needs_Evaluator SHALL accept an injected current-time (`now`) so that the
   time-driven revert is exercisable with a controlled clock, and SHALL pass that time
   through to the Memory_Graph evidence queries.

### Requirement 12: Due-vs-Neglected Categorical Basis (CRITICAL CARE)

**User Story:** As the Aria system architect, I want the due/neglected distinction to be
a real category, not a disguised percentage of window elapsed, so this module never
smuggles a number into a need (steering percentage test; the module's CRITICAL-CARE
constraint).

#### Acceptance Criteria

1. THE Needs_Evaluator SHALL define `satisfied` categorically as "qualifying evidence
   exists within the window" (the binary fact the Memory_Graph queries return) — a real
   category that passes the percentage test.
2. WHEN a need is non-satisfied (no qualifying evidence in window), THE Needs_Evaluator
   SHALL report it as `due` — the direct categorical complement of satisfied ("evidence
   has aged out; the need is now due for fresh evidence"), requiring no additional
   signal.
3. THE Needs_Evaluator SHALL NOT compute `due` or `neglected` from any measure of "how
   much of the window has elapsed", "time since last evidence", or any other numeric
   fraction of the window — in particular it SHALL NOT implement "due = >50% of window
   elapsed" or any variant.
4. THE Needs_Evaluator SHALL NOT emit `neglected` on the basis of a numeric cutoff. The
   `neglected` category is preserved in the `NeedStates` contract but is NOT produced by
   this evaluator, because no source document provides a percentage-free categorical
   basis reachable through the sanctioned evidence queries to distinguish it from `due`
   (see OQ-1). This is flagged, not invented.

### Requirement 13: Needs Never Pull PAD

**User Story:** As the Aria system architect, I want the needs to influence only what
surfaces in retrieval and what context Soul_Filter/Daemon see — never PAD — so the
protected chain holds (Addendum §3 "Stage 5 redefined"; steering protected chain).

#### Acceptance Criteria

1. THE Needs_System SHALL output the four categorical need states as: a Stage-1
   retrieval PREFERENCE for Appraisal_Chain, and context for Soul_Filter (This Moment /
   Constraints) and Daemon (initiative) — per the Module 2 entry Outputs.
2. THE Needs_System SHALL NOT provide any path by which a need state computes, adds to,
   or triggers a PAD change (Addendum §3: the needs act "never as a pull on PAD").
3. THE Needs_System SHALL express need influence only as categorical states handed to
   consumers, leaving the meaning-making (and any eventual PAD effect, via appraisal) to
   those consumers — Module 2 performs no appraisal and writes no PAD.

### Requirement 14: Produce the NeedStates Contract Shape Unchanged

**User Story:** As Soul_Filter (Module 5, already built), I want Module 2 to hand me the
exact `NeedStates` shape I already consume, so that I need no modification (Module 2 →
`NeedStates` contract, `daemon/soul_filter.py`).

#### Acceptance Criteria

1. THE Needs_System SHALL produce a `NeedStates` value carrying the four `NeedState`
   fields (connection, growth, purpose, continuity) and the continuous `energy` float.
2. THE Needs_System SHALL produce the exact `NeedStates` / `NeedState` types Soul_Filter
   already imports (from `daemon/soul_filter.py`), so Soul_Filter consumes the output
   unchanged.
3. THE Needs_System SHALL NOT require any modification to `daemon/soul_filter.py` or
   `daemon/graph_manager.py`; IF the contract were found to need a change, THE change
   SHALL be flagged for the architect, not made here.

### Requirement 15: Inputs and Outputs Boundary

**User Story:** As the Aria system, I want Module 2 to accept exactly the inputs and
emit exactly the outputs the Build Plan defines, so its behavior is fully determined by
Memory_Graph and Daemon.

#### Acceptance Criteria

1. THE Needs_System SHALL accept qualifying-evidence query RESULTS from Memory_Graph
   (by calling Memory_Graph's evidence queries).
2. THE Needs_System SHALL accept a Soul_Tick signal (Energy decay) and an Idle_Recovery
   signal (Energy refill) from the Daemon, by exposing `on_soul_tick()` and
   `on_idle_recovery()` for the Daemon to call.
3. THE Needs_System SHALL output Energy (continuous) and the four categorical need
   states, combined in the `NeedStates` contract.
4. THE Needs_System SHALL depend on Memory_Graph via its real interface (injected), and
   on the Daemon via the documented contract (the method calls it makes) — a fake Daemon
   / injected clock drives them in tests.

## Open Questions

Per Rule 1 (do not invent) and Rule 2 (do not resolve conflicts silently), the following
are flagged rather than resolved by invention.

1. **OQ-1 — Categorical basis for `due` vs `neglected` (PRIMARY FLAG).** Addendum §3
   states the four needs are `satisfied / due / neglected` and that state is "determined
   by whether qualifying evidence exists in the graph within a recency window." That
   determination is BINARY (evidence in-window → satisfied; else not) — exactly what the
   Memory_Graph evidence queries return (a `bool`). The Addendum provides a
   percentage-free categorical basis for `satisfied` but does **not** provide a general
   percentage-free basis to split the non-satisfied state into `due` vs `neglected` for
   Connection, Growth, or Purpose. The **only** place the docs gesture at a distinct
   categorical `neglected` fact is Continuity: "neglected when updates have gapped for a
   long stretch, **or new evidence contradicts rather than extends** it." Of those, "a
   long stretch" is a duration (fails the percentage test), and "contradicts rather than
   extends" is a distinct categorical fact — but it is **not reachable** through the
   existing `continuity_evidence` query (which returns only a bool for "narrative
   extended within 60d"), and wiring a contradiction signal would require a Memory_Graph
   contract addition (which Requirement 14.3 forbids making unilaterally). **Decision
   (most defensible categorical reading):** collapse to `satisfied` vs non-satisfied,
   and label non-satisfied as `due` (Requirement 12). Do NOT invent a numeric cutoff for
   `neglected`. `neglected` stays in the contract enum but is not emitted. **Deferred to
   the architect:** whether to (a) leave the two-state reading, (b) add a Memory_Graph
   query exposing a categorical `neglected` fact (e.g. Continuity contradiction; Growth
   "an UncertaintyNode ABANDONED in-window with none resolved"), or (c) something else.
   This does not cost downstream behavior: the one documented consumer of the categorical
   states (Stage-1 retrieval preference, Addendum §3) fires for `due` OR `neglected`
   identically, and Soul_Filter reads only `NeedStates.energy`.
2. **OQ-2 — Self-entity id for Continuity.** `continuity_evidence(self_entity_id, ...)`
   requires the id of the self-referential EntityNode (Resolution Log item 2). Which
   module owns/provides that id at wiring time is not pinned by any document. Module 2
   accepts it as an injected value (constructor / call param). If the self node does not
   yet exist, Continuity is reported non-satisfied (`due`) — there is no narrative
   extension to find. Flagged for the architect to confirm the provisioning path.
3. **OQ-3 — Purpose evidence is the weakest signal.** Addendum §3 explicitly flags
   Purpose (Beneficence) as "the weakest, lowest-confidence signal of the four —
   outcome visibility is often genuinely limited in-session." Additionally,
   Memory_Graph's `purpose_evidence` carries its own `TODO(OQ6-M2)`: its current query
   (a positive-valence EventNode in-window) is a stand-in "to be superseded by whatever
   query Module 2 specifies." Module 2 does **not** specify a richer follow-through query
   here (that would be inventing a mechanism); it calls `purpose_evidence` as-is and
   records that both the signal's weakness and the query's exact structural definition
   remain architect items.
4. **OQ-4 — Contract location.** The `NeedStates` / `NeedState` contract currently lives
   in `daemon/soul_filter.py` (declared there as a placeholder while Module 2 was
   unbuilt). Module 2 imports and produces that exact class so Soul_Filter consumes it
   unchanged (Requirement 14). Ideally the canonical contract would relocate to Module 2
   with Soul_Filter importing it; this is deferred because `soul_filter.py` must not be
   modified in this task. Flagged, not acted on.

## Build-Time Tuning Constants

Intentional placeholders, to be set once Soul_Tick cadence is locked — consistent with
how the Resolution Log treats them ("Open — build-time tuning constants only:
k_load / k_rest (Energy)"):

- **k_load** — Energy active-load EMA decay coefficient (F-2a). Placeholder default,
  `TODO(build-time)`.
- **k_rest** — Energy idle-recovery EMA drift coefficient (F-2b). Placeholder default,
  `TODO(build-time)`.

Not build-time tuning (locked, reused, not reopened): the recency windows
(72h/14d/14d/60d, Resolution Log item 7, owned by Memory_Graph), the Energy operational
thresholds (30 / 20, in-spec, reused from `soul_filter.py`), Energy_Baseline (100.0,
the contract default) and Energy_Min (0.0, the battery floor).


---

## needs-system — design.md

# Design Document — Module 2: Needs System

## Overview

Needs_System is a single module (Resolution Log item 11) with two internally separated,
mutually independent components:

- **Energy_Tracker** — owns the one continuous value this module is permitted to own,
  Energy. A resource / battery model on a 0–100 scale: single-rate EMA decay toward
  empty under active load (`k_load`), drift-to-baseline recovery toward full during idle
  (`k_rest`) — two constants, no valence, no asymmetry (Resolution Log item 6). Energy
  is SUBSTRATE, explicitly exempt from the no-invented-formula rule; it is exposed as
  context and NEVER writes PAD.
- **Needs_Evaluator** — derives the four categorical need states (Connection, Growth,
  Purpose, Continuity) as `satisfied` / `due` from qualifying graph evidence within each
  need's recency window, by calling Memory_Graph's existing evidence queries. It is
  stateless: each evaluation is a pure function of (current time, graph contents), so a
  need reverts satisfied→due purely because evidence aged out of its window as time
  advances — nothing is actively subtracted (Addendum §3).

The module combines both into the `NeedStates` contract (`daemon/soul_filter.py`) so
Soul_Filter (Module 5) consumes the output unchanged.

This design implements requirements.md as written, using only mechanisms already
specified there or in the supporting documents (`ARIA_Soul_Spec_v4.md`,
`ARIA_Soul_Spec_v4_Addendum.md`, `ARIA_Resolution_Log.md`, the Module 2 Build Plan
entry, `daemon/graph_manager.py`, `daemon/soul_filter.py`). No new mechanism, formula,
or window is introduced. The one genuine gap — the `due` vs `neglected` categorical
split — is carried forward as a flagged decision (OQ-1), not resolved by invention.

## Hard Constraints (carried from requirements.md, non-negotiable)

1. **Energy is the only number.** The four needs carry NO numeric score, percentage,
   0–100 value, "pressure", or "level" — anywhere, ever (Req 7). Energy is the sole
   sanctioned numeric (steering "No invented numbers").
2. **Energy never writes PAD.** Needs_System holds no PAD_Engine reference and calls no
   PAD mutator (Req 6). Energy is exposed as context only.
3. **Needs never pull PAD.** No path from a need state to a PAD change (Req 13; Addendum
   §3 "Stage 5 redefined").
4. **The `due`/`neglected` split is never a disguised percentage.** No "% of window
   elapsed", no "time since evidence" cutoff, no "due = >50%" (Req 12; steering
   percentage test).
5. **Evidence queries are called, not reimplemented.** Memory_Graph owns "does evidence
   exist"; Needs_System owns "what it means for the state" (Req 8.2).
6. **Windows are reused, not reinvented.** 72h/14d/14d/60d come from Resolution Log
   item 7, owned by Memory_Graph's query defaults (Req 9).
7. **k_load / k_rest are build-time placeholders**, clearly marked `TODO(build-time)`
   (F-2a / F-2b; Req 3.3, 4.3).
8. **Single module, two independent components** (Req 1; Resolution Log item 11).
9. **soul_filter.py and graph_manager.py are not modified** (Req 14.3).

## Architecture

```
                     ┌───────────────────────────────────────────────┐
                     │                 Needs_System                    │
                     │  (single module — Resolution Log item 11)       │
                     │                                                 │
  Daemon ───────────▶│  on_soul_tick()        ┌───────────────────┐   │
  (Soul_Tick,        │  on_idle_recovery() ──▶ │  Energy_Tracker   │   │
   active load)      │                         │  Energy: float    │   │
  Daemon ───────────▶│                         │  0..100 (SUBSTRATE)│  │
  (Idle_Recovery)    │                         │  EMA k_load/k_rest│   │
                     │                         │  NO PAD reference │   │
                     │                         └─────────┬─────────┘   │
                     │                                   │ energy      │
                     │  get_need_states(now) ┐           ▼             │
  Memory_Graph ─────▶│   ┌──────────────────┴──┐   ┌──────────────┐   │
  connection_evidence│   │  Needs_Evaluator     │   │  NeedStates  │   │
  growth_evidence    │◀──┤  (stateless)         │──▶│ connection   │   │
  purpose_evidence   │   │  satisfied ⇔ evidence │   │ growth       │   │
  continuity_evidence│   │  in-window; else due │   │ purpose      │   │
  (each → bool)      │   │  NEVER a number      │   │ continuity   │   │
                     │   └──────────────────────┘   │ energy:float │   │
                     │                               └──────┬───────┘   │
                     └──────────────────────────────────────┼──────────┘
                                                            │
                    ┌───────────────────────┬───────────────┼───────────────┐
                    ▼                        ▼               ▼               ▼
             Appraisal_Chain           Soul_Filter        Soul_Filter      Daemon
             Stage 1 (retrieval        (Constraints:      (This Moment /   (initiative)
             PREFERENCE from            energy <30/<20)    context from
             due/neglected needs)                          need states)
                    │                                                    │
                    │  NEEDS influence appraisal INDIRECTLY (preference) │
                    │  — never a pull on PAD. NO ARROW TO PAD_Engine.    │
                    └────────────────────────────────────────────────────┘

  PAD_Engine (Module 1): NOT connected to Needs_System. No inbound arrow.
  Energy is context; needs are preference. Neither writes PAD.
```

## Components and Interfaces

### `EnergyTracker` (class) — the substrate component

Owns the single live Energy value. In-process, synchronous. Holds no PAD reference.

**State held:**
- `_energy: float` — current Energy, 0..100. Unset until `initialize()` (mirrors
  PAD_Engine's initialize-before-use discipline).
- `_initialized: bool` — sentinel for the pre-initialize guard.

**Methods:**
- `initialize(restored: Optional[float] = None)` — set Energy from `restored` (if a
  valid finite 0..100 value) else Energy_Baseline (100.0) (Req 2.2, 2.3). The
  State_Manager conversion happens at the call site, not here (mirrors PAD_Engine).
- `on_soul_tick()` — one active-load EMA step toward Energy_Min via `k_load`
  (Req 3). Clamped not to overshoot below Energy_Min.
- `on_idle_recovery()` — one idle EMA step toward Energy_Baseline via `k_rest`
  (Req 4). Clamped not to overshoot above Energy_Baseline. This is the Build Plan's
  "Energy refill signal — from Daemon (idle)", resolved to drift-to-baseline
  (Resolution Log item 6), not a discrete increment.
- `get_energy() -> float` — current Energy (Req 5.1).
- `energy_band() -> EnergyBand` — categorical NORMAL / LOW / CRITICAL from the in-spec
  thresholds (Req 5.2).

**The EMA step (the only formula; sanctioned by Resolution Log item 6):**
```
_ema_step(current, target, k)  =  k * target + (1 - k) * current
```
- Active load: `target = ENERGY_MIN (0.0)`, `k = k_load` → Energy falls toward empty.
- Idle:        `target = ENERGY_BASELINE (100.0)`, `k = k_rest` → Energy drifts to full.

This is the identical EMA form PAD_Engine uses (`k * baseline + (1-k) * current`),
per Addendum §3 ("the same EMA-style math already locked for PAD") and Resolution Log
item 6. Two constants total (`k_load`, `k_rest`); no positive/negative asymmetry because
Energy has no valence (Resolution Log item 6: "Two constants, not four"). Applied
per-tick (discrete), exactly as PAD_Engine applies its decay per Soul_Tick — no
wall-clock `dt` is used, so no time-integration formula is invented.

**Why `EnergyTracker` has no PAD reference (Req 6):** the strongest guarantee that
Energy never writes PAD is structural absence — the class cannot import, hold, or call
PAD_Engine, so there is no path to `apply_appraisal_delta`. Energy is emitted only as a
float / band for other modules to read. (This mirrors Addendum §5's F4 decision: a
mechanism with no PAD path, by construction.)

### `NeedsEvaluator` (class) — the categorical component

Derives the four need states from Memory_Graph evidence. **Stateless** with respect to
need states (Req 11.2): it stores only its injected dependencies (the graph and the
self-entity id), never a mutable need value. Every call recomputes from scratch.

**Injected dependencies:**
- `graph: MemoryGraph` — the real Module 3 interface (Rule 6). Never re-created here.
- `self_entity_id: Optional[str]` — the self-referential EntityNode id for
  `continuity_evidence` (OQ-2). May be `None` (then Continuity is `due` — no narrative
  to find).

**Methods:**
- `evaluate_connection(now) -> NeedState`
- `evaluate_growth(now) -> NeedState`
- `evaluate_purpose(now) -> NeedState`
- `evaluate_continuity(now) -> NeedState`
- `evaluate_all(now) -> Dict[str, NeedState]`

**The categorical rule (identical shape for all four — the heart of Req 12):**
```
evidence_present = graph.<need>_evidence(now=now[, self_entity_id])   # a bool
state = NeedState.SATISFIED if evidence_present else NeedState.DUE
```
- `SATISFIED` ⇔ qualifying evidence exists within the window (the bool is True). A real
  category — "there either is qualifying evidence in the window or there isn't" — passes
  the percentage test.
- non-satisfied ⇒ `DUE` — the direct categorical complement ("evidence aged out; the
  need is now due"). No second signal, no numeric fraction, no window-elapsed measure.
- `NEGLECTED` is **never emitted** — see the decision section below (OQ-1).

`now` is passed straight through to the Memory_Graph query, which applies its own locked
window default (`WINDOW_CONNECTION`/etc.). The evaluator introduces no window constant of
its own (Req 9.2).

### `NeedsSystem` (class) — the single module facade

Composes one `EnergyTracker` and one `NeedsEvaluator` (Req 1). The Daemon and consumers
talk to this facade.

**Methods:**
- `initialize(restored_energy=None)` — delegates to `EnergyTracker.initialize`.
- `on_soul_tick()` / `on_idle_recovery()` — delegate to `EnergyTracker` (Req 15.2). The
  Daemon (Module 8) calls these; Needs_System is the callee (mirrors PAD_Engine). The
  Daemon owns the active-load-vs-idle decision (its F-8b attentional policy) — this
  module does not detect load itself.
- `get_energy() -> float`, `energy_band() -> EnergyBand` — Energy read surface (Req 5).
- `get_need_states(now=None) -> NeedStates` — **the primary output**. Builds the exact
  `soul_filter.NeedStates` with the four evaluated `NeedState`s + current Energy (Req 14).
  `now` defaults from an injected clock (`clock` callable, default UTC now) so production
  needs no explicit time while tests inject a controlled clock (Req 11.3).

**Clock injection.** `NeedsSystem(clock=...)` accepts a `Callable[[], datetime]`
(default: aware-UTC now). `get_need_states(now=None)` uses the explicit `now` if given,
else `clock()`. This is the injected-clock seam that makes the time-driven revert
(Req 11) testable, and mirrors Memory_Graph's own `now=None → _now()` pattern.

## Data Types

```python
class EnergyBand(Enum):          # categorical readout of the substrate (Req 5.2)
    NORMAL = "normal"            # Energy >= 30
    LOW = "low"                  # 20 <= Energy < 30   (v4 "below 30" cognitive-load)
    CRITICAL = "critical"        # Energy < 20         (DMN shallow-pass gate)
```

Reused from `daemon/soul_filter.py` (imported, not redefined — single source of truth):
- `NeedState` (satisfied / due / neglected) — the categorical need enum.
- `NeedStates` — the output contract (four `NeedState` + `energy: float`).
- `ENERGY_LOW = 30.0`, `ENERGY_CRITICAL = 20.0` — the in-spec operational thresholds.

Module-local constants:
- `ENERGY_BASELINE = 100.0` (full battery / idle target; = `NeedStates` default).
- `ENERGY_MIN = 0.0` (empty battery / load target).
- `K_LOAD`, `K_REST` — build-time placeholders, `TODO(build-time)` (F-2a / F-2b).

## The `due` vs `neglected` Decision (OQ-1) — full rationale

This is the module's designated CRITICAL-CARE point. The reasoning, in full, so the
architect can audit it:

1. **What the governing doc actually says.** Addendum §3: the four needs are
   `satisfied / due / neglected`, and each state is "determined by whether qualifying
   evidence exists in the graph within a recency window ... When evidence ages out of its
   window, the state reverts on its own." The *determination mechanism it specifies* is
   binary: evidence-in-window vs not. That is exactly the shape of the Memory_Graph
   evidence queries — each returns a single `bool`.

2. **What that yields, honestly.** A binary fact yields two categories. Mapping is
   forced: `satisfied` = evidence present (True). The complement is one category, most
   naturally named `due` ("it's now due for fresh evidence") — matching the Addendum's
   "reverts on its own" framing.

3. **Why not a third category from the same data.** To split the complement into `due`
   vs `neglected` from the evidence booleans alone, one would need a *second* signal. The
   only signal the window gives is "how long since evidence" — a duration, i.e. a
   percentage of the window elapsed. That is exactly the "number in disguise" the
   percentage test and this module's CRITICAL-CARE constraint forbid ("Never implement
   'due = >50% window elapsed'"). Rejected.

4. **The one categorical `neglected` fact the docs mention.** Only Continuity gets a
   distinct categorical hint: "neglected when ... new evidence contradicts rather than
   extends it." This is a real category (contradiction is a yes/no fact, not a fraction).
   But it is **not reachable** through `continuity_evidence`, which returns only "was the
   narrative extended within 60d (bool)". Surfacing a contradiction fact would require a
   new Memory_Graph query — which Req 14.3 forbids adding unilaterally, and which Rule 1
   forbids inventing. So even here, `neglected` cannot be produced without either a
   forbidden numeric cutoff or a forbidden contract change.

5. **Decision.** Implement the most defensible categorical reading: `satisfied` ⇔
   evidence in-window; else `due`. Preserve `neglected` in the contract enum (Soul_Filter
   still imports it) but **do not emit it**. Flag the split as OQ-1 for the architect,
   with two concrete, percentage-free options offered (Continuity contradiction fact;
   Growth "abandoned-in-window with none resolved" fact) — both of which would require a
   Memory_Graph query the architect must approve.

6. **Why this is safe / lossless downstream.** The single documented consumer of the
   categorical states is the Stage-1 retrieval PREFERENCE (Addendum §3): it surfaces
   preferred edges when a need is "due or neglected" — it treats the two identically, so
   collapsing loses no retrieval behavior. Soul_Filter reads only `NeedStates.energy`
   (verified in `daemon/soul_filter.py`: `_derive_constraints` uses
   `need_states.energy < ENERGY_LOW`; it does not branch on the four categorical fields).
   So emitting `due` instead of `neglected` changes no current behavior while keeping the
   module honest about the gap.

## PAD-purity: how "never writes PAD" and "needs never pull PAD" are guaranteed

- **Structural (Req 6.1):** `needs_system.py` does not import `PADEngine` and no
  Needs_System class holds a PAD reference or has a PAD parameter. There is no line that
  could call `apply_appraisal_delta` or any PAD mutator. Verified by a source scan and a
  signature scan in the tests.
- **Functional tripwire (Req 6, Req 13):** the tests monkeypatch
  `PADEngine.apply_appraisal_delta` to raise, then exercise the full Needs_System cycle
  (tick, recovery, evaluate) and assert it never fires; and they run the cycle beside a
  real, initialized PAD_Engine and assert its PAD is byte-identical before and after
  (Needs_System cannot touch what it cannot reach).
- **Semantic (Req 13):** Needs_System performs no appraisal and emits only categorical
  states + an Energy number. Any eventual PAD effect must route through Appraisal_Chain
  (Stage-1 preference → Q1–Q4 → Stage-4 PAD delta), which is outside this module.

## Error Handling

- **Pre-initialize guard.** `on_soul_tick` / `on_idle_recovery` / `get_energy` /
  `energy_band` / `get_need_states` raise `RuntimeError` if called before `initialize()`
  (mirrors PAD_Engine's `_require_initialized`). Prevents reading an unset Energy.
- **Invalid restored Energy.** Non-finite, non-numeric, or out-of-[0,100] restored values
  fall back to Energy_Baseline (Req 2.2 fallback), mirroring PAD_Engine's
  `_is_valid_snapshot`.
- **Missing self node.** If `self_entity_id` is `None` or absent from the graph,
  `continuity_evidence` returns False → Continuity is `due` (OQ-2). No crash.
- **Graph query is authoritative.** Needs_Evaluator never second-guesses a query result;
  a `bool` is mapped directly to a category. No numeric post-processing.

## Testing Strategy

Plain `pytest`, no `hypothesis` (matches Modules 1/3/5 style). Proves:
1. **Categorical, no number:** each need field on the produced `NeedStates` is a
   `NeedState`; no numeric per-need field/attribute/method exists; the only numeric is
   `energy`. (Req 7)
2. **Time-driven revert:** with a REAL Memory_Graph, one piece of evidence created at T0;
   a need is `satisfied` at `now = T0 + (window - ε)` and `due` at
   `now = T0 + (window + ε)` — flip caused purely by advancing the injected clock,
   nothing subtracted, graph unchanged. (Req 11)
3. **Energy substrate:** decays monotonically toward Energy_Min under repeated
   `on_soul_tick`, recovers monotonically toward Energy_Baseline under repeated
   `on_idle_recovery`, never overshoots either bound; bands map at 30/20. (Req 3, 4, 5)
4. **Never writes PAD:** structural (no PAD import / no PAD param) + tripwire
   (monkeypatched mutator never fires) + real-PAD-unchanged. (Req 6, 13)
5. **Real integration:** the evaluator calls the real `*_evidence` methods (call-count
   spy proves delegation, not reimplementation); qualifying evidence for each of the four
   needs (built via the real graph write methods) flips its state satisfied↔due. (Req 8)
6. **Soul_Filter contract:** the produced value is a real `soul_filter.NeedStates`, and
   passing it through the real `SoulFilter._derive_constraints` / `assemble_instruction`
   yields the energy-gated "do not overextend" constraint iff Energy < 30 — consumed
   unchanged. (Req 14)

## Open Questions

See requirements.md Open Questions. Summary: **OQ-1** due-vs-neglected categorical basis
(implemented as satisfied/due, `neglected` flagged and not emitted); **OQ-2** self-entity
id provisioning (injected); **OQ-3** Purpose weakest signal + Memory_Graph
`purpose_evidence` placeholder (`TODO(OQ6-M2)`); **OQ-4** contract location (imported from
`soul_filter.py`, ideally relocated). None are resolved by invention. **k_load / k_rest**
are build-time placeholders (F-2a / F-2b), not architectural gaps.


---

## needs-system — tasks.md

# Implementation Plan — Module 2: Needs System

This plan implements design.md exactly as written. Each task is small and independently
testable. Precedence: `ARIA_Resolution_Log.md` > `ARIA_Soul_Spec_v4_Addendum.md` >
`ARIA_Soul_Spec_v4.md`. Nothing here reopens a locked flag (F-2c/F-2d RESOLVED;
F-2a/F-2b are build-time placeholders). The `due`/`neglected` split is implemented as
the flagged categorical reading (satisfied/due), never a numeric cutoff (OQ-1).

- [x] 1. Module scaffold + reuse-not-redefine imports.
  - Create `daemon/needs_system.py` with module docstring citing Resolution Log
    6/7/11 and the flag disposition.
  - Import `NeedState`, `NeedStates`, `ENERGY_LOW`, `ENERGY_CRITICAL` from
    `daemon.soul_filter` (single source of truth; OQ-4). Import `MemoryGraph` from
    `daemon.graph_manager` for typing only.
  - Do NOT import `PADEngine` or any PAD mutator anywhere in the file (Req 6.1).
  - _Requirements: 1.1, 6.1, 14.2_

- [x] 2. Module constants.
  - `ENERGY_BASELINE = 100.0`, `ENERGY_MIN = 0.0`.
  - `K_LOAD`, `K_REST` as clearly-marked `TODO(build-time)` placeholders (F-2a/F-2b).
  - `EnergyBand` enum (NORMAL / LOW / CRITICAL) from the in-spec 30/20 thresholds.
  - _Requirements: 3.3, 4.3, 5.2_

- [x] 3. `_ema_step` helper (the only formula).
  - `_ema_step(current, target, k) = k*target + (1-k)*current` — the same EMA form as
    PAD, sanctioned by Resolution Log item 6. No other formula introduced.
  - _Requirements: 3.1, 4.1_

- [x] 4. `EnergyTracker.__init__` + `initialize` + validity + pre-init guard.
  - `_energy`, `_initialized`. `initialize(restored=None)` → restored (if finite,
    0..100) else `ENERGY_BASELINE`. `_require_initialized` raises `RuntimeError`.
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 5. `EnergyTracker.on_soul_tick` (active-load decay, k_load).
  - One `_ema_step` toward `ENERGY_MIN` with `K_LOAD`; clamp ≥ `ENERGY_MIN`.
  - _Requirements: 3.1, 3.2, 3.4_

- [x] 6. `EnergyTracker.on_idle_recovery` (drift-to-baseline, k_rest).
  - One `_ema_step` toward `ENERGY_BASELINE` with `K_REST`; clamp ≤ `ENERGY_BASELINE`.
    Drift-to-baseline, NOT a discrete increment (Resolution Log item 6).
  - _Requirements: 4.1, 4.2, 4.4_

- [x] 7. `EnergyTracker.get_energy` + `energy_band`.
  - `get_energy()` returns the float; `energy_band()` maps via `ENERGY_LOW`/
    `ENERGY_CRITICAL`. No PAD anywhere (Req 6.2).
  - _Requirements: 5.1, 5.2, 6.2, 6.3_

- [x] 8. `NeedsEvaluator.__init__` (inject graph + self_entity_id, stateless).
  - Store only `graph` and `self_entity_id`; NO mutable need state (Req 11.2).
  - _Requirements: 8.1, 8.2, 11.2_

- [x] 9. Per-need evaluators (categorical map).
  - `evaluate_connection/growth/purpose/continuity(now)` each call the matching real
    `graph.*_evidence(now=...)` (continuity also passes `self_entity_id`) and map the
    returned `bool`: True → `SATISFIED`, else `DUE`. Never `NEGLECTED`; never a number
    (Req 7, 10, 12).
  - _Requirements: 7.1, 8.3, 8.4, 9.1, 9.2, 10.1-10.4, 12.1, 12.2, 12.4_

- [x] 10. `NeedsEvaluator.evaluate_all(now)`.
  - Return `{connection, growth, purpose, continuity}` → `NeedState`.
  - _Requirements: 7.1, 11.1_

- [x] 11. `NeedsSystem` facade (compose the two components + clock).
  - `__init__(graph, self_entity_id=None, clock=_now)` builds an `EnergyTracker` and a
    `NeedsEvaluator`. `initialize(restored_energy=None)`.
  - Delegate `on_soul_tick` / `on_idle_recovery` / `get_energy` / `energy_band`.
  - _Requirements: 1.1, 1.2, 1.3, 15.2_

- [x] 12. `NeedsSystem.get_need_states(now=None)` — the primary output.
  - `now = now or clock()`. Build `soul_filter.NeedStates(connection=…, growth=…,
    purpose=…, continuity=…, energy=self._energy.get_energy())` (Req 14.1, 14.2).
  - _Requirements: 5.4, 11.3, 13.1, 14.1, 14.2, 15.3_

- [x] 13. Tests — `tests/test_needs_system.py` (plain pytest, no hypothesis).
  - Categorical/no-number; time-driven revert via injected clock; Energy decay/refill
    substrate + bands; never-writes-PAD (structural + tripwire + real-PAD-unchanged);
    real graph_manager evidence integration (call-count spy + state flips); Soul_Filter
    `NeedStates` contract consumed unchanged.
  - _Requirements: all_

- [x] 14. Verify.
  - `python3 -m pytest tests/test_needs_system.py -q` green; then `python3 -m pytest -q`
    stays 229 + new. No modification to `graph_manager.py` / `soul_filter.py`. Temp
    files cleaned.
  - _Requirements: all_

## Notes

- **F-2a / F-2b** (`k_load` / `k_rest` values): build-time placeholders (Resolution Log
  "Open — build-time tuning constants only"). Mechanism is locked by Resolution Log
  item 6.
- **F-2c** (need→window): RESOLVED, Resolution Log item 7 — reused via Memory_Graph
  query defaults.
- **F-2d** (one module/two): RESOLVED, Resolution Log item 11 — single module, two
  components.
- **OQ-1** (due vs neglected): flagged; implemented as satisfied/due, `neglected` not
  emitted. No numeric cutoff.

