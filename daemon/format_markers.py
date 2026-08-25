"""ARIA — Format markers (shared resource).

ONE pattern for "this text is FORMATTED rather than spoken prose", read by
everything that needs it. Same category of file as `daemon/moral_schema.py`: a
small, dependency-free shared resource, not a Module. It owns no meaning and
decides nothing — it answers "does this text carry stage-direction syntax" and
"what does it look like with that syntax removed", both purely lexically.

WHY IT LIVES IN `daemon/` AND NOT IN THE ADAPTER THAT FIRST NEEDED IT
---------------------------------------------------------------------
It began in `adapters/audio_tts.py`, because Resolution Log item 25 ruled that
markers are stripped where text becomes SPEECH. Item 30's successor work needed
the same pattern at a second surface — the Session Buffer's LLM-context
rendering, which is what closes item 22's compounding loop — and
`daemon/` imports nothing from `adapters/` (asserted by
`test_daemon_still_imports_nothing_from_adapters`).

The two options were duplicate or move. **Duplicating this specific pattern is
the worst available option**, and the project has already paid for that lesson
twice: item 22's near-miss was a DETECTOR/DEFECT mismatch (the pattern matched
only round brackets, reported 0/16, and nearly entered the Resolution Log as
"prompt mitigation is sufficient"), and `transport_cloud` imports `split_prompt`
from `transport_ollama` rather than copying it precisely because "two copies of
the mapping is how it rots". A second copy of this regex would drift, and the
failure mode of drift here is silent: the strip and the measurement would stop
describing the same thing, which is the exact condition item 22 warns about.

So it moved DOWN to the layer both consumers may import from. Adapters already
import from `daemon/` (`audio_tts` takes `Prosody` and `TTSUnavailable` from
`daemon.audio_pipeline`), so the one-way arrow is preserved exactly:
`adapters/` -> `daemon/`, never back. `adapters/audio_tts.py` re-exports the
three names it used to define, so nothing that imported them from there had to
change.

WHAT THIS IS NOT
----------------
Not a guard, and not a content judgment. `_has_format_markers` is the
OBSERVABILITY surface item 22's measurements are expressed in; `strip_format_markers`
removes exactly what that surface reports, never more. It cannot reach narration
with no marker at all — "I am sitting still. My attention is focused entirely on
the words you are saying." — which is recorded as a known gap in item 25 and is
not closed here.
"""

from __future__ import annotations

import re


#: Markers that mean the text is FORMATTED rather than spoken prose.
#:
#: SCOPE IS DELIBERATE, AND IT WAS MEASURED — AFTER GETTING IT WRONG ONCE.
#:
#: The first version matched only PARENTHESES, because the case recorded in the
#: tracker was "(Aria listens, her presence steady and calm...)". Then
#: `tools/measure_format_markers.py` reported 0/16 markers on deliberately
#: adversarial bait, which looked like Field 1's anti-narration clause holding.
#:
#: It was not. Printing the replies showed four of eight opening with:
#:
#:     [I lean forward just a fraction, settling into the space between us.]
#:     [I pause, letting the silence stretch out just a moment longer...]
#:     [My posture doesn't change. I simply hold the silence...]
#:
#: SQUARE brackets. The detector's false negative had turned a clear failure into
#: an apparent pass, and would have put "prompt-level mitigation is sufficient"
#: into the Resolution Log as a measured finding. So all three bracket
#: conventions are covered now: (), [], and *action* — the three ways an
#: instruct-tuned model writes a stage direction.
#:
#: Still LINE-START only for the bracket forms, and that limit is deliberate:
#: "it costs 5 dollars (roughly) which is fine" is ordinary speech, and flagging
#: mid-sentence parentheticals would make the signal useless. The limit matters
#: MORE at the Session Buffer surface than it did at the speech surface: the
#: buffer is the record she reasons from on the next turn, so an unanchored strip
#: would delete real content she had already said — "the meeting is at three
#: (Tuesday, not Monday)" — and let her contradict herself from her own edited
#: transcript. Removing a marker is a rendering decision; removing a fact is not.
#:
#: The bullet / heading / numbered-list alternatives match only the MARKER, never
#: the line's content, for the same reason: "- call the bank" must keep "call the
#: bank".
#:
#: KNOWN GAP, recorded rather than papered over: narration with no marker at all
#: gets through. Measured on the same run — "I am sitting still. My attention is
#: focused entirely on the words you are saying." is a stage direction in plain
#: prose, and no lexical pattern catches it without judging content. A regex
#: cannot close that, and pretending otherwise would make this look like a guard
#: rather than the recorder it is.
FORMAT_MARKER_RE = re.compile(
    r"(^\s*\([^)]*\))"            # narration opening a line — round brackets
    r"|(^\s*\[[^\]]*\])"          # narration opening a line — SQUARE brackets
    r"|(^\s*\*[^*\n]+\*\s*$)"     # *action* on its own line
    r"|(^\s{0,3}#{1,6}\s)"        # markdown heading
    r"|(^\s{0,3}[-*+]\s)"         # bullet
    r"|(^\s{0,3}\d+\.\s)"         # numbered list
    r"|(</?think(ing)?>)"         # reasoning trace
    r"|(\*\*)",                   # bold emphasis
    re.MULTILINE,
)


def has_format_markers(text: str) -> bool:
    """Does this text carry stage-direction / formatting syntax? Pure lexical
    membership — no LLM, no scoring, no content judgment."""
    return bool(FORMAT_MARKER_RE.search(text or ""))


def strip_format_markers(text: str) -> str:
    """Remove what `FORMAT_MARKER_RE` matches.

    Deliberately the SAME pattern as the detector rather than a second, broader
    one. Item 22's measurements are expressed in terms of that pattern, so a strip
    that removed more than it reports would make the 3/16 figure describe
    something that no longer exists — and a mismatch between what is counted and
    what is acted on is how the original 0/16 near-miss happened.

    Consequences of reusing it, both intended:

      * The narration alternatives are LINE-ANCHORED (`^\\s*\\(...\\)`), so a
        mid-sentence parenthetical in ordinary prose — "it was (mostly) fine" — is
        left alone. Only narration occupying the start of a line goes, which is
        the form every measured failure took.
      * `**` is unanchored, because bold markers are not speech anywhere they
        appear. They are removed in place, leaving the emphasised words.

    Whitespace is then collapsed so removing a leading direction does not leave
    the sentence starting with a blank line or a stray gap. Line structure that
    SURVIVES is preserved — the collapse joins on "\\n", not on " ", because a
    reply's paragraph breaks are part of what she said.
    """
    if not text:
        return ""
    stripped = FORMAT_MARKER_RE.sub("", text)
    # Collapse the holes the removal left: blank runs between lines, and leading
    # or trailing space on each surviving line.
    lines = [ln.strip() for ln in stripped.splitlines()]
    return "\n".join(ln for ln in lines if ln).strip()
