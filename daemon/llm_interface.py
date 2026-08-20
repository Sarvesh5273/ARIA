"""ARIA — Module 9: LLM Interface (`daemon/llm_interface.py`).

Responsibility (`ARIA_Module_Build_Plan.md`, Module 9): send the five-field
instruction + the user's current message to the cloud LLM and return candidate
text, loading Gemma locally only on cloud failure and unloading on restore;
apply NO judgment (all validation is in Soul Filter — Module 5).

------------------------------------------------------------------------------
THE FRAME (steering/project-rules.md; v4 "The Fundamental Architectural
Principle"): "Aria is not the LLM. Aria is not the voice. She is the system
that uses them." The LLM is a HOT-SWAPPABLE TOOL; Aria is not. This module is
that tool's socket — a pure conduit. It is deliberately dumb: it renders one
instruction + one user message into a prompt, hands it to whichever backend is
serving, and returns the raw text. It never judges, scores, gates, filters,
rewrites, retries, or fabricates. (v4 "Cloud Models Are Her Knowledge, Not Her
Voice": the model returns raw knowledge; "Aria provides the judgment" — and
Aria's judgment is Soul Filter's Output Validation Gate, NOT here.)

THE FIVE-FIELD BOUNDARY (steering "Five-field LLM boundary"; Addendum §9;
`ARIA_Resolution_Log.md` item 14): The model receives exactly three surfaces:
(1) the instruction Soul Filter produced — the five fields in fixed order, OR
the emergency Type A/B/C set, (2) an optional session_context (the ephemeral
conversation transcript for the current session, passed in as an opaque
string), and (3) the user's current message. This module still holds NO
handle to the graph, PAD, State Manager, Needs, or Appraisal Chain, so no
internal state can reach a prompt through it; the contents of session_context
are guaranteed upstream by SessionBuffer, not here. There is therefore
no pathway through which a PAD number, a `relational_stage` label, a needs
state, an appraisal output, a salience/poignancy value, or memory contents
could enter a prompt: the module cannot reach them.

F-9a (`ARIA_Resolution_Log.md` item 14 — RESOLVED): the Gemma local-fallback
path receives the IDENTICAL instruction + user-message limit as the cloud path.
This module assembles the prompt ONCE (`assemble_prompt`, a pure function of
`(instruction, user_message)`) and hands that SAME `AssembledPrompt` to
whichever backend serves — so cloud and Gemma provably receive an identical
prompt, "no exception for the local model."

F-9b (`ARIA_Resolution_Log.md` item 15 — RESOLVED): the Output Gate lives in
Soul Filter (Module 5), not here. This module defines and runs NO gate, no
scoring, no anti-pattern check. The covering instruction's "Output Gate under
Layer 9" label is a documentation artifact only (item 15).

BRAIN STRUCTURE (v4 "Brain Structure (Three Tiers — Updated Conv.6)"):
    CLOUD LLM (Primary)  — Claude / GPT-4o-mini / DeepSeek (TBD)
        ↕ if cloud fails ↕
    Gemma 4 E2B QAT (Local Fallback Only) — loads on cloud failure, unloads on
        restore.
The concrete provider is TBD in v4 and is NOT hardcoded here (Rule: the LLM is
a hot-swappable tool). Both tiers are reached through an INJECTED transport
Protocol (`ModelTransport` / `LocalModelTransport`) — a real cloud SDK or a
real Gemma runtime is wired in at the call site, never imported here.

Dependencies are INJECTED and their REAL/contracted interfaces are called,
never redefined (Rule 6). The Soul Filter contract types (`LLMClient`,
`LLMInstruction`, and the four instruction dataclasses) are IMPORTED from
`daemon/soul_filter.py` — never re-declared — so Soul Filter can use this
module as its `llm_client` unchanged.

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`. Rule 1: mechanisms
not in the docs are FLAGGED (see "Build-time tuning flags" below), never
invented.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Protocol, runtime_checkable

# --- REAL contract, imported and never redefined (Rule 6) ------------------
# Module 9 IS the concrete implementation of Soul Filter's LLMClient contract;
# it must satisfy these exact types so Soul Filter uses it unchanged.
from daemon.soul_filter import (  # noqa: F401  (LLMClient re-exported for callers)
    LLMClient,
    LLMInstruction,
    FiveFieldInstruction,
    EmergencyInstruction,
    RetryInstruction,
    MinimumSafeInstruction,
)


# ===========================================================================
# Transport failure signals.
# ===========================================================================
class LLMTransportError(Exception):
    """Raised BY an injected transport to signal it could not fulfil this
    request (timeout, connection reset, 5xx, rate-limit, model-not-loaded, …).

    This is the ONLY signal the Interface treats as "this backend is
    unavailable → fall back / degrade". The concrete transport adapter (wired
    in at the call site) is responsible for translating its provider-specific
    failures into this error; genuine programming bugs are NOT caught here and
    propagate normally, so a fallback is never silently masking a defect."""


class LLMUnavailableError(Exception):
    """Raised by the Interface when BOTH the cloud and the local transports
    failed for one turn — no candidate could be obtained from any backend.

    The Interface does NOT fabricate text in this case: inventing a reply would
    be exactly the judgment/voice this module is forbidden to have (v4 "Cloud
    Models Are Her Knowledge, Not Her Voice"). It reports the mechanical
    unavailability upward; the graceful-degradation experience (the Visual
    Layer's "inward/waiting" loop, v4 Module 10; Daemon orchestration, Module
    8) is owned there, NOT here. See OQ-9c."""


# ===========================================================================
# Assembled prompt — the ONLY thing that crosses to a model.
# ===========================================================================
@dataclass(frozen=True)
class AssembledPrompt:
    """The COMPLETE prompt for one turn, derived PURELY from one
    `LLMInstruction` + the user's current message. It has exactly three text
    surfaces and nothing else:

      * ``instruction_text`` — the five fields in FIXED ORDER (Addendum §9),
        OR the emergency Type A/B/C set, OR a retry (base five fields +
        state-free correctives), OR the minimum-safe set. Authored upstream by
        Soul Filter; this module only serialises it, never edits it.
      * ``user_message`` — the user's current message. Held SEPARATELY from
        ``instruction_text`` so a no-numbers/no-state scan can inspect the
        instruction framing alone (the user's own words may legitimately contain
        digits).
      * ``session_context`` — the ephemeral conversation transcript for the
        current session (Recent turns / Medium summaries / Old topic tags),
        rendered by SessionBuffer and passed through verbatim. Optional; empty
        string when the buffer is empty or a caller supplies none. Interleaved
        between ``instruction_text`` and ``user_message`` by ``as_text()``.

    Provider-agnostic: a cloud SDK adapter typically maps ``instruction_text``
    → system role and ``user_message`` → the user turn; a local Gemma adapter
    does the same. ``as_text()`` is the canonical single-string rendering used
    for logging and for the identical-prompt proof.

    FROZEN so equality is structural: the F-9a proof is simply that the object
    handed to cloud equals the object handed to Gemma (`assemble_prompt` is
    called once per turn and the one result is shared)."""

    instruction_text: str
    user_message: str
    kind: str
    session_context: str = ""


    def as_text(self) -> str:
        parts = [self.instruction_text]
        if self.session_context:
            parts.append(self.session_context)
        parts.append(self.user_message)
        return "\n\n".join(parts)


# ===========================================================================
# Prompt assembly — a PURE function of (instruction, user_message).
# ===========================================================================
def assemble_prompt(instruction: LLMInstruction, user_message: str, session_context: str = "") -> AssembledPrompt:
    """Render one Soul Filter instruction + the user's current message into an
    `AssembledPrompt`, using ONLY the instruction's own fields and the given
    message.

    This is a PURE function — deterministic, side-effect-free, and blind to
    everything except its two arguments. It is the same function on the cloud
    path and the Gemma path, which is exactly what makes F-9a hold (Resolution
    Log item 14): identical inputs → identical prompt → identical bytes to
    whichever model serves.

    It performs NO judgment: it does not inspect, score, filter, or reconcile
    content; it does not compare ``user_message`` against the instruction's own
    copy; it dispatches purely on the instruction's concrete type."""
    if isinstance(instruction, FiveFieldInstruction):
        instruction_text = _render_five_field(instruction)
    elif isinstance(instruction, EmergencyInstruction):
        instruction_text = _render_emergency(instruction)
    elif isinstance(instruction, RetryInstruction):
        instruction_text = _render_retry(instruction)
    elif isinstance(instruction, MinimumSafeInstruction):
        instruction_text = _render_minimum_safe(instruction)
    else:  # pragma: no cover - structural guard, not judgment
        raise TypeError(
            "LLM Interface received an unknown instruction type: "
            f"{type(instruction)!r}. Only Soul Filter's LLMInstruction union "
            "(FiveFieldInstruction, EmergencyInstruction, RetryInstruction, "
            "MinimumSafeInstruction) is accepted."
        )
    # The user's current message is taken from the contract argument verbatim —
    # NOT inspected, NOT reconciled against the instruction's own copy (that
    # would be judgment). It is the ONLY personal datum that crosses.
    return AssembledPrompt(
        instruction_text=instruction_text,
        user_message=user_message,
        kind=instruction.kind,
        session_context=session_context,
    )


def _render_five_field(instr: FiveFieldInstruction) -> str:
    """The five fields in FIXED ORDER (Addendum §9): Persona Anchor, Behavioral
    Register, Relational Register, This Moment, then the closed Constraints list
    (each a specific prohibition). Uses only the instruction's own field text —
    no paraphrase, no added framing. Constraints are joined as plain "- " lines
    (a hyphen bullet, never a number, so no digit is introduced by formatting).
    """
    parts = [
        instr.persona_anchor,
        instr.behavioral_register,
        instr.relational_register,
        instr.this_moment,
    ]
    if instr.constraints:
        parts.append("\n".join(f"- {c}" for c in instr.constraints))
    return "\n\n".join(p for p in parts if p)


def _render_emergency(instr: EmergencyInstruction) -> str:
    """The fixed three-instruction emergency set, verbatim, one per line (v4
    "The Three Emergency Instruction Sets"). The routing metadata — the letter
    (A/B/C) and the internal `emergency_type` classification — is NOT rendered:
    v4 states the type "stays local … never crosses to the cloud", and the set
    "replaces the entire normal output … Nothing else is sent." Only the three
    sentences cross, plus (via AssembledPrompt) the user message."""
    return "\n".join(instr.instructions)


def _render_retry(instr: RetryInstruction) -> str:
    """The base five fields (fixed order) followed by the fixed corrective
    sentence(s) for the failed check(s) (v4 gate "retry once with corrective
    instruction"). The correctives are authored state-free by Soul Filter
    ("What Is Never Sent to Cloud"); this module only appends them verbatim."""
    base_text = _render_five_field(instr.base)
    corrective_text = "\n".join(instr.correctives)
    if not corrective_text:
        return base_text
    return f"{base_text}\n\n{corrective_text}"


def _render_minimum_safe(instr: MinimumSafeInstruction) -> str:
    """The three-instruction minimum-safe-output set, verbatim, one per line
    (v4 "MINIMUM SAFE OUTPUT MODE"). No state, no five fields."""
    return "\n".join(instr.instructions)


# ===========================================================================
# Injected transports (the hot-swappable tool). No provider is named here.
# ===========================================================================
@runtime_checkable
class ModelTransport(Protocol):
    """A model backend. Given an assembled prompt, return the model's raw
    candidate text. Raise `LLMTransportError` (only) to signal unavailability.

    This is the seam that keeps the LLM a hot-swappable tool: a Claude adapter,
    a GPT-4o-mini adapter, a DeepSeek adapter, or a local Gemma adapter all
    satisfy this one method. No concrete provider is imported by this module."""

    def generate(self, prompt: AssembledPrompt) -> str:
        ...


@runtime_checkable
class LocalModelTransport(ModelTransport, Protocol):
    """A LOCAL model backend with an explicit load/unload lifecycle — Gemma 4
    E2B QAT (v4). It "Loads on cloud failure, unloads on restore" (v4 Brain
    Structure), so the socket must be able to bring it up and tear it down and
    to ask whether it is currently resident."""

    @property
    def is_loaded(self) -> bool:
        ...

    def load(self) -> None:
        ...

    def unload(self) -> None:
        ...


# ===========================================================================
# The LLM Interface — Module 9.
# ===========================================================================
class LLMInterface:
    """Concrete implementation of Soul Filter's `LLMClient` contract
    (`generate(instruction, user_message) -> str`). A judgment-free conduit:
    cloud-primary with a Gemma local fallback, both behind INJECTED transports.

    Structural boundary (the whole point of this module): it is constructed
    with model transports ONLY. It holds NO graph, PAD, State Manager, Needs,
    Appraisal, embedding, or memory handle — so no such data can reach a prompt
    through it. Its only per-turn inputs are the `LLMInstruction` + the
    `user_message` the contract hands to `generate()`.

    Fallback lifecycle (v4 Brain Structure "loads on cloud failure, unloads on
    restore"): each turn tries the cloud transport FIRST.
      * cloud succeeds → return its text verbatim; if the local model was
        loaded (we were in fallback), UNLOAD it — this is the "restore".
      * cloud raises `LLMTransportError` → LOAD the local model if not already
        resident and serve the SAME prompt from it (F-9a).
      * local also raises `LLMTransportError` → raise `LLMUnavailableError`
        (never fabricate a reply).
    Trying cloud-first every turn is what detects "restore" and triggers the
    unload; the retry/health-check cadence and any memory-reclaiming idle-unload
    are build-time tuning flags, not invented here (see OQ-9a / OQ-9b)."""

    def __init__(
        self,
        *,
        cloud_transport: ModelTransport,
        local_transport: LocalModelTransport,
    ) -> None:
        # ONLY transports are injected. There is deliberately no graph/PAD/state
        # parameter — the absence of the handle is the guarantee (mirrors PAD
        # Engine Req 7: enforcement is the absence of the surface, not a check).
        self._cloud = cloud_transport
        self._local = local_transport

    # -- Soul Filter's LLMClient contract ----------------------------------
    def generate(
        self,
        instruction: LLMInstruction,
        user_message: str,
        session_context: str = "",
        transport: Optional[ModelTransport] = None,
    ) -> str:
        """Render one candidate from the instruction + user's current message.

        The client is BLIND (Addendum §9): it sees only what the instruction
        carries. Prompt assembly happens EXACTLY ONCE, in one call site below,
        regardless of which path runs — this is what keeps the F-9a
        identical-prompt property (Resolution Log item 14) intact whether the
        cloud/local internal chain serves, or a caller-supplied transport does.

        TWO PATHS, chosen by whether `transport` is supplied:

        1. `transport` is not None (CALLER'S DECISION): the caller — in
           practice `daemon/aria_daemon.py` via `BackendRouter.select()` —
           has already decided which backend should serve this turn. This
           module does not second-guess that choice: it calls
           `transport.generate(prompt)` and returns the result VERBATIM. It
           does NOT try the cloud first, and it does NOT touch the local
           model's load/unload lifecycle on this path — that lifecycle is
           the supplied transport's own concern (or, for Gemma specifically,
           the Daemon's / BackendRouter's, via `ensure_local_loaded()`). If
           the supplied transport raises `LLMTransportError`, it PROPAGATES
           unchanged: the caller chose that transport, so the caller owns
           the failure. This module does NOT silently fall back to the
           internal cloud/local chain on that error — doing so would make a
           routing decision here, which is not this module's job (Resolution
           Log item 15: no judgment, no validation, verbatim passthrough).

        2. `transport` is None (BACKWARD-COMPATIBLE internal path): the
           EXISTING logic runs completely unchanged — cloud is primary; on
           `LLMTransportError` the local model is loaded (if not already)
           and served the SAME prompt; if local also fails,
           `LLMUnavailableError` is raised; on cloud success, if local was
           loaded, it is unloaded ("unload on restore", v4).

        NOTE (lifecycle interaction): the internal path (path 2) UNLOADS the
        local model whenever the cloud succeeds ("unload on restore", v4).
        That conflicts with the architect decision that Gemma loads at
        startup and stays resident (16GB Mac; 7.7GB model fits). Once the
        Daemon is wired to `BackendRouter` it ALWAYS supplies `transport`
        (path 1), so the internal path — and its unload — is never taken in
        production. The internal path is retained here for backward
        compatibility only, and remains covered by
        `test_fallback_unloads_gemma_on_cloud_restore`."""
        # Assemble ONCE. This single prompt is what any backend receives on
        # either path, which is the mechanical guarantee behind F-9a
        # (Resolution Log item 14).
        prompt = assemble_prompt(instruction, user_message, session_context)

        if transport is not None:
            # CALLER'S DECISION (see path 1 above). Opaque passthrough: no
            # judgment, no cloud-first attempt, no load/unload lifecycle
            # touch, no swallowing of LLMTransportError.
            return transport.generate(prompt)  # verbatim — no judgment

        try:
            candidate = self._cloud.generate(prompt)
        except LLMTransportError as cloud_error:
            # Cloud is down → serve from the local fallback with the SAME prompt.
            return self._serve_from_local(prompt, cloud_error)

        # Cloud succeeded. If the local model was up (we had been in fallback),
        # this is the "restore" — unload it (v4 "unloads on restore").
        if self._local.is_loaded:
            self._local.unload()
        return candidate  # verbatim — no judgment

    def _serve_from_local(
        self, prompt: AssembledPrompt, cloud_error: LLMTransportError
    ) -> str:
        """Cloud failed: load Gemma if needed and serve the IDENTICAL prompt.
        If the local model also fails, report unavailability (never invent)."""
        if not self._local.is_loaded:
            self._local.load()  # "Loads on cloud failure" (v4)
        try:
            return self._local.generate(prompt)  # SAME prompt object (F-9a)
        except LLMTransportError as local_error:
            raise LLMUnavailableError(
                "Both cloud and local (Gemma) transports failed this turn; no "
                "candidate could be obtained. The LLM Interface does not "
                "fabricate a reply (v4 'Cloud Models Are Her Knowledge, Not Her "
                "Voice'); graceful degradation is the Daemon/Visual Layer's job "
                "(Modules 8/10), not the Interface's."
            ) from local_error

    # -- Read-only observability (NOT a decision surface) ------------------
    @property
    def serving_from_local(self) -> bool:
        """True while the local fallback is resident (cloud is currently down).
        A read-through of the local transport's own `is_loaded` — the Interface
        keeps no independent state and makes no judgment; this is a convenience
        readout for the Daemon/Visual Layer's degradation UX (Modules 8/10)."""
        return self._local.is_loaded
