# Design Document — Module 2: Needs System

> ## AMENDMENT 2026-08-20 — OQ-1 CLOSED, `neglected` now emitted
>
> Everything below stating that `NEGLECTED` is **never emitted** is
> **SUPERSEDED** for Connection / Growth / Purpose. It remains accurate for
> Continuity only.
>
> **Mechanism: two windows over the SAME evidence query.** `_state` is now
> 3-valued — `satisfied` if evidence in the need's own window, else `due` if in
> the next rung up the locked ladder, else `neglected`:
>
> | Need | satisfied within | neglected when nothing within |
> |---|---|---|
> | Connection | 72h | 14d (`WINDOW_GROWTH`) |
> | Growth | 14d | 60d (`WINDOW_CONTINUITY`) |
> | Purpose | 14d | 60d (`WINDOW_CONTINUITY`) |
> | Continuity | 60d | *(two-valued — see below)* |
>
> This is Addendum §3's own shape, taken from the one need it defines fully:
> Continuity is *"neglected when updates have gapped for a long stretch"* — a long
> stretch is a **wider window**, not a counter. A counter was explicitly REJECTED:
> §3 rules it out in the same paragraph that establishes the three states — *"the
> state reverts on its own; nothing actively subtracts anything … **not a running
> clock**"*.
>
> No window, constant, counter or storage is introduced: both windows are
> already-locked ladder values (ResLog item 7 assigns the near ones; the far one is
> the next rung), and `graph_manager` needed no change because all four
> `*_evidence` methods already accept `window`. State stays a **pure function of
> (now, graph)** and `NeedsEvaluator` stays stateless (Req 11.2).
>
> **Continuity stays two-valued**, deliberately. 60d is already the TOP rung of the
> locked 72h/14d/60d ladder, so there is no wider window to step to without
> inventing one; and §3 gives Continuity a QUALITY criterion rather than a gap
> (*"or new evidence contradicts rather than extends it"*), which needs a signal
> that is not wired to the narrative-update path. `TODO(Addendum §3)` in
> `evaluate_continuity`; not invented (Rule 1).
>
> **Known consequence:** an empty graph has no evidence in either window, so a
> brand-new install reports Connection/Growth/Purpose as `neglected`, not `due`. It
> is what §3's rule yields, and it self-corrects on the first qualifying turn.
> Flagged rather than special-cased.

## Overview

Needs_System is a single module (Resolution Log item 11) with two internally separated,
mutually independent components:

- **Energy_Tracker** — owns the one continuous value this module is permitted to own,
  Energy. A resource / battery model on a 0–100 scale: single-rate EMA decay toward
  empty under active load (`k_load`), drift-to-baseline recovery toward full during idle
  (`k_rest`) — two constants, no valence, no asymmetry (Resolution Log item 6). Energy
  is SUBSTRATE, explicitly exempt from the no-invented-formula rule; it is exposed as
  context and NEVER writes PAD.
- **Needs_Evaluator** — derives the four categorical need states (Connection, Growth,
  Purpose, Continuity) as `satisfied` / `due` from qualifying graph evidence within each
  need's recency window, by calling Memory_Graph's existing evidence queries. It is
  stateless: each evaluation is a pure function of (current time, graph contents), so a
  need reverts satisfied→due purely because evidence aged out of its window as time
  advances — nothing is actively subtracted (Addendum §3).

The module combines both into the `NeedStates` contract (`daemon/soul_filter.py`) so
Soul_Filter (Module 5) consumes the output unchanged.

This design implements requirements.md as written, using only mechanisms already
specified there or in the supporting documents (`ARIA_Soul_Spec_v4.md`,
`ARIA_Soul_Spec_v4_Addendum.md`, `ARIA_Resolution_Log.md`, the Module 2 Build Plan
entry, `daemon/graph_manager.py`, `daemon/soul_filter.py`). No new mechanism, formula,
or window is introduced. The one genuine gap — the `due` vs `neglected` categorical
split — is carried forward as a flagged decision (OQ-1), not resolved by invention.

## Hard Constraints (carried from requirements.md, non-negotiable)

1. **Energy is the only number.** The four needs carry NO numeric score, percentage,
   0–100 value, "pressure", or "level" — anywhere, ever (Req 7). Energy is the sole
   sanctioned numeric (steering "No invented numbers").
2. **Energy never writes PAD.** Needs_System holds no PAD_Engine reference and calls no
   PAD mutator (Req 6). Energy is exposed as context only.
3. **Needs never pull PAD.** No path from a need state to a PAD change (Req 13; Addendum
   §3 "Stage 5 redefined").
4. **The `due`/`neglected` split is never a disguised percentage.** No "% of window
   elapsed", no "time since evidence" cutoff, no "due = >50%" (Req 12; steering
   percentage test).
5. **Evidence queries are called, not reimplemented.** Memory_Graph owns "does evidence
   exist"; Needs_System owns "what it means for the state" (Req 8.2).
6. **Windows are reused, not reinvented.** 72h/14d/14d/60d come from Resolution Log
   item 7, owned by Memory_Graph's query defaults (Req 9).
7. **k_load / k_rest are build-time placeholders**, clearly marked `TODO(build-time)`
   (F-2a / F-2b; Req 3.3, 4.3).
8. **Single module, two independent components** (Req 1; Resolution Log item 11).
9. **soul_filter.py and graph_manager.py are not modified** (Req 14.3).

## Architecture

```
                     ┌───────────────────────────────────────────────┐
                     │                 Needs_System                    │
                     │  (single module — Resolution Log item 11)       │
                     │                                                 │
  Daemon ───────────▶│  on_soul_tick()        ┌───────────────────┐   │
  (Soul_Tick,        │  on_idle_recovery() ──▶ │  Energy_Tracker   │   │
   active load)      │                         │  Energy: float    │   │
  Daemon ───────────▶│                         │  0..100 (SUBSTRATE)│  │
  (Idle_Recovery)    │                         │  EMA k_load/k_rest│   │
                     │                         │  NO PAD reference │   │
                     │                         └─────────┬─────────┘   │
                     │                                   │ energy      │
                     │  get_need_states(now) ┐           ▼             │
  Memory_Graph ─────▶│   ┌──────────────────┴──┐   ┌──────────────┐   │
  connection_evidence│   │  Needs_Evaluator     │   │  NeedStates  │   │
  growth_evidence    │◀──┤  (stateless)         │──▶│ connection   │   │
  purpose_evidence   │   │  satisfied ⇔ evidence │   │ growth       │   │
  continuity_evidence│   │  in-window; else due │   │ purpose      │   │
  (each → bool)      │   │  NEVER a number      │   │ continuity   │   │
                     │   └──────────────────────┘   │ energy:float │   │
                     │                               └──────┬───────┘   │
                     └──────────────────────────────────────┼──────────┘
                                                            │
                    ┌───────────────────────┬───────────────┼───────────────┐
                    ▼                        ▼               ▼               ▼
             Appraisal_Chain           Soul_Filter        Soul_Filter      Daemon
             Stage 1 (retrieval        (Constraints:      (This Moment /   (initiative)
             PREFERENCE from            energy <30/<20)    context from
             due/neglected needs)                          need states)
                    │                                                    │
                    │  NEEDS influence appraisal INDIRECTLY (preference) │
                    │  — never a pull on PAD. NO ARROW TO PAD_Engine.    │
                    └────────────────────────────────────────────────────┘

  PAD_Engine (Module 1): NOT connected to Needs_System. No inbound arrow.
  Energy is context; needs are preference. Neither writes PAD.
```

## Components and Interfaces

### `EnergyTracker` (class) — the substrate component

Owns the single live Energy value. In-process, synchronous. Holds no PAD reference.

**State held:**
- `_energy: float` — current Energy, 0..100. Unset until `initialize()` (mirrors
  PAD_Engine's initialize-before-use discipline).
- `_initialized: bool` — sentinel for the pre-initialize guard.

**Methods:**
- `initialize(restored: Optional[float] = None)` — set Energy from `restored` (if a
  valid finite 0..100 value) else Energy_Baseline (100.0) (Req 2.2, 2.3). The
  State_Manager conversion happens at the call site, not here (mirrors PAD_Engine).
- `on_soul_tick()` — one active-load EMA step toward Energy_Min via `k_load`
  (Req 3). Clamped not to overshoot below Energy_Min.
- `on_idle_recovery()` — one idle EMA step toward Energy_Baseline via `k_rest`
  (Req 4). Clamped not to overshoot above Energy_Baseline. This is the Build Plan's
  "Energy refill signal — from Daemon (idle)", resolved to drift-to-baseline
  (Resolution Log item 6), not a discrete increment.
- `get_energy() -> float` — current Energy (Req 5.1).
- `energy_band() -> EnergyBand` — categorical NORMAL / LOW / CRITICAL from the in-spec
  thresholds (Req 5.2).

**The EMA step (the only formula; sanctioned by Resolution Log item 6):**
```
_ema_step(current, target, k)  =  k * target + (1 - k) * current
```
- Active load: `target = ENERGY_MIN (0.0)`, `k = k_load` → Energy falls toward empty.
- Idle:        `target = ENERGY_BASELINE (100.0)`, `k = k_rest` → Energy drifts to full.

This is the identical EMA form PAD_Engine uses (`k * baseline + (1-k) * current`),
per Addendum §3 ("the same EMA-style math already locked for PAD") and Resolution Log
item 6. Two constants total (`k_load`, `k_rest`); no positive/negative asymmetry because
Energy has no valence (Resolution Log item 6: "Two constants, not four"). Applied
per-tick (discrete), exactly as PAD_Engine applies its decay per Soul_Tick — no
wall-clock `dt` is used, so no time-integration formula is invented.

**Why `EnergyTracker` has no PAD reference (Req 6):** the strongest guarantee that
Energy never writes PAD is structural absence — the class cannot import, hold, or call
PAD_Engine, so there is no path to `apply_appraisal_delta`. Energy is emitted only as a
float / band for other modules to read. (This mirrors Addendum §5's F4 decision: a
mechanism with no PAD path, by construction.)

### `NeedsEvaluator` (class) — the categorical component

Derives the four need states from Memory_Graph evidence. **Stateless** with respect to
need states (Req 11.2): it stores only its injected dependencies (the graph and the
self-entity id), never a mutable need value. Every call recomputes from scratch.

**Injected dependencies:**
- `graph: MemoryGraph` — the real Module 3 interface (Rule 6). Never re-created here.
- `self_entity_id: Optional[str]` — the self-referential EntityNode id for
  `continuity_evidence` (OQ-2). May be `None` (then Continuity is `due` — no narrative
  to find).

**Methods:**
- `evaluate_connection(now) -> NeedState`
- `evaluate_growth(now) -> NeedState`
- `evaluate_purpose(now) -> NeedState`
- `evaluate_continuity(now) -> NeedState`
- `evaluate_all(now) -> Dict[str, NeedState]`

**The categorical rule (identical shape for all four — the heart of Req 12):**
```
evidence_present = graph.<need>_evidence(now=now[, self_entity_id])   # a bool
state = NeedState.SATISFIED if evidence_present else NeedState.DUE
```
- `SATISFIED` ⇔ qualifying evidence exists within the window (the bool is True). A real
  category — "there either is qualifying evidence in the window or there isn't" — passes
  the percentage test.
- non-satisfied ⇒ `DUE` — the direct categorical complement ("evidence aged out; the
  need is now due"). No second signal, no numeric fraction, no window-elapsed measure.
- `NEGLECTED` is **emitted as of 2026-08-20** for Connection / Growth / Purpose,
  via the two-window model (satisfied if evidence in the need's own window, else
  due if in the next rung up the locked ladder, else neglected). Still never
  emitted for Continuity: 60d is the top rung, and Addendum §3 gives it a quality
  criterion ("contradicts rather than extends") with no signal wired. The OQ-1
  decision section below is superseded on this point, kept for provenance.

`now` is passed straight through to the Memory_Graph query, which applies its own locked
window default (`WINDOW_CONNECTION`/etc.). The evaluator introduces no window constant of
its own (Req 9.2).

### `NeedsSystem` (class) — the single module facade

Composes one `EnergyTracker` and one `NeedsEvaluator` (Req 1). The Daemon and consumers
talk to this facade.

**Methods:**
- `initialize(restored_energy=None)` — delegates to `EnergyTracker.initialize`.
- `on_soul_tick()` / `on_idle_recovery()` — delegate to `EnergyTracker` (Req 15.2). The
  Daemon (Module 8) calls these; Needs_System is the callee (mirrors PAD_Engine). The
  Daemon owns the active-load-vs-idle decision (its F-8b attentional policy) — this
  module does not detect load itself.
- `get_energy() -> float`, `energy_band() -> EnergyBand` — Energy read surface (Req 5).
- `get_need_states(now=None) -> NeedStates` — **the primary output**. Builds the exact
  `soul_filter.NeedStates` with the four evaluated `NeedState`s + current Energy (Req 14).
  `now` defaults from an injected clock (`clock` callable, default UTC now) so production
  needs no explicit time while tests inject a controlled clock (Req 11.3).

**Clock injection.** `NeedsSystem(clock=...)` accepts a `Callable[[], datetime]`
(default: aware-UTC now). `get_need_states(now=None)` uses the explicit `now` if given,
else `clock()`. This is the injected-clock seam that makes the time-driven revert
(Req 11) testable, and mirrors Memory_Graph's own `now=None → _now()` pattern.

## Data Types

```python
class EnergyBand(Enum):          # categorical readout of the substrate (Req 5.2)
    NORMAL = "normal"            # Energy >= 30
    LOW = "low"                  # 20 <= Energy < 30   (v4 "below 30" cognitive-load)
    CRITICAL = "critical"        # Energy < 20         (DMN shallow-pass gate)
```

Reused from `daemon/soul_filter.py` (imported, not redefined — single source of truth):
- `NeedState` (satisfied / due / neglected) — the categorical need enum.
- `NeedStates` — the output contract (four `NeedState` + `energy: float`).
- `ENERGY_LOW = 30.0`, `ENERGY_CRITICAL = 20.0` — the in-spec operational thresholds.

Module-local constants:
- `ENERGY_BASELINE = 100.0` (full battery / idle target; = `NeedStates` default).
- `ENERGY_MIN = 0.0` (empty battery / load target).
- `K_LOAD`, `K_REST` — build-time placeholders, `TODO(build-time)` (F-2a / F-2b).

## The `due` vs `neglected` Decision (OQ-1) — full rationale

This is the module's designated CRITICAL-CARE point. The reasoning, in full, so the
architect can audit it:

1. **What the governing doc actually says.** Addendum §3: the four needs are
   `satisfied / due / neglected`, and each state is "determined by whether qualifying
   evidence exists in the graph within a recency window ... When evidence ages out of its
   window, the state reverts on its own." The *determination mechanism it specifies* is
   binary: evidence-in-window vs not. That is exactly the shape of the Memory_Graph
   evidence queries — each returns a single `bool`.

2. **What that yields, honestly.** A binary fact yields two categories. Mapping is
   forced: `satisfied` = evidence present (True). The complement is one category, most
   naturally named `due` ("it's now due for fresh evidence") — matching the Addendum's
   "reverts on its own" framing.

3. **Why not a third category from the same data.** To split the complement into `due`
   vs `neglected` from the evidence booleans alone, one would need a *second* signal. The
   only signal the window gives is "how long since evidence" — a duration, i.e. a
   percentage of the window elapsed. That is exactly the "number in disguise" the
   percentage test and this module's CRITICAL-CARE constraint forbid ("Never implement
   'due = >50% window elapsed'"). Rejected.

4. **The one categorical `neglected` fact the docs mention.** Only Continuity gets a
   distinct categorical hint: "neglected when ... new evidence contradicts rather than
   extends it." This is a real category (contradiction is a yes/no fact, not a fraction).
   But it is **not reachable** through `continuity_evidence`, which returns only "was the
   narrative extended within 60d (bool)". Surfacing a contradiction fact would require a
   new Memory_Graph query — which Req 14.3 forbids adding unilaterally, and which Rule 1
   forbids inventing. So even here, `neglected` cannot be produced without either a
   forbidden numeric cutoff or a forbidden contract change.

5. **Decision.** Implement the most defensible categorical reading: `satisfied` ⇔
   evidence in-window; else `due`. Preserve `neglected` in the contract enum (Soul_Filter
   still imports it) but **do not emit it**. Flag the split as OQ-1 for the architect,
   with two concrete, percentage-free options offered (Continuity contradiction fact;
   Growth "abandoned-in-window with none resolved" fact) — both of which would require a
   Memory_Graph query the architect must approve.

6. **Why this is safe / lossless downstream.** The single documented consumer of the
   categorical states is the Stage-1 retrieval PREFERENCE (Addendum §3): it surfaces
   preferred edges when a need is "due or neglected" — it treats the two identically, so
   collapsing loses no retrieval behavior. Soul_Filter reads only `NeedStates.energy`
   (verified in `daemon/soul_filter.py`: `_derive_constraints` uses
   `need_states.energy < ENERGY_LOW`; it does not branch on the four categorical fields).
   So emitting `due` instead of `neglected` changes no current behavior while keeping the
   module honest about the gap.

## PAD-purity: how "never writes PAD" and "needs never pull PAD" are guaranteed

- **Structural (Req 6.1):** `needs_system.py` does not import `PADEngine` and no
  Needs_System class holds a PAD reference or has a PAD parameter. There is no line that
  could call `apply_appraisal_delta` or any PAD mutator. Verified by a source scan and a
  signature scan in the tests.
- **Functional tripwire (Req 6, Req 13):** the tests monkeypatch
  `PADEngine.apply_appraisal_delta` to raise, then exercise the full Needs_System cycle
  (tick, recovery, evaluate) and assert it never fires; and they run the cycle beside a
  real, initialized PAD_Engine and assert its PAD is byte-identical before and after
  (Needs_System cannot touch what it cannot reach).
- **Semantic (Req 13):** Needs_System performs no appraisal and emits only categorical
  states + an Energy number. Any eventual PAD effect must route through Appraisal_Chain
  (Stage-1 preference → Q1–Q4 → Stage-4 PAD delta), which is outside this module.

## Error Handling

- **Pre-initialize guard.** `on_soul_tick` / `on_idle_recovery` / `get_energy` /
  `energy_band` / `get_need_states` raise `RuntimeError` if called before `initialize()`
  (mirrors PAD_Engine's `_require_initialized`). Prevents reading an unset Energy.
- **Invalid restored Energy.** Non-finite, non-numeric, or out-of-[0,100] restored values
  fall back to Energy_Baseline (Req 2.2 fallback), mirroring PAD_Engine's
  `_is_valid_snapshot`.
- **Missing self node.** If `self_entity_id` is `None` or absent from the graph,
  `continuity_evidence` returns False → Continuity is `due` (OQ-2). No crash.
- **Graph query is authoritative.** Needs_Evaluator never second-guesses a query result;
  a `bool` is mapped directly to a category. No numeric post-processing.

## Testing Strategy

Plain `pytest`, no `hypothesis` (matches Modules 1/3/5 style). Proves:
1. **Categorical, no number:** each need field on the produced `NeedStates` is a
   `NeedState`; no numeric per-need field/attribute/method exists; the only numeric is
   `energy`. (Req 7)
2. **Time-driven revert:** with a REAL Memory_Graph, one piece of evidence created at T0;
   a need is `satisfied` at `now = T0 + (window - ε)` and `due` at
   `now = T0 + (window + ε)` — flip caused purely by advancing the injected clock,
   nothing subtracted, graph unchanged. (Req 11)
3. **Energy substrate:** decays monotonically toward Energy_Min under repeated
   `on_soul_tick`, recovers monotonically toward Energy_Baseline under repeated
   `on_idle_recovery`, never overshoots either bound; bands map at 30/20. (Req 3, 4, 5)
4. **Never writes PAD:** structural (no PAD import / no PAD param) + tripwire
   (monkeypatched mutator never fires) + real-PAD-unchanged. (Req 6, 13)
5. **Real integration:** the evaluator calls the real `*_evidence` methods (call-count
   spy proves delegation, not reimplementation); qualifying evidence for each of the four
   needs (built via the real graph write methods) flips its state satisfied↔due. (Req 8)
6. **Soul_Filter contract:** the produced value is a real `soul_filter.NeedStates`, and
   passing it through the real `SoulFilter._derive_constraints` / `assemble_instruction`
   yields the energy-gated "do not overextend" constraint iff Energy < 30 — consumed
   unchanged. (Req 14)

## Open Questions

See requirements.md Open Questions. Summary: **OQ-1** due-vs-neglected categorical basis
(implemented as satisfied/due, `neglected` flagged and not emitted); **OQ-2** self-entity
id provisioning (injected); **OQ-3** Purpose weakest signal + Memory_Graph
`purpose_evidence` placeholder (`TODO(OQ6-M2)`); **OQ-4** contract location (imported from
`soul_filter.py`, ideally relocated). None are resolved by invention. **k_load / k_rest**
are build-time placeholders (F-2a / F-2b), not architectural gaps.
