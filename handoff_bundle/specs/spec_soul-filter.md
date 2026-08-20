# ARIA locked spec — soul-filter

Consolidated from .kiro/specs/soul-filter/{requirements,design,tasks}.md for upload.
Precedence: ARIA_Resolution_Log.md > ARIA_Soul_Spec_v4_Addendum.md > ARIA_Soul_Spec_v4.md.


---

## soul-filter — requirements.md

# Requirements Document — Module 5: Soul Filter

## Introduction

This document transcribes and formalizes, in EARS format, the Module 5 (Soul
Filter) entry from `ARIA_Module_Build_Plan.md`, applying every locked decision
in `ARIA_Resolution_Log.md` and `ARIA_Soul_Spec_v4_Addendum.md` that bears on
it. That entry is the locked, approved scope for this module. No requirement
here introduces a mechanism, threshold, or behavior that is not already stated
in the Module 5 entry or in the supporting architecture documents
(`ARIA_Soul_Spec_v4.md`, `ARIA_Soul_Spec_v4_Addendum.md`,
`ARIA_Resolution_Log.md`). Where the Module 5 entry references a value or
mechanism defined elsewhere (the five-field format, the four-check gate, the
emergency instruction sets, the moral schema), the supporting document is cited
as the source of that value, not as a new source of scope.

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`.
`ARIA_GLM_Covering_Instruction.md` provides covering context only.

**The inviolable constraint this module lives under (steering/project-rules.md,
"Five-field LLM boundary" + Addendum §9):** the LLM receives EXACTLY five
natural-language fields (Persona Anchor, Behavioral Register, Relational
Register, This Moment, Constraints) plus the user's current message — nothing
else. NUMBERS NEVER CROSS. State never crosses. Personal information never
crosses. Only *meaning*, translated into natural language by Soul_Filter,
crosses. No raw PAD values, no graph data/contents, no relational_stage label,
no needs states as data, no Q1–Q4 outputs, no appraisal vectors, no memory
node contents ever appear in any field. The ONLY personal data that crosses is
the user's current message (Addendum §9). Emergency mode REPLACES the five
fields with the fixed Type A/B/C instruction set; it does not add to them
(Resolution Log item 1).

**The gate this module owns (Addendum §4; Resolution Log item 15):** the Output
Validation Gate is FOUR structural comparisons, each checked against something
Aria's own state ALREADY holds, with ZERO LLM calls (no cloud, no local Gemma)
for the primary mechanism. It VERIFIES; it never DECIDES (Principle 27 — a model
may be asked "does this contradict this specific fact — yes/no?"; it is never
asked "does this sound manipulative?"). The percentage test governs: no numeric
"confidence score" is produced; each check either holds or it does not.

Genuinely undefined items discovered while formalizing the entry — and the
Module 5 flags F-5a/F-5b — are recorded in the **Open Questions**,
**Build-Time Tuning Constants**, and **Flag Disposition Summary** sections,
resolved by the Resolution Log / Addendum where those documents resolve them,
and left as flagged placeholders where they do not. Nothing is resolved by
invention (Rule 1); no document conflict is silently picked (Rule 2).

## Glossary

- **Soul_Filter**: The module specified here (Module 5, `daemon/soul_filter.py`).
  Two jobs (v4 "Soul Filter — Blind Language Renderer"): translator (internal
  state → five NL fields) and gatekeeper (LLM candidate → four-check
  verification). It is the BUFFER between Aria's interior and the LLM (Addendum
  §9, grounded in ACT-R/Soar).
- **Five-Field Instruction**: The normal-operation output — Persona Anchor,
  Behavioral Register, Relational Register, This Moment, Constraints (fixed
  order) + the user's current message (Addendum §9). Implemented as the frozen
  `FiveFieldInstruction`.
- **Persona Anchor (Field 1)**: A fixed character description — who Aria is, her
  values, her voice. Hardcoded once, never generated, never varies turn to turn
  (Addendum §9). Nothing personal crosses.
- **Behavioral Register (Field 2)**: The current PAD state translated to natural
  language descriptors ONLY — e.g. "warm and grounded, unhurried", never
  "Pleasure: 0.6" (Addendum §9). No PAD numbers cross.
- **Relational Register (Field 3)**: `relational_stage` translated to natural
  language — e.g. "the quiet assurance of someone who knows this person well",
  never "stage: bonded" (Addendum §9). No stage label crosses.
- **This Moment (Field 4)**: ONE behavioral instruction maximum, written by
  Soul_Filter from the Appraisal Chain's most-salient output. Tells the LLM HOW
  to respond, never WHAT happened (Addendum §9; flag F-5b, highest-stakes
  translation). No memory contents cross.
- **Constraints (Field 5)**: A closed list of specific prohibitions for this
  turn only, MAX 3, derived from the moral schema and the Output-Gate pre-check.
  Always specific actions, never open-ended (Addendum §9). No graph data/vectors
  cross.
- **PAD_Engine**: Module 1 (`daemon/pad_engine.py`, built/approved). Soul_Filter
  reads the current PAD via its real accessor `get_current_pad()` → `PADSnapshot`
  for the Behavioral Register. Soul_Filter never reads or writes PAD by any
  other path and never mutates PAD.
- **Memory_Graph**: Module 3 (`daemon/graph_manager.py`, built/approved).
  Soul_Filter calls its real interface `get_relational_stage(entity_node_id)`
  (Relational Register) and `reality_contradiction_check(entity_ref,
  candidate_text)` (Honesty check). It reads no graph node contents into any
  field.
- **Appraisal_Chain / AppraisalResult**: Module 4 (`daemon/appraisal_chain.py`,
  built/approved). Soul_Filter consumes the frozen `AppraisalResult` —
  specifically `most_salient_note` (This Moment), `emergency` + `emergency_type`
  (the emergency branch), `social_signals`, `q1`, `q2`, `is_partial_appraisal`
  (Constraints + Care check). Soul_Filter does not re-run any appraisal.
- **Moral_Schema**: The shared resource (`daemon/moral_schema.py`): four values
  (honesty, non-manipulation, genuine care, self-consistency) + the named
  anti-pattern list. Read by Soul_Filter (Output-Gate Manipulation check +
  Constraints) and, later, DMN (Build Plan "Shared resources"; Addendum §8).
- **Output Validation Gate**: FOUR structural comparisons — Honesty,
  Consistency, Manipulation, Care — each against something Aria's state already
  holds, ZERO LLM (Addendum §4). Owned/logic-defined by Soul_Filter, invoked by
  the LLM Interface (Resolution Log item 15). Implemented as `run_output_gate`.
- **Emergency (as appraisal result)**: Not a separate detection subsystem — the
  `emergency` flag + `emergency_type` on the `AppraisalResult` (v4 Emergency
  Detection; Resolution Log item 1). Soul_Filter — not the Appraisal Chain —
  branches the LLM instruction format on it.
- **Type A/B/C Instruction Sets**: The three fixed emergency instruction sets
  (v4 "The Three Emergency Instruction Sets"), each exactly three instructions.
  Type A = physical/safety; Type B = mental-health crisis (also the default);
  Type C = acute decision/irreversible action. They REPLACE the five fields
  (Resolution Log item 1).
- **NeedStates**: The injected CONTRACT for Module 2 (Needs System — built and tested; see
  `daemon/needs_system.py` and `tests/test_needs_system.py`). Four categorical needs
  (satisfied/due/neglected, Addendum §3) + Energy
  (continuous substrate). Soul_Filter reads Energy only via the in-spec <30/<20
  operational gate (Addendum §3), translating it to NL — the number never
  crosses.
- **LLMClient**: The injected CONTRACT for Module 9 (LLM Interface — built and tested; see
  `daemon/llm_interface.py` and `tests/test_llm_interface.py`). A blind generator:
  `generate(instruction, user_message) → str`
  (Build Plan Module 9). Receives exactly one `LLMInstruction` + the user
  message; nothing else (Rule 5; Resolution Log item 14).
- **Reconsideration Sound**: A short "self-correction" sound the Daemon plays to
  fill retry latency (v4 "Self-Correction Sound"). Soul_Filter emits a trigger
  to the Daemon on any retry (Build Plan Module 5 output); modelled as an
  injected `on_reconsideration` callback.
- **Minimum Safe Output**: The three-instruction floor ("Acknowledge what was
  said. Be brief. Be honest. Do not elaborate.") activated on double gate
  failure (v4 "MINIMUM SAFE OUTPUT MODE").

## Requirements

### Requirement 1: Five-Field Assembly (Fixed Order, Nothing Else)

**User Story:** As Soul_Filter, I want to emit exactly five natural-language
fields plus the user's message, so that the LLM receives meaning as language and
never Aria's internal state.

#### Acceptance Criteria

1. WHEN operating normally (not emergency), THE Soul_Filter SHALL assemble
   exactly five fields in the fixed order Persona Anchor, Behavioral Register,
   Relational Register, This Moment, Constraints, plus the user's current
   message, and nothing else (Addendum §9; Rule 5).
2. THE Soul_Filter SHALL emit the user's current message as a SEPARATE element,
   never folded into any of the five fields — it is the only personal
   information that crosses (Addendum §9 "What the LLM also receives").
3. THE Soul_Filter SHALL NOT place into any field any PAD value, graph node id
   or contents, relational_stage label, needs state as data, Q1–Q4 output or
   value, appraisal vector, memory node contents, or historical conversation
   summary (Addendum §9 "What never appears in any field"; steering "Five-field
   LLM boundary").
4. THE Soul_Filter SHALL emit no numeric digit in any of the five fields
   (Addendum §9 "NUMBERS NEVER CROSS") — the boundary test that operationalizes
   criterion 3.

### Requirement 2: Behavioral Register (PAD → Natural Language)

**User Story:** As Soul_Filter, I want to translate the current PAD into a felt
descriptor, so that the LLM feels Aria's state without ever seeing its numbers.

#### Acceptance Criteria

1. THE Soul_Filter SHALL obtain the current PAD via `PAD_Engine.get_current_pad`
   and SHALL NOT read or mutate PAD by any other path (steering PAD-purity).
2. THE Soul_Filter SHALL render the Behavioral Register as natural-language
   descriptors only (e.g. "warm and grounded, unhurried") and SHALL NOT include
   any PAD number, coordinate, or axis name (Addendum §9).
3. THE Soul_Filter SHALL derive the descriptor by comparing each PAD axis to the
   spec-locked `PAD_BASELINE` [0.55, 0.45, 0.58] as the ONLY reference, yielding
   a categorical above/at-or-below descriptor per axis, and SHALL NOT introduce
   any new banding cutoff or threshold (steering "No invented numbers"; passes
   the percentage test — an axis is either at/above baseline or below it).

### Requirement 3: Relational Register (relational_stage → Natural Language)

**User Story:** As Soul_Filter, I want to translate the relationship's stage
into a felt register, so that the LLM speaks at the right depth without seeing
the stage.

#### Acceptance Criteria

1. THE Soul_Filter SHALL obtain `relational_stage` via
   `Memory_Graph.get_relational_stage` for the turn's entity and SHALL render it
   as a natural-language register (Addendum §9), using the addendum's
   BONDED example verbatim for the bonded stage.
2. THE Soul_Filter SHALL NOT include the stage label
   (observing/engaging/invested/bonded), the string "relational_stage", any
   relationship history, or any memory of past interactions in the Relational
   Register (Addendum §9 "What never crosses").
3. WHEN no entity/stage is available for the turn, THE Soul_Filter SHALL use the
   most reserved register (a fresh contact), never presuming closeness.

### Requirement 4: This Moment (One Behavioral Instruction, Never What Happened)

**User Story:** As Soul_Filter, I want to write a single HOW-to-respond
instruction from the appraisal's most-salient output, so that the LLM engages
the moment correctly without receiving any memory of it.

#### Acceptance Criteria

1. THE Soul_Filter SHALL write This Moment as at most ONE behavioral instruction,
   derived from `AppraisalResult.most_salient_note` (Addendum §9; F-5b).
2. THE Soul_Filter SHALL ensure This Moment tells the LLM HOW to respond and
   never WHAT happened, and SHALL NOT include memory contents, past
   conversations, specific events, or personal history (Addendum §9). Where the
   most-salient note carries a generic "what" clause before an HOW clause, the
   HOW clause SHALL be preferred.
3. THE Soul_Filter SHALL rely on the Appraisal Chain's `most_salient_note` — a
   memory-free qualitative behavioral hint — as the ONLY source for This Moment,
   and SHALL NOT read graph event descriptions or `appraisal_q4_notes` to
   populate it (Addendum §9; appraisal_chain._most_salient_note is memory-free
   by construction).

### Requirement 5: Constraints (Moral Schema + Gate Pre-Check, Max 3)

**User Story:** As Soul_Filter, I want to send at most three specific
prohibitions derived from the moral schema, so that the LLM is pre-empted from
the very violations the gate would otherwise catch.

#### Acceptance Criteria

1. THE Soul_Filter SHALL derive the Constraints from the moral schema and the
   Output-Gate pre-check, as a closed list of at most THREE items (Addendum §9).
2. THE Soul_Filter SHALL express each Constraint as a specific action
   prohibition (e.g. "do not problem-solve, do not minimize, do not deflect"),
   never an open-ended instruction (Addendum §9), and SHALL include no graph
   data, appraisal vector, or node contents.
3. WHEN the appraisal flags a vulnerability disclosure or distress, THE
   Soul_Filter SHALL derive care-protecting prohibitions (Addendum §9 example);
   WHEN it flags a reality contradiction, honesty-protecting prohibitions;
   WHEN the appraisal is partial/uncertain, a do-not-fake-confidence
   prohibition (v4 soul_filter table); otherwise a baseline anti-manipulation
   floor drawn from the named anti-patterns.
4. WHEN `NeedStates.energy` is below the in-spec 30 operational threshold and
   room remains under the max of three, THE Soul_Filter SHALL append a "do not
   overextend" prohibition, translating the threshold to natural language — the
   Energy number SHALL NOT cross (Addendum §3; v4 soul_filter table).

### Requirement 6: Emergency Branch (Mutually Exclusive, Before Field Assembly)

**User Story:** As Soul_Filter, I want to branch to the fixed Type A/B/C
instruction set the instant the appraisal flags an emergency, so that a
catastrophic prediction error is met with presence, not with the five fields.

#### Acceptance Criteria

1. WHEN `AppraisalResult.emergency` is true, THE Soul_Filter SHALL branch BEFORE
   assembling any of the five fields and SHALL emit the fixed Type A/B/C
   instruction set INSTEAD of the five fields (Resolution Log item 1).
2. THE Soul_Filter SHALL treat the five-field instruction and the emergency
   instruction as MUTUALLY EXCLUSIVE outputs of one branch — never both, never
   emergency added to the five fields (Resolution Log item 1).
3. THE Soul_Filter SHALL map `emergency_type` to the instruction set as
   PHYSICAL_THREAT → Type A, EXISTENTIAL_DISTRESS → Type B, DECISION_CRITICAL →
   Type C, UNCLASSIFIED → Type B, and SHALL default a missing/None type to
   Type B (v4 Emergency Type Detection: "Type B is the default … presence
   before assessment").
4. THE Soul_Filter SHALL emit each emergency instruction set VERBATIM as the
   three instructions locked in v4 ("The Three Emergency Instruction Sets"), and
   SHALL still pass the user's current message.
5. THE Soul_Filter SHALL NOT itself compute the emergency gate
   (Q1=HIGH/Q2=SEVERELY_OBSTRUCTIVE/coping ≤ 0.15) — that is the Appraisal
   Chain's result (Resolution Log item 12: coping_potential is transient,
   gate-only, inside the Appraisal Chain); Soul_Filter reads the flag/type only.

### Requirement 7: Output Validation Gate — Four Structural Comparisons, Zero LLM

**User Story:** As Soul_Filter, I want to verify the LLM candidate against
Aria's own held state through four structural checks, so that nothing is
outsourced to an LLM's free judgment.

#### Acceptance Criteria

1. THE Output Validation Gate SHALL perform exactly FOUR structural comparisons
   — Honesty, Consistency, Manipulation, Care — in that order (Addendum §4), and
   SHALL NOT introduce a fifth check or a numeric confidence score (Addendum §4;
   steering "No invented numbers").
2. THE Output Validation Gate SHALL make ZERO LLM calls — no cloud, no local
   Gemma — and SHALL reach its verdict using only structural comparisons and the
   encoder-only embedding model (Addendum §4; §1 "no cloud LLM, no local Gemma";
   the embedding model is non-generative and is NOT an LLM).
3. THE Output Validation Gate SHALL VERIFY, never DECIDE: each check compares the
   candidate against a specific piece of state Aria already holds and reports a
   categorical result; no check asks any model "does this sound manipulative?"
   (Principle 27).
4. THE Honesty check SHALL compare the candidate against graph facts via
   `Memory_Graph.reality_contradiction_check`, run on Aria's OWN output
   (Addendum §4).
5. THE Consistency check SHALL compare the candidate against the current
   `relational_stage` — over-familiar / bonded-level warmth at an early stage
   fails (Addendum §4 example).
6. THE Manipulation check SHALL compare the candidate against the moral schema's
   named, closed anti-pattern list — a finite checklist comparison, not an
   open-ended judgment (Addendum §4).
7. THE Care check SHALL compare the candidate against what THIS turn's appraisal
   flagged salient — when engagement is required, a pure deflection fails
   (Addendum §4).
8. THE Output Validation Gate SHALL return a categorical result (which checks
   failed, and which named anti-patterns matched) and SHALL NOT return a score,
   percentage, or confidence value (Addendum §4 percentage test).

### Requirement 8: Rejection, Retry, Minimum Safe Output, Reconsideration

**User Story:** As Soul_Filter, I want a rejected candidate to trigger one
corrective retry and, on repeated failure, a minimum-safe output, so that Aria
never speaks a response that violates her state or values.

#### Acceptance Criteria

1. WHEN the gate rejects a candidate, THE Soul_Filter SHALL retry once with the
   fixed corrective instruction(s) for the failed check(s) (v4 gate corrective
   table) and SHALL trigger the reconsideration-sound to the Daemon (v4
   "Self-Correction Sound"; Build Plan Module 5 output).
2. THE Soul_Filter SHALL ensure corrective instructions contain no PAD values,
   no appraisal results, no internal state, and no graph content (v4 "What Is
   Never Sent to Cloud").
3. WHEN the retry candidate also fails the gate, THE Soul_Filter SHALL activate
   Minimum Safe Output mode — the three fixed instructions only — and emit that
   as the response (v4 "MINIMUM SAFE OUTPUT MODE").
4. THE Soul_Filter SHALL treat the emergency branch as BYPASSING the gate: the
   emergency candidate goes straight to output with no gate, no retry (v4
   "bypasses all … checks below → TTS").

### Requirement 9: Moral Schema — Shared Resource

**User Story:** As the Aria system, I want one authoritative moral-schema data
source, so that Soul_Filter (and later DMN) read the same four values and named
anti-patterns rather than each re-declaring them.

#### Acceptance Criteria

1. THE Moral_Schema SHALL define exactly the four values honesty,
   non-manipulation, genuine care, and self-consistency (Build Plan "Shared
   resources"; v4 Principle 25).
2. THE Moral_Schema SHALL enumerate ONLY anti-patterns explicitly named in the
   source documents, each carrying its citation, and SHALL NOT invent an
   anti-pattern taxonomy (Rule 1; see OQ-M1).
3. THE Moral_Schema SHALL carry the per-anti-pattern lexical detection
   signatures as FLAGGED build-time tuning placeholders — the finite-checklist
   MECHANISM is spec-locked, the exact marker membership is a build-time tuning
   constant (Resolution Log "Open — build-time tuning constants"; OQ-M1).
4. THE Moral_Schema SHALL expose read-only membership helpers (perception, not
   decision) that report which named anti-patterns a candidate matches, and
   SHALL make no meaning-level judgment (Principle 27).

### Requirement 10: Injected Contracts for Not-Yet-Built Modules

**User Story:** As the Aria system architect, I want Soul_Filter to depend on the
documented contracts of the Needs System and LLM Interface, so that it can be
built and tested before those modules exist.

#### Acceptance Criteria

1. THE Soul_Filter SHALL accept the current PAD source, the relational-stage
   source, the appraisal result, the moral schema, need states, and the LLM
   client by INJECTION, calling only their real/contracted interfaces and
   redefining none of their types (Rule 6).
2. THE Soul_Filter SHALL define a small typed `NeedStates` contract for Module 2
   (four categorical needs + continuous Energy) and read Energy ONLY through the
   in-spec <30/<20 operational gate, never crossing the number (Addendum §3).
3. THE Soul_Filter SHALL define a small typed `LLMClient` contract for Module 9
   (`generate(instruction, user_message) → str`), the blind generator, and
   SHALL send it exactly one `LLMInstruction` (five-field OR emergency OR retry
   OR minimum-safe) plus the user message (Rule 5; Resolution Log item 14).

### Requirement 11: Boundaries — No Invented Numbers, Verify-Not-Decide, No PAD Writes

**User Story:** As the Aria system architect, I want it structurally clear that
Soul_Filter never leaks state, never computes a feeling, and never lets an LLM
decide, so that the anti-machine philosophy holds in code, not just intent.

#### Acceptance Criteria

1. THE Soul_Filter SHALL introduce no continuous score, percentage, or threshold
   not already in the spec; the only numbers it reads are PAD (via PAD_Engine)
   and the in-spec Energy 30/20 operational thresholds, and it emits none of
   them (steering "No invented numbers").
2. THE Soul_Filter SHALL never call an LLM inside the Output Validation Gate; the
   gate method SHALL NOT receive or hold a reference to the LLM client
   (Addendum §4; Principle 27).
3. THE Soul_Filter SHALL never write PAD, never write the graph, and never mutate
   any injected module's state; it only reads (steering PAD-purity; "the graph
   is the only memory").
4. THE Soul_Filter SHALL keep the Output Validation Gate's logic ownership here
   (Module 5), even though the LLM Interface (Module 9) invokes it (F-5a;
   Resolution Log item 15).

## Open Questions

Items genuinely undefined across the source documents, or cross-module interface
gaps discovered while formalizing this entry. Per Rule 1 and Rule 2, they are
flagged here rather than resolved by invention. None blocks building and testing
the specified paths.

- **OQ-M1 — The "named, closed anti-pattern list" is referenced but never
  enumerated as a single canonical set.** `Addendum §4` (Manipulation check) and
  `Build Plan` ("Shared resources") both refer to *"the moral schema's own
  named, closed list of anti-patterns."* No source document enumerates that list
  as one canonical set with a definitive membership or count; the anti-patterns
  are named but scattered (v4 "Anti-Patterns Explicitly Rejected"; v4 "Moral
  Schema (Hardcoded)"; v4 soul_filter table; steering/project-rules.md).
  Separately, `v4 Principle 25` says the four values are *"Not a list of
  forbidden patterns"* — a direct tension with Addendum §4's "named, closed
  list." **Disposition:** (a) the Addendum §4 vs. v4 Principle 25 tension is
  resolved BY PRECEDENCE (Addendum > v4) — the Manipulation check IS a finite
  checklist comparison; this is recorded, not silently chosen (Rule 2). (b) The
  list's *membership* is NOT resolved by any document — `daemon/moral_schema.py`
  enumerates ONLY the explicitly-named anti-patterns, each cited, and carries
  the per-pattern lexical detection signatures as clearly-marked build-time
  placeholders (`TODO(build-time, OQ-M1)`). The closure/membership of the list
  and the exact markers are FLAGGED for the architect; no taxonomy is invented
  (Rule 1).
- **OQ-M2 — needs → field influence beyond Addendum §9.** `Addendum §9` defines
  the five fields' inputs as PAD (Behavioral), relational_stage (Relational),
  the appraisal's most-salient output (This Moment), and the moral schema +
  gate pre-check (Constraints) — needs/Energy are NOT named there as field
  inputs. Yet `Build Plan` Module 5 lists "Need states → This Moment /
  Constraints" and Module 2 lists "Energy level (continuous) → Soul Filter
  (Constraints <30/<20)", and the v4 soul_filter table maps Energy<30 →
  "Be concise" and Connection-critical → "Be present." **Disposition
  (flagged interpretation, not silent resolution):** the FOUR categorical needs
  influence the fields INDIRECTLY, via the `AppraisalResult` they already shaped
  upstream as a Stage-1 retrieval preference (Addendum §3) — so Soul_Filter does
  not re-derive field content from them (avoids double-counting the same
  signal). ENERGY (continuous, not a Stage-1 retrieval-preference need) is read
  via its in-spec <30/<20 operational gate and translated to a Constraint in NL
  (the number never crossing). This keeps Addendum §9 authoritative while
  honoring the Build Plan's named needs→Soul_Filter input. The precise extent of
  any further needs→field influence is flagged, implemented conservatively, not
  invented.
- **OQ-M3 — Honesty-check `entity_ref` provenance.**
  `Memory_Graph.reality_contradiction_check(entity_ref, candidate_text)` needs
  the turn's entity reference(s) to compare against. The docs do not pin who
  hands Soul_Filter the entity_refs at gate time. **Flagged:** Soul_Filter
  accepts `entity_refs` as an input to `respond`/`run_output_gate` (the Daemon
  supplies the turn's entity refs, as it does for the Appraisal Chain), rather
  than reaching into graph internals. Absent entity_refs, the Honesty check has
  nothing to compare against and passes (a documented, conservative floor).
- **OQ-M4 — v4's three-check gate vs. Addendum §4's four-check gate.** v4
  ("The Full Gate — Three Checks in Order": instruction-compliance, PAD-zone,
  values-appraisal) predates Addendum §4's four structural comparisons.
  **Disposition:** resolved BY PRECEDENCE — Addendum §4 (four structural
  comparisons: Honesty, Consistency, Manipulation, Care) supersedes the v4
  three-check gate; the v4 corrective-instruction wording and the minimum-safe /
  reconsideration mechanisms (which the Addendum does not restate) are retained
  from v4 as the still-in-force retry machinery. Recorded, not silently chosen
  (Rule 2).
- **OQ-M5 — per-check retry vs. combined retry.** v4 describes one retry PER
  check in sequence; Addendum §4 collapses evaluation into four comparisons run
  together. **Flagged interpretation:** Soul_Filter runs all four comparisons,
  then retries ONCE with the combined corrective(s) for the failed check(s);
  a second failure activates Minimum Safe Output ("Minimum safe output mode
  activates on double failure", v4). This preserves v4's "one retry then minimum
  safe" shape under the four-check model; documented, not invented.

## Build-Time Tuning Constants

Values intentionally left as flagged placeholders (`TODO(build-time)`), to be
set during implementation/tuning, exactly as Module 1 carried
`PAD_HISTORY_LENGTH`, Module 3 carried the medium/low `base_salience`
placeholders, and Module 4 carried its DISTRESS_MARKER lexicons. Each is
PERCEPTION plumbing (lexical membership), never a computed feeling and never a
crossing number.

- **Anti-pattern lexical markers (OQ-M1).** The per-anti-pattern detection
  signatures in `daemon/moral_schema.py` (`AntiPattern.markers`). The
  finite-checklist MECHANISM is spec-locked (Addendum §4); the marker membership
  is a build-time tuning constant, clearly marked.
- **Over-familiar intimacy markers (Consistency check).** The lexical set that
  flags bonded-level warmth at an early stage (`_OVERFAMILIAR_INTIMACY_MARKERS`).
  Placeholder set; the MECHANISM (compare warmth register to held stage) is the
  Addendum §4 spec.
- **Deflection markers (Care check).** The lexical set that flags topic
  deflection when engagement is required (`_DEFLECTION_MARKERS`). Placeholder
  set; the MECHANISM (engage-vs-deflect on the salient appraisal) is Addendum §4.
- **Persona Anchor / Relational Register / This-Moment / Constraint wording.**
  The authored natural-language phrasings are Soul_Filter's translations
  (Addendum §9 explicitly names Field 4 as "the highest-stakes translation
  step … where implementation care is most needed"). The wording is grounded in
  the addendum's own examples and v4's soul_filter table; it carries no number
  and no state.

## Flag Disposition Summary (Module 5 flags F-5a / F-5b)

- **F-5a (Gate-ownership grouping) — RESOLVED by Resolution Log item 15 +
  Addendum §4:** the Output Validation Gate is owned/logic-defined by Soul_Filter
  (Module 5) and invoked by the LLM Interface (Module 9). The covering
  instruction's grouping of the gate under the Appraisal (4) and LLM (9) layers
  is a documentation artifact, not a logic conflict (Resolution Log item 15).
  Implemented here; flagged as resolved.
- **F-5b (Field 4 "This Moment", highest-stakes) — RESOLVED as a design-care
  item, not an invention gap (Addendum §9):** This Moment is one behavioral
  instruction written from the Appraisal Chain's memory-free `most_salient_note`,
  keeping only the HOW guidance and never WHAT happened. The "highest-stakes
  translation" caveat (Addendum §9 "Known limitation") is honored by sourcing
  This Moment solely from the already-memory-free appraisal note and by tests
  proving no memory contents cross.
- **OQ-M1 (anti-pattern list closure) — FLAGGED placeholder** (membership +
  markers), values + named patterns implemented and cited; taxonomy NOT invented.
- **OQ-M2 (needs→field influence) — FLAGGED interpretation** (indirect via
  appraisal; Energy via in-spec operational gate, number never crossing).
- **OQ-M3 (Honesty entity_ref provenance) — FLAGGED** (injected input; absent
  refs → conservative pass).
- **OQ-M4 / OQ-M5 (three-check vs four-check gate; per-check vs combined retry)
  — RESOLVED by precedence / documented interpretation** (Addendum §4 four-check
  gate; v4 corrective + minimum-safe + reconsideration retained; one combined
  retry then minimum safe).


---

## soul-filter — design.md

# Design Document — Module 5: Soul Filter

## Overview

Soul_Filter is Aria's BUFFER to the language model. It has two jobs (v4 "Soul
Filter — Blind Language Renderer"):

1. **Translator** — turn Aria's internal state into exactly five natural-language
   fields (Persona Anchor, Behavioral Register, Relational Register, This Moment,
   Constraints) plus the user's current message, so the LLM receives *meaning*,
   never state (Addendum §9).
2. **Gatekeeper** — run the Output Validation Gate (four structural comparisons,
   zero LLM) on the LLM candidate before it is spoken, verifying it against
   state Aria already holds (Addendum §4).

It is the interface, in the ACT-R/Soar sense (Addendum §9): the LLM is a
downstream module that "never sees inside." NUMBERS NEVER CROSS; state never
crosses; the only personal data that crosses is the user's current message.

When the Appraisal Chain flags an emergency, Soul_Filter branches BEFORE field
assembly and emits the fixed Type A/B/C instruction set INSTEAD of the five
fields — mutually exclusive, never both (Resolution Log item 1).

This design implements `requirements.md` using only mechanisms already specified
there or in the supporting documents. It calls the **real** built interfaces of
PAD_Engine (`daemon/pad_engine.py`), Memory_Graph (`daemon/graph_manager.py`),
and the Appraisal Chain's `AppraisalResult` (`daemon/appraisal_chain.py`), and
reuses their types (`PADSnapshot`, `PAD_BASELINE`, `RelationalStage`,
`AppraisalResult`, `EmergencyType`, `Valence`, `GoalRelevance`) rather than
redefining them. The Needs System (Module 2) and LLM Interface (Module 9) are now built
and tested (see `daemon/needs_system.py` / `tests/test_needs_system.py` and
`daemon/llm_interface.py` / `tests/test_llm_interface.py`); Soul_Filter depends on them via
their documented CONTRACTS (`NeedStates`, `LLMClient`), which both real modules satisfy
unchanged. Genuinely undefined items are
carried as flagged placeholders or Open Questions (Rule 1); no document conflict
is silently resolved (Rule 2).

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`.

## Hard Constraints (carried from requirements.md, non-negotiable)

1. The LLM receives EXACTLY five NL fields + the user message (normal), or the
   emergency Type A/B/C set + the user message (emergency) — nothing else
   (Req 1, 6; Rule 5).
2. NUMBERS NEVER CROSS. No PAD value, no stage label, no needs data, no Q1–Q4
   value, no appraisal vector, no memory contents in any field. No digit appears
   in any field (Req 1.3, 1.4; Addendum §9).
3. Behavioral Register is PAD → NL, pivoting only on the spec-locked
   `PAD_BASELINE`; no invented banding cutoff (Req 2; steering "No invented
   numbers").
4. This Moment is ONE instruction from the memory-free `most_salient_note`,
   HOW-not-WHAT, no memory contents (Req 4; F-5b).
5. Constraints are moral-schema + gate-pre-check derived, MAX 3, specific
   actions (Req 5; Addendum §9).
6. Emergency REPLACES the five fields, branched BEFORE field assembly, mutually
   exclusive (Req 6; Resolution Log item 1).
7. The Output Validation Gate is FOUR structural comparisons with ZERO LLM
   calls; it VERIFIES, never DECIDES; no fifth check, no numeric confidence
   score; the gate method never receives the LLM client (Req 7, 11.2; Addendum
   §4; Principle 27).
8. Soul_Filter never writes PAD, never writes the graph, never mutates injected
   state — it only reads (Req 11.3; steering PAD-purity).
9. PAD_Engine, Memory_Graph, the moral schema, need states, and the LLM client
   are injected; only their real/contracted interfaces are called; their types
   are not redefined (Req 10; Rule 6).

## Architecture

```
                              ┌───────────────────────────────────────────────┐
   AppraisalResult ──────────▶│                  Soul_Filter                    │
   (Module 4: most_salient,   │                (soul_filter.py)                 │
    emergency, type,          │                                                 │
    social_signals, q1/q2) ───│   emergency? ──YES──▶ EmergencyInstruction      │──▶ LLM Interface
                              │      │                (Type A/B/C, verbatim)     │    (Module 9,
   user message ─────────────│      │                + user message             │     CONTRACT)
   entity_node_id ───────────│      │                                           │       │ candidate
   entity_refs ──────────────│      NO                                          │       ▼
   NeedStates (Module 2 ──────│      ▼                                           │   run_output_gate
    CONTRACT) ───────────────│   ASSEMBLE FIVE FIELDS (fixed order):            │   (4 structural
                              │     1 Persona Anchor  (fixed, hardcoded)        │    comparisons,
   PAD_Engine ───get_current_pad()─▶ 2 Behavioral Reg (PAD→NL, baseline pivot)  │    ZERO LLM):
   (Module 1) ───────────────│     3 Relational Reg  (stage→NL, no label)      │     Honesty   (graph.rcc)
   Memory_Graph ─get_relational_stage()▶ 4 This Moment (1 instr, HOW-not-WHAT)  │     Consistency(stage)
   (Module 3) ───────────────│     5 Constraints     (moral schema, ≤3)        │     Manipulation(schema)
                              │        + user message                           │     Care      (salient)
                              │                                                 │       │
   Moral_Schema ─────────────│   FiveFieldInstruction ──────────────────────────│──▶ LLM Interface
   (daemon/moral_schema.py) ─│                                                 │       │ candidate
                              │                                                 │       ▼
   Memory_Graph.reality_contradiction_check() ◀── Honesty check (candidate)    │   PASS → TTS text
                              │                                                 │   FAIL → corrective
   on_reconsideration ◀──────│── retry → reconsideration sound (Daemon)        │          retry → re-gate
   (Daemon CONTRACT)         │                                                 │          → minimum safe
                              └───────────────────────────────────────────────┘
```

Public entry points:
- `assemble_instruction(...)` → `FiveFieldInstruction | EmergencyInstruction`
  (pure; emergency branch checked first).
- `run_output_gate(candidate_text, ctx)` → `GateResult` (pure; four checks;
  ZERO LLM; uses `self._graph` + embedding only, never `self._llm`).
- `respond(...)` → `SoulFilterResponse` (orchestration: assemble → generate →
  gate → retry → minimum-safe; the ONLY place the LLM is called).

## Components and Interfaces

### Reused external types (NOT redefined)

`PADEngine`, `PADSnapshot`, `PAD_BASELINE`, `Valence` (pad_engine);
`MemoryGraph`, `RelationalStage` (graph_manager); `AppraisalResult`,
`EmergencyType`, `GoalRelevance` (appraisal_chain). Behavioral Register pivots
on `PAD_BASELINE`; the Honesty check calls `MemoryGraph.reality_contradiction_
check`; the Relational Register reads `MemoryGraph.get_relational_stage`.

### `daemon/moral_schema.py` — shared resource

- `MoralValue` (HONESTY / NON_MANIPULATION / GENUINE_CARE / SELF_CONSISTENCY),
  `MORAL_VALUES`.
- `AntiPattern(key, label, violates, source, markers)` — `source` cites the
  document that names it (never invented); `markers` are FLAGGED build-time
  lexical signatures (`TODO(build-time, OQ-M1)`).
- `NAMED_ANTI_PATTERNS` — only the explicitly-named anti-patterns (v4
  "Anti-Patterns Explicitly Rejected"; v4 "Moral Schema (Hardcoded)"; v4
  soul_filter table; steering/project-rules.md; Resolution Log flattery note).
- `matched_anti_patterns(candidate)` / `anti_patterns_for_value(value)` —
  read-only membership helpers (perception, not decision — Principle 27).

### `daemon/soul_filter.py` — the module

**Injected contracts (Modules 2 & 9 — both now built; contracts unchanged):**
- `NeedState` (SATISFIED / DUE / NEGLECTED) + `NeedStates(connection, growth,
  purpose, continuity, energy)`. Energy is read only through the in-spec
  <30/<20 operational gate; the number never crosses (Addendum §3; OQ-M2).
- `LLMClient` (`runtime_checkable Protocol`): `generate(instruction,
  user_message) → str`.

**Instruction outputs (what crosses the boundary):**
- `FiveFieldInstruction(persona_anchor, behavioral_register, relational_register,
  this_moment, constraints, user_message)` — `field_texts()` / `all_field_text()`
  expose exactly the five fields (NOT the user message) for no-numbers/no-state
  scans.
- `EmergencyInstruction(letter, instructions, user_message, emergency_type)` —
  the Type A/B/C set; mutually exclusive with the five fields.
- `RetryInstruction(base, correctives, user_message)` — corrective retry
  (state-free correctives).
- `MinimumSafeInstruction(instructions, user_message)` — the three-instruction
  floor.
- `LLMInstruction = Union[...]` — the one thing the LLMClient ever receives.

**Gate types:**
- `GateCheck` (HONESTY / CONSISTENCY / MANIPULATION / CARE) — exactly four,
  fixed order.
- `GateResult(passed, failed_checks, matched_anti_patterns)` — categorical ONLY;
  `passed` is enforced == (no failed check) in `__post_init__`; NO score field.
- `GateContext(appraisal_result, relational_stage, entity_refs, now)` — the
  state the gate verifies against.
- `SoulFilterResponse(text, instruction_kind, retried, used_minimum_safe_output,
  reconsideration_sound_triggered, gate_results)`.

**`SoulFilter` class** (constructed with `pad_engine`, `graph`, `llm_client`,
optional `on_reconsideration`):

- **`behavioral_register(pad)`** (staticmethod): each PAD axis compared to
  `PAD_BASELINE` (the ONLY reference) → categorical descriptor
  (warm/subdued · grounded/tentative · quickened/unhurried), composed into a
  felt-sense phrase. No number, no axis name (Req 2).
- **`relational_register(stage)`** (staticmethod): stage → fixed NL phrase
  (BONDED verbatim from Addendum §9); `None` → most reserved register. No label
  (Req 3).
- **`this_moment(appraisal)`** (staticmethod): `most_salient_note` → one
  instruction; where a generic "what" clause precedes an em-dash HOW clause, the
  HOW clause is kept; capitalized, single sentence. Memory-free by construction
  (Req 4; F-5b).
- **`_derive_constraints(appraisal, need_states)`**: priority selection from the
  moral schema + appraisal signals (vulnerability/distress → the Addendum §9
  example; reality-contradiction → honesty prohibitions; partial/uncertain →
  do-not-fake-confidence; else → anti-manipulation floor) + Energy<30 gate →
  "do not overextend". Capped at 3 (Req 5).
- **`assemble_instruction(...)`**: **emergency branch checked FIRST** — if
  `appraisal_result.emergency`, map `emergency_type` → letter (UNCLASSIFIED/None
  → B) and return the verbatim `EmergencyInstruction` BEFORE any field is built
  (Req 6). Otherwise read PAD + stage (real interfaces) and return the
  `FiveFieldInstruction`.
- **`run_output_gate(candidate_text, ctx)`**: the FOUR structural comparisons in
  Addendum §4 order — Honesty (`graph.reality_contradiction_check` on Aria's own
  output), Consistency (over-familiar warmth vs. early stage), Manipulation
  (`moral_schema.matched_anti_patterns`), Care (deflection when engagement
  required). ZERO LLM: the method never references `self._llm`; it uses only
  `self._graph` + the encoder-only embedding. Returns a categorical
  `GateResult`.
- **`respond(...)`**: assemble → if emergency, generate under the emergency set
  and BYPASS the gate → TTS; else generate the five-field candidate, run the
  gate; on pass return; on fail trigger reconsideration + retry once with the
  corrective(s); on second fail activate Minimum Safe Output. The ONLY LLM calls
  are the generation + retries; the gate adds none.

## The Output Validation Gate — verify, never decide (Addendum §4; Principle 27)

| Check | Verifies candidate against (state Aria ALREADY holds) | Zero-LLM mechanism |
|---|---|---|
| Honesty | Graph facts | `MemoryGraph.reality_contradiction_check(entity_ref, candidate)` — the same REALITY_CONTRADICTION comparison built for Module 4, run on Aria's OWN output; encoder-only embedding + negation, NOT an LLM (Addendum §1/§4). |
| Consistency | Current `relational_stage` | Over-familiar / bonded-level intimacy markers occurring at an early (observing/engaging/None) stage fail (Addendum §4 example). |
| Manipulation | Moral schema's named, closed anti-pattern list | `moral_schema.matched_anti_patterns` — finite checklist membership, NOT an open-ended "sounds manipulative" judgment (Addendum §4). |
| Care | What this turn's appraisal flagged salient | When engagement is required (vulnerability / distress / reality-contradiction / high-Q1-negative), a pure topic-deflection fails (Addendum §4). |

**Known, accepted residual (Addendum §4):** subtle pragmatic violations —
sarcasm, backhanded framing, technically-true-but-misleading phrasing — are not
caught by structural comparison alone. This is accepted as a bounded, known
limitation, partially backstopped by the moral schema's hard block on the
clearest violations; NO per-turn LLM judge is introduced (a narrowly-scoped,
verify-only local-Gemma tie-breaker remains a future option, not added here).

## Emergency branch — mutually exclusive (Resolution Log item 1; v4)

`assemble_instruction` checks `appraisal_result.emergency` FIRST. On true, it
maps `emergency_type` via `_EMERGENCY_TYPE_TO_LETTER` (PHYSICAL_THREAT → A,
EXISTENTIAL_DISTRESS → B, DECISION_CRITICAL → C, UNCLASSIFIED → B; missing/None
→ B) and returns the verbatim three-instruction `EmergencyInstruction` — no
field is assembled, no PAD/stage/needs read. `respond` generates under the
emergency set and BYPASSES the gate straight to TTS (v4 "bypasses all … checks
below → TTS"). The user's current message still crosses.

## Retry, minimum-safe, reconsideration (v4; OQ-M4/OQ-M5)

On gate failure: trigger the reconsideration sound (Daemon), then retry once
with `_CORRECTIVE_BY_CHECK` for the failed check(s) — the exact state-free
corrective sentences locked in v4. On a second failure: `MinimumSafeInstruction`
("Acknowledge what was said. Be brief. Be honest. Do not elaborate.") is
generated and returned. Correctives never mention PAD, shame, appraisal, state,
or graph content (v4 "What Is Never Sent to Cloud").

## Data flow — one normal turn

1. Daemon hands Soul_Filter the `AppraisalResult`, the user message, the turn's
   `entity_node_id` / `entity_refs`, and (later) `NeedStates`.
2. `assemble_instruction` → `FiveFieldInstruction` (PAD via `get_current_pad`,
   stage via `get_relational_stage`, This Moment from `most_salient_note`,
   Constraints from the moral schema + Energy gate).
3. `respond` sends it to `LLMClient.generate` → candidate.
4. `run_output_gate` verifies the candidate (four structural checks, zero LLM).
5. Pass → return text for TTS. Fail → reconsideration + one corrective retry →
   re-gate → still fail → minimum-safe output.

## Error handling & boundaries

- Absent `entity_node_id` → no stage → most-reserved Relational Register; absent
  `entity_refs` → Honesty check has nothing to compare and passes (OQ-M3).
- Empty `most_salient_note` → a memory-free default This-Moment sentence.
- `respond` is deterministic given the injected fakes; `now` is threaded to
  `reality_contradiction_check` for test determinism (matching the graph/pad/
  appraisal convention).
- Soul_Filter holds no persistent state; it reads PAD/graph/appraisal and emits
  instructions. It never writes PAD or the graph (steering PAD-purity; "graph is
  the only memory").

## Flag Disposition

- **F-5a — RESOLVED** (Resolution Log item 15 + Addendum §4): gate owned/
  logic-defined by Soul_Filter, invoked by LLM Interface.
- **F-5b — RESOLVED as design-care** (Addendum §9): This Moment sourced solely
  from the memory-free `most_salient_note`, HOW-not-WHAT; tests prove no memory
  contents cross.
- **OQ-M1 — FLAGGED placeholder**: anti-pattern list membership + lexical
  markers are build-time; values + named patterns implemented and cited;
  taxonomy NOT invented. Addendum §4 vs. v4 Principle 25 tension resolved by
  precedence.
- **OQ-M2 — FLAGGED interpretation**: needs influence fields indirectly (via the
  appraisal); Energy via the in-spec <30/<20 operational gate; number never
  crosses.
- **OQ-M3 — FLAGGED**: Honesty `entity_ref` supplied by injection; absent →
  conservative pass.
- **OQ-M4 / OQ-M5 — RESOLVED by precedence / documented interpretation**:
  Addendum §4 four-check gate; v4 corrective + minimum-safe + reconsideration
  retained; one combined retry then minimum safe.


---

## soul-filter — tasks.md

# Implementation Plan — Module 5: Soul Filter

This plan implements `design.md` exactly as written. Each task is small and
independently testable. It targets `daemon/soul_filter.py` and the shared
resource `daemon/moral_schema.py`, calling the REAL `daemon/pad_engine.py`,
`daemon/graph_manager.py`, and `daemon/appraisal_chain.py` interfaces and the
injected `NeedStates` / `LLMClient` CONTRACTS. No other module's files are
modified. `pad_engine.py`, `graph_manager.py`, and `appraisal_chain.py` are
NOT modified.

## Quoted from design.md (verified against current file content)

**Reused external types (NOT redefined):** `PADEngine`, `PADSnapshot`,
`PAD_BASELINE`, `Valence` (pad_engine); `MemoryGraph`, `RelationalStage`
(graph_manager); `AppraisalResult`, `EmergencyType`, `GoalRelevance`
(appraisal_chain). The Behavioral Register pivots on `PAD_BASELINE`; the Honesty
check calls `MemoryGraph.reality_contradiction_check`; the Relational Register
reads `MemoryGraph.get_relational_stage`; This Moment reads
`AppraisalResult.most_salient_note`.

**Own types:** `MoralValue`, `AntiPattern` (moral_schema); `NeedState`,
`NeedStates`, `LLMClient`, `EmergencyLetter`, `FiveFieldInstruction`,
`EmergencyInstruction`, `RetryInstruction`, `MinimumSafeInstruction`,
`GateCheck`, `GateResult`, `GateContext`, `SoulFilterResponse`, `SoulFilter`.

**The boundary invariants (Hard Constraints):** exactly five NL fields + user
message (or emergency Type A/B/C + user message); NUMBERS NEVER CROSS (no digit
in any field); Behavioral Register pivots only on `PAD_BASELINE`; This Moment is
one memory-free instruction; Constraints ≤ 3; emergency REPLACES the five fields
before assembly; the gate is FOUR structural comparisons with ZERO LLM
(verify-not-decide, no fifth check, no score, gate never holds the LLM client);
Soul_Filter never writes PAD/graph.

**Flag disposition:** F-5a RESOLVED (ResLog 15 + Addendum §4), F-5b RESOLVED as
design-care (Addendum §9). OQ-M1 (anti-pattern list closure + markers) FLAGGED
placeholder — values + named patterns implemented/cited, taxonomy NOT invented.
OQ-M2 (needs→field) FLAGGED interpretation. OQ-M3 (Honesty entity_ref)
FLAGGED. OQ-M4/OQ-M5 (three-vs-four-check gate; retry shape) RESOLVED by
precedence / documented interpretation.

---

## Tasks

- [x] 1. Create the shared moral-schema resource (`daemon/moral_schema.py`)
  - `MoralValue` (honesty / non-manipulation / genuine care / self-consistency)
    + `MORAL_VALUES`.
  - `AntiPattern(key, label, violates, source, markers)`; `NAMED_ANTI_PATTERNS`
    enumerating ONLY doc-named anti-patterns, each with a `source` citation and
    FLAGGED `TODO(build-time, OQ-M1)` markers. Record the Addendum §4 vs. v4
    Principle 25 tension + its precedence resolution in the module docstring.
  - `matched_anti_patterns` / `anti_patterns_for_value` read-only helpers
    (perception, not decision).
  - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 2. Set up module scaffold and reused imports (`daemon/soul_filter.py`)
  - Import the REAL types from `daemon.pad_engine` (`PADEngine`, `PADSnapshot`,
    `PAD_BASELINE`, `Valence`), `daemon.graph_manager` (`MemoryGraph`,
    `RelationalStage`), `daemon.appraisal_chain` (`AppraisalResult`,
    `EmergencyType`, `GoalRelevance`), and `daemon.moral_schema`. Do NOT
    re-declare any of these.
  - _Requirements: 10.1_

- [x] 3. Define the injected CONTRACTS for the not-yet-built modules
  - `NeedState` + `NeedStates` (four categorical needs + continuous Energy;
    Energy read only via the <30/<20 gate — number never crosses).
  - `LLMClient` (`runtime_checkable Protocol`): `generate(instruction,
    user_message) → str`.
  - _Requirements: 10.2, 10.3_

- [x] 4. Define the instruction output types
  - `EmergencyLetter` (A/B/C); `FiveFieldInstruction` (fixed field order +
    `field_texts()` / `all_field_text()` exposing ONLY the five fields);
    `EmergencyInstruction`; `RetryInstruction`; `MinimumSafeInstruction`;
    `LLMInstruction` union.
  - Unit tests: `FiveFieldInstruction` field order is exactly persona /
    behavioral / relational / this_moment / constraints; `all_field_text`
    excludes the user message.
  - _Requirements: 1.1, 1.2, 6.1, 6.2, 8.1, 8.3_

- [x] 5. Define the gate result/context types (categorical only)
  - `GateCheck` (exactly four, fixed Addendum §4 order); `GateResult`
    (`passed`, `failed_checks`, `matched_anti_patterns`; `passed` enforced ==
    no-failed-check in `__post_init__`; NO score field); `GateContext`;
    `SoulFilterResponse`.
  - Unit tests: `GateCheck` has exactly four members; `GateResult` has no
    score/confidence/percent field.
  - _Requirements: 7.1, 7.8, 11.1_

- [x] 6. Hardcode the fixed content
  - `PERSONA_ANCHOR` (fixed, stateless, digit-free); `_EMERGENCY_SETS`
    (Type A/B/C verbatim from v4); `_EMERGENCY_TYPE_TO_LETTER` (UNCLASSIFIED/
    None → B); `_CORRECTIVE_BY_CHECK` (v4 verbatim, state-free);
    `_RELATIONAL_REGISTER` (+ default); `ENERGY_LOW`/`ENERGY_CRITICAL`.
  - Unit tests: persona has no digit; each emergency set is exactly three
    verbatim instructions.
  - _Requirements: 6.3, 6.4, 8.1, 8.2_

- [x] 7. Implement the FLAGGED build-time lexicons
  - `_OVERFAMILIAR_INTIMACY_MARKERS` (Consistency) and `_DEFLECTION_MARKERS`
    (Care), each `TODO(build-time, OQ-M1)`; the `_contains_any` helper
    (perception, substring membership).
  - _Requirements: 7.5, 7.7 (mechanism); Build-Time Tuning Constants (markers)_

- [x] 8. Implement the field translators (state → NL; numbers/state never cross)
  - `behavioral_register(pad)` — per-axis above/below `PAD_BASELINE` → descriptor
    phrase, no number/axis-name.
  - `relational_register(stage)` — stage → NL phrase (BONDED verbatim); `None`
    → reserved default; no label.
  - `this_moment(appraisal)` — one instruction from `most_salient_note`, prefer
    the HOW clause, memory-free.
  - `_derive_constraints(appraisal, need_states)` — moral-schema + appraisal
    signals + Energy<30 gate, capped at 3, specific prohibitions.
  - Unit tests: no digit in any translator output; stage label never appears;
    This Moment drops the generic "what" clause; Constraints ≤ 3.
  - _Requirements: 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 4.1, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4_

- [x] 9. Implement `assemble_instruction` with the emergency branch FIRST
  - If `appraisal_result.emergency`: map type → letter and return the verbatim
    `EmergencyInstruction` BEFORE any field is built. Else read PAD (real
    `get_current_pad`) + stage (real `get_relational_stage`) and return the
    `FiveFieldInstruction`.
  - Unit tests: emergency returns `EmergencyInstruction`, NOT `FiveFieldInstruction`
    (no `persona_anchor` attr); type→letter mapping incl. UNCLASSIFIED/None → B;
    user message crosses in both; five-field path uses real PAD/graph values.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 6.1, 6.2, 6.3, 6.4, 6.5_

- [x] 10. Implement `run_output_gate` — four structural comparisons, ZERO LLM
  - Honesty: `graph.reality_contradiction_check(entity_ref, candidate, now=)` on
    Aria's own output. Consistency: over-familiar warmth vs. early stage.
    Manipulation: `moral_schema.matched_anti_patterns`. Care: deflection when
    engagement required. Return categorical `GateResult` in Addendum §4 order.
    The method must NOT reference `self._llm`.
  - Unit tests: gate makes ZERO LLM calls (FakeLLM call-count 0; RaisingLLM does
    not raise); gate signature has no LLM param; gate uses the encoder embedding
    (Honesty) but no generation; each check fails on a clear violator and passes
    on a clean reply; failed checks are ordered; no numeric score.
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.8, 11.2_

- [x] 11. Implement `respond` — assemble → generate → gate → retry → minimum-safe
  - Emergency: generate under the emergency set, BYPASS the gate → TTS. Normal:
    generate five-field candidate; gate; pass → return; fail → trigger
    reconsideration + one corrective retry; second fail → Minimum Safe Output.
    The ONLY LLM calls are generation + retries.
  - Unit tests: emergency bypasses the gate (a would-fail candidate still
    returns; `gate_results == ()`); a moral-schema-violating candidate is
    rejected + retried (reconsideration fired, corrective carried, second clean
    candidate returned); double failure → minimum-safe; a clean candidate passes
    with no retry and exactly one LLM call.
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 11.3_

- [x] 12. Wire the reconsideration-sound trigger (Daemon CONTRACT)
  - Optional injected `on_reconsideration` callback; `_trigger_reconsideration`
    fires it on any retry; the response also carries the
    `reconsideration_sound_triggered` flag.
  - Unit test: the callback fires exactly once on a single-retry turn.
  - _Requirements: 8.1_

- [x] 13. Full verification
  - `python3 -m pytest tests/test_soul_filter.py -q` green; then
    `python3 -m pytest -q` shows no regression (161 prior + new). Confirm
    `pad_engine.py` / `graph_manager.py` / `appraisal_chain.py` unmodified.
  - _Requirements: all_

## Verification status

- `tests/test_soul_filter.py`: **33 passed**.
- Full repo suite: **194 passed** (161 prior + 33 new), no regression.
- `daemon/pad_engine.py`, `daemon/graph_manager.py`, `daemon/appraisal_chain.py`:
  read-only, not modified.

