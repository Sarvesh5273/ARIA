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
