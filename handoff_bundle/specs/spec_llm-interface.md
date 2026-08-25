# ARIA locked spec — llm-interface
Consolidated from .kiro/specs/llm-interface/{requirements,design,tasks}.md for upload.
Precedence: ARIA_Resolution_Log.md > ARIA_Soul_Spec_v4_Addendum.md > ARIA_Soul_Spec_v4.md.

> **AMENDMENT 2026-08-24 — the public surface is `{generate, last_route}`.**
> Resolution Log **item 26**. `serving_from_local` is GONE. Statements below that
> name it, or give the surface as `{generate, serving_from_local}`, predate the
> ruling and are left in place so the change is legible; where they disagree with
> this, this wins.
>
> It returned `self._local.is_loaded` under a docstring reading "cloud is
> currently down". Those were one fact under v4's cloud-primary lifecycle and
> stopped being one under Track A, which pins the local voice resident from
> startup and makes it the default — so it read True during entirely healthy
> operation. `last_route` records where the last candidate actually came from and
> consults no residency: `no_turn_yet`, `cloud_chosen`,
> `cloud_unhealthy_fallback`, `local_chosen`, `no_cloud_adapter`.
>
> One behaviour is a rule rather than a rename: an unconfigured cloud tier raises
> `LLMTransportError` identically to a real outage, so `no_cloud_adapter`
> OUTRANKS `cloud_unhealthy_fallback` — a local-first bring-up is the intended
> state, not degradation. The seam is a duck-typed `is_configured` marker read
> with `getattr(..., True)`, so `daemon/` still imports nothing from `adapters/`.
>
> The module gains ONE attribute, `_last_route`: a record, never an input. The
> structural guarantee this spec rests on is untouched — the constructor still
> takes transports only, so no graph, PAD, needs, appraisal or state handle can
> reach a prompt through it.


---

## llm-interface — requirements.md

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


---

## llm-interface — design.md

# Design Document — Module 9: LLM Interface

## Overview

The LLM_Interface is the socket for Aria's **hot-swappable language tool**. v4's
Fundamental Architectural Principle: *"Aria is not the LLM. Aria is not the
voice. She is the system that uses them. … The LLM is a hot-swappable tool. Aria
is not."* Its one job is to take the instruction Soul_Filter produced plus the
user's current message, hand it to whichever model backend is serving, and
return the model's raw text.

It is deliberately the **dumbest** module in the system:

1. **Pure conduit** — it renders one instruction + one user message into a
   prompt and returns the model's text verbatim. It applies NO judgment: no
   gate, no score, no anti-pattern check, no filtering, no content-based retry.
   All evaluation is Soul_Filter's Output Validation Gate (Addendum §4;
   `ARIA_Resolution_Log.md` item 15). v4: *"Cloud Models Are Her Knowledge, Not
   Her Voice … Aria provides the judgment"* — and that judgment is Soul_Filter's.
2. **Structurally blind** — it is constructed with model transports ONLY. It
   holds no handle to the graph, PAD, State Manager, Needs, Appraisal Chain, or
   memory. So there is no pathway through which a PAD number, a
   `relational_stage` label, a needs state, an appraisal output, or memory
   contents could enter a prompt: the module cannot reach them (steering
   "Five-field LLM boundary"; Addendum §9).
3. **Cloud-primary, Gemma-fallback** — cloud is tried first; on cloud failure
   Gemma 4 E2B QAT is loaded and serves the SAME prompt; on restore Gemma is
   unloaded (v4 Brain Structure).

This design implements `requirements.md` using only mechanisms already specified
there or in the supporting documents. It calls the **real** contract of
Soul_Filter (`daemon/soul_filter.py`) — importing `LLMClient`, `LLMInstruction`,
and the four instruction dataclasses rather than redefining them (Rule 6) — and
abstracts the actual model transport behind an injected Protocol so no provider
is hardcoded (v4: cloud provider "TBD"). Genuinely undefined items are carried
as build-time tuning flags (Rule 1); no document conflict is silently resolved
(Rule 2).

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`.

## Hard Constraints (carried from requirements.md, non-negotiable)

1. `generate(instruction, user_message, session_context="") -> str` matches
   Soul_Filter's `LLMClient` contract exactly; Soul_Filter uses this module unchanged
   (Req 1, 10).
2. Every prompt is derived SOLELY from the LLMInstruction + the User_Message.
   The module holds no graph/PAD/state/needs/appraisal/memory handle — the
   boundary is structural, not conventional (Req 2; steering).
3. The prompt is assembled ONCE, by a pure deterministic function, and the SAME
   prompt is handed to whichever backend serves — cloud and Gemma are provably
   identical (Req 3; F-9a / Resolution Log item 14).
4. Cloud is primary; Gemma loads on cloud failure, serves the same prompt, and
   unloads on restore; it stays loaded across a sustained outage (Req 4; v4).
5. NO judgment: no gate, no scoring, no filtering, no content-based retry;
   candidate text is returned verbatim even if it would fail the gate (Req 5;
   F-9b / Resolution Log item 15).
6. Emergency renders only the three Type A/B/C sentences + user message; the
   letter and internal `emergency_type` never cross (Req 6; v4).
7. All four LLMInstruction kinds render; an unknown type raises `TypeError`
   (Req 7).
8. Transports are injected; no concrete provider is imported (Req 8).
9. If both backends fail, raise `LLMUnavailableError`; never fabricate (Req 9).

## Architecture

```
                          ┌──────────────────────────────────────────────────┐
  Soul_Filter (Module 5)  │                 LLM_Interface                     │
  ───────────────────────▶│               (llm_interface.py)                  │
  generate(instruction,   │                                                   │
           user_message,  │   1. assemble_prompt(instruction, user_message,   │
           session_context)│      session_context)                           │
                          │        │  PURE · deterministic · blind             │
   LLMInstruction:        │        ▼                                          │
     FiveFieldInstruction │   AssembledPrompt { instruction_text, user_message,│
                          │                     kind, session_context }        │
     EmergencyInstruction │        │  (frozen → structural equality = F-9a)    │
     RetryInstruction     │        │                                          │
     MinimumSafeInstr.    │        ▼                                          │
   + user_message         │   2. try CLOUD first ──────────────▶ ModelTransport (cloud)
                          │        │  success → (unload Gemma if loaded)  ─┐   │  [Claude/GPT/
                          │        │            return text VERBATIM       │   │   DeepSeek — TBD,
                          │        │                                       │   │   injected]
                          │   LLMTransportError (cloud down)               │   │
                          │        ▼                                       │   │
                          │   3. load Gemma if needed ─────────▶ LocalModelTransport
                          │      serve SAME prompt from Gemma              │   │  [Gemma 4 E2B QAT,
                          │        │  success → return text VERBATIM       │   │   load/unload,
                          │        │  LLMTransportError → LLMUnavailableError   │   injected]
                          │        ▼                                       │   │
   candidate text ◀───────│──── return str (no judgment) ◀─────────────────┘   │
   (to Soul_Filter's                                                            │
    Output Gate)          │   NO graph · NO PAD · NO state · NO gate · NO score │
                          └──────────────────────────────────────────────────┘
```

Public surface:
- `generate(instruction, user_message, session_context="")` → `str` — the LLMClient
  contract; the only method Soul_Filter calls. Orchestrates cloud-primary /
  Gemma-fallback.
- `assemble_prompt(instruction, user_message, session_context="")` → `AssembledPrompt` —
  the pure, deterministic, blind prompt builder (module-level function; the basis of
  F-9a). `session_context`, when non-empty, is interleaved between `instruction_text` and
  `user_message` in `AssembledPrompt.as_text()`. Public so it can be reasoned about and
  tested in isolation.
- `serving_from_local` (read-only property) → `bool` — observability readout
  (True while Gemma is resident); a pass-through of the local transport's
  `is_loaded`, carrying no independent state and making no decision.

Everything else (`LLMTransportError`, `LLMUnavailableError`, `AssembledPrompt`,
`ModelTransport`, `LocalModelTransport`) is a small type; the four instruction
dataclasses and `LLMClient` are imported from Soul_Filter.

## Components and Interfaces

### Imported contract (NOT redefined) — `daemon/soul_filter.py`

`LLMClient` (the Protocol this module implements), `LLMInstruction` (the union),
and `FiveFieldInstruction` / `EmergencyInstruction` / `RetryInstruction` /
`MinimumSafeInstruction`. Importing them (rather than re-declaring) is what
guarantees Soul_Filter can inject this module as its `llm_client` unchanged
(Rule 6; Req 10).

### `AssembledPrompt` (frozen dataclass)

Text surfaces and nothing else:
- `instruction_text: str` — the instruction framing (five fields in fixed
  order, OR the emergency set, OR retry base+correctives, OR minimum-safe set).
- `user_message: str` — the user's current message, the ONLY personal datum
  (Addendum §9). Held SEPARATELY so a no-numbers/no-state scan can inspect
  `instruction_text` alone (the user's own words may legitimately contain
  digits).
- `kind: str` — mirrors the instruction's `kind`, for logging/observability.
- `session_context: str = ""` — the ephemeral, Daemon-assembled conversation
  transcript (`SessionBuffer.get_context()`); defaults to empty for callers/tests
  that predate it. Held as its own surface, distinct from both `instruction_text`
  and `user_message`, for the same reason `user_message` is separate: so a
  no-numbers/no-state scan of `instruction_text` is unaffected by it.
- `as_text()` → the canonical single-string rendering: `instruction_text`, then
  (when non-empty) `session_context`, then `user_message`, each separated by a
  blank line. No labels/numbering/tokens are injected (that could smuggle a
  digit or label into the framing).

Frozen so equality is structural — the F-9a proof reduces to "the prompt object
handed to cloud equals (indeed, is) the object handed to Gemma."

### `assemble_prompt(instruction, user_message, session_context="")` — pure, blind, deterministic

Dispatches on the instruction's concrete type and renders the framing from ONLY
that instruction's own fields, then pairs it with the `user_message` and
`session_context` arguments (both taken verbatim, never inspected or reconciled
against the instruction's own copy — reconciliation would be judgment). Per-kind renderers:

| Instruction | `instruction_text` is … | What NEVER appears |
|---|---|---|
| FiveFieldInstruction | Persona Anchor, Behavioral Register, Relational Register, This Moment (fixed order), then Constraints as `- ` bullets | any 6th field, any state/number (Soul_Filter authored the fields state-free) |
| EmergencyInstruction | the three Type A/B/C sentences, verbatim, one per line | the `letter`, the internal `emergency_type` (v4: "stays local … never crosses") |
| RetryInstruction | the base five fields + the state-free correctives | internal state; the correctives are authored state-free by Soul_Filter |
| MinimumSafeInstruction | the three minimum-safe sentences | five fields; state |

Constraints and multi-sentence sets are joined with `- ` bullets / newlines,
never numbered — numbering would inject a digit into the framing. An unknown
type raises `TypeError` (structural guard, not content judgment).

**Why this is F-9a (Resolution Log item 14):** `assemble_prompt` is a pure
function of `(instruction, user_message, session_context)`. `generate` calls it
exactly once per turn and shares the one result with whichever backend serves.
Identical inputs → identical prompt; the local path adds nothing. There is "no
exception for the local model" because there is no second assembly path.

### `ModelTransport` / `LocalModelTransport` (injected Protocols)

- `ModelTransport.generate(prompt) -> str` — a backend. Raises
  `LLMTransportError` (only) to signal unavailability. A cloud SDK adapter or a
  local Gemma adapter both satisfy it. No concrete provider is imported here —
  the LLM stays a hot-swappable tool (v4; Req 8).
- `LocalModelTransport(ModelTransport)` adds `is_loaded` (property), `load()`,
  `unload()` — the Gemma lifecycle ("loads on cloud failure, unloads on
  restore", v4 Brain Structure).

#### Planned (future module, NOT implemented in this spec or in current code)

**BackendRouter (planned).** A future 3-tier transport topology is planned for an
upcoming module: Gemma (local, fast/cheap tier), Groq (general-purpose cloud tier), and
Azure (reasoning-heavy cloud tier), replacing today's simpler cloud-primary /
Gemma-fallback pair (`ModelTransport` / `LocalModelTransport`). This is a forward-looking
architecture note, not a description of current behavior — `daemon/llm_interface.py`
today implements exactly two transports, wired in as shown above. Do not implement
BackendRouter as part of this spec; it will get its own requirements/design/tasks when
its module is started.

### `LLMInterface` — the module

Constructed with `cloud_transport` and `local_transport` ONLY. The absence of
any graph/PAD/state parameter is the enforcement mechanism (mirrors PAD Engine
Req 7: "the enforcement is the absence of the call path/surface itself, not a
detection branch").

`generate(instruction, user_message, session_context="")`:
1. `prompt = assemble_prompt(instruction, user_message, session_context)` — assembled once.
2. Try `cloud_transport.generate(prompt)`.
   - Success → if `local_transport.is_loaded` (we had been in fallback), call
     `local_transport.unload()` (Restore). Return the text VERBATIM.
   - `LLMTransportError` → step 3.
3. Fallback: if not `local_transport.is_loaded`, call `local_transport.load()`.
   Then `local_transport.generate(prompt)` with the SAME prompt.
   - Success → return VERBATIM.
   - `LLMTransportError` → raise `LLMUnavailableError` (from the local error).

## Fallback lifecycle — load on failure, unload on restore (v4 Brain Structure)

Trying the cloud first on EVERY turn is what makes Restore detectable without a
separate probe: the first post-outage cloud success naturally triggers the
Gemma unload. During a sustained outage, `is_loaded` short-circuits the load, so
Gemma is loaded once, not per turn, and is never unloaded mid-outage (Req 4.6).
This is the minimal mechanism that satisfies the spec-locked "loads on cloud
failure, unloads on restore" with no invented cadence. Any additional
health-check/backoff (OQ-9a) or memory-reclaiming idle-unload (OQ-9b) is a
build-time tuning flag layered onto a real transport, not part of this logic.

## No judgment — the module never reads the candidate (Req 5; ResLog 15)

The returned `str` is passed through untouched. There is deliberately no code
path that inspects candidate content: no gate, no `moral_schema` import, no
anti-pattern scan, no confidence score, no "retry if it looks bad." Retries are
Soul_Filter's decision, expressed by Soul_Filter re-calling `generate` with a
`RetryInstruction` (which this module renders like any other instruction). The
public surface is exactly `{generate, serving_from_local}` — there is no
`gate` / `validate` / `score` / `check` / `filter` method to accidentally grow
one. This is F-9b: the Output Gate lives in Soul_Filter (ResLog item 15).

## Total unavailability — report, never fabricate (Req 9; v4)

When both backends fail, `LLMUnavailableError` is raised (chaining the local
transport's error as `__cause__`). Fabricating a reply would be exactly the
"voice" this module must not have (v4 "Cloud Models Are Her Knowledge, Not Her
Voice"). The graceful "inward/waiting" degradation loop is the Visual_Layer's
(Module 10), orchestrated by the Daemon (Module 8) — not this module (OQ-9c).
`daemon/soul_filter.py` does not catch this error (confirmed by reading it); no
contract change is required or made (Rule 2).

## Error handling & boundaries

- The only failure the Interface treats as "backend unavailable" is
  `LLMTransportError`. Other exceptions (adapter bugs) propagate unchanged —
  a fallback never masks a defect (Req 8.3).
- `load()`/`unload()` are guarded by `is_loaded`, so they are idempotent across
  repeated calls within an outage / after a restore.
- The Interface holds no persistent state beyond its two transports; whether
  Gemma is resident is read from the transport itself (`serving_from_local`).
- The Interface never writes PAD, the graph, or any store — it has no handle to
  any of them (steering PAD-purity; "graph is the only memory").

## Testing strategy (see tests/test_llm_interface.py)

Plain pytest, NO hypothesis (Modules 1/3/4/5 precedent). Fakes: a
`FakeCloudTransport` and a `FakeLocalTransport` (record every prompt; can be set
to raise `LLMTransportError`); a `FakeEmbedding` for the REAL `MemoryGraph` in
integration tests. The five mandated proofs plus the structural boundary proof:
- prompt contains ONLY instruction fields + user message (digit/state scan on
  `instruction_text`; emergency type/letter absence);
- cloud and Gemma receive the IDENTICAL prompt (object identity + equality),
  per instruction kind and end-to-end via SoulFilter (F-9a);
- cloud failure loads/serves Gemma; restore unloads Gemma; sustained outage
  loads once; both-down raises `LLMUnavailableError`;
- verbatim passthrough of manipulative/empty/odd text; no gate/score surface;
  no state-source imports; constructor takes transports only (no judgment; no
  leak path);
- real `SoulFilter.respond()` flows (normal, retry, emergency, and full
  fallback-through-Gemma) with this Interface injected as `llm_client`.

## Flag Disposition

- **F-9a — RESOLVED** (`ARIA_Resolution_Log.md` item 14): Gemma receives the
  identical instruction + user-message prompt as cloud. Guaranteed by a single
  pure `assemble_prompt` whose one result is shared with whichever backend
  serves; the local path adds nothing; the module has no graph handle at all.
- **F-9b — RESOLVED** (`ARIA_Resolution_Log.md` item 15): the Output Validation
  Gate is owned/logic-defined by Soul_Filter and merely wrapped around this
  Interface; this module defines no gate. The covering instruction's "Output
  Gate under Layer 9" is a documentation artifact of its layer numbering.
- **OQ-9a (cloud retry/health-check cadence), OQ-9b (Gemma idle-unload timeout),
  OQ-9c (owner of total-unavailability UX), OQ-9d (context-window sizing)** —
  FLAGGED as build-time tuning / other-module concerns; not invented here. The
  spec-locked "unload on restore" IS implemented; anything beyond it is left as
  a placeholder per Rule 1 and the Resolution Log's treatment of cadences/sizes.


---

## llm-interface — tasks.md

# Implementation Plan — Module 9: LLM Interface

This plan implements `design.md` exactly as written. Each task is small and
independently testable. All tasks are complete; the suite is green
(`python3 -m pytest tests/test_llm_interface.py -q` → 35 passed; full suite →
229 passed, 194 prior + 35 new, no regressions).

## Quoted from design.md (verified against current file content)

**The contract this module implements** (imported, never redefined — Rule 6),
from `daemon/soul_filter.py`:
```python
@runtime_checkable
class LLMClient(Protocol):
    def generate(self, instruction: "LLMInstruction", user_message: str) -> str: ...

LLMInstruction = Union[
    FiveFieldInstruction, EmergencyInstruction, RetryInstruction, MinimumSafeInstruction
]
```

**The fallback lifecycle** (design.md "Fallback lifecycle"): try cloud first →
success returns verbatim and unloads Gemma if it was loaded (Restore) → cloud
`LLMTransportError` loads Gemma (once) and serves the SAME prompt → local
`LLMTransportError` raises `LLMUnavailableError`. "Loads on cloud failure,
unloads on restore" (v4 Brain Structure).

**The F-9a mechanism** (design.md): `assemble_prompt` is a pure function of
`(instruction, user_message)`; `generate` calls it once and shares the one
`AssembledPrompt` with whichever backend serves — identical inputs → identical
prompt → identical bytes to cloud and Gemma (Resolution Log item 14).

---

## Tasks

- [x] 1. Module scaffold and contract import
  - Create `daemon/llm_interface.py`; import `LLMClient`, `LLMInstruction`, and
    the four instruction dataclasses from `daemon.soul_filter` (never redefine).
  - Confirm no circular import: `soul_filter.py` does not import
    `llm_interface` (verified).
  - _Requirements: 1.1, 10.1, 10.2_

- [x] 2. Transport failure signals
  - `LLMTransportError` — the ONLY signal a transport uses to mean "unavailable
    → fall back". `LLMUnavailableError` — raised by the Interface when both
    backends fail (never fabricate).
  - _Requirements: 8.3, 9.1, 9.2_

- [x] 3. `AssembledPrompt` frozen dataclass
  - Fields `instruction_text: str`, `user_message: str`, `kind: str`; method
    `as_text()` = `instruction_text` + blank line + `user_message` (no injected
    labels/numbering). Frozen → structural equality (the F-9a substrate).
  - Unit test: `as_text()` is exactly framing + user message; the user's digits
    appear only in the user-message portion.
  - _Requirements: 2.4, 3.1_

- [x] 4. `assemble_prompt(instruction, user_message)` — pure, blind, deterministic
  - Dispatch on concrete instruction type; render framing from ONLY the
    instruction's own fields; pair with the `user_message` argument verbatim
    (no inspection/reconciliation). Unknown type → `TypeError`.
  - Unit tests: deterministic for identical inputs; unknown type raises;
    `user_message` argument (not the instruction's own copy) is what crosses.
  - _Requirements: 2.1, 3.1, 3.4, 5.3, 7.4_

- [x] 5. Per-kind renderers
  - `_render_five_field`: Persona Anchor, Behavioral Register, Relational
    Register, This Moment in FIXED ORDER, then Constraints as `- ` bullets
    (never numbered — no digit injected). Uses `field_texts()`-equivalent
    content only.
  - `_render_emergency`: the three Type A/B/C sentences only; NO `letter`, NO
    `emergency_type` (v4 "stays local … never crosses").
  - `_render_retry`: base five fields + state-free correctives.
  - `_render_minimum_safe`: the three minimum-safe sentences.
  - Unit tests: five-field prompt contains each `field_texts()` element in fixed
    order and no digit/state; emergency prompt contains the three sentences and
    NO type name/value and NO "Type X"/letter label and no digit; retry = base +
    correctives; minimum-safe = three sentences.
  - _Requirements: 6.1, 6.2, 6.3, 7.1, 7.2, 7.3_

- [x] 6. Injected transport Protocols
  - `ModelTransport.generate(prompt) -> str`; `LocalModelTransport` adds
    `is_loaded` (property), `load()`, `unload()`. Both `@runtime_checkable`. No
    concrete provider imported.
  - Unit test: the fakes satisfy `ModelTransport` / `LocalModelTransport`.
  - _Requirements: 8.1, 8.2_

- [x] 7. `LLMInterface.__init__` — transports only (the structural boundary)
  - Keyword-only `cloud_transport`, `local_transport`; store as `_cloud`,
    `_local`. NO graph/PAD/state/needs/appraisal/memory/embedding parameter.
  - Unit tests: constructor params are exactly `{cloud_transport,
    local_transport}` with no forbidden name; instance `vars` are exactly
    `{_cloud, _local}`; the module imports none of `pad_engine`,
    `graph_manager`, `appraisal_chain`, `state_manager`, `moral_schema` (import
    scan) and DOES import `soul_filter`.
  - _Requirements: 2.2, 2.3_

- [x] 8. `generate` — cloud-primary orchestration + verbatim passthrough
  - Assemble once; try cloud; on success return verbatim and unload Gemma if it
    was loaded; on `LLMTransportError` delegate to the local path.
  - Unit tests: healthy cloud never loads Gemma and returns its text verbatim;
    manipulative/empty/odd cloud text is returned unchanged (no judgment).
  - _Requirements: 1.2, 1.3, 4.1, 4.2, 5.1, 5.2, 5.4_

- [x] 9. `_serve_from_local` — load on failure, same prompt, or report
  - Load Gemma if not loaded; serve the SAME `AssembledPrompt`; on local
    `LLMTransportError` raise `LLMUnavailableError` (chained), never fabricate.
  - Unit tests: cloud failure loads + serves Gemma (verbatim, incl.
    manipulative text); both-down raises `LLMUnavailableError` with the local
    error as `__cause__` and after attempting `load()`.
  - _Requirements: 4.3, 4.4, 5.4, 9.1, 9.2_

- [x] 10. Restore + sustained-outage behavior
  - First post-outage cloud success unloads Gemma; a sustained outage loads
    Gemma exactly once and never unloads mid-outage.
  - Unit tests: `test_fallback_unloads_gemma_on_cloud_restore`,
    `test_fallback_stays_on_gemma_across_a_sustained_outage`.
  - _Requirements: 4.5, 4.6_

- [x] 11. `serving_from_local` observability property
  - Read-through of `local_transport.is_loaded`; no independent state, no
    decision.
  - Covered by the fallback/restore tests.
  - _Requirements: 5.1 (it decides nothing); 9.3 (readout for the degradation
    owner)_

- [x] 12. F-9a proofs — identical prompt to cloud and Gemma
  - Force a cloud outage; assert `cloud.received[0] is local.received[0]` AND
    equality, parametrized over all four instruction kinds; assert deterministic
    assembly; assert it holds end-to-end via `SoulFilter.respond` (normal +
    emergency).
  - _Requirements: 3.2, 3.3, 3.4_

- [x] 13. Contract conformance
  - `isinstance(interface, soul_filter.LLMClient)`; `generate` signature is
    `(self, instruction, user_message)`.
  - _Requirements: 1.1, 1.4, 10.2_

- [x] 14. No-gate/no-scoring surface proof (F-9b)
  - Assert the public surface is exactly `{generate, serving_from_local}` and no
    method name contains gate/validate/score/check/judge/filter/moderate/
    correct/retry.
  - _Requirements: 5.1, 5.2, 5.3_

- [x] 15. Integration with the REAL Soul Filter (Module 5)
  - Build a real `SoulFilter` (real `PADEngine`, real `MemoryGraph` +
    `FakeEmbedding`) with `llm_client=LLMInterface(...)`; drive
    `SoulFilter.respond()`:
    - normal turn → cloud candidate flows through; the assembled five-field
      prompt carries `PERSONA_ANCHOR` and no digit; user message carried;
    - gate-failing first candidate → SoulFilter retries → the second call to the
      Interface carries a `RetryInstruction` (kind `"retry"`) with the corrective
      and no digit;
    - emergency → Interface prompt kind `"emergency"`; internal type does not
      cross; gate bypassed;
    - cloud down → the ENTIRE respond flow completes via Gemma and the Output
      Gate still runs on Gemma's candidate; Gemma got the identical prompt;
    - Energy<30 → "do not overextend" crosses with no digit.
  - Do NOT modify `daemon/soul_filter.py` (unchanged; verified).
  - _Requirements: 1.4, 3.2, 5.4, 6.1, 6.2, 10.1, 10.3_

- [x] 16. Full-suite verification
  - `python3 -m pytest tests/test_llm_interface.py -q` → 35 passed.
  - `python3 -m pytest -q` → 229 passed (194 prior + 35), no regressions.
  - Confirm, by inspection and tests, that the two Module 9 flags are resolved
    (F-9a via ResLog 14, F-9b via ResLog 15) and OQ-9a…9d remain flagged
    build-time/other-module concerns, not invented here.
  - _Requirements: all_

