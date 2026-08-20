# Requirements Document — Module 9: LLM Interface

## Introduction

This document transcribes and formalizes, in EARS format, the Module 9 (LLM
Interface) entry from `ARIA_Module_Build_Plan.md`. That entry is the locked,
approved scope for this module. No requirement here introduces a mechanism,
threshold, or behavior that is not already stated in the Module 9 entry or in
the supporting architecture documents (`ARIA_Soul_Spec_v4.md`,
`ARIA_Soul_Spec_v4_Addendum.md`, `ARIA_Resolution_Log.md`,
`.kiro/steering/project-rules.md`). Where the entry references a value or
mechanism defined elsewhere (the five-field boundary, the emergency instruction
sets, the cloud/Gemma tiering), the supporting document is cited as the source,
not as a new source of scope.

The LLM Interface is the socket for a **hot-swappable tool**. v4's Fundamental
Architectural Principle: *"Aria is not the LLM. Aria is not the voice. She is
the system that uses them. … The LLM is a hot-swappable tool. Aria is not."*
This module sends what Soul Filter produced to a language model and returns the
model's raw text. It is a **pure conduit**: it renders no judgment, runs no
gate, and — by construction — cannot reach any of Aria's internal state.

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`.
`ARIA_GLM_Covering_Instruction.md` provides covering context only.

Per the Module 9 entry, the two flags are **F-9a** (Gemma receives the same
five-field-only + user-message limit as cloud) and **F-9b** (the "Output Gate"
label under this layer belongs to Soul Filter). Both are **resolved** by the
Resolution Log (items 14 and 15 respectively) and are recorded in the Flag
Disposition section, not reopened. Genuinely undefined items (retry cadence,
idle-unload, context sizes) are build-time tuning constants, recorded in Open
Questions / Build-Time Tuning Constants rather than invented (Rule 1).

## Glossary

- **LLM_Interface**: The module specified here (Module 9,
  `daemon/llm_interface.py`). The concrete implementation of Soul Filter's
  `LLMClient` contract. Owns no meaning and no state beyond its two injected
  transports.
- **Soul_Filter**: Module 5 (`daemon/soul_filter.py`). The buffer that produces
  the instruction and the user message the LLM_Interface sends, and that runs
  the Output Validation Gate on the returned candidate. The LLM_Interface's
  only caller.
- **LLMClient**: The `runtime_checkable` `Protocol` defined in
  `daemon/soul_filter.py` — `generate(instruction: LLMInstruction,
  user_message: str, session_context: str = "") -> str`. The exact contract the
  LLM_Interface implements; imported, never redefined (Rule 6).
- **LLMInstruction**: The union type defined in `daemon/soul_filter.py` —
  `FiveFieldInstruction | EmergencyInstruction | RetryInstruction |
  MinimumSafeInstruction`. The one and only structured input the LLM_Interface
  receives per turn (besides the user message).
- **FiveFieldInstruction**: Soul Filter's normal-operation output — the five
  natural-language fields in fixed order (Persona Anchor, Behavioral Register,
  Relational Register, This Moment, Constraints) plus the user message
  (Addendum §9).
- **EmergencyInstruction**: The fixed Type A/B/C three-instruction set that
  REPLACES the five fields in emergency mode (Resolution Log item 1; v4 "The
  Three Emergency Instruction Sets"). Carries a `letter` and an internal
  `emergency_type` as routing metadata.
- **RetryInstruction / MinimumSafeInstruction**: Soul Filter's corrective-retry
  and minimum-safe-output instructions (v4 gate). Also members of
  LLMInstruction, so the LLM_Interface must render them too.
- **User_Message**: The user's current message — the ONLY personal datum that
  ever crosses to a model (Addendum §9 "what crosses").
- **Session_Context**: The ephemeral, Daemon-assembled conversation transcript for
  the current session (`SessionBuffer.get_context()`), passed through Soul_Filter
  to `generate` as the `session_context` parameter. Not a new personal-data
  channel — it is conversation the user already had this session, not graph or
  internal-state data.
- **Assembled_Prompt**: The complete, provider-agnostic prompt for one turn,
  derived purely from one LLMInstruction + the User_Message + the Session_Context.
  Its text surfaces are the instruction framing, the session context, and the
  user message — held separately so the instruction framing can be verified
  clean of numbers/state independently of the other two.
- **Model_Transport**: The injected backend abstraction — `generate(prompt) ->
  str`, raising `LLMTransportError` on unavailability. A hot-swappable tool: a
  cloud SDK adapter or a local Gemma adapter both satisfy it. No concrete
  provider is named by this module (v4 lists cloud provider as "TBD").
- **Local_Model_Transport**: A Model_Transport with an explicit `load()` /
  `unload()` / `is_loaded` lifecycle — Gemma 4 E2B QAT (v4 Brain Structure).
- **Cloud_Transport / Cloud LLM**: The primary Model_Transport (v4: Claude /
  GPT-4o-mini / DeepSeek, TBD).
- **Gemma**: Gemma 4 E2B QAT, the LOCAL fallback model. "Loads on cloud
  failure, unloads on restore" (v4 Brain Structure).
- **Cloud_Failure**: A turn on which the Cloud_Transport raises
  `LLMTransportError` (timeout, connection error, 5xx, rate-limit, etc.).
- **Restore**: The first turn after a Cloud_Failure period on which the
  Cloud_Transport succeeds again.
- **Output_Validation_Gate**: The four structural comparisons owned by
  Soul_Filter (Addendum §4; Resolution Log item 15). NOT part of this module.
- **Daemon / Visual_Layer**: Modules 8 / 10. Owners of the graceful-degradation
  experience (the "inward/waiting" loop) when the LLM is unavailable — NOT this
  module.

## Requirements

### Requirement 1: Conduit From Soul Filter to the Model

**User Story:** As Soul_Filter, I want a component that takes the instruction I
produced plus the user's current message and returns the model's candidate
text, so that I can obtain a candidate to run through my Output Validation Gate.

#### Acceptance Criteria

1. THE LLM_Interface SHALL expose `generate(instruction, user_message,
   session_context="") -> str`, matching the `LLMClient` contract defined in
   `daemon/soul_filter.py` exactly.
2. WHEN Soul_Filter calls `generate` with an LLMInstruction, a User_Message, and the
   current Session_Context, THE LLM_Interface SHALL send the corresponding
   Assembled_Prompt to a model and return the model's candidate text.
3. THE LLM_Interface SHALL return the model's candidate text VERBATIM, without
   modification, truncation, rewriting, or substitution.
4. THE LLM_Interface SHALL be usable as Soul_Filter's injected `llm_client`
   with no change to `daemon/soul_filter.py`.

### Requirement 2: The Five-Field Boundary Is Structural

**User Story:** As the Aria system architect, I want it to be structurally
impossible for graph data, PAD numbers, `relational_stage` labels, needs
states, appraisal outputs, or memory contents to enter a prompt through the LLM
Interface, so that the five-field boundary holds by construction, not by
convention (steering "Five-field LLM boundary").

#### Acceptance Criteria

1. THE LLM_Interface SHALL derive every prompt solely from the LLMInstruction
   object and the User_Message passed to `generate`.
2. THE LLM_Interface SHALL NOT accept, hold, or reference a handle to the memory
   graph, PAD Engine, State Manager, Needs System, Appraisal Chain, embedding
   model, or any persistent store.
3. THE LLM_Interface SHALL be constructible with model transports only, so that
   no state-bearing dependency is available to it at runtime.
4. THE Assembled_Prompt SHALL carry the User_Message as a surface distinct from
   the instruction framing, so that the instruction framing can be verified to
   contain no numeric or state value independently of the user's own words.

### Requirement 3: Identical Prompt on Cloud and Gemma (F-9a)

**User Story:** As the Aria system architect, I want the Gemma local-fallback
path to receive the identical instruction + user-message limit as the cloud
path, so that the local model gets no extra context and "no exception for the
local model" holds (`ARIA_Resolution_Log.md` item 14).

#### Acceptance Criteria

1. THE LLM_Interface SHALL assemble the Assembled_Prompt from the LLMInstruction
   and User_Message by a single, pure, deterministic function.
2. WHEN a turn is served by Gemma after a Cloud_Failure, THE LLM_Interface SHALL
   send Gemma the same Assembled_Prompt it presented (or would have presented)
   to the Cloud_Transport for that turn.
3. THE LLM_Interface SHALL NOT add any context, field, retrieval, or graph data
   to the Gemma path that is not also on the cloud path.
4. WHEN `generate` is called with identical inputs, THE LLM_Interface SHALL
   assemble an identical Assembled_Prompt (deterministic assembly).

### Requirement 4: Cloud Primary, Gemma Fallback With Load/Unload Lifecycle

**User Story:** As the Aria system, I want the cloud model used as primary and
Gemma loaded only on cloud failure and unloaded on restore, so that the local
model is a fallback tool, not the default voice (v4 Brain Structure: "Loads on
cloud failure, unloads on restore").

#### Acceptance Criteria

1. WHEN `generate` is called, THE LLM_Interface SHALL attempt the
   Cloud_Transport first.
2. WHEN the Cloud_Transport returns a candidate, THE LLM_Interface SHALL return
   it and SHALL NOT invoke the Local_Model_Transport for that turn.
3. WHEN a Cloud_Failure occurs and Gemma is not loaded, THE LLM_Interface SHALL
   load Gemma before serving from it.
4. WHEN a Cloud_Failure occurs, THE LLM_Interface SHALL serve the turn from
   Gemma using the same Assembled_Prompt (Requirement 3).
5. WHEN a Restore occurs (the Cloud_Transport succeeds while Gemma is loaded),
   THE LLM_Interface SHALL unload Gemma.
6. WHILE a Cloud_Failure period persists across multiple turns, THE
   LLM_Interface SHALL keep Gemma loaded (loading it once, not once per turn).

### Requirement 5: No Judgment, No Validation, No Gate (F-9b)

**User Story:** As the Aria system architect, I want the LLM Interface to apply
no judgment or validation, so that all evaluation stays in Soul_Filter's Output
Validation Gate and the LLM "never gets final say" (v4;
`ARIA_Resolution_Log.md` item 15).

#### Acceptance Criteria

1. THE LLM_Interface SHALL NOT evaluate, score, rank, filter, moderate, or
   validate the candidate text it returns.
2. THE LLM_Interface SHALL NOT implement any output gate, anti-pattern check,
   moral-schema comparison, or confidence score.
3. THE LLM_Interface SHALL NOT decide to retry, rewrite, or suppress a
   candidate based on the candidate's content (retry decisions belong to
   Soul_Filter, which re-invokes `generate` with a RetryInstruction).
4. THE LLM_Interface SHALL return a candidate unchanged even when that candidate
   would fail Soul_Filter's Output Validation Gate.

### Requirement 6: Emergency Instruction Handling

**User Story:** As the Aria system, I want the LLM Interface to send the fixed
Type A/B/C emergency set (and nothing else) when Soul_Filter emits an
EmergencyInstruction, so that emergency mode replaces the five fields and the
internal classification never crosses (Resolution Log item 1; v4).

#### Acceptance Criteria

1. WHEN `generate` receives an EmergencyInstruction, THE LLM_Interface SHALL
   assemble the prompt from the three fixed emergency instruction sentences plus
   the User_Message, and nothing else.
2. THE LLM_Interface SHALL NOT include the emergency `letter` (A/B/C) or the
   internal `emergency_type` classification in the prompt (v4: the type "stays
   local … never crosses to the cloud").
3. THE LLM_Interface SHALL treat an EmergencyInstruction and a
   FiveFieldInstruction as mutually exclusive per-turn inputs (it renders
   whichever one it is given; it never combines them).

### Requirement 7: All Instruction Kinds Are Rendered

**User Story:** As Soul_Filter, I want the LLM Interface to accept every member
of the LLMInstruction union, so that the normal, emergency, corrective-retry,
and minimum-safe paths all reach a model.

#### Acceptance Criteria

1. THE LLM_Interface SHALL assemble a prompt for a FiveFieldInstruction (the
   five fields in fixed order + Constraints + User_Message).
2. THE LLM_Interface SHALL assemble a prompt for a RetryInstruction (the base
   five fields + the state-free correctives + User_Message).
3. THE LLM_Interface SHALL assemble a prompt for a MinimumSafeInstruction (the
   three minimum-safe instructions + User_Message).
4. IF `generate` receives an object that is not a member of the LLMInstruction
   union, THEN THE LLM_Interface SHALL raise a `TypeError` rather than guess a
   rendering (a structural guard, not a judgment about content).

### Requirement 8: Provider-Agnostic, Injected Transports

**User Story:** As the Aria system architect, I want the actual model transport
abstracted behind an injected interface, so that the LLM stays a hot-swappable
tool and no provider is hardcoded (v4: cloud provider "TBD"; the LLM is a
hot-swappable tool).

#### Acceptance Criteria

1. THE LLM_Interface SHALL obtain its cloud and local backends as injected
   Model_Transport / Local_Model_Transport dependencies.
2. THE LLM_Interface SHALL NOT import or hardcode any concrete model provider
   (Claude, GPT-4o-mini, DeepSeek, or a specific Gemma runtime).
3. THE LLM_Interface SHALL treat a Model_Transport as unavailable for a turn
   only when it raises `LLMTransportError`.

### Requirement 9: Total Unavailability Reports, Never Fabricates

**User Story:** As the Aria system, I want the LLM Interface to report when no
backend can serve a turn rather than invent a reply, so that a fabricated voice
never reaches the user and graceful degradation is handled by the owning module
(v4 "Cloud Models Are Her Knowledge, Not Her Voice").

#### Acceptance Criteria

1. WHEN both the Cloud_Transport and the Local_Model_Transport fail for one
   turn, THE LLM_Interface SHALL raise `LLMUnavailableError`.
2. THE LLM_Interface SHALL NOT synthesize, template, or otherwise fabricate
   candidate text when no backend can serve.
3. THE LLM_Interface SHALL NOT own the graceful-degradation user experience (the
   "inward/waiting" loop); that is the Visual_Layer's (Module 10), orchestrated
   by the Daemon (Module 8). See OQ-9c.

### Requirement 10: Satisfy the Real Contract Unchanged

**User Story:** As the Aria system architect, I want Module 9 to be the concrete
`LLMClient` so that Soul_Filter uses it with no modification (Rule 6: call the
real interface, do not redefine it).

#### Acceptance Criteria

1. THE LLM_Interface SHALL import `LLMClient`, `LLMInstruction`, and the four
   instruction dataclasses from `daemon/soul_filter.py` and SHALL NOT redefine
   them.
2. THE LLM_Interface SHALL be an instance of the `LLMClient` `runtime_checkable`
   Protocol.
3. THE LLM_Interface SHALL NOT modify `daemon/soul_filter.py` or any other core
   module; IF the contract were found to need a change, THEN it SHALL be flagged
   for the architect rather than changed here (Rule 2). No such change was
   needed (see Flag Disposition).

## Open Questions

Per Rule 1, genuinely undefined items are flagged here rather than resolved by
invention. None block the transcription above; the Module 9 entry's only flags
(F-9a, F-9b) are both resolved by the Resolution Log (see Flag Disposition).

- **OQ-9a — Cloud retry / health-check cadence.** The Interface tries cloud
  first every turn (which is how Restore is detected). Whether a real deployment
  should additionally back off, batch, or health-check the cloud between turns
  during a sustained outage is a build-time tuning concern, not specified in any
  source document. Consistent with the Resolution Log's treatment of tick
  cadences as build-time tuning constants. Not resolved here.
- **OQ-9b — Gemma idle-unload timeout.** v4 pins exactly one unload trigger:
  "unloads on restore," which is implemented. Whether Gemma should ALSO be
  unloaded to reclaim memory after a long idle period (even while cloud remains
  down) is not specified. Not invented; left as a build-time tuning flag.
- **OQ-9c — Owner of total-unavailability UX.** Requirement 9 raises
  `LLMUnavailableError` when both backends fail. v4 assigns the graceful
  "inward/waiting" degradation loop to the Visual_Layer (Module 10) and Daemon
  orchestration (Module 8). Exactly which module catches `LLMUnavailableError`
  and drives that loop is out of Module 9's scope; recorded for the Daemon /
  Visual Layer specs. `daemon/soul_filter.py` does not catch it (confirmed by
  reading the module); this is a boundary note, not a contract change (Rule 2).
- **OQ-9d — Context-window sizing (8K/32K).** v4's Context Window table lists
  "8K tokens (casual) / 32K (deep)". Selecting/enforcing a context size and any
  75%-fill consolidation trigger are handled upstream (Soul Filter / graph
  consolidation) and/or inside a concrete transport, not by this conduit. Not
  implemented here; flagged as a build-time/transport concern.

## Flag Disposition

- **F-9a — RESOLVED** (`ARIA_Resolution_Log.md` item 14): "Gemma receives the
  identical instruction Soul Filter would send the cloud LLM (five fields, or
  Emergency Type A/B/C per item 1) plus the user message — nothing else, no
  graph access, no exception for the local model." Implemented by assembling the
  prompt once (a pure function of instruction + user message) and handing that
  same prompt to whichever backend serves (Requirement 3). No graph handle
  exists on the local path because none exists on the module at all
  (Requirement 2).
- **F-9b — RESOLVED** (`ARIA_Resolution_Log.md` item 15): the Output Validation
  Gate is owned and logic-defined by Soul_Filter (Module 5) and merely invoked
  around the LLM Interface; the covering instruction's "Output Gate under Layer
  9" is a documentation artifact of its layer numbering, "not a logic conflict."
  This module defines no gate (Requirement 5).

## Build-Time Tuning Constants

Intentionally left as placeholders, consistent with how the Resolution Log
treats undetermined cadences/sizes. None is an architectural gap:

- **Cloud retry / health-check cadence and backoff** (OQ-9a).
- **Gemma idle-unload timeout** (OQ-9b) — beyond the spec-locked "unload on
  restore," which IS implemented.
- **Context-window sizes** (OQ-9d) — 8K/32K are v4 figures for the context
  layer, not enforced by this conduit.
- **Concrete provider selection** (cloud: Claude / GPT-4o-mini / DeepSeek, TBD;
  local: a specific Gemma 4 E2B QAT runtime) — wired at the call site as an
  injected transport, never hardcoded here (Requirement 8).

### Planned (future module, NOT implemented in this spec or in current code)

**BackendRouter (planned).** A future 3-tier transport topology is planned for an
upcoming module: Gemma (local, fast/cheap tier), Groq (general-purpose cloud tier), and
Azure (reasoning-heavy cloud tier), replacing today's simpler cloud-primary /
Gemma-fallback pair (`ModelTransport` / `LocalModelTransport`). This is a forward-looking
architecture note, not a description of current behavior — `daemon/llm_interface.py`
today implements exactly two transports. Do not implement BackendRouter as part of this
spec; it will get its own requirements/design/tasks when its module is started.
