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
