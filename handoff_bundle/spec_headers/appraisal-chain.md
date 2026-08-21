# ARIA locked spec — appraisal-chain

> ## AMENDMENT 2026-08-20 — conflict-arc 2nd close condition implemented
>
> **1.** Addendum §1's second close condition (*"or enough turns pass without that
> entity recurring"*) now exists in behaviour via `_conflict_arc_absence_close()`,
> which runs once per turn, increments the absent counter for every open arc whose
> entity did not recur (including turns with no entity), and closes those at the
> threshold. Categorical — the turns have passed or they have not. Absence closures
> write the same single `"resolved"` edge as a Q2 flip. Previously
> `_arc_absent_turns` was reset but never incremented and never read.
>
> **2.** `_ARC_CLOSE_ABSENT_TURNS` is **5**, not 3 (architect-set; both are
> `TODO(build-time)` placeholders). It is an ALIAS of
> `_CONFLICT_ARC_ABSENT_TURN_THRESHOLD` so the knob and its `AppraisalConfig`
> override cannot drift.
>
> **3.** `poignancy_base_hint()` is **deleted**. It returned 0.35 for medium/low —
> the same invented magnitude removed from Module 3's OQ2. v4 "Argument Buffer
> Mode" names the multiplicand (*the resolution is "weighted 3× higher than **the
> conflict itself**"*), so the `"resolved"` edge now takes the **opening
> EventNode's own `base_salience`**. Non-zero at every tier because an arc only
> opens on a Q2=negative node (Baumeister +0.15).
>
> **Also:** `_need_prefs` keys Connection on `neglected` alone, per Addendum §3; it
> previously fired on `due` too. Growth/Purpose/Continuity untouched.
>
> **4.** VALENCE_UNCERTAIN no longer closes an arc. Addendum §1 says the arc
> closes on a flip to `Q2=positive/neutral`; VALENCE_UNCERTAIN is neither, but the
> else-branch treated everything not-NEGATIVE as a flip — so user confusion
> counted as repair and wrote a `"resolved"` edge, which the Invested→Bonded FAITH
> gate reads. It now breaks the consecutive-negative run without closing the arc.
> An opener is marked only when no arc is already open, or a later negative would
> clobber `_arc_open_event` mid-arc and point the closure edge at the wrong node.
>
> **5.** New public `has_distress_markers(text)` — the disjunction of
> `_distress_marker` and `_emergency_cue_kind`, exposed for the Daemon's STEP 4b
> distress gate. Read-only, lexical, invents no lexicon.
>
> **Open:** nothing READS edge `salience` for any decision, so item 5's 3× is
> representational only.

Consolidated from .kiro/specs/appraisal-chain/{requirements,design,tasks}.md for upload.
Precedence: ARIA_Resolution_Log.md > ARIA_Soul_Spec_v4_Addendum.md > ARIA_Soul_Spec_v4.md.
