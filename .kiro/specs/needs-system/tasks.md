# Implementation Plan — Module 2: Needs System

This plan implements design.md exactly as written. Each task is small and independently
testable. Precedence: `ARIA_Resolution_Log.md` > `ARIA_Soul_Spec_v4_Addendum.md` >
`ARIA_Soul_Spec_v4.md`. Nothing here reopens a locked flag (F-2c/F-2d RESOLVED;
F-2a/F-2b are build-time placeholders). The `due`/`neglected` split is implemented as
the flagged categorical reading (satisfied/due), never a numeric cutoff (OQ-1).

- [x] 1. Module scaffold + reuse-not-redefine imports.
  - Create `daemon/needs_system.py` with module docstring citing Resolution Log
    6/7/11 and the flag disposition.
  - Import `NeedState`, `NeedStates`, `ENERGY_LOW`, `ENERGY_CRITICAL` from
    `daemon.soul_filter` (single source of truth; OQ-4). Import `MemoryGraph` from
    `daemon.graph_manager` for typing only.
  - Do NOT import `PADEngine` or any PAD mutator anywhere in the file (Req 6.1).
  - _Requirements: 1.1, 6.1, 14.2_

- [x] 2. Module constants.
  - `ENERGY_BASELINE = 100.0`, `ENERGY_MIN = 0.0`.
  - `K_LOAD`, `K_REST` as clearly-marked `TODO(build-time)` placeholders (F-2a/F-2b).
  - `EnergyBand` enum (NORMAL / LOW / CRITICAL) from the in-spec 30/20 thresholds.
  - _Requirements: 3.3, 4.3, 5.2_

- [x] 3. `_ema_step` helper (the only formula).
  - `_ema_step(current, target, k) = k*target + (1-k)*current` — the same EMA form as
    PAD, sanctioned by Resolution Log item 6. No other formula introduced.
  - _Requirements: 3.1, 4.1_

- [x] 4. `EnergyTracker.__init__` + `initialize` + validity + pre-init guard.
  - `_energy`, `_initialized`. `initialize(restored=None)` → restored (if finite,
    0..100) else `ENERGY_BASELINE`. `_require_initialized` raises `RuntimeError`.
  - _Requirements: 2.1, 2.2, 2.3_

- [x] 5. `EnergyTracker.on_soul_tick` (active-load decay, k_load).
  - One `_ema_step` toward `ENERGY_MIN` with `K_LOAD`; clamp ≥ `ENERGY_MIN`.
  - _Requirements: 3.1, 3.2, 3.4_

- [x] 6. `EnergyTracker.on_idle_recovery` (drift-to-baseline, k_rest).
  - One `_ema_step` toward `ENERGY_BASELINE` with `K_REST`; clamp ≤ `ENERGY_BASELINE`.
    Drift-to-baseline, NOT a discrete increment (Resolution Log item 6).
  - _Requirements: 4.1, 4.2, 4.4_

- [x] 7. `EnergyTracker.get_energy` + `energy_band`.
  - `get_energy()` returns the float; `energy_band()` maps via `ENERGY_LOW`/
    `ENERGY_CRITICAL`. No PAD anywhere (Req 6.2).
  - _Requirements: 5.1, 5.2, 6.2, 6.3_

- [x] 8. `NeedsEvaluator.__init__` (inject graph + self_entity_id, stateless).
  - Store only `graph` and `self_entity_id`; NO mutable need state (Req 11.2).
  - _Requirements: 8.1, 8.2, 11.2_

- [x] 9. Per-need evaluators (categorical map).
  - `evaluate_connection/growth/purpose/continuity(now)` each call the matching real
    `graph.*_evidence(now=...)` (continuity also passes `self_entity_id`) and map the
    returned `bool`: True → `SATISFIED`, else `DUE`. Never `NEGLECTED`; never a number
    (Req 7, 10, 12).
  - _Requirements: 7.1, 8.3, 8.4, 9.1, 9.2, 10.1-10.4, 12.1, 12.2, 12.4_

- [x] 10. `NeedsEvaluator.evaluate_all(now)`.
  - Return `{connection, growth, purpose, continuity}` → `NeedState`.
  - _Requirements: 7.1, 11.1_

- [x] 11. `NeedsSystem` facade (compose the two components + clock).
  - `__init__(graph, self_entity_id=None, clock=_now)` builds an `EnergyTracker` and a
    `NeedsEvaluator`. `initialize(restored_energy=None)`.
  - Delegate `on_soul_tick` / `on_idle_recovery` / `get_energy` / `energy_band`.
  - _Requirements: 1.1, 1.2, 1.3, 15.2_

- [x] 12. `NeedsSystem.get_need_states(now=None)` — the primary output.
  - `now = now or clock()`. Build `soul_filter.NeedStates(connection=…, growth=…,
    purpose=…, continuity=…, energy=self._energy.get_energy())` (Req 14.1, 14.2).
  - _Requirements: 5.4, 11.3, 13.1, 14.1, 14.2, 15.3_

- [x] 13. Tests — `tests/test_needs_system.py` (plain pytest, no hypothesis).
  - Categorical/no-number; time-driven revert via injected clock; Energy decay/refill
    substrate + bands; never-writes-PAD (structural + tripwire + real-PAD-unchanged);
    real graph_manager evidence integration (call-count spy + state flips); Soul_Filter
    `NeedStates` contract consumed unchanged.
  - _Requirements: all_

- [x] 14. Verify.
  - `python3 -m pytest tests/test_needs_system.py -q` green; then `python3 -m pytest -q`
    stays 229 + new. No modification to `graph_manager.py` / `soul_filter.py`. Temp
    files cleaned.
  - _Requirements: all_

## Notes

- **F-2a / F-2b** (`k_load` / `k_rest` values): build-time placeholders (Resolution Log
  "Open — build-time tuning constants only"). Mechanism is locked by Resolution Log
  item 6.
- **F-2c** (need→window): RESOLVED, Resolution Log item 7 — reused via Memory_Graph
  query defaults.
- **F-2d** (one module/two): RESOLVED, Resolution Log item 11 — single module, two
  components.
- **OQ-1** (due vs neglected): flagged; implemented as satisfied/due, `neglected` not
  emitted. No numeric cutoff.
