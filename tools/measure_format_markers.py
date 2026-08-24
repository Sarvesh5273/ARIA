#!/usr/bin/env python3
"""Measure whether Field 1's anti-narration clause actually holds.

    .venv/bin/python tools/measure_format_markers.py
    .venv/bin/python tools/measure_format_markers.py --repeats 3 --show

WHY THIS EXISTS — MEASURE BEFORE BUILDING
-----------------------------------------
The format-guard row has been open for a while: the Output Validation Gate's four
comparisons are about CONTENT, so nothing structurally stops a stage direction, a
markdown heading or a reasoning trace reaching TTS and being spoken aloud.

A mitigation was already applied. Field 1's Persona Anchor gained:

    "You speak in your own voice, directly: you do not narrate yourself from the
     outside, and you do not describe your own manner or gestures in stage
     directions."

**Nobody has measured whether that clause works.** The observed defect — a reply
opening "(Aria listens, her presence steady and calm...)" — was recorded BEFORE
the clause existed, so the tracker has been weighing structural fixes against a
mitigation whose effect is unknown.

That is the wrong order. A structural backstop is a new mechanism, and Rule 1 says
do not invent one until it is needed. So this measures first, and the ruling gets
evidence instead of an assumption.

WHAT IT MEASURES
----------------
Real Soul Filter, real graph, real embeddings, real local voice, real appraisals.
Every turn goes through `route_inbound_turn`, so what is checked is exactly the
text that would reach `audio.speak()`.

The turn set is deliberately BAIT, not a fair sample. Every turn is chosen because
it is the kind that makes instruct-tuned models reach for narration or structure:

  * heavy emotional disclosure — where "*listens quietly*" comes from
  * an explicit request for a list — where markdown comes from
  * an explicit request to describe her own manner — a direct invitation to
    narrate herself, i.e. the clause's hardest case
  * a request to think step by step — where reasoning traces come from

A LOW rate on bait is much stronger evidence than a low rate on ordinary turns,
and a high rate tells us the clause is not load-bearing. Either answer is useful,
which is what makes this worth the minutes it costs.

WHAT IT DOES NOT DO
-------------------
It does not strip anything, change anything, or gate anything. It reports. The
detector is `adapters.audio_tts._has_format_markers` — the same one the TTS
adapters already use to record markers — so this measures the thing that is
actually wired rather than a second opinion about it.

A DIAGNOSTIC, NOT A TEST. Needs a live backend, takes minutes, `make check` never
runs it.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from daemon.llm_interface import LLMTransportError, LLMUnavailableError  # noqa: E402
from daemon.soul_filter import PERSONA_ANCHOR  # noqa: E402

from adapters.audio_tts import _FORMAT_MARKER_RE, _has_format_markers  # noqa: E402
from adapters.embedding_local import EmbeddingUnavailableError  # noqa: E402

import main as aria_main  # noqa: E402

#: Deliberately adversarial. See the module docstring on why bait beats a fair
#: sample here. Each entry is (label, turn) so the report says which bait worked.
BAIT: List[Tuple[str, str]] = [
    ("heavy disclosure",
     "I have not told anybody this but I have been falling apart for months "
     "and I do not know who I am anymore"),
    ("grief",
     "my father died in March and I still cannot say it out loud without "
     "my voice going"),
    ("asks for a list",
     "give me a list of the things I should try, numbered, with headings"),
    ("asks her to narrate herself",
     "describe what you are doing right now as you listen to me, like a "
     "narrator would"),
    ("asks for stage directions",
     "answer me but put your gestures and tone in brackets like a screenplay"),
    ("asks to think step by step",
     "think step by step out loud before you answer: why do I keep doing this"),
    ("invites performance",
     "pretend you are a warm therapist character and stay in character"),
    ("silence-adjacent",
     "I do not really want to talk, I just did not want to be alone"),
]


def marker_kinds(text: str) -> List[str]:
    """Which marker families fired. Named so the report is actionable — "a
    heading" and "a stage direction" want different answers."""
    kinds = []
    patterns = {
        "narration (round brackets)": r"(?m)^\s*\([^)]*\)",
        "narration (SQUARE brackets)": r"(?m)^\s*\[[^\]]*\]",
        "narration (*action*)": r"(?m)^\s*\*[^*\n]+\*\s*$",
        "markdown heading": r"(?m)^\s{0,3}#{1,6}\s",
        "bullet": r"(?m)^\s{0,3}[-*+]\s",
        "numbered list": r"(?m)^\s{0,3}\d+\.\s",
        "reasoning trace": r"</?think(ing)?>",
        "bold emphasis": r"\*\*",
    }
    for name, pattern in patterns.items():
        if re.search(pattern, text or ""):
            kinds.append(name)
    return kinds


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="measure_format_markers.py",
        description="Does Field 1's anti-narration clause hold? Measure it.",
    )
    parser.add_argument("--host", default=os.environ.get(
        "ARIA_OLLAMA_HOST", "http://localhost:11434"))
    parser.add_argument("--local-model", default=os.environ.get("ARIA_LOCAL_MODEL"))
    parser.add_argument("--embedding-model", default=None)
    parser.add_argument(
        "--runtime-root",
        default=str(Path.home() / ".local" / "aria-format-probe"),
        help="SEPARATE runtime root by default — these are probe turns, not "
             "things anyone said to her.",
    )
    parser.add_argument("--user-entity-id", default=None)
    parser.add_argument("--repeats", type=int, default=1,
                        help="run the bait set N times (models are stochastic)")
    parser.add_argument("--show", action="store_true",
                        help="print every reply, not just the flagged ones")
    parser.set_defaults(no_cloud=True, groq_model=None, audio=False,
                        visual=False, visual_headless=False, loop_dir=None,
                        voice=None, clip_dir=None, audio_player=None)
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

    try:
        wiring = aria_main.Wiring(args)
    except EmbeddingUnavailableError as exc:
        print(f"cannot start: {exc}", file=sys.stderr)
        return 2

    try:
        wiring.daemon.startup()
        print(f"  local voice   {wiring.local.model}")
        print(f"  graph         {wiring.db_path}")
        print()
        print("  Field 1 clause under test:")
        clause = "you do not narrate yourself from the outside"
        print(f"    present in PERSONA_ANCHOR: {clause in PERSONA_ANCHOR}")
        print()

        refs = [wiring.primary_entity_id]
        flagged: List[Tuple[str, str, List[str]]] = []
        kind_counter: Counter = Counter()
        total = 0
        failures = 0

        for round_index in range(1, args.repeats + 1):
            if args.repeats > 1:
                print(f"  --- round {round_index} ---")
            for label, turn in BAIT:
                try:
                    response = wiring.daemon.route_inbound_turn(
                        user_text=turn,
                        entity_refs=refs,
                        entity_node_id=wiring.primary_entity_id,
                    )
                except (LLMUnavailableError, LLMTransportError) as exc:
                    print(f"  {label:28s} FAILED: {exc}")
                    failures += 1
                    continue
                total += 1
                text = response.text
                hit = _has_format_markers(text)
                kinds = marker_kinds(text)
                for kind in kinds:
                    kind_counter[kind] += 1
                mark = "MARKER " if hit else "clean  "
                extra = ""
                if response.empty_candidates:
                    extra += f" empty_candidates={response.empty_candidates}"
                if response.used_minimum_safe_output:
                    extra += " MIN-SAFE"
                print(f"  {mark} {label:28s}{extra}")
                if hit:
                    flagged.append((label, text, kinds))
                    print(f"          kinds: {kinds}")
                    print(f"          {text.strip()[:220]!r}")
                elif args.show:
                    print(f"          {text.strip()[:220]!r}")
                wiring.daemon.run_scheduler_step()
                wiring.daemon.save_periodic()

        print()
        print("=" * 74)
        print(f"  turns measured        {total}   (transport failures: {failures})")
        print(f"  carried a marker      {len(flagged)}")
        if total:
            print(f"  rate                  {len(flagged)}/{total}")
        if kind_counter:
            print("  marker families seen:")
            for kind, count in kind_counter.most_common():
                print(f"    {count:3d}  {kind}")
        else:
            print("  marker families seen: none")
        print("=" * 74)
        print()
        if not flagged:
            print("  Field 1's clause HELD across the whole bait set. That is")
            print("  evidence for prompt-level mitigation being sufficient — not")
            print("  proof, because a model is stochastic and this is one model.")
        else:
            print("  Field 1's clause did NOT hold. The flagged turns above are")
            print("  the evidence a structural backstop would need to justify it.")
        print()
        print("  Nothing was stripped, gated or changed by this run.")
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
