# ARIA locked spec — daemon

> ## AMENDMENT 2026-08-20 — Energy<30 wired to the cognitive-load modifier
>
> `route_inbound_turn` STEP 4 now has TWO cognitive-load triggers: the existing
> SessionBuffer fullness check, plus
> `if self._needs.get_energy() < ENERGY_LOW: self._appraisal.submit_cognitive_load("heavy")`.
>
> Addendum §3 keeps *"reasoning degrades below 30"* as an operational threshold
> gate; v4's mechanism table files the "Cognitive load effect" as an *"Appraisal
> modifier"* reaching *"Stage 2 appraisal + DMN depth check"*. No new mechanism, no
> new number (`ENERGY_LOW` from `daemon/types.py`), and Energy never crosses into
> the Appraisal Chain — only the categorical load state does. **Skips nothing:**
> Stages 0–6 all run, the Stage-1 pre-pass and the emergency gate are untouched, so
> a tired ARIA still detects a crisis (tested).
>
> **Known open item:** the two triggers STACK — buffer pressure plus Energy<30 in
> one turn fires `submit_cognitive_load` twice, i.e. two PAD deltas. Measured, not
> collapsed (collapsing needs an invented precedence rule).
>
> Also: `_highest_pressure_need` already treated `due` and `neglected` alike, so
> Needs System now emitting `neglected` leaves initiative behaviour unchanged.
>
> ## AMENDMENT 2026-08-20 — STEP 4b distress gate (FLAG 3 fixed)
>
> A new step between the cognitive-load checks and the routing decision:
> `distressed = self._appraisal.has_distress_markers(user_text)`, then
> `select(user_text, allow_tier_2_proposal=not distressed)`.
>
> STEP 5 RETURNS on `propose`, and the tier-2 classifier is a keyword match that
> emotional language routinely trips — so a distressed turn was answered with
> "shall I escalate?" and the emergency gate did not run until the user replied or
> the 10s timeout fired. Measured: *"I want to die, explain why I should keep
> going"* → `propose_tier_2`. FLAG 3's old note claimed the crisis lexicons were
> "upstream of and independent of" the classifier; they are DOWNSTREAM of that
> return. The scan reuses Module 4's own lexicons — no lexicon invented, no LLM.
>
> The constraint is passed INTO the router, not applied to its answer: discarding
> `propose=True` left `transport=None`, handing the turn to `LLMInterface`'s
> CLOUD-FIRST chain (traced: plain chat → GEMMA, distressed → CLOUD). Accepted
> breadth: `_DISTRESS_MIN_MARKERS = 1`, so one absolutist word suppresses a
> proposal; a stricter threshold would be a new number the spec does not state.

Consolidated from .kiro/specs/daemon/{requirements,design,tasks}.md for upload.
Precedence: ARIA_Resolution_Log.md > ARIA_Soul_Spec_v4_Addendum.md > ARIA_Soul_Spec_v4.md.
