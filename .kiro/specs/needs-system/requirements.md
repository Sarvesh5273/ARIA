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
