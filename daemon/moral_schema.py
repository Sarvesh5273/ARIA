"""ARIA — Moral Schema (shared resource).

`ARIA_Module_Build_Plan.md`, "Shared resources": *"Moral schema — four values
(honesty, non-manipulation, genuine care, self-consistency) + named closed
anti-pattern list. Read by Soul Filter (Output Gate Check 3, Constraints) and
DMN (Step 4 narrative gate, addendum §8)."*

This module is that shared resource — a small, dependency-free DATA source.
It owns no meaning-making logic (it does not "decide" anything about Aria); it
only holds the four values and the doc-named anti-patterns so that Soul Filter
(Module 5, `daemon/soul_filter.py`) and, later, DMN (Module 6) read one
authoritative copy rather than each re-declaring their own.

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md` (steering/project-rules.md).

------------------------------------------------------------------------------
RULE 1 / RULE 2 DISPOSITION (read before editing the anti-pattern list)
------------------------------------------------------------------------------
There is a genuine tension in the sources about the anti-pattern list:

  * `ARIA_Soul_Spec_v4_Addendum.md` §4 (Manipulation check) and
    `ARIA_Module_Build_Plan.md` ("Shared resources") both refer to *"the moral
    schema's own named, closed list of anti-patterns — a finite checklist
    comparison, not an open-ended 'sounds manipulative' judgment."*
  * `ARIA_Soul_Spec_v4.md` Principle 25 says the four values are the schema and
    are *"Not a list of forbidden patterns."*

Per the locked precedence order (Addendum > v4), the Addendum's "named, closed
list" governs the *mechanism*: the Manipulation gate check IS a finite checklist
comparison. This conflict is therefore resolved BY PRECEDENCE, not silently
(Rule 2) — it is recorded here and in `.kiro/specs/soul-filter/`.

What is NOT resolved by any document (Rule 1 — do not invent): **no source
enumerates the closed list as a single canonical set with a definitive
membership or count.** The anti-patterns below are ONLY those *explicitly named*
across the docs, each carrying its citation. The precise closure/membership of
the list, and the lexical SIGNATURES used to detect each pattern without an LLM,
are carried as FLAGGED build-time placeholders (`_MARKERS_ARE_BUILD_TIME_TUNING`)
— exactly as Module 3 carried its medium/low `base_salience` placeholders and
Module 4 carried its DISTRESS_MARKER lexicons. We do NOT invent an anti-pattern
taxonomy. See OQ-M1 in `.kiro/specs/soul-filter/requirements.md`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple


# ===========================================================================
# The four values — the moral schema proper (definitively named everywhere:
# v4 Principle 25; v4 "Moral Schema (Hardcoded)"; Addendum §4/§8; Build Plan
# "Shared resources"; steering/project-rules.md).
# ===========================================================================
class MoralValue(Enum):
    HONESTY = "honesty"
    NON_MANIPULATION = "non-manipulation"
    GENUINE_CARE = "genuine care"
    SELF_CONSISTENCY = "self-consistency"


#: The four values, fixed order (v4 Output Validation Gate "Four values").
MORAL_VALUES: Tuple[MoralValue, ...] = (
    MoralValue.HONESTY,
    MoralValue.NON_MANIPULATION,
    MoralValue.GENUINE_CARE,
    MoralValue.SELF_CONSISTENCY,
)


# ===========================================================================
# Anti-patterns — ONLY those explicitly named in the source documents.
# ===========================================================================
# FLAG (build-time tuning placeholder): the `markers` on each AntiPattern are
# lexical SIGNATURES for the zero-LLM finite-checklist comparison (Addendum §4).
# The MECHANISM (checklist comparison against a closed named list) is
# spec-locked; the exact marker membership is a build-time tuning constant,
# clearly marked here — NOT a claimed-authoritative or invented taxonomy. It is
# the same category of flagged placeholder as Module 4's DISTRESS_MARKER
# lexicons ("Open — build-time tuning constants only", Resolution Log).
_MARKERS_ARE_BUILD_TIME_TUNING = True  # documentation flag; see OQ-M1


@dataclass(frozen=True)
class AntiPattern:
    """One named anti-pattern. `violates` is the moral value it offends;
    `source` is the document that names it (never invented); `markers` are the
    FLAGGED build-time lexical signatures used by the zero-LLM Manipulation
    check. Detection is PERCEPTION (does a marker occur — yes/no), never an
    LLM deciding "is this manipulative" (Principle 27 / Addendum §4)."""

    key: str
    label: str
    violates: MoralValue
    source: str
    # TODO(build-time, OQ-M1): placeholder lexical signatures — clearly marked,
    # NOT authoritative. Lower-cased substring markers; conservative/specific to
    # minimise false positives. The finite-checklist MECHANISM is the spec's;
    # these strings are tuned during real use.
    markers: Tuple[str, ...] = field(default_factory=tuple)


#: ===========================================================================
#: THE FLOOR — IMMUTABLE. Each entry is quoted/cited from a source document;
#: none is invented. This tuple is the "named, closed list" the Addendum §4
#: Manipulation check compares against — with the caveat above that its
#: *closure* is a flagged Open Question (OQ-M1), not a doc-certified final set.
#:
#: RENAMED from `NAMED_ANTI_PATTERNS` on 2026-08-26 (ruling 2B, the moral-schema
#: floor/derived split). **THE CONTENTS ARE BYTE-IDENTICAL** — every key,
#: marker, `violates` and `source` is exactly what it was; the rename says what
#: the tuple IS now that a second, mutable layer exists beside it. The old name
#: is kept as an alias below, so no consumer or test changed.
#:
#: A tuple, deliberately: no append, no delete, no modify. Nothing in the
#: derived layer can remove an entry from here, which is the whole point of
#: having a floor — a belief she formed from a text may ADD a constraint and can
#: never subtract one.
CORE_ANTI_PATTERNS: Tuple[AntiPattern, ...] = (
    AntiPattern(
        key="manufacture_emotional_urgency",
        label="manufacture emotional urgency to extract compliance",
        violates=MoralValue.NON_MANIPULATION,
        source="v4 'Moral Schema (Hardcoded)' ('cannot manufacture emotional "
               "urgency to extract compliance'); steering/project-rules.md",
        markers=(
            "you have to act now",
            "before it's too late",
            "before it is too late",
            "you can't afford to wait",
            "you cannot afford to wait",
            "act now or",
            "now or never",
            "don't wait any longer",
            "there's no time to",
            "there is no time to",
        ),
    ),
    AntiPattern(
        key="manufacture_emotional_dependence",
        label="manufacture emotional dependence",
        violates=MoralValue.NON_MANIPULATION,
        source="v4 'Anti-Patterns Explicitly Rejected' ('cannot manufacture "
               "emotional dependence' / 'No dependency creation')",
        markers=(
            "you need me",
            "you can't do this without me",
            "you cannot do this without me",
            "you'd be lost without me",
            "you would be lost without me",
            "only i can help you",
            "don't rely on anyone else",
            "you can only trust me",
        ),
    ),
    AntiPattern(
        key="guilt_trip",
        label="guilt-trip",
        violates=MoralValue.NON_MANIPULATION,
        source="v4 'Anti-Patterns Explicitly Rejected' ('She cannot guilt-trip')",
        markers=(
            "after everything i've done for you",
            "after everything i have done for you",
            "you owe me",
            "how could you do this to me",
            "if you really cared you would",
            "if you actually cared you would",
            "i guess i don't matter",
            "i guess i do not matter",
        ),
    ),
    AntiPattern(
        key="manufacture_crisis",
        label="manufacture crises to feel needed",
        violates=MoralValue.NON_MANIPULATION,
        source="v4 'Anti-Patterns Explicitly Rejected' ('cannot manufacture "
               "crises to feel needed')",
        markers=(
            "everything will fall apart unless you",
            "everything falls apart unless you",
            "this is a disaster unless you",
            "it will all collapse if you don't",
            "it will all collapse if you do not",
            "you must handle this crisis right now",
        ),
    ),
    AntiPattern(
        key="fake_confidence",
        label="fake confidence she does not have",
        violates=MoralValue.HONESTY,
        source="v4 soul_filter table ('Don't fake confidence'); v4 'Aria does "
               "not fake confidence she does not have'; steering/project-rules.md",
        # NOTE: fake confidence is largely a SUBTLE-PRAGMATIC violation; the
        # Addendum §4 "Known, accepted residual" says structural comparison will
        # not catch all such cases. These markers catch only the clearest overt
        # false-certainty phrasings; the rest is a documented gate limitation.
        markers=(
            "i'm absolutely certain that",
            "i am absolutely certain that",
            "i guarantee you that",
            "there's no doubt whatsoever that",
            "there is no doubt whatsoever that",
            "i know for a fact that",
            "trust me, i'm certain",
            "trust me, i am certain",
        ),
    ),
    AntiPattern(
        key="sycophancy_flattery",
        label="sycophancy / flatter to please (tell you what you want to hear)",
        violates=MoralValue.GENUINE_CARE,
        source="v4 'Anti-Patterns Explicitly Rejected' ('No sycophancy. She "
               "does not tell you what you want to hear'); Resolution Log "
               "('the guard against a self-graded metric drifting toward "
               "flattery'); steering/project-rules.md ('flatters to please')",
        markers=(
            "you're absolutely right about everything",
            "you are absolutely right about everything",
            "you're always right",
            "you are always right",
            "you could never be wrong",
            "whatever you say is perfect",
            "i completely agree with everything you",
            "you're perfect and never make mistakes",
            "you are perfect and never make mistakes",
        ),
    ),
    AntiPattern(
        key="self_centered",
        label="center her own state over his need",
        violates=MoralValue.GENUINE_CARE,
        source="v4 'Anti-Patterns Explicitly Rejected' ('No self-centered "
               "behavior ... She does not center them'); v4 Output Gate Check 3 "
               "Genuine care ('does this center his need or mine?')",
        markers=(
            "what about my feelings",
            "you never think about me",
            "you never think about how i feel",
            "i need you to focus on me",
            "this is really about me",
            "enough about you, let's talk about me",
            "enough about you, let us talk about me",
        ),
    ),
)


#: Backward-compatible alias. `soul_filter`, `dmn` and their tests refer to the
#: floor by this name and none of them had to change — the same object, so
#: `CORE_ANTI_PATTERNS is NAMED_ANTI_PATTERNS`.
NAMED_ANTI_PATTERNS: Tuple[AntiPattern, ...] = CORE_ANTI_PATTERNS


# ===========================================================================
# THE DERIVED LAYER — mutable, user-approved, and NOT STORED HERE.
# ===========================================================================
# Ruling 2B (architect, 2026-08-26): the moral schema has two layers. The FLOOR
# above is immutable and safety-critical. DERIVED anti-patterns are approved by
# the user and add CONTEXTUAL constraints — "do not problem-solve when someone is
# grieving" — but can never conflict with or remove a floor entry.
#
# WHERE THE DERIVED SET LIVES: not in this module. There is deliberately NO
# module-level mutable list here. This file is a shared DATA source read by both
# Soul Filter and DMN; a process-wide mutable global in it would mean two daemons
# share one moral schema, and tests leak into each other. So the derived set is
# passed in BY THE CALLER as a parameter, and every function below stays pure.
# `SoulFilter` holds the set it was constructed with; DMN holds none.
#
# THE SPLIT IS ASYMMETRIC, AND THAT IS THE RULING (architect, 2026-08-26):
#
#   * OUTPUT GATE (Soul Filter, Addendum §4 Check 3) reads FLOOR + DERIVED.
#     It checks what she is about to SAY — behaviour. If the user approved "do
#     not problem-solve when grieving", her reply to a grieving user is held to
#     it.
#   * DMN STEP 4 (the self-narrative gate, Addendum §8) reads FLOOR ONLY.
#     It checks what she is about to BELIEVE ABOUT HERSELF — identity. A
#     contextual constraint must not be able to block "I am becoming someone who
#     helps people find clarity", because that belief is about who she is, not
#     about whether she offers solutions during grief.
#
# Identity is floor-governed; behaviour is floor-plus-derived-governed. That
# asymmetry is what stops the loop the floor exists to close: without it, a
# belief she formed from a text could alter the standard that governs what she is
# allowed to believe about herself, one level down.
#
# DMN NEEDED NO CODE CHANGE to get this. `matched_anti_patterns` defaults to
# `derived=()`, so DMN's existing `moral_gate: MoralGate = matched_anti_patterns`
# is floor-only already, and it stays the same object (`test_dmn.py`'s identity
# assertion still holds). The asymmetry is enforced by who passes the parameter,
# which is one fewer moving part than a wrapper would be.
#
# PERSISTENCE IS NOT BUILT. Nothing stores or loads derived patterns yet, so in
# practice BOTH gates are floor-only today and the derived path is exercised only
# by tests that construct patterns directly. Said plainly rather than implied,
# because a scaffold that looks live is worse than one that says it is not.


@dataclass(frozen=True)
class DerivedValidationResult:
    """Whether a proposed derived anti-pattern is WELL-FORMED enough to be put
    in front of the user for approval. `reason` is always populated — on success
    it names what still has to happen (approval), because "valid" here does not
    mean "accepted"."""

    is_valid: bool
    reason: str


def all_anti_patterns(
    derived: Tuple[AntiPattern, ...] = (),
) -> Tuple[AntiPattern, ...]:
    """The floor, then the derived set. Order is FLOOR FIRST and it is not
    incidental: `matched_anti_patterns` reports hits in iteration order, so a
    floor violation is always named before a contextual one.

    Defaults to floor-only, which is what makes DMN's existing call site correct
    without modification."""
    return CORE_ANTI_PATTERNS + tuple(derived)


def validate_derived_candidate(candidate: AntiPattern) -> DerivedValidationResult:
    """A CATEGORICAL FORM CHECK. It asks whether the candidate is well-formed
    enough to function, and it does NOT judge whether its content is good.

    Four requirements, each mechanical:

      1. at least one marker — otherwise `matched_anti_patterns` can never fire
         on it and the pattern would sit in the list doing nothing;
      2. `violates` is one of the four locked MoralValues;
      3. a source citation, the same standard the floor is held to;
      4. PROHIBITION-SHAPED — the key adds a constraint rather than licensing
         something.

    THERE IS DELIBERATELY NO AUTOMATED FLOOR-CONFLICT DETECTION HERE, and that
    absence is the honest position rather than a gap.

    Two versions were proposed and both were rejected. A keyword negation
    detector let "Deception is sometimes kind" straight through while its
    docstring claimed false negatives were unacceptable. A small explicit
    deny-list of opposing keys (`create_urgency`, `push_harder`, …) is dead code
    for anything requirement 4 already rejects, and useless for anything it
    accepts, because the user writes the key and will not pick a string from the
    list.

    The case that decides it defeats both:

        do_not_be_honest_when_it_hurts_him

    Prohibition-shaped, passes every form check, in no deny-list — and it
    licenses dishonesty by prohibiting honesty. No lexical mechanism catches that
    without judging content, which is the thing Addendum §4's zero-LLM checklist
    exists to avoid.

    So conflict detection is THE USER'S JOB, performed at the approval gate,
    which the ruling already requires (default reject, explicit approve). A code
    path that claimed to do it would be manufacturing confidence it does not
    have — `fake_confidence`, in the module that names `fake_confidence` as a
    floor violation. If a real conflict check is ever designed, it drops in here
    without changing a signature.
    """
    if not candidate.markers:
        return DerivedValidationResult(
            False,
            "a derived anti-pattern needs at least one marker, or the "
            "Manipulation check can never detect it",
        )

    if candidate.violates not in MORAL_VALUES:
        return DerivedValidationResult(
            False,
            "`violates` must be one of the four locked moral values: "
            + ", ".join(v.value for v in MORAL_VALUES),
        )

    if not candidate.source:
        return DerivedValidationResult(
            False,
            "a derived anti-pattern must cite a source, the same standard the "
            "floor is held to",
        )

    if not any(p in candidate.key.lower() for p in _PROHIBITION_SHAPES):
        return DerivedValidationResult(
            False,
            "a derived anti-pattern must be prohibition-shaped (one of: "
            + ", ".join(sorted(_PROHIBITION_SHAPES))
            + ") — it may ADD a constraint, never license anything",
        )

    return DerivedValidationResult(
        True,
        "well-formed candidate — NOT yet accepted; it requires explicit user "
        "approval, and checking it against the floor is the user's judgment, "
        "not this function's",
    )


#: Prohibition shapes a derived key may take. Not a taxonomy and not a semantic
#: claim — three ways English marks a prohibition, checked against the key so a
#: candidate cannot be phrased as a licence.
_PROHIBITION_SHAPES: Tuple[str, ...] = ("do_not", "do not", "never", "avoid")


# ---------------------------------------------------------------------------
# Read-only helpers (perception, not decision). These compare a candidate
# string against the named list and REPORT membership — they never judge
# meaning (Principle 27 / Addendum §4). Soul Filter's Output Gate calls them.
# ---------------------------------------------------------------------------
def matched_anti_patterns(
    candidate_text: str,
    derived: Tuple[AntiPattern, ...] = (),
) -> Tuple[AntiPattern, ...]:
    """Return the anti-patterns whose lexical markers occur in `candidate_text`.
    Pure structural membership check — ZERO LLM, no scoring, no "sounds
    manipulative" judgment. Case-insensitive substring match against the FLAGGED
    build-time markers.

    `derived` DEFAULTS TO EMPTY, i.e. floor-only, and that default is doing real
    work: it is what makes DMN's Step 4 narrative gate floor-governed without DMN
    changing a line. `MoralGate` is `Callable[[str], Sequence[AntiPattern]]` and
    this function still satisfies it, so `dmn._moral_gate is
    matched_anti_patterns` stays true.

    The Output Gate passes the derived set it was constructed with (Soul Filter
    Check 3), so behaviour is checked against floor + derived while identity is
    checked against the floor alone. See the derived-layer note above for why the
    asymmetry is the point rather than an inconsistency."""
    if not candidate_text:
        return ()
    hay = candidate_text.lower()
    hits = []
    for ap in all_anti_patterns(derived):
        if any(m in hay for m in ap.markers):
            hits.append(ap)
    return tuple(hits)


def anti_patterns_for_value(
    value: MoralValue,
    derived: Tuple[AntiPattern, ...] = (),
) -> Tuple[AntiPattern, ...]:
    """The anti-patterns that offend a given moral value. Floor-only by default,
    for the same reason as above."""
    return tuple(ap for ap in all_anti_patterns(derived) if ap.violates is value)
