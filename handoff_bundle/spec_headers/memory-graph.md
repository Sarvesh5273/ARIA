# ARIA locked spec — memory-graph

> ## AMENDMENT 2026-08-20 — OQ2 CLOSED, medium/low floors REMOVED
>
> Everything below about medium/low `base_salience` **placeholders (medium 0.35,
> low 0.15, `TODO(OQ2)`)** is **SUPERSEDED**. Those numbers no longer exist in
> code and must not be reintroduced.
>
> `ARIA_Resolution_Log.md` item 9 line 96 states literally: *"Medium/Low → no
> floor, decays/discards as already locked."* That is a positive instruction, not
> silence. This spec read it as a gap and filled the gap with invented magnitudes
> — against the highest-precedence document.
>
> Current behaviour: `_MEDIUM_LOW_BASE_SALIENCE_PLACEHOLDER` is deleted;
> `_compute_base_salience` falls through to **0.0** for medium/low. Only the
> in-spec **Critical 0.85 / High 0.55** floors remain. The v4 Baumeister **+0.15**
> negative bonus still stacks "on top of whichever floor applies", which for
> medium/low is nothing. Tested: at 65d untouched, medium/low reach `faded` while
> critical stays `vivid` and high holds at `present`. Body kept for provenance.

Consolidated from .kiro/specs/memory-graph/{requirements,design,tasks}.md for upload.
Precedence: ARIA_Resolution_Log.md > ARIA_Soul_Spec_v4_Addendum.md > ARIA_Soul_Spec_v4.md.
