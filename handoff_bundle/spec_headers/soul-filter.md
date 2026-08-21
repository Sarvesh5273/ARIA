# ARIA locked spec — soul-filter

> ## AMENDMENT 2026-08-20 — ARCHITECT RULING on Field 5
>
> **Field 5 (Constraints) carries behavioural INSTRUCTIONS, not prohibitions
> only.** Wherever the body says Field 5 is *"a closed list of specific
> prohibitions"*, read *behavioural instructions, mostly prohibitions*. MAX-3 and
> "always specific actions" UNCHANGED.
>
> Formalises existing practice — the Energy<30 row (`"do not overextend"`) already
> lived there. Unblocks v4 instruction-table line 949 (*"Energy critically low
> (below 20) → 'You are running low. Acknowledge it if it comes up naturally.'"*),
> now emitted as **`"acknowledge fatigue if it comes up naturally"`**. Previously
> `ENERGY_CRITICAL` was imported and never referenced.
>
> v4's *"You are running low"* clause is NOT passed through — that half is state
> rendered as a claim, and state never crosses (Addendum §9). Gates are checked
> most-severe-first (<20 before <30): at most one constraint slot is ever free, and
> since Energy<20 implies Energy<30 the milder instruction would otherwise always
> take it and the <20 row could never fire.
>
> **RECORDED IN THE PRECEDENCE CHAIN 2026-08-20** as `ARIA_Resolution_Log.md`
> item 16, with Addendum §9's Constraints row amended in place to match. §9 no
> longer contradicts the code.
>
> **Two more v4 uncertainty rows landed 2026-08-20.** v4's table has FOUR, not two.
> Live now: **944** INPUT_UNCERTAIN → `do not project onto what you do not know yet`,
> and **946** resolved-this-turn → `let it show that something became clearer`. Both
> categorical off signals `AppraisalResult` already carried. With 943 in the base
> branch, three of four are live. **Row order is a FLAGGED presentation choice** —
> base → 944 → Energy<20 → Energy<30 → 946; highest-stakes prohibition first,
> lowest-stakes permission last, since the MAX-3 cap decides which survives.
> **Row 945 ("Uncertainty weight above 0.5") is PARKED and not implementable**: the
> phrase occurs once in the whole precedence chain, no such quantity exists, and
> manufacturing one would be a number deciding what she says about her own interior.
> Rule 1. See the design body for the full reasoning.

Consolidated from .kiro/specs/soul-filter/{requirements,design,tasks}.md for upload.
Precedence: ARIA_Resolution_Log.md > ARIA_Soul_Spec_v4_Addendum.md > ARIA_Soul_Spec_v4.md.
