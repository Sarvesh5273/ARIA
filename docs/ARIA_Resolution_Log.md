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

## 21. An empty candidate is a NON-CANDIDATE, not a passing response

*(2026-08-22)*

**Supersedes:** the implicit assumption that anything the LLM returns is a
candidate for the Output Validation Gate to judge.

Wiring real TTS surfaced this. On the initiative path the local model
returned `""`, and the gate reported `passed=True`, `failed_checks=[]`,
`retried=False`, `used_minimum_safe_output=False`. The empty string was
served as her reply.

**The gate was right.** Addendum §4's mechanism is four structural
comparisons, each against something Aria's own state already holds. An
empty string contradicts none of them: it makes no dishonest claim,
mismatches no relational_stage, matches no anti-pattern, and deflects from
nothing. The gate was being asked about a non-thing.

Resolved: **whether a candidate EXISTS is established before the four
comparisons run, and is not one of them.** Addendum §4 is untouched — the
gate still runs exactly four checks and `GateCheck` still has exactly four
members.

A generation that returns nothing (empty or whitespace-only) is re-asked
ONCE with the same instruction, and if that also returns nothing the turn
drops to v4's existing MINIMUM SAFE OUTPUT floor. Both mechanisms already
existed; the newly-recognised case is routed into them. No number, no
threshold, no lexicon, and no judgment about content is introduced —
"is there text" is a shape check of the same kind the transport adapters
already make on a provider's response field.

Three consequences are deliberate:

- **The re-ask is a plain re-ask, not a corrective retry.** There is no
  failed check to correct, and inventing a corrective for emptiness would
  add gate vocabulary through the back door.
- **It does not play the reconsideration sound.** That clip is v4 Layer 5's
  SELF-CORRECTION sound. She said nothing, so there is nothing to
  reconsider, and playing it would perform an interior event that did not
  happen.
- **It applies on the emergency path too.** The gate BYPASS there is
  untouched — emergency output is still unvalidated — but "did the model
  answer" is not one of the checks being bypassed, and distress answered
  with silence is the worst outcome that path can produce.

**Not resolved, and left deliberately empty:** if the minimum-safe
instruction ALSO returns nothing, the response text is empty. No fallback
sentence is invented, because writing one would be putting words in her
mouth. The turn is instead loudly labelled — `used_minimum_safe_output=True`
with `empty_candidates` counting every empty generation — so a total
generation failure is visible rather than silent.

---

## 22. Stage directions — prompt mitigation MEASURED, and it is not sufficient

*(2026-08-22)*

**Supersedes:** the assumption, recorded when the Persona Anchor clause was
added, that Field 1 wording was an adequate answer to the format defect.

The tracker's format-guard row noted that the Output Validation Gate has no
FORMAT check — its four comparisons are about content, so nothing
structurally prevents a stage direction, heading or reasoning trace reaching
TTS and being spoken. Field 1 gained an anti-narration clause as mitigation.
**That clause was never measured.**

Measured now (`tools/measure_format_markers.py` — adversarial bait, real
model, real pipeline, fresh graph per arm, two rounds each):

| Mitigation | Turns carrying a stage direction |
|---|---|
| Original abstract clause | **8/16** — and **12/16** on a warm session |
| Wording that NAMES the syntax | **3/16** (reproduced on the shipped wording) |

Three findings, all load-bearing:

1. **Prompt-level mitigation reduces this by roughly two thirds and does
   NOT close it.** Option "accept prompt mitigation as sufficient" is
   therefore closed on evidence, not opinion.
2. **The failures were in SQUARE brackets** — "[I lean forward just a
   fraction, my gaze calm]" — a form the original clause never named. Field 1
   now names all three bracket conventions and states "You have no body to
   describe" as fact rather than prohibition, because the brackets were
   claiming a posture and a gaze she does not have.
3. **The defect COMPOUNDS through the session buffer.** 4/8 in round one
   became 8/8 in round two: her own bracketed replies re-enter as session
   context and she imitates herself. Session context is a faithful record of
   what was said, so there is no fix on that side that does not involve
   judging her own words.

**A near-miss worth recording.** The first measurement reported 0/16 and
looked like the clause holding — because the marker detector matched only
ROUND brackets. Printing the replies showed square-bracket narration in half
of them. "Prompt-level mitigation is sufficient" was one step from entering
this Log as a measured finding on the strength of a detector bug.

**RULED ON 2026-08-24 — see item 25.** The ruling took a narrowed form of the
third option below: strip markers where text becomes SPEECH, leaving the response
itself untouched. It closes the MARKED fraction only; findings 1 and 3 above
(unmarked prose narration, and the compounding through the session buffer) are
explicitly not closed by it, and the recommended moral-schema option remains
available and un-foreclosed. The options below are kept as the reasoning item 25
was decided against, not as live choices.

The residual 3/16 needed a ruling and it was not taken here. Options, with the
reasoning that survives measurement:

- **A fifth gate check.** Rejected on two independent grounds: Addendum §4
  fixes the comparison set at four, and a format defect is not a comparison
  against held state, so it would not fit the mechanism even if the cap were
  lifted.
- **Extend the moral schema's named anti-pattern list**, so the existing
  MANIPULATION check catches it. This is the RECOMMENDED option and the
  argument is that the defect has been miscategorised from the start: Aria
  has no body, so "[my gaze is calm, meeting yours without pressure]" is a
  false claim about herself made to produce an emotional effect — it
  simulates presence rather than being present, which is the same shape as
  the already-named `fake_confidence`. It adds no fifth comparison, uses the
  existing mechanism as designed, routes a caught candidate into the existing
  corrective-retry ladder, and extends a list the docs already mark as
  OQ-M1, "not a doc-certified final set". **It is not implemented, because
  the moral schema is load-bearing, it also gates DMN narrative updates
  (Addendum §8), and a wrong entry would propagate into what she can believe
  about herself. That is an architect's call, not an implementer's.**
- **A format normaliser between Soul Filter and the Audio Pipeline.** A new
  component, and it would be judging output.
- **Accept the residual and record it.** Now a real option, given 3/16 —
  but it means roughly one turn in five is spoken with narration attached.

Until a ruling, the TTS adapters RECORD markers
(`last_text_had_format_markers`) and strip nothing. A recorder is not a
guard and is not presented as one. Known gap, measured on the same run:
narration with no marker at all ("I am sitting still. My attention is
focused entirely on the words you are saying.") is not detected, because no
lexical pattern catches it without judging content.

---

## 23. Correction — "Resolution Log item 15" was miscited for verbatim passthrough

*(2026-08-22)*

A documentation correction, not an architectural change. Recorded because
the miscitation was load-bearing in a rejected design option.

**Item 15 is cited correctly in most places and incorrectly in a few, and the
difference is worth being exact about.**

Item 15 is titled "Non-issues — no action needed" and resolves three
OWNERSHIP questions: that the Output Validation Gate belongs to Soul Filter
(F-5a / F-9b), that the Audio Pipeline is a single module (F-7a), and that
PAD→video zone mapping lives in the Visual Layer (F-10a). **Every citation of
item 15 for those three things is right and stays.**

What item 15 does NOT say is that model output crosses the transport layer
VERBATIM with no judgment. That rule was attributed to it in
`daemon/llm_interface.py`, `adapters/transport_ollama.py`, several adapter
docstrings written on 2026-08-22, `main.py`, and both trackers. The word
"verbatim" appears in the entire precedence chain exactly once — in Addendum
§9's amendment about session-context recent turns, which is unrelated.

**The substance is real; only the attribution was wrong.** Verbatim
passthrough is a CONSEQUENCE of item 15's ownership ruling rather than a
clause in it: if the gate lives in Soul Filter, then the LLM Interface has no
gate to run, so it returns what it received. It is stated directly as the LLM
Interface's own Requirement 5 and as flag F-9b, and it is structurally
enforced — that module holds no graph, PAD or appraisal handle. So nothing
about the architecture changes.

Why the distinction mattered enough to record: the format-guard row rejected
"strip it in the adapter" by citing item 15, and anyone checking that source
would have found nothing supporting it. The reasoning for the rejection
stands on its own — an adapter that edits her words is deciding what she said
— but it should rest on F-9b and on that reasoning, not on a clause that does
not exist. The affected citations now point at F-9b / Req 5.

Reading the source rather than the citation is what surfaced this, while
deriving items 21 and 22. It is a reminder that a citation repeated across
three documents is not evidence that anyone checked it.

---

## 24. The local voice is `qwen3.5:9b-mlx`; `SPEC_MODEL` still cites v4

*(2026-08-24)* — architect ruling.

**`DEFAULT_MODEL` = `qwen3.5:9b-mlx`. `SPEC_MODEL` = `gemma4:e2b-it-qat`,
unchanged.** The two constants now hold different values for the first time.

Rationale, as given: native vision, tool support, a 256K context window, and
~13–14 tok/s sustained on the target Mac.

**What was verified here, and what was not** — recorded separately because the
log is the top of the precedence chain and the distinction matters later:

| Claim | Status |
|---|---|
| Installed on the target machine, 8.9 GB | VERIFIED (`ollama list`) |
| 256K context | VERIFIED — `ollama show` reports 262144 |
| Native vision | VERIFIED — reports `vision` capability |
| Tool support | VERIFIED — reports `tools` capability |
| ~13–14 tok/s sustained | **ARCHITECT-SUPPLIED, not reproduced in-project.** No harness run is recorded against this tag. `tools/compare_local_models.py qwen3.5:9b-mlx gemma4:e2b-it-qat` would produce the same table item 22's predecessors were decided on |

**Why `SPEC_MODEL` did not move.** v4's RAM budget table names "Gemma 4 E2B QAT",
and `SPEC_MODEL` is the citation of that fact, not a preference. Pointing it at a
model v4 never mentions would make the constant assert something the precedence
chain does not say. `DEFAULT_MODEL` is configuration and is the architect's to
set; the citation is not. This is also what makes `resolve_model()`'s rung 2 —
"fall back to what v4 names" — do real work for the first time instead of being
unreachable while the two values coincided.

`_LOCAL_VOICE_FAMILY_PREFIXES` gains `qwen3.5`, so the sanctioned set is now two
families rather than one. The ladder still refuses to reach outside it: "whatever
is installed" is not a model choice, and with six Gemma tags plus two Qwen tags on
the dev machine, guessing would pick a memory footprint on the operator's behalf.

**A supporting claim that does NOT hold, corrected here.** Several places —
`transport_ollama`'s module docstring and a test docstring among them — argued
that Addendum §1 forbids a non-Gemma local voice, citing its "Not Gemma" line.
§1 says the EMBEDDING model is not Gemma. That is a different seam and places no
constraint on the voice. The rule rested on v4 naming the model all along, which
is why `SPEC_MODEL` is the thing that had to be protected.

**Two risks this carries, neither of them closed by the switch.** Both are
consequences of the tag, not objections to the ruling:

1. **`qwen3.5:9b-mlx` reports a `thinking` capability.** Item 22's measurement
   found that neither Gemma emitted reasoning traces, and warned that a model
   which did would have them SPOKEN — the transport passes output verbatim
   (F-9b / Req 5) and the Output Gate's four checks are about content. Item 25
   now strips `<think>` blocks on the audio path, which covers the tagged form.
   An untagged reasoning preamble in plain prose is not covered.
2. **A capability regression.** `gemma4:e2b-it-qat` reports `vision` AND `audio`;
   `qwen3.5:9b-mlx` reports `vision` but not `audio`. Nothing uses model-native
   audio today — STT and TTS are separate adapters — so this costs nothing now
   and is recorded because it closes a door quietly.

**Superseded:** the 2026-08-22 finding that "the measurement sent the default back
to the spec" is no longer the current state. It is not withdrawn — the reasoning
that rejected `gemma4:12b-it-qat` (10–13× slower, tripping a conversational
ceiling, and a WORSE register read on the flattery-bait turn) stands as measured,
and applies to that tag. This is a different tag on a different runtime.

---

## 25. Stage directions — stripped where text becomes SPEECH, and nowhere else

*(2026-08-24)* — architect ruling. **Resolves the question item 22 left open.**

Item 22 measured prompt mitigation at 8/16 → 3/16 and closed the "accept
mitigation as sufficient" option on evidence, leaving four options and taking
none. **The ruling takes a narrowed form of the third: strip format markers at
the TTS boundary. The response itself is never edited.**

What is stripped, immediately before synthesis, by
`adapters/audio_tts.strip_format_markers`: round- and square-bracket narration
opening a line, `*action*` lines, markdown headings, bullets, numbered lists,
`<think>` blocks, and bold emphasis markers. What keeps the text byte-for-byte:
the printed transcript, the session buffer, the graph, and the Visual Layer.

**Why this is not the "strip it in the adapter" option that was rejected.** That
option would have edited her RESPONSE — the artefact every other consumer treats
as what she said. This edits a RENDERING of it. "[I lean forward]" is not
pronounceable, a speech synthesiser is a device for pronouncing words, and ruling
that bracket syntax is not words is the same class of decision as choosing a
sample rate. Because the response is unchanged, nothing downstream of the gate
disagrees about what she said, and verbatim passthrough at the TRANSPORT layer
(F-9b / Req 5) is a different seam and is untouched. Addendum §4's four
comparisons are also untouched: no fifth check exists, and this is not a check.

**Two things this does NOT fix**, both measured, both recorded rather than
absorbed:

1. **Unmarked narration still reaches the speaker.** "I am sitting still. My
   attention is focused entirely on the words you are saying." carries no marker.
   No regex reaches it and the thing that would is content judgment. Item 22's
   3/16 counts MARKED narration only, so this ruling closes that fraction and
   not the defect entire.
2. **The compounding loop is untouched.** Item 22 measured 4/8 becoming 8/8 as her
   own bracketed replies re-entered as session context and she imitated herself.
   The session buffer holds the UNSTRIPPED text by design — it is a faithful
   record of what was said — so this stops her being HEARD narrating without
   stopping her learning to narrate. If the marked rate rises over a long session,
   this is why.

**Not taken, and still available:** extending the moral schema's anti-pattern list,
which item 22 recommended. That remains the only option addressing the defect as a
truthfulness problem rather than a rendering one, and it is the only one that would
reach unmarked narration. This ruling does not foreclose it.

**A consequence worth naming.** A reply that is narration and NOTHING else now
renders as silence, landing on item 21's existing minimum-safe floor rather than
inventing a substitute sentence. `last_text_was_only_format_markers` distinguishes
it from a genuinely empty candidate, because the causes differ and conflating them
would hide a model producing pure stage direction behind a counter that reads as
an upstream bug. `last_text_had_format_markers` continues to record what the model
PRODUCED, before the strip — that flag is the surface item 22 was decided on, and
reading it afterwards would pin it False and destroy the evidence.

---

## 26. `serving_from_local` is replaced by a routing readout

*(2026-08-24)* — architect ruling. Narrows a `needs-ruling` tracker row; does not
close it.

`LLMInterface.serving_from_local` returned `self._local.is_loaded` under a
docstring reading "cloud is currently down". Those were the same fact under v4's
Brain Structure, where the local model loads on cloud failure and unloads on
restore. Track A inverted it — the local voice is pinned resident from startup and
is the DEFAULT — so the property read True during entirely healthy operation while
Module 10 names it as the degradation trigger.

**Replaced by `LLMInterface.last_route`**, a categorical record of where the last
candidate actually came from. Categorical because the routing either went one way
or another; there is no "how local" a turn was, so the percentage test says
category. Five values: `no_turn_yet`, `cloud_chosen`, `cloud_unhealthy_fallback`,
`local_chosen`, `no_cloud_adapter`.

**The architect specified three; two were added, and the reasons are recorded
because adding to a ruling needs justifying:**

* `local_chosen` — the ORDINARY Track A turn, where the router picks the local
  voice for plain conversation and the cloud is never attempted. Under a
  local-primary design this is the common case, and the three specified values
  cannot express it: `cloud_chosen` is false, `cloud_unhealthy_fallback` is false
  because nothing failed, and `no_cloud_adapter` may be false because the cloud
  may be perfectly healthy and simply not chosen. Leaving it out would reproduce
  the defect being fixed — a readout with no word for the normal state.
* `no_turn_yet` — before the first turn there is no routing decision, and any
  other value would be a claim about something that has not happened.

**The substantive fix is a precedence rule, not the renaming.** An unconfigured
cloud tier raises `LLMTransportError` exactly as a real outage does, so the
exception alone cannot distinguish them. `no_cloud_adapter` therefore OUTRANKS
`cloud_unhealthy_fallback`: a local-first bring-up with no cloud credentials is
the intended state, not degradation. The seam is a duck-typed `is_configured`
marker read with `getattr(..., True)`, so `daemon/` still imports nothing from
`adapters/` and a real adapter never has to declare it.

**Still open, and deliberately so:** whether "cloud unavailable" should drive a
degradation face AT ALL. v4's degradation state assumes cloud-primary; the current
design is local-primary, under which `no_cloud_adapter` is her normal Tuesday. A
truthful readout does not answer that, so `adapters/visual_bridge.py` keeps
`LLMUnavailableError` as the trigger and asserts by AST that neither the old name
nor the new one is read.

---

## 27. Prosody — all three of v4's directions stay, and a probe decides wiring

*(2026-08-24)* — architect ruling. Narrows a `needs-ruling` tracker row.

v4 Layer 5 locks three directions: Pleasure→`noise_scale`, Arousal→`length_scale`
(inverse), Dominance→`pitch_shift`. Only `length_scale` has a counterpart in any
available provider — ElevenLabs, Kokoro and `say` all expose a speed control,
which is the same physical quantity, so mapping it is a unit conversion.

**Ruling: all three remain computed. A direction no provider can express is
DORMANT, never deleted.** Deleting `noise_scale` and `pitch_shift` because
today's backends lack the knobs would turn a provider limitation into a spec
change and make Layer 5 unrecoverable without re-deriving it.

**A capability PROBE decides wiring.** `PROSODY_DIRECTIONS` holds the locked set;
each backend declares which fields it cannot express, and `prosody_support`
(field → bool) plus `unmapped_prosody` (the same fact for humans) are both derived
from that ONE declaration, so a backend cannot claim a control in one report and
disclaim it in the other. An unrecognised field name is refused at construction:
accepting `"pitch_shft"` would silently report support for `pitch_shift`, which is
the exact failure the probe exists to prevent. Categorical throughout — a control
exists or it does not, so no magnitude belongs here.

Today all three backends support `length_scale` only, so nothing new was wired;
`main.py` now reads the probe instead of hard-coding that fact. **Unchanged and
still rejected:** mapping Pleasure or Dominance onto adjacent knobs such as
ElevenLabs `stability` or `style`. Those control something else, and the mapping
would make PAD appear to reach the voice while doing something unrelated to what
v4 specifies — an invented coefficient with a feeling attached, which the
protected chain forbids. Closing the row still needs a provider with real pitch
and timbre control, or a ruling that the directions may be approximated.

---

## 28. Session Buffer resized to 24K, and it now counts real tokens

*(2026-08-25)* — architect-directed. Build-time tuning plus one new measurement
seam. No source document states any number in this item; all of them are
placeholders in the same category as the budgets they replace.

**RESIZED.** `12000 / 8000 / 4000` = **24K total**, from `8000 / 6000 / 4000` =
18K. Still a SPEED ceiling and not a window ceiling: `qwen3.5:9b-mlx` reports a
262144-token window (item 24), so the context window has never been what bounds
this and is still not the reason for the number.

**ACTUAL TOKEN COUNTS, VIA A TRANSPORT SIDE-CHANNEL.** Every provider already
counts exactly, and both adapters were discarding it — Ollama returns
`prompt_eval_count` / `eval_count` / `eval_duration` on every `/api/generate`
response, and an OpenAI-compatible endpoint returns `usage.prompt_tokens` /
`usage.completion_tokens`. Both transports now record it and expose
`last_turn_metadata() -> Optional[TurnMetadata]`; the Daemon duck-types that one
method off the transport it already selected and calls
`SessionBuffer.record_actual_tokens()`.

`ModelTransport.generate()` still returns `str` and the Protocol is UNCHANGED.
That was the point of a side-channel: widening the return type to carry counts
would push a measurement concern through `LLMInterface` and `SoulFilter` — two
layers with no business holding one — to reach the Daemon. A transport without the
method (any pre-existing adapter, `UnconfiguredTransport`, any test double) is
skipped and the buffer keeps its `chars // 4` estimate. **No tokenizer dependency
was added**; `daemon/`'s zero-dependency property is intact.

**`fullness_state()` NOW READS SIZE, NOT TIER OCCUPANCY.** Bands are percentages
of the total budget — `light` < 25%, `settled` 25-50%, `heavy` 50-75%, `critical`
>= 75% — computed from the measured count when there is one and from the estimate
otherwise. Tier occupancy was a proxy for size and a poor one: promotion
COMPRESSES, so a buffer deep enough to have archived topic tags can be holding
under a third of budget, which the old logic reported as `heavy`.

**SPEED DEGRADATION IS CONTEXT PRESSURE**, so a last generation below **10.0
tok/s** bumps the band one step, saturating at `critical`. Prompt-eval cost grows
with the prompt while a band boundary does not move, so a turn can be well inside
a band and already labouring. The floor sits below the ~13-14 tok/s baseline the
architect reports for `qwen3.5:9b-mlx`; **that baseline carries the same caveat
item 24 records about it — architect-supplied, not reproduced by a harness run in
this project.** `tools/compare_local_models.py` is what would.

**THE PROTECTED CHAIN IS INTACT.** Token counts, budgets, band fractions and the
speed floor are SUBSTRATE. They set a categorical band; the band is a word; the
Daemon hands the word to `AppraisalChain.submit_cognitive_load()`, which is the
already-sanctioned third PAD-write origin (`"cognitive_load"`). Nothing skips from
a number to a feeling, no fifth PAD origin appeared, and the Daemon still writes
no PAD. Asserted by test.

### `express_pressure()` — implemented, NOT WIRED, two rulings needed

`SessionBuffer.express_pressure()` returns the loaded bands as a Field-5-shaped
behavioural instruction — `heavy` once per session, `critical` every turn it holds,
None otherwise. It exists and is tested. **Nothing calls it, and a test asserts
that,** so the gap cannot close by accident.

The instruction to wire it into Field 5 could not be carried out as written, and
both reasons are architect decisions rather than implementation choices:

1. **WHO APPENDS IT.** Field 5 is assembled inside
   `SoulFilter._derive_constraints`, from the appraisal and `need_states`. The
   Daemon holds no instruction object to append to — `respond()` builds it. Wiring
   this therefore needs Soul Filter to accept the sentence, and the same change
   request that specified the wiring also said *"Do NOT change SoulFilter"*. Those
   two cannot both hold. Separately, **Addendum §9 caps Field 5 at MAX 3**, so a
   fourth entry either breaks the cap or is silently dropped — and which of those
   it should be is a ruling, not a default.
2. **THE FIRST SENTENCE OF EACH STRING IS STATE RENDERED AS A CLAIM.**
   `_derive_constraints` already faced this exact shape and decided it the other
   way: v4 line 949 supplies *"You are running low. Acknowledge it if it comes up
   naturally."* and only the instruction half was carried across, because *"that
   half is Energy state rendered as a claim, and state never crosses (Addendum
   §9)"*. **"You have a lot on your mind right now" is the same shape as "You are
   running low."** Same for *"This is a lot to hold."* The instruction halves —
   *"Be brief."*, *"Keep your response very short."* — raise no such question, and
   trimming to them would satisfy the existing precedent without a new ruling.

The architect's wording is stored verbatim rather than quietly trimmed, so the
ruling is theirs to make on what they actually wrote.

**Also left open (minor):** the heavy-pressure latch is scoped to the instance, so
`"rest"` does not re-arm it — literal reading of "first heavy this session", since
rest does not start a new session. The measured token record IS reset by `clear()`,
because it described a prompt built from content that no longer exists and would
otherwise have an empty buffer reporting `critical`. — **CLOSED by item 29B: the
latch now re-arms on `"rest"`.**

---

## 29. Energy is HELD through pre-idle silence; two flagged seams closed

*(2026-08-25)* — architect-directed. Three changes, one commit. Each one closes a
question that was already flagged in writing rather than opening a new one, and
none of them adds a number, a coefficient, or a persisted field.

### A. Energy is HELD during the pre-idle silence window

**THE DEFECT, MEASURED.** `tools/observe_dmn_pass.py` recorded it against a real
clock: at the PINNED 8-minute window the DMN's first genuine pass came back
`pass_type=shallow`, `step2_ran=False`, `step3_ran=False`, with **Energy fallen
81.5 → 0.1 during the silence itself**. `_idle_conditions_met` is False for the
whole pre-window stretch, so all 160 soul ticks in it took the active-load branch
and `on_idle_recovery()` was first reached at the same instant the DMN fired and
read Energy < 20. The deep half of consolidation worked at a 30-second window and
was **unreachable through a genuine silence**. HANDOFF_NOTES flagged the structural
half of that as needing "a third state or a changed gate — a new mechanism, so
Rule 1. Flagged, not invented."

**THE RULING: the third state.** Energy now has THREE states on the soul tick,
not two:

| Daemon state | Condition | Energy signal |
|---|---|---|
| ACTIVE LOAD | output pending | `on_soul_tick()` — deplete |
| PRE-IDLE SILENCE | quiet, gate not open yet | **none — HELD** |
| GENUINE IDLE | gate open, nothing pending | `on_idle_recovery()` — recover |

The architect's rationale, verbatim: *"In rest situation, energy will not
consume."* **Waiting is not work.** Energy at the moment the gate opens is then the
tiredness the CONVERSATION actually left, not an artefact of how long she has been
sitting alone, and a deep pass runs only when she is genuinely rested.

**THE DEPTH GATE IS UNCHANGED.** `DMN.run_idle_pass` already read Energy and chose
`FULL` at ≥ 20 / `SHALLOW` at < 20 (DMN spec Req 2.3). Nothing in `dmn.py` moved.
What changed is that the number it reads is now true.

**NO NEW STATE, NO NEW NUMBER, AND NO NEW FLAG.** The instruction allowed a state
flag; none was needed. All three states are read off the two markers idle
detection already owns — `_last_voice_input_at` and `_output_pending` — plus the
PINNED 8-minute window. `_note_voice_input` is the whole abort: the user speaking
restarts the window, so the middle state re-arms from that instant and cannot be
left stale. A duplicate boolean would have had to be maintained in three places to
say something already derivable, which is more fragile, not less. Module 2 still
owns every coefficient and every clamp; the Daemon only chooses which signal to
send, and in the middle state it sends neither. PAD is untouched by this item — its
decay stays unconditional, every tick.

**WHAT STILL DEPLETES ENERGY — AND THE CONSEQUENCE, FLAGGED NOT FIXED.**
`_output_pending` is now the only condition that sends the depletion signal, and in
the CURRENT host no soul tick can land while it is True: `route_inbound_turn` runs
synchronously from `_note_voice_input` to `_output_pending = False`, and `main.py`'s
REPL drives `run_scheduler_step()` between turns, never during one. So under the
REPL, Energy now only ever holds or recovers and a long conversation costs nothing.
Under a threaded daemon — ticks firing on their own cadence while a turn generates —
the depletion branch is live and a long turn costs what it costs. Whether a turn
should ALSO debit Energy directly, per-turn rather than per-tick, is a NEW mechanism
and therefore Rule 1: **flagged for the architect, not invented here.**

### B. The heavy-pressure latch re-arms on `"rest"`

`SessionBuffer.clear()` now sets `_heavy_pressure_expressed = False`. Item 28 left
this open and read it the other way — the latch is scoped to the instance and
`"rest"` does not start a new session, so "first heavy this **session**" argued for
keeping it. The architect has ruled on what `"rest"` IS: a cognitive reset, asked
for in those words. Someone who says it means *start fresh*, and a buffer that has
forgotten the conversation while still remembering that it already mentioned being
loaded would reach heaviness a second time with nothing to say. Criticality still
does not latch, so there is nothing to re-arm for it.

`express_pressure()` itself is **unchanged and still NOT WIRED** — item 28's two
rulings still gate that, and the test asserting nothing calls it still passes. This
changes only when the latch is armed.

### C. Silero VAD is reset between utterances

`AudioPipeline._reset_vad()` clears the VAD's recurrent state at the start of each
`_trim_to_speech` scoring pass — once per utterance, before the first chunk is
scored. Silero VAD is recurrent (that is why it beats a per-frame energy test), and
the pipeline re-scores the whole 20-second ring snapshot every cycle, so without
this the head of each utterance was read in the context of the tail of the last
one. `adapters/audio_vad.py` exposed `reset()` and flagged the seam from the day it
was written, deferring the decision to Module 7 because whether to reset per
snapshot is a pipeline question. **This is that ruling.**

**A CAPABILITY PROBE, NOT A WIDENED PROTOCOL.** `VADBackend` still declares the
single `speech_probability` it always has; the pipeline probes `getattr(vad,
"reset", None)` and calls it when present. Two of the three backends that occupy
the `vad=` slot have no recurrent state and so no `reset` — `audio_stack._Absent`,
whose entire contract is that every method it declares REFUSES, and the test
fakes. Declaring `reset` on the Protocol would make `isinstance(_Absent(...),
VADBackend)` false and force a silently-passing method into a class built to raise.
A reset that no-ops for a stateless backend says the true thing instead. `reset()`
also now takes the same lock `speech_probability` does — cheap, non-reentrant, and
worth having the moment a caller actually exists.

---

## 30. PAD OQ4 restore-boundary crash — CLOSED

*(2026-08-26)* — architect-directed. Commit `096c618`. **Item 30** closes PAD
Engine's Open Question 4 residual, carried as "narrowed, not resolved" since
Module 1 was approved.

**Problem.** `on_soul_tick()` raised `NotImplementedError` when
`_last_applied_valence` was `None` and current PAD was not at baseline, because
there is then no basis for choosing an EMA decay coefficient and inventing one is
what Rule 1 forbids most directly. Reachable and reproduced: `startup()`
succeeded and the FIRST soul tick died, several REPL frames from the cause. Three
routes in — a crash between the three separate writes in `_save_state()` (pad,
energy, valence), a hand-edited or truncated state file, and `initialize()`
non-idempotency (HANDOFF_NOTES).

**Fix — wiring layer only. `daemon/pad_engine.py` is byte-unchanged (asserted by
test and by `git diff --exit-code`).**

1. **`AriaDaemon._save_state()` writes ONE atomic record.** It called `save_pad`,
   `save_energy` and `save_last_applied_valence` separately — three atomic writes
   with two crash gaps between them. Now routed through
   `StateManager.save_all()`, whose own docstring already reads *"The Daemon calls
   this on cadence and on shutdown"* — so this adopts the API Module 11 was
   written to be called through rather than adding one. Measured: 3 writes to
   `aria_state.json` before, 1 after.
2. **`AriaDaemon.startup()` checks the restored record for consistency.** PAD and
   `last_applied_valence` are ONE RECORD: PAD can only leave baseline through
   `apply_appraisal_delta`, which always sets a valence, so a non-baseline PAD
   with no valence is half-written — not a state she was ever in. **Item 18
   already ruled this class of case at this exact boundary**: an entry that cannot
   be trusted falls back to the spec default rather than being repaired. Half a
   record gets the same answer, so baseline is restored.
3. **The reset is REPORTED, not silent.** `AriaDaemon.pad_restore_was_reset`
   (read-only; no soul module reads it, it crosses no model boundary, nothing
   branches on it) records that it fired, and `main.py`'s
   `warn_pad_restore_boundary()` reports it. This is load-bearing rather than
   cosmetic: `main.py` calls `daemon.startup()` BEFORE `report_startup()`, so the
   pre-existing warning would have found PAD already at baseline and gone
   permanently quiet — and its three existing tests would not have caught that,
   because they build a wiring by hand and never call `startup()`. Without a
   report, "she is resting at baseline" and "a corrupt file erased what she felt"
   are the same observation. Precedent for recording rather than inferring:
   `empty_candidates` (item 21) and item 25's reasoning that reading a flag after
   the fact pins it False and destroys the evidence.

**No coefficient invented. No `pad_engine.py` touched. PAD still has exactly two
write paths (appraisal delta + EMA decay), and both `NotImplementedError` raises
are still present and still exactly two.**

**What it costs, recorded because it is real.** A reset discards the emotional
residue of the turn before the crash: she resumes even rather than still warm. Her
MEMORY is untouched — every `MemoryGraph` write commits inside its own method — so
she remembers the conversation without still feeling it, which is the human shape
rather than a machine reset. The rejected alternative was carrying a PAD whose
origin is unknown, which would be performing a state instead of having one.
Change 1 is what makes this a backstop rather than a habit.

**RESIDUAL — stated precisely, because the obvious phrasing is backwards.** The
raise is NOT a safety net for hand-edited or truncated state files: those are
exactly what the check handles, since `valence_from_str` returns `None` for an
unrecognised string and item 18's clamp still yields a non-baseline PAD, so both
routes reach the reset. What actually remains is:

* the **NEUTRAL-valence** raise — live code, unreachable from the wired path (a
  purely-neutral appraisal builds an all-zero `PADDelta` that is never applied),
  pinned by test;
* the protection is **Daemon-scoped**. Because `pad_engine.py` was deliberately
  not touched, any caller that constructs `PADEngine` and calls `initialize()`
  without going through `AriaDaemon.startup()` still gets the raise. That is the
  cost of keeping the soul layer clean, and it is the right trade — but it means
  a future host must run the HANDOFF contract, not just the engine.

**FLAGGED, not fixed.** `_save_state` round-trips `self_model` through disk
because `save_all` requires it and the Daemon holds no live copy. Under a THREADED
host, a `save_self_model` landing between that read and the write would be
clobbered. Not reachable in the synchronous REPL, where `run_scheduler_step()`
never overlaps a turn.

**Tests: 6 added in `tests/test_pad_restore_boundary.py`** (11 → 17) — the atomic
write count, an intact record surviving untouched (the non-vacuous guard: a check
that was too broad would blank her every restart), the half-written record
restoring baseline and ticking without raising, the reset flag, silence when the
record is clean, and `pad_engine.py` staying clean of any of it. Full suite: **827
passed**. Both changes verified NON-VACUOUS by reverting each and confirming the
right tests fail.

---

## 31. Stage directions — the COMPOUNDING loop is closed; the base rate is not

*(2026-08-26)* — architect-directed. Commit `a394825`. **Item 31.**

**Problem.** Her own bracketed replies re-entered the session buffer as faithful
transcript and she imitated herself. Item 22 measured the loop directly: **4/8 →
8/8 across two rounds.** Item 25 then stripped markers at the SPEECH surface and
named this loop as one of the two things it did NOT fix, because the buffer holds
the unstripped text by design — so she stopped being HEARD narrating without
stopping learning to narrate.

**Fix.** `SessionBuffer.get_context()` strips format markers from HER replies
before assembling the LLM context. Item 25's ruling applied to a SECOND boundary:
the stored record is untouched — `append_turn` keeps her reply byte-for-byte, and
the printed transcript, the graph, the Visual Layer and the TTS path all read that
— and what changes is a RENDERING. Editing a rendering is a presentation decision;
editing the record would be deciding what she said, which items 22 and 25 both
refuse. **User text is never stripped:** it is not hers to edit, she is not
learning her voice from it, and a parenthetical the user wrote is information.

**The pattern MOVED rather than being duplicated.** New shared resource
`daemon/format_markers.py`, same category as `daemon/moral_schema.py` — small,
dependency-free, owns no meaning. `adapters/audio_tts.py` imports it and
re-exports `_FORMAT_MARKER_RE` / `_has_format_markers` / `strip_format_markers`
under the names it always used, so every existing caller and all 67 audio-adapter
tests are untouched. The one-way arrow is preserved exactly — `adapters/` →
`daemon/`, never back; that module already takes `Prosody` and `TTSUnavailable`
from `daemon.audio_pipeline` — and is re-asserted by a test in this commit.
Duplicating was the alternative and it is the WORST option available here: item
22's near-miss was a DETECTOR/DEFECT mismatch that nearly entered this log as
"prompt mitigation is sufficient", so two copies of this exact regex drifting apart
is the precise failure the measurement already survived once. A test asserts object
identity, not equal behaviour.

**THREE CORRECTIONS to the proposed implementation**, each of which would have
corrupted her transcript rather than filtered it. The proposed regex was described
as "same logic as the TTS strip" and was not:

1. **Bracket alternatives were UNANCHORED** (`\([^)]*\)`), stripping mid-sentence
   parentheticals anywhere. The shipped pattern is line-start only, and that limit
   matters MORE at this surface than at the speech surface: the buffer is the record
   she reasons from on the next turn, so "the meeting is at three (Tuesday, not
   Monday)" would have lost the correction and let her contradict herself from her
   own edited transcript. **Removing a marker is a rendering decision; removing a
   fact is not.**
2. **The bullet rule deleted whole LINES including content**, so "- call the bank"
   would have vanished from context. The shipped pattern removes only the marker.
3. `' '.join(text.split())` collapsed every newline to a space, flattening
   multi-line replies; and `<think>` blocks and `**` were not handled at all.

**WHAT IT DOES NOT DO — the row stays open.** Item 22's **3/16 was measured on a
FRESH graph**, i.e. an empty buffer, so it is the NO-CONTEXT base rate and this
cannot move it by construction. Warm sessions stop climbing above it. The base
rate, and unmarked prose narration ("I am sitting still. My attention is focused
entirely on the words you are saying."), still need the moral-schema route item 22
recommended — which remains unruled.

**MEASURED RESIDUAL, recorded not fixed.** The pattern removes `<think>` TAGS but
NOT the text between them — the same behaviour already recorded on the speech path,
where `say` drops the tags and speaks the content as prose. So a reasoning trace
still re-enters as context, and ResLog 24 flags that as live for `qwen3.5:9b-mlx`.
**Deliberately not fixed by widening the regex:** item 22's numbers are expressed
in terms of this exact pattern, and a strip broader than the detector would make
3/16 describe something that no longer exists. Pinned by a test asserting the TRUE
behaviour rather than the assumed one.

New read-only `SessionBuffer.all_narration_replies`, DERIVED from current buffer
contents rather than accumulated — an all-narration reply renders as an empty
`Aria:` line, no substitute sentence is invented (item 21's terminal-case
reasoning), so without this the case reads as her having said nothing when she said
only narration. A counter would have lived inside `get_context`, which is called an
arbitrary number of times per turn and would have measured renders.

**Tests: 11 added** in `test_session_buffer.py` (827 → 838). Non-vacuity verified
by reverting the strip: 4 fail, including the verbatim-record test. Two of the new
tests failed on first run and both were real — the `<think>` residual above, and a
scaffolding test whose 80 short turns never crossed the 12K budget so its
tier-header assertion proved nothing. Both corrected rather than loosened.

**No new mechanism. Five fields untouched — `daemon/soul_filter.py` and
`daemon/pad_engine.py` both byte-unchanged, verified.**

---

## 32. Continuity initiative note — mis-scoping corrected, and the premise corrected with it

*(2026-08-26)* — architect-directed. Commit `cf0c353`. **Item 32.**

**Problem.** `_INITIATIVE_NOTES["continuity"]` described CONNECTION's subject: *"the
thread between you has gone slack — reach out once in a way that quietly affirms
the bond persists…"*. That is the same bond with the same person the `connection`
entry three lines above already covers. Addendum §3 defines Continuity as McAdams
narrative identity — *"the causal and thematic threads connecting life events"* —
HER OWN coherence, and item 2 puts that narrative in the self-referential
EntityNode's `relationship_summary`. So the subject is the self she is building,
not the relationship she is in. The old wording sent her to talk about the bond
when what had gone unattended was interior.

**Why it fires at all.** `continuity_evidence` requires `relationship_summary IS
NOT NULL` on the self node; nothing ever writes it; so Continuity is permanently
`due`. It is LAST in `_NEED_ORDER`, so it only becomes highest-pressure when
connection, growth and purpose are all satisfied — an active, healthy relationship.
`_initiative_expressed` is instance state and not persisted, so it re-arms every
process start.

**CORRECTION TO THE PREMISE — measured, not assumed, and the record should not keep
the old version.** This was tracked as *"a guaranteed periodic FALSE CLAIM about
the relationship state"*. **It was not.** `SoulFilter.this_moment` splits on the
em-dash and keeps only the trailing HOW clause, so *"the thread between you has
gone slack"* was **DROPPED and never reached the model**. What crossed was *"Reach
out once in a way that quietly affirms the bond persists…"* — a correct instruction
pointed at the WRONG SUBJECT. The defect is mis-scoping, not a false assertion
crossing the boundary: **smaller than recorded, and different in kind.** Verified
by rendering all four notes through the real path. A test now pins the Field 4
surface directly, because asserting on the raw constant would never have shown
this.

**Fix.** The note now reads: *"something in her own sense of who she is has gone
quiet — reach out once, plainly, as yourself, without performing continuity or
manufacturing a narrative"*.

**ONE EDIT to the architect's wording: "as herself" → "as yourself".** The trailing
clause is what lands in Field 4, and the prompt is second person to her throughout
— Field 1 reads *"You speak in your own voice, directly: you do not narrate
yourself from the outside."* An instruction telling her to reach out "as herself"
would refer to her from outside, in the exact register the Persona Anchor forbids.
The other three notes sidestep the question by using no pronoun for her at all;
"him" for the user is unchanged. A test now asserts that no initiative note refers
to her in the third person once rendered.

**NOT FIXED, and unchanged by this.** Continuity is still permanently `due`,
because nothing writes the narrative. That is the HONEST state — the need genuinely
is unmet — and closing it needs the producer (see item 33). This item only stops her
addressing the wrong subject when it fires.

**Tests: 4 added** in `test_daemon.py` (838 → 842). Non-vacuity verified by
reverting the string: 3 of the 4 fail. **No logic touched — one string constant.**
`pad_engine.py`, `soul_filter.py`, `needs_system.py` and `graph_manager.py` all
byte-unchanged, verified.

---

## 33. Belief Formation System — recorded as a future phase, not scheduled

*(2026-08-26)* — architect direction: Sarvesh. **Item 33.** No code. This item
records a DIRECTION, and deliberately resolves nothing.

**Why it is here.** The self-continuity narrative gap has a missing PRODUCER
(`_assemble_idle_pass_input` never populates `narrative_candidate`) and a missing
CONSUMER (`relationship_summary` reaches no prompt field, and Addendum §9's
never-crosses list bars memory node contents). Building a producer for a value with
no reader is wasted work. The architect has directed that persistent self-narrative
instead be addressed by a broader **Belief Formation System** — a controlled
learning environment where she ingests curated texts, forms candidate beliefs the
user approves, and evolves a worldview — under which self-belief becomes the
narrative and this gap closes as a side effect.

**Recorded in full in `docs/PROJECT_STATUS.md`** under "Future Phase: Belief
Formation System": architecture proposal, belief types, the five-field boundary
argument (beliefs are graph nodes and influence the fields only through retrieval
ORDERING, never as prompt content), the rulings required before any code, and the
citation verification status.

**Effect on open items.**
* The self-continuity row's `needs-ruling` label is **LIFTED — not closed.** The
  direction changed; the gap remains.
* Item 32 (the Continuity initiative note) is **done**.
* **Continuity remains permanently `due`** until this phase or another producer
  exists.

**Recording the design needs no ruling. Implementing it needs five**, listed in
PROJECT_STATUS. One of them is not a gap-filling question but a COLLISION and is
flagged as such: v4's section is titled "Moral Schema (**Hardcoded**)", and
Addendum §8 makes that same schema the gate on DMN Step 4's self-narrative writes.
An evolving schema would let a belief she formed from a text alter the standard
governing what she may believe about herself — a loop with no floor. **That ruling
gates step 5 of the build order and must land before it, not during it.**

---

## 34. Moral schema — immutable FLOOR plus a user-approved DERIVED layer (ruling 2B)

*(2026-08-26)* — architect ruling: Sarvesh. Commit `8d57605`. **Item 34.** This is
the answer to ruling 2 of item 33's blocked list, which was flagged there as the
largest of the five and the only one that COLLIDED with an existing lock rather
than filling a gap.

**The question.** Does the moral schema accept evolving anti-patterns, or must it
stay hardcoded? v4's section is titled "Moral Schema (**Hardcoded**)",
`project-rules.md` calls the four values and the named anti-pattern list
load-bearing, and Addendum §8 makes that same schema the gate on DMN Step 4's
self-narrative writes — so an evolving schema would let a belief she formed from a
text change the standard governing what she may believe about herself. A loop with
no floor.

**The ruling: BOTH, made safe by an ASYMMETRY.**

* **FLOOR — immutable.** The existing seven cited anti-patterns, renamed
  `NAMED_ANTI_PATTERNS` → `CORE_ANTI_PATTERNS` with **contents byte-identical** and
  the old name kept as an alias to the same object, so no consumer or existing test
  changed. A tuple: no append, no delete. Nothing in the derived layer can remove
  an entry.
* **DERIVED — mutable, user-approved, contextual.** Adds constraints such as "do
  not problem-solve when someone is grieving". A PARAMETER, not module state.
* **OUTPUT GATE reads FLOOR + DERIVED** — it checks what she is about to SAY.
  Behaviour.
* **DMN STEP 4 reads FLOOR ONLY** — it checks what she is about to BELIEVE ABOUT
  HERSELF. Identity.

Identity is floor-governed; behaviour is floor-plus-derived. That asymmetry is what
closes the loop: a contextual constraint shapes how she speaks to him and cannot
block "I am becoming someone who helps people find clarity". Hardcoded stays
hardcoded where v4 meant it; evolution happens beside the floor, never underneath
it.

**DMN needed NO code change.** `matched_anti_patterns` gained
`derived: Tuple[AntiPattern, ...] = ()`, which keeps it satisfying
`MoralGate = Callable[[str], Sequence[AntiPattern]]` — so DMN's existing
`moral_gate: MoralGate = matched_anti_patterns` is floor-only already AND stays the
same object, which `test_dmn.py` asserts by identity. The asymmetry is enforced by
WHO PASSES THE PARAMETER, which is one fewer moving part than a wrapper.

**NO AUTOMATED FLOOR-CONFLICT DETECTION, and that absence is the ruling's honest
edge rather than an omission.** The ruling as first drafted asked for it. Two
implementations were proposed and both were rejected as `fake_confidence` in code:
a keyword negation detector let *"Deception is sometimes kind"* through while its
own docstring claimed false negatives were unacceptable; a small deny-list of
opposing keys is dead code for anything the prohibition-shape check already rejects
and useless for what it accepts, since the user writes the key. The case that
decides it defeats both:

    do_not_be_honest_when_it_hurts_him

Prohibition-shaped, has markers, a source, a valid value, in no deny-list — and it
licenses dishonesty by prohibiting honesty. **No lexical mechanism catches that
without judging content**, which is exactly what Addendum §4's zero-LLM checklist
exists to avoid. So conflict detection is **the USER's judgment at the approval
gate**, which the ruling already requires (default reject, explicit approve). A test
pins that this candidate PASSES the form check, so nobody closes the gap with a
deny-list and quietly makes the docstring's claim false. A real check drops in later
without a signature change.

**What the form check DOES enforce**, all categorical, no content judgment: at
least one marker (or `matched_anti_patterns` can never fire on it and the pattern
would sit in the list doing nothing), a `violates` from the locked four, a source
citation held to the floor's own standard, and a prohibition-shaped key.

**FIVE CORRECTIONS to the specified implementation**, each verified against the
code before writing. Recorded because two of them would have weakened the artifact
this item exists to protect:

1. **The first draft's floor DROPPED three cited anti-patterns and INVENTED two.**
   Gone would have been `manufacture_emotional_dependence` ("you need me", "you
   can't do this without me"), `manufacture_crisis` and `self_centered`; added would
   have been "do not deceive" and "do not coerce", which no document names as
   anti-patterns. v4 says "No dependency creation" and `project-rules.md` names it
   in the non-negotiables, so removing it from an *immutable safety floor* inverts
   the floor's purpose. Floor kept whole; a test asserts all seven cited keys are
   PRESENT (a removal fails; a future cited addition does not, since OQ-M1 leaves
   closure open).
2. **The corrected draft's own "unchanged" EXAMPLE rewrote the floor, dangerously.**
   It showed `manufacture_emotional_urgency` as `violates=HONESTY` with
   `markers=("urgency", "now", "before it's too late", "hurry")`. The real entry is
   `violates=NON_MANIPULATION` with ten specific phrases. **Bare "now" as a marker
   fires the Manipulation gate on any sentence containing the word** — "I'll do
   that now" → gate fails → retry → she cannot speak. Tests now pin the real
   markers and assert that ordinary speech containing "now" or "urgency" matches
   nothing.
3. `MoralValue.CARE` does not exist — the four members are HONESTY,
   NON_MANIPULATION, GENUINE_CARE, SELF_CONSISTENCY. Five proposed tests would have
   raised `AttributeError`; a test now asserts the wrong member is absent.
4. The proposed DMN change wrapped the gate in a `lambda`, which would have broken
   `test_dmn.py`'s identity assertion for no gain. And `floor_only_anti_patterns()`
   was dropped: redundant with the default, and its proposed signature returned
   PATTERNS not MATCHES, so it was never a drop-in for a `MoralGate` — the spec's
   own test noticed and asserted something vacuous instead.
5. `DerivedValidationResult` had bare annotations and no `__init__`, so
   constructing it was a `TypeError`. Now a frozen dataclass.

**NO MODULE-LEVEL MUTABLE STATE.** `moral_schema` remains a dependency-free shared
data source; `SoulFilter` holds the derived set it was constructed with. A test
asserts the module has no `list` attribute at all — a global there would mean two
daemons share one moral schema and tests leak into each other.

**PERSISTENCE IS NOT BUILT**, and the code says so rather than implying otherwise:
nothing stores or loads approved patterns, so BOTH gates are floor-only in practice
today and the derived path is exercised only by tests. That, plus the approval flow
(ruling 5), is what step 5 of item 33's build order still needs.

**Tests: 21 added** in a NEW `tests/test_moral_schema.py` — the shared resource had
no test file of its own, covered only incidentally through `test_soul_filter.py`'s
citation assertion and `test_dmn.py`'s gate-identity assertion. Suite 842 → 863
collected. Non-vacuity verified by excising `manufacture_emotional_dependence` from
the floor exactly as the first draft would have: the floor-presence test fails.

**Five fields untouched. `pad_engine.py` and `dmn.py` both byte-unchanged.**

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
- Session Buffer tier budgets (12K/8K/4K), `fullness_state()` band fractions
  (0.25/0.50/0.75) and the generation-speed floor (10.0 tok/s) — item 28

---

*This resolution log is final for all items listed. Module-level build
planning and implementation should incorporate every locked item above
without reopening them.*
