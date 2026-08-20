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
