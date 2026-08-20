"""Module 1 — PAD Engine (Pleasure/Arousal/Dominance state owner).

Locked spec: see .kiro/specs/pad-engine/{requirements,design}.md. This
module is the sole owner and mutator of Aria's live, in-memory PAD state.
Exactly two mutation paths exist: apply_appraisal_delta (an Appraisal_Chain
PAD_Delta, including an Aha_Insight_PAD_Delta) and on_soul_tick (EMA_Decay
on every Soul_Tick). No other interface may modify Pleasure, Arousal, or
Dominance.

This file implements all 21 tasks in tasks.md: scaffold, Valence enum,
PADSnapshot, PADDelta, module constants, PADEngine.__init__ and state
fields, initialize() (including the restored_valence parameter that fixes
the routine restore-boundary case, per requirements.md/design.md's
narrowed Open Question 4), the pre-initialize() RuntimeError guard,
apply_appraisal_delta's addition logic, on_soul_tick's full valence
handling — NEGATIVE/POSITIVE/VALENCE_UNCERTAIN decay (VALENCE_UNCERTAIN
resolved to reuse EMA_COEFFICIENT_NEGATIVE, per requirements.md's
resolved Open Question 3), the NEUTRAL raise (Requirement 3's note, not
an Open Question), the residual restore-boundary raise (narrowed Open
Question 4, now rare rather than routine), and the baseline no-op skip —
the standalone EMA decay helper, get_current_pad, and get_pad_history.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Deque, Literal, Optional, Tuple
from collections import deque


# ---------------------------------------------------------------------------
# Task 2 — Valence enum (exactly four members)
# ---------------------------------------------------------------------------

class Valence(Enum):
    """Valence of the Appraisal_Chain event that produced a PADDelta.

    Exactly four members, per design.md's Data Types section. The fourth
    member, VALENCE_UNCERTAIN, exists because v4's EventNode schema defines
    appraisal_q2 as four-valued; a partial appraisal can still produce a
    real PAD_Delta at Stage 4 with Q2 = VALENCE_UNCERTAIN. Former Open
    Question 3 (which coefficient VALENCE_UNCERTAIN should use) is now
    resolved: it reuses EMA_COEFFICIENT_NEGATIVE, the same precedent-based
    decision documented in on_soul_tick and design.md's Open Question 3
    section.
    """
    POSITIVE = "positive"
    NEGATIVE = "negative"
    NEUTRAL = "neutral"
    VALENCE_UNCERTAIN = "valence_uncertain"


# ---------------------------------------------------------------------------
# Task 3 — PADSnapshot (frozen)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PADSnapshot:
    """An immutable Pleasure/Arousal/Dominance reading.

    Frozen so that no consumer holding a returned snapshot can mutate
    PAD_Engine's live state — the only mutation paths are PADEngine's own
    apply_appraisal_delta and on_soul_tick methods (not yet implemented in
    this file).
    """
    pleasure: float
    arousal: float
    dominance: float


# ---------------------------------------------------------------------------
# Task 4 — PADDelta (frozen)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PADDelta:
    """The (dP, dA, dD) output of Appraisal_Chain Stage 4.

    valence: the valence of the Appraisal_Chain event that produced this
    delta. Stored by apply_appraisal_delta into PADEngine's internal
    _last_applied_valence, and read by on_soul_tick (which takes no
    parameter of its own) to select the EMA_Decay coefficient; does not
    affect how apply_appraisal_delta adds d_pleasure/d_arousal/d_dominance.
    This field is a scope addition relative to the Build Plan's three
    named inputs (see requirements.md Requirement 4's note) — introduced
    to make the Resolution Log's whole-event, per-tick decay decision
    implementable.

    origin: informational only (e.g. for logging/debugging); it does not
    change how the delta is applied, since Aha_Insight_PAD_Delta and a
    normal PAD_Delta are processed identically (Req 4.3).
    """
    d_pleasure: float
    d_arousal: float
    d_dominance: float
    valence: Valence
    origin: Literal["appraisal", "aha_insight", "cognitive_load"] = "appraisal"


# ---------------------------------------------------------------------------
# Task 5 — module constants
# ---------------------------------------------------------------------------

# Fixed PAD baseline (Req 8, locked). Matches state_manager.py's existing
# PAD_BASELINE = (0.55, 0.45, 0.58) exactly — this module does not introduce
# a second definition of the baseline.
PAD_BASELINE = PADSnapshot(pleasure=0.55, arousal=0.45, dominance=0.58)

# Asymmetric EMA decay coefficients (Req 3.2, Req 3.3, locked).
EMA_COEFFICIENT_NEGATIVE = 0.6
EMA_COEFFICIENT_POSITIVE = 0.75

# Build-time tuning constant (requirements.md "Build-Time Tuning
# Constants"). Placeholder default; to be tuned once Soul_Tick cadence is
# locked (Open Question 1). Not an architectural decision — mirrors
# state_manager.py's SAVE_CADENCE_SECONDS and the Resolution Log's
# k_load/k_rest treatment.
PAD_HISTORY_LENGTH = 50  # placeholder default, tune at build time

# No coefficient constant is defined for NEUTRAL or the residual
# restore-boundary case — defining one would silently resolve an
# unresolved requirement/Open Question by invention. VALENCE_UNCERTAIN
# does NOT get a new constant either: former Open Question 3 is resolved
# by reusing EMA_COEFFICIENT_NEGATIVE (see on_soul_tick), per the
# Addendum's "reuse before invent" principle — not by inventing a third
# coefficient value.


# ---------------------------------------------------------------------------
# Task 12 — standard EMA decay helper
# ---------------------------------------------------------------------------

def _ema_decay(current: float, baseline: float, coefficient: float) -> float:
    """The standard EMA form: new = coefficient * baseline + (1 -
    coefficient) * current. Applied independently to each of P, A, D by
    on_soul_tick (Task 11); this is the only formula used there — no other
    formula is introduced."""
    return coefficient * baseline + (1 - coefficient) * current



# ---------------------------------------------------------------------------
# Task 6 — PADEngine.__init__ and state fields
# ---------------------------------------------------------------------------

class PADEngine:
    """Sole owner and mutator of Aria's live, in-memory PAD state.

    All 21 tasks implemented: __init__/state fields, initialize() (with
    the restored_valence parameter for the routine post-restart case),
    the pre-initialize() RuntimeError guard, apply_appraisal_delta's
    addition logic, on_soul_tick's full valence handling
    (NEGATIVE/POSITIVE/VALENCE_UNCERTAIN decay — VALENCE_UNCERTAIN reuses
    the NEGATIVE coefficient, resolved Open Question 3 — the NEUTRAL
    raise, the residual restore-boundary raise, narrowed Open Question 4,
    and the baseline no-op skip), get_current_pad, and get_pad_history.
    """

    def __init__(self) -> None:
        # Current PAD. Left unset (no attribute assignment) until
        # initialize() is called — per design.md's Restore/persist
        # boundary section, baseline-or-restored assignment is
        # initialize()'s job, not __init__'s. _initialized is the sentinel
        # used to detect "never initialized" for the pre-initialize()
        # guard (Task 9).
        self._initialized: bool = False
        self._pleasure: Optional[float] = None
        self._arousal: Optional[float] = None
        self._dominance: Optional[float] = None

        # Valence of the most recently applied PADDelta. None until the
        # first PADDelta is applied this process lifetime.
        self._last_applied_valence: Optional[Valence] = None

        # Bounded PAD_History ring buffer.
        self._history: Deque[PADSnapshot] = deque(maxlen=PAD_HISTORY_LENGTH)

    # -----------------------------------------------------------------
    # Task 7 — initialize()
    # -----------------------------------------------------------------

    def initialize(
        self,
        restored: Optional[PADSnapshot],
        restored_valence: Optional[Valence] = None,
    ) -> None:
        """Set current PAD from a restored snapshot, or fall back to
        PAD_BASELINE if restored is None or invalid.

        Accepts only Optional[PADSnapshot] for `restored` — does not
        accept, import, or reference state_manager.py's PADState type.
        Converting a PADState into a PADSnapshot is explicitly out of
        scope for PADEngine; per design.md's Restore/persist boundary
        section, that conversion happens at the call site that wires
        PADEngine and StateManager together, not inside either class.

        restored_valence: the Valence corresponding to the persisted
        `last_applied_valence` string state_manager.py now stores
        alongside PAD (see daemon/state_manager.py's
        load_last_applied_valence). This is the fix for the routine case
        of (former, now-narrowed) Open Question 4: on a normal restart,
        the call-site wiring layer loads the persisted string, converts
        it to a Valence via the extended Task 8 helper, and passes it
        here, so _last_applied_valence is no longer None and
        on_soul_tick's restore-boundary raise does not fire. Converting
        the raw string into a Valence member happens at that same
        call-site helper — NOT inside PADEngine, NOT inside
        StateManager — mirroring exactly how `restored` itself is
        converted from PADState. If the caller has no persisted valence
        (first-ever run, corrupted/missing field, or a crash between an
        appraisal delta and the next save), it passes None here (the
        default), and the residual restore-boundary raise in
        on_soul_tick remains exactly as before for that rarer case.
        """
        if restored is None or not self._is_valid_snapshot(restored):
            self._pleasure = PAD_BASELINE.pleasure
            self._arousal = PAD_BASELINE.arousal
            self._dominance = PAD_BASELINE.dominance
        else:
            self._pleasure = restored.pleasure
            self._arousal = restored.arousal
            self._dominance = restored.dominance

        self._initialized = True
        # _last_applied_valence is set from restored_valence if the caller
        # supplied one (the routine post-restart case, now that
        # state_manager.py persists this alongside PAD); otherwise it
        # remains None, exactly as before. Restore-boundary raise vs.
        # baseline no-op skip in on_soul_tick is unchanged either way —
        # only the None case's likelihood has changed (rare instead of
        # routine), not its handling.
        self._last_applied_valence = restored_valence

    @staticmethod
    def _is_valid_snapshot(snapshot: PADSnapshot) -> bool:
        """Basic validity check: all three components must be finite
        floats (not NaN, not +/-inf, not a non-numeric value)."""
        for value in (snapshot.pleasure, snapshot.arousal, snapshot.dominance):
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                return False
            if value != value:  # NaN check without importing math
                return False
            if value in (float("inf"), float("-inf")):
                return False
        return True

    # -----------------------------------------------------------------
    # Task 9 — pre-initialize() guard
    # -----------------------------------------------------------------

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError(
                "PADEngine method called before initialize(). "
                "initialize() must be called at least once before "
                "get_current_pad(), on_soul_tick(), or "
                "apply_appraisal_delta() may be used."
            )

    def get_current_pad(self) -> PADSnapshot:
        """Implements Task 17. Returns a PADSnapshot of the current
        _pleasure, _arousal, _dominance values. Single method, no
        caller-identity parameter — all five consumers (Soul_Filter,
        Visual_Layer, Audio_Pipeline, Appraisal_Chain Stage 1, Daemon)
        call this same accessor."""
        self._require_initialized()
        return PADSnapshot(
            pleasure=self._pleasure,
            arousal=self._arousal,
            dominance=self._dominance,
        )

    def on_soul_tick(self) -> None:
        """Implements Tasks 11, 13, 14 (resolved), 15, 16.

        - NEGATIVE (Task 11): selects EMA_COEFFICIENT_NEGATIVE, applies it
          uniformly to P, A, D via the Task 12 EMA helper, and appends the
          resulting PADSnapshot to _history.
        - VALENCE_UNCERTAIN (Task 14, formerly Open Question 3, now
          resolved): also selects EMA_COEFFICIENT_NEGATIVE — the same
          coefficient as NEGATIVE, not a new value. Rationale: v4's
          Emergency Type Detection already establishes "when
          classification is ambiguous, default to the more cautious
          treatment" (UNCLASSIFIED defaults to Type B, the most careful
          emergency type). VALENCE_UNCERTAIN is a real Q2 appraisal
          outcome (appraisal ran and returned an ambiguous category, not
          missing data), so this precedent applies directly. Reuses the
          existing NEGATIVE coefficient constant rather than inventing a
          third value (Addendum's "reuse before invent" principle). See
          design.md's Open Question 3 section (now a resolved decision).
        - POSITIVE (Task 11): selects EMA_COEFFICIENT_POSITIVE, applied
          uniformly to P, A, D, appended to _history.
        - NEUTRAL (Task 13): raises NotImplementedError. NOT an Open
          Question — per requirements.md Requirement 3's note, neutral
          valence handling is recorded as an in-requirement note only.
          Distinct from Open Question 4 (VALENCE_UNCERTAIN is no longer a
          raising case at all).
        - None with current PAD NOT at PAD_BASELINE (Task 15, the
          residual restore-boundary case): raises NotImplementedError.
          This is the narrowed (not closed) Open Question 4 — a
          persistence-boundary omission, now expected to be rare rather
          than routine, since state_manager.py persists
          last_applied_valence alongside PAD and initialize()'s
          restored_valence parameter populates _last_applied_valence on a
          normal restart. This raise fires only when no persisted valence
          exists at all (first-ever run, corrupted/missing field, or a
          crash between an appraisal delta and the next save).
        - None with current PAD exactly at PAD_BASELINE (Task 16): no-op
          skip — decaying baseline toward baseline is a no-op by
          construction regardless of coefficient, so skipping resolves
          nothing by invention. The tick still "occurred," so the
          unchanged baseline snapshot is still appended to _history.

        No default coefficient is picked for the NEUTRAL or
        restore-boundary raising cases. No history entry is appended when
        this method raises. The two remaining NotImplementedError
        messages (NEUTRAL, restore-boundary) are distinct from one
        another.
        """
        self._require_initialized()

        if self._last_applied_valence is Valence.NEGATIVE:
            coefficient = EMA_COEFFICIENT_NEGATIVE
        elif self._last_applied_valence is Valence.VALENCE_UNCERTAIN:
            # Resolved Open Question 3: reuse EMA_COEFFICIENT_NEGATIVE,
            # not a new constant. See docstring above and design.md's
            # Open Question 3 section for the "default to the more
            # cautious treatment" rationale.
            coefficient = EMA_COEFFICIENT_NEGATIVE
        elif self._last_applied_valence is Valence.POSITIVE:
            coefficient = EMA_COEFFICIENT_POSITIVE
        elif self._last_applied_valence is Valence.NEUTRAL:
            raise NotImplementedError(
                "on_soul_tick: no EMA_Decay coefficient is defined for "
                "NEUTRAL valence. This is NOT an Open Question — per "
                "requirements.md Requirement 3's note, handling of a "
                "neutral-valence originating event is recorded as an "
                "in-requirement note only, deliberately left unresolved "
                "rather than defaulted to 0.6, 0.75, or no decay."
            )
        elif self._last_applied_valence is None and not self._is_at_baseline():
            raise NotImplementedError(
                "on_soul_tick: current PAD was restored to a non-baseline "
                "value and no Appraisal_Chain PADDelta has been applied "
                "yet this session, so no valence is available to select "
                "an EMA_Decay coefficient. This IS Open Question 4 in "
                "requirements.md (decay coefficient on restore, before "
                "any same-session delta) — a persistence-boundary "
                "omission, since state_manager.py does not persist the "
                "originating valence alongside PAD. Flagged for architect "
                "decision, not resolved here."
            )
        else:
            # _last_applied_valence is None and current PAD is exactly
            # PAD_BASELINE (Task 16): no-op skip. Decaying baseline toward
            # baseline is a no-op by construction regardless of which
            # (unresolved) coefficient would have been chosen, so
            # skipping resolves nothing by invention. The tick still
            # "occurred," so the unchanged baseline snapshot is appended.
            self._history.append(
                PADSnapshot(
                    pleasure=self._pleasure,
                    arousal=self._arousal,
                    dominance=self._dominance,
                )
            )
            return

        self._pleasure = _ema_decay(self._pleasure, PAD_BASELINE.pleasure, coefficient)
        self._arousal = _ema_decay(self._arousal, PAD_BASELINE.arousal, coefficient)
        self._dominance = _ema_decay(self._dominance, PAD_BASELINE.dominance, coefficient)

        self._history.append(
            PADSnapshot(
                pleasure=self._pleasure,
                arousal=self._arousal,
                dominance=self._dominance,
            )
        )

    def _is_at_baseline(self) -> bool:
        return (
            self._pleasure == PAD_BASELINE.pleasure
            and self._arousal == PAD_BASELINE.arousal
            and self._dominance == PAD_BASELINE.dominance
        )

    def apply_appraisal_delta(self, delta: PADDelta) -> None:
        """Implements Task 10: adds delta.d_pleasure/d_arousal/d_dominance
        to current PAD, and stores delta.valence into
        _last_applied_valence. Does not branch on delta.origin — a normal
        PADDelta and an Aha_Insight_PAD_Delta are processed identically
        (Req 4.3). Does not append to _history (only Soul_Tick outcomes
        are recorded, per design.md's PAD_History Semantics).

        After applying the delta, each dimension is clamped to [0.0, 1.0].
        This represents physiological homeostasis — humans cannot experience
        unbounded emotion intensity. This is the RESOLUTION of former Open
        Question 2 (PAD numeric bounds), which earlier spec revisions
        carried forward as "no clamping code introduced": the clamp is
        intentional, not accidental. Grounding: Mehrabian's own standardized
        PAD scales are bounded ([-1, +1]); Russell's circumplex is a bounded
        space; emotion-regulation research requires bounded intensity for
        adaptive regulation to function. EMA_Decay on Soul_Tick provides the
        natural recovery path from a bounded extreme — unbounded PAD would
        let a single event produce an unrealistically prolonged state (e.g.
        Pleasure = 50 taking hundreds of ticks to decay back toward
        baseline). Two downstream consumers already assume a normalized
        [0, 1] range — Visual_Layer's zone thresholds and Audio_Pipeline's
        prosody anchor at 0.5 — so the bound is consistent with the built
        system, not only with the literature. Covered by
        test_apply_appraisal_delta_clamps_to_bounds.

        SCOPE OF THE CLAMP (flagged, deliberately not implied to be
        system-wide): the clamp is applied HERE only. on_soul_tick's
        EMA_Decay does not clamp — it cannot leave [0, 1] given an in-range
        current value and the in-range baseline, so no clamp is needed there.
        initialize() does NOT clamp a restored snapshot: _is_valid_snapshot
        rejects only NaN, +/-inf, non-numeric values and bool, so an
        out-of-range persisted value (e.g. pleasure = 5.0) would be accepted
        as-is. Whether initialize() should additionally clamp or reject an
        out-of-range restore is a NEW open question for the architect (see
        requirements.md Open Questions), deliberately not resolved here.
        """
        self._require_initialized()

        self._pleasure = max(0.0, min(1.0, self._pleasure + delta.d_pleasure))
        self._arousal = max(0.0, min(1.0, self._arousal + delta.d_arousal))
        self._dominance = max(0.0, min(1.0, self._dominance + delta.d_dominance))
        self._last_applied_valence = delta.valence

    def get_pad_history(self) -> Tuple[PADSnapshot, ...]:
        """Implements Task 18. Returns an immutable Tuple[PADSnapshot, ...]
        copy of _history, in chronological order (oldest first). Since
        PADSnapshot is itself frozen and this returns a tuple (not the
        live deque), the caller (e.g. DMN) cannot mutate PADEngine's
        internal _history through the returned value. Not subject to the
        pre-initialize() guard — Task 9 and design.md's Error Handling
        section name only get_current_pad(), on_soul_tick(), and
        apply_appraisal_delta() for that guard; get_pad_history() is not
        among them."""
        return tuple(self._history)

