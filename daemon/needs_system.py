"""Module 2 — Needs System (Energy substrate + categorical needs evaluator).

Locked spec: see .kiro/specs/needs-system/{requirements,design,tasks}.md.

A SINGLE module (Resolution Log item 11) with two internally separated,
mutually independent components:

  * EnergyTracker  — owns Energy, the one continuous value this module may own.
    A resource/battery model on a 0..100 scale: single-rate EMA decay toward
    empty under active load (k_load), drift-to-baseline recovery toward full
    during idle (k_rest). Two constants, no valence, no asymmetry (Resolution
    Log item 6). Energy is SUBSTRATE — explicitly exempt from the
    no-invented-formula rule (that rule protects appraised *meaning*, not a
    depletion resource). It is exposed as context and NEVER writes PAD.

  * NeedsEvaluator — derives the four categorical need states (Connection,
    Growth, Purpose, Continuity) from qualifying graph evidence within each
    need's recency window, by CALLING Memory_Graph's existing evidence queries
    (never reimplementing them). Stateless: each evaluation is a pure function
    of (current time, graph contents), so a need reverts satisfied->due purely
    because evidence ages out of its window as time advances — nothing is
    actively subtracted (Addendum §3).

Flag disposition (Module 2 Build Plan entry):
  F-2a (k_load value)  : mechanism RESOLVED by Resolution Log item 6 (EMA
                         decay under load); value is a build-time placeholder.
  F-2b (k_rest value)  : mechanism RESOLVED by Resolution Log item 6
                         (drift-to-baseline recovery, NOT discrete increments);
                         value is a build-time placeholder.
  F-2c (need->window)  : RESOLVED by Resolution Log item 7 (72h/14d/14d/60d),
                         reused via Memory_Graph's query defaults.
  F-2d (one module/two): RESOLVED by Resolution Log item 11 (single module,
                         two components).

CRITICAL-CARE decision (OQ-1, design.md "The due vs neglected Decision"):
The Addendum's determination mechanism is BINARY — "whether qualifying
evidence exists in the graph within a recency window" — which is exactly what
the Memory_Graph evidence queries return (a bool). satisfied <=> evidence
in-window; the complement is `due` (the need is now due for fresh evidence).
`neglected` is NEVER emitted, because no source document gives a
percentage-free categorical basis reachable through the sanctioned evidence
queries to distinguish it from `due` (the only splitters available are a
window-elapsed fraction — forbidden by the percentage test — or a new
Memory_Graph query, which must not be added unilaterally). `neglected` stays
in the contract enum but is flagged, not invented. See OQ-1.

PAD-purity: this module imports NO PAD_Engine, holds NO PAD reference, and
calls NO PAD mutator. Energy is emitted only as a float / band; needs are
emitted only as categorical states. Any eventual PAD effect must route through
the Appraisal Chain (Stage-1 preference -> Q1-Q4 -> Stage-4 delta), outside
this module (Addendum §3; steering PAD-purity / protected chain).

Dependencies are INJECTED and their REAL interfaces are called, never
redefined (Rule 6): Memory_Graph (`daemon/graph_manager.py`). The Daemon
(Module 8) is built and tested; it calls `on_soul_tick()` /
`on_idle_recovery()` — this module is the callee, mirroring PAD_Engine
(Module 1). The output contract `NeedStates` is imported from
`daemon.types` (OQ-4 resolved); Module 2 PRODUCES that exact class so
Soul_Filter consumes it unchanged.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Dict, Optional

# --- REAL interfaces / contract (imported, never redefined) ----------------
# The NeedStates / NeedState contract and the in-spec Energy thresholds live in
# soul_filter.py; import them so Module 2 produces exactly the shape Soul_Filter
# consumes (Req 14). NO PAD_Engine import anywhere in this module (Req 6.1).
from daemon.types import (
    NeedState,
    NeedStates,
    ENERGY_LOW,       # 30.0 — v4 "below 30" cognitive-load / reasoning-degrades
    ENERGY_CRITICAL,  # 20.0 — DMN shallow-pass gate / "critically low"
)
from daemon.graph_manager import (  # typing only; injected at runtime
    MemoryGraph,
    # The locked recency windows (Resolution Log item 7 / precision-decay ladder
    # 72h / 14d / 60d). Imported rather than restated so the two-window need
    # states can never drift from the values graph_manager owns.
    WINDOW_GROWTH,
    WINDOW_CONTINUITY,
)


# ===========================================================================
# Module constants
# ===========================================================================

# Battery bounds on v4's 0..100 Energy scale (the scale the in-spec 30/20
# thresholds already live on, and the scale the NeedStates contract defaults
# to with energy=100.0). NOT invented feelings — the substrate's natural range.
ENERGY_BASELINE = 100.0  # "full battery": idle-recovery drift target (Req 2.2, 4.1)
ENERGY_MIN = 0.0         # "empty battery": active-load decay target (Req 3.1)

# --- Build-time tuning placeholders (F-2a / F-2b) --------------------------
# Resolution Log item 6 LOCKS the mechanism (single-rate EMA decay under load;
# drift-to-baseline recovery during idle; exactly two constants because Energy
# has no valence). The VALUES below are build-time tuning constants (Resolution
# Log "Open — build-time tuning constants only: k_load / k_rest"), to be set
# once Soul_Tick cadence is locked. They are NOT architectural decisions —
# exactly the pattern PAD_Engine used for PAD_HISTORY_LENGTH.
K_LOAD = 0.05  # TODO(build-time): Energy active-load EMA decay coefficient (F-2a)
K_REST = 0.03  # TODO(build-time): Energy idle-recovery EMA drift coefficient (F-2b)


class EnergyBand(Enum):
    """Categorical readout of the Energy SUBSTRATE, derived from the in-spec
    operational thresholds ONLY (Req 5.2). This is not a "need score" — it is
    the same kind of operational threshold gate as Q4 <= 0.15 for Emergency
    (Addendum §3: "the existing 'reasoning degrades below 30' rule stays as an
    operational threshold gate"). Consumers may read the raw float instead."""
    NORMAL = "normal"      # Energy >= ENERGY_LOW (30)
    LOW = "low"            # ENERGY_CRITICAL (20) <= Energy < ENERGY_LOW (30)
    CRITICAL = "critical"  # Energy < ENERGY_CRITICAL (20)


def _now() -> datetime:
    """Aware-UTC clock, matching graph_manager._now()'s convention so ISO
    timestamps compare consistently with graph rows."""
    return datetime.now(timezone.utc)


def _ema_step(current: float, target: float, k: float) -> float:
    """The one and only formula in this module: the standard EMA blend
    new = k*target + (1-k)*current — the SAME EMA-style math already locked for
    PAD (Addendum §3; Resolution Log item 6), applied per-tick (discrete, no
    wall-clock dt) exactly as PAD_Engine applies its decay per Soul_Tick. No
    other formula is introduced. Sanctioned because Energy is a battery
    resource, not appraised meaning (Resolution Log item 6)."""
    return k * target + (1.0 - k) * current


# ===========================================================================
# Component 1 — EnergyTracker (SANCTIONED SUBSTRATE; never writes PAD)
# ===========================================================================

class EnergyTracker:
    """Owns the single live Energy value. Holds NO PAD reference (Req 6.1) —
    there is no line here that could reach a PAD mutator, so "Energy never
    writes PAD" is guaranteed structurally, not just by convention (mirrors
    Addendum §5's F4 zero-PAD-path decision)."""

    def __init__(self) -> None:
        self._energy: Optional[float] = None
        self._initialized: bool = False

    def initialize(self, restored: Optional[float] = None) -> None:
        """Set Energy from a valid restored value, else ENERGY_BASELINE
        (Req 2.2, 2.3). The State_Manager (Module 11) -> float conversion
        happens at the wiring call site, not here (mirrors PAD_Engine's
        restore boundary)."""
        if restored is None or not self._is_valid_energy(restored):
            self._energy = ENERGY_BASELINE
        else:
            self._energy = float(restored)
        self._initialized = True

    @staticmethod
    def _is_valid_energy(value) -> bool:
        """Finite numeric within [ENERGY_MIN, ENERGY_BASELINE]. Anything else
        falls back to baseline (Req 2.2)."""
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        if value != value:  # NaN, without importing math
            return False
        if value in (float("inf"), float("-inf")):
            return False
        return ENERGY_MIN <= value <= ENERGY_BASELINE

    def _require_initialized(self) -> None:
        if not self._initialized:
            raise RuntimeError(
                "EnergyTracker method called before initialize(). "
                "initialize() must be called before on_soul_tick(), "
                "on_idle_recovery(), get_energy(), or energy_band()."
            )

    def on_soul_tick(self) -> None:
        """Daemon Soul_Tick under active load: one EMA decay step toward
        ENERGY_MIN using k_load (Req 3). Single coefficient — no valence, no
        asymmetry (Resolution Log item 6). Clamped so it never overshoots below
        empty (Req 3.4)."""
        self._require_initialized()
        stepped = _ema_step(self._energy, ENERGY_MIN, K_LOAD)
        self._energy = max(ENERGY_MIN, stepped)

    def on_idle_recovery(self) -> None:
        """Daemon idle "Energy refill signal": one EMA drift step toward
        ENERGY_BASELINE using k_rest (Req 4). This is drift-to-baseline
        recovery (Resolution Log item 6), NOT a discrete increment. Clamped so
        it never overshoots above full (Req 4.4)."""
        self._require_initialized()
        stepped = _ema_step(self._energy, ENERGY_BASELINE, K_REST)
        self._energy = min(ENERGY_BASELINE, stepped)

    def get_energy(self) -> float:
        """Current Energy (Req 5.1). This is the value carried into
        NeedStates.energy; consumers apply their own thresholds
        (e.g. Soul_Filter's `energy < ENERGY_LOW`)."""
        self._require_initialized()
        return self._energy

    def energy_band(self) -> EnergyBand:
        """Categorical band from the in-spec 30/20 thresholds (Req 5.2). Pure
        substrate readout — never feeds a PAD computation (Req 6.2, 6.3)."""
        e = self.get_energy()
        if e < ENERGY_CRITICAL:
            return EnergyBand.CRITICAL
        if e < ENERGY_LOW:
            return EnergyBand.LOW
        return EnergyBand.NORMAL


# ===========================================================================
# Component 2 — NeedsEvaluator (STRICTLY CATEGORICAL; no numeric score ever)
# ===========================================================================

class NeedsEvaluator:
    """Derives the four categorical need states from Memory_Graph evidence.

    STATELESS with respect to need states (Req 11.2): stores only its injected
    dependencies, never a mutable need value. Each evaluate_* call recomputes
    from (now, graph). A need reverts satisfied->due purely because evidence
    ages out of its window as `now` advances — nothing is subtracted.

    The categorical rule (Req 12) is TWO WINDOWS over the SAME evidence query:
        near = graph.<need>_evidence(now=now)                   # its own window
        far  = graph.<need>_evidence(now=now, window=<next rung>)
        state = SATISFIED if near else DUE if far else NEGLECTED

    This is Addendum §3's own shape, taken from the one need it defines fully:
    Continuity is "neglected when updates have gapped for a long stretch". A
    "long stretch" is a wider window, not a counter — §3 rules a counter out in
    the same breath ("the state reverts on its own; nothing actively subtracts
    anything ... not a running clock"). Both windows are already-locked values
    from the 72h/14d/60d ladder (Resolution Log item 7 assigns the near ones;
    the far one is the next rung up), so no window and no number is introduced.

    Continuity remains TWO-valued — see evaluate_continuity. No number is ever
    produced (Req 7)."""

    def __init__(
        self, graph: MemoryGraph, self_entity_id: Optional[str] = None
    ) -> None:
        # REAL Memory_Graph interface, injected (Rule 6) — never re-created.
        self._graph = graph
        # Self-referential EntityNode id for continuity_evidence (OQ-2).
        # May be None -> Continuity reports `due` (no narrative to find).
        self._self_entity_id = self_entity_id

    @staticmethod
    def _state(evidence_present: bool, evidence_in_long_window: bool) -> NeedState:
        """Three categorical states from two evidence facts (Addendum §3).

        Pure function of (now, graph). No counter, no clock, no number: each
        input is a graph yes/no, and the output is one of three categories with
        nothing in between — no numeric fraction, no window-elapsed measure, no
        'due = >50%' (Req 12.3). The state reverts on its own as `now` advances
        because both facts are recomputed from the graph every call; nothing is
        stored and nothing is subtracted."""
        if evidence_present:
            return NeedState.SATISFIED
        if evidence_in_long_window:
            return NeedState.DUE
        return NeedState.NEGLECTED

    def evaluate_connection(self, now: datetime) -> NeedState:
        """Connection = Relatedness: an interaction the appraisal chain already
        scored Q1 medium-or-above (Addendum §3; Resolution Log item 7). Calls
        the REAL graph query (Req 8.1, 8.2, 10.1) TWICE — same query, two
        already-locked windows: satisfied within 72h, neglected once nothing
        qualifies within 14d (the next rung up the ladder)."""
        return self._state(
            self._graph.connection_evidence(now=now),
            self._graph.connection_evidence(now=now, window=WINDOW_GROWTH),
        )

    def evaluate_growth(self, now: datetime) -> NeedState:
        """Growth = Competence: an UncertaintyNode actually resolved
        (confirmed/inferred, not abandoned) (Addendum §3; Resolution Log
        item 7). Satisfied within 14d; neglected once nothing qualifies within
        60d (the next rung up). (Req 10.2)"""
        return self._state(
            self._graph.growth_evidence(now=now),
            self._graph.growth_evidence(now=now, window=WINDOW_CONTINUITY),
        )

    def evaluate_purpose(self, now: datetime) -> NeedState:
        """Purpose = Beneficence: user follow-through / explicit positive
        feedback (Addendum §3; Resolution Log item 7). Satisfied within 14d;
        neglected once nothing qualifies within 60d (the next rung up).

        Addendum §3 flags this as the WEAKEST, lowest-confidence signal of the
        four, and that remains true — outcome visibility is genuinely limited
        in-session.

        OQ6 RESOLVED 2026-08-26 (Resolution Log item 36a), so the stale note that
        used to sit here is gone: `purpose_evidence` is no longer a stand-in with
        a `TODO(OQ6-M2)`. It now implements §3's two named signals as an OR —
        explicit positive feedback about HER (`q2=positive` AND `q3=self`) or
        follow-through (an in-window node sharing an `entity_ref` with an earlier
        node from a DIFFERENT session at `q1` medium/high). Module 2 still calls
        it as-is and still does not define what follow-through means; the
        definition lives in Module 3 where the query does.

        The residual weakness §3 names propagates to a NEGLECTED verdict as well
        as a DUE one — flagged, not resolved here. (Req 10.3)"""
        return self._state(
            self._graph.purpose_evidence(now=now),
            self._graph.purpose_evidence(now=now, window=WINDOW_CONTINUITY),
        )

    def evaluate_continuity(self, now: datetime) -> NeedState:
        """Continuity = narrative coherence: the self-continuity narrative
        extended (relationship_summary updated) on the self-referential
        EntityNode within 60d (Addendum §3; Resolution Log item 7). If no self
        entity id is available, there is no narrative to find -> `due` (OQ-2).
        (Req 10.4)

        DELIBERATELY TWO-VALUED — the only need of the four that cannot use the
        two-window rule. Addendum §3 gives Continuity a QUALITY criterion, not
        just a longer gap: "neglected when updates have gapped for a long
        stretch, or new evidence CONTRADICTS rather than extends it". Its own
        window is already 60d, the top rung of the locked 72h/14d/60d ladder, so
        there is no wider window to step up to without inventing one.

        TODO(Addendum §3): Continuity NEGLECTED needs a "contradicts rather than
        extends" signal. The graph has adjacent machinery (GRAPH_CONFLICT /
        reality_contradiction_check) but wiring either to the narrative-update
        path is a mechanism this module does not have and must not invent
        (Rule 1). Until then Continuity reports satisfied/due only."""
        if self._self_entity_id is None:
            return NeedState.DUE
        evidence = self._graph.continuity_evidence(self._self_entity_id, now=now)
        return NeedState.SATISFIED if evidence else NeedState.DUE

    def evaluate_all(self, now: datetime) -> Dict[str, NeedState]:
        """All four need states as of `now` (Req 10, 11.1). A single `now` is
        used for all four so the snapshot is consistent."""
        return {
            "connection": self.evaluate_connection(now),
            "growth": self.evaluate_growth(now),
            "purpose": self.evaluate_purpose(now),
            "continuity": self.evaluate_continuity(now),
        }
    def set_self_entity_id(self, entity_id: Optional[str]) -> None:
        """Set the self-referential EntityNode id for Continuity evaluation.
        Called by the Daemon after startup() discovers or creates the self node."""
        self._self_entity_id = entity_id


# ===========================================================================
# The single module facade — composes the two independent components
# ===========================================================================

class NeedsSystem:
    """Module 2 facade (Resolution Log item 11: single module). Composes one
    EnergyTracker and one NeedsEvaluator — two independent components (Req 1).
    The Daemon (Module 8) and the consumers talk to this facade.

    NO PAD reference, NO PAD parameter, NO PAD mutator call anywhere (Req 6,
    13). Needs influence appraisal only INDIRECTLY, as a Stage-1 retrieval
    preference downstream; Energy is exposed only as context."""

    def __init__(
        self,
        graph: MemoryGraph,
        self_entity_id: Optional[str] = None,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._energy = EnergyTracker()
        self._needs = NeedsEvaluator(graph, self_entity_id)
        # Injected clock (Req 11.3): get_need_states(now=None) defaults from it,
        # so production needs no explicit time while tests drive a controlled
        # clock to exercise the time-driven revert. Mirrors graph_manager's
        # now=None -> _now() pattern.
        self._clock = clock

    # -- Energy (substrate) delegation --------------------------------------
    def initialize(self, restored_energy: Optional[float] = None) -> None:
        """Initialize the Energy substrate (Req 2). The categorical needs
        component is stateless and needs no initialization."""
        self._energy.initialize(restored_energy)

    def on_soul_tick(self) -> None:
        """Daemon Soul_Tick (active-load Energy decay) — Req 15.2."""
        self._energy.on_soul_tick()

    def on_idle_recovery(self) -> None:
        """Daemon idle Energy-refill signal (drift-to-baseline) — Req 15.2."""
        self._energy.on_idle_recovery()

    def get_energy(self) -> float:
        return self._energy.get_energy()

    def energy_band(self) -> EnergyBand:
        return self._energy.energy_band()

    def set_self_entity_id(self, entity_id: Optional[str]) -> None:
        self._needs.set_self_entity_id(entity_id)   

    @property
    def self_entity_id(self) -> Optional[str]:
        """Read-only access to the self-referential EntityNode id for testing
        and inspection. Mutation only via set_self_entity_id()."""
        return self._needs._self_entity_id

    # -- Combined output ----------------------------------------------------
    def get_need_states(self, now: Optional[datetime] = None) -> NeedStates:
        """THE primary output (Req 14): the exact soul_filter.NeedStates shape —
        four categorical NeedState fields + the continuous Energy float — so
        Soul_Filter consumes it unchanged. `now` defaults from the injected
        clock (Req 11.3). The four needs carry NO numeric score; Energy is the
        only number, and it is substrate context (Req 7, 13)."""
        energy = self._energy.get_energy()  # raises if not initialized (guard)
        now = now if now is not None else self._clock()
        states = self._needs.evaluate_all(now)
        return NeedStates(
            connection=states["connection"],
            growth=states["growth"],
            purpose=states["purpose"],
            continuity=states["continuity"],
            energy=energy,
        )
