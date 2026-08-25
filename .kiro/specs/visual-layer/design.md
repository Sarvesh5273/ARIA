# Design — Module 10: Visual Layer

## Overview

The Visual Layer (`daemon/visual_layer.py`) is Aria's face. It plays the role v4's directory
assigns to `video_controller.py`: "PAD zone → PyQt6 window loop signal." One module that, on
each step of its own independent loop:

1. **READS** the current PAD via a read-only seam (`PADReader.get_current_pad()`), and
2. **SELECTS** exactly one of eight CATEGORICAL video zones from that PAD (v4 "PAD → Video
   Zone Mapping" table), then
3. combines the zone with the current **speaking-state** (idle vs talking) into a `ZoneLoop`,
4. applies the **8-second minimum-before-switch** stability gate to zone changes (v4
   constants table), and
5. drives an **injected `VideoWindow`** (the PyQt6/libmpv abstraction) to play that loop.

On cloud failure it instead shows the **inward/waiting** degradation loop (v4 "Graceful
degradation video state"), overriding PAD-driven selection until the cloud restores.

The single most important property is what the Visual Layer does NOT do: **it computes no
meaning and no feeling, and it never writes PAD.** Mapping PAD→zone is a READ of substrate for
PRESENTATION (project-rules.md substrate-vs-feeling chain; v4 "Representation Layer"), not an
appraisal. Zone selection is CATEGORICAL — WHICH discrete zone — decided by boolean
threshold-membership tests, never by a distance/centroid/score/percentage (project-rules.md
"the percentage test"). It holds no Appraisal/Graph/Needs/State/SoulFilter/LLM collaborator
and imports none of them.

This design implements requirements.md as written, using only mechanisms already specified
there or in the supporting documents (v4 zone table + 8 s constant + inward/waiting loop;
ResLog item 15; Build Plan Module 10). No new mechanism, formula, or threshold is introduced.
The one genuine gap v4 leaves open — the precedence order among overlapping zone signatures,
and whether each zone's moderate values are hard gates — is carried as a flagged
`TODO(F-10-zone-precedence)` presentation placeholder; only the v4 "+"/"-" markers are used as
predicates.

## Hard Constraints (carried from requirements.md, non-negotiable)

1. **COMPUTES NO FEELING / NEVER WRITES PAD.** The module never calls a PAD mutator
   (grep-clean: `apply_appraisal_delta` / `on_soul_tick` / `initialize` never appear in the
   source). Its only PAD collaborator is the read-only `PADReader` (exposes only
   `get_current_pad()`). PAD-purity is structural: there is no mutator on the seam (Req 2).
2. **CATEGORICAL ZONE SELECTION.** `map_pad_to_zone` returns a `Zone` enum member via boolean
   threshold tests — no distance, centroid, weighted score, or percentage (Req 3). Boundaries
   are v4-cited; the precedence order is a flagged presentation placeholder.
3. **VARIANT FOLLOWS SPEAKING-STATE.** talking↔idle changes only the variant of the current
   zone, promptly, and is NOT subject to the 8 s zone gate (Req 4).
4. **8-SECOND MINIMUM-BEFORE-SWITCH.** A zone holds ≥ 8 s before a different zone may take
   over (v4 constants table; Req 5).
5. **GRACEFUL DEGRADATION.** On cloud failure → inward/waiting loop, overriding PAD zones,
   prompt (not gated), no fabricated content (v4; Req 6).
6. **INJECTED WINDOW — NO GUI HARDCODED.** The display is driven through an injected
   `VideoWindow` Protocol; PyQt6/libmpv are never imported here (Rule 6; Req 7).
7. **INDEPENDENT OF LANGUAGE GENERATION.** `refresh()` depends only on the PAD seam + window
   (+ speaking/cloud signals); it never touches the LLM/Soul Filter/Appraisal (v4; Req 8).
8. **EXPOSES `VisualLayerPort`.** `set_speaking` / `set_cloud_available` / `refresh`, drivable
   by the REAL Daemon's existing signals unchanged (Req 9).

## Architecture

```
                     external signals (top-of-tree WIRING — OQ-1/OQ-2)
   PAD (read)        speaking-state              cloud availability      loop-tick
   (PAD_Engine)      (Daemon speak() boundary)   (llm serving_from_local) (timer/thread)
        │                    │                          │                    │
        ▼                    ▼                          ▼                    ▼
 ┌───────────────────────── VisualLayer (Module 10) ─────────────────────────────┐
 │  set_speaking(bool)         → _speaking            (prompt variant re-render)   │
 │  set_cloud_available(bool)  → _cloud_available     (prompt degrade / restore)   │
 │  refresh(now):                                                                  │
 │     pad = PADReader.get_current_pad()   ── READ (presentation) ──┐              │
 │     if not _cloud_available:  target = ZoneLoop(INWARD_WAITING)  │  (override)  │
 │     else:                                                        │              │
 │        candidate = map_pad_to_zone(pad)   [CATEGORICAL, v4 table] │              │
 │        _apply_stability_gate(candidate, now)   [8 s min, v4]      │              │
 │        target = ZoneLoop(_current_zone, TALKING if _speaking else IDLE)         │
 │     _render(target)   → window.play_loop(target)  ONLY if target != _current_loop│
 └─────────────────────────────────────────────────────────────────────────────────┘
        │                                                                    │
        ▼                                                                    ▼
   PADReader (get_current_pad ONLY — read-only seam)              VideoWindow (play_loop)
   real = PAD_Engine (Module 1)                        real = ui/aria_window.py (PyQt6+libmpv)
                                                       [injected — no GUI hardcoded; tests: fake]
```

The ONLY inward-facing collaborator is the read-only `PADReader`; the ONLY outward collaborator
is the `VideoWindow`. There is deliberately no Appraisal/Graph/Needs/State/SoulFilter/LLM edge
on this diagram — that absence is the structural proof that no refresh, no speaking change, and
no degradation can reach a PAD write, any state mutation, or the language turn.

## Value types

- **`Zone`** (Enum): the eight v4 zones — `NEUTRAL_IDLE`, `ENGAGED`, `WARM`, `THINKING`,
  `CONCERNED`, `PLAYFUL`, `LOW_TIRED`, `FIRM` — plus `INWARD_WAITING` (the degradation state;
  NOT a PAD-mapped zone, v4 "Graceful degradation video state").
- **`SpeakingState`** (Enum): `IDLE` / `TALKING` — the two loop variants per zone (v4
  "Speaking State").
- **`ZoneLoop`** (frozen): `zone: Zone`, `variant: SpeakingState`. The immutable "video-zone
  loop signal" handed to the window (Build Plan Module 10 Outputs). `loop_id` property yields
  the file-key string (e.g. `"engaged_talking"`, `"neutral_idle_idle"`, `"inward_waiting"`),
  matching v4's "16 video loop files (8 zones × 2 states)" + the separate inward/waiting loop.
  For `INWARD_WAITING` the variant is normalized to `IDLE` (single loop, no talking variant).

## Injected Protocols (Rule 6)

Each is a `runtime_checkable` Protocol; the real implementation wraps the v4-named tool, tests
inject fakes. No concrete provider is imported.

| Protocol | Method(s) | Real (v4) | Role |
|---|---|---|---|
| `PADReader` | `get_current_pad() -> PADSnapshot` | PAD_Engine (Module 1) | READ-ONLY seam (no mutator) |
| `VideoWindow` | `play_loop(loop: ZoneLoop) -> None` | `ui/aria_window.py` (PyQt6 frameless always-on-top + libmpv) | plays a loop; finishes current cycle before switching |

`VisualLayerPort` (also `runtime_checkable`) is the DRIVER contract this module implements —
`set_speaking(bool)`, `set_cloud_available(bool)`, `refresh(now=None) -> ZoneLoop`. It is the
"clean contract the Daemon can drive" (ResLog): the Daemon defines no visual port, so the
contract lives here.

## `map_pad_to_zone(pad) -> Zone` — CATEGORICAL, v4 table

A pure function of a `PADSnapshot` (no engine, no state, no write). It asks, for each zone, a
boolean membership question ("does PAD satisfy this zone's v4 signature? — holds or it
doesn't"), NEVER "how close is PAD to this zone?" (which would be a number in disguise —
project-rules.md percentage test). The v4 "+"/"-" markers are the predicates; the moderate
descriptive values (e.g. Warm's "A:0.4 D:0.5") are treated as feel-descriptors, NOT extra hard
gates — using them as gates would invent tight boundaries v4 did not mark. Precedence runs
most-specific/most-extreme first; `NEUTRAL_IDLE` (≈ baseline) is the DEFAULT when no other
signature holds:

```
p, a, d = pad.pleasure, pad.arousal, pad.dominance          # a READ; never written
if p <= LOW_TIRED_P_MAX and a <= LOW_TIRED_A_MAX and d <= LOW_TIRED_D_MAX: return LOW_TIRED
if p <= CONCERNED_P_MAX:                                                    return CONCERNED
if p >= PLAYFUL_P_MIN and a >= PLAYFUL_A_MIN and d >= PLAYFUL_D_MIN:        return PLAYFUL
if d >= FIRM_D_MIN:                                                         return FIRM
if a >= THINKING_A_MIN:                                                     return THINKING
if p >= ENGAGED_P_MIN and a >= ENGAGED_A_MIN and d >= ENGAGED_D_MIN:        return ENGAGED
if p >= WARM_P_MIN:                                                         return WARM
return NEUTRAL_IDLE                                                         # default (baseline)
```

Boundaries (v4-CITED, "PAD → Video Zone Mapping"):
`LOW_TIRED_P_MAX=0.4, LOW_TIRED_A_MAX=0.3, LOW_TIRED_D_MAX=0.4` (P:0.4- A:0.3- D:0.4-);
`CONCERNED_P_MAX=0.3` (P:0.3-); `PLAYFUL_P_MIN=0.7, PLAYFUL_A_MIN=0.6, PLAYFUL_D_MIN=0.7`
(P:0.7+ A:0.6+ D:0.7+); `FIRM_D_MIN=0.8` (D:0.8+); `THINKING_A_MIN=0.7` (A:0.7+);
`ENGAGED_P_MIN=ENGAGED_A_MIN=ENGAGED_D_MIN=0.6` (P:0.6+ A:0.6+ D:0.6+); `WARM_P_MIN=0.7`
(P:0.7+); Neutral/Idle = default (≈ baseline 0.55/0.45/0.58).

The ORDER of these checks is the `TODO(F-10-zone-precedence)` presentation placeholder — v4's
table does not order overlapping signatures (e.g. a high-everything PAD satisfies Playful,
Engaged AND Thinking). The order is deterministic and documented; it never affects PAD,
meaning, or memory (exactly like `select_thinking_sound`'s flagged trigger precedence in
`aria_daemon.py`). Chosen rationale: extreme/most-specific signatures win over broad ones
(Playful ⊃-narrower-than Engaged; low-everything Low/Tired before the single-marker Concerned),
so the broad `ENGAGED` band and the single-pleasure `WARM` do not swallow the more specific
zones. This is a presentation nicety, not a claim about feeling.

## `VisualLayer` — state and methods

Volatile working state (none persisted — the Visual Layer owns no memory):
- `_speaking: bool` — current speaking-state (default idle/False).
- `_cloud_available: bool` — degradation trigger (default True).
- `_current_zone: Optional[Zone]` — the PAD-zone identity for the 8 s gate (None before first
  refresh).
- `_current_zone_since: Optional[datetime]` — when `_current_zone` last changed (8 s gate).
- `_current_loop: Optional[ZoneLoop]` — what the window is actually showing (render dedup).

### `refresh(now=None) -> ZoneLoop`
The independent loop step. `now` defaults to the injected clock (mirrors `aria_daemon.py`).
1. If `not _cloud_available`: `_render(ZoneLoop(INWARD_WAITING, IDLE))`; return. (Override,
   prompt, ungated — Req 6.)
2. Else read PAD (read-only), `candidate = map_pad_to_zone(pad)`, apply the stability gate:
   - `_current_zone is None` → establish immediately, set `_current_zone_since = now` (Req 5.4).
   - `candidate != _current_zone` and `now - _current_zone_since >= STABILITY_WINDOW` → switch,
     reset timer (Req 5.3).
   - else → hold current zone (Req 5.2).
3. `variant = TALKING if _speaking else IDLE`; `_render(ZoneLoop(_current_zone, variant))`.

### `set_speaking(is_speaking) -> None` (Req 4)
Stores the flag; if it changed AND a zone is established AND not degraded, promptly re-renders
the current zone's other variant (mouth tracks voice). Does NOT change zone identity or reset
the 8 s timer. During degradation or before the first zone, it only stores the flag.

### `set_cloud_available(available) -> None` (Req 6)
Stores the flag; if it changed: unavailable → prompt `_render(INWARD_WAITING)`; available →
prompt re-render of the current zone (if established) so full presence returns with no
announcement. Neither transition is 8 s-gated.

### `_render(target: ZoneLoop) -> None` (Req 7.3)
`if target != _current_loop: window.play_loop(target); _current_loop = target`. The window
owns finishing the current loop cycle before switching (v4); this module only signals the
target and de-dups identical signals.

## PAD-purity, categorical & independence — the structural guarantees

- The module imports exactly one daemon symbol: `from daemon.pad_engine import PADSnapshot`
  (a read-only type). It imports NO write-capable module (graph_manager, appraisal_chain,
  needs_system, state_manager, aria_daemon, soul_filter, llm_interface) and NO GUI toolkit
  (PyQt6, mpv).
- `map_pad_to_zone` returns a `Zone` enum via `>=`/`<=` comparisons only — no arithmetic that
  produces a score/distance/percentage.
- No method references a PAD mutator, a graph/needs/state write, or an LLM/Soul-Filter call.
- The `PADReader` seam has no mutator, so even `refresh()` (which reads PAD) cannot write it.

These are enforced by tests (source scans + a live tripwire against the REAL PADEngine).

## Testing strategy (see tests/test_visual_layer.py)

Plain pytest, NO hypothesis. Fakes for the window and PAD seam; a live tripwire against the
REAL `PADEngine`; the REAL `AriaDaemon` for the end-to-end contract. Highlights:
- **Categorical & varies with PAD**: `map_pad_to_zone` returns a `Zone` (never a number),
  covers all eight zones across representative PADs, is a pure function, and (tripwire) never
  writes PAD.
- **Variant follows speaking-state**: `set_speaking(True)` → talking variant of current zone;
  `set_speaking(False)` → idle; a variant flip does NOT change the zone and is NOT 8 s-gated.
- **8 s minimum-before-switch**: a new candidate within 8 s holds the old zone; at ≥ 8 s it
  switches; the 8.0 s boundary switches; the first zone is immediate.
- **Graceful degradation**: `set_cloud_available(False)` → `INWARD_WAITING` regardless of PAD;
  restore resumes the PAD zone; degradation is prompt and ungated; no fabricated content.
- **Independence**: `refresh()` uses only PAD seam + window; the module imports no
  LLM/SoulFilter/Appraisal; repeated `refresh()` with no turn in progress works.
- **PAD-purity / no-write tripwire**: many refreshes + speaking + degradation leave the REAL
  PADEngine's PAD byte-identical and its mutator uncalled; plus source-scan structural proofs
  (no forbidden imports/calls).
- **Contract**: `isinstance(visual, VisualLayerPort)`; window driven only on change (de-dup);
  and the REAL `AriaDaemon` driving speaking-state through its EXISTING `speak()` boundary
  (via a top-of-tree wiring bridge) while the Visual Layer reads PAD from the REAL `PADEngine`.

## Open Questions (flagged; not resolved by invention)

- **OQ-1 (build-time wiring):** the independent driver loop (repeated `refresh()`), top-of-tree.
- **OQ-2 (signal wiring):** the Daemon defines no visual port; wiring `speak()`-boundary →
  `set_speaking` and an LLM-availability signal → `set_cloud_available` is top-of-tree. The
  contract is EXPOSED here; the Daemon is NOT modified. A Daemon-side hook would be a flagged
  contract change. **Amended 2026-08-24 (ResLog 26):** the signal named here and elsewhere in
  this spec was `serving_from_local`, which no longer exists — it reported the local model's
  RESIDENCY, which Track A made permanently True. `adapters/visual_bridge.py` wires
  `LLMUnavailableError` instead and asserts by AST that neither `serving_from_local` nor its
  replacement `last_route` is read, because the deeper question is still open: under a
  local-primary design "no cloud" is the resting state, so a truthful routing readout still
  does not say whether she should LOOK withdrawn.
- **OQ-3 (zone precedence / gate reading):** `TODO(F-10-zone-precedence)` — the precedence
  order among overlapping signatures and the descriptive-vs-gate reading of moderate values
  are documented presentation placeholders; only v4 "+"/"-" markers are predicates. Never a
  feeling score.
