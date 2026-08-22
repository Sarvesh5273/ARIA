# ARIA Soul Spec v4 — Addendum 2: Build-Plan Resolution Log

Companion to ARIA_Soul_Spec_v4.md, ARIA_Soul_Spec_v4_Addendum.md, and
ARIA_GLM_Covering_Instruction.md. Resolves every Flag raised in the
first-pass ARIA_Module_Build_Plan.md plus gaps found in architect
review. Where this conflicts with any earlier document, this is correct.

---

## 1. Emergency Mode — Rule 5 exception

Rule 5 amended: the five-field format applies in normal operation only.
When the emergency gate fires (Q1=HIGH, Q2=SEVERELY_OBSTRUCTIVE,
Q4 coping_potential ≤0.15), Soul Filter branches BEFORE field assembly
and sends the fixed Type A/B/C instruction set instead of the five
fields — replacing, not extending them. Soul Filter and LLM Interface
must treat "five-field instruction" and "emergency instruction" as
mutually exclusive outputs of one branch, not as two coexisting inputs.

## 2. Self-model vs. Rule 7

Rule 7 amended: applies to autobiographical memory only. Split the
self-model:
- STAYS as non-graph working state (self_model.json): quality record,
  consistency flags, recent-learning-user, recent-learning-self.
  Same category as PAD/Energy — operational readout, not memory.
- MOVES to the graph: the self-continuity narrative. Aria gets a
  self-referential EntityNode; the narrative lives in that node's
  existing `relationship_summary` field (same mechanism already used
  for every other entity). Written by DMN Step 4 exactly as before —
  same trigger conditions, same "appeared more than once" gate. No
  new node type, no new DMN mechanism.

## 3. EventNode.emergency_type

appraisal_q2 stays 4-value (positive/negative/neutral/
VALENCE_UNCERTAIN) — unchanged. Add new nullable field:
`emergency_type: "PHYSICAL_THREAT" / "EXISTENTIAL_DISTRESS" /
"DECISION_CRITICAL" / "UNCLASSIFIED" / null` — populated only on
turns where the emergency gate fires; null otherwise. Persisted
turn's appraisal_q2 is simply "negative" as normal. coping_potential
is transient — computed only during the Stage-2 gate check, discarded
if the gate doesn't fire; not a persisted field (see item 12).

## 4. Module 11 — State Manager

New module. Responsibility: serialize PAD, Energy, and the narrowed
self-model working-state (per item 2) to aria_state.json /
self_model.json on a fixed cadence and on shutdown; restore on daemon
startup. Owns no meaning — pure read/write plumbing. Does not persist
anything graph-owned. Write cadence is a build-time tuning flag, not
an architectural decision.

## 5. Argument Buffer closure

No new node type — v4's "single Argument Buffer node" language
describes the effect, not new schema. On arc closure (per the
addendum §1 state machine), write one edge: edge_type="resolved",
from the closing EventNode to the opening EventNode, salience
weighted 3× (reuses the existing Argument Buffer resolution-weight
rule). The Invested→Bonded gate condition becomes: does a "resolved"
edge exist on this entity_ref within the relevant window?

## 6. Energy decay/refill mechanism

Single-rate EMA decay during active load (constant k_load);
drift-to-baseline recovery during idle (constant k_rest). Two
constants, not four — Energy has no valence, so PAD's asymmetric
positive/negative coefficients don't apply. This is a resource/battery
model, explicitly exempt from the no-invented-formula rule (that rule
protects appraised *meaning* — trust, poignancy — not a depletion
resource). k_load and k_rest values are build-time tuning flags.

## 7. Need → recency-window mapping

Connection → 72h · Growth → 14d · Purpose → 14d · Continuity → 60d.
Reuses the three windows already locked for precision decay — no new
windows introduced.

## 8. Precision decay clock

Lazy, retrieval-triggered evaluation — not a continuous background
timer. Each node's `last_accessed` field is checked against the
resistance thresholds at the moment Stage 1 or DMN retrieves it;
precision updates then, not on a sweep. No new always-on clock needed.

## 9. Salience floors by poignancy tier

At EventNode creation, base_salience gets a floor set by
poignancy_category:
- Critical → floor 0.85 (resists vivid→present indefinitely — stays
  word-for-word forever, any valence)
- High → floor 0.55 (resists present→softened — permanently settles
  at "the gist," does not resist vivid→present; ~72h to soften from
  exact wording, then holds)
- Medium/Low → no floor, decays/discards as already locked

The existing Baumeister +0.15 negative-event bonus stacks on top of
whichever floor applies. Resistance checks compare against
base_salience (which never decays) — never against the fluctuating
salience field, which habituation can lower. This prevents a Critical
memory from ever softening due to repetitive retrieval.

## 10. Trivial resolutions (no further deliberation needed)

- Staleness counter "interactions" = user turns since node creation,
  incremented by Appraisal Chain, read by DMN — uses the existing
  interaction_count field, no new field needed.
- Remove aria_state.json.relationship_depth entirely — fully
  superseded by EntityNode.relational_stage.
- Active Inference (Paper 1) is a descriptive framing over the
  existing Stage 0–6 appraisal chain, not a separate subsystem —
  no dedicated module.
- Live Stage-6 EventNode writes and DMN Step-1 buffer-to-graph writes
  are different node populations (per-turn appraised events vs.
  session-level meta-observations) — no overlap, no double-write.
- The 5-Need Interaction Map (v4 Layer 2) is descriptive flavor, not
  a mechanism — the described blends emerge naturally from Soul
  Filter reading PAD + need states together. No dedicated module.
- Attentional policy is implementable as literally stated in v4
  (highest-pressure need + most recently salient node) — no further
  formalization required.

## 11. Needs System module boundary

Single module. Energy and the four categorical needs share the same
soul-tick trigger and consumers (Soul Filter, Appraisal Chain, DMN) —
no independent lifecycle to justify a split. Internally implemented
as two separated components (energy tracker + needs evaluator) to
preserve the distinct-mechanisms distinction without a module split.

## 12. coping_potential scope

Not a persisted field, not computed on every turn. Transient value,
computed only during the emergency-gate check (Stage 2), alongside
emergency_type (item 3) — discarded if the gate doesn't fire.
Normal-turn Q4 stays purely qualitative (appraisal_q4_notes), as
already locked.

## 13. Buffer-item poignancy

No independent classifier for buffer items. Each self-monitoring
buffer item inherits poignancy_category directly from the EventNode
of the turn it's observing — no re-appraisal, pure reuse.

## 14. Gemma fallback scope

Confirmed: Gemma receives the identical instruction Soul Filter would
send the cloud LLM (five fields, or Emergency Type A/B/C per item 1)
plus the user message — nothing else, no graph access, no exception
for the local model.

## 15. Non-issues — no action needed

Output Gate ownership, Audio Pipeline module split, and video
ownership are documentation artifacts of the covering instruction's
layer numbering, not logic conflicts — v4 and the addendum already
resolve all three:
- Output Validation Gate is owned/logic-defined by Soul Filter
  (Module 5), invoked by LLM Interface (Module 9).
- Audio Pipeline is a single module (input chain + output chain
  together), per v4's own file layout.
- PAD→video zone mapping lives in Visual Layer (Module 10); v4's
  "soul_filter's job, not the LLM's" language is colloquial (soul
  layer generally, not the LLM) and doesn't override v4's own
  directory structure, which lists video_controller.py separately.

## 16. Field 5 — behavioural instructions, not prohibitions only

Addendum §9 defines Constraints (Field 5) as "a closed list of specific
prohibitions." Amended: Field 5 carries specific behavioural
INSTRUCTIONS, most of which are prohibitions. Everything else about the
field is unchanged — maximum three items, always specific actions rather
than vague directives, and no numbers or state may cross.

This formalises what the field already carried rather than widening it
after the fact: the Energy<30 row ("do not overextend") was derived from
the Energy gate, not from the moral schema, and lived in Field 5 from the
start. The amendment unblocks v4's soul_filter instruction table row for
Energy<20 — "You are running low. Acknowledge it if it comes up
naturally." — which has no prohibition form and was therefore never
emitted despite being specified.

Two constraints on how such a row crosses:

- Only the INSTRUCTION half crosses. v4's "You are running low" clause is
  Energy state rendered as a claim, and state never crosses (§9). The
  emitted form is the action alone.
- "Never open-ended" means "a specific action, not a vague directive."
  A specific action carrying a condition ("if it comes up naturally") is
  still specific; a directive with no identifiable action is not.

Where two Energy rows both apply, the more severe fires first: Energy<20
implies Energy<30, so checking the milder gate first would let it consume
the last of the three slots and the <20 row could never be emitted at
all.

## 17. `neglected` need state — two-window derivation

Addendum §3 requires three categorical states for Connection, Growth,
Purpose and Continuity — satisfied / due / neglected — and the same
section forbids a counter: "the state reverts on its own; nothing
actively subtracts anything ... not a running clock." A
consecutive-due-turns counter is therefore not available.

Resolved: `neglected` is derived from TWO windows over the same
qualifying-evidence query. Satisfied when evidence falls inside the
need's own window (item 7); due when it falls inside the next wider
window; neglected when it falls inside neither.

  Connection  72h → 14d      Growth  14d → 60d      Purpose  14d → 60d

Both windows are values item 7 already locked, so no window and no
constant is introduced, and the state remains a pure function of (now,
graph) that reverts on its own. This reads Addendum §3's own Continuity
wording — "neglected when updates have gapped for a long stretch" — as
what it says: a long stretch is a wider window, not an elapsed count.

Continuity remains TWO-valued. Its own window is 60d, already the widest
rung, so there is no wider window to step to; and §3 gives Continuity a
quality criterion rather than a gap — "or new evidence contradicts rather
than extends it" — which requires a contradiction signal that does not
yet exist. Continuity `neglected` stays open; it is not to be
approximated with a fourth window.

Consequence, accepted: a graph with no evidence at all reports
Connection / Growth / Purpose as neglected rather than due, since nothing
falls in either window. This is what the rule yields and it corrects
itself on the first qualifying interaction.

## 18. Restore-boundary clamping — State Manager

PAD is bounded to [0.0, 1.0] (v4 Layer 1) and Module 1 clamps live PAD in
apply_appraisal_delta, but nothing bounded a RESTORED value, so a
hand-edited or truncated state file could seed an out-of-range PAD into a
live session.

Resolved: the clamp belongs at the State Manager restore boundary, not
inside PAD_Engine. `load_pad` bounds each axis to [0.0, 1.0]; `load_energy`
bounds Energy to its 0–100 scale. Module 11 still computes nothing and
interprets nothing — bounding a value read off disk is a boundary check,
not meaning.

Non-finite input is treated as CORRUPT rather than clamped, falling back
to the spec default like any other unusable entry. NaN has no position on
a scale, and it survives a naive clamp as the upper bound — a corrupt
Energy entry would otherwise restore as "fully rested."

The clamp is a READ boundary only. Save records what the owning module
hands over; the resulting asymmetry for out-of-range input is intended.

## 19. Post-approval work — authorisation of record

Everything in this item was architect-directed after the thirteen modules
were approved. None of it appeared in v4, the Addendum, or this log, which
left a reviewer unable to distinguish architect-approved work from agent
invention. Rule 1 ends "the architect resolves it"; this item is that
resolution, recorded so the distinction is legible.

Authorised, and locked on the same terms as any item above:

- **Session Buffer (Module 12)** — ephemeral three-tier conversation
  buffer, rule-based summarisation, cognitive-load reporting. Not
  persistent memory; the graph remains the only memory.
- **`session_context`** — the current session's transcript, passed to the
  LLM alongside the five fields. Ephemeral record of what was already
  said, not internal state. Its tension with §9's unqualified "nothing
  else" is NOT resolved by this item and remains open.
- **Meta-commands** — `rest` / `focus` / `unfocus`, and the backend
  vocabulary ("use cloud" / "stay local" / ...). These bypass appraisal
  and write no EventNode.
- **BackendRouter (Module 13)** and the Track A wiring that threads a
  caller-supplied transport through Soul Filter to the LLM Interface.
  Gemma is the default voice for conversation and is tried first; Groq is
  a fallback; the reasoning tier is proposed, never taken silently.
- **Energy<30 → cognitive-load modifier.** Addendum §3 keeps "reasoning
  degrades below 30" as an operational threshold gate and v4's mechanism
  table files the effect as an appraisal modifier. It routes through the
  Appraisal Chain's existing cognitive-load entry point. Energy itself
  does not cross into that module; only the categorical load state does.
  No appraisal stage is skipped — in particular the emergency gate and the
  Stage-1 social-signal pre-pass both still run.
- **Daemon distress gate.** The reasoning-tier proposal defers a turn
  before appraisal runs, and the tier-2 classifier is a keyword match that
  emotional language routinely trips. A turn carrying distress or an
  emergency cue is therefore never deferred: the Daemon scans it against
  the Appraisal Chain's existing lexicons and instructs the router not to
  propose. Presence takes precedence over routing. The scan introduces no
  lexicon and no threshold of its own.
- **Conflict-arc absent-turn count = 5.** Still a build-time tuning
  constant under "Open" below, not an architectural decision.

---

## 20. Ephemeral session context — third sanctioned surface

*(2026-08-22)*

Item 19 authorised `session_context` as post-approval work but explicitly
left its tension with Addendum §9's unqualified "nothing else" unresolved.
This item resolves it.

Resolved: ephemeral session context is a THIRD sanctioned surface
alongside the five fields and the user's current message — the current
session's transcript only, appended and never merged into a field, and
still appended in emergency mode. Addendum §9 carries the in-place
amendment.

"Nothing else" is NOT narrowed. Reading it as "nothing else *from past
sessions*" would legalise seven of the nine never-crosses items: only the
last two concern past sessions, while PAD values, graph node IDs or
contents, relational_stage label, needs states as data, Q1–Q4 outputs,
memory node contents and appraisal vectors are current-turn data excluded
on their own terms.

The boundary is the SESSION boundary: within-session is a transcript,
across-session is memory and stays out. If the Session Buffer is ever
changed to persist across sessions, this item does not cover it and must
be revisited.

Item 19's own wording stands as the dated record of what was true when
written.

---

## Resolved during build-plan review (post-approval, GLM's own flags)

- **relational_stage transition-gate evaluator** → DMN Step 4
  (Module 6), batched during idle consolidation, not reactive.
  Module 3 (Memory Graph) stores the field; Module 6 evaluates and
  writes transitions.
- **Present World Model + language-switch state** → Daemon (Module 8)
  volatile working state, not persisted. Consistent with Rule 7
  (forbids only a second *persistent* store).
- **Self-model quality-record population** → DMN Step 1 (Module 6),
  from the NEXT turn's appraisal output (user's appraisal_q2 +
  topic-continuation/pivot signal from consecutive EventNodes) — NOT
  the Output Validation Gate's Check-3 result, which is a pre-reaction
  structural safety check, incapable of judging response quality.
  Grounds "responded well" in observed user reaction, not self-report
  — the guard against a self-graded metric drifting toward flattery.

---

## Open — build-time tuning constants only

Not architectural gaps. Parameters to set during implementation, not
before:

- VULNERABILITY_DISCLOSURE embedding-similarity cutoff
- REALITY_CONTRADICTION comparison-window duration
- Conflict-arc open/close turn-counts
- Soul-tick & DMN-tick intervals (only idle=8min, reflection=6h pinned)
- k_load / k_rest (Energy)
- State Manager write cadence

---

*This resolution log is final for all items listed. Module-level build
planning and implementation should incorporate every locked item above
without reopening them.*
