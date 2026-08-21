# ARIA locked spec — needs-system

> ## AMENDMENT 2026-08-20 — OQ-1 CLOSED, `neglected` now emitted
>
> Everything below stating that `NEGLECTED` is **never emitted** is
> **SUPERSEDED** for Connection / Growth / Purpose; still accurate for Continuity.
>
> `_state` is 3-valued via **two windows over the SAME evidence query**:
> `satisfied` if evidence in the need's own window, else `due` if in the next rung
> up the locked ladder, else `neglected`. Connection 72h→14d, Growth 14d→60d,
> Purpose 14d→60d. A counter was explicitly REJECTED — Addendum §3 rules it out in
> the same paragraph that establishes the three states (*"reverts on its own;
> nothing actively subtracts anything … not a running clock"*). No window,
> constant, counter or storage introduced; `graph_manager` unchanged because all
> four `*_evidence` methods already accept `window`. State stays a pure function of
> (now, graph); `NeedsEvaluator` stays stateless.
>
> Continuity stays two-valued: 60d is the top rung of the locked ladder, and §3
> gives it a quality criterion (*"contradicts rather than extends"*) with no signal
> wired to the narrative path. Known consequence: an empty graph reports
> `neglected` on first run, self-correcting on the first qualifying turn.

Consolidated from .kiro/specs/needs-system/{requirements,design,tasks}.md for upload.
Precedence: ARIA_Resolution_Log.md > ARIA_Soul_Spec_v4_Addendum.md > ARIA_Soul_Spec_v4.md.
