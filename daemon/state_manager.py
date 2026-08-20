"""Module 11 — State Manager (pure persistence plumbing).

Locked spec: ARIA_Module_Build_Plan.md, Module 11. Owns NO meaning: it does
not compute PAD, decay Energy, or interpret the self-model. The live owners
(Module 1 PAD Engine, Module 2 Needs System, Module 6 DMN) hold the
authoritative in-memory state; this module only snapshots it to disk and
restores it. PAD math, Energy depletion, and self-model updates all stay in
their owning modules (ResLog §4: "Owns no meaning — pure read/write plumbing").

What it persists (ResLog §2 — self-model split):
  aria_state.json  -> pad (pleasure/arousal/dominance), energy (continuous),
                       last_applied_valence (opaque string or null — this
                       module stores it as raw text and does not know what
                       it means; see ARIA_Resolution_Log.md item 4, "owns
                       no meaning")
  self_model.json  -> narrowed self-model working-state only:
                        quality_record, consistency_flags,
                        recent_learning_user, recent_learning_self

What it does NOT persist:
  - self-continuity narrative: graph-owned, lives in the self-referential
    EntityNode's relationship_summary (Module 3). ResLog §2.
  - relationship_depth: removed entirely (ResLog §10); superseded by
    EntityNode.relational_stage.
  - the four categorical need states (Connection/Growth/Purpose/Continuity):
    derived from graph evidence at runtime, never persisted (Addendum §3).
    Only Energy is persisted, as a continuous value.

Write cadence is a build-time tuning flag (ResLog §4); the Daemon (Module 8)
drives periodic save_all() calls plus a final save on shutdown. This module
is synchronous (tiny atomic JSON writes); the daemon may offload to an
executor if it ever needs non-blocking saves.
"""

from __future__ import annotations

import json
import logging
import math
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("aria.state")

# ---------------------------------------------------------------------------
# Tuning flags / defaults
# ---------------------------------------------------------------------------

# Locked PAD baseline (v4 Layer 1). Module 1 owns live PAD computation; this is
# only the default returned when no state file exists yet (first run / corrupt
# file), so callers always get a valid, spec-conformant state to boot from.
PAD_BASELINE = (0.55, 0.45, 0.58)  # pleasure, arousal, dominance

# Energy baseline is NOT locked anywhere in the spec (v4/Addendum/ResLog pin
# only the 30 and 20 operational gates). Scale is 0-100, inherited from the
# existing Phase-1 code and consistent with those gates. 100 = fully rested.
# Treat as a tuning flag; Module 2 (Needs) owns live Energy dynamics.
DEFAULT_ENERGY = 100.0

# ---------------------------------------------------------------------------
# Restore bounds. These make RESTORE defensive: a hand-edited, truncated or
# corrupted state file must not be able to seed an out-of-range value into a
# live session. This is a boundary check on data read from disk, not meaning —
# the module still computes nothing and still does not interpret the values.
# ---------------------------------------------------------------------------

# PAD is bounded to [0.0, 1.0] (v4 Layer 1). Module 1 already clamps LIVE PAD in
# apply_appraisal_delta; restore now enforces the same locked bound.
PAD_MIN = 0.0
PAD_MAX = 1.0

# Energy bounds mirror Module 2's ENERGY_MIN / ENERGY_BASELINE (0.0 / 100.0) by
# VALUE, deliberately not by import — Module 11 depends on no other module. The
# 0-100 scale is a tuning flag (see DEFAULT_ENERGY above), so this clamp inherits
# that status rather than asserting a spec-locked range.
ENERGY_MIN = 0.0
ENERGY_MAX = DEFAULT_ENERGY

# Save cadence — build-time tuning flag (ResLog §4). Not an architectural
# decision. The Daemon reads this to schedule periodic save_all() calls.
SAVE_CADENCE_SECONDS = 30.0

# Self-model rolling window (v4 self-model field 1: "last 20 self-assessments").
QUALITY_RECORD_MAX = 20
QUALITY_VALUES = ("responded_well", "adequately", "poorly")  # documented, not enforced

# Consistency flags (v4 self-model field 2). "Resets each session" is the
# Daemon/DMN's concern, not this module's — we persist whatever we are given.
CONSISTENCY_FLAG_NAMES = (
    "honest_when_uncomfortable",
    "pushed_back_when_appropriate",
    "initiated_when_needed",
    "acknowledged_mistake",
)

# Keys this module owns / recognises in aria_state.json.
_KEY_PAD = "pad"
_KEY_ENERGY = "energy"
_KEY_LAST_APPLIED_VALENCE = "last_applied_valence"
_KEY_SELF_ENTITY_ID = "self_entity_id"
# Superseded keys dropped on write (locked decisions) so they are not perpetuated.
_SUPERSEDED_KEYS = frozenset({"relationship_depth", "needs"})


# ---------------------------------------------------------------------------
# Persisted payloads — Module 11's serialisation schema only. Modules 1/2/6
# may use richer live objects and convert at this boundary, or adopt these.
# ---------------------------------------------------------------------------

@dataclass
class PADState:
    """Pleasure / Arousal / Dominance. Three continuous values, nothing else."""
    pleasure: float
    arousal: float
    dominance: float

    @classmethod
    def baseline(cls) -> "PADState":
        return cls(PAD_BASELINE[0], PAD_BASELINE[1], PAD_BASELINE[2])

    def as_dict(self) -> Dict[str, float]:
        return {
            "pleasure": float(self.pleasure),
            "arousal": float(self.arousal),
            "dominance": float(self.dominance),
        }


@dataclass
class SelfModel:
    """Narrowed self-model working-state (ResLog §2). Narrative is NOT here."""
    quality_record: List[str] = field(default_factory=list)
    consistency_flags: Dict[str, bool] = field(default_factory=dict)
    recent_learning_user: str = ""
    recent_learning_self: str = ""

    @classmethod
    def default(cls) -> "SelfModel":
        # All consistency flags start False on a fresh self-model.
        return cls(consistency_flags={name: False for name in CONSISTENCY_FLAG_NAMES})


# ---------------------------------------------------------------------------
# State Manager
# ---------------------------------------------------------------------------

class StateManager:
    """Persists and restores the non-graph operational working-state."""

    def __init__(self, state_dir: Path | str | None = None):
        self.state_dir = Path(state_dir) if state_dir else (
            Path.home() / ".local" / "aria" / "state"
        )
        self.state_file = self.state_dir / "aria_state.json"
        self.self_model_file = self.state_dir / "self_model.json"

    # -- low-level JSON helpers ------------------------------------------------

    def _read_json(self, path: Path) -> Dict:
        """Read+parse JSON; return {} for missing or corrupt files (never raise)."""
        if not path.exists():
            return {}
        try:
            return json.loads(path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("State file %s unreadable (%s); starting fresh", path, exc)
            return {}

    @staticmethod
    def _bounded(raw, low: float, high: float) -> float:
        """Coerce a restored value to float and clamp it into [low, high].

        Raises ValueError/TypeError for anything unusable so the caller's
        existing `except (TypeError, ValueError)` path logs and falls back to the
        spec default — the same handling a non-numeric entry already got.

        Non-finite input is unusable ON PURPOSE. `json.loads` accepts a literal
        `NaN`/`Infinity`, and NaN silently survives a naive
        `max(low, min(high, v))` as `high` — i.e. a corrupt Energy entry would
        quietly restore as "fully rested". Treating it as corrupt (Module 2's
        _is_valid_energy does the same) is the honest reading: a value with no
        position on the scale is not a value to clamp.
        """
        value = float(raw)                      # TypeError/ValueError -> caller
        if not math.isfinite(value):
            raise ValueError(f"non-finite value {raw!r}")
        if value < low:
            return low
        if value > high:
            return high
        return value

    def _write_json_atomic(self, path: Path, data: Dict) -> None:
        """Atomic write: temp file in same dir, then os.replace (POSIX-atomic).

        Resilient to crashes mid-write — a crash leaves either the old or the
        new complete file, never a torn one. This is plumbing robustness, not
        logic.
        """
        self.state_dir.mkdir(parents=True, exist_ok=True)
        tmp_fd, tmp_name = tempfile.mkstemp(
            dir=str(self.state_dir), prefix=path.name + ".", suffix=".tmp"
        )
        os.close(tmp_fd)
        tmp_path = Path(tmp_name)
        try:
            tmp_path.write_text(json.dumps(data, indent=2))
            os.replace(tmp_path, path)
        except Exception:
            tmp_path.unlink(missing_ok=True)
            raise

    # -- aria_state.json: PAD + Energy ----------------------------------------

    def load_pad(self) -> PADState:
        """Restore PAD, clamped to the locked [0.0, 1.0] bound (v4 Layer 1).

        A corrupt or hand-edited file cannot seed an out-of-range axis into a
        live session. Unusable entries (non-numeric, NaN, ±inf) fall back to the
        baseline, as before.
        """
        data = self._read_json(self.state_file).get(_KEY_PAD, {})
        try:
            return PADState(
                pleasure=self._bounded(
                    data.get("pleasure", PAD_BASELINE[0]), PAD_MIN, PAD_MAX),
                arousal=self._bounded(
                    data.get("arousal", PAD_BASELINE[1]), PAD_MIN, PAD_MAX),
                dominance=self._bounded(
                    data.get("dominance", PAD_BASELINE[2]), PAD_MIN, PAD_MAX),
            )
        except (TypeError, ValueError):
            logger.warning("pad entry corrupt in %s; using baseline", self.state_file)
            return PADState.baseline()

    def save_pad(self, pad: PADState) -> None:
        """Write pad into aria_state.json, preserving sibling modules' keys.

        Drops the superseded `relationship_depth` and legacy `needs` keys
        (ResLog §10 / Addendum §3) so they are not perpetuated; keeps any other
        keys it does not own (e.g. voiceprint_enrolled, first_run_complete).
        """
        data = self._read_json(self.state_file)
        data[_KEY_PAD] = pad.as_dict()
        for key in _SUPERSEDED_KEYS:
            data.pop(key, None)
        self._write_json_atomic(self.state_file, data)

    def load_energy(self) -> float:
        """Restore Energy, clamped to [ENERGY_MIN, ENERGY_MAX] (0.0-100.0).

        Note the clamp is more informative than a reject: a file saying -50
        restores as 0.0 ("empty"), preserving the direction the file recorded,
        where Module 2's own restore guard would have discarded it and booted at
        full. Unusable entries (non-numeric, NaN, ±inf) still fall back to the
        default.
        """
        raw = self._read_json(self.state_file).get(_KEY_ENERGY, DEFAULT_ENERGY)
        try:
            return self._bounded(raw, ENERGY_MIN, ENERGY_MAX)
        except (TypeError, ValueError):
            logger.warning("energy entry corrupt in %s; using default", self.state_file)
            return DEFAULT_ENERGY

    def save_energy(self, energy: float) -> None:
        data = self._read_json(self.state_file)
        data[_KEY_ENERGY] = float(energy)
        for key in _SUPERSEDED_KEYS:
            data.pop(key, None)
        self._write_json_atomic(self.state_file, data)

    def load_last_applied_valence(self) -> Optional[str]:
        """Returns the raw string last written by save_last_applied_valence,
        or None if the key is missing or the file doesn't exist yet.

        This module stores the value as an opaque string and does not know
        what it means (Module 11 "owns no meaning" per ARIA_Resolution_Log.md
        item 4) — it does not import or reference Module 1's Valence enum,
        and it does not validate what a "valid" valence string looks like.
        That is Module 1 (PAD_Engine)'s concern, not this module's.
        """
        value = self._read_json(self.state_file).get(_KEY_LAST_APPLIED_VALENCE)
        if value is None:
            return None
        return str(value)

    def save_last_applied_valence(self, valence: Optional[str]) -> None:
        data = self._read_json(self.state_file)
        data[_KEY_LAST_APPLIED_VALENCE] = valence if valence is None else str(valence)
        for key in _SUPERSEDED_KEYS:
            data.pop(key, None)
        self._write_json_atomic(self.state_file, data)

    def load_self_entity_id(self) -> Optional[str]:
        """Returns the persisted self-referential EntityNode id, or None on
        first run. Stored as an opaque string — this module owns no meaning
        about what the id refers to (the graph owns that)."""
        value = self._read_json(self.state_file).get(_KEY_SELF_ENTITY_ID)
        if value is None:
            return None
        return str(value)

    def save_self_entity_id(self, node_id: str) -> None:
        """Persist the self-referential EntityNode id. Called once at first
        startup when the node is created; not part of the periodic save cadence
        (the id never changes after creation)."""
        data = self._read_json(self.state_file)
        data[_KEY_SELF_ENTITY_ID] = str(node_id)
        for key in _SUPERSEDED_KEYS:
            data.pop(key, None)
        self._write_json_atomic(self.state_file, data)

    # -- self_model.json: narrowed self-model working-state --------------------

    def load_self_model(self) -> SelfModel:
        data = self._read_json(self.self_model_file)
        flags = {name: False for name in CONSISTENCY_FLAG_NAMES}
        flags.update({str(k): bool(v) for k, v in data.get("consistency_flags", {}).items()})
        record = [str(x) for x in data.get("quality_record", [])]
        return SelfModel(
            quality_record=record[-QUALITY_RECORD_MAX:],  # keep rolling window
            consistency_flags=flags,
            recent_learning_user=str(data.get("recent_learning_user", "")),
            recent_learning_self=str(data.get("recent_learning_self", "")),
        )

    def save_self_model(self, sm: SelfModel) -> None:
        # Clamp the rolling window on save as a safety net (Module 6 owns the
        # invariant live; this just guarantees we never persist more than 20).
        record = list(sm.quality_record)[-QUALITY_RECORD_MAX:]
        data = {
            "quality_record": record,
            "consistency_flags": {k: bool(v) for k, v in sm.consistency_flags.items()},
            "recent_learning_user": str(sm.recent_learning_user),
            "recent_learning_self": str(sm.recent_learning_self),
        }
        self._write_json_atomic(self.self_model_file, data)

    # -- convenience: whole-state snapshot / restore --------------------------

    def load_all(self) -> Tuple[PADState, float, SelfModel, Optional[str]]:
        return self.load_pad(), self.load_energy(), self.load_self_model(), self.load_last_applied_valence()

    def save_all(
        self,
        pad: PADState,
        energy: float,
        self_model: SelfModel,
        last_applied_valence: Optional[str] = None,
    ) -> None:
        """Flush everything. The Daemon calls this on cadence and on shutdown."""
        # Two files, so a read-modify-write on aria_state.json (pad+energy+
        # last_applied_valence share it) plus one write to self_model.json.
        data = self._read_json(self.state_file)
        data[_KEY_PAD] = pad.as_dict()
        data[_KEY_ENERGY] = float(energy)
        data[_KEY_LAST_APPLIED_VALENCE] = (
            last_applied_valence if last_applied_valence is None else str(last_applied_valence)
        )
        for key in _SUPERSEDED_KEYS:
            data.pop(key, None)
        self._write_json_atomic(self.state_file, data)
        self.save_self_model(self_model)


# ---------------------------------------------------------------------------
# Smoke test: `python state_manager.py` — round-trips through a temp dir.
# Uses only this module; no dependency on Modules 1/2/6/8 (built later).
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import shutil
    import tempfile as _tf

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    tmp = Path(_tf.mkdtemp(prefix="aria_state_smoke_"))
    try:
        sm = StateManager(state_dir=tmp)

        # 1. Fresh load returns spec defaults.
        pad, energy, model = sm.load_all()[:3]
        assert pad == PADState.baseline(), pad
        assert energy == DEFAULT_ENERGY, energy
        assert model == SelfModel.default(), model
        last_valence = sm.load_last_applied_valence()
        assert last_valence is None, last_valence
        print("defaults OK:", pad, round(energy, 2), model, last_valence)

        # 2. Round-trip a populated state, including a non-null valence.
        pad = PADState(0.62, 0.40, 0.71)
        energy = 43.5
        model = SelfModel(
            quality_record=["responded_well", "poorly"] * 12,  # 24 entries -> clamps to 20
            consistency_flags={n: True for n in CONSISTENCY_FLAG_NAMES},
            recent_learning_user="frustrated about deploy",
            recent_learning_self="over-explaining when tired",
        )
        sm.save_all(pad, energy, model, "negative")

        pad2, energy2, model2, valence2 = sm.load_all()
        assert pad2 == pad, (pad2, pad)
        assert energy2 == energy, (energy2, energy)
        assert len(model2.quality_record) == QUALITY_RECORD_MAX, len(model2.quality_record)
        assert model2.consistency_flags == model.consistency_flags
        assert model2.recent_learning_user == model.recent_learning_user
        assert valence2 == "negative", valence2
        print("round-trip OK; quality_record clamped to", len(model2.quality_record))
        print("last_applied_valence round-trip (non-null) OK:", valence2)

        # 2b. Round-trip None explicitly (e.g. no PADDelta applied yet).
        sm.save_last_applied_valence(None)
        assert sm.load_last_applied_valence() is None
        print("last_applied_valence round-trip (None) OK")

        # 3. Sibling keys preserved, superseded keys dropped.
        sm.state_file.write_text(json.dumps({
            "pad": {"pleasure": 0.1, "arousal": 0.2, "dominance": 0.3},
            "energy": 10.0,
            "last_applied_valence": "positive",
            "voiceprint_enrolled": True,      # sibling module — must survive
            "first_run_complete": True,        # sibling module — must survive
            "relationship_depth": 0.73,        # superseded (ResLog §10) — must drop
            "needs": {"connection": 0.5},      # legacy — must drop
        }))
        sm.save_pad(PADState(0.55, 0.45, 0.58))
        disk = json.loads(sm.state_file.read_text())
        assert disk.get("voiceprint_enrolled") is True, "sibling key clobbered"
        assert disk.get("first_run_complete") is True, "sibling key clobbered"
        assert disk.get("last_applied_valence") == "positive", "sibling key clobbered"
        assert "relationship_depth" not in disk, "superseded key not dropped"
        assert "needs" not in disk, "legacy key not dropped"
        print("key-preservation OK; disk keys:", sorted(disk))

        # 4. Corrupt file -> defaults, no crash.
        sm.self_model_file.write_text("{ not json")
        model3 = sm.load_self_model()
        assert model3 == SelfModel.default(), model3
        print("corrupt-file OK (fell back to default)")

        print("\nALL SMOKE TESTS PASSED")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
