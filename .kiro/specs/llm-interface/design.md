# Design Document — Module 9: LLM Interface

> ## AMENDMENT 2026-08-24 — `serving_from_local` is replaced by `last_route`
>
> Resolution Log **item 26**. Every statement below that names
> `serving_from_local`, or gives the public surface as
> `{generate, serving_from_local}`, predates that ruling and is left in place so
> the change is legible. **The current surface is `{generate, last_route}`.**
>
> `serving_from_local` returned `self._local.is_loaded` under a docstring reading
> "cloud is currently down". Those were the same fact under v4's cloud-primary
> lifecycle and stopped being the same fact under Track A, which pins the local
> voice resident from startup and makes it the default — so the property read True
> during entirely healthy operation.
>
> `last_route` records where the last candidate actually came from, as one of five
> categorical values: `no_turn_yet`, `cloud_chosen`, `cloud_unhealthy_fallback`,
> `local_chosen`, `no_cloud_adapter`. It consults no residency. Note especially
> that line 251's reasoning below — "whether Gemma is resident is read from the
> transport itself" — is exactly what the ruling reversed: residency is no longer
> evidence of routing.
>
> One behaviour is a rule rather than a rename: an unconfigured cloud tier raises
> `LLMTransportError` identically to a real outage, so `no_cloud_adapter` OUTRANKS
> `cloud_unhealthy_fallback`. A local-first bring-up is the intended state, not
> degradation. The seam is a duck-typed `is_configured` marker read with
> `getattr(..., True)`, so `daemon/` still imports nothing from `adapters/`.
>
> The module gains ONE attribute, `_last_route`. It is a record, never an input —
> nothing reads it to decide anything — and the structural guarantee this spec
> rests on is unchanged: the constructor still takes transports only, so no graph,
> PAD, needs, appraisal or state handle can reach a prompt through it.

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
