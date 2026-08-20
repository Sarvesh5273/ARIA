"""Unit tests for daemon/pad_engine.py — all 21 tasks (scaffold, Valence
enum, PADSnapshot, PADDelta, module constants, PADEngine.__init__/state
fields, initialize() including the restored_valence parameter,
the pre-initialize() RuntimeError guard, apply_appraisal_delta's addition
logic, on_soul_tick's full valence handling — NEGATIVE/POSITIVE/
VALENCE_UNCERTAIN decay (VALENCE_UNCERTAIN resolved to reuse
EMA_COEFFICIENT_NEGATIVE, per resolved former Open Question 3), the
NEUTRAL raise (Requirement 3's note, not an Open Question), the residual
restore-boundary raise (narrowed Open Question 4), and the baseline no-op
skip — the standalone EMA decay helper, get_current_pad, get_pad_history,
and API-surface tests) — plus Task 8 (the call-site conversion helper,
extended to also convert the persisted last_applied_valence string) and
Task 20 (the StateManager round-trip integration test that uses it).

Per Task 8/design.md's Restore/persist boundary section, the conversion
helpers below live outside both PADEngine's module and
daemon/state_manager.py — this test file is the "dedicated small wiring
function/test harness for this spec" Task 8 names as an acceptable
location. They are not added to daemon/pad_engine.py or to
daemon/state_manager.py.
"""

import dataclasses

import pytest

from daemon.pad_engine import (
    EMA_COEFFICIENT_NEGATIVE,
    EMA_COEFFICIENT_POSITIVE,
    PAD_BASELINE,
    PAD_HISTORY_LENGTH,
    PADDelta,
    PADEngine,
    PADSnapshot,
    Valence,
    _ema_decay,
)
from daemon.state_manager import PADState, StateManager


# ---------------------------------------------------------------------------
# Task 8 — call-site conversion helper (outside PADEngine, outside
# StateManager). Extended (not duplicated into a second helper) to also
# convert the persisted last_applied_valence string into Optional[Valence],
# per the narrowed Open Question 4 fix.
# ---------------------------------------------------------------------------

def _pad_state_to_snapshot(pad_state: PADState) -> PADSnapshot:
    """Converts a daemon.state_manager.PADState (as returned by
    StateManager.load_pad()) into a daemon.pad_engine.PADSnapshot (as
    accepted by PADEngine.initialize()), for use at the call site that
    wires PADEngine and StateManager together (e.g. Daemon's startup
    sequence). Neither PADEngine nor StateManager is modified to know
    about the other's type; this function is the only place that knows
    about both."""
    return PADSnapshot(
        pleasure=pad_state.pleasure,
        arousal=pad_state.arousal,
        dominance=pad_state.dominance,
    )


def _last_applied_valence_string_to_valence(value):
    """Converts the raw string (or None) daemon.state_manager.py's
    StateManager.load_last_applied_valence() returns into
    Optional[daemon.pad_engine.Valence], for use at the same call site
    that wires PADEngine and StateManager together, for passing into
    PADEngine.initialize()'s restored_valence parameter. This extends the
    existing PADState->PADSnapshot conversion helper's responsibility
    rather than duplicating it into a second helper function.

    Contract: if value is None, missing, or does not match any known
    Valence member's .value, returns None — never guesses a member."""
    if value is None:
        return None
    for member in Valence:
        if member.value == value:
            return member
    return None



# ---------------------------------------------------------------------------
# Task 2 — Valence enum has exactly four members, with these exact values
# ---------------------------------------------------------------------------

def test_valence_has_exactly_four_members():
    members = {member.name: member.value for member in Valence}
    assert members == {
        "POSITIVE": "positive",
        "NEGATIVE": "negative",
        "NEUTRAL": "neutral",
        "VALENCE_UNCERTAIN": "valence_uncertain",
    }
    assert len(Valence) == 4


# ---------------------------------------------------------------------------
# Task 4 — PADDelta is frozen (attempting to set an attribute after
# construction raises)
# ---------------------------------------------------------------------------

def test_pad_delta_is_frozen():
    delta = PADDelta(
        d_pleasure=0.1,
        d_arousal=-0.05,
        d_dominance=0.0,
        valence=Valence.POSITIVE,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        delta.d_pleasure = 0.9  # type: ignore[misc]


def test_pad_delta_default_origin_is_appraisal():
    delta = PADDelta(
        d_pleasure=0.0,
        d_arousal=0.0,
        d_dominance=0.0,
        valence=Valence.NEUTRAL,
    )
    assert delta.origin == "appraisal"


def test_pad_delta_accepts_aha_insight_origin():
    delta = PADDelta(
        d_pleasure=0.0,
        d_arousal=0.0,
        d_dominance=0.0,
        valence=Valence.NEUTRAL,
        origin="aha_insight",
    )
    assert delta.origin == "aha_insight"


# ---------------------------------------------------------------------------
# Task 3 — PADSnapshot is also frozen (same rationale as PADDelta)
# ---------------------------------------------------------------------------

def test_pad_snapshot_is_frozen():
    snap = PADSnapshot(pleasure=0.5, arousal=0.5, dominance=0.5)
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.pleasure = 0.9  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Task 5 — module constants have exactly the locked/placeholder values
# (simple equality checks, not property tests, per design.md's Testing
# Strategy "Explicitly not property-tested" note)
# ---------------------------------------------------------------------------

def test_pad_baseline_locked_value():
    assert PAD_BASELINE == PADSnapshot(pleasure=0.55, arousal=0.45, dominance=0.58)


def test_ema_coefficients_locked_values():
    assert EMA_COEFFICIENT_NEGATIVE == 0.6
    assert EMA_COEFFICIENT_POSITIVE == 0.75


def test_pad_history_length_placeholder_default():
    assert PAD_HISTORY_LENGTH == 50


# ---------------------------------------------------------------------------
# Task 7 — initialize(restored)
# ---------------------------------------------------------------------------

def test_initialize_none_falls_back_to_baseline():
    engine = PADEngine()
    engine.initialize(None)
    assert engine._pleasure == PAD_BASELINE.pleasure
    assert engine._arousal == PAD_BASELINE.arousal
    assert engine._dominance == PAD_BASELINE.dominance


def test_initialize_invalid_snapshot_falls_back_to_baseline():
    engine = PADEngine()
    invalid = PADSnapshot(pleasure=float("nan"), arousal=0.1, dominance=0.1)
    engine.initialize(invalid)
    assert engine._pleasure == PAD_BASELINE.pleasure
    assert engine._arousal == PAD_BASELINE.arousal
    assert engine._dominance == PAD_BASELINE.dominance


def test_initialize_valid_non_baseline_snapshot_is_used_exactly():
    engine = PADEngine()
    restored = PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2)
    engine.initialize(restored)
    assert engine._pleasure == restored.pleasure
    assert engine._arousal == restored.arousal
    assert engine._dominance == restored.dominance


# ---------------------------------------------------------------------------
# Task 7b — initialize()'s restored_valence parameter (fixes the routine
# case of the narrowed Open Question 4)
# ---------------------------------------------------------------------------

def test_initialize_with_restored_valence_does_not_raise_and_decays_correctly():
    engine = PADEngine()
    restored = PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2)
    engine.initialize(restored, restored_valence=Valence.NEGATIVE)

    # Does not raise (unlike the residual case with no restored_valence).
    engine.on_soul_tick()

    # Decays using NEGATIVE's coefficient, exactly as if that valence had
    # been supplied via a same-session apply_appraisal_delta call instead.
    comparison_engine = PADEngine()
    comparison_engine.initialize(restored)
    comparison_engine.apply_appraisal_delta(
        PADDelta(d_pleasure=0.0, d_arousal=0.0, d_dominance=0.0, valence=Valence.NEGATIVE)
    )
    comparison_engine.on_soul_tick()

    assert engine._pleasure == pytest.approx(comparison_engine._pleasure)
    assert engine._arousal == pytest.approx(comparison_engine._arousal)
    assert engine._dominance == pytest.approx(comparison_engine._dominance)


def test_initialize_without_restored_valence_preserves_old_behavior():
    # No restored_valence argument -> defaults to None -> on_soul_tick
    # still raises for the residual case, exactly as before Task 7b
    # existed (confirms the default preserves prior behavior).
    engine = PADEngine()
    engine.initialize(PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2))

    with pytest.raises(NotImplementedError):
        engine.on_soul_tick()


# ---------------------------------------------------------------------------
# Task 9 — pre-initialize() guard on get_current_pad(), on_soul_tick(), and
# apply_appraisal_delta()
# ---------------------------------------------------------------------------

def test_get_current_pad_raises_runtime_error_before_initialize():
    engine = PADEngine()
    with pytest.raises(RuntimeError):
        engine.get_current_pad()


def test_on_soul_tick_raises_runtime_error_before_initialize():
    engine = PADEngine()
    with pytest.raises(RuntimeError):
        engine.on_soul_tick()


def test_apply_appraisal_delta_raises_runtime_error_before_initialize():
    engine = PADEngine()
    delta = PADDelta(
        d_pleasure=0.0,
        d_arousal=0.0,
        d_dominance=0.0,
        valence=Valence.NEUTRAL,
    )
    with pytest.raises(RuntimeError):
        engine.apply_appraisal_delta(delta)


def test_no_runtime_error_from_any_method_after_initialize():
    engine = PADEngine()
    engine.initialize(None)

    # None of the three methods raises RuntimeError for this reason
    # anymore. on_soul_tick() here hits Task 16's no-op skip
    # (_last_applied_valence is None and PAD is exactly PAD_BASELINE),
    # which is a legitimate no-op, not a RuntimeError.
    engine.get_current_pad()
    engine.on_soul_tick()
    delta = PADDelta(
        d_pleasure=0.0,
        d_arousal=0.0,
        d_dominance=0.0,
        valence=Valence.NEUTRAL,
    )
    engine.apply_appraisal_delta(delta)


# ---------------------------------------------------------------------------
# Task 10 — apply_appraisal_delta(delta)
# ---------------------------------------------------------------------------

# NOTE: these two exercise the IN-RANGE path only, where addition and
# clamped addition coincide. The clamp itself is covered by
# test_apply_appraisal_delta_clamps_to_bounds below.

def test_apply_appraisal_delta_is_pure_addition_positive_magnitude():
    engine = PADEngine()
    restored = PADSnapshot(pleasure=0.2, arousal=0.3, dominance=0.4)
    engine.initialize(restored)

    delta = PADDelta(
        d_pleasure=0.1,
        d_arousal=0.05,
        d_dominance=0.02,
        valence=Valence.POSITIVE,
    )
    engine.apply_appraisal_delta(delta)

    assert engine._pleasure == pytest.approx(restored.pleasure + delta.d_pleasure)
    assert engine._arousal == pytest.approx(restored.arousal + delta.d_arousal)
    assert engine._dominance == pytest.approx(restored.dominance + delta.d_dominance)


def test_apply_appraisal_delta_is_pure_addition_negative_magnitude():
    engine = PADEngine()
    restored = PADSnapshot(pleasure=0.2, arousal=0.3, dominance=0.4)
    engine.initialize(restored)

    delta = PADDelta(
        d_pleasure=-0.15,
        d_arousal=-0.2,
        d_dominance=-0.01,
        valence=Valence.NEGATIVE,
    )
    engine.apply_appraisal_delta(delta)

    assert engine._pleasure == pytest.approx(restored.pleasure + delta.d_pleasure)
    assert engine._arousal == pytest.approx(restored.arousal + delta.d_arousal)
    assert engine._dominance == pytest.approx(restored.dominance + delta.d_dominance)


def test_apply_appraisal_delta_clamps_to_bounds():
    """Former Open Question 2, RESOLVED: PAD is bounded to [0.0, 1.0] and the
    clamp in apply_appraisal_delta is INTENTIONAL (physiological homeostasis),
    not accidental. Proven structurally: a delta that would overshoot the
    upper bound lands exactly on 1.0, a delta that would undershoot the lower
    bound lands exactly on 0.0, and an in-range delta is NOT clamped — so a
    broken implementation that always returned a bound could not pass."""
    # Upper bound: 0.9 + 0.5 = 1.4 -> clamped to exactly 1.0 on every axis.
    engine = PADEngine()
    engine.initialize(PADSnapshot(pleasure=0.9, arousal=0.9, dominance=0.9))
    engine.apply_appraisal_delta(
        PADDelta(d_pleasure=0.5, d_arousal=0.5, d_dominance=0.5,
                 valence=Valence.POSITIVE)
    )
    high = engine.get_current_pad()
    assert high.pleasure == 1.0
    assert high.arousal == 1.0
    assert high.dominance == 1.0

    # Lower bound: 0.1 - 0.5 = -0.4 -> clamped to exactly 0.0 on every axis.
    engine2 = PADEngine()
    engine2.initialize(PADSnapshot(pleasure=0.1, arousal=0.1, dominance=0.1))
    engine2.apply_appraisal_delta(
        PADDelta(d_pleasure=-0.5, d_arousal=-0.5, d_dominance=-0.5,
                 valence=Valence.NEGATIVE)
    )
    low = engine2.get_current_pad()
    assert low.pleasure == 0.0
    assert low.arousal == 0.0
    assert low.dominance == 0.0

    # An in-range delta is NOT clamped — the bound is a limit, not a coercion.
    engine3 = PADEngine()
    engine3.initialize(PADSnapshot(pleasure=0.5, arousal=0.5, dominance=0.5))
    engine3.apply_appraisal_delta(
        PADDelta(d_pleasure=0.2, d_arousal=-0.2, d_dominance=0.1,
                 valence=Valence.POSITIVE)
    )
    mid = engine3.get_current_pad()
    assert mid.pleasure == pytest.approx(0.7)
    assert mid.arousal == pytest.approx(0.3)
    assert mid.dominance == pytest.approx(0.6)


def test_apply_appraisal_delta_aha_insight_and_appraisal_origin_identical_outcome():
    engine_appraisal = PADEngine()
    engine_appraisal.initialize(PADSnapshot(pleasure=0.3, arousal=0.3, dominance=0.3))
    engine_aha = PADEngine()
    engine_aha.initialize(PADSnapshot(pleasure=0.3, arousal=0.3, dominance=0.3))

    delta_appraisal = PADDelta(
        d_pleasure=0.07,
        d_arousal=-0.02,
        d_dominance=0.01,
        valence=Valence.POSITIVE,
        origin="appraisal",
    )
    delta_aha = PADDelta(
        d_pleasure=0.07,
        d_arousal=-0.02,
        d_dominance=0.01,
        valence=Valence.POSITIVE,
        origin="aha_insight",
    )

    engine_appraisal.apply_appraisal_delta(delta_appraisal)
    engine_aha.apply_appraisal_delta(delta_aha)

    assert engine_appraisal._pleasure == engine_aha._pleasure
    assert engine_appraisal._arousal == engine_aha._arousal
    assert engine_appraisal._dominance == engine_aha._dominance


@pytest.mark.parametrize(
    "valence",
    [Valence.POSITIVE, Valence.NEGATIVE, Valence.NEUTRAL, Valence.VALENCE_UNCERTAIN],
)
def test_apply_appraisal_delta_sets_last_applied_valence(valence):
    engine = PADEngine()
    engine.initialize(None)

    delta = PADDelta(
        d_pleasure=0.0,
        d_arousal=0.0,
        d_dominance=0.0,
        valence=valence,
    )
    engine.apply_appraisal_delta(delta)

    assert engine._last_applied_valence is valence


# ---------------------------------------------------------------------------
# Task 12 — standard EMA decay helper
# ---------------------------------------------------------------------------

def test_ema_decay_hand_computed_negative_coefficient():
    # coefficient=0.6, baseline=0.55, current=0.2
    # new = 0.6 * 0.55 + 0.4 * 0.2 = 0.33 + 0.08 = 0.41
    result = _ema_decay(current=0.2, baseline=0.55, coefficient=0.6)
    assert result == pytest.approx(0.41)


def test_ema_decay_hand_computed_positive_coefficient():
    # coefficient=0.75, baseline=0.45, current=0.9
    # new = 0.75 * 0.45 + 0.25 * 0.9 = 0.3375 + 0.225 = 0.5625
    result = _ema_decay(current=0.9, baseline=0.45, coefficient=0.75)
    assert result == pytest.approx(0.5625)


# ---------------------------------------------------------------------------
# Task 11 — on_soul_tick() for POSITIVE and NEGATIVE cases only
# ---------------------------------------------------------------------------

def test_on_soul_tick_negative_moves_toward_baseline_strictly_between():
    engine = PADEngine()
    restored = PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2)
    engine.initialize(restored)
    engine.apply_appraisal_delta(
        PADDelta(d_pleasure=0.0, d_arousal=0.0, d_dominance=0.0, valence=Valence.NEGATIVE)
    )

    engine.on_soul_tick()

    for value, base, start in (
        (engine._pleasure, PAD_BASELINE.pleasure, restored.pleasure),
        (engine._arousal, PAD_BASELINE.arousal, restored.arousal),
        (engine._dominance, PAD_BASELINE.dominance, restored.dominance),
    ):
        if base != start:
            lo, hi = (start, base) if start < base else (base, start)
            assert lo < value < hi
        else:
            assert value == base


def test_on_soul_tick_positive_moves_toward_baseline_strictly_between():
    engine = PADEngine()
    restored = PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2)
    engine.initialize(restored)
    engine.apply_appraisal_delta(
        PADDelta(d_pleasure=0.0, d_arousal=0.0, d_dominance=0.0, valence=Valence.POSITIVE)
    )

    engine.on_soul_tick()

    for value, base, start in (
        (engine._pleasure, PAD_BASELINE.pleasure, restored.pleasure),
        (engine._arousal, PAD_BASELINE.arousal, restored.arousal),
        (engine._dominance, PAD_BASELINE.dominance, restored.dominance),
    ):
        if base != start:
            lo, hi = (start, base) if start < base else (base, start)
            assert lo < value < hi
        else:
            assert value == base


def test_on_soul_tick_same_coefficient_applied_uniformly_across_dimensions():
    engine = PADEngine()
    restored = PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2)
    engine.initialize(restored)
    engine.apply_appraisal_delta(
        PADDelta(d_pleasure=0.0, d_arousal=0.0, d_dominance=0.0, valence=Valence.NEGATIVE)
    )

    engine.on_soul_tick()

    # Derive the implied coefficient from each dimension's pre/post values
    # and baseline; all three must agree (this is the property that would
    # have caught a per-dimension-movement interpretation).
    def implied_coefficient(post, base, pre):
        return (post - pre) / (base - pre)

    coeff_p = implied_coefficient(engine._pleasure, PAD_BASELINE.pleasure, restored.pleasure)
    coeff_a = implied_coefficient(engine._arousal, PAD_BASELINE.arousal, restored.arousal)
    coeff_d = implied_coefficient(engine._dominance, PAD_BASELINE.dominance, restored.dominance)

    assert coeff_p == pytest.approx(EMA_COEFFICIENT_NEGATIVE)
    assert coeff_a == pytest.approx(EMA_COEFFICIENT_NEGATIVE)
    assert coeff_d == pytest.approx(EMA_COEFFICIENT_NEGATIVE)


def test_on_soul_tick_appends_exactly_one_history_entry():
    engine = PADEngine()
    engine.initialize(PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2))
    engine.apply_appraisal_delta(
        PADDelta(d_pleasure=0.0, d_arousal=0.0, d_dominance=0.0, valence=Valence.POSITIVE)
    )

    assert len(engine._history) == 0
    engine.on_soul_tick()
    assert len(engine._history) == 1

    expected = PADSnapshot(
        pleasure=engine._pleasure,
        arousal=engine._arousal,
        dominance=engine._dominance,
    )
    assert engine._history[-1] == expected


# ---------------------------------------------------------------------------
# Task 13 — on_soul_tick() NEUTRAL case: raises NotImplementedError,
# NOT an Open Question
# ---------------------------------------------------------------------------

def test_on_soul_tick_neutral_raises_not_implemented_error():
    engine = PADEngine()
    engine.initialize(None)
    engine.apply_appraisal_delta(
        PADDelta(d_pleasure=0.0, d_arousal=0.0, d_dominance=0.0, valence=Valence.NEUTRAL)
    )

    with pytest.raises(NotImplementedError):
        engine.on_soul_tick()

    assert len(engine._history) == 0


def test_on_soul_tick_neutral_message_differs_from_residual_restore_boundary():
    # Renamed from test_on_soul_tick_neutral_message_differs_from_task_14_and_15:
    # VALENCE_UNCERTAIN (formerly "Task 14") no longer raises at all (resolved
    # Open Question 3 — decays like NEGATIVE instead), so it is no longer part
    # of this NotImplementedError-message-distinctness comparison. Only NEUTRAL
    # (Task 13) and the residual restore-boundary case (Task 15) still raise.
    engine = PADEngine()
    engine.initialize(None)
    engine.apply_appraisal_delta(
        PADDelta(d_pleasure=0.0, d_arousal=0.0, d_dominance=0.0, valence=Valence.NEUTRAL)
    )
    with pytest.raises(NotImplementedError) as neutral_exc:
        engine.on_soul_tick()

    engine2 = PADEngine()
    engine2.initialize(PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2))
    with pytest.raises(NotImplementedError) as restore_exc:
        engine2.on_soul_tick()

    assert str(neutral_exc.value) != str(restore_exc.value)


# ---------------------------------------------------------------------------
# Task 14 — on_soul_tick() VALENCE_UNCERTAIN case: RESOLVED (former Open
# Question 3) — decays identically to NEGATIVE, does NOT raise
# ---------------------------------------------------------------------------
# REMOVED: test_on_soul_tick_valence_uncertain_raises_not_implemented_error
# and test_on_soul_tick_valence_uncertain_message_differs_from_task_13_and_15
# (both previously here) — they asserted VALENCE_UNCERTAIN raises
# NotImplementedError, which is no longer true now that former Open
# Question 3 is resolved (VALENCE_UNCERTAIN reuses EMA_COEFFICIENT_NEGATIVE
# instead of raising). Replaced by the tests below, which assert the new,
# correct behavior instead of re-testing around a stale one.

def test_on_soul_tick_valence_uncertain_decays_identically_to_negative():
    delta_kwargs = dict(d_pleasure=0.03, d_arousal=-0.04, d_dominance=0.01)

    engine_negative = PADEngine()
    engine_negative.initialize(PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2))
    engine_negative.apply_appraisal_delta(PADDelta(**delta_kwargs, valence=Valence.NEGATIVE))
    engine_negative.on_soul_tick()

    engine_uncertain = PADEngine()
    engine_uncertain.initialize(PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2))
    engine_uncertain.apply_appraisal_delta(
        PADDelta(**delta_kwargs, valence=Valence.VALENCE_UNCERTAIN)
    )
    engine_uncertain.on_soul_tick()

    assert engine_uncertain._pleasure == pytest.approx(engine_negative._pleasure)
    assert engine_uncertain._arousal == pytest.approx(engine_negative._arousal)
    assert engine_uncertain._dominance == pytest.approx(engine_negative._dominance)


def test_on_soul_tick_valence_uncertain_does_not_raise_and_appends_history():
    engine = PADEngine()
    engine.initialize(PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2))
    engine.apply_appraisal_delta(
        PADDelta(
            d_pleasure=0.0,
            d_arousal=0.0,
            d_dominance=0.0,
            valence=Valence.VALENCE_UNCERTAIN,
        )
    )

    assert len(engine._history) == 0
    engine.on_soul_tick()  # must not raise
    assert len(engine._history) == 1

    expected = PADSnapshot(
        pleasure=engine._pleasure,
        arousal=engine._arousal,
        dominance=engine._dominance,
    )
    assert engine._history[-1] == expected


# ---------------------------------------------------------------------------
# Task 15 — on_soul_tick() residual restore-boundary case
# (_last_applied_valence is None AND current PAD != PAD_BASELINE): raises
# NotImplementedError. This is the NARROWED Open Question 4 — unchanged
# trigger condition/message, now expected to be rare rather than routine
# (see Task 7b tests below for the routine, non-raising case).
# ---------------------------------------------------------------------------

def test_on_soul_tick_restore_boundary_raises_not_implemented_error():
    engine = PADEngine()
    restored = PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2)
    engine.initialize(restored)

    with pytest.raises(NotImplementedError):
        engine.on_soul_tick()

    # Current PAD is unchanged (still exactly the restored value) and
    # _history gained no entry.
    assert engine._pleasure == restored.pleasure
    assert engine._arousal == restored.arousal
    assert engine._dominance == restored.dominance
    assert len(engine._history) == 0


def test_on_soul_tick_restore_boundary_message_differs_from_neutral():
    # Renamed from test_on_soul_tick_restore_boundary_message_differs_from_task_13_and_14:
    # VALENCE_UNCERTAIN (formerly "Task 14") no longer raises at all, so it
    # is no longer part of this comparison. Only NEUTRAL (Task 13) and this
    # residual restore-boundary case (Task 15) still raise.
    engine = PADEngine()
    engine.initialize(PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2))
    with pytest.raises(NotImplementedError) as restore_exc:
        engine.on_soul_tick()

    engine2 = PADEngine()
    engine2.initialize(None)
    engine2.apply_appraisal_delta(
        PADDelta(d_pleasure=0.0, d_arousal=0.0, d_dominance=0.0, valence=Valence.NEUTRAL)
    )
    with pytest.raises(NotImplementedError) as neutral_exc:
        engine2.on_soul_tick()

    assert str(restore_exc.value) != str(neutral_exc.value)


# ---------------------------------------------------------------------------
# Task 16 — on_soul_tick() None-at-baseline case: no-op skip
# ---------------------------------------------------------------------------

def test_on_soul_tick_none_at_baseline_is_no_op_and_appends_history():
    engine = PADEngine()
    engine.initialize(None)  # baseline, no restore, no delta applied yet

    engine.on_soul_tick()

    assert engine._pleasure == PAD_BASELINE.pleasure
    assert engine._arousal == PAD_BASELINE.arousal
    assert engine._dominance == PAD_BASELINE.dominance
    assert len(engine._history) == 1
    assert engine._history[-1] == PAD_BASELINE


# ---------------------------------------------------------------------------
# Task 17 — get_current_pad()
# ---------------------------------------------------------------------------

def test_get_current_pad_matches_internal_values_after_initialize():
    engine = PADEngine()
    restored = PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2)
    engine.initialize(restored)

    snap = engine.get_current_pad()

    assert snap == PADSnapshot(
        pleasure=engine._pleasure,
        arousal=engine._arousal,
        dominance=engine._dominance,
    )


def test_get_current_pad_matches_internal_values_after_decay_or_delta_call():
    engine = PADEngine()
    engine.initialize(PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2))
    engine.apply_appraisal_delta(
        PADDelta(d_pleasure=0.0, d_arousal=0.0, d_dominance=0.0, valence=Valence.NEGATIVE)
    )
    engine.on_soul_tick()

    snap = engine.get_current_pad()

    assert snap == PADSnapshot(
        pleasure=engine._pleasure,
        arousal=engine._arousal,
        dominance=engine._dominance,
    )


# ---------------------------------------------------------------------------
# Task 18 — get_pad_history()
# ---------------------------------------------------------------------------

def test_get_pad_history_length_below_max_and_chronological_order():
    engine = PADEngine()
    engine.initialize(PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2))
    engine.apply_appraisal_delta(
        PADDelta(d_pleasure=0.0, d_arousal=0.0, d_dominance=0.0, valence=Valence.NEGATIVE)
    )

    recorded = []
    for _ in range(3):
        engine.on_soul_tick()
        engine.apply_appraisal_delta(
            PADDelta(d_pleasure=0.0, d_arousal=0.0, d_dominance=0.0, valence=Valence.NEGATIVE)
        )
        recorded.append(
            PADSnapshot(
                pleasure=engine._pleasure,
                arousal=engine._arousal,
                dominance=engine._dominance,
            )
        )

    history = engine.get_pad_history()
    assert len(history) == 3
    assert history == tuple(recorded)


def test_get_pad_history_bounded_at_pad_history_length_oldest_evicted_first():
    engine = PADEngine()
    engine.initialize(PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2))
    engine.apply_appraisal_delta(
        PADDelta(d_pleasure=0.0, d_arousal=0.0, d_dominance=0.0, valence=Valence.NEGATIVE)
    )

    n = PAD_HISTORY_LENGTH + 5
    recorded = []
    for _ in range(n):
        engine.on_soul_tick()
        engine.apply_appraisal_delta(
            PADDelta(d_pleasure=0.0, d_arousal=0.0, d_dominance=0.0, valence=Valence.NEGATIVE)
        )
        recorded.append(
            PADSnapshot(
                pleasure=engine._pleasure,
                arousal=engine._arousal,
                dominance=engine._dominance,
            )
        )

    history = engine.get_pad_history()
    assert len(history) == PAD_HISTORY_LENGTH
    assert history == tuple(recorded[-PAD_HISTORY_LENGTH:])


def test_get_pad_history_returned_tuple_cannot_mutate_internal_history():
    engine = PADEngine()
    engine.initialize(PADSnapshot(pleasure=0.1, arousal=0.9, dominance=0.2))
    engine.apply_appraisal_delta(
        PADDelta(d_pleasure=0.0, d_arousal=0.0, d_dominance=0.0, valence=Valence.NEGATIVE)
    )
    engine.on_soul_tick()

    history = engine.get_pad_history()
    assert isinstance(history, tuple)

    # Tuples themselves are immutable (no item assignment possible); this
    # asserts that mutation attempts on the returned value are rejected by
    # the language, and that its elements (frozen PADSnapshots) are
    # likewise immutable, so nothing about the returned value can be used
    # to alter it.
    with pytest.raises(TypeError):
        history[0] = PADSnapshot(pleasure=0.0, arousal=0.0, dominance=0.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        history[0].pleasure = 0.0  # type: ignore[misc]

    # A second call to get_pad_history() is unaffected and still reflects
    # PADEngine's real internal history.
    history_again = engine.get_pad_history()
    assert history_again == history


# ---------------------------------------------------------------------------
# Task 19 — API-surface tests: no direct-assignment surface, structural
# rejection of out-of-contract inputs
# ---------------------------------------------------------------------------

def test_pad_engine_public_method_list_is_exactly_the_documented_set():
    public_methods = {
        name
        for name in dir(PADEngine)
        if not name.startswith("_") and callable(getattr(PADEngine, name))
    }
    assert public_methods == {
        "initialize",
        "apply_appraisal_delta",
        "on_soul_tick",
        "get_current_pad",
        "get_pad_history",
    }


def test_pad_engine_has_no_setter_for_pleasure_arousal_dominance():
    public_methods = {
        name
        for name in dir(PADEngine)
        if not name.startswith("_") and callable(getattr(PADEngine, name))
    }
    forbidden = {"set_pleasure", "set_arousal", "set_dominance"}
    assert public_methods.isdisjoint(forbidden)


def test_no_method_accepts_needs_pressure_f4_or_barge_in_signature():
    import inspect

    forbidden_param_names = {
        "needs_pressure",
        "needs_system_pressure",
        "f4",
        "f4_signal",
        "barge_in",
        "barge_in_signal",
        "interrupt_signal",
    }
    public_methods = [
        name
        for name in dir(PADEngine)
        if not name.startswith("_") and callable(getattr(PADEngine, name))
    ]
    for name in public_methods:
        method = getattr(PADEngine, name)
        params = set(inspect.signature(method).parameters) - {"self"}
        assert params.isdisjoint(forbidden_param_names)


# ---------------------------------------------------------------------------
# Task 8 (test) — conversion function returns a PADSnapshot with matching
# pleasure/arousal/dominance values, given a representative PADState;
# extended helper converts the persisted last_applied_valence string
# ---------------------------------------------------------------------------

def test_pad_state_to_snapshot_matches_fields():
    pad_state = PADState(pleasure=0.12, arousal=0.34, dominance=0.56)
    snapshot = _pad_state_to_snapshot(pad_state)

    assert isinstance(snapshot, PADSnapshot)
    assert snapshot.pleasure == pad_state.pleasure
    assert snapshot.arousal == pad_state.arousal
    assert snapshot.dominance == pad_state.dominance


def test_last_applied_valence_string_to_valence_matches_known_member():
    assert _last_applied_valence_string_to_valence("negative") is Valence.NEGATIVE
    assert _last_applied_valence_string_to_valence("positive") is Valence.POSITIVE
    assert _last_applied_valence_string_to_valence("neutral") is Valence.NEUTRAL
    assert (
        _last_applied_valence_string_to_valence("valence_uncertain")
        is Valence.VALENCE_UNCERTAIN
    )


def test_last_applied_valence_string_to_valence_none_returns_none():
    assert _last_applied_valence_string_to_valence(None) is None


def test_last_applied_valence_string_to_valence_unknown_string_returns_none():
    # Corrupted/unrecognized field -> None, never a guessed member.
    assert _last_applied_valence_string_to_valence("some_corrupted_value") is None
    assert _last_applied_valence_string_to_valence("") is None


# ---------------------------------------------------------------------------
# Task 20 — StateManager round-trip integration test, using the Task 8
# conversion helper (not any conversion logic inside PADEngine or
# StateManager)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "pleasure, arousal, dominance",
    [
        (0.55, 0.45, 0.58),  # baseline-equal example
        (0.1, 0.9, 0.2),  # non-baseline example
        (0.0, 1.0, 0.5),  # boundary-ish example
    ],
)
def test_state_manager_round_trip_preserves_pad_values(tmp_path, pleasure, arousal, dominance):
    state_manager = StateManager(state_dir=tmp_path)

    engine = PADEngine()
    engine.initialize(PADSnapshot(pleasure=pleasure, arousal=arousal, dominance=dominance))
    original = engine.get_current_pad()

    state_manager.save_pad(
        PADState(pleasure=original.pleasure, arousal=original.arousal, dominance=original.dominance)
    )

    loaded_pad_state = state_manager.load_pad()
    restored_snapshot = _pad_state_to_snapshot(loaded_pad_state)

    new_engine = PADEngine()
    new_engine.initialize(restored_snapshot)

    assert new_engine.get_current_pad() == original
