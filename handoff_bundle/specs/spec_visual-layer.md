# ARIA locked spec — visual-layer

Consolidated from .kiro/specs/visual-layer/{requirements,design,tasks}.md for upload.
Precedence: ARIA_Resolution_Log.md > ARIA_Soul_Spec_v4_Addendum.md > ARIA_Soul_Spec_v4.md.


---

## visual-layer — requirements.md

# Requirements — Module 10: Visual Layer

## Introduction

This document transcribes and formalizes, in EARS format, the Module 10 (Visual Layer)
entry from `ARIA_Module_Build_Plan.md`. That entry is the locked, approved scope for this
module. No requirement here introduces a mechanism, threshold, or behavior not already
stated in the Module 10 entry or in the supporting architecture documents
(`ARIA_Soul_Spec_v4.md` "Representation Layer — Video Avatar (Locked Conv.6)" and its
"PAD → Video Zone Mapping" / "Transition Logic" / "Speaking State" / "Graceful degradation
video state" sub-sections, the v4 constants table "Video zone stability | 8 seconds min
before switch | video_controller.py", and the v4 directory structure; `ARIA_Resolution_Log.md`
item 15; `daemon/pad_engine.py`'s `get_current_pad`; `daemon/aria_daemon.py`'s speaking-state
bookkeeping and port pattern). Where the Module 10 entry references a value or mechanism
defined elsewhere (the 8-zone table, the 8-second stability constant, the inward/waiting
degradation loop, the PyQt6/libmpv window), the supporting document is cited as the source,
not as a new source of scope.

Precedence when documents conflict: `ARIA_Resolution_Log.md` >
`ARIA_Soul_Spec_v4_Addendum.md` > `ARIA_Soul_Spec_v4.md`.
`ARIA_GLM_Covering_Instruction.md` is covering context only.

**The Visual Layer READS and DISPLAYS. It computes NO meaning and NO feeling.** It READS the
current PAD (a presentation read of substrate, v4 "Representation Layer") and the current
speaking-state (idle vs talking), SELECTS one of eight CATEGORICAL video zones, and drives an
injected PyQt6/libmpv window to play that zone's loop. It never appraises, never judges, and
— critically — **never writes PAD** (project-rules.md PAD-purity: "PAD changes only via an
Appraisal Chain PAD delta or EMA decay. Nothing else … writes to PAD directly, ever"). Zone
selection is CATEGORICAL — WHICH of the discrete zones — never a "feeling score" or a
percentage-of-the-way-there (project-rules.md "the percentage test").

**The one flag and its disposition (from the Module 10 entry):**

| Flag | Subject | Disposition |
|------|---------|-------------|
| **F-10a** | Video-owner discrepancy | **RESOLVED** by `ARIA_Resolution_Log.md` item 15: "PAD→video zone mapping lives in Visual Layer (Module 10); v4's 'soul_filter's job, not the LLM's' language is colloquial (soul layer generally, not the LLM) and doesn't override v4's own directory structure, which lists video_controller.py separately." PAD→zone mapping is implemented HERE, in `daemon/visual_layer.py` (the role v4's directory assigns to `video_controller.py`). Not reopened. v4's "Video selection is soul_filter's job, not the LLM's" is honored in spirit: the LLM never selects the video — the local soul layer does, running independently in parallel with language generation. |

**Additional locked / flagged items:**

- **PAD→zone is a READ of substrate for PRESENTATION**, not a feeling computation
  (project-rules.md substrate-vs-feeling chain; v4 "Representation Layer"). The Visual Layer
  NEVER writes PAD, and holds no Appraisal/Graph/Needs/State collaborator.
- **Zone selection is CATEGORICAL** (v4's 8-zone table). The eight zones and their PAD-region
  markers ARE spec (v4 "PAD → Video Zone Mapping" table). What v4 leaves OPEN — the exact
  precedence order among simultaneously-satisfied (overlapping) zone signatures, and whether
  each zone's descriptive moderate values are hard gates or feel-descriptors — is carried as
  a clearly-flagged build-time PRESENTATION placeholder (`TODO(F-10-zone-precedence)`), never
  an invented "feeling score." Only the v4 "+"/"-" markers are used as categorical predicates.
- **The 8-second minimum-before-switch is a v4 CONSTANT** — v4 "Transition Logic": "If PAD
  stays in a zone for less than 8 seconds, no switch — prevents flickering", and the v4
  constants table: "Video zone stability | 8 seconds min before switch | video_controller.py".
  Cited, not invented.
- **The inward/waiting degradation loop is a v4 STATE** — v4 "Graceful degradation video
  state": "During cloud failure, an inward/waiting loop plays — not sleeping … but withdrawn.
  Present but quiet." Shown on cloud failure; content is NOT fabricated.
- **Runs INDEPENDENTLY / in PARALLEL with language generation** — v4: "PAD zone mapping runs
  locally, independently, in parallel with language generation. The LLM never knows which
  video is playing." The visual loop does not block on, or depend on, the LLM turn.
- **The real PyQt6 frameless always-on-top window + embedded libmpv are abstracted behind an
  INJECTED interface** (`VideoWindow` Protocol; Rule 6; v4 "PyQt6 frameless floating window …
  libmpv embedded"). No GUI is hardcoded; tests inject a fake.
- **The independent visual-loop driver** (a timer/thread calling `refresh()` on a fast
  cadence) is BUILD-TIME WIRING at the top of the tree, not an architectural decision of this
  module. FLAGGED as a wiring concern (OQ-1). The speaking-state and cloud-availability
  signals arrive from the Daemon / LLM Interface readouts (`aria_daemon.py`'s output-pending
  boundary around `speak()`; `llm_interface.py`'s `serving_from_local`); wiring them is also
  top-of-tree (OQ-2).

## Glossary

- **Visual Layer**: the module specified here (Module 10, `daemon/visual_layer.py`) — plays
  the role v4's directory assigns to `video_controller.py`: "PAD zone → PyQt6 window loop
  signal."
- **Zone**: one of the EIGHT categorical video zones from v4's "PAD → Video Zone Mapping"
  table — Neutral/Idle, Engaged, Warm, Thinking, Concerned, Playful, Low/Tired, Firm — plus
  the separate **Inward/Waiting** degradation state (v4 "Graceful degradation video state").
- **Speaking-state**: idle vs talking. Each zone has two loop variants (v4 "Speaking State":
  "Each zone has two loop variants — idle and talking. When Aria speaks, the talking variant
  of the current zone plays. Approximately 16 video files total." = 8 zones × 2).
- **ZoneLoop**: the immutable (zone, variant) selection the Visual Layer hands the window —
  the "video-zone loop signal" (Build Plan Module 10 Outputs).
- **PADReader**: the READ-ONLY seam this module holds onto PAD_Engine — exposes only
  `get_current_pad()`. There is no mutator on this seam (mirrors Module 7's PADReader).
- **VideoWindow**: the injected GUI/video-driver Protocol (a ZonePlayer). Its real
  implementation is v4's `ui/aria_window.py` — a PyQt6 frameless always-on-top window with
  embedded libmpv that plays loop files and finishes the current loop cycle before switching
  (v4 "Current loop finishes its cycle before switching — no jarring cuts"). Tests inject a
  fake. No GUI is hardcoded (Rule 6).
- **VisualLayerPort**: the clean contract a driver (the Daemon) can drive — `set_speaking`,
  `set_cloud_available`, `refresh`. The Daemon defines no visual port today, so this module
  EXPOSES the contract (ResLog: "if none is defined, expose a clean contract the Daemon can
  drive"). `runtime_checkable`.

## Requirements

### Requirement 1: PAD→video-zone mapping lives here (F-10a RESOLVED)

**User Story:** As the Aria system architect, I want the PAD→video-zone mapping implemented
in the Visual Layer, so the file layout matches v4's directory structure and ResLog item 15.

#### Acceptance Criteria
1. THE Visual Layer SHALL implement PAD→zone mapping in `daemon/visual_layer.py` (the role v4
   assigns to `video_controller.py`) — F-10a RESOLVED by ResLog item 15; NOT reopened.
2. THE LLM SHALL NOT select the video: zone selection SHALL run locally in the soul layer,
   independently and in parallel with language generation (v4: "Video selection is
   soul_filter's job, not the LLM's … The LLM never knows which video is playing").

### Requirement 2: Reads PAD + speaking-state; computes no meaning or feeling; never writes PAD

**User Story:** As the Aria system, I want the Visual Layer to only READ PAD and speaking-state
and DISPLAY a zone, so meaning and feeling come from the appraisal/PAD modules, not from the
presentation layer (project-rules.md).

#### Acceptance Criteria
1. THE Visual Layer SHALL READ the current PAD via the read-only `PADReader` seam at
   refresh/selection time (v4 "Representation Layer" — a presentation read of substrate).
2. THE Visual Layer SHALL NOT write PAD anywhere (project-rules.md PAD-purity). It SHALL NOT
   call any PAD mutator (`apply_appraisal_delta`, `on_soul_tick`, `initialize`).
3. THE Visual Layer SHALL NOT appraise, judge, or classify meaning — it SHALL only select a
   categorical zone for display.
4. THE Visual Layer SHALL hold NO reference to the Appraisal Chain, the Memory Graph, the
   Needs System, the State Manager, the Soul Filter, or the LLM Interface, and SHALL NOT
   import any of them — the only inward collaborators SHALL be the READ-ONLY `PADReader` seam
   and the injected `VideoWindow`. That absence is the structural guarantee that it computes
   no feeling and writes no state.

### Requirement 3: Categorical zone selection — WHICH zone, never a feeling score

**User Story:** As the Aria system, I want the zone chosen categorically (which discrete
zone), so the presentation of feeling is never itself a computed feeling (project-rules.md
"the percentage test").

#### Acceptance Criteria
1. THE Visual Layer SHALL map a PAD reading to exactly one of the eight v4 zones —
   Neutral/Idle, Engaged, Warm, Thinking, Concerned, Playful, Low/Tired, Firm (v4 "PAD →
   Video Zone Mapping" table).
2. THE mapping SHALL be CATEGORICAL: it SHALL test PAD-region membership by boolean threshold
   comparisons ("holds or it doesn't") and SHALL NOT compute a distance, a centroid nearness,
   a weighted score, or a percentage (project-rules.md "the percentage test"; "Everywhere
   else, categorical").
3. THE mapping SHALL be a pure function of the PAD reading: identical PAD SHALL yield the
   identical zone, and computing the zone SHALL NOT write PAD or any state.
4. THE zone-boundary numbers SHALL be CITED to v4's "PAD → Video Zone Mapping" table (the
   "+"/"-" markers: Engaged P/A/D ≥ 0.6; Playful P ≥ 0.7, A ≥ 0.6, D ≥ 0.7; Warm P ≥ 0.7;
   Thinking A ≥ 0.7; Concerned P ≤ 0.3; Low/Tired P ≤ 0.4, A ≤ 0.3, D ≤ 0.4; Firm D ≥ 0.8;
   Neutral/Idle ≈ baseline = the DEFAULT when no other signature holds).
5. THE precedence order among simultaneously-satisfied (overlapping) zone signatures SHALL be
   a documented, clearly-flagged build-time PRESENTATION placeholder
   (`TODO(F-10-zone-precedence)`) — v4's table does not order overlaps; the order chosen is
   deterministic and never affects PAD, meaning, or memory (mirrors `select_thinking_sound`'s
   flagged trigger precedence in `aria_daemon.py`).

### Requirement 4: Talking vs idle variant follows speaking-state

**User Story:** As the Aria system, I want the talking variant to play while Aria speaks and
the idle variant otherwise, so the avatar's mouth matches her voice (v4 "Speaking State").

#### Acceptance Criteria
1. WHEN speaking-state is talking, THE Visual Layer SHALL select the TALKING variant of the
   current zone; WHEN idle, THE idle variant (v4: "When Aria speaks, the talking variant of
   the current zone plays").
2. A change of speaking-state (idle↔talking) SHALL change only the VARIANT of the current
   zone, SHALL NOT change the zone identity, and SHALL NOT be subject to the 8-second
   zone-stability gate (the gate governs zone flicker, not the mouth) — the variant SHALL
   update promptly so the mouth tracks the voice.
3. THE speaking-state SHALL be an INPUT signal the Visual Layer receives (Build Plan Module 10
   Inputs: "Speaking state (idle vs talking variant) — from Daemon / Audio Pipeline"); the
   Visual Layer SHALL NOT derive it from PAD or from the LLM.

### Requirement 5: 8-second minimum-before-switch (zone stability, v4 constant)

**User Story:** As the Aria system, I want a zone to hold for at least 8 seconds before
switching, so the avatar does not flicker between zones (v4 "Transition Logic").

#### Acceptance Criteria
1. THE Visual Layer SHALL NOT switch to a different zone until the current zone has been
   displayed for at least 8 seconds (v4 constants table: "Video zone stability | 8 seconds
   min before switch"; v4 "If PAD stays in a zone for less than 8 seconds, no switch —
   prevents flickering").
2. WHEN the PAD-mapped candidate zone differs from the current zone AND fewer than 8 seconds
   have elapsed since the current zone was established, THE Visual Layer SHALL HOLD the
   current zone (no switch).
3. WHEN the candidate zone differs AND at least 8 seconds have elapsed, THE Visual Layer SHALL
   switch to the candidate zone and reset the stability timer. A boundary of exactly 8.0 s
   SHALL permit the switch (the gate is ≥).
4. THE FIRST zone established (no prior zone) SHALL be displayed immediately (there is no
   prior zone to hold), starting the stability timer.
5. THE 8-second constant SHALL be defined as a v4-CITED constant (`ZONE_STABILITY_SECONDS = 8`),
   overridable via injection for testing but defaulting to the v4 value.

### Requirement 6: Graceful degradation — inward/waiting loop on cloud failure

**User Story:** As the Aria system, I want an inward/waiting loop shown during cloud failure,
so Aria stays present but withdrawn without fabricating content (v4 "Graceful degradation
video state").

#### Acceptance Criteria
1. WHEN cloud availability is signalled as unavailable, THE Visual Layer SHALL display the
   inward/waiting loop, OVERRIDING PAD-driven zone selection (v4: "During cloud failure, an
   inward/waiting loop plays — not sleeping … but withdrawn. Present but quiet").
2. THE inward/waiting loop SHALL be a single loop (not fabricated, no idle/talking variant
   split) — it is a distinct display STATE, not one of the eight PAD zones.
3. WHEN cloud availability is restored, THE Visual Layer SHALL resume PAD-driven zone
   selection (re-establishing the current zone's loop), with no announcement (v4: "Full voice
   returns naturally, no announcement").
4. Entering/leaving the degradation state SHALL be prompt (a failure is not zone flicker) and
   SHALL NOT be gated by the 8-second zone-stability window.
5. THE cloud-availability signal SHALL be an INPUT the Visual Layer receives (from the Daemon
   / LLM Interface `serving_from_local` readout / `LLMUnavailableError`); the Visual Layer
   SHALL NOT itself talk to any model or fabricate degradation text.

### Requirement 7: Drives an injected PyQt6/libmpv window — no GUI hardcoded (Rule 6)

**User Story:** As the Aria system architect, I want the window/video driver injected behind a
Protocol, so the layer is testable headless with a fake and the real GUI is hot-swappable.

#### Acceptance Criteria
1. THE Visual Layer SHALL drive the display through an injected `VideoWindow` Protocol (a
   ZonePlayer) — the "video-zone loop signal" to the PyQt6 window (Build Plan Module 10
   Outputs).
2. THE Visual Layer SHALL NOT import or instantiate PyQt6, libmpv, or any concrete GUI/video
   toolkit; the real `VideoWindow` (v4's `ui/aria_window.py`: "PyQt6 frameless floating
   window … libmpv embedded") SHALL be injected.
3. THE Visual Layer SHALL request a loop from the window only when the target loop changes
   (zone switch, variant flip, or degradation enter/exit) — it SHALL NOT re-issue the same
   loop every refresh (the window owns finishing the current loop cycle before switching, v4
   "Current loop finishes its cycle before switching").

### Requirement 8: Runs independently / in parallel with language generation

**User Story:** As the Aria system, I want the visual loop to run independently of the LLM
turn, so the avatar keeps living while language is generated (v4 "runs locally,
independently, in parallel with language generation").

#### Acceptance Criteria
1. THE Visual Layer's `refresh()` SHALL depend only on the injected `PADReader` and
   `VideoWindow` (plus its own speaking/cloud signals) — it SHALL NOT call, block on, or hold
   a reference to the LLM Interface, the Soul Filter, or the Appraisal Chain.
2. THE Visual Layer SHALL be drivable on its own cadence (repeated `refresh()` calls) with no
   inbound turn in progress — the visual loop is not coupled to `route_inbound_turn`.
3. THE independent driver loop (timer/thread calling `refresh()`) SHALL be top-of-tree
   BUILD-TIME WIRING (OQ-1), not implemented as an architectural mechanism inside this module.

### Requirement 9: Exposes a clean contract the Daemon can drive (VisualLayerPort)

**User Story:** As the Daemon, I want a clean visual contract to drive, so I can push
speaking-state and cloud-availability and step the visual loop without this module reaching
back into me (the Daemon defines no visual port today).

#### Acceptance Criteria
1. THE Visual Layer SHALL expose `set_speaking(is_speaking: bool)`, `set_cloud_available(
   available: bool)`, and `refresh(now=None)` as its driver contract (`VisualLayerPort`).
2. `isinstance(visual_layer, VisualLayerPort)` SHALL hold (the Protocol is
   `runtime_checkable`).
3. THE contract SHALL be drivable by the REAL Daemon's EXISTING signals UNCHANGED: the
   Daemon's output-pending boundary around `audio.speak()` maps to `set_speaking(True/False)`,
   and the LLM Interface's `serving_from_local` maps to `set_cloud_available(...)` — verified
   end-to-end with the REAL `AriaDaemon` reading PAD from the REAL `PADEngine`. No core module
   is modified (if a contract needs changing, it is FLAGGED, not changed).

### Requirement 10: Constants — cited or flagged, never invented (Rule 4)

**User Story:** As the Aria system architect, I want every constant either cited to v4 or
clearly flagged as a build-time placeholder, so no number is invented (Rule 4).

#### Acceptance Criteria
1. THE Visual Layer SHALL define `ZONE_STABILITY_SECONDS = 8` and the per-zone boundary
   thresholds as constants CITED to v4 ("PAD → Video Zone Mapping" table; constants table).
2. THE zone-precedence ORDER and the descriptive-vs-gate reading of each zone's moderate
   values SHALL be a clearly-flagged `TODO(F-10-zone-precedence)` build-time presentation
   placeholder — the only invention-free path for what v4 leaves open. No "feeling score",
   percentage, or new numeric threshold SHALL be introduced.

## Open Questions (flagged; not resolved by invention)

- **OQ-1 (build-time wiring):** the independent driver loop (a timer/thread repeatedly calling
  `refresh()` on a fast cadence) lives at the top-of-tree wiring layer, not in this module.
  Named, not resolved here.
- **OQ-2 (signal wiring):** the Daemon defines no visual port today; wiring its output-pending
  boundary around `speak()` to `set_speaking(...)` and the LLM Interface's `serving_from_local`
  to `set_cloud_available(...)` is top-of-tree wiring. This module EXPOSES the contract (per
  ResLog "expose a clean contract the Daemon can drive") but does NOT modify the Daemon. If a
  Daemon-side hook is later desired, that is a FLAGGED contract change, not made here.
- **OQ-3 (zone precedence / gate reading):** `TODO(F-10-zone-precedence)` — v4's zone table
  does not order overlapping signatures nor say whether each zone's moderate descriptive
  values are hard gates. Only the "+"/"-" markers are used as predicates; the precedence order
  is a documented presentation placeholder. Never resolved by an invented feeling score.


---

## visual-layer — design.md

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
  `set_speaking` and `serving_from_local` → `set_cloud_available` is top-of-tree. The contract
  is EXPOSED here; the Daemon is NOT modified. A Daemon-side hook would be a flagged contract
  change.
- **OQ-3 (zone precedence / gate reading):** `TODO(F-10-zone-precedence)` — the precedence
  order among overlapping signatures and the descriptive-vs-gate reading of moderate values
  are documented presentation placeholders; only v4 "+"/"-" markers are predicates. Never a
  feeling score.


---

## visual-layer — tasks.md

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

