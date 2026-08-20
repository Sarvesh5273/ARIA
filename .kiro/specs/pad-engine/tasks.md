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

- [ ] 1. Set up module scaffold
  - Create the PAD_Engine module file/package structure (no other module's
    files are touched).
  - Add imports needed for `Enum`, `dataclass`, `Optional`, `Deque`,
    `Tuple`, `Literal`, and `collections.deque`.
  - _Requirements: (structural only, no acceptance criteria yet)_

- [ ] 2. Implement `Valence` enum with exactly four members
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

- [ ] 3. Implement `PADSnapshot` frozen dataclass
  - Fields: `pleasure: float`, `arousal: float`, `dominance: float`.
  - Frozen/immutable, per design.md's Data Types rationale (no consumer can
    mutate PAD_Engine's live state through a returned snapshot).
  - _Requirements: 7.1_

- [ ] 4. Implement `PADDelta` frozen dataclass
  - Fields: `d_pleasure: float`, `d_arousal: float`, `d_dominance: float`,
    `valence: Valence`, `origin: Literal["appraisal", "aha_insight"] =
    "appraisal"`.
  - Frozen/immutable, matching design.md's Data Types section verbatim.
  - Write a unit test asserting the dataclass is frozen (attempting to set
    an attribute after construction raises).
  - _Requirements: 2.2, 4.1, 4.3_

- [ ] 5. Implement module constants
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

- [ ] 6. Implement `PADEngine.__init__` and state fields
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

- [ ] 7. Implement `initialize(restored)` including the baseline-fallback and
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

- [ ] 7b. Extend `initialize()` with a `restored_valence` parameter (this
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

- [ ] 8. Extend the call-site conversion helper (outside `PADEngine`,
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

- [ ] 9. Implement the pre-`initialize()` guard on `get_current_pad()`,
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

- [ ] 10. Implement `apply_appraisal_delta(delta)`
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

- [ ] 11. Implement `on_soul_tick()` for the `POSITIVE` and `NEGATIVE` cases
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

- [ ] 12. Implement the standard EMA decay helper
  - Extract the EMA form `new = coefficient * baseline + (1 - coefficient)
    * current`, applied independently to each of P, A, D, into a small
    internal helper used by Task 11 (`NEGATIVE`/`POSITIVE`) and also by
    Task 14 (`VALENCE_UNCERTAIN`, which reuses the `NEGATIVE` coefficient
    value through this same helper) — not reused by Tasks 13/15, which
    raise before reaching this helper.
  - Write a unit test verifying the helper's output against hand-computed
    values for at least two coefficient/starting-PAD combinations.
  - _Requirements: 3.1, 3.2, 3.3_

- [ ] 13. Implement `on_soul_tick()` `NEUTRAL` case: raise
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

- [ ] 14. Implement `on_soul_tick()` `VALENCE_UNCERTAIN` case: decay using
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

- [ ] 15. Implement `on_soul_tick()` residual restore-boundary case: raise
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

- [ ] 16. Implement `on_soul_tick()` `None`-at-baseline case: no-op skip
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

- [ ] 17. Implement `get_current_pad()`
  - Returns a `PADSnapshot` of the current `_pleasure`, `_arousal`,
    `_dominance` values. Single method, no caller-identity parameter (per
    design.md: all five consumers call the same accessor). Subject to the
    Task 9 pre-`initialize()` guard.
  - Write a unit test: returned snapshot matches current internal PAD
    values exactly, immediately after both `initialize()` and after a
    decay/delta call.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ] 18. Implement `get_pad_history()`
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

- [ ] 19. Verify no direct-assignment surface exists, and structural
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

- [ ] 20. Integration test: `StateManager` round-trip boundary, using the
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

- [ ] 21. Wire together and run full test suite; confirm remaining Open
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
