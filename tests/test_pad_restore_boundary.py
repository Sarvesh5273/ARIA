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
