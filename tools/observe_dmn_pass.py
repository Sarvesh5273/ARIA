#!/usr/bin/env python3
"""Watch a real DMN idle-consolidation pass happen. Module 6, first execution.

    .venv/bin/python tools/observe_dmn_pass.py
    .venv/bin/python tools/observe_dmn_pass.py --turns 4 --tail 120

WHY THIS EXISTS
---------------
Module 6 is 44 passing tests and, until this ran, had never executed once against
a real graph with real embeddings. Nothing about that was negligence — the idle
window is 8 minutes and it is PINNED by v4, and `main.py` deliberately offers no
command to fake `now`, because a false timestamp written into the graph corrupts
the only memory she has.

So the cheapest high-information action available is to wait. This harness waits
properly: real clock, real graph, real embeddings, real local voice. It fakes
nothing.

WHAT IT DOES, IN ORDER
----------------------
1. Builds the REAL wiring — `main.Wiring`, the same object `main.py` runs. Not a
   reconstruction of it. If the wiring is wrong, this observes the wrong thing.
2. Drives a few real turns through `route_inbound_turn`, because a DMN pass over
   an empty graph consolidates nothing and would prove nothing. Each turn is a
   real appraisal, a real EventNode, and a real self-monitoring buffer item. At
   least three turns, so at least one buffer item has a NEXT turn to read as the
   observed reaction — that is what Step 1's anti-flattery quality grade needs.
3. Stops talking, and drives BOTH CLOCKS on their real intervals for the whole
   idle window, exactly as `run_scheduler_step()` does.
4. Prints what the first genuine pass actually did, field by field, plus the
   before/after graph counts and self-model.

WHY IT DRIVES THE CLOCKS ITSELF INSTEAD OF CALLING run_scheduler_step()
----------------------------------------------------------------------
`run_scheduler_step()` returns which clocks fired and DISCARDS the DMNPassResult.
That is the right shape for a scheduler and the wrong shape for an observation, so
this loop reproduces its two independent-interval comparisons and keeps the
result. `soul_tick()` / `dmn_tick()` are the documented primary interface; the
scheduler is described in its own docstring as the convenience wrapper.

Nothing here is a substitute for the scheduler and nothing here is a test.

THE THING THIS MEASURES THAT NOTHING ELSE DOES
----------------------------------------------
In the REPL, `run_scheduler_step()` is called only after a turn, and `input()`
blocks. So while a real user sits reading a reply, NO clock advances: PAD does not
decay, Energy does not recover, and the DMN cannot fire. This harness is the first
thing in the project that drives the clocks through a genuine silence, which means
it is also the first thing to exercise `NeedsSystem.on_idle_recovery()` — the
Energy refill path — for real.

WHERE IT WRITES
---------------
A SEPARATE runtime root by default (`~/.local/aria-observation`), not her real
one. The turns below are a harness script, not things anyone said to her, and
writing them into her real memory would make her remember a conversation that did
not happen. Pass `--runtime-root ~/.local/aria` to observe against the real graph
instead; every timestamp is real either way, which is the part that matters.

A DIAGNOSTIC, NOT A TEST. It needs a live backend and takes over eight minutes, so
`make check` never runs it.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daemon.aria_daemon import (  # noqa: E402
    DEFAULT_DMN_TICK_INTERVAL,
    DEFAULT_SOUL_TICK_INTERVAL,
    IDLE_NO_VOICE_WINDOW,
)
from daemon.llm_interface import LLMTransportError, LLMUnavailableError  # noqa: E402

from adapters.embedding_local import EmbeddingUnavailableError  # noqa: E402

import main as aria_main  # noqa: E402

#: Deliberately ordinary turns. The point is a populated graph, not a stress
#: test of appraisal — the emotional range is already covered by
#: tools/compare_local_models.py. Three is the floor: buffer item N reads
#: EventNode N+1 as the observed reaction, so the last turn's item never gets
#: graded and a two-turn run would grade exactly one.
TURNS = [
    "I have been rebuilding the deploy pipeline this week and it is finally "
    "starting to hold together",
    "the part I am pleased about is that the rollback path works now, that had "
    "been broken for months",
    "I think I want to leave the monitoring piece until next week though",
    "thanks for listening, I am going to go make some tea",
]

#: Table counts read before and after, so "the pass wrote something" is a
#: measurement rather than a claim. Mirrors main.report_state's set.
_COUNTED_TABLES = (
    "event_nodes", "entity_nodes", "emotion_nodes", "uncertainty_nodes", "edges",
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _counts(wiring) -> dict:
    """Table counts. Uses the same `graph._conn` private read `main.report_state`
    already makes and names in its docstring: Module 3 exposes no count API, and
    inventing public API on the graph for a diagnostic readout is the wrong
    trade."""
    return {
        table: wiring.graph._conn.execute(
            f"SELECT COUNT(*) FROM {table}"
        ).fetchone()[0]
        for table in _COUNTED_TABLES
    }


def _print_self_model(wiring, label: str) -> None:
    """Read the narrowed self-model working state (ResLog §2). `load_self_model`
    returns a `SelfModel` dataclass, not a dict — the narrative is deliberately
    NOT in it."""
    model = wiring.state.load_self_model()
    quality = list(model.quality_record)
    print(f"  {label:14s} quality_record={len(quality)} entries "
          f"{quality[-3:] if quality else ''}")
    set_flags = [name for name, value in model.consistency_flags.items() if value]
    print(f"  {'':14s} consistency_flags set: {set_flags or 'none'}")
    if model.recent_learning_user or model.recent_learning_self:
        print(f"  {'':14s} learning user={model.recent_learning_user!r} "
              f"self={model.recent_learning_self!r}")


def drive_turns(wiring, turns: List[str], verbose: bool) -> int:
    """Run the harness turns through the real pipeline. Returns how many landed."""
    entity_refs = [wiring.primary_entity_id] if wiring.primary_entity_id else []
    landed = 0
    for index, text in enumerate(turns, start=1):
        started = time.monotonic()
        try:
            response = wiring.daemon.route_inbound_turn(
                user_text=text,
                entity_refs=entity_refs,
                entity_node_id=wiring.primary_entity_id,
            )
        except (LLMUnavailableError, LLMTransportError) as exc:
            print(f"  turn {index}  FAILED: {exc}")
            continue
        elapsed = time.monotonic() - started
        landed += 1
        note = ""
        if response.retried:
            note += " retried"
        if response.used_minimum_safe_output:
            note += " MINIMUM-SAFE"
        print(f"  turn {index}  {elapsed:5.1f}s{note}")
        if verbose:
            print(f"           you  > {text}")
            print(f"           aria > {response.text.strip()[:200]}")
        # Advance the clocks between turns the way the REPL does, so Energy and
        # PAD move for the same reason they move in real use.
        wiring.daemon.run_scheduler_step()
        wiring.daemon.save_periodic()
    return landed


def wait_for_pass(
    wiring,
    *,
    window: timedelta,
    soul_interval: timedelta,
    dmn_interval: timedelta,
    grace: timedelta,
    tail_seconds: float,
):
    """Drive both clocks on their own real intervals until a DMN pass returns a
    result, or until the window plus `grace` has elapsed.

    Reproduces `run_scheduler_step()`'s two independent interval comparisons and
    keeps the DMNPassResult the scheduler drops. `now` is never passed: every
    comparison is against the real clock.
    """
    start = _now()
    deadline = start + window + grace
    last_soul = start
    last_dmn = start
    soul_ticks = 0
    dmn_ticks = 0
    soul_tick_errors: List[str] = []
    next_report = start

    print(f"  idle window   {window} (PINNED by v4)")
    print(f"  soul tick     every {soul_interval}  (F-8a placeholder)")
    print(f"  dmn tick      every {dmn_interval}  (F-8a placeholder)")
    print(f"  giving up at  {deadline.isoformat(timespec='seconds')}")
    print()

    while True:
        now = _now()
        if now >= deadline:
            print("\n  window elapsed with no pass. Conditions at give-up:")
            print(f"    idle_conditions_met="
                  f"{wiring.daemon._idle_conditions_met(now)}  "
                  f"energy={wiring.needs.get_energy():.1f}")
            return None, soul_ticks, dmn_ticks, soul_tick_errors

        if (now - last_soul) >= soul_interval:
            try:
                wiring.daemon.soul_tick(now=now)
                soul_ticks += 1
            except NotImplementedError as exc:
                # The PAD OQ4 / NEUTRAL residual. Recorded LOUDLY and stepped
                # over rather than swallowed: it is a real, reachable behaviour
                # of the wired system during silence, and it is exactly the
                # `raise` the tracker calls a narrowed-not-closed Open Question.
                # Not repaired here — that needs an architect ruling, and
                # inventing a coefficient to make it go away is the one thing
                # Rule 1 forbids.
                message = str(exc).strip().splitlines()[0]
                if message not in soul_tick_errors:
                    soul_tick_errors.append(message)
                    print(f"  !! soul_tick raised NotImplementedError: {message}")
            last_soul = now

        if (now - last_dmn) >= dmn_interval:
            result = wiring.daemon.dmn_tick(now=now)
            dmn_ticks += 1
            last_dmn = now
            if result is not None:
                return result, soul_ticks, dmn_ticks, soul_tick_errors

        if now >= next_report:
            waited = now - start
            remaining = max(timedelta(0), (start + window) - now)
            print(f"  +{int(waited.total_seconds()):4d}s  "
                  f"idle_in={int(remaining.total_seconds()):4d}s  "
                  f"soul={soul_ticks:3d} dmn={dmn_ticks:2d}  "
                  f"energy={wiring.needs.get_energy():5.1f}  "
                  f"PAD={wiring.pad.get_current_pad().pleasure:.3f}/"
                  f"{wiring.pad.get_current_pad().arousal:.3f}/"
                  f"{wiring.pad.get_current_pad().dominance:.3f}")
            next_report = now + timedelta(seconds=tail_seconds)

        time.sleep(0.5)


def report_pass(result) -> None:
    print()
    print("=" * 74)
    print(f"  DMN PASS RAN — pass_type={result.pass_type.value}  "
          f"step2_ran={result.step2_ran}  step3_ran={result.step3_ran}")
    print("=" * 74)
    rows = [
        ("Step 1  buffer poignancy", {
            k: getattr(v, "value", v) for k, v in result.buffer_poignancy.items()
        }),
        ("Step 1  promoted", result.buffer_promoted),
        ("Step 1  discarded", result.buffer_discarded),
        ("Step 1  emotion nodes", result.emotion_nodes),
        ("Step 1  quality appended", result.quality_appended),
        ("Step 1  buffer consumed", result.buffer_consumed),
        ("Step 2  edges written", result.edges_written),
        ("Step 2  aha insights", [i.description for i in result.aha_insights]),
        ("Step 2  newly connected", result.newly_connected_nodes),
        ("Step 3  resolved", result.uncertainties_resolved),
        ("Step 3  abandoned", result.uncertainties_abandoned),
        ("Step 4  learning nodes", result.learning_nodes),
        ("Step 4  salience adjusted", result.salience_adjusted),
        ("Step 4  stage transitions", {
            k: (getattr(a, "value", a), getattr(b, "value", b))
            for k, (a, b) in result.stage_transitions.items()
        }),
        ("Step 4  narrative", result.narrative_status),
    ]
    for label, value in rows:
        if isinstance(value, (list, dict)) and not value:
            value = "-"
        print(f"  {label:28s} {value}")
    if result.narrative_written:
        print(f"  {'Step 4  narrative text':28s} {result.narrative_written}")
    if result.narrative_block_reasons:
        print(f"  {'Step 4  blocked because':28s} "
              f"{result.narrative_block_reasons}")
    print()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="observe_dmn_pass.py",
        description="Drive real turns, then wait out the real 8-minute idle "
                    "window and report the DMN pass.",
    )
    parser.add_argument("--host", default=os.environ.get(
        "ARIA_OLLAMA_HOST", "http://localhost:11434"))
    parser.add_argument("--local-model", default=os.environ.get("ARIA_LOCAL_MODEL"))
    parser.add_argument("--embedding-model", default=None)
    parser.add_argument(
        "--runtime-root",
        default=str(Path.home() / ".local" / "aria-observation"),
        help="graph + state location. Defaults to a SEPARATE root so harness "
             "turns do not become memories in her real graph.",
    )
    parser.add_argument("--user-entity-id", default=None)
    parser.add_argument(
        "--turns", type=int, default=len(TURNS),
        help=f"how many of the {len(TURNS)} scripted turns to run (min 3, so at "
             f"least one buffer item has a reaction to be graded against)",
    )
    parser.add_argument(
        "--window-minutes", type=float, default=None,
        help="OVERRIDE the idle window. v4 PINS it at 8 minutes; this exists "
             "only to re-check the plumbing quickly and any observation made "
             "with it is not an observation of the specified behaviour.",
    )
    parser.add_argument("--tail", type=float, default=60.0,
                        help="seconds between progress lines while waiting")
    parser.add_argument("--quiet", action="store_true",
                        help="do not print her replies")
    # `main.Wiring` reads these. Defaulted rather than exposed: this harness
    # observes idle consolidation, and a cloud key sitting in the environment
    # must not make a diagnostic run send prompts to a third party as a side
    # effect. Local-only, always.
    parser.set_defaults(no_cloud=True, groq_model=None)
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.embedding_model is None:
        from adapters.embedding_local import DEFAULT_MODEL as _EMB
        args.embedding_model = _EMB

    local_model = aria_main.resolve_local_model(args)
    if local_model is None:
        return 2
    args.local_model = local_model

    window = IDLE_NO_VOICE_WINDOW
    if args.window_minutes is not None:
        window = timedelta(minutes=args.window_minutes)
        print(f"  WARNING  idle window overridden to {window}. v4 PINS it at "
              f"{IDLE_NO_VOICE_WINDOW}; this run observes the plumbing, not the "
              f"specified behaviour.\n")

    try:
        wiring = aria_main.Wiring(args)
    except EmbeddingUnavailableError as exc:
        print(f"cannot start: {exc}", file=sys.stderr)
        return 2

    if args.window_minutes is not None:
        # `AriaDaemon` accepts `idle_no_voice_window` as a constructor argument,
        # but `main.Wiring` does not pass one through — and adding a knob to the
        # production wiring so a diagnostic can shorten a PINNED window would be
        # the wrong direction entirely. So the override is a private write, made
        # only on the explicit flag, and named rather than hidden.
        wiring.daemon._idle_no_voice_window = window

    try:
        wiring.daemon.startup()
        print(f"  graph         {wiring.db_path}")
        print(f"  state         {wiring.state_dir}")
        print(f"  local voice   {wiring.local.model}")
        print(f"  embedding     {wiring.embedding.model} "
              f"dim={wiring.embedding_dim}")
        print(f"  speaking to   {wiring.primary_entity_id}")
        print()

        before = _counts(wiring)
        print(f"  graph before  {before}")
        _print_self_model(wiring, "self before")
        print()

        count = max(3, min(args.turns, len(TURNS)))
        print(f"  driving {count} real turns")
        landed = drive_turns(wiring, TURNS[:count], verbose=not args.quiet)
        if landed == 0:
            print("no turn landed, so there is nothing to consolidate.",
                  file=sys.stderr)
            return 2
        mid = _counts(wiring)
        print(f"\n  graph after turns  {mid}")
        print(f"  energy {wiring.needs.get_energy():.1f}  "
              f"buffer {wiring.daemon.session_buffer_fullness}")
        print()
        print("  now going quiet. Nothing is faked from here — the clocks run "
              "on the real clock.")
        print()

        result, soul_ticks, dmn_ticks, tick_errors = wait_for_pass(
            wiring,
            window=window,
            soul_interval=DEFAULT_SOUL_TICK_INTERVAL,
            dmn_interval=DEFAULT_DMN_TICK_INTERVAL,
            grace=timedelta(minutes=1),
            tail_seconds=args.tail,
        )

        print(f"\n  soul ticks    {soul_ticks}")
        print(f"  dmn ticks     {dmn_ticks}  (most return None: not idle yet)")
        if tick_errors:
            print(f"  soul_tick raised on at least one tick: {tick_errors}")

        if result is None:
            return 1

        report_pass(result)
        after = _counts(wiring)
        print(f"  graph before  {before}")
        print(f"  graph after   {after}")
        delta = {k: after[k] - before[k] for k in after if after[k] != before[k]}
        print(f"  delta         {delta or 'nothing written'}")
        _print_self_model(wiring, "self after")
        print(f"  energy        {wiring.needs.get_energy():.1f}")
        pad = wiring.pad.get_current_pad()
        print(f"  PAD           P={pad.pleasure:.3f} A={pad.arousal:.3f} "
              f"D={pad.dominance:.3f}")
        return 0
    except LLMTransportError as exc:
        print(f"cannot start: the local voice would not load: {exc}",
              file=sys.stderr)
        return 2
    finally:
        if wiring.daemon.started:
            wiring.daemon.shutdown()
        wiring.close()


if __name__ == "__main__":
    sys.exit(main())
