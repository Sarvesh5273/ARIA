"""Tests for daemon/state_manager.py — Module 11 (State Manager).

Plain pytest, no hypothesis, no mock library (matching test_pad_engine.py, the
only other file that exercises StateManager). StateManager's whole job is the
filesystem, so these use pytest's `tmp_path` rather than fakes — the same choice
test_pad_engine.py makes for its Task 20 round-trip. Nothing here touches the
real ~/.local/aria/state; every StateManager is constructed with an explicit
state_dir.

Until now Module 11's only verification was the `__main__` smoke block inside
the module itself, which pytest never runs. These tests cover that block's
ground plus the paths it skipped entirely: Energy bounds, PAD bounds, corrupt
and non-numeric entries, atomic-write behaviour on a failed write, and load
independence.

RESTORE IS DEFENSIVE (architect ruling): PAD axes clamp to the locked [0.0, 1.0]
(v4 Layer 1) and Energy clamps to [0.0, 100.0], so a hand-edited or corrupted
file cannot seed an out-of-range value into a live session. Unusable entries —
non-numeric, NaN, ±inf — still fall back to the spec default rather than being
clamped, since a value with no position on the scale is not a value to bound.
SAVE is unchanged: it records what the owning module hands it (Module 1 clamps
live PAD itself); the clamp is a read-boundary check, so an out-of-range save
followed by a load is deliberately asymmetric.
"""

import json
from pathlib import Path

import pytest

from daemon.state_manager import (
    CONSISTENCY_FLAG_NAMES,
    DEFAULT_ENERGY,
    ENERGY_MAX,
    ENERGY_MIN,
    PAD_BASELINE,
    PAD_MAX,
    PAD_MIN,
    QUALITY_RECORD_MAX,
    PADState,
    SelfModel,
    StateManager,
)


def make_manager(tmp_path, subdir=None):
    """A StateManager rooted in an isolated temp dir. `subdir` exercises the
    mkdir-on-demand path (the dir does not exist until a save)."""
    return StateManager(state_dir=(tmp_path / subdir) if subdir else tmp_path)


def write_state_file(sm, payload):
    """Hand-write aria_state.json, as a previous run would have left it."""
    sm.state_dir.mkdir(parents=True, exist_ok=True)
    sm.state_file.write_text(json.dumps(payload))


# ===========================================================================
# 1) No file yet — every loader returns the spec default
# ===========================================================================

def test_load_returns_defaults_when_no_file_exists(tmp_path):
    sm = make_manager(tmp_path)
    assert not sm.state_file.exists()

    assert sm.load_pad() == PADState.baseline()
    assert sm.load_energy() == pytest.approx(DEFAULT_ENERGY)
    assert sm.load_self_model() == SelfModel.default()
    assert sm.load_last_applied_valence() is None
    assert sm.load_self_entity_id() is None

    # Reading must not create anything — first run stays clean until a save.
    assert not sm.state_file.exists()
    assert not sm.self_model_file.exists()


def test_load_all_returns_the_four_defaults_in_order(tmp_path):
    pad, energy, model, valence = make_manager(tmp_path).load_all()
    assert pad == PADState.baseline()
    assert pad.pleasure == pytest.approx(PAD_BASELINE[0])
    assert energy == pytest.approx(DEFAULT_ENERGY)
    assert model == SelfModel.default()
    assert all(v is False for v in model.consistency_flags.values())
    assert valence is None


def test_default_self_model_has_every_consistency_flag_false(tmp_path):
    model = make_manager(tmp_path).load_self_model()
    assert set(model.consistency_flags) == set(CONSISTENCY_FLAG_NAMES)
    assert model.quality_record == []
    assert model.recent_learning_user == ""
    assert model.recent_learning_self == ""


# ===========================================================================
# 2) Restore from a valid snapshot on disk
# ===========================================================================

def test_restores_from_valid_snapshot_json(tmp_path):
    sm = make_manager(tmp_path)
    write_state_file(sm, {
        "pad": {"pleasure": 0.62, "arousal": 0.40, "dominance": 0.71},
        "energy": 43.5,
        "last_applied_valence": "negative",
        "self_entity_id": "node-abc",
    })
    sm.self_model_file.write_text(json.dumps({
        "quality_record": ["responded_well", "poorly"],
        "consistency_flags": {"acknowledged_mistake": True},
        "recent_learning_user": "frustrated about deploy",
        "recent_learning_self": "over-explaining when tired",
    }))

    assert sm.load_pad() == PADState(0.62, 0.40, 0.71)
    assert sm.load_energy() == pytest.approx(43.5)
    assert sm.load_last_applied_valence() == "negative"
    assert sm.load_self_entity_id() == "node-abc"

    model = sm.load_self_model()
    assert model.quality_record == ["responded_well", "poorly"]
    assert model.consistency_flags["acknowledged_mistake"] is True
    # Absent flags still materialise as False, never missing keys.
    assert model.consistency_flags["honest_when_uncomfortable"] is False
    assert set(model.consistency_flags) == set(CONSISTENCY_FLAG_NAMES)
    assert model.recent_learning_user == "frustrated about deploy"


def test_save_all_then_load_all_round_trips(tmp_path):
    sm = make_manager(tmp_path)
    pad = PADState(0.11, 0.22, 0.33)
    model = SelfModel(
        quality_record=["adequately"],
        consistency_flags={name: True for name in CONSISTENCY_FLAG_NAMES},
        recent_learning_user="u",
        recent_learning_self="s",
    )
    sm.save_all(pad, 43.5, model, "positive")

    pad2, energy2, model2, valence2 = sm.load_all()
    assert pad2 == pad
    assert energy2 == pytest.approx(43.5)
    assert model2 == model
    assert valence2 == "positive"


def test_none_valence_round_trips_as_none(tmp_path):
    sm = make_manager(tmp_path)
    sm.save_last_applied_valence("negative")
    assert sm.load_last_applied_valence() == "negative"
    sm.save_last_applied_valence(None)   # e.g. no PADDelta applied yet
    assert sm.load_last_applied_valence() is None


def test_corrupt_json_falls_back_to_defaults_without_raising(tmp_path):
    sm = make_manager(tmp_path)
    write_state_file(sm, {})               # ensure the dir exists
    sm.state_file.write_text("{ not json")
    sm.self_model_file.write_text("{ not json")

    assert sm.load_pad() == PADState.baseline()
    assert sm.load_energy() == pytest.approx(DEFAULT_ENERGY)
    assert sm.load_self_model() == SelfModel.default()
    assert sm.load_last_applied_valence() is None


def test_non_numeric_entries_fall_back_to_defaults(tmp_path):
    # Type coercion failure is the ONE thing restore does reject: it falls back
    # to the spec default rather than propagating a junk value.
    sm = make_manager(tmp_path)
    write_state_file(sm, {
        "pad": {"pleasure": "abc", "arousal": 0.4, "dominance": 0.7},
        "energy": "not-a-number",
    })
    assert sm.load_pad() == PADState.baseline()   # whole entry, not per-field
    assert sm.load_energy() == pytest.approx(DEFAULT_ENERGY)


def test_partial_pad_entry_fills_missing_axes_from_baseline(tmp_path):
    sm = make_manager(tmp_path)
    write_state_file(sm, {"pad": {"pleasure": 0.9}})
    pad = sm.load_pad()
    assert pad.pleasure == pytest.approx(0.9)
    assert pad.arousal == pytest.approx(PAD_BASELINE[1])
    assert pad.dominance == pytest.approx(PAD_BASELINE[2])


# ===========================================================================
# 3) Atomic writes — no torn or partial files
# ===========================================================================

def test_save_creates_state_dir_on_demand(tmp_path):
    sm = make_manager(tmp_path, subdir="nested/deeper")
    assert not sm.state_dir.exists()
    sm.save_energy(50.0)
    assert sm.state_file.exists()
    assert sm.load_energy() == pytest.approx(50.0)


def test_successful_save_leaves_no_temp_files(tmp_path):
    sm = make_manager(tmp_path)
    sm.save_all(PADState(0.6, 0.4, 0.7), 55.0, SelfModel.default(), "positive")
    sm.save_pad(PADState(0.5, 0.5, 0.5))
    sm.save_energy(10.0)

    assert list(tmp_path.glob("*.tmp")) == []
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "aria_state.json", "self_model.json"]
    # Every write lands as complete, parseable JSON.
    assert isinstance(json.loads(sm.state_file.read_text()), dict)
    assert isinstance(json.loads(sm.self_model_file.read_text()), dict)


def test_failed_write_leaves_the_previous_file_intact(tmp_path, monkeypatch):
    """The atomicity guarantee that matters: a crash mid-write leaves either the
    old complete file or the new one, never a torn one. Writing to the temp file
    is made to fail, so os.replace never runs."""
    sm = make_manager(tmp_path)
    sm.save_energy(42.0)
    before = sm.state_file.read_text()

    real_write_text = Path.write_text

    def exploding_write_text(self, *args, **kwargs):
        if self.name.endswith(".tmp"):          # only the atomic temp file
            raise OSError("simulated disk full")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", exploding_write_text)
    with pytest.raises(OSError):
        sm.save_energy(99.0)
    monkeypatch.undo()

    assert sm.state_file.read_text() == before        # byte-identical, untorn
    assert sm.load_energy() == pytest.approx(42.0)    # old value survived
    assert list(tmp_path.glob("*.tmp")) == []         # temp file cleaned up


def test_save_preserves_sibling_keys_and_drops_superseded_ones(tmp_path):
    # Other modules share aria_state.json; a save must not clobber their keys.
    # relationship_depth (ResLog item 10) and legacy `needs` (Addendum §3) are
    # superseded and must be dropped rather than perpetuated.
    sm = make_manager(tmp_path)
    write_state_file(sm, {
        "pad": {"pleasure": 0.1, "arousal": 0.2, "dominance": 0.3},
        "energy": 10.0,
        "last_applied_valence": "positive",
        "voiceprint_enrolled": True,
        "first_run_complete": True,
        "relationship_depth": 0.73,
        "needs": {"connection": 0.5},
    })
    sm.save_pad(PADState(0.55, 0.45, 0.58))

    disk = json.loads(sm.state_file.read_text())
    assert disk["voiceprint_enrolled"] is True
    assert disk["first_run_complete"] is True
    assert disk["last_applied_valence"] == "positive"
    assert disk["energy"] == pytest.approx(10.0)
    assert "relationship_depth" not in disk
    assert "needs" not in disk


# ===========================================================================
# 4) Load independence
#
# NOTE: StateManager has no get_current() / get_snapshot() pair — it is
# load/save plumbing with no live in-memory state to hand out (PAD_Engine owns
# get_current_pad()). The equivalent guarantee is that every load reads the file
# afresh and returns an INDEPENDENT object, so a caller mutating what it got
# back cannot corrupt the file or a later load.
# ===========================================================================

def test_each_load_returns_an_independent_object(tmp_path):
    sm = make_manager(tmp_path)
    sm.save_all(PADState(0.6, 0.4, 0.7), 55.0,
                SelfModel(quality_record=["adequately"],
                          consistency_flags={n: False for n in CONSISTENCY_FLAG_NAMES}),
                None)

    first = sm.load_pad()
    second = sm.load_pad()
    assert first == second
    assert first is not second          # a fresh object per load

    first.pleasure = 0.0                # caller mutates its copy
    assert sm.load_pad().pleasure == pytest.approx(0.6)   # disk untouched
    assert second.pleasure == pytest.approx(0.6)          # sibling untouched


def test_loaded_self_model_containers_are_not_shared(tmp_path):
    sm = make_manager(tmp_path)
    sm.save_self_model(SelfModel(
        quality_record=["responded_well"],
        consistency_flags={n: False for n in CONSISTENCY_FLAG_NAMES},
    ))
    a = sm.load_self_model()
    b = sm.load_self_model()
    assert a == b
    assert a.quality_record is not b.quality_record
    assert a.consistency_flags is not b.consistency_flags

    a.quality_record.append("poorly")
    a.consistency_flags["acknowledged_mistake"] = True
    fresh = sm.load_self_model()
    assert fresh.quality_record == ["responded_well"]
    assert fresh.consistency_flags["acknowledged_mistake"] is False


def test_saved_object_is_decoupled_from_the_file(tmp_path):
    # Mutating the object AFTER saving must not retroactively change the file.
    sm = make_manager(tmp_path)
    pad = PADState(0.2, 0.3, 0.4)
    sm.save_pad(pad)
    pad.pleasure = 0.99
    assert sm.load_pad() == PADState(0.2, 0.3, 0.4)


# ===========================================================================
# 5) PAD values outside [0, 1] — CURRENT behaviour is neither clamp nor reject
# ===========================================================================

def test_out_of_range_pad_is_clamped_on_restore(tmp_path):
    # The headline case: pleasure=5.0 clamps to 1.0. PAD is bounded to [0,1]
    # (v4 Layer 1); a corrupted file cannot exceed it.
    sm = make_manager(tmp_path)
    write_state_file(sm, {
        "pad": {"pleasure": 5.0, "arousal": -3.0, "dominance": 1.5},
    })
    pad = sm.load_pad()
    assert pad.pleasure == pytest.approx(1.0)     # 5.0  -> PAD_MAX
    assert pad.arousal == pytest.approx(0.0)      # -3.0 -> PAD_MIN
    assert pad.dominance == pytest.approx(1.0)    # 1.5  -> PAD_MAX


def test_in_range_pad_passes_through_unchanged(tmp_path):
    # Valid values are untouched — clamping must not perturb good data.
    sm = make_manager(tmp_path)
    write_state_file(sm, {
        "pad": {"pleasure": 0.5, "arousal": 0.45, "dominance": 0.58},
    })
    assert sm.load_pad() == PADState(0.5, 0.45, 0.58)


def test_pad_bounds_are_inclusive(tmp_path):
    sm = make_manager(tmp_path)
    for pleasure, arousal, dominance in [(0.0, 0.0, 0.0), (1.0, 1.0, 1.0)]:
        sm.save_pad(PADState(pleasure, arousal, dominance))
        assert sm.load_pad() == PADState(pleasure, arousal, dominance)


def test_pad_clamp_is_a_read_boundary_not_a_write_one(tmp_path):
    # save records what the owning module hands over (Module 1 clamps live PAD
    # itself); the defence is on the way back IN. The asymmetry is deliberate.
    sm = make_manager(tmp_path)
    sm.save_pad(PADState(5.0, -3.0, 0.5))
    on_disk = json.loads(sm.state_file.read_text())["pad"]
    assert on_disk["pleasure"] == pytest.approx(5.0)      # stored verbatim
    assert sm.load_pad() == PADState(1.0, 0.0, 0.5)       # clamped on restore


def test_non_finite_pad_is_treated_as_corrupt_not_clamped(tmp_path):
    # json.loads accepts a literal NaN/Infinity, and NaN survives a naive
    # max(low, min(high, v)) as `high` — which would silently restore as
    # "maximum pleasure". A value with no position on the scale is corrupt.
    sm = make_manager(tmp_path)
    sm.state_dir.mkdir(parents=True, exist_ok=True)
    for literal in ("NaN", "Infinity", "-Infinity"):
        sm.state_file.write_text(
            '{"pad": {"pleasure": %s, "arousal": 0.4, "dominance": 0.7}}' % literal)
        assert sm.load_pad() == PADState.baseline(), literal


# ===========================================================================
# 6) Energy outside [0, 100] — same: not clamped, not rejected
# ===========================================================================

def test_out_of_range_energy_is_clamped_on_restore(tmp_path):
    # The two headline cases: -50.0 -> 0.0 and 150.0 -> 100.0.
    sm = make_manager(tmp_path)

    write_state_file(sm, {"energy": -50.0})
    assert sm.load_energy() == pytest.approx(ENERGY_MIN)     # 0.0

    write_state_file(sm, {"energy": 150.0})
    assert sm.load_energy() == pytest.approx(ENERGY_MAX)     # 100.0

    write_state_file(sm, {"energy": 999.0})
    assert sm.load_energy() == pytest.approx(ENERGY_MAX)


def test_in_range_energy_passes_through_unchanged(tmp_path):
    sm = make_manager(tmp_path)
    write_state_file(sm, {"energy": 75.0})
    assert sm.load_energy() == pytest.approx(75.0)


def test_energy_bounds_are_inclusive(tmp_path):
    sm = make_manager(tmp_path)
    for energy in (ENERGY_MIN, 25.0, ENERGY_MAX):
        sm.save_energy(energy)
        assert sm.load_energy() == pytest.approx(energy)


def test_clamped_energy_preserves_the_direction_the_file_recorded(tmp_path):
    """A clamp is more informative than a reject. Module 2's own restore guard
    (EnergyTracker._is_valid_energy) discards an out-of-range value and boots at
    ENERGY_BASELINE — so a file saying -50 would have come back as "fully
    rested". Clamping keeps "empty" meaning empty."""
    sm = make_manager(tmp_path)
    write_state_file(sm, {"energy": -50.0})
    restored = sm.load_energy()
    assert restored == pytest.approx(0.0)
    assert restored != pytest.approx(DEFAULT_ENERGY)


def test_non_finite_energy_is_treated_as_corrupt_not_clamped(tmp_path):
    sm = make_manager(tmp_path)
    sm.state_dir.mkdir(parents=True, exist_ok=True)
    for literal in ("NaN", "Infinity", "-Infinity"):
        sm.state_file.write_text('{"energy": %s}' % literal)
        assert sm.load_energy() == pytest.approx(DEFAULT_ENERGY), literal


def test_load_all_applies_the_same_clamps(tmp_path):
    # load_all() must not be a second, unguarded path onto the same data.
    sm = make_manager(tmp_path)
    write_state_file(sm, {
        "pad": {"pleasure": 5.0, "arousal": -3.0, "dominance": 0.5},
        "energy": 150.0,
    })
    pad, energy, _model, _valence = sm.load_all()
    assert pad == PADState(1.0, 0.0, 0.5)
    assert energy == pytest.approx(ENERGY_MAX)


def test_integer_energy_is_coerced_to_float(tmp_path):
    sm = make_manager(tmp_path)
    write_state_file(sm, {"energy": 43})
    energy = sm.load_energy()
    assert isinstance(energy, float)
    assert energy == pytest.approx(43.0)


# ===========================================================================
# Rolling window — the one clamp this module DOES apply (v4 "last 20
# self-assessments"), enforced on both the read and the write side.
# ===========================================================================

def test_quality_record_clamped_to_twenty_on_save(tmp_path):
    sm = make_manager(tmp_path)
    sm.save_self_model(SelfModel(quality_record=["responded_well"] * 24))
    on_disk = json.loads(sm.self_model_file.read_text())["quality_record"]
    assert len(on_disk) == QUALITY_RECORD_MAX


def test_quality_record_clamped_to_twenty_on_load(tmp_path):
    sm = make_manager(tmp_path)
    sm.state_dir.mkdir(parents=True, exist_ok=True)
    sm.self_model_file.write_text(json.dumps(
        {"quality_record": [f"entry-{i}" for i in range(30)]}))
    record = sm.load_self_model().quality_record
    assert len(record) == QUALITY_RECORD_MAX
    assert record[0] == "entry-10"      # keeps the MOST RECENT 20
    assert record[-1] == "entry-29"


# ===========================================================================
# Boundary: Module 11 "owns no meaning" — no PAD math, no need evaluation, no
# graph, no LLM surface. Structural, mirroring the house boundary tests.
# ===========================================================================

def test_state_manager_owns_no_meaning_surface(tmp_path):
    public = [m for m in dir(StateManager) if not m.startswith("_")]
    for name in public:
        low = name.lower()
        assert "decay" not in low, name
        assert "appraise" not in low and "appraisal" not in low, name
        assert "prompt" not in low and "llm" not in low, name
        assert "graph" not in low and "retrieve" not in low, name
    # Every public method is a load/save (plus the two file-path attributes).
    assert all(n.startswith(("load_", "save_")) for n in public), public


# ===========================================================================
# Primary (user) entity id — added 2026-08-22. An exact mirror of the self
# entity id methods, for the same reason Resolution Log §2 gave the self entity
# one: an EntityNode id that must survive a restart or the graph loses track of
# who it is about.
#
# Without this, every process start invents a new id and one person becomes a
# series of strangers — relational_stage can never advance past OBSERVING and
# nothing is ever first-of-kind twice.
# ===========================================================================

def test_primary_entity_id_defaults_to_none_on_first_run(tmp_path):
    sm = make_manager(tmp_path)
    assert sm.load_primary_entity_id() is None
    # Reading must not create anything, same as every other loader.
    assert not sm.state_file.exists()


def test_primary_entity_id_round_trips_across_instances(tmp_path):
    """The whole point: it survives a process restart. Without this, every start
    invents a new id and one person becomes a series of strangers."""
    make_manager(tmp_path).save_primary_entity_id("user-node-1")
    assert make_manager(tmp_path).load_primary_entity_id() == "user-node-1"


def test_primary_entity_id_restores_from_a_hand_written_snapshot(tmp_path):
    sm = make_manager(tmp_path)
    write_state_file(sm, {
        "self_entity_id": "aria-node",
        "primary_entity_id": "user-node",
    })
    assert sm.load_primary_entity_id() == "user-node"


def test_primary_entity_id_is_stored_as_an_opaque_string(tmp_path):
    """This module owns no meaning about the id; the graph owns that. A
    non-string is coerced rather than validated — same as the self id."""
    sm = make_manager(tmp_path)
    sm.save_primary_entity_id(12345)
    assert sm.load_primary_entity_id() == "12345"


def test_primary_and_self_entity_ids_are_independent_keys(tmp_path):
    """The two must never alias. If they did, Aria's self node and the user's
    node would collide, and every self-referential narrative the DMN writes
    would be written about the user instead."""
    sm = make_manager(tmp_path)
    sm.save_self_entity_id("aria-node")
    sm.save_primary_entity_id("user-node")
    assert sm.load_self_entity_id() == "aria-node"
    assert sm.load_primary_entity_id() == "user-node"

    raw = json.loads(sm.state_file.read_text())
    assert raw["self_entity_id"] == "aria-node"
    assert raw["primary_entity_id"] == "user-node"


def test_saving_primary_entity_id_preserves_sibling_keys(tmp_path):
    """The sibling-key guarantee this module already makes for every writer.
    Writing the id must not clobber PAD, Energy or the self id."""
    sm = make_manager(tmp_path)
    sm.save_pad(PADState(0.7, 0.3, 0.6))
    sm.save_energy(42.0)
    sm.save_last_applied_valence("negative")
    sm.save_self_entity_id("aria-node")

    sm.save_primary_entity_id("user-node")

    assert sm.load_pad() == PADState(0.7, 0.3, 0.6)
    assert sm.load_energy() == pytest.approx(42.0)
    assert sm.load_last_applied_valence() == "negative"
    assert sm.load_self_entity_id() == "aria-node"
    assert sm.load_primary_entity_id() == "user-node"


def test_saving_primary_entity_id_writes_no_extra_files(tmp_path):
    """The state dir holds exactly two files. A new key goes INSIDE
    aria_state.json, never beside it."""
    sm = make_manager(tmp_path)
    sm.save_pad(PADState.baseline())
    sm.save_self_model(SelfModel.default())
    sm.save_primary_entity_id("user-node")
    assert sorted(p.name for p in sm.state_dir.iterdir()) == [
        "aria_state.json", "self_model.json"
    ]
    assert not list(sm.state_dir.glob("*.tmp"))
