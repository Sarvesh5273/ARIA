"""BackendRouter — 3-tier language-model backend selection (`daemon/backend_router.py`).

RESPONSIBILITY: decide WHICH language-model backend transport should serve a
turn — a keyword-heuristic tier-2 ("reasoning") classifier, a session-scoped
manual override, a cheap cached health probe, and a `select()` method that
combines them into a routing decision. It selects; it never generates text
itself.

THE THREE TIERS AND THE CANONICAL VOCABULARY:

    Tier 0  local      Gemma 4 12B MLX via Ollama/MLX  (~7.7GB RAM, on-device)
    Tier 1  general    Groq Llama 3.3 70B              (free tier, HTTP API)
    Tier 2  reasoning  Azure Foundry -> Kimi K2.7       (paid, HTTP API)

Pinned everywhere in this module and its tests as:

    TIER_TO_KEY = {"tier_0": "gemma", "tier_1": "groq", "tier_2": "azure"}
    VALID_TIERS = ("tier_0", "tier_1", "tier_2")

Health dictionaries are always keyed by "gemma" / "groq" / "azure". Overrides
are always one of the strings "tier_0" / "tier_1" / "tier_2", or None.

THIS MODULE IS INFRASTRUCTURE, NOT PERSONALITY. It touches NO PAD (emotion),
memory graph, needs system, appraisal chain, poignancy, relational stage, or
any other Soul state, and holds NO handle to any of those modules — the
absence of the handle is the guarantee, exactly as `daemon/llm_interface.py`,
`daemon/audio_pipeline.py` and `daemon/visual_layer.py` each argue their own
structural boundary by what they do NOT import or hold. It computes no
feeling and carries no personality logic. The only daemon module it imports
from is `daemon/llm_interface.py`, for the `ModelTransport` /
`LocalModelTransport` transport contracts (Rule 6: depend on the real
interface, never redefine it). No concrete provider (Ollama, MLX, the Groq
SDK, the Azure SDK, `requests`, `httpx`) is imported here — all three
transports are INJECTED at construction, exactly like `LLMInterface`'s own
`cloud_transport` / `local_transport`.

WHAT THIS MODULE EXPLICITLY DOES NOT DO, because those belong to the Daemon
(Module 8):

  - It does NOT run the classifier before Stage 0 of the appraisal pipeline —
    the Daemon calls `classify()` / `select()` at whatever point in its own
    turn-routing it chooses.
  - It does NOT implement the pause-and-ask UX state machine that would ask
    the user "this looks like it needs deeper reasoning — use Azure?" when
    `select()` returns `(None, True)`. This module only raises the flag by
    returning `propose=True`; the Daemon decides what to do with it.
  - It does NOT intercept meta-commands ("use cloud", "stay local", ...).
  - It does NOT call any language model. `daemon/llm_interface.py` does that;
    this module only decides which transport a caller should hand to it.

META-COMMAND VOCABULARY (reference-only documentation for the Daemon; this
module does not read user text for meta-commands and does not act on this
list itself — it is recorded here only because the Daemon will need it when
it wires meta-command interception on top of `set_override`):

    "use cloud" / "switch to cloud" / "use Kimi"            -> tier_2
    "stay local" / "use Gemma" / "go local"                 -> tier_0
    "use Groq" / "use general"                              -> tier_1
    "go back to normal" / "reset backend" / "default mode"  -> None

FLAG A — CLOSED (Track A). `daemon/llm_interface.py`'s
`generate(instruction, user_message, session_context="", transport=None)` now
accepts an optional caller-supplied transport: when supplied, it is called
directly (verbatim passthrough, no cloud-first attempt, no lifecycle touch),
bypassing the internal cloud-primary/local-fallback chain entirely. Selection
is wired end-to-end: `daemon/aria_daemon.py`'s `route_inbound_turn()` calls
`BackendRouter.select()` and hands the result to
`SoulFilter.respond(transport=...)`, which passes it through opaquely to
`LLMInterface.generate(transport=...)`. Gemma's lifecycle owner is now the
Daemon: `AriaDaemon.startup()` calls `ensure_local_loaded()` once (below), and
nothing in this codebase unloads it afterward (architect decision: Gemma
loads at startup and stays resident). See `HANDOFF_NOTES.md` "Track A" for
the full record.

FLAG B — FIXED. Health probing is no longer optimistic. A non-local transport
that exposes no `HealthProbe` can no longer answer the question, so `_probe_one`
returns `None` (UNKNOWN) rather than `True`, and `check_health()` does NOT put
UNKNOWN in the healthy set — only an explicit `is_healthy() -> True` counts as
healthy. Consequences, all intended: a tier-2 keyword match no longer proposes
escalation unless Azure explicitly reports healthy; Groq is only selected when
it explicitly reports healthy; and the all-down degradation return `(None,
False)` is reachable instead of dead. A transport that IS up but simply cannot
say so is treated as unavailable for ROUTING purposes only — nothing prevents a
caller from handing it to `generate()` directly, and a genuinely down transport
still surfaces as an `LLMTransportError` there. No timeout, retry count, or
backoff is invented here.

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`. Rule 1: mechanisms
not described in the docs are FLAGGED (see FLAG A / FLAG B above and the
TODO(build-time) markers below), never invented.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable, Dict, Literal, Optional, Protocol, Tuple, runtime_checkable

# --- REAL interface (imported, never redefined; Rule 6) --------------------
# The only daemon module this router depends on. No concrete provider
# (Ollama/MLX/Groq SDK/Azure SDK/requests/httpx) is imported anywhere here —
# all three transports are injected at construction.
from daemon.llm_interface import ModelTransport, LocalModelTransport


# ===========================================================================
# Canonical tier vocabulary (pinned once, used everywhere — including tests).
# ===========================================================================

VALID_TIERS: Tuple[str, str, str] = ("tier_0", "tier_1", "tier_2")

TIER_TO_KEY: Dict[str, str] = {
    "tier_0": "gemma",
    "tier_1": "groq",
    "tier_2": "azure",
}


# ===========================================================================
# Module constants — BOTH are build-time tuning placeholders (Rule 4 / "No
# invented numbers"). Neither is an architectural decision.
# ===========================================================================

# TODO(build-time): tier-2 routing lexicon. The MECHANISM (word-boundary
# keyword match, no neural classifier) is the locked decision; this exact
# membership is a tuning constant, to be refined by watching real traffic.
# Same category of flagged placeholder as appraisal_chain.py's
# _ABSOLUTIST_WORDS and soul_filter.py's _DEFLECTION_MARKERS.
TIER_2_KEYWORDS: Tuple[str, ...] = (
    # --- base entries ---
    "debug", "traceback", "error", "explain why", "compare",
    "optimize", "refactor", "algorithm", "mathematics",
    "philosophy", "ethics", "analyze",
    "proof", "theorem", "complex", "deep dive",
    # --- inflected / derived forms (tuning, added because strict \b
    # excludes them; see the CONSEQUENCE note on _TIER_2_RE below) ---
    "debugging", "debugged",
    "tracebacks",
    "errors",
    "compares", "comparing", "compared", "comparison", "comparisons",
    "optimizes", "optimizing", "optimized", "optimization",
    "refactors", "refactoring", "refactored",
    "algorithms", "algorithmic",
    "mathematical",
    "philosophical",
    "ethical",
    "analyzes", "analyzing", "analyzed", "analysis",
    "analyse", "analyses", "analysing", "analysed",
    "proofs",
    "theorems",
    "complexity",
    "deep dives",
    # --- REMOVED (tuning, not a mechanism change): "medical" / "medically" /
    # "legal" / "legally". Too broad for a personal companion — they fire on
    # casual conversation ("my doctor said...", "my legal paperwork...").
    # The remaining keywords cover actual reasoning needs. See FLAG 3 in
    # HANDOFF_NOTES.md. No replacement needed.
)

# One precompiled, case-insensitive, word-boundary-anchored alternation over
# the lexicon above. re.escape protects the multi-word phrases' internal
# spaces (which are fine inside the \b...\b anchoring — the boundary applies
# to the whole phrase's start/end, not to the space within it).
#
# CONSEQUENCE OF STRICT \b (verified empirically, not assumed): with this
# exact regex, "complexity" does NOT match "complex" (the word boundary after
# "complex" fails when followed by "ity"), and "errors" does NOT match
# "error" either (the trailing "s" likewise breaks the boundary) — plain \b
# is symmetric on both sides of every alternative, so plural/suffixed forms
# of single-word entries are excluded exactly like longer compounds are.
# Whether stemming/prefix-matching is desired is a flagged build-time
# question, not something invented here.
#
# UPDATE (tuning, not a mechanism change): because strict \b excludes
# inflected forms, the common ones are now EXPLICIT entries in
# TIER_2_KEYWORDS above ("debugging", "errors", "complexity", ...) rather
# than being matched by a suffix pattern. The regex mechanism is unchanged;
# only the lexicon membership grew. Any inflection not listed above still
# does not match — that remains a build-time tuning question, not a bug.
_TIER_2_RE = re.compile(
    r"\b(?:" + "|".join(re.escape(k) for k in TIER_2_KEYWORDS) + r")\b",
    re.IGNORECASE,
)

# TODO(build-time): health-cache TTL. No source document states a value;
# 30s is a placeholder chosen only to make the per-turn call cheap. Not an
# architectural decision (same treatment as pad_engine.py's
# PAD_HISTORY_LENGTH).
HEALTH_CACHE_TTL_SECONDS: float = 30.0


def _now() -> datetime:
    """Aware-UTC clock, matching graph_manager / needs_system / dmn / daemon /
    visual_layer convention so timestamps compare consistently across
    modules."""
    return datetime.now(timezone.utc)


# ===========================================================================
# HealthProbe — an OPTIONAL narrow probe, checked structurally (Rule 6: no
# concrete provider imported; this is a Protocol, not a new dependency).
# ===========================================================================

@runtime_checkable
class HealthProbe(Protocol):
    """OPTIONAL narrow probe a transport MAY expose so the router can report
    reachability without spending a `generate()` call. NOT part of
    `ModelTransport` (which exposes exactly one method, `generate`) — checked
    structurally via `isinstance` at runtime, never assumed.

    `ModelTransport.generate(prompt)` is the transport's only guaranteed
    method; calling it purely to probe health would spend a real API token or
    a real local-inference pass on every turn, directly contradicting the
    requirement that health checks be cheap. `HealthProbe` is how a transport
    MAY volunteer a cheap answer instead."""

    def is_healthy(self) -> bool:
        ...


class BackendRouter:
    """Selects which of three injected LLM backend transports should serve a
    turn. See the module docstring for the tier vocabulary, the structural
    Soul-state boundary, and FLAG A / FLAG B.

    Holds exactly: the three injected transports, a session-scoped override,
    an injected clock, and the health-probe cache. No other state."""

    def __init__(
        self,
        *,
        gemma_transport: LocalModelTransport,
        groq_transport: ModelTransport,
        azure_transport: ModelTransport,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        # Injected REAL transports — never constructed here (Rule 6).
        self._gemma = gemma_transport
        self._groq = groq_transport
        self._azure = azure_transport
        self._clock = clock

        # Session-scoped override (Optional[str], one of VALID_TIERS or
        # None). Lives ONLY in this instance for the life of the process —
        # NEVER persisted to aria_state.json or anywhere else.
        self._override: Optional[str] = None

        # Health-probe cache: the last computed {"gemma","groq","azure"}
        # dict plus the clock time it was computed at. None until the first
        # check_health() call.
        self._health_cache: Optional[Dict[str, bool]] = None
        self._health_cached_at: Optional[datetime] = None

    # -- classification (pure; no model load, no network, no mutation) -----

    def classify(self, user_text: str) -> Literal["propose_tier_2", "tier_1_ok"]:
        """Pure function of `user_text` plus the flagged `TIER_2_KEYWORDS`
        lexicon. Returns "propose_tier_2" if the tier-2 regex matches
        anywhere in the text, else "tier_1_ok". Empty / None / whitespace-only
        text always returns "tier_1_ok". No model load, no network call, no
        state mutation."""
        if not user_text or not user_text.strip():
            return "tier_1_ok"
        if _TIER_2_RE.search(user_text):
            return "propose_tier_2"
        return "tier_1_ok"

    # -- session-scoped override --------------------------------------------

    def set_override(self, tier: Optional[str]) -> None:
        """Accepts `None` (clears the override) or one of `VALID_TIERS`.
        Anything else raises `ValueError` naming the offending value and
        listing the valid ones. Session-scoped: lives only in this instance,
        is NEVER persisted, and dies with the process."""
        if tier is not None and tier not in VALID_TIERS:
            raise ValueError(
                f"Invalid backend tier override: {tier!r}. "
                f"Valid tiers are {VALID_TIERS!r} (or None to clear)."
            )
        self._override = tier

    def get_override(self) -> Optional[str]:
        """The current session-scoped override, or None if unset."""
        return self._override

    def clear_override(self) -> None:
        """Reset the override to None (classifier-driven selection resumes)."""
        self._override = None

    # -- health probing (Part 5 resolution; FLAG B) -------------------------

    def check_health(self) -> dict[str, bool]:
        """Returns `{"gemma": bool, "groq": bool, "azure": bool}` — the HEALTHY
        SET. A key is True only when its transport EXPLICITLY reported healthy;
        an UNKNOWN probe (see `_probe_one`) is NOT in the healthy set.

        CACHED: if a previous result exists and
        `(clock() - cached_at) < HEALTH_CACHE_TTL_SECONDS`, the cached dict is
        returned (a COPY, so a caller mutating the returned dict cannot
        corrupt the cache). Otherwise every backend is re-probed, the fresh
        result is stored, and a copy of it is returned.

        Per-backend probe resolution order:
          1. transport is None                    -> False
          2. isinstance(transport, HealthProbe)    -> bool(transport.is_healthy())
          3. the local tier (gemma) with no probe  -> bool(transport.is_loaded)
          4. anything else with no probe           -> UNKNOWN, folded to False
             (FLAG B FIXED: no probe means no answer, and "no answer" is not
             "yes" — see module docstring). Routing therefore never assumes an
             unprobeable cloud transport is reachable. A transport that IS up
             but cannot say so is unavailable for ROUTING only; it still works
             if handed to `generate()` directly, and a genuinely down one
             surfaces as an `LLMTransportError` there. No timeout, retry
             count, or backoff is invented for this probe."""
        now = self._clock()
        if (
            self._health_cache is not None
            and self._health_cached_at is not None
            and (now - self._health_cached_at).total_seconds() < HEALTH_CACHE_TTL_SECONDS
        ):
            return dict(self._health_cache)

        probes = {
            "gemma": self._probe_one(self._gemma, is_local=True),
            "groq": self._probe_one(self._groq, is_local=False),
            "azure": self._probe_one(self._azure, is_local=False),
        }
        # UNKNOWN (None) is not healthy. Only an explicit True joins the
        # healthy set — a transport that could not answer is left out of it.
        fresh = {key: (probe is True) for key, probe in probes.items()}
        self._health_cache = fresh
        self._health_cached_at = now
        return dict(fresh)

    @staticmethod
    def _probe_one(transport, *, is_local: bool) -> Optional[bool]:
        """One backend's probe, per the resolution order in `check_health`.
        True = explicitly healthy, False = explicitly unhealthy, None =
        UNKNOWN (the transport cannot answer). UNKNOWN is deliberately NOT
        collapsed to True here — that was FLAG B."""
        if transport is None:
            return False
        if isinstance(transport, HealthProbe):
            return bool(transport.is_healthy())
        if is_local:
            # The local tier (gemma) with no HealthProbe: fall back to its
            # own load-state property (LocalModelTransport.is_loaded is a
            # PROPERTY, never called with parens). Residency IS a real answer,
            # so the local tier is never UNKNOWN.
            return bool(transport.is_loaded)
        # FLAG B FIXED: a non-local transport with no probe cannot report, so
        # the honest answer is UNKNOWN — never an optimistic True.
        return None

    # -- local model lifecycle (startup) -------------------------------------

    def ensure_local_loaded(self) -> bool:
        """Load the local (tier_0) transport if it is not already resident.
        Returns True if the model is resident afterwards. Infrastructure
        only — no PAD, no graph, no appraisal. Called once by the Daemon at
        startup (architect decision: Gemma loads at startup and stays
        resident); the router itself never unloads it."""
        if self._gemma.is_loaded:
            return True
        self._gemma.load()
        return bool(self._gemma.is_loaded)

    # -- selection -----------------------------------------------------------

    def select(self, user_text: str) -> tuple[Optional[ModelTransport], bool]:
        """Returns `(transport_or_None, propose_flag)`.

        Reads the override from internal state and health from
        `check_health()` itself — `select` takes only `user_text` (the
        original design note's wider `(user_text, session_override,
        backend_health)` signature is superseded by the module's own
        declared contract; the declared signature wins)."""
        override = self.get_override()
        if override is not None:
            # Override WINS UNCONDITIONALLY — deliberately not health-gated.
            # A user who says "use cloud" gets the cloud transport even if
            # the probe says it is down; the resulting failure surfaces at
            # generate() time and is the Daemon's to handle. Do NOT add a
            # health check here — test_override_takes_precedence depends on
            # exactly this.
            return self._transport_for_tier(override), False

        # health is the HEALTHY SET: True means EXPLICITLY healthy. An UNKNOWN
        # probe is already folded out by check_health(), so every gate below
        # reads "explicitly healthy", never "not known to be down" (FLAG B).
        health = self.check_health()

        if self.classify(user_text) == "propose_tier_2" and health["azure"]:
            return None, True  # Daemon owns the pause-and-ask UX

        # CONSEQUENCE (documented, not a bug): when the classifier matches
        # but azure is not explicitly healthy (down OR unprobeable), the
        # propose branch above is skipped and the turn falls through to the
        # normal gemma -> groq chain below. That is intended — a tier-2-shaped
        # request with no reasoning tier available still gets an answer from
        # whatever IS up, rather than blocking.
        #
        # FALLBACK ORDER (architect decision): Gemma is the DEFAULT VOICE for
        # all conversation (emotional / personal talk) — it is tried FIRST,
        # not as a last resort. Groq is reserved for FUTURE tools/search and
        # now serves only as the fallback when the local model is unavailable
        # (unhealthy) or not resident (not yet loaded) — never the default.
        if health["gemma"] and self._gemma.is_loaded:  # PROPERTY, no parens
            return self._gemma, False

        if health["groq"]:  # explicitly healthy only — UNKNOWN does not qualify
            return self._groq, False

        # Degradation path. REACHABLE since FLAG B was fixed: gemma unavailable
        # plus non-local transports that are down OR unprobeable lands here.
        return None, False  # everything down; Daemon raises/degrades

    # -- private helpers ------------------------------------------------------

    def _transport_for_tier(self, tier: str) -> ModelTransport:
        """Maps "tier_0"/"tier_1"/"tier_2" to the injected transport."""
        if tier == "tier_0":
            return self._gemma
        if tier == "tier_1":
            return self._groq
        if tier == "tier_2":
            return self._azure
        raise ValueError(  # pragma: no cover - set_override already guards this
            f"Invalid backend tier: {tier!r}. Valid tiers are {VALID_TIERS!r}."
        )
