# Tasks — Module 10: Visual Layer

This plan implements design.md exactly as written. Each task is small and independently
testable. Precedence: `ARIA_Resolution_Log.md` > `ARIA_Soul_Spec_v4_Addendum.md` >
`ARIA_Soul_Spec_v4.md`. Nothing reopens a locked item (F-10a RESOLVED by ResLog item 15).
Genuinely-undefined values are `TODO(F-10-zone-precedence)` placeholders, never invented. No
other core module is modified (the Daemon is UNCHANGED; the Visual Layer EXPOSES the contract
the Daemon can drive).

- [x] 1. Module scaffold + minimal, read-only imports.
  - Create `daemon/visual_layer.py` with a docstring citing the eight constraints, v4
    "Representation Layer — Video Avatar" (zone table / transition logic / speaking state /
    graceful degradation), the v4 constants table (8 s stability), ResLog item 15 (F-10a
    RESOLVED), and the Build Plan Module 10 entry.
  - Import ONLY `PADSnapshot` (read-only type) from `daemon.pad_engine`; import NO
    write-capable module (graph/appraisal/needs/state/daemon/soul_filter/llm_interface) and NO
    GUI toolkit (PyQt6/mpv). No import cycle.
  - _Requirements: 1.1, 2.4, 7.2, 8.1_

- [x] 2. Constants — v4-CITED vs FLAGGED placeholders.
  - CITED: `ZONE_STABILITY_SECONDS = 8` (v4 constants table); per-zone boundaries
    `LOW_TIRED_*`, `CONCERNED_P_MAX`, `PLAYFUL_*`, `FIRM_D_MIN`, `THINKING_A_MIN`, `ENGAGED_*`,
    `WARM_P_MIN` (v4 "PAD → Video Zone Mapping" table markers).
  - FLAGGED: the zone-precedence ORDER + descriptive-vs-gate reading as
    `TODO(F-10-zone-precedence)`.
  - _Requirements: 3.4, 3.5, 5.5, 10.1, 10.2_

- [x] 3. Value types.
  - `Zone` enum (8 v4 zones + `INWARD_WAITING`); `SpeakingState` enum (`IDLE`/`TALKING`);
    `ZoneLoop` frozen (`zone`, `variant`, `loop_id` property; `INWARD_WAITING` normalizes
    variant to `IDLE`).
  - _Requirements: 3.1, 4.1, 6.2_

- [x] 4. Injected Protocols (hot-swappable; no GUI hardcoded) + driver contract.
  - `PADReader` (`get_current_pad` ONLY — read-only seam), `VideoWindow` (`play_loop`), both
    `runtime_checkable`. `VisualLayerPort` (`set_speaking`/`set_cloud_available`/`refresh`),
    `runtime_checkable`.
  - _Requirements: 2.1, 7.1, 7.2, 9.1, 9.2_

- [x] 5. `map_pad_to_zone(pad)` — CATEGORICAL, v4 table, pure read.
  - Boolean threshold-membership tests only (no distance/centroid/score/percentage); v4-cited
    boundaries; most-specific-first precedence with `NEUTRAL_IDLE` default; the "+"/"-"
    markers are the predicates, moderate values are descriptors. Pure function; no PAD write.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [x] 6. `VisualLayer.__init__` — inject read-only PAD seam + window + clock + stability window.
  - Store `pad_source` (read-only), `window`, `clock` (default UTC now), `stability`
    (default `ZONE_STABILITY_SECONDS`, injectable). Init volatile state: `_speaking=False`,
    `_cloud_available=True`, `_current_zone=None`, `_current_zone_since=None`,
    `_current_loop=None`.
  - _Requirements: 2.1, 5.5, 8.2_

- [x] 7. `_render` + `refresh` — read PAD, map zone, 8 s gate, variant, drive window.
  - `_render(target)`: call `window.play_loop(target)` ONLY when `target != _current_loop`.
  - `refresh(now=None)`: degradation override first; else read PAD → `map_pad_to_zone` →
    stability gate (first-zone immediate; switch only at ≥ 8 s; else hold) → variant from
    `_speaking` → `_render`. Returns the driven `ZoneLoop`. Never writes PAD.
  - _Requirements: 2.1, 2.2, 3.1, 5.1, 5.2, 5.3, 5.4, 6.1, 7.3, 8.1, 8.2_

- [x] 8. `set_speaking` + `set_cloud_available` — prompt, ungated variant/degradation signals.
  - `set_speaking`: store flag; prompt variant re-render if a zone is established and not
    degraded; never changes zone identity or resets the 8 s timer.
  - `set_cloud_available`: store flag; unavailable → prompt `INWARD_WAITING`; available →
    prompt re-render of the current zone; neither 8 s-gated.
  - _Requirements: 4.1, 4.2, 4.3, 6.1, 6.3, 6.4, 6.5_

- [x] 9. Tests — `tests/test_visual_layer.py` (plain pytest, no hypothesis).
  - Categorical + varies-with-PAD (all 8 zones, `Zone`-typed, pure) + never-writes-PAD
    tripwire (REAL PADEngine); variant follows speaking-state (talking/idle, ungated, no zone
    change); 8 s minimum-before-switch (hold < 8 s, switch ≥ 8 s, 8.0 s boundary, first-zone
    immediate); graceful degradation (inward/waiting overrides PAD, prompt, restore resumes,
    ungated); independence (only PAD seam + window; no LLM/SoulFilter/Appraisal import;
    repeated refresh with no turn); PAD/graph/state never written (tripwire + source scans);
    `isinstance(visual, VisualLayerPort)`; window driven only on change (de-dup); REAL
    `AriaDaemon` driving speaking-state via its `speak()` boundary while the Visual Layer reads
    the REAL `PADEngine`.
  - _Requirements: 1.*, 2.*, 3.*, 4.*, 5.*, 6.*, 7.*, 8.*, 9.*, 10.*_

- [x] 10. Verify — module green, then full suite green (no regressions).
  - `python3 -m pytest tests/test_visual_layer.py -q` → green.
  - `python3 -m pytest -q` → prior 374 stay green + new Visual Layer tests. No other module
    modified.
  - _Requirements: 9.3_
