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
otherwise have an empty buffer reporting `critical`.

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
