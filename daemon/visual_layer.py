"""Module 10 — Visual Layer (Aria's face).

Locked spec: see .kiro/specs/visual-layer/{requirements,design,tasks}.md.

Responsibility (`ARIA_Module_Build_Plan.md`, Module 10): map the current PAD to
one of eight video zones (idle + talking variants) and drive the PyQt6 frameless
always-on-top window with libmpv, running independently and in parallel with
language generation. This module plays the role v4's directory structure assigns
to `video_controller.py`: "PAD zone -> PyQt6 window loop signal."

===========================================================================
HARD PHILOSOPHY CONSTRAINTS (a violation is WRONG even if tests pass)
===========================================================================

1. COMPUTES NO FEELING / NEVER WRITES PAD. Mapping PAD -> a video zone is a
   READ of substrate for PRESENTATION (steering/project-rules.md substrate-vs-
   feeling chain; v4 "Representation Layer"), NOT an appraisal. The Visual Layer
   READS current PAD via a read-only seam and NEVER writes it (project-rules.md
   PAD-purity: "PAD changes only via an Appraisal Chain PAD delta or EMA decay.
   Nothing else ... writes to PAD directly, ever"). Grep-clean: no PAD mutator
   (`apply_appraisal_delta`/`on_soul_tick`/`initialize`) appears in this module.
   It holds NO Appraisal/Graph/Needs/State/SoulFilter/LLM collaborator.

2. ZONE SELECTION IS CATEGORICAL (WHICH zone). `map_pad_to_zone` decides zone
   membership by boolean threshold comparisons ("holds or it doesn't") -- NEVER
   a distance, centroid nearness, weighted score, or percentage
   (project-rules.md "the percentage test": if you can ask "what percent of the
   way there is this?", it is a number in disguise and wrong). The eight zones
   and their PAD-region "+"/"-" markers ARE spec (v4 "PAD -> Video Zone Mapping"
   table). No feeling score is ever computed.

3. VARIANT FOLLOWS SPEAKING-STATE. Each zone has idle + talking variants (v4
   "Speaking State": "When Aria speaks, the talking variant of the current zone
   plays"). A talking<->idle change alters only the VARIANT of the current zone,
   promptly, and is NOT subject to the 8-second zone gate (the gate governs zone
   flicker, not the mouth).

4. 8-SECOND MINIMUM-BEFORE-SWITCH. A zone holds >= 8 s before a different zone
   may take over (v4 "Transition Logic": "If PAD stays in a zone for less than 8
   seconds, no switch -- prevents flickering"; v4 constants table: "Video zone
   stability | 8 seconds min before switch | video_controller.py").

5. GRACEFUL DEGRADATION. On cloud failure, the inward/waiting loop plays,
   overriding PAD zones (v4 "Graceful degradation video state": "an inward/
   waiting loop plays -- not sleeping ... but withdrawn. Present but quiet").
   Content is NOT fabricated; the loop is a distinct display STATE, not a zone.

6. INJECTED WINDOW -- NO GUI HARDCODED. The display is driven through an
   injected `VideoWindow` Protocol (v4's `ui/aria_window.py`: PyQt6 frameless
   floating window with libmpv embedded). PyQt6/libmpv are NEVER imported here
   (Rule 6). Tests inject a fake.

7. RUNS INDEPENDENTLY / IN PARALLEL WITH LANGUAGE GENERATION. `refresh()`
   depends only on the read-only PAD seam + the window (+ its own speaking/cloud
   signals). It never calls, blocks on, or holds a reference to the LLM
   Interface, Soul Filter, or Appraisal Chain (v4: "PAD zone mapping runs
   locally, independently, in parallel with language generation. The LLM never
   knows which video is playing").

8. EXPOSES A CLEAN CONTRACT THE DAEMON CAN DRIVE (`VisualLayerPort`). The Daemon
   defines no visual port today, so this module EXPOSES the contract (ResLog:
   "if none is defined, expose a clean contract the Daemon can drive"):
   set_speaking / set_cloud_available / refresh. No core module is modified.

===========================================================================
FLAG DISPOSITION (cite; do not invent -- Rule 1)
===========================================================================
  F-10a Video-owner discrepancy : RESOLVED by ARIA_Resolution_Log.md item 15 --
        "PAD->video zone mapping lives in Visual Layer (Module 10); v4's
        'soul_filter's job, not the LLM's' language is colloquial ... and
        doesn't override v4's own directory structure, which lists
        video_controller.py separately." Implemented HERE. Not reopened. v4's
        "Video selection is soul_filter's job, not the LLM's" is honored: the
        LLM never selects the video -- the local soul layer does.

  Zone precedence / gate reading (TODO(F-10-zone-precedence)) : v4's zone table
        does not order overlapping signatures (a high-everything PAD satisfies
        Playful, Engaged AND Thinking) nor state whether each zone's moderate
        descriptive values are hard gates. Only the v4 "+"/"-" markers are used
        as categorical predicates; the moderate values are feel-descriptors. The
        precedence ORDER (most-specific first) is a documented, deterministic
        PRESENTATION placeholder -- it never affects PAD, meaning, or memory
        (mirrors select_thinking_sound's flagged trigger precedence in
        aria_daemon.py). Never resolved by an invented feeling score.

  Driver-loop / signal wiring (OQ-1/OQ-2) : the independent timer/thread that
        calls refresh(), and wiring the Daemon's speak()-boundary ->
        set_speaking and the LLM Interface's serving_from_local ->
        set_cloud_available, are top-of-tree BUILD-TIME wiring, not this
        module's concern. The contract is exposed here; the Daemon is unchanged.

Precedence when documents conflict: ARIA_Resolution_Log.md >
ARIA_Soul_Spec_v4_Addendum.md > ARIA_Soul_Spec_v4.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Callable, Optional, Protocol, runtime_checkable

# --- REAL interface (imported, never redefined; read-only type only) -------
# Only PADSnapshot crosses in: a frozen, read-only PAD reading. NO write-capable
# module is imported (graph/appraisal/needs/state/daemon/soul_filter/llm), and
# NO GUI toolkit (PyQt6/mpv). That absence is the structural PAD-purity +
# independence guarantee (design.md "structural guarantees").
from daemon.pad_engine import PADSnapshot


# ===========================================================================
# Constants -- v4-CITED (Rule 4). No invented numbers.
# ===========================================================================

# v4 constants table: "Video zone stability | 8 seconds min before switch |
# video_controller.py"; v4 "Transition Logic": "If PAD stays in a zone for less
# than 8 seconds, no switch -- prevents flickering". Injectable for testing;
# defaults to the v4 value.
ZONE_STABILITY_SECONDS = 8

# Per-zone PAD-region boundaries -- the v4 "PAD -> Video Zone Mapping" table
# "+"/"-" markers, used as CATEGORICAL predicates (not a score). Each is the
# defining marker v4 gives for that zone; the moderate descriptive values v4
# also lists (e.g. Warm "A:0.4 D:0.5") are feel-descriptors, NOT extra gates
# (TODO(F-10-zone-precedence)).
LOW_TIRED_P_MAX = 0.4   # v4 Low/Tired  "P:0.4-"
LOW_TIRED_A_MAX = 0.3   # v4 Low/Tired  "A:0.3-"
LOW_TIRED_D_MAX = 0.4   # v4 Low/Tired  "D:0.4-"
CONCERNED_P_MAX = 0.3   # v4 Concerned  "P:0.3-"
PLAYFUL_P_MIN = 0.7     # v4 Playful    "P:0.7+"
PLAYFUL_A_MIN = 0.6     # v4 Playful    "A:0.6+"
PLAYFUL_D_MIN = 0.7     # v4 Playful    "D:0.7+"
FIRM_D_MIN = 0.8        # v4 Firm       "D:0.8+"
THINKING_A_MIN = 0.7    # v4 Thinking   "A:0.7+"
ENGAGED_P_MIN = 0.6     # v4 Engaged    "P:0.6+"
ENGAGED_A_MIN = 0.6     # v4 Engaged    "A:0.6+"
ENGAGED_D_MIN = 0.6     # v4 Engaged    "D:0.6+"
WARM_P_MIN = 0.7        # v4 Warm       "P:0.7+"
# Neutral/Idle = v4 "~baseline" (0.55/0.45/0.58) -- the DEFAULT when no other
# signature holds. Not a threshold; it is the fall-through category.


def _now() -> datetime:
    """Wall clock, timezone-aware UTC (matches aria_daemon.py's _now)."""
    return datetime.now(timezone.utc)


# ===========================================================================
# Value types.
# ===========================================================================

class Zone(Enum):
    """The eight categorical video zones (v4 "PAD -> Video Zone Mapping"), plus
    the separate INWARD_WAITING degradation STATE (v4 "Graceful degradation
    video state") -- which is NOT a PAD-mapped zone."""
    NEUTRAL_IDLE = "neutral_idle"
    ENGAGED = "engaged"
    WARM = "warm"
    THINKING = "thinking"
    CONCERNED = "concerned"
    PLAYFUL = "playful"
    LOW_TIRED = "low_tired"
    FIRM = "firm"
    # Degradation state -- distinct from the 8 zones; shown on cloud failure.
    INWARD_WAITING = "inward_waiting"


# The eight PAD-mapped zones, in canonical (v4-table) order -- excludes the
# INWARD_WAITING degradation state. Used by tests/tools that enumerate the
# real zone catalog.
PAD_ZONES = (
    Zone.NEUTRAL_IDLE,
    Zone.ENGAGED,
    Zone.WARM,
    Zone.THINKING,
    Zone.CONCERNED,
    Zone.PLAYFUL,
    Zone.LOW_TIRED,
    Zone.FIRM,
)


class SpeakingState(Enum):
    """The two loop variants per zone (v4 "Speaking State": "two loop variants
    -- idle and talking")."""
    IDLE = "idle"
    TALKING = "talking"


@dataclass(frozen=True)
class ZoneLoop:
    """The immutable "video-zone loop signal" handed to the window (Build Plan
    Module 10 Outputs). `loop_id` is the file-key the window plays -- matching
    v4's "16 video loop files (8 zones x 2 states: idle + talking)" plus the
    separate inward/waiting loop.

    For INWARD_WAITING the variant is normalized to IDLE at construction: the
    degradation loop is a single loop with no talking variant (v4 "an inward/
    waiting loop" -- singular; "present but quiet")."""
    zone: Zone
    variant: SpeakingState = SpeakingState.IDLE

    def __post_init__(self) -> None:
        # Normalize the degradation state to a single (IDLE) variant. Uses
        # object.__setattr__ because the dataclass is frozen.
        if self.zone is Zone.INWARD_WAITING and self.variant is not SpeakingState.IDLE:
            object.__setattr__(self, "variant", SpeakingState.IDLE)

    @property
    def loop_id(self) -> str:
        """File-key for the window, e.g. "engaged_talking", "neutral_idle_idle",
        "inward_waiting"."""
        if self.zone is Zone.INWARD_WAITING:
            return self.zone.value
        return f"{self.zone.value}_{self.variant.value}"


# ===========================================================================
# Injected Protocols (Rule 6). Real impls wrap the v4-named tools; tests inject
# fakes. No concrete provider is imported here.
# ===========================================================================

@runtime_checkable
class PADReader(Protocol):
    """The READ-ONLY seam onto PAD_Engine (Module 1). Exposes ONLY
    get_current_pad(); there is deliberately no mutator, so the presentation
    read can never become a PAD write (project-rules.md PAD-purity)."""

    def get_current_pad(self) -> PADSnapshot:
        ...


@runtime_checkable
class VideoWindow(Protocol):
    """The injected GUI/video driver (a ZonePlayer). Real impl = v4's
    `ui/aria_window.py`: a PyQt6 frameless always-on-top window with embedded
    libmpv. It plays a loop and owns "finishing the current loop cycle before
    switching -- no jarring cuts" (v4 "Transition Logic"). This module only
    signals WHICH loop; it never imports PyQt6/libmpv."""

    def play_loop(self, loop: ZoneLoop) -> None:
        ...


@runtime_checkable
class VisualLayerPort(Protocol):
    """The clean contract a driver (the Daemon) can drive. The Daemon defines no
    visual port today, so the contract lives here (ResLog: "expose a clean
    contract the Daemon can drive"). The Daemon's EXISTING signals map onto it:
    the output-pending boundary around `audio.speak()` -> set_speaking(True/
    False); the LLM Interface's `serving_from_local` -> set_cloud_available(...)."""

    def set_speaking(self, is_speaking: bool) -> None:
        ...

    def set_cloud_available(self, available: bool) -> None:
        ...

    def refresh(self, now: Optional[datetime] = None) -> ZoneLoop:
        ...


# ===========================================================================
# PAD -> zone mapping -- CATEGORICAL (v4 table). Pure read; no PAD write.
# ===========================================================================

def map_pad_to_zone(pad: PADSnapshot) -> Zone:
    """Select WHICH of the eight v4 zones a PAD reading falls in -- CATEGORICAL.

    For each zone we ask a boolean membership question ("does PAD satisfy this
    zone's v4 signature? -- holds or it doesn't"), NEVER "how close is PAD to
    this zone?" (a distance/percentage would be a number in disguise --
    project-rules.md percentage test). Only the v4 "+"/"-" markers are used as
    predicates; a zone's moderate descriptive values are feel-descriptors, not
    gates (TODO(F-10-zone-precedence)).

    Precedence runs most-specific / most-extreme first, with NEUTRAL_IDLE
    (~baseline) as the DEFAULT when no other signature holds. The ORDER is a
    documented, deterministic PRESENTATION placeholder for the overlaps v4's
    table does not order (e.g. a high-everything PAD satisfies Playful, Engaged
    AND Thinking) -- it never affects PAD, meaning, or memory.

    Pure function: identical PAD -> identical Zone; computing the zone reads
    (never writes) PAD.
    """
    p, a, d = pad.pleasure, pad.arousal, pad.dominance

    # Low/Tired -- low everything (v4 "P:0.4- A:0.3- D:0.4-"). Most specific of
    # the "down" zones (three markers); checked before single-marker Concerned.
    if p <= LOW_TIRED_P_MAX and a <= LOW_TIRED_A_MAX and d <= LOW_TIRED_D_MAX:
        return Zone.LOW_TIRED
    # Concerned -- low pleasure (v4 "P:0.3-").
    if p <= CONCERNED_P_MAX:
        return Zone.CONCERNED
    # Playful -- high everything (v4 "P:0.7+ A:0.6+ D:0.7+"). Most specific of
    # the "up" zones; checked before the broad Engaged band and single markers.
    if p >= PLAYFUL_P_MIN and a >= PLAYFUL_A_MIN and d >= PLAYFUL_D_MIN:
        return Zone.PLAYFUL
    # Firm -- very high dominance (v4 "D:0.8+").
    if d >= FIRM_D_MIN:
        return Zone.FIRM
    # Thinking -- high arousal (v4 "A:0.7+", "Any P", "D:0.5").
    if a >= THINKING_A_MIN:
        return Zone.THINKING
    # Engaged -- high-ish everything (v4 "P:0.6+ A:0.6+ D:0.6+").
    if p >= ENGAGED_P_MIN and a >= ENGAGED_A_MIN and d >= ENGAGED_D_MIN:
        return Zone.ENGAGED
    # Warm -- high pleasure with moderate arousal (v4 "P:0.7+", "A:0.4 D:0.5").
    # Reached only when the higher-arousal zones above did not match, i.e.
    # "high pleasure, calm" -- exactly Warm's feel.
    if p >= WARM_P_MIN:
        return Zone.WARM
    # Default: Neutral/Idle (~baseline 0.55/0.45/0.58) -- "Calm, present,
    # breathing" (v4).
    return Zone.NEUTRAL_IDLE


# ===========================================================================
# The Visual Layer.
# ===========================================================================

class VisualLayer:
    """Module 10. Reads PAD + speaking-state, selects a categorical zone, applies
    the 8-second stability gate, and drives an injected VideoWindow -- running
    independently of language generation, and NEVER writing PAD.

    Volatile working state only (the Visual Layer owns no memory; nothing here is
    persisted)."""

    def __init__(
        self,
        *,
        pad_source: PADReader,
        window: VideoWindow,
        clock: Callable[[], datetime] = _now,
        stability_seconds: float = ZONE_STABILITY_SECONDS,
    ) -> None:
        # --- injected collaborators (never instantiated here) ---
        # The ONLY inward collaborator is the read-only PAD seam; the ONLY
        # outward collaborator is the window. No Appraisal/Graph/Needs/State/
        # SoulFilter/LLM edge exists -- the structural proof of "no feeling, no
        # state write, independent of language generation".
        self._pad_source = pad_source
        self._window = window
        self._clock = clock
        self._stability_window = timedelta(seconds=stability_seconds)

        # --- volatile working state ---
        self._speaking: bool = False              # idle vs talking (v4 Speaking State)
        self._cloud_available: bool = True        # degradation trigger
        self._current_zone: Optional[Zone] = None       # PAD-zone identity (8 s gate)
        self._current_zone_since: Optional[datetime] = None  # when it last changed
        self._current_loop: Optional[ZoneLoop] = None    # what the window shows (dedup)

    # -----------------------------------------------------------------
    # Driver contract (VisualLayerPort) -- signals in, plus the loop step.
    # -----------------------------------------------------------------

    def set_speaking(self, is_speaking: bool) -> None:
        """INPUT: speaking-state (idle vs talking), from the Daemon/Audio
        Pipeline (Build Plan Module 10 Inputs). Changes ONLY the variant of the
        current zone, promptly, so the mouth tracks the voice (v4 "When Aria
        speaks, the talking variant of the current zone plays"). Does NOT change
        the zone identity and is NOT subject to the 8 s zone gate. Never writes
        PAD."""
        is_speaking = bool(is_speaking)
        if is_speaking == self._speaking:
            return
        self._speaking = is_speaking
        # Prompt variant re-render, but only if a zone is established and we are
        # not in the degradation override (during degradation she is withdrawn;
        # before the first refresh there is no zone yet).
        if self._current_zone is not None and self._cloud_available:
            self._render(ZoneLoop(self._current_zone, self._variant()))

    def set_cloud_available(self, available: bool) -> None:
        """INPUT: cloud-availability, from the Daemon / LLM Interface readout
        (`serving_from_local` / LLMUnavailableError). Unavailable -> the inward/
        waiting loop plays (v4 "Graceful degradation video state"), overriding
        PAD zones, promptly (a failure is not zone flicker -> ungated).
        Available -> resume PAD-driven zones with no announcement (v4 "Full voice
        returns naturally, no announcement"). Never writes PAD, never fabricates
        content, never talks to a model."""
        available = bool(available)
        if available == self._cloud_available:
            return
        self._cloud_available = available
        if not available:
            # Enter degradation immediately.
            self._render(ZoneLoop(Zone.INWARD_WAITING))
        else:
            # Restore: re-establish the current zone's loop immediately so full
            # presence returns without waiting for the next tick. If no zone was
            # ever established, the next refresh() establishes it.
            if self._current_zone is not None:
                self._render(ZoneLoop(self._current_zone, self._variant()))

    def refresh(self, now: Optional[datetime] = None) -> ZoneLoop:
        """One step of the independent visual loop (v4: "runs locally,
        independently, in parallel with language generation"). Reads PAD
        (presentation read), maps it to a categorical zone, applies the 8-second
        stability gate, combines with speaking-state, and drives the window.
        Returns the ZoneLoop now displayed.

        Depends ONLY on the read-only PAD seam + the window (+ the speaking/cloud
        signals). It never calls, blocks on, or references the LLM/Soul Filter/
        Appraisal -- so the face keeps living while language is generated. Never
        writes PAD."""
        now = self._as_dt(now)

        # (1) Graceful-degradation override -- prompt, PAD-independent, ungated.
        if not self._cloud_available:
            self._render(ZoneLoop(Zone.INWARD_WAITING))
            return self._current_loop  # type: ignore[return-value]

        # (2) READ current PAD (presentation read of substrate; never a write).
        pad = self._pad_source.get_current_pad()
        candidate = map_pad_to_zone(pad)

        # (3) 8-second minimum-before-switch stability gate (v4). The gate
        # governs ZONE identity only -- not the idle/talking variant.
        if self._current_zone is None:
            # First zone: display immediately (no prior zone to hold).
            self._current_zone = candidate
            self._current_zone_since = now
        elif candidate is not self._current_zone:
            elapsed = now - self._current_zone_since  # type: ignore[operator]
            if elapsed >= self._stability_window:
                # >= 8 s held -> switch and reset the timer (8.0 s boundary
                # permits the switch: the gate is >=).
                self._current_zone = candidate
                self._current_zone_since = now
            # else: < 8 s -> HOLD current zone (prevents flickering).
        # candidate is current zone -> nothing to change.

        # (4) Variant follows speaking-state; drive the window on change.
        self._render(ZoneLoop(self._current_zone, self._variant()))
        return self._current_loop  # type: ignore[return-value]

    # -----------------------------------------------------------------
    # Read-only observability (NOT a decision/write surface).
    # -----------------------------------------------------------------

    @property
    def current_zone(self) -> Optional[Zone]:
        """The PAD-zone identity currently held (None before the first refresh).
        Read-only readout for wiring/diagnostics; not a decision surface."""
        return self._current_zone

    @property
    def current_loop(self) -> Optional[ZoneLoop]:
        """The ZoneLoop the window is currently showing (None before anything is
        rendered). Read-only readout."""
        return self._current_loop

    @property
    def is_degraded(self) -> bool:
        """True while cloud is signalled unavailable (inward/waiting override)."""
        return not self._cloud_available

    # -----------------------------------------------------------------
    # Internals.
    # -----------------------------------------------------------------

    def _variant(self) -> SpeakingState:
        return SpeakingState.TALKING if self._speaking else SpeakingState.IDLE

    def _render(self, target: ZoneLoop) -> None:
        """Drive the window ONLY when the target loop differs from what it is
        already showing (Req 7.3). The window owns finishing the current loop
        cycle before switching (v4); this module only signals the target and
        de-dups identical signals -- no re-issue of the same loop every tick."""
        if target != self._current_loop:
            self._window.play_loop(target)
            self._current_loop = target

    def _as_dt(self, now: Optional[datetime]) -> datetime:
        return now if now is not None else self._clock()
