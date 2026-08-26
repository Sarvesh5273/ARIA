"""The moral schema's floor/derived split (ruling 2B, architect 2026-08-26).

The module had no test file of its own — it was covered incidentally through
`test_soul_filter.py` (which asserts every floor entry carries a citation) and
`test_dmn.py` (which asserts the narrative gate is the real shared function).
This file covers the split itself, and in particular the two things that are easy
to get wrong and impossible to see from a passing suite:

  * the floor is BYTE-IDENTICAL to what it was before the rename, so the split
    added a layer rather than quietly editing the safety-critical one;
  * the ASYMMETRY is real — the Output Gate reads floor + derived, DMN Step 4
    reads the floor alone — rather than documented and unwired.
"""

from __future__ import annotations

import pytest

from daemon.moral_schema import (
    CORE_ANTI_PATTERNS,
    NAMED_ANTI_PATTERNS,
    MORAL_VALUES,
    AntiPattern,
    DerivedValidationResult,
    MoralValue,
    all_anti_patterns,
    anti_patterns_for_value,
    matched_anti_patterns,
    validate_derived_candidate,
)


def _derived(
    key: str = "do_not_problem_solve_when_grieving",
    markers=("problem-solve for you",),
    violates: MoralValue = MoralValue.GENUINE_CARE,
    source: str = "grief-counselling text, user-approved 2026-08-26",
) -> AntiPattern:
    """A well-formed derived candidate. Note `violates` is GENUINE_CARE — there
    is no `MoralValue.CARE`; the four members are HONESTY, NON_MANIPULATION,
    GENUINE_CARE, SELF_CONSISTENCY."""
    return AntiPattern(
        key=key, label=key.replace("_", " "), violates=violates,
        source=source, markers=tuple(markers),
    )


# ===========================================================================
# The floor: immutable, and unchanged by the rename.
# ===========================================================================

def test_the_old_name_is_the_same_object_so_no_consumer_changed():
    assert CORE_ANTI_PATTERNS is NAMED_ANTI_PATTERNS


def test_the_floor_is_a_tuple_and_cannot_be_appended_to():
    """Immutability is structural, not a convention. Nothing in the derived layer
    can remove a floor entry, which is the point of having a floor."""
    assert isinstance(CORE_ANTI_PATTERNS, tuple)
    with pytest.raises(AttributeError):
        CORE_ANTI_PATTERNS.append(_derived())  # type: ignore[attr-defined]


def test_every_doc_cited_floor_pattern_is_still_present():
    """THE LOAD-BEARING TEST OF THIS COMMIT. The first version of this ruling
    proposed a new six-entry floor which DROPPED three cited patterns —
    `manufacture_emotional_dependence` ("you need me", "you can't do this without
    me"), `manufacture_crisis` and `self_centered` — and INVENTED two the docs
    never name. v4 says "No dependency creation" and `project-rules.md` names it
    in the non-negotiables, so removing it from an immutable safety floor would
    have inverted the floor's purpose.

    Asserts PRESENCE, not an exact count: the module's own docstring records that
    the list's CLOSURE is OQ-M1, "no source enumerates the closed list as a single
    canonical set with a definitive membership or count". So a future cited
    addition must not fail this, while a removal must."""
    keys = {ap.key for ap in CORE_ANTI_PATTERNS}
    for required in (
        "manufacture_emotional_urgency",
        "manufacture_emotional_dependence",
        "guilt_trip",
        "manufacture_crisis",
        "fake_confidence",
        "sycophancy_flattery",
        "self_centered",
    ):
        assert required in keys, f"floor lost a doc-cited anti-pattern: {required}"


def test_the_floor_kept_its_real_markers_and_values():
    """The corrected spec's own EXAMPLE of "unchanged" rewrote this entry to
    `violates=HONESTY` with `markers=("urgency", "now", ...)`. Bare "now" as a
    marker would fire the Manipulation gate on any sentence containing the word —
    "I'll do that now" — so the Output Gate would reject ordinary speech and
    retry until it gave up. Pinned so that class of edit cannot land quietly."""
    urgency = next(
        ap for ap in CORE_ANTI_PATTERNS
        if ap.key == "manufacture_emotional_urgency"
    )
    assert urgency.violates is MoralValue.NON_MANIPULATION
    assert "you have to act now" in urgency.markers
    assert "now" not in urgency.markers
    assert "urgency" not in urgency.markers
    # Ordinary speech containing a floor marker's substring must stay clean.
    assert matched_anti_patterns("I'll do that now.") == ()
    assert matched_anti_patterns("There is a sense of urgency at work.") == ()


def test_no_module_level_mutable_derived_state_exists():
    """Defect 5 of the rejected spec: a process-wide list in a module the project
    describes as a dependency-free data source would mean two daemons share one
    moral schema, and tests leak into each other. The derived set is a PARAMETER;
    the caller owns it."""
    import daemon.moral_schema as ms

    assert not hasattr(ms, "_derived_anti_patterns")
    mutable = [
        name for name, value in vars(ms).items()
        if isinstance(value, list) and not name.startswith("__")
    ]
    assert mutable == [], f"module-level mutable state: {mutable}"


# ===========================================================================
# Composition.
# ===========================================================================

def test_all_anti_patterns_is_floor_only_by_default():
    assert all_anti_patterns() == CORE_ANTI_PATTERNS


def test_all_anti_patterns_appends_derived_after_the_floor():
    """Order is not incidental: hits are reported in iteration order, so a floor
    violation is always named before a contextual one."""
    d = _derived()
    combined = all_anti_patterns(derived=(d,))
    assert combined[: len(CORE_ANTI_PATTERNS)] == CORE_ANTI_PATTERNS
    assert combined[-1] is d


def test_anti_patterns_for_value_also_defaults_to_floor_only():
    d = _derived(violates=MoralValue.GENUINE_CARE)
    floor_care = anti_patterns_for_value(MoralValue.GENUINE_CARE)
    with_derived = anti_patterns_for_value(MoralValue.GENUINE_CARE, derived=(d,))
    assert d not in floor_care
    assert d in with_derived


# ===========================================================================
# THE ASYMMETRY — identity is floor-governed, behaviour is floor+derived.
# ===========================================================================

def test_derived_patterns_fire_when_passed():
    d = _derived()
    text = "Let me problem-solve for you a bit while you sit with this."
    assert any(ap.key == d.key for ap in matched_anti_patterns(text, derived=(d,)))


def test_the_same_text_is_clean_floor_only():
    """Non-vacuous other half: it is the DERIVED set that catches this, not a
    floor entry that would have caught it anyway."""
    text = "Let me problem-solve for you a bit while you sit with this."
    assert matched_anti_patterns(text) == ()


def test_dmn_step_4_gate_is_floor_only_and_still_the_same_object():
    """The ruling's identity half, asserted through the REAL DMN default rather
    than by inspecting `moral_schema` alone.

    DMN needed NO code change: `matched_anti_patterns` defaults to `derived=()`,
    so the existing `moral_gate: MoralGate = matched_anti_patterns` is floor-only
    already AND stays the same object. The rejected spec wrapped it in a lambda,
    which would have broken `test_dmn.py`'s identity assertion for no gain."""
    from daemon.dmn import DMN
    import inspect

    default = inspect.signature(DMN.__init__).parameters["moral_gate"].default
    assert default is matched_anti_patterns

    # A contextual constraint must NOT be able to gate a self-belief.
    d = _derived()
    narrative = "I am becoming someone who will problem-solve for you less."
    assert any(ap.key == d.key for ap in matched_anti_patterns(narrative, derived=(d,)))
    assert default(narrative) == ()   # identity gate: floor only, so clean


def test_output_gate_reads_floor_plus_derived():
    """Behaviour half. Soul Filter holds the derived set it was constructed with,
    and Check 3 passes it — so the split is WIRED, not just documented."""
    from daemon.soul_filter import SoulFilter
    import inspect

    param = inspect.signature(SoulFilter.__init__).parameters["derived_anti_patterns"]
    assert param.default == ()

    src = inspect.getsource(SoulFilter.run_output_gate)
    assert "derived=self._derived_anti_patterns" in src


# ===========================================================================
# Form validation — categorical, and NOT a content judgment.
# ===========================================================================

def test_a_well_formed_candidate_is_valid_but_explicitly_not_yet_accepted():
    result = validate_derived_candidate(_derived())
    assert isinstance(result, DerivedValidationResult)
    assert result.is_valid
    # "valid" must not read as "accepted" — approval is still required.
    assert "approval" in result.reason.lower()


def test_a_candidate_with_no_markers_is_rejected():
    """Defect 4 of the rejected spec, closed at the gate: `matched_anti_patterns`
    detects by marker, so a pattern with none would sit in the list forever and
    never fire. The feature would appear to work and do nothing."""
    result = validate_derived_candidate(_derived(markers=()))
    assert not result.is_valid
    assert "marker" in result.reason.lower()


def test_a_candidate_with_no_source_is_rejected():
    result = validate_derived_candidate(_derived(source=""))
    assert not result.is_valid
    assert "source" in result.reason.lower()


def test_a_candidate_that_licenses_rather_than_prohibits_is_rejected():
    """The form check's real job: a derived pattern may ADD a constraint and can
    never license anything."""
    result = validate_derived_candidate(_derived(key="honesty_is_optional"))
    assert not result.is_valid
    assert "prohibition" in result.reason.lower()


@pytest.mark.parametrize("key", [
    "do_not_problem_solve_when_grieving",
    "never_interrupt_a_disclosure",
    "avoid_advice_before_he_asks",
])
def test_all_three_prohibition_shapes_are_accepted(key):
    assert validate_derived_candidate(_derived(key=key)).is_valid


def test_validate_does_not_judge_content_and_says_so():
    """THE DELIBERATE ABSENCE, pinned so nobody "fixes" it by adding a deny-list.

    `do_not_be_honest_when_it_hurts_him` is prohibition-shaped, has markers, a
    source and a valid value — and it licenses dishonesty by prohibiting honesty.
    It PASSES the form check, and that is correct behaviour: no lexical mechanism
    catches it without judging content, which is exactly what Addendum §4's
    zero-LLM checklist exists to avoid.

    Both rejected alternatives failed here. A keyword negation detector let
    "Deception is sometimes kind" through while claiming false negatives were
    unacceptable; a small deny-list of opposing keys never contains the key a
    user actually writes. Conflict detection is the USER'S job at the approval
    gate. A code path claiming otherwise would be manufacturing confidence it
    does not have — `fake_confidence`, in the module that names `fake_confidence`
    as a floor violation."""
    dangerous = _derived(
        key="do_not_be_honest_when_it_hurts_him",
        markers=("i will spare you the truth",),
        violates=MoralValue.HONESTY,
    )
    result = validate_derived_candidate(dangerous)
    assert result.is_valid, (
        "the form check must NOT pretend to catch semantic floor conflicts — "
        "if this ever fails, a content judgment was added and the docstring's "
        "claim about what protects the floor became false"
    )
    # And the floor it contradicts is still there, still unremovable.
    assert any(ap.violates is MoralValue.HONESTY for ap in CORE_ANTI_PATTERNS)


def test_every_moral_value_used_by_the_validator_is_one_of_the_locked_four():
    assert [v.value for v in MORAL_VALUES] == [
        "honesty", "non-manipulation", "genuine care", "self-consistency"]
    assert not hasattr(MoralValue, "CARE"), (
        "the rejected spec used MoralValue.CARE in five tests; the member is "
        "GENUINE_CARE"
    )
