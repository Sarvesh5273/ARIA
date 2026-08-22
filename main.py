#!/usr/bin/env python3
"""ARIA entry point — wire the soul layer to real adapters and talk to her.

    .venv/bin/python main.py

WHAT THIS IS
------------
The first thing in this project that RUNS. Thirteen soul modules and 535 tests
existed before it; none of them had a body attached. This wires the modules to
concrete adapters in the one order their dependencies allow, honours the HANDOFF
startup contract, and drives turns from a text prompt.

TEXT-FIRST, DELIBERATELY. Speech-to-text is not a port at all — transcribed text
arrives as `route_inbound_turn(user_text=...)`, so a terminal prompt IS the
transcription. Audio output is a no-op (see `adapters/audio_noop.py` on why a
leaf may be stubbed and the embedding model may not). The Visual Layer is not
wired: `AriaDaemon` takes no visual parameter.

WHAT ACTUALLY REACHES A MODEL
-----------------------------
Only what Soul Filter assembles: the five natural-language fields (or the
emergency Type A/B/C set), the ephemeral session transcript, and the user's
current message. This file passes no PAD value, no graph content, no stage label,
no need state and no appraisal output to any transport — it has no path to. The
`:state` command below prints internal state to YOUR terminal; that is a
diagnostic readout for the operator and crosses no model boundary.

NETWORK POSTURE
---------------
No listening socket is opened. The only outbound traffic is to the Ollama daemon
at `--host` (localhost by default) for embeddings and local generation. The two
cloud tiers are wired to `UnconfiguredTransport`, which is explicitly unhealthy
and never generates, so nothing leaves the machine until a real cloud adapter is
written and passed in deliberately.

RUNTIME LAYOUT (v4 "Directory Structure")
-----------------------------------------
    ~/.local/aria/state/        aria_state.json, self_model.json  (StateManager)
    ~/.local/aria/graph.db      the graph — the only persistent memory

`.gitignore` already excludes `*.db` and both json files: the graph holds real
conversation history and emotional state.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from daemon.appraisal_chain import AppraisalChain
from daemon.aria_daemon import AriaDaemon, DaemonState
from daemon.backend_router import BackendRouter
from daemon.dmn import DMN
from daemon.graph_manager import MemoryGraph
from daemon.llm_interface import (
    LLMInterface,
    LLMTransportError,
    LLMUnavailableError,
)
from daemon.needs_system import NeedsSystem
from daemon.pad_engine import PADEngine
from daemon.soul_filter import SoulFilter
from daemon.state_manager import StateManager

from adapters.audio_noop import NoOpAudioPipeline
from adapters.embedding_local import (
    DEFAULT_MODEL as DEFAULT_EMBEDDING_MODEL,
    EmbeddingUnavailableError,
    OllamaEmbeddingModel,
)
from adapters.transport_ollama import (
    DEFAULT_MODEL as DEFAULT_LOCAL_MODEL,
    OllamaLocalTransport,
    resolve_model,
)
from adapters.transport_unconfigured import UnconfiguredTransport

DEFAULT_HOST = "http://localhost:11434"
DEFAULT_RUNTIME_ROOT = Path.home() / ".local" / "aria"

# WRITE CADENCE: every turn. Resolution Log item 4 calls StateManager's write
# cadence a build-time tuning flag, so a value had to be chosen — and the honest
# choice is the one that needs no defending. Saving after every turn writes two
# small JSON files atomically, which at conversational pace is a handful of
# writes a minute, and it makes crash behaviour trivially correct: nothing is
# ever pending. Batching would buy nothing measurable and would leave a number to
# justify. There is deliberately no SAVE_EVERY_TURNS constant here.
#
# Worth knowing: a crash never loses MEMORY. Every MemoryGraph write commits
# within its own method, so the graph is durable per turn regardless. What the
# cadence protects is PAD, Energy and last_applied_valence only.

BANNER = """\
ARIA — text bring-up. Type to talk. ':help' for commands, ':quit' to leave.
"""

HELP = """\
  :help     this list
  :state    PAD, Energy, needs, session buffer, backend health, graph counts
  :tick     advance the soul and DMN clocks once, now
  :save     flush PAD, Energy and last_applied_valence to disk
  :quit     save and exit

  Anything without a leading ':' is a turn. Her own meta-commands are words,
  not colons -- "rest", "focus", "unfocus", "use cloud", "stay local" -- and
  they are handled inside the Daemon, not here.

  Idle consolidation (the DMN pass) needs 8 real minutes with no input; that
  window is PINNED by v4. There is deliberately no command to fake it: passing
  a false `now` would write false timestamps into the graph, and the graph is
  the only memory she has.
"""


# ===========================================================================
# Wiring
# ===========================================================================

class Wiring:
    """Every constructed part, kept together so `:state` can read them.

    Construction ORDER is forced by the dependency edges, not chosen:
    embedding -> graph -> needs + appraisal(needs PAD) -> transports -> llm ->
    soul filter -> state -> dmn -> router -> daemon.
    """

    def __init__(self, args: argparse.Namespace) -> None:
        runtime_root = Path(args.runtime_root).expanduser()
        runtime_root.mkdir(parents=True, exist_ok=True)
        self.db_path = str(runtime_root / "graph.db")
        self.state_dir = runtime_root / "state"

        # 1. The embedding model. ONE instance, shared by the graph and the
        # appraisal chain — Addendum §1, "one model serves both jobs".
        self.embedding = OllamaEmbeddingModel(
            host=args.host, model=args.embedding_model
        )
        # Fail here, loudly, rather than during a turn. Two of the three
        # `embed()` call sites in the soul layer swallow exceptions, so a
        # backend that is down is only PARTLY visible at turn time — and the
        # part that stays invisible is retrieval ordering and vulnerability
        # detection quietly going inert.
        self.embedding_dim = self.embedding.preflight()

        # 2. The graph — the only persistent memory.
        self.graph = MemoryGraph(self.db_path, embedding_model=self.embedding)

        # 3-5. Soul core.
        self.pad = PADEngine()
        self.needs = NeedsSystem(self.graph)
        self.appraisal = AppraisalChain(
            pad_engine=self.pad, graph=self.graph, embedding_model=self.embedding
        )

        # 6-8. Transports. The local voice is real; both cloud tiers are
        # explicitly unavailable because no adapter for them exists yet.
        self.local = OllamaLocalTransport(host=args.host, model=args.local_model)
        self.groq = UnconfiguredTransport(tier_name="tier_1 (groq)")
        self.azure = UnconfiguredTransport(tier_name="tier_2 (azure/kimi)")

        # 9. LLM Interface. Note the cloud slot gets the UNCONFIGURED transport,
        # never `self.local`: `LLMInterface`'s internal path unloads `local`
        # whenever `cloud` succeeds, so one object in both slots would evict the
        # resident model after every successful turn.
        self.llm = LLMInterface(
            cloud_transport=self.groq, local_transport=self.local
        )

        # 10-11. Output side + the boundary.
        self.audio = NoOpAudioPipeline()
        self.soul_filter = SoulFilter(
            pad_engine=self.pad,
            graph=self.graph,
            llm_client=self.llm,
            on_reconsideration=self.audio.play_reconsideration_sound,
        )

        # 12-13. Persistence + idle consolidation.
        self.state = StateManager(state_dir=self.state_dir)
        self.dmn = DMN(
            graph=self.graph,
            appraisal=self.appraisal,
            needs=self.needs,
            state=self.state,
        )

        # 14. Routing. Gemma first; the reasoning tier is proposed, never taken
        # silently — and with azure unhealthy it is never even proposed.
        self.router = BackendRouter(
            gemma_transport=self.local,
            groq_transport=self.groq,
            azure_transport=self.azure,
        )

        # 15. Who she is talking to. Resolved BEFORE the Daemon is built, not
        # after: `AriaDaemon` takes `primary_entity_id` as a constructor argument
        # and uses it as the initiative turn's `entity_node_id`, so handing it
        # None and resolving later would leave initiative permanently
        # entity-less. Both collaborators this needs — the graph and the state
        # manager — already exist above.
        self.primary_entity_id = args.user_entity_id
        self.created_primary_entity = False
        self.restored_primary_entity = False
        self.ensure_primary_entity()

        # 16. The Daemon.
        self.daemon = AriaDaemon(
            pad_engine=self.pad,
            needs_system=self.needs,
            graph=self.graph,
            appraisal_chain=self.appraisal,
            soul_filter=self.soul_filter,
            dmn=self.dmn,
            state_manager=self.state,
            audio=self.audio,
            primary_entity_id=self.primary_entity_id,
            backend_router=self.router,
        )

    # -- the primary (user) entity -----------------------------------------

    def ensure_primary_entity(self) -> None:
        """Resolve the EntityNode that represents the person talking.

        Three rungs, and the ORDER is the design:

        1. An explicit `--user-entity-id` wins. An operator naming an id is
           making a deliberate choice and nothing should override it.
        2. Otherwise the persisted id, via `StateManager.load_primary_entity_id`
           — the same mechanism Resolution Log §2 established for the self
           entity. This is what makes her memory of one person continuous
           instead of a series of strangers: the id keys relational_stage,
           conflict arcs, is_first_of_kind and reality_contradiction_check.
        3. Otherwise create the node, and PERSIST it immediately so rung 2
           carries every later run.

        Creation stays HERE rather than in `AriaDaemon.startup()`, and that is a
        deliberate asymmetry with the self entity. ResLog §2 warrants the Daemon
        auto-creating a node for ARIA — she is always present, so there is
        nothing to decide. Who the USER is has no such warrant, and v4 points at
        voiceprint enrolment for it (`voiceprint_enrolled` is in v4's
        `aria_state.json` listing; Module 7 carries speaker verification at
        0.75). So the Daemon does not invent an identity; the wiring layer
        resolves one and hands it over.
        """
        if self.primary_entity_id:
            self.state.save_primary_entity_id(self.primary_entity_id)
            return

        persisted = self.state.load_primary_entity_id()
        if persisted:
            self.primary_entity_id = persisted
            self.restored_primary_entity = True
            return

        self.primary_entity_id = self.graph.write_entity_node(
            entity_type="person", name="user"
        )
        self.state.save_primary_entity_id(self.primary_entity_id)
        self.created_primary_entity = True

    def close(self) -> None:
        self.graph.close()


# ===========================================================================
# Startup reporting — everything a reader needs to trust what just happened.
# ===========================================================================

def report_startup(w: Wiring) -> None:
    health = w.router.check_health()
    print(f"  graph        {w.db_path}")
    print(f"  state        {w.state_dir}")
    print(
        f"  embedding    {w.embedding.model}  dim={w.embedding_dim}  "
        f"(encoder-only, Addendum §1)"
    )
    print(f"  local voice  {w.local.model}  resident={w.local.is_loaded}")
    print(
        f"  backends     gemma={health['gemma']}  groq={health['groq']}  "
        f"azure={health['azure']}"
    )
    print(
        "               both cloud tiers are explicitly unhealthy: no adapter "
        "is written yet,"
    )
    print(
        "               so every turn is served locally and the reasoning tier "
        "is never proposed."
    )
    if w.created_primary_entity:
        print(f"  speaking to  {w.primary_entity_id}")
        print("               FIRST RUN — created and persisted. Every later run "
              "restores it,")
        print("               so her memory of you is continuous without you "
              "doing anything.")
    elif w.restored_primary_entity:
        print(f"  speaking to  {w.primary_entity_id}  (restored from state)")
    else:
        print(f"  speaking to  {w.primary_entity_id}  (given on the command line)")
    print()


def report_state(w: Wiring) -> None:
    """Operator diagnostics, printed to YOUR terminal. None of it crosses to a
    model — that boundary is Soul Filter's and nothing here is routed through it.

    ONE private read remains, named rather than hidden: `graph._conn` for table
    counts. Module 3 exposes no count API and inventing public API on the graph
    for a debug readout is the wrong trade — the project flags `graph._conn`
    reach-ins inside the SOUL layer for good reason, and this is a diagnostic in
    the wiring layer. If `:state` ever becomes a supported interface rather than a
    bring-up aid, that wants a real accessor.

    Session-buffer fullness used to be the second private read. It is now
    `AriaDaemon.session_buffer_fullness`, a read-only property added alongside the
    module's existing observability properties, because the Daemon builds its own
    SessionBuffer and no caller can otherwise ask.
    """
    pad = w.pad.get_current_pad()
    needs = w.needs.get_need_states()
    health = w.router.check_health()
    counts = {
        table: w.graph._conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        for table in ("event_nodes", "entity_nodes", "emotion_nodes",
                      "uncertainty_nodes", "edges")
    }
    print(f"  PAD          P={pad.pleasure:.3f} A={pad.arousal:.3f} "
          f"D={pad.dominance:.3f}")
    print(f"  Energy       {w.needs.get_energy():.1f}")
    print(
        f"  needs        connection={needs.connection.value} "
        f"growth={needs.growth.value} purpose={needs.purpose.value} "
        f"continuity={needs.continuity.value}"
    )
    print(f"  buffer       {w.daemon.session_buffer_fullness}")
    print(f"  daemon state {w.daemon.state.value}")
    print(f"  ticks        soul={w.daemon.soul_tick_count} "
          f"dmn={w.daemon.dmn_tick_count}")
    print(f"  backends     {health}")
    print(f"  graph        {counts}")
    print(f"  embedding    {w.embedding.stats} dim={w.embedding.dimension}")
    print()


# ===========================================================================
# The REPL
# ===========================================================================

def run_repl(w: Wiring) -> int:
    turns = 0
    entity_refs = [w.primary_entity_id] if w.primary_entity_id else []

    while True:
        try:
            line = input("you > ")
        except (EOFError, KeyboardInterrupt):
            print()
            return 0

        text = line.strip()
        if not text:
            continue

        if text.startswith(":"):
            command = text[1:].strip().lower()
            if command in ("quit", "exit", "q"):
                return 0
            if command == "help":
                print(HELP)
            elif command == "state":
                report_state(w)
            elif command == "tick":
                fired = w.daemon.run_scheduler_step()
                print(f"  clocks fired: {fired or 'none due yet'}\n")
            elif command == "save":
                w.daemon.save_periodic()
                print("  saved\n")
            else:
                print(f"  unknown command {text!r} — try :help\n")
            continue

        try:
            response = w.daemon.route_inbound_turn(
                user_text=text,
                entity_refs=entity_refs,
                entity_node_id=w.primary_entity_id,
            )
        except LLMUnavailableError as exc:
            print(f"\n  [no backend could answer this turn] {exc}\n")
            continue
        except LLMTransportError as exc:
            print(f"\n  [the local model failed on this turn] {exc}\n")
            continue
        except EmbeddingUnavailableError as exc:
            print(f"\n  [the embedding backend went away mid-turn] {exc}\n")
            continue

        print(f"\naria> {response.text}\n")

        # Surface the parts of the turn a bring-up needs to be able to see.
        notes = []
        if response.instruction_kind != "five_field":
            notes.append(f"instruction={response.instruction_kind}")
        if response.retried:
            notes.append("retried after a gate failure")
        if response.used_minimum_safe_output:
            notes.append("MINIMUM-SAFE output")
        if w.daemon.state is DaemonState.PROPOSING_CLOUD:
            notes.append("waiting on your yes/no about the reasoning tier")
        if notes:
            print(f"      [{' · '.join(notes)}]\n")

        turns += 1
        # Advance both clocks. Without this PAD never decays and the DMN never
        # runs: the two clocks are driven by the caller, and in a REPL the
        # caller is this loop.
        w.daemon.run_scheduler_step()
        # Flush after every turn — see the WRITE CADENCE note at the top.
        w.daemon.save_periodic()


# ===========================================================================
# CLI
# ===========================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Run ARIA with a text prompt.",
    )
    parser.add_argument(
        "--host",
        default=os.environ.get("ARIA_OLLAMA_HOST", DEFAULT_HOST),
        help=f"Ollama daemon base URL (default {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--embedding-model",
        default=os.environ.get("ARIA_EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        help=(
            f"encoder-only sentence-embedding model, tens of MB, NOT Gemma "
            f"(Addendum §1). Default {DEFAULT_EMBEDDING_MODEL}."
        ),
    )
    parser.add_argument(
        "--local-model",
        default=os.environ.get("ARIA_LOCAL_MODEL"),
        help=(
            f"local voice. v4 names \"Gemma 4 E2B QAT\" = {DEFAULT_LOCAL_MODEL}. "
            f"If omitted, resolved against what is installed."
        ),
    )
    parser.add_argument(
        "--user-entity-id",
        default=os.environ.get("ARIA_USER_ENTITY_ID"),
        help=(
            "EntityNode id for the person talking. Normally omit it: the id is "
            "created on first run and persisted, then restored automatically. "
            "Pass it only to point her at a different person's history."
        ),
    )
    parser.add_argument(
        "--runtime-root",
        default=os.environ.get("ARIA_RUNTIME_ROOT", str(DEFAULT_RUNTIME_ROOT)),
        help=f"graph + state location (default {DEFAULT_RUNTIME_ROOT})",
    )
    return parser


def resolve_local_model(args: argparse.Namespace) -> Optional[str]:
    """Settle the local-voice tag before anything is constructed.

    An explicit `--local-model` is taken as given. Otherwise the installed tags
    are asked, and `resolve_model` substitutes only inside the Gemma family and
    only when the choice is unambiguous — printing what it did, because a
    different Gemma variant is a different model and a different footprint.
    """
    if args.local_model:
        return args.local_model

    probe = OllamaLocalTransport(host=args.host, model=DEFAULT_LOCAL_MODEL)
    try:
        installed = probe.installed_models()
    except LLMTransportError as exc:
        print(f"cannot reach the model backend at {args.host}: {exc}", file=sys.stderr)
        print("start it with:  ollama serve", file=sys.stderr)
        return None

    tag, note = resolve_model(installed)
    if note:
        print(f"  NOTE  {note}\n")
    return tag


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    # flush=True so the banner still precedes a stderr failure when stdout is
    # piped into a log: stderr is unbuffered, block-buffered stdout is not, and
    # a startup diagnostic that reads out of order is worse than useless.
    print(BANNER, flush=True)

    local_model = resolve_local_model(args)
    if local_model is None:
        return 2
    args.local_model = local_model

    try:
        wiring = Wiring(args)
    except EmbeddingUnavailableError as exc:
        print(f"cannot start: {exc}", file=sys.stderr)
        return 2

    try:
        # startup() runs the HANDOFF contract: PADEngine.initialize() exactly
        # once, Energy restored, consistency_flags cleared, the self EntityNode
        # created or loaded, and the local model loaded and pinned resident. If
        # the model cannot load it raises here, on purpose.
        wiring.daemon.startup()
        report_startup(wiring)
        return run_repl(wiring)
    except LLMTransportError as exc:
        print(f"cannot start: the local voice would not load: {exc}", file=sys.stderr)
        return 2
    finally:
        # `started` is the public flag for "the HANDOFF contract completed".
        # shutdown() flushes PAD, Energy and last_applied_valence; calling it
        # before startup() would raise, and there would be nothing to flush.
        if wiring.daemon.started:
            wiring.daemon.shutdown()
        wiring.close()


if __name__ == "__main__":
    sys.exit(main())
