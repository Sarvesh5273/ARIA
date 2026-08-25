"""Module 8 — Daemon / Soul Tick (`daemon/aria_daemon.py`): the ORCHESTRATOR.

Locked spec: see .kiro/specs/daemon/{requirements,design,tasks}.md.

Responsibility (`ARIA_Module_Build_Plan.md`, Module 8): orchestrate the system —
drive the soul-tick (PAD decay, need depletion, attentional policy) and the
DMN-tick on TWO SEPARATE CLOCKS, route an inbound turn through the full
pipeline, select/play pre-cached thinking sounds from PAD+text, evaluate
initiative, and detect idle. Dependencies = ALL core modules.

===========================================================================
HARD PHILOSOPHY CONSTRAINTS (a violation is WRONG even if tests pass)
===========================================================================

1. THE DAEMON ORCHESTRATES; IT COMPUTES NO MEANING OR FEELING
   (steering/project-rules.md "the Daemon ORCHESTRATES … it does NOT compute
   meaning or feelings itself"). It routes signals, drives the two clocks, and
   CALLS the modules. It NEVER calls a PAD mutator: PAD moves ONLY inside
   PAD_Engine (EMA decay on `on_soul_tick`) and inside the Appraisal Chain
   (the Stage-4 delta via `apply_appraisal_delta`). Grep-clean:
   `apply_appraisal_delta` never appears in this module. Reading PAD
   (`get_current_pad`) for a presentation choice — a thinking sound — is
   explicitly allowed and is NOT a PAD write (v4 Layer 5). Need STATES come
   from Needs_System; the Daemon never derives them.

2. SOUL-TICK AND DMN-TICK ARE TWO SEPARATE CLOCKS, driven INDEPENDENTLY
   (v4 "Two-Process Separation" / "Continuous Self-Awareness"). The soul tick
   is the pulse (maintenance: PAD decay + Energy + attentional policy); the DMN
   tick is the dream (idle consolidation). The Daemon NEVER merges them — a
   soul tick never triggers a DMN pass and a DMN pass never drives PAD decay.
   They are separate public methods (`soul_tick` / `dmn_tick`) on independent
   intervals.

3. F4 AND BARGE-IN PRODUCE ZERO INTERNAL EFFECT (Addendum §5). They stop audio
   ONLY. There is NO path from `on_f4_interrupt` / `on_barge_in` to a PAD write,
   a graph write, a need change, a persisted-state write, or any appraisal —
   each method's ENTIRE body is a single call into the Audio Pipeline. F4 is a
   stop button, not an interpersonal event; whatever the user says AFTER it
   enters appraisal normally, as any input does.

4. THE HANDOFF STARTUP CONTRACT IS IMPLEMENTED EXACTLY (HANDOFF_NOTES):
   (a) `PADEngine.initialize()` is called EXACTLY ONCE at startup, with the
       restored PAD snapshot and the restored valence (loaded via
       `StateManager.load_last_applied_valence()` and converted by the wiring
       helper that also converts PADState→PADSnapshot); on the periodic save
       cadence and on shutdown, PAD_Engine's current `_last_applied_valence` is
       persisted via `StateManager.save_last_applied_valence()`.
   (b) after `StateManager.load_self_model()`, `consistency_flags` are
       explicitly CLEARED ("reset each session" — else they persist).
   (c) `initialize()` is NOT idempotent — `startup()` GUARDS against a second
       call (a second call would discard `_last_applied_valence` and
       reintroduce PAD Engine Open Question 4).

5. INITIATIVE: highest-pressure need + most-recently-salient node, expressed
   ONCE when critical, NEVER nagging, entering at soul_filter DIRECTLY —
   skipping wake/STT/VAD/Whisper (Addendum §7; v4 Layer 2 "She never nags").
   Keyed on the categorical `due` state (Needs_System never emits `neglected` —
   its OQ-1 — so `due` is the critical categorical state it DOES emit; FLAGGED
   for revisit if `neglected` is later split out). NO numeric need threshold
   (Addendum §3 supersedes v4's "Connection < 20": the four needs are
   categorical, not numeric).

===========================================================================
FLAG DISPOSITION (cite; do not invent — Rule 1)
===========================================================================
  F-8a Tick cadences   : only idle=8min and reflection=6h are PINNED (v4). The
        soul-tick and DMN-tick intervals are build-time tuning placeholders
        (Resolution Log "Open — build-time tuning constants only: Soul-tick &
        DMN-tick intervals"). Marked TODO(F-8a); injectable.
  F-8b Attentional policy: RESOLVED by Resolution Log item 10 — implementable AS
        LITERALLY STATED (highest-pressure need + most-recently-salient node);
        no further formalization. Since the four needs are CATEGORICAL, the
        tie-break among simultaneously-`due` needs is the canonical spec order
        (a deterministic, NON-numeric selection — a numeric "pressure" ranking
        would be an invented number, forbidden). FLAGGED as the tie-break policy.

  Present World Model + language-switch state = Daemon VOLATILE working state,
  NOT persisted (Resolution Log item 10; consistent with Rule 7 — no second
  PERSISTENT store).

  Audio Pipeline (Module 7) and Visual Layer (Module 10) are built and tested
  — the Daemon still depends on a documented CONTRACT and injects whatever
  satisfies it (Rule 6). Note the asymmetry: the Daemon defines
  `AudioPipelinePort` for Module 7, but defines NO visual port — Module 10
  exposes its own `VisualLayerPort` and is wired top-of-tree.

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Dict, List, Optional, Protocol, Sequence, Tuple, runtime_checkable

# --- REAL interfaces (imported, never redefined; Rule 6) -------------------
from daemon.pad_engine import (
    PADEngine, PADSnapshot, PADDelta, Valence, PAD_BASELINE,
)
from daemon.state_manager import (
    StateManager,
    PADState,
    SelfModel,
    CONSISTENCY_FLAG_NAMES,
    SAVE_CADENCE_SECONDS,
)
from daemon.needs_system import NeedsSystem, ENERGY_CRITICAL
# ENERGY_LOW (30.0) from its canonical home — the same in-spec operational gate
# soul_filter reads for "do not overextend" (v4 "Energy low (below 30)").
from daemon.types import ENERGY_LOW
from daemon.graph_manager import MemoryGraph, PoignancyCategory, RelationalStage
from daemon.appraisal_chain import (
    AppraisalChain,
    AppraisalResult,
    SocialSignals,
    GoalRelevance,
    Attribution,
)
from daemon.soul_filter import SoulFilter, NeedState, NeedStates, SoulFilterResponse
from daemon.dmn import DMN, DMNPassInput, BufferItem, ConnectionCandidate
from daemon.session_buffer import SessionBuffer
from daemon.backend_router import BackendRouter


# ===========================================================================
# Constants — PINNED cadences vs. FLAGGED build-time placeholders (F-8a).
# ===========================================================================

# PINNED by v4 (the only two cadence values the docs lock).
IDLE_NO_VOICE_WINDOW = timedelta(minutes=8)   # v4 Idle Detection ("8 minutes")
REFLECTION_INTERVAL = timedelta(hours=6)      # v4 reflection cadence ("6 h")

# F-8a build-time tuning placeholders (Resolution Log "Open — build-time tuning
# constants only: Soul-tick & DMN-tick intervals"). NOT architectural — same
# category as PAD_Engine's PAD_HISTORY_LENGTH and Needs_System's k_load/k_rest.
DEFAULT_SOUL_TICK_INTERVAL = timedelta(seconds=3)    # TODO(F-8a) "every few seconds"
DEFAULT_DMN_TICK_INTERVAL = timedelta(seconds=30)    # TODO(F-8a) "slower during interaction"

# Canonical need order (the order the four needs appear in v4 Layer 2 /
# NeedStates). Used ONLY as the deterministic, non-numeric tie-break among
# simultaneously-`due` needs (F-8b) — never as a pressure magnitude.
_NEED_ORDER = ("connection", "growth", "purpose", "continuity")


# ===========================================================================
# Backend-proposal state machine (Track A: BackendRouter wired into the
# conversation loop). See route_inbound_turn / _begin_proposal /
# _handle_proposal_response / _expire_proposal below.
# ===========================================================================

class DaemonState(Enum):
    """Turn-routing state. NORMAL is the ordinary pipeline; PROPOSING_CLOUD
    means the previous turn asked the user whether to escalate to the
    reasoning tier and the next inbound turn is that answer."""
    NORMAL = "normal"
    PROPOSING_CLOUD = "proposing_cloud"


# TODO(build-time): how long to wait for a spoken yes/no before answering
# anyway. No source document states a value; 10s is a placeholder chosen for
# a natural conversational pause. Not an architectural decision — same
# treatment as DEFAULT_SOUL_TICK_INTERVAL. Injectable for tests.
PROPOSAL_TIMEOUT_SECONDS = 10.0

# TODO(build-time): affirmative / negative response lexicons and the backend
# meta-command vocabulary. Word-boundary matched, case-insensitive. Same
# category of flagged placeholder as appraisal_chain.py's lexicons.
_AFFIRMATIVE: Tuple[str, ...] = (
    "yes", "yeah", "yep", "sure", "go ahead", "do it",
    "please do", "okay", "ok",
)
_NEGATIVE: Tuple[str, ...] = (
    "no", "nope", "nah", "don't", "do not", "stay local",
    "never mind", "nevermind",
)
_BACKEND_META_COMMANDS: Dict[Optional[str], Tuple[str, ...]] = {
    "tier_2": ("use cloud", "switch to cloud", "use kimi"),
    "tier_0": ("stay local", "use gemma", "go local"),
    "tier_1": ("use groq", "use general"),
    None:     ("go back to normal", "reset backend", "default mode"),
}

# Pre-authored, hardcoded strings — the same pattern as _INITIATIVE_NOTES and
# soul_filter.PERSONA_ANCHOR. Human, unhurried, and containing NO DIGITS (no
# number may cross to the user as a mechanical value; say "a moment", never
# "10 seconds") and NO backend/tier/vendor names (the user should not have to
# know what "tier_2" or "Azure" is).
_PROPOSAL_PROMPT = (
    "That one deserves more thought than I'd give it off the cuff. Want me "
    "to take my time with it?"
)
_PROPOSAL_TIMEOUT_REPLY = "I'll just take a swing at it."

# Brief, pre-authored acknowledgements for the backend meta-commands (STEP 3
# below), keyed the same way as _BACKEND_META_COMMANDS. Same no-digits /
# no-vendor-name rules as _PROPOSAL_PROMPT above — the user should never hear
# a tier name, a backend name, or a mechanical value.
_BACKEND_META_ACK: Dict[Optional[str], str] = {
    "tier_2": "Got it. I'll give this the deeper thought it deserves.",
    "tier_0": "Okay, staying close and simple for now.",
    "tier_1": "Alright, I'll widen my thinking for this.",
    None: "Back to normal, thanks for letting me know.",
}


def _phrase_in_text(text: str, phrase: str) -> bool:
    """Word-boundary, case-insensitive phrase match. Modeled on
    session_buffer.py's equivalent private helper (not imported — a private
    symbol from another module is not a public dependency; this is a small,
    independent module-level helper, matching this module's own style)."""
    escaped = re.escape(phrase)
    pattern = r"(?:^|\W)" + escaped + r"(?:$|\W)"
    return re.search(pattern, text, re.IGNORECASE) is not None


def _matches_any(text: str, phrases: Tuple[str, ...]) -> bool:
    low = (text or "").lower().strip()
    return any(_phrase_in_text(low, p) for p in phrases)


# Sentinel distinguishing "no backend meta-command matched" from "matched,
# and the tier to set is None" (the "go back to normal" entry legitimately
# maps to tier=None, which would collide with a plain Optional[str] return).
_NO_BACKEND_META_COMMAND = object()


def _match_backend_meta_command(text: str):
    """Returns the tier to set (one of VALID_TIERS, or None for "go back to
    normal") if `text` matches a backend meta-command, else the
    `_NO_BACKEND_META_COMMAND` sentinel."""
    for tier, phrases in _BACKEND_META_COMMANDS.items():
        if _matches_any(text, phrases):
            return tier
    return _NO_BACKEND_META_COMMAND


def _now() -> datetime:
    """Aware-UTC clock, matching graph_manager / needs_system / dmn convention
    so timestamps compare consistently across modules."""
    return datetime.now(timezone.utc)


# ===========================================================================
# Wiring helpers (module-level, pure) — the conversions the HANDOFF assigns to
# the Daemon's wiring layer. Neither PAD_Engine nor StateManager performs these
# (by design — see pad_engine.initialize / state_manager docstrings); they live
# HERE, at the single call site that wires the two together.
# ===========================================================================

def pad_state_to_snapshot(pad_state: PADState) -> PADSnapshot:
    """Module 11 `PADState` → Module 1 `PADSnapshot`. THE wiring helper
    HANDOFF_NOTES names ("the same wiring helper that converts PADState to
    PADSnapshot"). PAD_Engine.initialize() accepts only PADSnapshot; this
    bridges the persistence type to it at startup."""
    return PADSnapshot(
        pleasure=pad_state.pleasure,
        arousal=pad_state.arousal,
        dominance=pad_state.dominance,
    )


def snapshot_to_pad_state(snap: PADSnapshot) -> PADState:
    """Module 1 `PADSnapshot` → Module 11 `PADState`, for the save path."""
    return PADState(pleasure=snap.pleasure, arousal=snap.arousal, dominance=snap.dominance)


def valence_from_str(value: Optional[str]) -> Optional[Valence]:
    """Persisted opaque valence string → Module 1 `Valence` (the same wiring
    helper family as PADState→PADSnapshot, HANDOFF_NOTES). StateManager stores
    the string opaquely ("owns no meaning"); interpreting it is the Daemon's
    wiring job. None or an unrecognised string → None — exactly the residual
    restore-boundary input PAD Engine's (narrowed) Open Question 4 covers, in
    which case `restored_valence=None` is passed and PAD Engine's own handling
    stands unchanged (the Daemon does NOT invent a resolution)."""
    if value is None:
        return None
    try:
        return Valence(value)
    except ValueError:
        return None


def valence_to_str(valence: Optional[Valence]) -> Optional[str]:
    """Module 1 `Valence` → the opaque string StateManager persists."""
    return valence.value if valence is not None else None


def read_pad_last_valence(pad_engine: PADEngine) -> Optional[Valence]:
    """Read PAD_Engine's current `_last_applied_valence` for persistence.

    HANDOFF_NOTES assigns the Daemon the obligation to "save PADEngine's current
    _last_applied_valence … via get access added for this purpose, or by
    exposing it through an existing accessor — Module 1's implementation decides
    this." Module 1's implementation locked its public API to exactly five
    methods (enforced by its own `test_pad_engine_public_method_list_is_exactly
    _the_documented_set`), i.e. it decided NOT to add a public accessor. So the
    Daemon fulfils the obligation here in its wiring layer by reading the
    HANDOFF-NAMED field directly, WITHOUT expanding Module 1's locked surface
    (keeping the change additive and Module 1's test green). The field is set in
    PAD_Engine.__init__, so it is always present after construction."""
    return getattr(pad_engine, "_last_applied_valence", None)


def need_states_to_mapping(need_states: NeedStates) -> Dict[str, str]:
    """`NeedStates` (Module 2 output) → the {need: state_string} mapping the
    Appraisal Chain's Stage-1 retrieval preference consumes (Addendum §3 Stage
    5). Pure shape adapter — the CATEGORICAL need states are produced by Needs
    System; the Daemon computes none of them, and Energy (the only number) is
    intentionally NOT forwarded here (Stage 5 is a categorical preference)."""
    return {
        "connection": need_states.connection.value,
        "growth": need_states.growth.value,
        "purpose": need_states.purpose.value,
        "continuity": need_states.continuity.value,
    }


# ===========================================================================
# Layer 5 — Thinking sounds (pre-cached; categorical trigger; NOT a PAD write).
# ===========================================================================

class ThinkingSound(Enum):
    """The pre-cached thinking-sound CATEGORIES (v4 Layer 5 "Thinking Sounds as
    Emotional Leakage" table). The Daemon picks ONE by categorical trigger and
    hands the key to the Audio Pipeline to play a PRE-CACHED clip; Gemma never
    decides them and never knows they happened (v4). The concrete audio-clip
    inventory behind each category is the Audio Pipeline's build-time asset
    concern, not the Daemon's."""
    CONTEMPLATION = "contemplation"   # neutral question or problem ("Hmm…")
    SURPRISE = "surprise"             # "surprise"/"unexpected"/"suddenly" ("Oh!")
    CONCERN = "concern"               # "worry"/"problem"/"fail"/"error" ("Well…")
    WARMTH = "warmth"                 # Pleasure > 0.7 (soft "Mm.")
    PLAYFULNESS = "playfulness"       # Dominance > 0.6 + Pleasure > 0.5 ("Heh.")


# v4 Layer 5 trigger lexicons (verbatim from the table). These are the SPEC'S
# OWN example words — not an invented taxonomy.
_SURPRISE_WORDS = ("surprise", "unexpected", "suddenly")
_CONCERN_WORDS = ("worry", "problem", "fail", "error")
# v4 Layer 5 PAD thresholds (0.7 / 0.6 / 0.5) — IN-SPEC presentation thresholds
# (v4's own table), the same category as the emergency coping thresholds; NOT
# invented. Reading PAD against them selects a sound; it never writes PAD.
_WARMTH_PLEASURE = 0.7
_PLAYFUL_DOMINANCE = 0.6
_PLAYFUL_PLEASURE = 0.5


def select_thinking_sound(user_text: str, pad: PADSnapshot) -> Optional[ThinkingSound]:
    """Pick a pre-cached thinking sound from the user's text + current PAD
    (v4 Layer 5). Purely CATEGORICAL — content triggers first (more specific),
    then PAD-mood triggers (Playfulness before Warmth, as its two-condition
    trigger is the more specific), then Contemplation as the default for a
    question/problem. Returns None for contentless input (nothing to react to).

    The PRECEDENCE among simultaneously-true triggers is a presentation detail
    v4's table does not order; the order below is documented and FLAGGED as a
    build-time presentation choice — it never affects PAD, meaning, or memory.
    Reading `pad` here is a presentation read, explicitly sanctioned (v4 "The
    daemon reads the user's text and current PAD state and picks a pre-cached
    sound"); it is NOT a PAD write."""
    text = (user_text or "").strip()
    if not text:
        return None
    low = text.lower()
    # --- content triggers (v4 exact words) ---
    if any(w in low for w in _CONCERN_WORDS):
        return ThinkingSound.CONCERN
    if any(w in low for w in _SURPRISE_WORDS):
        return ThinkingSound.SURPRISE
    # --- PAD-mood triggers (v4 exact thresholds) ---
    if pad.dominance > _PLAYFUL_DOMINANCE and pad.pleasure > _PLAYFUL_PLEASURE:
        return ThinkingSound.PLAYFULNESS
    if pad.pleasure > _WARMTH_PLEASURE:
        return ThinkingSound.WARMTH
    # --- default: contemplation (neutral question or problem) ---
    return ThinkingSound.CONTEMPLATION


# ===========================================================================
# Initiative — pre-authored behavioral instructions per need (v4 "single gentle
# reach-out"). Selected by WHICH need is `due` (categorical, from Needs System)
# — the Daemon does not author meaning here any more than Soul_Filter authors
# meaning in its fixed PERSONA_ANCHOR: these are pre-authored, hardcoded strings
# picked by category. Each is a HOW instruction after an em-dash so Soul_Filter
# keeps only the behavioral guidance (never a "what happened") in This Moment.
# ===========================================================================
_INITIATIVE_NOTES: Dict[str, str] = {
    "connection": (
        "connection has gone quiet between you — reach out once, gently and "
        "briefly, without performing urgency and without asking him to respond"
    ),
    "growth": (
        "it has been a while since anything new — reach out once, lightly, from "
        "genuine curiosity, without demanding engagement"
    ),
    "purpose": (
        "something that matters has gone untended — reach out once, plainly, "
        "without manufacturing importance or pressure"
    ),
    "continuity": (
        "the thread between you has gone slack — reach out once in a way that "
        "quietly affirms the bond persists, without clinging or performing need"
    ),
}

# An INERT PAD delta for the initiative appraisal's required `pad_delta` field.
# It is NEVER applied: Soul_Filter reads AppraisalResult fields for rendering
# and gating but never touches `pad_delta` (see soul_filter.respond →
# assemble_instruction / run_output_gate — neither references it). The Daemon
# therefore performs NO PAD write for initiative; this is a data placeholder for
# a frozen contract field, not a feeling computation.
_INERT_PAD_DELTA = PADDelta(
    d_pleasure=0.0, d_arousal=0.0, d_dominance=0.0,
    valence=Valence.NEUTRAL, origin="appraisal",
)
# All-clear social signals for the initiative appraisal (no distress, no
# vulnerability, no contradiction, no arc) → Soul_Filter's routine-turn
# constraints ("do not flatter to be liked", "do not manufacture urgency"),
# which is exactly the no-nag posture initiative requires.
_NEUTRAL_SOCIAL_SIGNALS = SocialSignals(
    distress_marker=False, vulnerability_disclosure=False,
    reality_contradiction=False, conflict_arc_open=False,
    conflict_arc_closed_this_turn=False,
)


def build_initiative_appraisal(note: str) -> AppraisalResult:
    """Build the minimal AppraisalResult that carries an initiative's behavioral
    instruction into Soul_Filter (Addendum §7 "Aria already holds the behavioral
    instruction"). The MEANING (which need is due) came from Needs_System
    (categorical); the Daemon only packages a pre-authored HOW note into the
    contract Soul_Filter consumes. Non-emergency (five-field path), low
    poignancy, all-clear signals, and an INERT PAD delta that is never applied —
    so nothing here computes or writes a feeling."""
    return AppraisalResult(
        q1=GoalRelevance.MEDIUM,          # relevant, but not HIGH → no emergency, no forced engagement
        q2=Valence.NEUTRAL,
        q3=Attribution.USER,
        q4_notes=None,
        q4_has_needs_implications=False,
        is_partial_appraisal=False,
        poignancy=PoignancyCategory.LOW,
        pad_delta=_INERT_PAD_DELTA,       # never applied (see constant)
        emergency=False,
        emergency_type=None,
        event_node_id=None,
        uncertainty_node_id=None,
        resolved_uncertainty_ids=(),
        social_signals=_NEUTRAL_SOCIAL_SIGNALS,
        most_salient_note=note,
    )


# ===========================================================================
# Injected CONTRACT for Module 7 (Audio Pipeline — NOT YET BUILT; inject fake).
# ===========================================================================
@runtime_checkable
class AudioPipelinePort(Protocol):
    """The slice of the Audio Pipeline (Module 7, Build Plan) the Daemon drives.
    Module 7 is not built; the Daemon depends on this documented contract and a
    fake satisfies it in tests (Rule 6). Inbound STT is NOT here: transcribed
    text arrives at `route_inbound_turn` (the Daemon is the callee)."""

    def speak(self, text: str) -> None:
        """Render outbound validated text to speech (TTS)."""
        ...

    def stop_playback(self) -> None:
        """Stop current audio playback and return to listening (F4 / barge-in).
        Audio-only; carries NO information content (Addendum §5)."""
        ...

    def play_thinking_sound(self, sound: str) -> None:
        """Play a PRE-CACHED thinking-sound clip for the given category (Layer 5)."""
        ...

    def play_reconsideration_sound(self) -> None:
        """Play the short reconsideration sound during a Soul_Filter retry (v4
        "Self-Correction Sound")."""
        ...


# ===========================================================================
# The Daemon.
# ===========================================================================
class AriaDaemon:
    """Module 8 orchestrator. Drives two separate clocks, routes turns, plays
    thinking sounds, evaluates initiative, detects idle — and honors the HANDOFF
    startup contract. It CALLS the modules; it computes no meaning or feeling.

    All dependencies are INJECTED (real modules; fakes for the unbuilt Audio
    Pipeline / Visual Layer). The Daemon is the top of the dependency tree —
    nothing imports it — so wiring everything here introduces no cycle."""

    def __init__(
        self,
        *,
        pad_engine: PADEngine,
        needs_system: NeedsSystem,
        graph: MemoryGraph,
        appraisal_chain: AppraisalChain,
        soul_filter: SoulFilter,
        dmn: DMN,
        state_manager: StateManager,
        audio: AudioPipelinePort,
        primary_entity_id: Optional[str] = None,
        self_entity_id: Optional[str] = None,
        clock: Callable[[], datetime] = _now,
        soul_tick_interval: timedelta = DEFAULT_SOUL_TICK_INTERVAL,
        dmn_tick_interval: timedelta = DEFAULT_DMN_TICK_INTERVAL,
        idle_no_voice_window: timedelta = IDLE_NO_VOICE_WINDOW,
        backend_router: Optional[BackendRouter] = None,
        proposal_timeout: timedelta = timedelta(seconds=PROPOSAL_TIMEOUT_SECONDS),
    ) -> None:
        # --- injected REAL modules / contracts (never instantiated here) ---
        self._pad = pad_engine
        self._needs = needs_system
        self._graph = graph
        self._appraisal = appraisal_chain
        self._soul_filter = soul_filter
        self._dmn = dmn
        self._state = state_manager
        self._audio = audio
        self._primary_entity_id = primary_entity_id
        self._self_entity_id = self_entity_id
        # BackendRouter is OPTIONAL (Track A wiring) — defaults to None so
        # every existing AriaDaemon construction keeps working unchanged
        # (backward compatible: no router → behaviour is exactly as before).
        self._backend_router = backend_router
        self._proposal_timeout = proposal_timeout

        # --- clocks (two separate, independent) ---
        self._clock = clock
        self._soul_tick_interval = soul_tick_interval   # F-8a placeholder
        self._dmn_tick_interval = dmn_tick_interval      # F-8a placeholder
        self._idle_no_voice_window = idle_no_voice_window  # PINNED 8min by default
        self._last_soul_tick_at: datetime = clock()
        self._last_dmn_tick_at: datetime = clock()
        self._soul_tick_count = 0
        self._dmn_tick_count = 0

        # --- startup guard (HANDOFF (c): initialize() runs exactly once) ---
        self._started = False

        # --- VOLATILE working state (Resolution Log item 10 — NOT persisted) --
        self._present_world_model: Dict[str, object] = {}   # "paying attention now"
        self._language = "en"                                # v4: default English
        self._last_voice_input_at: datetime = clock()
        self._output_pending = False
        self._most_recently_salient_node: Optional[str] = None
        self._highest_pressure_need: Optional[str] = None
        self._attentional_focus: tuple = (None, None)
        # no-nag latch per need (v4 "expresses a need exactly once … does not
        # repeat"): True once expressed, reset to False when the need is
        # satisfied again.
        self._initiative_expressed: Dict[str, bool] = {n: False for n in _NEED_ORDER}
        self._last_turn_was_emergency: bool = False
        self._initiative_count = 0
        # Observability only: True when startup()'s PAD OQ4 consistency check
        # discarded a half-written PAD record. Set by startup(), never read by
        # any soul module, crosses no model boundary, decides nothing. It exists
        # because the reset is otherwise INVISIBLE — "she is calm today" and "the
        # fallback ate her state" look identical without it. Same reasoning
        # Resolution Log item 25 gives for recording what the model PRODUCED
        # before the strip: reading the condition afterwards would pin it False
        # and destroy the evidence.
        self._pad_restore_was_reset: bool = False
        # DMN-pass working inputs the Daemon tracks and relays.
        self._self_monitoring_buffer: List[BufferItem] = []
        self._active_uncertainty_refs: List[str] = []
        self._session_entity_refs: List[str] = []
        self._rupture_entity_refs: List[str] = []
        self._session_id = "aria"
        self._last_turn_buffer_item: Optional[BufferItem] = None
        self._session_buffer = SessionBuffer()

        # --- Backend-proposal state machine (Track A) — VOLATILE, NOT
        # persisted (same category as the Present World Model / language
        # setting, per Resolution Log item 10).
        #
        # JUDGMENT CALL / naming deviation: the task text names this field
        # `self._state`, but `self._state` is ALREADY bound above to the
        # injected StateManager (`self._state = state_manager`) and is used
        # throughout startup()/shutdown()/_save_state() as such. Reusing the
        # name here would silently clobber the StateManager reference. Named
        # `self._daemon_state` instead; the public read-only property is
        # still named `state` (Part 4h), so the observable contract matches
        # the spec even though the private attribute name differs. ---
        self._daemon_state: DaemonState = DaemonState.NORMAL
        self._pending_query: Optional[str] = None
        self._pending_kwargs: Optional[dict] = None       # the replay's routing args
        self._proposal_deadline: Optional[datetime] = None

    # =======================================================================
    # Startup / shutdown — the HANDOFF contract.
    # =======================================================================
    def startup(self) -> None:
        """Execute the HANDOFF startup contract EXACTLY ONCE (constraint 4)."""
        if self._started:
            # (c) initialize() is NOT idempotent — a second call resets
            # _last_applied_valence (discarding deltas applied since the first)
            # and reintroduces PAD Engine Open Question 4. GUARD it hard.
            raise RuntimeError(
                "AriaDaemon.startup() called more than once. "
                "PADEngine.initialize() must run exactly once per process "
                "(HANDOFF_NOTES: 'call initialize() exactly once per process "
                "lifetime'). Start a new process instead of re-initializing."
            )

        # Restore persisted working state (Module 11).
        pad_state, energy, self_model, valence_str = self._state.load_all()

        # (a) PAD Engine: initialize ONCE with restored PAD + restored valence.
        # BOTH conversions happen HERE, at the wiring call site.
        restored_snapshot = pad_state_to_snapshot(pad_state)
        restored_valence = valence_from_str(valence_str)

        # PAD OQ4 RESTORE-BOUNDARY CONSISTENCY CHECK.
        #
        # PAD and last_applied_valence are ONE RECORD: PAD can only leave
        # baseline through apply_appraisal_delta, which always sets a valence, so
        # a non-baseline PAD with no valence is a HALF-WRITTEN record, not a
        # state she was ever in. Carried into `initialize()` it makes the FIRST
        # `on_soul_tick()` raise NotImplementedError, several REPL frames from
        # the cause, because there is no basis for choosing an EMA decay
        # coefficient and inventing one is what Rule 1 forbids.
        #
        # Resolution Log item 18 already ruled this class of case at this exact
        # boundary: an entry that cannot be trusted falls back to the spec
        # default rather than being repaired ("NaN has no position on a scale").
        # Half a record is the same kind of thing, so it gets the same answer.
        #
        # This chooses NO coefficient, catches NO raise, and leaves
        # `pad_engine.py` byte-unchanged. The raise stays live for any case this
        # does not cover. Change 1 below (one atomic write instead of three)
        # is what makes this rare enough to be a backstop rather than a habit.
        #
        # WHAT IT COSTS, stated because it is a real cost: the emotional residue
        # of the turn before the crash is discarded — she resumes even rather
        # than still warm. The graph is untouched (every MemoryGraph write
        # commits inside its own method), so she remembers the conversation
        # without still feeling it, which is the human shape rather than a
        # machine reset. The alternative — presenting a feeling whose origin is
        # unknown — would be performing a state instead of having one.
        self._pad_restore_was_reset = (
            restored_snapshot != PAD_BASELINE and restored_valence is None
        )
        if self._pad_restore_was_reset:
            restored_snapshot = PAD_BASELINE

        self._pad.initialize(restored_snapshot, restored_valence)

        # Needs System: initialize the Energy substrate from restored Energy.
        self._needs.initialize(energy)

        # (b) CLEAR consistency_flags after load_self_model (they reset each
        # session) and persist the cleared flags so the clear is durable.
        for name in CONSISTENCY_FLAG_NAMES:
            self_model.consistency_flags[name] = False
        self._state.save_self_model(self_model)

        # Arm the two clocks and the idle timer at boot (not immediately idle).
        boot = self._clock()
        self._last_soul_tick_at = boot
        self._last_dmn_tick_at = boot
        self._last_voice_input_at = boot

        # Gap 3: ensure the self-referential EntityNode exists (Resolution
        # Log §2 — narrative and Continuity need both require it). Load the
        # persisted id; create on first run; propagate to NeedsSystem and DMN.
        # NeedsSystem and DMN are constructed before startup() so their
        # _self_entity_id field is updated here — same pattern as the
        # read_pad_last_valence wiring helper (both access a field the public
        # API does not expose directly).
        self._self_entity_id = self._state.load_self_entity_id()
        if self._self_entity_id is None:
            self._self_entity_id = self._graph.write_entity_node(
                entity_type="concept", name="aria", now=boot,
            )
            self._state.save_self_entity_id(self._self_entity_id)
        self._needs.set_self_entity_id(self._self_entity_id)
        self._dmn.set_self_entity_id(self._self_entity_id)

        # Track A: load Gemma at startup and keep it resident. Architect
        # decision — the local voice is the DEFAULT for conversation, so it
        # must be warm for the very first turn rather than loading lazily on
        # first use (16GB Mac; the 7.7GB model fits resident). If a router is
        # wired and `load()` raises, let it propagate: a daemon that cannot
        # bring up its default voice should fail loudly at startup, not
        # silently degrade mid-conversation. No router wired → no-op (fully
        # backward compatible).
        if self._backend_router is not None:
            self._backend_router.ensure_local_loaded()

        self._started = True

    def shutdown(self) -> None:
        """On shutdown, flush PAD + Energy + last_applied_valence (HANDOFF (a):
        round-trip last_applied_valence on shutdown)."""
        self._require_started()
        self._save_state()

    def save_periodic(self) -> None:
        """The periodic save cadence (StateManager.SAVE_CADENCE_SECONDS is a
        build-time tuning flag the Daemon schedules). Same round-trip as
        shutdown — including last_applied_valence (HANDOFF (a))."""
        self._require_started()
        self._save_state()

    def _save_state(self) -> None:
        """Persist PAD, Energy and last_applied_valence in ONE atomic write. The
        Daemon owns no meaning: it reads the live values from their owning
        modules and hands them to StateManager (pure plumbing).

        ONE WRITE, NOT THREE (PAD OQ4). This used to call `save_pad`,
        `save_energy` and `save_last_applied_valence` separately — three
        independent atomic writes with two gaps between them. A crash in either
        gap persisted a non-baseline PAD while the valence key went unwritten,
        which is the half-written record `startup()`'s consistency check now has
        to clean up. `StateManager.save_all` closes the gap: its own docstring
        already says "The Daemon calls this on cadence and on shutdown", so this
        adopts the API Module 11 was written to be called through rather than
        adding one. No new mechanism, no new key, nothing invented.

        `self_model` is round-tripped through disk because `save_all` requires
        it and the Daemon holds no live copy — `startup()` clears
        consistency_flags and persists them immediately, so disk is the current
        value. Read-modify-write of the same bytes, deliberately not a second
        source of truth for a file this method does not own. FLAGGED: under a
        THREADED host a `save_self_model` landing between this read and the
        write would be clobbered. Not reachable in the synchronous REPL, where
        `run_scheduler_step()` never overlaps a turn."""
        snap = self._pad.get_current_pad()
        energy = self._needs.get_energy()
        # last_applied_valence ROUND-TRIP (HANDOFF (a)).
        current_valence = read_pad_last_valence(self._pad)
        self._state.save_all(
            pad=snapshot_to_pad_state(snap),
            energy=energy,
            self_model=self._state.load_self_model(),
            last_applied_valence=valence_to_str(current_valence),
        )

    def _require_started(self) -> None:
        if not self._started:
            raise RuntimeError(
                "AriaDaemon method called before startup(). startup() runs the "
                "HANDOFF contract (PADEngine.initialize() once, consistency_flags "
                "cleared, state restored) and must be called first."
            )

    # =======================================================================
    # CLOCK 1 — the soul tick (maintenance). SEPARATE from the DMN tick.
    # =======================================================================
    def soul_tick(self, now: Optional[datetime] = None) -> None:
        """One soul tick: PAD decay + Energy + attentional policy + initiative.
        Drives Modules 1 and 2 — the Daemon calls their `on_soul_tick`; the
        modules own the math. This method NEVER runs a DMN pass (separate clock,
        constraint 2) and NEVER writes PAD itself (constraint 1).

        Energy has THREE states here, not two (Resolution Log item 29): deplete
        under active load, HOLD through the pre-idle silence window, recover at
        genuine idle. PAD is unaffected by that ruling — its decay is
        unconditional, every tick, as it always was."""
        self._require_started()
        now = self._as_dt(now)

        # 0 (Track A). Proposal timeout — reachable from the "user never
        # speaks at all" direction: there is NO timer, NO thread, NO asyncio
        # anywhere in this codebase, so a deadline compared against the
        # injected clock on the next tick is the house pattern (idle
        # detection already works exactly this way). This does NOT write PAD
        # itself — _expire_proposal replays the pending query through the
        # full pipeline, and any PAD movement is that replay's appraisal
        # byproduct, not an effect of this check.
        if (
            self._daemon_state is DaemonState.PROPOSING_CLOUD
            and self._proposal_deadline is not None
            and now >= self._proposal_deadline
        ):
            self._expire_proposal(now)

        # 1. PAD decay — Module 1 owns the EMA math; the Daemon only ticks it.
        self._pad.on_soul_tick()

        # 2. Energy — THREE states, not two (Resolution Log item 29):
        #      GENUINE IDLE      (gate open, nothing pending) -> RECOVER
        #      PRE-IDLE SILENCE  (quiet, gate not open yet)   -> HELD (no call)
        #      ACTIVE LOAD       (output pending)             -> DEPLETE
        # Module 2 still owns all the math; the Daemon only chooses which signal
        # to send, and in the middle state it sends NEITHER. This reads idle
        # STATE; it does not touch the DMN clock.
        if self._idle_conditions_met(now):
            self._needs.on_idle_recovery()
        elif self._in_pre_idle_silence(now):
            pass  # HELD — see _in_pre_idle_silence for why silence is not load.
        else:
            self._needs.on_soul_tick()

        # 3. Attentional policy (Resolution Log item 10, literal) — volatile.
        self._refresh_attentional_policy(now)

        # 4. Initiative (v4 Layer 2/6) — once, no nag, enters at soul_filter.
        self._maybe_initiate(now)

        self._soul_tick_count += 1

    # =======================================================================
    # CLOCK 2 — the DMN tick (idle consolidation). SEPARATE from the soul tick.
    # =======================================================================
    def dmn_tick(self, now: Optional[datetime] = None):
        """One DMN tick. Runs a DMN idle pass ONLY at genuine idle (conditions 1
        & 2 — no voice for 8 min, no pending output; the Daemon owns these). The
        THIRD condition (Energy) is DMN's: it reads Energy and chooses pass DEPTH
        (FULL ≥ 20 / SHALLOW < 20) — it does not gate whether idle fires (DMN
        spec Req 2.3). This method NEVER decays PAD (separate clock,
        constraint 2)."""
        self._require_started()
        now = self._as_dt(now)
        self._dmn_tick_count += 1
        if not self._idle_conditions_met(now):
            return None
        pass_input = self._assemble_idle_pass_input(now)
        result = self._dmn.run_idle_pass(pass_input)
        self._consume_dmn_result(result)
        return result

    def run_scheduler_step(self, now: Optional[datetime] = None) -> List[str]:
        """Advance BOTH clocks independently by their OWN intervals. Each fires
        on its own schedule; neither triggers the other (the two clocks never
        merge, constraint 2). Returns which clocks fired this step. The direct
        `soul_tick()` / `dmn_tick()` methods are the primary interface; this is
        the convenience scheduler for real operation."""
        self._require_started()
        now = self._as_dt(now)
        fired: List[str] = []
        if (now - self._last_soul_tick_at) >= self._soul_tick_interval:
            self.soul_tick(now=now)
            self._last_soul_tick_at = now
            fired.append("soul")
        if (now - self._last_dmn_tick_at) >= self._dmn_tick_interval:
            self.dmn_tick(now=now)
            self._last_dmn_tick_at = now
            fired.append("dmn")
        return fired

    

    # =======================================================================
    # Inbound turn routing — the full pipeline.
    #   Audio(STT) → Appraisal → Soul_Filter → LLM → Output Gate → Audio(TTS)
    # =======================================================================
    def route_inbound_turn(
        self,
        *,
        user_text: str,
        session_id: Optional[str] = None,
        entity_refs: Sequence[str] = (),
        entity_node_id: Optional[str] = None,
        active_uncertainty_refs: Sequence[str] = (),
        now: Optional[datetime] = None,
    ) -> SoulFilterResponse:
        """Route one inbound (already-transcribed) user turn through the full
        pipeline and return Soul_Filter's validated response. PAD moves ONLY
        inside the Appraisal Chain here (its Stage-4 delta via PAD_Engine) — the
        Daemon writes no PAD. The Daemon routes; the modules decide.

        STATE MACHINE (Track A — BackendRouter wired into the conversation
        loop): if the PREVIOUS turn asked the user whether to escalate to the
        reasoning tier, this turn is that answer (STEP 1) — everything below
        is skipped. Otherwise the ordinary pipeline runs, with two NEW
        interceptions ahead of it: a backend meta-command check (STEP 3) and
        a routing decision that may itself defer this turn into a proposal
        (STEP 5). When no BackendRouter is injected, STEP 3 and STEP 5 are
        no-ops and this method behaves EXACTLY as it did before Track A."""
        self._require_started()
        now = self._as_dt(now)
        session_id = session_id or self._session_id

        # --- STEP 1: proposal-response interception. If the previous turn
        # left us waiting for a yes/no, THIS turn IS that answer — nothing
        # below runs. -----------------------------------------------------
        if self._daemon_state is DaemonState.PROPOSING_CLOUD:
            return self._handle_proposal_response(user_text, now)

        # --- STEP 2: SessionBuffer meta-command check (existing, unchanged;
        # before appraisal, before Stage 0). --------------------------------
        meta = self._session_buffer.is_meta_command(user_text)
        if meta:
            return self._handle_meta_command(meta, now)

        # --- STEP 3 (NEW): backend meta-command check ("use cloud" / "stay
        # local" / ...). Bypasses appraisal, Soul Filter, the LLM, and the
        # Output Gate, exactly like the SessionBuffer meta-commands above.
        # Writes NO EventNode. No-op (falls through) when no router is
        # wired — fully backward compatible. --------------------------------
        if self._backend_router is not None:
            tier = _match_backend_meta_command(user_text)
            if tier is not _NO_BACKEND_META_COMMAND:
                return self._handle_backend_meta_command(tier, now)

        # --- STEP 4: cognitive load checks --------------------------------
        # (a) Working-memory pressure (existing, unchanged).
        fullness = self._session_buffer.fullness_state()
        if fullness in ("heavy", "critical"):
            self._appraisal.submit_cognitive_load(fullness)

        # (b) Energy below the in-spec 30 gate. Addendum §3: "The existing
        # 'reasoning degrades below 30' rule stays as an operational threshold
        # gate, same category as Q4 ≤ 0.15 for Emergency." v4's mechanism table
        # files the "Cognitive load effect" as an "Appraisal modifier" reaching
        # "Stage 2 appraisal + DMN depth check", so it routes through the
        # EXISTING submit_cognitive_load entry point — no new mechanism, and no
        # new number (ENERGY_LOW is the spec's own gate).
        #
        # The mapping is categorical: Energy is below the gate or it is not.
        # Energy itself NEVER crosses into the Appraisal Chain — that module
        # holds no Energy handle and needs none; only the categorical load state
        # crosses, exactly as buffer fullness does above.
        #
        # This SKIPS NOTHING. Every appraisal stage still runs, the Stage-1
        # social-signal pre-pass (including the vulnerability check) is
        # untouched, and the emergency gate is untouched — a tired ARIA still
        # detects a crisis. The only effect is the second-order PAD byproduct
        # submit_cognitive_load already emits.
        if self._needs.get_energy() < ENERGY_LOW:
            self._appraisal.submit_cognitive_load("heavy")

        # --- STEP 4b: distress gate on the proposal path (FLAG 3) -----------
        # BackendRouter's tier-2 classifier is a keyword match, and emotional
        # language routinely contains one of those keywords ("explain", "analyze",
        # "complex"). Because STEP 5 RETURNS on propose, a distressed turn would
        # be answered with "shall I use the reasoning tier?" and the appraisal —
        # including the emergency gate — would not run until the user replied or
        # the proposal timed out.
        #
        # Measured, not assumed: "I feel like everything falls apart. Can you
        # explain what's wrong with me?" matches TIER_2_KEYWORDS on "explain",
        # and "I want to die, explain why I should keep going" matches too. So
        # the earlier claim that the crisis lexicons sit "upstream of and
        # independent of" this classifier was backwards — they are DOWNSTREAM of
        # the return at STEP 5.
        #
        # The check reuses the Appraisal Chain's OWN lexicons via
        # has_distress_markers() — no new lexicon, no LLM, no embedding, one
        # local string scan. Presence beats routing: when it fires, the turn
        # skips the proposal branch entirely and flows through the full pipeline.
        #
        # It is passed to the ROUTER rather than used to discard the router's
        # answer. Discarding a propose=True result left transport=None, which
        # silently handed the turn to LLMInterface's internal CLOUD-FIRST chain —
        # so the most distressed, most personal messages were the ones leaving the
        # machine, while small talk got the local voice. Telling the router not to
        # propose lets its normal gemma-first order decide instead.
        distressed = self._appraisal.has_distress_markers(user_text)

        # --- STEP 5 (NEW): routing decision. If a router is wired, ask it
        # which transport should serve this turn. A "propose" result defers
        # the turn into the proposal state machine instead of continuing.
        # No router wired -> transport stays None and behaviour below is
        # exactly as it was before Track A. ----------------------------------
        transport = None
        if self._backend_router is not None:
            transport, propose = self._backend_router.select(
                user_text, allow_tier_2_proposal=not distressed
            )
            if propose:
                return self._begin_proposal(
                    user_text, now,
                    session_id=session_id,
                    entity_refs=entity_refs,
                    entity_node_id=entity_node_id,
                    active_uncertainty_refs=active_uncertainty_refs,
                )

        # --- STEP 6+: the existing pipeline, unchanged except that
        # soul_filter.respond(...) now also receives transport=transport. ---
        # (condition 2). This is audio-FSM bookkeeping, not meaning.
        self._note_voice_input(now)
        self._output_pending = True
        # Volatile Present World Model update (working state, not persisted).
        self._present_world_model["last_user_text"] = user_text

        # --- Layer 5 thinking sound: the instant transcription finishes,
        # BEFORE the LLM generates (v4). Reads PAD (presentation) + text; picks
        # a PRE-CACHED sound; Gemma never involved. NOT a PAD write. ----------
        self._play_thinking_sound(user_text)

        # --- Appraisal (Module 4): the meaning step. Needs states cross as a
        # Stage-1 retrieval PREFERENCE only (Addendum §3). PAD shifts here as
        # the appraisal's byproduct, via PAD_Engine — never via the Daemon. ---
        need_states = self._needs.get_need_states(now=now)
        appraisal = self._appraisal.appraise(
            user_text=user_text,
            session_id=session_id,
            entity_refs=list(entity_refs),
            need_states=need_states_to_mapping(need_states),
            active_uncertainty_refs=list(active_uncertainty_refs),
            now=now,
        )
        self._track_turn(appraisal, entity_refs, session_id)

        # --- Post-emergency flag: read BEFORE soul_filter, update AFTER appraisal.
        post_emergency = self._last_turn_was_emergency
        self._last_turn_was_emergency = appraisal.emergency
        post_emergency_this_turn = post_emergency and not appraisal.emergency


        # --- Soul_Filter (Module 5): assemble → LLM (Module 9) → Output Gate.
        # The five-field boundary and the gate are Soul_Filter's; the Daemon
        # passes the appraisal + the raw user message through unchanged.
        # `transport` is the Daemon's routing decision (Track A) — an opaque
        # handle passed through, never inspected. ----------------------------
        session_context = self._session_buffer.get_context()
        response = self._soul_filter.respond(
            appraisal_result=appraisal,
            user_message=user_text,
            entity_node_id=entity_node_id,
            entity_refs=tuple(entity_refs),
            need_states=need_states,
            now=now,
            post_emergency=post_emergency_this_turn,
            session_context=session_context,
            transport=transport,
        )

        # --- Actual token counts: the provider already counted, exactly, so
        # SessionBuffer stops budgeting against `chars // 4`. Read from the
        # transport the Daemon itself selected, AFTER the turn it describes. ---
        self._record_actual_tokens(transport)

        # --- Audio Pipeline (Module 7 contract): render validated text (TTS). -
        self._audio.speak(response.text)
        self._output_pending = False

        # --- Append turn to session buffer (ephemeral working memory) ------
        self._session_buffer.append_turn(user_text, response.text)

        # --- Reflection trigger: poignancy=critical forces an EARLY DMN partial
        # pass (Steps 1+4) while conversation continues (v4 "forced early partial
        # pass"). This is a DMN-CLOCK event triggered by content — it does NOT
        # decay PAD and does NOT merge the clocks. -----------------------------
        if appraisal.poignancy is PoignancyCategory.CRITICAL and appraisal.event_node_id:
            fp_input = DMNPassInput(
                buffer=[BufferItem(
                    observed_event_ref=appraisal.event_node_id,
                    entity_refs=list(entity_refs),
                )],
                entity_refs=list(entity_refs),
                session_id=session_id,
                now=now,
            )
            fp_result = self._dmn.run_forced_partial_pass(fp_input)
            self._consume_dmn_result(fp_result)

        return response

    def _record_actual_tokens(self, transport: Optional[object]) -> None:
        """Hand the served turn's REAL token counts to the SessionBuffer.

        `transport` is the same opaque routing handle passed to Soul Filter, and
        it stays opaque: this asks it ONE question, by duck type, and inspects
        nothing else. A transport with no `last_turn_metadata()` — a test double,
        `UnconfiguredTransport`, or any adapter written before this existed — is
        silently skipped, and the buffer keeps using its own `chars // 4`
        estimate. No Protocol changed to make this possible; nothing breaks by
        not implementing it.

        `transport is None` (no BackendRouter wired) is the same case: no handle,
        no counts, estimate stands.

        TWO HONEST LIMITS, both structural rather than fixable here:

        * ONE TURN OF LAG. These counts describe the prompt just sent, which was
          assembled before this turn was appended to the buffer. So STEP 4's
          cognitive-load read on the NEXT turn is measuring the prompt before
          last. Closing that gap would need a tokenizer inside `daemon/`, which
          the layer's zero-dependency property forbids for something this small.
        * WHOLE-PROMPT, NOT BUFFER-ONLY. `prompt_tokens` covers the five fields
          and the user's message too. That is the number worth bounding — it is
          what the model was actually asked to hold — but it is not a measurement
          of this buffer's content in isolation.

        This is a MEASUREMENT crossing into memory plumbing. It reaches PAD only
        the way buffer fullness always has: `fullness_state()` collapses it to a
        categorical band and the Appraisal Chain makes the meaning. No number
        goes anywhere near PAD, and the Daemon still writes no PAD.
        """
        if transport is None:
            return
        reader = getattr(transport, "last_turn_metadata", None)
        if not callable(reader):
            return
        metadata = reader()
        if metadata is None:
            return
        duration_ns = getattr(metadata, "duration_ns", None)
        self._session_buffer.record_actual_tokens(
            prompt_tokens=getattr(metadata, "prompt_tokens", None),
            gen_tokens=getattr(metadata, "gen_tokens", None),
            # Nanoseconds → milliseconds, the unit SessionBuffer asks for. None
            # stays None: a cloud tier reports no duration, and a zero would
            # claim an instant generation rather than an unmeasured one.
            gen_duration_ms=(
                duration_ns // 1_000_000 if isinstance(duration_ns, int) else None
            ),
        )

    # =======================================================================
    # Backend-proposal state machine (Track A). See the module-level
    # DaemonState / _AFFIRMATIVE / _NEGATIVE / _BACKEND_META_COMMANDS /
    # _PROPOSAL_PROMPT / _PROPOSAL_TIMEOUT_REPLY constants above.
    # =======================================================================
    def _handle_backend_meta_command(
        self, tier: Optional[str], now: datetime
    ) -> SoulFilterResponse:
        """A backend meta-command ("use cloud" / "stay local" / "use groq" /
        "go back to normal") sets or clears the router's session-scoped
        override and returns a brief pre-authored acknowledgement —
        bypassing appraisal, Soul Filter, the LLM, and the Output Gate,
        exactly like `_handle_meta_command` does for SessionBuffer's
        meta-commands. Writes NO EventNode; runs NO appraisal."""
        if tier is None:
            self._backend_router.clear_override()
        else:
            self._backend_router.set_override(tier)
        ack = _BACKEND_META_ACK[tier]
        self._audio.speak(ack)
        return SoulFilterResponse(
            text=ack,
            instruction_kind="five_field",
            retried=False,
            used_minimum_safe_output=False,
            reconsideration_sound_triggered=False,
            gate_results=(),
        )

    def _begin_proposal(
        self,
        user_text: str,
        now: datetime,
        *,
        session_id: Optional[str],
        entity_refs: Sequence[str],
        entity_node_id: Optional[str],
        active_uncertainty_refs: Sequence[str],
    ) -> SoulFilterResponse:
        """Defer this turn: store it (and the routing kwargs needed to replay
        it identically) and ask the user whether to escalate to the
        reasoning tier. Writes NO EventNode and runs NO appraisal — the
        pending query gets appraised on replay, so no user input is lost
        from the graph."""
        self._pending_query = user_text
        self._pending_kwargs = {
            "session_id": session_id,
            "entity_refs": entity_refs,
            "entity_node_id": entity_node_id,
            "active_uncertainty_refs": active_uncertainty_refs,
        }
        self._proposal_deadline = now + self._proposal_timeout
        self._daemon_state = DaemonState.PROPOSING_CLOUD

        self._note_voice_input(now)  # the user DID speak; idle must reset
        self._audio.speak(_PROPOSAL_PROMPT)
        # ARIA has finished speaking and is now waiting for the user, so
        # idle detection is not wedged.
        self._output_pending = False

        return SoulFilterResponse(
            text=_PROPOSAL_PROMPT,
            instruction_kind="five_field",
            retried=False,
            used_minimum_safe_output=False,
            reconsideration_sound_triggered=False,
            gate_results=(),
        )

    def _handle_proposal_response(self, user_text: str, now: datetime) -> SoulFilterResponse:
        """The user's answer to a pending proposal (or, if the deadline has
        already passed, a late reply arriving after the timeout already
        fired)."""
        if self._proposal_deadline is not None and now >= self._proposal_deadline:
            # Timed out already. Auto-answer the DEFERRED query via the
            # timeout path (4g), then treat THIS utterance as a FRESH turn —
            # state is NORMAL after _expire_proposal, so re-entering is safe
            # (no infinite recursion: PROPOSING_CLOUD cannot be re-entered by
            # this same call).
            self._expire_proposal(now)
            return self.route_inbound_turn(user_text=user_text, now=now)

        if _matches_any(user_text, _AFFIRMATIVE):
            self._backend_router.set_override("tier_2")
        elif _matches_any(user_text, _NEGATIVE):
            self._backend_router.set_override("tier_0")
        else:
            # NEITHER lexicon matches — FLAGGED DEFAULT: treat as negative
            # (the same action as an explicit negative match) so the user's
            # original question is still answered rather than dropped (FLAG
            # 2 in HANDOFF_NOTES.md; not stated in any source document).
            self._backend_router.set_override("tier_0")

        pending_query = self._pending_query
        pending_kwargs = self._pending_kwargs or {}
        # Clear BEFORE replay so a re-entrant path cannot loop.
        self._daemon_state = DaemonState.NORMAL
        self._proposal_deadline = None
        self._pending_query = None
        self._pending_kwargs = None

        return self.route_inbound_turn(user_text=pending_query, now=now, **pending_kwargs)

    def _expire_proposal(self, now: datetime) -> SoulFilterResponse:
        """The user never answered (soul_tick noticed the deadline passed,
        or a late reply arrived after it did): auto-answer with the DEFAULT
        VOICE (Gemma) rather than dropping the deferred query.

        NO PAD EFFECT HERE — the Daemon holds no PAD mutator path. The
        replay below runs the pending query through AppraisalChain.appraise
        (via the full route_inbound_turn pipeline), which produces its OWN
        PAD delta as a byproduct via PAD_Engine — that IS the emotional
        consequence of the timeout, arrived at through appraisal, not
        injected by the orchestrator (FLAG 1 in HANDOFF_NOTES.md)."""
        self._audio.speak(_PROPOSAL_TIMEOUT_REPLY)
        self._backend_router.set_override("tier_0")  # auto-answer uses Gemma

        pending_query = self._pending_query
        pending_kwargs = self._pending_kwargs or {}
        self._daemon_state = DaemonState.NORMAL
        self._proposal_deadline = None
        self._pending_query = None
        self._pending_kwargs = None

        return self.route_inbound_turn(user_text=pending_query, now=now, **pending_kwargs)

    # =======================================================================
    # F4 / barge-in — ZERO INTERNAL EFFECT (Addendum §5). Audio stop ONLY.
    # Each method's ENTIRE body is one call into the Audio Pipeline. There is
    # deliberately NO reference here to pad_engine, appraisal, graph, needs, or
    # state — proving structurally that there is no path to a PAD write or any
    # state mutation.
    # =======================================================================
    def on_f4_interrupt(self) -> None:
        """F4 interrupt (Addendum §5): a functional audio STOP mechanism only.
        No PAD effect, no appraisable event, no graph write, nothing internal —
        it just stops audio and returns to listening. Whatever the user says
        AFTER pressing it enters appraisal normally, like any input."""
        self._audio.stop_playback()

    def on_barge_in(self) -> None:
        """Pause-based barge-in (v4; Addendum §5 "The same logic applies to
        barge-in … stops and listens with zero internal effect"). SAME shape as
        F4 — audio stop only, zero internal effect."""
        self._audio.stop_playback()

    # =======================================================================
    # Idle detection (conditions 1 & 2 — Daemon-owned; condition 3 is DMN's).
    # The same two markers also separate the THREE Energy states the soul tick
    # chooses between (Resolution Log item 29) — see _in_pre_idle_silence.
    # =======================================================================
    def _idle_conditions_met(self, now: Optional[datetime] = None) -> bool:
        """Idle conditions the Daemon owns (v4 Idle Detection): (1) no voice
        input for 8 minutes; (2) no pending output. Condition (3) — Energy > 20
        — is NOT gated here: DMN reads Energy to choose pass DEPTH (DMN spec
        Req 2.3), so gating it here too would make the shallow pass unreachable.
        The Daemon detects "genuinely idle right now"; DMN decides how deep."""
        now = self._as_dt(now)
        no_voice_for_window = (now - self._last_voice_input_at) >= self._idle_no_voice_window
        no_pending_output = not self._output_pending
        return no_voice_for_window and no_pending_output

    def _in_pre_idle_silence(self, now: Optional[datetime] = None) -> bool:
        """The MIDDLE state (Resolution Log item 29): she has gone quiet, nothing
        is pending, and the 8-minute idle gate has not opened yet. Energy is HELD
        here — neither depleted nor recovered.

        WHY SILENCE IS NOT LOAD. `_idle_conditions_met` is False for this whole
        stretch, so before item 29 every soul tick in it took the active-load
        branch: `tools/observe_dmn_pass.py` measured Energy falling 81.5 -> 0.1
        across a real 8-minute silence, which made the DMN's first genuine pass
        SHALLOW and left Steps 2 and 3 permanently unreachable through a real
        silence. Waiting is not work. The architect's ruling: "in rest situation,
        energy will not consume" — so Energy at the moment the gate opens is the
        tiredness the CONVERSATION actually left, not an artefact of how long she
        has been sitting alone.

        This introduces no state and no number. The three states are read off the
        two markers idle detection already owns (`_last_voice_input_at` and
        `_output_pending`) and the PINNED 8-minute window. `_note_voice_input`
        aborts the middle state for free: the user speaking restarts the window,
        so the gate re-arms from that instant.
        """
        now = self._as_dt(now)
        within_window = (now - self._last_voice_input_at) < self._idle_no_voice_window
        return within_window and not self._output_pending

    def _note_voice_input(self, now: Optional[datetime] = None) -> None:
        """Record that voice input arrived (resets idle condition 1, and aborts
        the pre-idle silence window — item 29's middle state is derived from this
        timestamp, so restarting it is the whole abort)."""
        self._last_voice_input_at = self._as_dt(now)

    # =======================================================================
    # Attentional policy + initiative (ResLog item 10; v4 Layer 2/6).
    # =======================================================================
    def _refresh_attentional_policy(self, now: Optional[datetime] = None) -> None:
        """Refresh the volatile attentional focus = (highest-pressure need,
        most-recently-salient node) — Resolution Log item 10, LITERAL. Reads
        categorical need states from Needs_System (the Daemon derives none) and
        resets the no-nag latch for any need that is satisfied again."""
        need_states = self._needs.get_need_states(now=now)
        for name in _NEED_ORDER:
            if getattr(need_states, name) is NeedState.SATISFIED:
                self._initiative_expressed[name] = False  # recovered → may reach out again later
        self._highest_pressure_need = self._select_highest_pressure_need(need_states)
        self._attentional_focus = (self._highest_pressure_need, self._most_recently_salient_node)

    @staticmethod
    def _select_highest_pressure_need(need_states: NeedStates) -> Optional[str]:
        """The "highest-pressure need" (Resolution Log item 10, literal). The
        four needs are CATEGORICAL (satisfied/due — Addendum §3): a `due` need
        has pressure, a satisfied one does not. There is NO numeric magnitude to
        rank by (inventing one is forbidden — the percentage test), so the
        tie-break among simultaneously-`due` needs is the canonical spec order
        (F-8b, FLAGGED). Keyed on `due` — the critical categorical state Needs
        System emits; `neglected` is accepted too but is never currently emitted
        (Needs System OQ-1, FLAGGED for revisit). Returns the need name or None
        (all satisfied)."""
        for name in _NEED_ORDER:
            if getattr(need_states, name) in (NeedState.DUE, NeedState.NEGLECTED):
                return name
        return None

    def _maybe_initiate(self, now: Optional[datetime] = None):
        """Evaluate initiative on the soul tick: if the highest-pressure need is
        `due` and has NOT yet been expressed this due-episode, express it ONCE
        (v4 "expresses a need exactly once … does not repeat"). No numeric
        threshold. Returns the response if it fired, else None."""
        need = self._highest_pressure_need
        if need is None:
            return None
        if self._initiative_expressed.get(need, False):
            return None  # already expressed once — NEVER nag (v4)
        response = self._route_initiative(need, now)
        self._initiative_expressed[need] = True  # latch: no repeat until satisfied
        return response

    def _route_initiative(self, need: str, now: Optional[datetime] = None) -> SoulFilterResponse:
        """Aria-initiated speech ENTERS AT soul_filter DIRECTLY (Addendum §7):
        wake-word, speaker verification, VAD and Whisper STT are skipped
        entirely, and the Appraisal Chain is NOT invoked (no user turn to
        appraise). The Daemon selects a PRE-AUTHORED behavioral instruction by
        which need is due (categorical, from Needs_System) and hands it to
        Soul_Filter through a minimal appraisal whose inert PAD delta is never
        applied — so the Daemon computes and writes NO feeling."""
        note = _INITIATIVE_NOTES[need]
        appraisal = build_initiative_appraisal(note)
        need_states = self._needs.get_need_states(now=now)
        self._output_pending = True
        response = self._soul_filter.respond(
            appraisal_result=appraisal,
            user_message="",                     # Aria-initiated: no user message
            entity_node_id=self._primary_entity_id,
            entity_refs=(),                      # a gentle reach-out asserts no specific fact
            need_states=need_states,
            now=now,
        )
        self._audio.speak(response.text)          # TTS (Module 7 contract)
        self._output_pending = False
        self._initiative_count += 1
        return response

    # =======================================================================
    # Thinking-sound playback (Layer 5).
    # =======================================================================
    def _play_thinking_sound(self, user_text: str) -> Optional[ThinkingSound]:
        """Select a pre-cached thinking sound (categorical, from text + PAD) and
        hand its key to the Audio Pipeline. Reads PAD for PRESENTATION only —
        never a PAD write (v4 Layer 5)."""
        pad = self._pad.get_current_pad()  # presentation read (allowed)
        sound = select_thinking_sound(user_text, pad)
        if sound is not None:
            self._audio.play_thinking_sound(sound.value)
        return sound

    def on_reconsideration(self) -> None:
        """Play the reconsideration sound (v4 "Self-Correction Sound") during a
        Soul_Filter retry. Build Plan Module 5 output: "Reconsideration-sound
        trigger (on retry) → Daemon." Callers wire this as Soul_Filter's
        `on_reconsideration` callback; it only plays audio (no internal effect)."""
        self._audio.play_reconsideration_sound()

    # =======================================================================
    # Language-switch state (volatile working state; v4 "Language Switching").
    # =======================================================================
    def set_language(self, language: str) -> None:
        """Set the current language. Conversation-driven only (v4: "the user
        triggers it … No automatic detection that overrides the user's intent").
        VOLATILE working state — NOT persisted (Resolution Log item 10)."""
        self._language = language

    @property
    def language(self) -> str:
        return self._language

    # =======================================================================
    # DMN-pass input assembly + result consumption (Daemon supplies the buffer
    # and the graph-derived candidate/uncertainty/entity/rupture refs — mirrors
    # how the Appraisal Chain already receives entity_refs from the Daemon).
    # =======================================================================
    def _assemble_idle_pass_input(self, now: Optional[datetime] = None) -> DMNPassInput:
        """Assemble a DMN idle-pass input from the Daemon's tracked working
        state and the REAL graph's highest-salience-unconnected selection (the
        additive Module 8 closure). Each structural-fact record maps 1:1 to a
        ConnectionCandidate — pure PACKAGING; the Daemon decides no meaning, and
        DMN's Step 2 makes the categorical connection/aha decision."""
        candidates = [
            ConnectionCandidate(**rec)
            for rec in self._graph.highest_salience_unconnected_candidates(now=now)
        ]
        return DMNPassInput(
            buffer=list(self._self_monitoring_buffer),
            connection_candidates=candidates,
            active_uncertainty_refs=list(self._active_uncertainty_refs),
            entity_refs=list(self._session_entity_refs),
            rupture_entity_refs=list(self._rupture_entity_refs),
            session_id=self._session_id,
            now=now,
        )

    def _consume_dmn_result(self, result) -> None:
        """Clear the buffer items DMN consumed (so they are not re-processed)
        and clear the ruptures relayed to that pass."""
        consumed = set(result.buffer_consumed)
        self._self_monitoring_buffer = [
            b for b in self._self_monitoring_buffer
            if b.observed_event_ref not in consumed
        ]
        if self._last_turn_buffer_item is not None and (
            self._last_turn_buffer_item.observed_event_ref in consumed
        ):
            self._last_turn_buffer_item = None
        self._rupture_entity_refs = []

    def _track_turn(
        self, appraisal: AppraisalResult, entity_refs: Sequence[str], session_id: str
    ) -> None:
        """Update the Daemon's volatile DMN-input working state from a turn's
        appraisal: append a self-monitoring buffer item (linking the PREVIOUS
        turn's reaction — consecutive EventNodes), track active/resolved
        uncertainties, session entities, most-recently-salient node, and relay
        any REALITY_CONTRADICTION rupture (Addendum §1) for DMN's regression."""
        self._session_id = session_id
        event_id = appraisal.event_node_id
        if event_id:
            # Most-recently-salient node (attentional policy volatile state).
            self._most_recently_salient_node = event_id
            # Link the previous turn's reaction (consecutive EventNodes) for the
            # observed-reaction quality grade (DMN Step 1 anti-flattery guard).
            if self._last_turn_buffer_item is not None:
                self._last_turn_buffer_item.reaction_event_ref = event_id
            item = BufferItem(observed_event_ref=event_id, entity_refs=list(entity_refs))
            self._self_monitoring_buffer.append(item)
            self._last_turn_buffer_item = item

        # Track uncertainty lifecycle (relayed to DMN Step 3).
        if appraisal.uncertainty_node_id:
            self._active_uncertainty_refs.append(appraisal.uncertainty_node_id)
        for ref in appraisal.resolved_uncertainty_ids:
            if ref in self._active_uncertainty_refs:
                self._active_uncertainty_refs.remove(ref)

        # Track session entities (relayed to DMN Step 4 stage evaluation).
        for ref in entity_refs:
            if ref not in self._session_entity_refs:
                self._session_entity_refs.append(ref)

        # Relay a REALITY_CONTRADICTION rupture (Addendum §1 detects it live in
        # appraisal; the Daemon relays it — regression is a live rupture).
        if appraisal.social_signals.reality_contradiction:
            for ref in entity_refs:
                if ref not in self._rupture_entity_refs:
                    self._rupture_entity_refs.append(ref)

    # =======================================================================
    # Small helpers.
    # =======================================================================
    def _as_dt(self, now: Optional[datetime]) -> datetime:
        return now if now is not None else self._clock()

    def _handle_meta_command(self, command: str, now: Optional[datetime] = None) -> SoulFilterResponse:
        if command == "rest":
            # Force DMN consolidation of recent buffer before clearing
            if self._self_monitoring_buffer:
                fp_input = DMNPassInput(
                    buffer=list(self._self_monitoring_buffer),
                    entity_refs=list(self._session_entity_refs),
                    session_id=self._session_id,
                    now=now or self._clock(),
                )
                fp_result = self._dmn.run_forced_partial_pass(fp_input)
                self._consume_dmn_result(fp_result)
            self._session_buffer.clear()
            return SoulFilterResponse(
                text="There. My head feels clearer. Where were we?",
                instruction_kind="five_field", retried=False,
                used_minimum_safe_output=False,
                reconsideration_sound_triggered=False, gate_results=(),
            )
        if command == "focus":
            self._session_buffer.set_focus_mode(True)
            return SoulFilterResponse(
                text="Okay. Just us, right here.",
                instruction_kind="five_field", retried=False,
                used_minimum_safe_output=False,
                reconsideration_sound_triggered=False, gate_results=(),
            )
        if command == "unfocus":
            self._session_buffer.set_focus_mode(False)
            return SoulFilterResponse(
                text="There. I have the full picture again.",
                instruction_kind="five_field", retried=False,
                used_minimum_safe_output=False,
                reconsideration_sound_triggered=False, gate_results=(),
            )
        raise RuntimeError(f"Unknown meta-command: {command}")

    # -- read-only observability (NOT decision surfaces) -------------------
    @property
    def soul_tick_count(self) -> int:
        return self._soul_tick_count

    @property
    def dmn_tick_count(self) -> int:
        return self._dmn_tick_count

    @property
    def initiative_count(self) -> int:
        return self._initiative_count

    @property
    def attentional_focus(self) -> tuple:
        """(highest-pressure need, most-recently-salient node) — volatile
        working state (Resolution Log item 10)."""
        return self._attentional_focus

    @property
    def started(self) -> bool:
        return self._started

    @property
    def pad_restore_was_reset(self) -> bool:
        """True when `startup()`'s PAD OQ4 consistency check discarded a
        half-written PAD record and restored baseline instead (see startup()).

        Read-only, observability ONLY — no soul module reads it, it crosses no
        model boundary, and nothing branches on it. It exists so the reset is
        visible: a silent fallback makes "she is resting at baseline today"
        indistinguishable from "a corrupt state file erased what she felt", and
        those need different responses from whoever is running her."""
        return self._pad_restore_was_reset

    @property
    def session_buffer_fullness(self) -> str:
        """The session buffer's categorical fullness state, read-only.

        Added 2026-08-22 for the wiring layer's diagnostics. The Daemon
        constructs its own `SessionBuffer` internally, so a caller has no handle
        to ask `fullness_state()` itself — and this is the one piece of that
        buffer's state a caller has any business seeing, since it is what drives
        the cognitive-load trigger in STEP 4.

        Read-only and categorical, like every other property in this section. It
        is NOT a decision surface: nothing outside this module may act on it, and
        it crosses no boundary to any model.
        """
        return self._session_buffer.fullness_state()

    # -- read-only observability (Track A — NOT decision surfaces) ----------
    @property
    def state(self) -> DaemonState:
        """Turn-routing state (NORMAL / PROPOSING_CLOUD). Read-only."""
        return self._daemon_state

    @property
    def proposal_pending(self) -> bool:
        """True while waiting for the user's answer to a backend-escalation
        proposal."""
        return self._daemon_state is DaemonState.PROPOSING_CLOUD

    @property
    def pending_query(self) -> Optional[str]:
        """The deferred user turn awaiting a proposal answer, or None."""
        return self._pending_query
