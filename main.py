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

NETWORK POSTURE — READ THIS BEFORE SETTING AN API KEY
-----------------------------------------------------
No listening socket is opened, ever.

By DEFAULT the only outbound traffic is to the Ollama daemon at `--host`
(localhost) for embeddings and local generation. Both cloud tiers are wired to
`UnconfiguredTransport`, which is explicitly unhealthy and never generates, so
nothing leaves the machine.

That changes the moment a cloud key is present in the environment. A real adapter
now exists (`adapters/transport_cloud.py`), and if `GROQ_API_KEY` (+ a model) or
`AZURE_AI_API_KEY` (+ endpoint and deployment) are set, the matching tier becomes
real and the assembled prompt for a turn it serves — five natural-language fields,
the ephemeral session transcript, the user's current message — is sent to a third
party. `--no-cloud` refuses to build either tier regardless of the environment.

What still never crosses is structural rather than a promise: nothing in this file
hands a transport anything but an `AssembledPrompt`, and `LLMInterface` holds no
graph, PAD, needs, appraisal or state handle to put anything else in one. So no
PAD value, no graph content, no `relational_stage` label, no need state and no
appraisal output can reach a provider (Addendum §9).

Gemma stays the default voice either way. Groq is a fallback, and the reasoning
tier is PROPOSED and never taken silently — so keying a tier does not quietly
reroute ordinary conversation off the machine.

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
from daemon.pad_engine import PAD_BASELINE, PADEngine
from daemon.soul_filter import SoulFilter
from daemon.state_manager import StateManager

from daemon.visual_layer import VisualLayer, VisualLayerPort

from adapters import audio_stack, visual_window
from adapters._provider import AudioBackendUnavailable
from adapters.audio_noop import NoOpAudioPipeline
from adapters.visual_bridge import CloudAvailabilityReporter, SpeakingSignalAudio
from adapters.embedding_local import (
    DEFAULT_MODEL as DEFAULT_EMBEDDING_MODEL,
    EmbeddingUnavailableError,
    OllamaEmbeddingModel,
)
from adapters.transport_cloud import (
    azure_from_env,
    env_summary as cloud_env_summary,
    groq_from_env,
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

        # 6-8. Transports. The local voice is always real. Each cloud tier is
        # real IF its environment is fully configured, and explicitly
        # unconfigured otherwise — never half-real, because a tier that exists
        # but cannot work is worse than one that says it is absent.
        self.local = OllamaLocalTransport(host=args.host, model=args.local_model)
        self.groq = self._resolve_cloud_tier(
            "tier_1 (groq)",
            None if args.no_cloud else groq_from_env(model=args.groq_model),
        )
        self.azure = self._resolve_cloud_tier(
            "tier_2 (azure/kimi)",
            None if args.no_cloud else azure_from_env(),
        )
        self.cloud_disabled_by_flag = args.no_cloud

        # 9. LLM Interface. Note the cloud slot gets the UNCONFIGURED transport,
        # never `self.local`: `LLMInterface`'s internal path unloads `local`
        # whenever `cloud` succeeds, so one object in both slots would evict the
        # resident model after every successful turn.
        self.llm = LLMInterface(
            cloud_transport=self.groq, local_transport=self.local
        )

        # 10-11. Output side + the boundary.
        #
        # The visual layer is built BEFORE the audio port, because the port is
        # what carries the speaking signal to it (see `_build_visual`). The
        # Daemon is not modified: `SpeakingSignalAudio` satisfies
        # `AudioPipelinePort` and goes in the same slot.
        self.visual, self.visual_window = self._build_visual(args)
        self.audio = self._build_audio(args)
        if self.visual is not None:
            self.audio = SpeakingSignalAudio(audio=self.audio, visual=self.visual)
            self.cloud_reporter = CloudAvailabilityReporter(visual=self.visual)
        else:
            self.cloud_reporter = None
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

    # -- visual --------------------------------------------------------------

    def _build_visual(self, args: argparse.Namespace):
        """Module 10, or nothing. Returns `(visual_layer, window)`.

        WHY THE DAEMON IS NOT TOUCHED. `AriaDaemon` takes no visual parameter, and
        Module 10's own flag disposition calls the driver-loop and signal wiring
        "top-of-tree BUILD-TIME wiring, not this module's concern." Adding a
        `visual=` parameter to an approved module's constructor to wire a leaf
        would need a ruling. The signals are taken from where Module 10 says they
        live instead — see `adapters/visual_bridge.py`.

        `--visual` gives the real PyQt6 + libmpv window; `--visual-headless` gives
        the logging window, which is the only way to watch the zone machinery on a
        machine without those providers. Neither is on by default: the layer is a
        leaf, so its absence changes nothing inside the system.

        WHO CALLS `refresh()`. Nobody, until someone does — Module 10 has no timer
        and deliberately does not: "the independent timer/thread that calls
        refresh() ... is top-of-tree wiring." The REPL drives it beside
        `run_scheduler_step()`, which makes the visual loop as input-driven as the
        soul clocks currently are. That is a real limitation of a REPL host rather
        than of Module 10, and it is the same limitation the DMN observation
        surfaced for the two clocks.
        """
        if not (args.visual or args.visual_headless):
            return None, None
        if args.visual_headless or not args.loop_dir:
            window = visual_window.LoggingVideoWindow()
        else:
            window = visual_window.MpvVideoWindow(loop_dir=args.loop_dir)
        return VisualLayer(pad_source=self.pad, window=window), window

    # -- audio ---------------------------------------------------------------

    def _build_audio(self, args: argparse.Namespace):
        """The `AudioPipelinePort`: the no-op by default, real audio on `--audio`.

        The default stays the no-op deliberately. Audio is a LEAF — nothing
        downstream reads what it did, `speak()` returns None, and no soul state
        depends on the result — so substituting it changes no behaviour inside the
        system, which is the reasoning `adapters/audio_noop.py` sets out. Making
        real audio the default would instead mean every text bring-up starts
        talking out loud.

        `--audio` builds the OUTPUT chain only. That is not a compromise: the
        Daemon's port is output-only (`speak`, `stop_playback`,
        `play_thinking_sound`, `play_reconsideration_sound`), and transcribed text
        arrives as `route_inbound_turn(user_text=...)`, so the REPL prompt IS the
        transcription and no inbound backend is missing from the wired path. She
        can speak before she can hear, and that is a real intermediate state.

        BE AWARE OF WHAT THIS TURNS ON. With `--audio`, whatever passes the Output
        Gate is spoken — including a stage direction, a markdown heading or a
        reasoning block, because the gate's four checks are about content and none
        is about form. That is the tracker's open `needs-ruling` row, and the TTS
        adapters record such markers without stripping them (F-9b / Req 5 keep
        verbatim passthrough at that layer). Measured: macOS `say` reads a leading
        "(Aria listens...)" aloud, 0.81 s of speech becoming 3.11 s — and
        adversarial bait produces a stage direction on 3/16 turns even after
        Field 1 was sharpened (Resolution Log item 22).
        """
        if not args.audio:
            return NoOpAudioPipeline()
        return audio_stack.build_output_only(
            pad_source=self.pad,
            voice=args.voice,
            clip_dir=args.clip_dir,
            player=args.audio_player,
        )

    # -- cloud tiers --------------------------------------------------------

    @staticmethod
    def _resolve_cloud_tier(tier_name: str, transport):
        """Take a configured cloud transport, or hold the slot honestly.

        `UnconfiguredTransport` is NOT retired now that a real adapter exists —
        it is still the right object for an unkeyed tier. It answers
        `is_healthy()` with an explicit False and raises from `generate()`, both
        of which are true, so `BackendRouter.select()` skips the tier and never
        proposes the reasoning escalation. Passing `self.local` into a cloud slot
        remains the one thing not to do: `LLMInterface`'s internal path unloads
        `local` whenever `cloud` succeeds.
        """
        if transport is not None:
            return transport
        return UnconfiguredTransport(tier_name=tier_name)

    @property
    def cloud_tiers_live(self) -> list:
        """Which cloud tiers are real this run. Used by the startup report to
        state the network posture out loud rather than leaving it inferable."""
        return [
            t for t in (self.groq, self.azure)
            if not isinstance(t, UnconfiguredTransport)
        ]

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
        # Playback owns a subprocess and temp WAVs, so it has to be told to let
        # go. Closed BEFORE the graph so an interrupted reply stops talking while
        # the rest of shutdown runs, rather than after it.
        #
        # `.wrapped` unwraps the SpeakingSignalAudio decorator when the visual
        # layer is on; without it the reach for `_playback` would find nothing and
        # a subprocess would outlive the process that started it.
        # `getattr` with a default throughout: if construction failed partway,
        # close() still has to release whatever DID get built, and an
        # AttributeError here would mask the original failure.
        port = getattr(self.audio, "wrapped", getattr(self, "audio", None))
        playback = getattr(port, "_playback", None)
        if playback is not None and hasattr(playback, "close"):
            playback.close()
        window = getattr(self, "visual_window", None)
        if window is not None and hasattr(window, "close"):
            window.close()
        graph = getattr(self, "graph", None)
        if graph is not None:
            graph.close()


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
    live = w.cloud_tiers_live
    if not live:
        if w.cloud_disabled_by_flag:
            print("               --no-cloud: both cloud tiers refused "
                  "regardless of the environment.")
        else:
            print("               both cloud tiers are unconfigured, so they "
                  "are explicitly unhealthy:")
            print(f"               {'  '.join(cloud_env_summary())}")
        print(
            "               every turn is served locally, the reasoning tier is "
            "never proposed,"
        )
        print("               and nothing leaves this machine.")
    else:
        # Say it plainly, every run. An operator who set a key a week ago should
        # not have to remember that in order to know where their words are going.
        print("               NETWORK POSTURE: prompts CAN now leave this "
              "machine. Live cloud tiers:")
        for tier in live:
            print(f"                 {tier.describe()}")
        print("               Gemma is still the default voice; Groq is a "
              "fallback and the reasoning")
        print("               tier is proposed, never taken silently. "
              "--no-cloud turns both off.")
    # Unwrap the SpeakingSignalAudio decorator before reaching for the pipeline's
    # parts. Without this the report reads "SPEAKING — NoneType -> ?" whenever the
    # visual layer is on, which is exactly when someone is checking it.
    port = getattr(w.audio, "wrapped", w.audio)
    if isinstance(port, NoOpAudioPipeline):
        print("  audio        no-op (text only). --audio to speak, "
              "--audio-preflight to see backends.")
    else:
        primary = getattr(port, "_tts_primary", None)
        playback = getattr(port, "_playback", None)
        print(f"  audio        SPEAKING — {type(primary).__name__}"
              f" -> {playback.describe() if playback is not None else '?'}")
        # Read from the PROBE rather than hardcoded, so this line cannot claim a
        # capability the active backend does not have. Said out loud because it is
        # a real gap in v4's Layer 5 voice expression, not a detail.
        support = dict(getattr(primary, "prosody_support", {}))
        unmapped = list(getattr(primary, "unmapped_prosody", []))
        if support:
            reaches = [f for f, ok in support.items() if ok]
            print(f"               prosody: {', '.join(reaches) or 'nothing'} "
                  f"reaches the voice")
            if unmapped:
                print(f"               dormant but still computed: {unmapped} "
                      f"— v4 Layer 5 keeps all three")
        print("               format markers are STRIPPED for speech only "
              "(ResLog 25): the text,")
        print("               session buffer and graph keep them. Unmarked "
              "plain-prose narration")
        print("               is still spoken — no regex reaches it. Known gap.")
    warn_pad_restore_boundary(w)
    if w.visual is None:
        print("  visual       off. --visual (PyQt6 + libmpv) or --visual-headless.")
    else:
        kind = type(w.visual_window).__name__
        print(f"  visual       Module 10 live — {kind}")
        if hasattr(w.visual_window, "describe"):
            print(f"               {w.visual_window.describe()}")
        print("               speaking signal comes from the audio port "
              "(AriaDaemon unmodified);")
        print("               degradation is driven by LLMUnavailableError — "
              "'nothing could answer")
        print("               this turn' — which holds under both a "
              "cloud-primary and a local-primary")
        print("               design. The routing readout is NOT wired: under "
              "local-primary, 'no")
        print("               cloud' is the resting state, not a face change. "
              "See visual_bridge.py.")
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


def warn_pad_restore_boundary(w: Wiring) -> None:
    """Say so at STARTUP if the next soul tick is going to raise.

    PAD Engine's Open Question 4 residual: `on_soul_tick` raises
    `NotImplementedError` when PAD was restored to a NON-BASELINE value and no
    valence came back with it, because there is then no basis for choosing an
    EMA decay coefficient and inventing one is exactly what Rule 1 forbids.

    The HANDOFF contract normally prevents this — `AriaDaemon.startup()` restores
    `last_applied_valence` and passes it to `initialize()`, and the write cadence
    is every turn, so the field is one turn behind at worst. The residual case is
    a crash BETWEEN an appraisal delta and the next save, which leaves PAD off
    baseline with the valence key never written.

    Demonstrated reproducibly: with that state file, `startup()` succeeds and the
    FIRST `soul_tick()` raises — which in this REPL means the first turn dies with
    a traceback several frames from the cause.

    So this prints the cause up front. It does NOT resolve it: no coefficient is
    chosen, the raise is not caught, and `pad_engine.py` is untouched. Closing OQ4
    is an architect decision.
    """
    pad = w.pad.get_current_pad()
    at_baseline = (
        pad.pleasure == PAD_BASELINE.pleasure
        and pad.arousal == PAD_BASELINE.arousal
        and pad.dominance == PAD_BASELINE.dominance
    )
    if at_baseline or w.state.load_last_applied_valence() is not None:
        return
    print("  PAD          WARNING — restored off baseline "
          f"(P={pad.pleasure:.3f}) with NO persisted valence.")
    print("               The next soul tick will raise NotImplementedError: this "
          "is PAD Engine's")
    print("               Open Question 4 residual, and no decay coefficient may "
          "be invented for it")
    print("               (Rule 1). Usual cause: a crash between an appraisal "
          "delta and the next save.")
    print(f"               Operator remedy: set last_applied_valence in "
          f"{w.state_dir}/aria_state.json")
    print("               to one of positive/negative/neutral/valence_uncertain, "
          "or reset PAD to")
    print("               baseline by removing the pad key. Neither is a fix — "
          "OQ4 needs a ruling.")


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
    if w.visual is not None:
        loop = w.visual.current_loop
        print(
            f"  visual       zone={w.visual.current_zone.value if w.visual.current_zone else '-'}"
            f"  loop={loop.loop_id if loop else '-'}"
            f"  degraded={w.visual.is_degraded}"
        )
    print(f"  ticks        soul={w.daemon.soul_tick_count} "
          f"dmn={w.daemon.dmn_tick_count}")
    print(f"  backends     {health}")
    # WHERE THE LAST ANSWER CAME FROM. Replaces what used to be reported as
    # "serving_from_local", which returned the local model's residency and
    # therefore said "cloud is down" during entirely healthy operation. Reads
    # `local_chosen` on an ordinary Track A turn, and distinguishes an
    # unconfigured cloud tier (`no_cloud_adapter`, the intended state of a
    # local-first bring-up) from one that actually fell over
    # (`cloud_unhealthy_fallback`).
    print(f"  last route   {w.llm.last_route}")
    print(f"  graph        {counts}")
    print(f"  embedding    {w.embedding.stats} dim={w.embedding.dimension}")
    print()


# ===========================================================================
# The REPL
# ===========================================================================

def report_turn_outcome(w: Wiring, *, served: bool) -> None:
    """Relay "a backend answered / did not" to the Visual Layer.

    Edge-triggered inside `CloudAvailabilityReporter`, so calling it on every turn
    costs nothing and needs no state here.
    """
    if w.cloud_reporter is None:
        return
    if served:
        w.cloud_reporter.report_turn_served()
    else:
        w.cloud_reporter.report_turn_failed()


def step_visual(w: Wiring) -> None:
    """One step of Module 10's independent loop.

    A REPL is the wrong host for this and it is worth being honest about why:
    `input()` blocks, so between turns nothing advances — the same limitation the
    DMN observation found for the two soul clocks (see
    `tools/observe_dmn_pass.py`). The 8-second stability gate therefore only ever
    sees turn-to-turn intervals here, which in practice are longer than 8 seconds,
    so the anti-flicker rule is satisfied trivially rather than exercised. A real
    host wants a timer.
    """
    if w.visual is None:
        return
    w.visual.refresh()
    # The real window owns a Qt event loop that someone has to turn over. The
    # driver must NOT call QApplication.exec(), which would never return and would
    # stop the soul clocks entirely.
    if hasattr(w.visual_window, "pump"):
        w.visual_window.pump()


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
            # Module 10's degradation trigger: withdrawn, not sleeping. This is
            # the other signal its docstring names, and the one that means the
            # same thing whether the cloud or the local voice is primary.
            report_turn_outcome(w, served=False)
            continue
        except LLMTransportError as exc:
            print(f"\n  [the local model failed on this turn] {exc}\n")
            report_turn_outcome(w, served=False)
            continue
        except EmbeddingUnavailableError as exc:
            print(f"\n  [the embedding backend went away mid-turn] {exc}\n")
            continue

        report_turn_outcome(w, served=True)

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
        # Third loop, and it is genuinely independent of the other two (v4: the
        # visual layer "runs locally, independently, in parallel with language
        # generation"). Module 10 owns no timer by design, so the host drives it.
        step_visual(w)
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
    parser.add_argument(
        "--groq-model",
        default=os.environ.get("ARIA_GROQ_MODEL"),
        help=(
            "model tag for the tier-1 Groq backend. No default is invented — "
            "without this (or ARIA_GROQ_MODEL) the tier stays unconfigured even "
            "if GROQ_API_KEY is set."
        ),
    )
    parser.add_argument(
        "--audio",
        action="store_true",
        help=(
            "speak her replies out loud (the OUTPUT chain: PAD -> prosody -> TTS "
            "-> playback). Off by default: audio is a leaf, so the no-op changes "
            "nothing inside the system, and a text bring-up should not start "
            "talking. NOTE this is where the open format-guard question bites — "
            "a stage direction or a markdown heading that passes the Output Gate "
            "WILL be spoken, because the gate's four checks are about content."
        ),
    )
    parser.add_argument(
        "--audio-preflight",
        action="store_true",
        help="report which of the seven audio backends are available, then exit",
    )
    parser.add_argument(
        "--visual",
        action="store_true",
        help=(
            "run Module 10 with the real PyQt6 + libmpv window (needs --loop-dir "
            "and the 17 loop files v4 names). Off by default: the visual layer is "
            "a leaf, so its absence changes nothing inside the system."
        ),
    )
    parser.add_argument(
        "--visual-headless",
        action="store_true",
        help=(
            "run Module 10 with a logging window instead of a display. The zone "
            "mapping, the 8-second stability gate, the talking/idle variant and "
            "the inward/waiting override all run for real and are reported by "
            ":state — this is how to watch them without PyQt6 or libmpv."
        ),
    )
    parser.add_argument(
        "--loop-dir",
        default=os.environ.get("ARIA_LOOP_DIR"),
        help=(
            "directory of video loop files. v4 names 16 (8 zones x idle/talking) "
            "plus the inward/waiting loop; each file is named for its loop key, "
            "e.g. engaged_talking.mp4."
        ),
    )
    parser.add_argument(
        "--visual-preflight",
        action="store_true",
        help="report the visual providers and loop-file catalogue, then exit",
    )
    parser.add_argument(
        "--voice",
        default=os.environ.get("ARIA_VOICE"),
        help="system TTS voice name (macOS `say -v`). No default is chosen here.",
    )
    parser.add_argument(
        "--clip-dir",
        default=os.environ.get("ARIA_CLIP_DIR"),
        help=(
            "directory of pre-cached WAV clips for the thinking and "
            "reconsideration sounds (v4 Layer 5). Each file's stem is its key. "
            "Missing clips are a recorded no-op, never a failed turn."
        ),
    )
    parser.add_argument(
        "--audio-player",
        default=os.environ.get("ARIA_AUDIO_PLAYER"),
        help=(
            "playback binary. Defaults to the first of "
            f"{list(audio_stack.audio_playback.PLAYER_CANDIDATES)} found on PATH."
        ),
    )
    parser.add_argument(
        "--no-cloud",
        action="store_true",
        default=_env_flag("ARIA_NO_CLOUD"),
        help=(
            "refuse to build either cloud tier even when keys are present. The "
            "off switch is a flag rather than the absence of one because "
            "unsetting an environment variable is easy to forget and the cost of "
            "forgetting is prompts leaving the machine."
        ),
    )
    return parser


def _env_flag(name: str) -> bool:
    """An env var read as a boolean. Anything set and not obviously falsey is
    True — the safe direction for a switch whose ON position means "send less"."""
    raw = (os.environ.get(name) or "").strip().lower()
    return raw not in ("", "0", "false", "no", "off")


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

    if args.audio_preflight:
        # Answered before anything is constructed, because "can she talk yet" must
        # not require a reachable model backend to ask.
        print("Audio backends (Module 7 — seven injected Protocols):\n")
        print(audio_stack.preflight_report())
        print()
        print(f"  output chain (what AudioPipelinePort drives): "
              f"{'READY' if audio_stack.output_chain_ready() else 'not ready'}")
        print(f"  input chain  (capture -> VAD -> STT):         "
              f"{'READY' if audio_stack.input_chain_ready() else 'not ready'}")
        print()
        print("  The Daemon's port is OUTPUT ONLY — transcribed text arrives as")
        print("  route_inbound_turn(user_text=...), so the REPL prompt is the")
        print("  transcription and the input chain is not needed to run --audio.")
        return 0

    if args.visual_preflight:
        print("Visual Layer (Module 10 — one injected VideoWindow Protocol):\n")
        print(visual_window.preflight_report(args.loop_dir))
        print()
        print("  --visual-headless runs the zone machinery with no display, which")
        print("  is how to watch the categorical mapping and the 8-second gate")
        print("  without PyQt6 or libmpv installed.")
        return 0

    local_model = resolve_local_model(args)
    if local_model is None:
        return 2
    args.local_model = local_model

    try:
        wiring = Wiring(args)
    except EmbeddingUnavailableError as exc:
        print(f"cannot start: {exc}", file=sys.stderr)
        return 2
    except AudioBackendUnavailable as exc:
        # A missing audio or video provider is a CONFIGURATION problem with a
        # one-line remedy, which the adapter already put in the message. A
        # traceback here would bury it under eight frames of import machinery.
        print(f"cannot start: {exc}", file=sys.stderr)
        print("  --audio-preflight and --visual-preflight report what is missing "
              "without starting anything.", file=sys.stderr)
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
