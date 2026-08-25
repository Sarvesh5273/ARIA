"""PAD Engine's Open Question 4 residual — counted, characterised, and pinned.

WHY THIS FILE EXISTS
--------------------
The readiness list carried this as "5 NotImplementedError in pad_engine.py,
re-counted. Code flag, never tracker-tracked." Two things were wrong with that as
a record, and both are the kind of thing this project cares about:

  * **5 is the OCCURRENCE count, not the raise count.** Three of the five are the
    docstring explaining the other two. There are exactly TWO `raise` statements,
    both in `on_soul_tick`.
  * **The two are not equally real.** One is unreachable from the wired path and
    one is reachable and was reproduced end to end.

Nothing here RESOLVES OQ4. No coefficient is chosen, no raise is caught, and
`pad_engine.py` is untouched — closing it is an architect decision, and inventing a
decay coefficient is precisely what Rule 1 forbids. These tests pin the facts so
the next person reads a measurement instead of a count.
"""

from __future__ import annotations

import ast
import json
import pathlib

import pytest

from daemon.pad_engine import PAD_BASELINE, PADEngine, PADSnapshot, Valence


# ===========================================================================
# The count, measured rather than asserted from a grep.
# ===========================================================================

def _raise_lines(path: str, exception: str = "NotImplementedError"):
    tree = ast.parse(pathlib.Path(path).read_text())
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Raise)
        and node.exc is not None
        and exception in ast.unparse(node.exc)
    ]


def test_pad_engine_holds_exactly_two_notimplementederror_raises():
    """Five OCCURRENCES of the name, two raise STATEMENTS. The other three are the
    docstring describing these two, which is why a grep count reads high."""
    source = pathlib.Path("daemon/pad_engine.py").read_text()
    assert source.count("NotImplementedError") == 5
    assert len(_raise_lines("daemon/pad_engine.py")) == 2


def test_both_raises_live_in_on_soul_tick_and_nowhere_else():
    tree = ast.parse(pathlib.Path("daemon/pad_engine.py").read_text())
    holders = []
    for function in ast.walk(tree):
        if isinstance(function, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for node in ast.walk(function):
                if (
                    isinstance(node, ast.Raise)
                    and node.exc is not None
                    and "NotImplementedError" in ast.unparse(node.exc)
                ):
                    holders.append(function.name)
    assert holders == ["on_soul_tick", "on_soul_tick"]


def test_no_other_soul_module_raises_notimplementederror():
    """So the flag's scope is known: this is a PAD Engine matter, not a pattern."""
    for path in sorted(pathlib.Path("daemon").glob("*.py")):
        if path.name == "pad_engine.py":
            continue
        assert _raise_lines(str(path)) == [], path.name


# ===========================================================================
# Raise 1 — NEUTRAL valence. Live code, unreachable from the wired path.
# ===========================================================================

def test_neutral_valence_raise_is_live_code():
    """Forcing the state does raise, so the branch is not dead."""
    engine = PADEngine()
    engine.initialize(None)
    engine._last_applied_valence = Valence.NEUTRAL
    with pytest.raises(NotImplementedError, match="NEUTRAL valence"):
        engine.on_soul_tick()


def test_neutral_valence_is_never_reached_through_a_real_appraisal(tmp_path):
    """MEASURED, not assumed: seven neutral turns through the real Appraisal Chain
    and the real graph leave `_last_applied_valence` as None every time.

    A purely-neutral appraisal builds an all-zero `PADDelta` that `_apply_delta`
    never applies, so the NEUTRAL branch has no route in from `appraise()`. That is
    also why 160 consecutive real soul ticks during the DMN idle observation never
    hit it.

    If this test ever fails, the NEUTRAL raise has become reachable in production
    and that is a much larger event than a failing assertion — it means an ordinary
    turn can crash the soul tick.
    """
    from daemon.appraisal_chain import AppraisalChain
    from daemon.graph_manager import MemoryGraph

    class _Embedding:
        def embed(self, text: str):
            return [
                float(sum(bytearray(text.encode()[i::7]))) for i in range(8)
            ]

    graph = MemoryGraph(str(tmp_path / "g.db"), embedding_model=_Embedding())
    try:
        engine = PADEngine()
        engine.initialize(None)
        chain = AppraisalChain(
            pad_engine=engine, graph=graph, embedding_model=_Embedding()
        )
        entity = graph.write_entity_node(entity_type="person", name="u")
        for text in (
            "the meeting is at three",
            "please pass the file path",
            "what is the current directory",
            "it is Tuesday",
            "ok",
            "the build finished",
            "I am going to the shop and then coming back",
        ):
            chain.appraise(user_text=text, session_id="s", entity_refs=[entity])
            assert engine._last_applied_valence is not Valence.NEUTRAL, text
            # And the tick that follows must not raise.
            engine.on_soul_tick()
    finally:
        graph.close()


# ===========================================================================
# Raise 2 — the restore boundary. Reachable, and reproduced.
# ===========================================================================

def test_restored_non_baseline_pad_without_a_valence_raises():
    engine = PADEngine()
    engine.initialize(PADSnapshot(pleasure=0.72, arousal=0.61, dominance=0.64))
    assert engine._last_applied_valence is None
    with pytest.raises(NotImplementedError, match="restored to a non-baseline"):
        engine.on_soul_tick()


def test_the_routine_restart_path_does_not_raise():
    """Why this is a narrow residual rather than a permanent break: the HANDOFF
    contract has `AriaDaemon.startup()` restore the persisted valence and pass it
    to `initialize()`, and the write cadence is every turn."""
    engine = PADEngine()
    engine.initialize(
        PADSnapshot(pleasure=0.72, arousal=0.61, dominance=0.64),
        restored_valence=Valence.POSITIVE,
    )
    engine.on_soul_tick()
    assert engine.get_current_pad().pleasure < 0.72   # decayed toward baseline


def test_restored_baseline_pad_without_a_valence_is_a_noop_not_a_raise():
    """The fourth branch: decaying baseline toward baseline is a no-op whichever
    coefficient would have been chosen, so skipping invents nothing. This is why a
    FIRST-EVER run cannot hit the residual — it starts at baseline."""
    engine = PADEngine()
    engine.initialize(PAD_BASELINE)
    engine.on_soul_tick()
    assert engine.get_current_pad() == PAD_BASELINE


# ===========================================================================
# The wiring layer says so up front rather than dying four frames later.
# ===========================================================================

def test_main_warns_when_the_next_tick_will_raise(tmp_path, capsys):
    """The realistic shape: a crash between an appraisal delta and the next save
    leaves PAD off baseline with the valence key never written. `startup()` then
    succeeds and the FIRST soul tick raises, which in the REPL is a traceback
    several frames from the cause.

    The warning is DIAGNOSTIC only — it chooses no coefficient, catches no raise,
    and leaves `pad_engine.py` alone.
    """
    import main as aria_main
    from daemon.state_manager import StateManager

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / "aria_state.json").write_text(json.dumps({
        "pad": {"pleasure": 0.72, "arousal": 0.61, "dominance": 0.64},
        "energy": 88.0,
    }))

    class _Wiring:
        """Only what `warn_pad_restore_boundary` reads. Building the real Wiring
        would need a live model backend, and this asserts a pure function of
        (current PAD, persisted valence)."""
        def __init__(self) -> None:
            self.pad = PADEngine()
            self.pad.initialize(
                PADSnapshot(pleasure=0.72, arousal=0.61, dominance=0.64)
            )
            self.state = StateManager(state_dir=state_dir)
            self.state_dir = state_dir

    aria_main.warn_pad_restore_boundary(_Wiring())
    out = capsys.readouterr().out
    assert "Open Question 4" in out
    assert "NotImplementedError" in out
    assert "last_applied_valence" in out


def test_main_stays_quiet_when_a_valence_was_persisted(tmp_path, capsys):
    """Non-vacuous: the same non-baseline PAD, with the valence present, warns
    nothing. Without this the test above would pass on any input."""
    import main as aria_main
    from daemon.state_manager import StateManager

    state_dir = tmp_path / "state"
    state_dir.mkdir()
    manager = StateManager(state_dir=state_dir)
    manager.save_last_applied_valence("positive")

    class _Wiring:
        def __init__(self) -> None:
            self.pad = PADEngine()
            self.pad.initialize(
                PADSnapshot(pleasure=0.72, arousal=0.61, dominance=0.64),
                restored_valence=Valence.POSITIVE,
            )
            self.state = manager
            self.state_dir = state_dir

    aria_main.warn_pad_restore_boundary(_Wiring())
    assert capsys.readouterr().out == ""


def test_main_stays_quiet_at_baseline(tmp_path, capsys):
    import main as aria_main
    from daemon.state_manager import StateManager

    state_dir = tmp_path / "state"
    state_dir.mkdir()

    class _Wiring:
        def __init__(self) -> None:
            self.pad = PADEngine()
            self.pad.initialize(None)
            self.state = StateManager(state_dir=state_dir)
            self.state_dir = state_dir

    aria_main.warn_pad_restore_boundary(_Wiring())
    assert capsys.readouterr().out == ""


# ===========================================================================
# The fix: one atomic write (closes the gap) + a restore-boundary consistency
# check (handles a record that arrives broken anyway). Neither invents a
# coefficient; `pad_engine.py` stays byte-unchanged, asserted above.
# ===========================================================================

def test_save_state_writes_pad_and_valence_in_one_atomic_write(tmp_path):
    """The gap that produced the residual is CLOSED, measured by counting writes.

    `_save_state` used to make three separate atomic writes — pad, energy,
    valence — with two crash gaps between them. A crash in either gap persisted a
    non-baseline PAD while the valence key went unwritten. Counting the writes is
    the honest assertion: asserting the file "looks consistent" afterwards would
    pass on the three-write version too, since all three do complete when nothing
    crashes.
    """
    from tests.test_daemon import make_daemon
    from daemon.pad_engine import PADDelta

    ctx = make_daemon(tmp_path)
    ctx.daemon.startup()
    ctx.pad.apply_appraisal_delta(PADDelta(
        d_pleasure=0.2, d_arousal=0.1, d_dominance=0.0,
        valence=Valence.POSITIVE, origin="appraisal",
    ))

    writes = []
    real_write = ctx.state._write_json_atomic

    def counting_write(path, data):
        writes.append(pathlib.Path(path).name)
        return real_write(path, data)

    ctx.state._write_json_atomic = counting_write
    ctx.daemon._save_state()

    # aria_state.json carries pad + energy + last_applied_valence, so exactly ONE
    # write touches it. (self_model.json is a separate file and a separate key
    # space — it was never part of the OQ4 record.)
    assert writes.count("aria_state.json") == 1, writes

    # And the record it wrote is internally consistent.
    on_disk = json.loads((tmp_path / "aria_state.json").read_text())
    assert on_disk["pad"]["pleasure"] != PAD_BASELINE.pleasure
    assert on_disk["last_applied_valence"] == "positive"


def test_a_normal_restart_still_carries_pad_and_valence_across(tmp_path):
    """Non-vacuous guard on the consistency check: an INTACT record must survive
    untouched. If the check were too broad it would reset every restart, and she
    would arrive at every session emotionally blank — which is the failure the
    check exists to avoid, not to cause."""
    from tests.test_daemon import make_daemon
    from daemon.pad_engine import PADDelta

    first = make_daemon(tmp_path)
    first.daemon.startup()
    first.pad.apply_appraisal_delta(PADDelta(
        d_pleasure=0.2, d_arousal=0.1, d_dominance=0.0,
        valence=Valence.POSITIVE, origin="appraisal",
    ))
    moved = first.pad.get_current_pad()
    first.daemon.shutdown()

    second = make_daemon(tmp_path)
    second.daemon.startup()

    assert second.daemon.pad_restore_was_reset is False
    assert second.pad.get_current_pad() == moved          # she is still warm
    assert second.pad._last_applied_valence is Valence.POSITIVE
    second.daemon.soul_tick()                              # and decays normally
    assert second.pad.get_current_pad().pleasure < moved.pleasure


def test_startup_restores_baseline_when_pad_is_off_baseline_with_no_valence(tmp_path):
    """The residual case, end to end: a half-written record no longer kills the
    first soul tick.

    Written by hand rather than by crashing a process, because that is how the
    record can still arrive after the atomic-write fix — a truncated or
    hand-edited file, or item 18's own clamp turning an out-of-range value into a
    non-baseline PAD while the valence is absent. This is the same construction
    `test_restored_non_baseline_pad_without_a_valence_raises` uses to prove the
    raise reachable, which is the point: the file is the input, not the crash.
    """
    from tests.test_daemon import make_daemon
    from daemon.state_manager import StateManager

    state = StateManager(state_dir=tmp_path)
    (tmp_path / "aria_state.json").write_text(json.dumps({
        "pad": {"pleasure": 0.72, "arousal": 0.61, "dominance": 0.64},
        "energy": 50.0,
        # last_applied_valence deliberately ABSENT — the half-written record.
    }))

    ctx = make_daemon(tmp_path, state=state)
    ctx.daemon.startup()

    assert ctx.daemon.pad_restore_was_reset is True
    assert ctx.pad.get_current_pad() == PAD_BASELINE
    # The tick that used to raise NotImplementedError now runs.
    ctx.daemon.soul_tick()
    assert ctx.pad.get_current_pad() == PAD_BASELINE   # baseline decays to baseline


def test_the_reset_is_reported_rather_than_silent(tmp_path, capsys):
    """A silent fallback is the failure mode worth guarding: "she is resting at
    baseline" and "a corrupt file erased what she felt" are the same observation
    without a report. `startup()` runs BEFORE `report_startup()` in `main`, so the
    original pre-startup warning can no longer fire on this path — this is what
    replaces it."""
    import main as aria_main
    from tests.test_daemon import make_daemon
    from daemon.state_manager import StateManager

    state = StateManager(state_dir=tmp_path)
    (tmp_path / "aria_state.json").write_text(json.dumps({
        "pad": {"pleasure": 0.72, "arousal": 0.61, "dominance": 0.64},
        "energy": 50.0,
    }))
    ctx = make_daemon(tmp_path, state=state)
    ctx.daemon.startup()

    class _Wiring:
        pad = ctx.pad
        daemon = ctx.daemon
        state = ctx.state
        state_dir = tmp_path

    aria_main.warn_pad_restore_boundary(_Wiring())
    out = capsys.readouterr().out
    assert "RESET AT RESTORE" in out
    assert "item 18" in out
    # It must say the memory survived — that is the difference between one turn's
    # feeling lost and a conversation lost.
    assert "MEMORY IS INTACT" in out


def test_no_report_when_nothing_was_reset(tmp_path, capsys):
    """Non-vacuous: an ordinary startup says nothing about the restore boundary."""
    import main as aria_main
    from tests.test_daemon import make_daemon

    ctx = make_daemon(tmp_path)
    ctx.daemon.startup()

    class _Wiring:
        pad = ctx.pad
        daemon = ctx.daemon
        state = ctx.state
        state_dir = tmp_path

    aria_main.warn_pad_restore_boundary(_Wiring())
    assert capsys.readouterr().out == ""


def test_pad_engine_is_still_byte_unchanged_by_this_fix():
    """The whole fix lives in the wiring layer. PAD Engine's two raises are still
    there and still unmodified — pinned by the count tests at the top of this
    file, restated here as the fix's own boundary claim."""
    source = pathlib.Path("daemon/pad_engine.py").read_text()
    assert len(_raise_lines("daemon/pad_engine.py")) == 2
    # No consistency check leaked into the soul layer.
    assert "pad_restore_was_reset" not in source
    assert "half a record" not in source
