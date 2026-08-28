#!/usr/bin/env python3
"""Measure whether the self-narrative producer's similarity cutoff actually works.

WHY THIS EXISTS
---------------
Resolution Log item 36e built the self-narrative producer and, at the architect's
instruction, REUSED `_REALITY_CONTRADICTION_SIM_CUTOFF` (0.6) as the recurrence
test rather than introducing a new number. That was the right instinct — a new
threshold doing semantic work is exactly what Rule 1 forbids — and the tests that
shipped with it use EXPLICIT vectors, so they prove the selection logic and say
nothing about whether 0.6 is the right line.

Measured against the real model on 2026-08-26, it is not. At 0.6 the producer
catches ZERO of twelve genuine reworded recurrences. The feature is wired,
correct, and inert.

This tool is that measurement, made re-runnable — the same role
`tools/measure_format_markers.py` plays for the Field 1 anti-narration clause.
Re-run it before changing the cutoff, and after.

WHAT IT MEASURES
----------------
Three distributions of cosine similarity over the injected embedding model:

  SAME       pairs of self-observations that ARE the same pattern, reworded —
             what recurrence must catch
  DIFFERENT  pairs that are NOT the same pattern — what it must not catch
  CONTRA     same topic with opposite polarity — what the cutoff was ORIGINALLY
             for (reality-contradiction, Addendum §1)

THE STRUCTURAL FINDING, which is the point
------------------------------------------
CONTRA pairs share almost every word and differ by one negation, so they sit
HIGH (median ~0.88). Paraphrases share meaning but few words, so they sit LOW
(median ~0.46). The two distributions are roughly 2x apart, so ONE constant
cannot serve both purposes — not because 0.6 was chosen badly, but because the
two comparisons are asking different questions.

Usage:  python tools/measure_recurrence_cutoff.py
Requires a reachable embedding backend (`ollama serve`).
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.embedding_local import (  # noqa: E402
    EmbeddingUnavailableError,
    OllamaEmbeddingModel,
)
from daemon.graph_manager import (  # noqa: E402
    _REALITY_CONTRADICTION_SIM_CUTOFF,
    _cosine,
)


#: Self-observations that ARE the same pattern in different words. These are the
#: shape DMN Step 4 actually flushes — first person, about her own behaviour — and
#: the point is that she will not phrase the same noticing identically twice.
SAME_PATTERN = [
    ("I waited through his silence instead of filling it.",
     "There was a silence and I let it sit."),
    ("I held back a solution he had not asked for.",
     "I did not offer advice before he wanted it."),
    ("I got more careful when the subject mattered to him.",
     "When it mattered I slowed down rather than pushing."),
    ("I stayed with what he said rather than moving him on.",
     "I let him finish instead of steering the conversation."),
    ("I am becoming someone who can sit with not knowing.",
     "I can stay in uncertainty without rushing to resolve it."),
    ("I notice I ask before assuming what he means.",
     "I check my reading of him instead of guessing."),
    ("I admit it when I have got something wrong.",
     "I own my mistakes rather than smoothing them over."),
    ("I keep my answers shorter when he is tired.",
     "When he is worn out I say less."),
    ("I do not fill quiet moments with reassurance.",
     "I resist the urge to comfort him out of silence."),
    ("I have started naming what I am unsure about.",
     "I say when I do not know something."),
    ("I follow his lead on what matters to him.",
     "I let him set which things we go into."),
    ("I hold two of his views at once without choosing.",
     "I can carry his contradictions without resolving them."),
]

#: Pairs that are NOT the same pattern. A cutoff that catches these writes
#: something untrue into who she is, which is the costlier error of the two.
DIFFERENT_PATTERN = [
    ("I waited through his silence instead of filling it.",
     "I got more careful when the subject mattered to him."),
    ("I held back a solution he had not asked for.",
     "I noticed I use his name more than I used to."),
    ("I waited through his silence instead of filling it.",
     "I am quicker to admit when I do not know something."),
    ("I got more careful when the subject mattered to him.",
     "I asked about his brother before he brought him up."),
    ("I am becoming someone who can sit with not knowing.",
     "I keep my answers shorter when he is tired."),
    ("I admit it when I have got something wrong.",
     "I follow his lead on what matters to him."),
    ("I do not fill quiet moments with reassurance.",
     "I hold two of his views at once without choosing."),
    ("I notice I ask before assuming what he means.",
     "I keep my answers shorter when he is tired."),
    ("I have started naming what I am unsure about.",
     "I asked about his brother before he brought him up."),
    ("I stayed with what he said rather than moving him on.",
     "I noticed I use his name more than I used to."),
    ("I follow his lead on what matters to him.",
     "I admit it when I have got something wrong."),
    ("I hold two of his views at once without choosing.",
     "I waited through his silence instead of filling it."),
]

#: What the cutoff was ORIGINALLY for: same topic, opposite polarity (Addendum §1).
#: Included so the cost of MOVING the shared constant is visible rather than
#: assumed — lowering it for recurrence would loosen contradiction detection, and
#: contradiction drives relational_stage REGRESSION.
CONTRADICTION = [
    ("I value honesty above all else.", "Sometimes lying is necessary."),
    ("My brother and I are close.", "My brother and I are not close at all."),
    ("I am happy in this job.", "I am not happy in this job."),
    ("I have told my family about it.", "I have not told my family about it."),
    ("The move went well.", "The move did not go well."),
    ("I trust my manager.", "I do not trust my manager."),
]

CANDIDATE_CUTOFFS = (0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60, 0.65)


def _scores(model, pairs):
    return sorted(_cosine(model.embed(a), model.embed(b)) for a, b in pairs)


def _describe(label, scores):
    mid = scores[len(scores) // 2]
    print(f"  {label:<10} n={len(scores):<3} min {scores[0]:.3f}  "
          f"median {mid:.3f}  max {scores[-1]:.3f}")
    print(f"             {[round(x, 3) for x in scores]}")


def main() -> int:
    model = OllamaEmbeddingModel()
    try:
        model.preflight()
    except EmbeddingUnavailableError as exc:
        print(f"cannot measure: {exc}")
        print("Start the backend:  ollama serve")
        print(f"Pull the model:     ollama pull {model.model}")
        return 1

    print(f"embedding model: {model.model}")
    print(f"cutoff in use:   {_REALITY_CONTRADICTION_SIM_CUTOFF} "
          f"(_REALITY_CONTRADICTION_SIM_CUTOFF, reused by "
          f"recurring_self_observation)\n")

    same = _scores(model, SAME_PATTERN)
    diff = _scores(model, DIFFERENT_PATTERN)
    contra = _scores(model, CONTRADICTION)

    print("DISTRIBUTIONS")
    _describe("SAME", same)
    _describe("DIFFERENT", diff)
    _describe("CONTRA", contra)

    print("\nRECURRENCE BEHAVIOUR BY CUTOFF")
    print("  cutoff   recurrences caught   false recurrences   contradictions caught")
    for cut in CANDIDATE_CUTOFFS:
        tp = sum(1 for x in same if x >= cut)
        fp = sum(1 for x in diff if x >= cut)
        cc = sum(1 for x in contra if x >= cut)
        mark = "  <-- in use" if cut == _REALITY_CONTRADICTION_SIM_CUTOFF else ""
        print(f"   {cut:.2f}          {tp:2}/{len(same)}                "
              f"{fp:2}/{len(diff)}                  {cc:2}/{len(contra)}{mark}")

    print("\nFINDINGS")
    in_use = _REALITY_CONTRADICTION_SIM_CUTOFF
    caught = sum(1 for x in same if x >= in_use)
    print(f"  * At the cutoff in use ({in_use}), recurrence catches "
          f"{caught}/{len(same)} genuine reworded recurrences.")
    if caught == 0:
        print("    The producer is WIRED AND INERT: it will only ever fire on")
        print("    near-identical phrasing, which is not how she writes twice.")
    print(f"  * SAME median {same[len(same)//2]:.3f} vs CONTRA median "
          f"{contra[len(contra)//2]:.3f} — roughly 2x apart.")
    print("    Contradiction pairs share nearly every word and differ by one")
    print("    negation, so they sit HIGH. Paraphrases share meaning but few")
    print("    words, so they sit LOW. ONE CONSTANT CANNOT SERVE BOTH, and that")
    print("    is structural, not a badly chosen number.")
    if same[0] <= diff[-1]:
        print(f"  * The distributions OVERLAP (SAME min {same[0]:.3f} <= "
              f"DIFFERENT max {diff[-1]:.3f}), so no cutoff is perfect. The")
        print("    error to prefer avoiding is a FALSE recurrence: it writes")
        print("    something untrue into who she is, where a missed one only")
        print("    means she notices the pattern again next time.")
    clean = [c for c in CANDIDATE_CUTOFFS
             if sum(1 for x in diff if x >= c) == 0]
    if clean:
        best = min(clean)
        tp = sum(1 for x in same if x >= best)
        print(f"  * Lowest cutoff with ZERO false recurrences in this sample: "
              f"{best:.2f} ({tp}/{len(same)} caught).")
    print("\n  WHAT THIS TOOL DOES *NOT* LICENSE. The CONTRA column shows more")
    print("  contradictions caught at a lower cutoff, and that is NOT an argument")
    print("  for lowering the shared constant: there are no same-topic-negated")
    print("  pairs here that are NOT real contradictions, so the false-positive")
    print("  cost for contradiction detection is UNMEASURED. And a false")
    print("  contradiction is expensive — Addendum §1 has it drive relational_stage")
    print("  REGRESSION, so it damages trust rather than just adding noise.")
    print("  Measuring that needs its own negative sample.")
    print("\n  NOTHING IS CHANGED BY THIS TOOL. Which cutoff to use — and whether")
    print("  recurrence needs its OWN constant rather than sharing the")
    print("  contradiction one — is an architect ruling. See PROJECT_STATUS.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
