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
