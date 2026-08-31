#!/usr/bin/env python3
"""ARIA voice host — speak to her, she speaks back.

    .venv/bin/python voice_main.py --vad-model ~/.local/aria/models/silero_vad.onnx

WHAT THIS IS
------------
The inbound driver loop. `main.py` is the same system with a keyboard where the
microphone should be: it drives `route_inbound_turn(user_text=...)` from a text
prompt, because "transcribed text arrives as a string" is the Daemon's actual
contract and a REPL prompt satisfies it. This file supplies the transcription from
a voice instead, and changes nothing else — same soul modules, same construction
order, same HANDOFF contract, same graph.

WHERE THIS SITS IN THE SPEC, AND WHY IT IS A SEPARATE FILE
----------------------------------------------------------
Module 7's spec names this loop and declines to design it:

    OQ-1 (build-time wiring): the streaming driver loop that calls
    `capture_turn()` and forwards its text to `AriaDaemon.route_inbound_turn`
    lives at the top-of-tree wiring layer, not in this module. Named, not
    resolved here.

That classification is a scoping statement, not an authorisation of a particular
design — so `docs/RESOLUTION_LOG_DRAFT.md` proposes the entry that would make this
loop authorised of record, the same way Resolution Log item 19 was written to make
post-approval work legible. Until that is signed off, read this file as a proposal
with running code attached.

Separate from `main.py` deliberately. `main.py`'s text path is verified, is what
`make preflight` and the tracker describe, and needs no microphone, no model file
and no `onnxruntime`. Folding voice into it would make every text bring-up depend
on five providers and two model files.

THE SHAPE OF THE LOOP, AND THE ONE PLACE v4 STOPS SHORT
-------------------------------------------------------
Read literally, v4's audio flow is a stateless poll: capture into a rolling 20 s
ring, ask the wake word, verify the speaker, trim to speech, transcribe. Taken at
face value that transcribes the ring AT THE MOMENT the wake word fires — which is
mid-sentence, because the question has not been asked yet.

**v4 does not say how long to keep listening after being woken.** There is no
end-of-utterance constant, no silence hangover and no maximum utterance length in
v4, the Addendum, the Resolution Log, the Build Plan or any `.kiro` spec. The
nearest row, "Post-speak window | 5–10s random", is the only occurrence of that
phrase in the repository and has no prose, no trigger and no mechanism.

So the loop endpoints the utterance itself, at this layer, with the boundary
values flagged as build-time tuning and exposed as CLI flags rather than buried.
`adapters/audio_endpoint.py` carries the full reasoning, including why the 0.75 s
barge-in window is NOT the number to borrow (it governs her own sentences on the
output side) and why using an in-spec number with an undefined mechanism reads
worse than an honest placeholder.

    mic ──▶ Endpointer ──(one complete utterance)──▶ QueuedCapture
                                                          │
                                              pipeline.capture_turn()
                                    wake ▶ speaker ▶ VAD trim ▶ Whisper
                                                          │
                                          daemon.route_inbound_turn(text)
                                                          │
                                               pipeline.speak(reply)

One `capture_turn()` per utterance, so Whisper runs once per turn. Every cited gate
stays inside `AudioPipeline`, applied to a whole utterance — the endpointer trims
nothing and applies no threshold of its own.

WHAT IS REAL AND WHAT IS DEFERRED — the honest inventory
--------------------------------------------------------
REAL: microphone (sounddevice, 16 kHz mono), Silero VAD (ONNX, 512/0.5), Whisper
base on CPU, `language="en"`, the appraisal chain, the graph, Soul Filter's five
fields, the Output Gate, PAD→prosody, and Kokoro `af_bella` — v4's named local
voice.

DEFERRED, and each one says so out loud at startup rather than being inferable:

  * **Speaker verification.** See `DeferredSpeakerVerification` below. v4 names a
    Silero speaker model that Silero does not publish, so this needs an architect
    decision and cannot be resolved by reading the spec harder.
  * **The wake word**, unless a Picovoice key and a trained `.ppn` are supplied.
    The fallback is `HotkeyWakeWord`, which is v4's OWN named alternative
    ("Porcupine … or hotkey fallback"), so using it needs no ruling.
  * **Barge-in and F4.** v4 assigns the 0.75 s window to `aria_daemon.py` and the
    Daemon has both zero-effect handlers, but nothing anywhere specifies who
    segments her reply, who watches the window, or where the key listener lives.
    Unspecified rather than unbuilt. Consequence here: the microphone is not fed
    while she speaks, so she cannot currently be interrupted.
  * **Thinking sounds.** The Daemon selects a category every turn; without
    `--clip-dir` the clip is a recorded no-op. v4 specifies 5 categories and 23
    files but names no filenames.

NETWORK POSTURE. Unchanged from `main.py` and worth restating because a voice host
feels different: no listening socket, and by default the only outbound traffic is
to the local Ollama daemon. Whisper and Kokoro both run on this machine. Audio
never leaves it unless `ELEVENLABS_API_KEY` is set, and prompts never leave it
unless a cloud LLM tier is keyed. `--no-cloud` refuses both regardless.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Optional, Tuple

from daemon.audio_pipeline import AudioSegment

from main import (
    DEFAULT_KOKORO_VOICE,
    Wiring,
    advance_clocks,
    build_parser,
    report_startup,
    resolve_local_model,
)
from daemon.llm_interface import LLMTransportError, LLMUnavailableError

from adapters import audio_stack, audio_stt
from adapters._provider import AudioBackendUnavailable
from adapters.audio_capture import SoundDeviceCapture, list_devices
from adapters.audio_endpoint import (
    DEFAULT_HANGOVER_SECONDS,
    DEFAULT_MIN_SPEECH_SECONDS,
    Endpointer,
    QueuedCapture,
)
from adapters.audio_playback import CommandLinePlayback
from adapters.audio_vad import SileroVAD
from adapters.audio_wake import HotkeyWakeWord, PorcupineWakeWord
from adapters.embedding_local import EmbeddingUnavailableError

DEFAULT_VAD_MODEL = os.path.expanduser("~/.local/aria/models/silero_vad.onnx")


# ===========================================================================
# The one thing that cannot be built, and must therefore be impossible to miss.
# ===========================================================================

class DeferredSpeakerVerification:
    """Occupies the speaker slot and passes every voice. NOT a backend.

    WHY THIS EXISTS AT ALL. `AudioPipeline.capture_turn()` applies v4's cited 0.75
    cosine gate unconditionally, and `audio_stack._Absent` raises from every
    method, so there is no way to run inbound audio without SOMETHING in this slot.

    WHY IT CANNOT BE THE REAL THING YET. v4 names "Silero Speaker Verification
    (voiceprint.pt)". Silero publishes STT, TTS, VAD and text enhancement — there
    is no Silero speaker-embedding model to download. `adapters/audio_speaker.py`
    is written and correct and will work the moment it is given a scripted model
    and an enrolled voiceprint; what is missing is the DECISION about which model
    substitutes, and that adapter already refuses to make it:

        "the alternative is substituting a different speaker model, which is a
        decision about identity verification and therefore an architect call, not
        an adapter's (Rule 1)."

    Enrolment is unbuilt for the same reason and one more: binding a voiceprint to
    an `EntityNode` id is the wiring layer's call, and v4's own `aria_state.json`
    listing has a `voiceprint_enrolled` key with no procedure attached.

    WHY IT LIVES HERE AND NOT IN `adapters/`. HANDOFF_NOTES records exactly this
    reasoning for the wake word: an always-passing backend "must not be something a
    wiring layer can pick by accident", and a test asserts `audio_wake` exports
    only its two real classes. The same argument applies with more force to
    identity. So this class sits in the host that uses it, on the line that uses
    it, and `--i-accept-no-speaker-verification` is required to construct it.

    WHAT IS ACTUALLY GIVEN UP. Anyone audible becomes her primary entity for that
    turn: their words are appraised, move PAD, and are written to the graph against
    an id that means "the person I know". That is the door speaker verification
    exists to close — `audio_speaker.py` states the consequence directly, that
    treating an unrecognised voice as an event "would mean an unrecognised voice
    could move her emotional state". On a private machine with one person in the
    room that is an acceptable bring-up risk. It is not acceptable silently.
    """

    #: Above v4's cited 0.75 gate by construction. Not a threshold and not a
    #: measurement — the point is that this class does not verify anything.
    ALWAYS_PASSES = 1.0

    def __init__(self, *, acknowledged: bool) -> None:
        if not acknowledged:
            raise AudioBackendUnavailable(
                "inbound audio needs a speaker-verification backend, and this "
                "build has no model for one: v4 names Silero's speaker model and "
                "Silero does not publish one, so substituting a different model "
                "is an architect decision (Rule 1). Passing every voice instead "
                "means anyone audible is treated as the enrolled speaker — their "
                "words are appraised, move PAD and enter the graph. Re-run with "
                "--i-accept-no-speaker-verification to accept that for a "
                "bring-up."
            )
        self.comparisons = 0

    def similarity(self, audio: AudioSegment) -> float:
        self.comparisons += 1
        return self.ALWAYS_PASSES


# ===========================================================================
# Wake word — real when the operator supplies the assets, v4's fallback otherwise.
# ===========================================================================

def build_wake_word(args: argparse.Namespace) -> Tuple[object, str]:
    """Return `(backend, description)`.

    Porcupine when a key AND a keyword file are both given; otherwise
    `HotkeyWakeWord`, which v4 names itself ("Porcupine — ~2MB RAM, or hotkey
    fallback") and which therefore needs no ruling.

    NO KEYWORD IS INVENTED HERE, and the adapter would refuse one anyway. v4 never
    writes the wake phrase down — `hi_aria.onnx` in its runtime layout is the only
    evidence of one, and it names the ONNX path v4 marks as the alternative to
    Porcupine. "Aria" is not a Porcupine built-in, so a real deployment needs a
    trained `.ppn` and only the operator can supply it.
    """
    if args.porcupine_key and args.porcupine_keyword:
        backend = PorcupineWakeWord(
            access_key=args.porcupine_key,
            keyword_paths=[args.porcupine_keyword],
        )
        return backend, (
            f"Porcupine (v4's named engine) — {os.path.basename(args.porcupine_keyword)}"
        )
    return HotkeyWakeWord(), "hotkey fallback (v4's own named alternative)"


# ===========================================================================
# Wiring
# ===========================================================================

class VoiceWiring(Wiring):
    """`main.py`'s wiring with a microphone in front of it.

    Only `_build_audio` is overridden. Every soul module, the construction order,
    the primary-entity ladder and the HANDOFF contract are inherited unchanged —
    which is the point: this file must not be a second version of the system.
    """

    def _build_audio(self, args: argparse.Namespace):
        # The host owns the device. `CaptureBackend.read()` drains, so exactly one
        # consumer may hold it — the endpointer needs frames, therefore the
        # pipeline gets a push-fed `QueuedCapture` instead of the microphone.
        self.mic = SoundDeviceCapture(device=args.mic_device)
        self.queued_capture = QueuedCapture()
        self.endpointer = Endpointer(
            vad=SileroVAD(model_path=args.vad_model),
            hangover_seconds=args.silence_hangover,
            min_speech_seconds=args.min_speech,
        )
        self.wake, self.wake_description = build_wake_word(args)
        self.speaker = DeferredSpeakerVerification(
            acknowledged=args.i_accept_no_speaker_verification
        )
        # Owned here rather than inside the builder so the loop can wait for a
        # reply to finish playing before it listens again — see `_await_silence`.
        self.playback = CommandLinePlayback(
            player=args.audio_player, clip_dir=args.clip_dir
        )
        return audio_stack.build_input_chain(
            pad_source=self.pad,
            capture=self.queued_capture,
            wake_word=self.wake,
            speaker_verification=self.speaker,
            vad_model_path=args.vad_model,
            whisper_model_size=args.whisper_model,
            voice=args.voice,
            kokoro_voice=args.kokoro_voice,
            playback=self.playback,
        )

    def close(self) -> None:
        # Release the device BEFORE the base class tears down playback and the
        # graph: an open PortAudio stream outliving the process that opened it is
        # the one resource here that a later run would notice.
        mic = getattr(self, "mic", None)
        if mic is not None:
            mic.stop()
        super().close()


# ===========================================================================
# Reporting
# ===========================================================================

def report_voice_startup(w: VoiceWiring, args: argparse.Namespace) -> None:
    """Everything the text host reports, plus what the ears are doing.

    The deferred rows are printed EVERY run on purpose. An operator who accepted a
    trade-off three weeks ago should not have to remember it in order to know
    whether the voice in the room is being verified.
    """
    report_startup(w)
    vad = w.endpointer._vad
    print(f"  hearing      mic={args.mic_device if args.mic_device is not None else 'default'}"
          f"  whisper={args.whisper_model}  language={audio_stt.DEFAULT_LANGUAGE}")
    print(f"               VAD    {os.path.basename(args.vad_model)}  "
          f"lookback={vad.context_size} samples "
          f"({'v5 export' if vad.context_size else 'pre-v5 export'})")
    print(f"               endpoint  hangover={args.silence_hangover}s  "
          f"min-speech={args.min_speech}s  — BUILD-TIME values, no spec authority")
    print(f"               wake   {w.wake_description}")
    if isinstance(w.wake, HotkeyWakeWord):
        print("               press ENTER to address her; the gate is a real "
              "keypress, so")
        print("               nothing is transcribed unless you asked for it.")
    print("  speaker      NOT VERIFIED — every audible voice is treated as you.")
    print("               v4 names a Silero speaker model that Silero does not "
          "publish, so the")
    print("               substitution is an architect decision (Rule 1). Anyone "
          "in earshot can")
    print("               move her PAD and write to her graph. See "
          "DeferredSpeakerVerification.")
    print("  barge-in     OFF — the mic is not fed while she speaks, so she "
          "cannot be")
    print("               interrupted. v4 names the 0.75 s window and its owner "
          "but nothing")
    print("               specifies the mechanism, so it is unspecified rather "
          "than unbuilt.")
    if not w.playback.clip_keys:
        print("  clips        none — thinking and reconsideration sounds are a "
              "recorded no-op.")
        print("               --clip-dir takes contemplation/surprise/concern/"
              "warmth/playfulness")
        print("               and reconsideration .wav files (v4 names the "
              "categories, not filenames).")
    print()


# ===========================================================================
# The loop
# ===========================================================================

def _await_reply_finished(w: VoiceWiring) -> None:
    """Block until she has stopped talking, then forget what the mic heard.

    TWO REASONS, and the second is the one that bites. Without the wait the loop
    would immediately capture her own voice through the microphone and transcribe
    it as the next turn — she would answer herself, appraise it, and write it to
    the graph as something the user said.

    `CommandLinePlayback.wait()` exists for exactly this and says so: "NOT used on
    the wired path — `speak()` is fire-and-forget so a barge-in can interrupt it —
    but a bring-up that wants to hear a clip end needs it." Using it is what
    forecloses barge-in here, which is why the startup report says barge-in is off.
    That is a consequence of an unspecified mechanism, not a preference.
    """
    w.playback.wait()
    w.mic.read()            # discard whatever arrived while she was speaking
    w.endpointer.reset()


def _clear_pipeline_ring(w: VoiceWiring) -> None:
    """Drop the previous utterance from the pipeline's ring buffer.

    THE ONE PRIVATE REACH-IN IN THIS FILE, named rather than hidden — the same
    treatment `main.py` gives `graph._conn` for `:state`'s table counts.

    Why it is necessary: `capture_turn()` appends to the 20 s ring and then trims
    THE WHOLE RING. Since this host hands over one complete utterance per turn,
    without clearing it turn two would re-transcribe turn one's audio alongside the
    new speech — she would hear the previous sentence again, appraise it again, and
    write a second EventNode for something said once.

    Why it is a reach-in: `RingBuffer.clear()` is public, but `AudioPipeline` keeps
    the buffer private and exposes no input reset. The right fix is a public
    `reset_input()` on Module 7 — which is an approved module, so adding a method
    to it is a ruling rather than an edit. Proposed in
    `docs/RESOLUTION_LOG_DRAFT.md`; until then this line, with this comment.
    """
    w.audio._ring.clear()


def run_voice_loop(w: VoiceWiring, args: argparse.Namespace) -> int:
    entity_refs = [w.primary_entity_id] if w.primary_entity_id else []
    hotkey = w.wake if isinstance(w.wake, HotkeyWakeWord) else None

    print("Listening. Ctrl+C to leave.")
    if hotkey is not None:
        print("Press ENTER, then speak. She hears the whole sentence — there is "
              "no fixed window.\n")
    else:
        print("Say her wake word, then speak.\n")

    while True:
        try:
            if hotkey is not None:
                input("[enter to speak] ")
                hotkey.trigger()

            # --- STAGE 1: Listen / endpoint ---------------------------------
            t0 = time.perf_counter()
            utterance = None
            w.mic.read()
            w.endpointer.reset()
            while utterance is None:
                utterance = w.endpointer.feed(w.mic.read())
            t_listen = time.perf_counter() - t0

            print(f"      [heard {len(utterance) / 16000:.1f}s"
                  f" · {w.endpointer.last_end_reason}]")

            # --- STAGE 2: STT (wake + speaker + VAD trim + Whisper) --------
            t0 = time.perf_counter()
            _clear_pipeline_ring(w)
            w.queued_capture.push(utterance)
            text = w.audio.capture_turn()
            t_stt = time.perf_counter() - t0

            if not text or not text.strip():
                print("      [nothing to route — a gate declined or no words "
                      "were found]\n")
                continue

            print(f"\nyou  > {text}")

            # --- STAGE 3: Soul (appraisal → graph → filter → LLM → gate) ---
            t0 = time.perf_counter()
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
            t_soul = time.perf_counter() - t0

            print(f"aria > {response.text}\n")
            notes = []
            if response.instruction_kind != "five_field":
                notes.append(f"instruction={response.instruction_kind}")
            if response.retried:
                notes.append("retried after a gate failure")
            if response.used_minimum_safe_output:
                notes.append("MINIMUM-SAFE output")
            if notes:
                print(f"      [{' · '.join(notes)}]\n")

            # --- STAGE 4: TTS (Kokoro synthesis + playback start) ----------
            t0 = time.perf_counter()
            w.audio.speak(response.text)
            t_tts = time.perf_counter() - t0

            # --- STAGE 5: Wait for playback to finish -----------------------
            t0 = time.perf_counter()
            _await_reply_finished(w)
            t_play = time.perf_counter() - t0

            # --- TIMING REPORT ----------------------------------------------
            total = t_listen + t_stt + t_soul + t_tts + t_play
            print(f"  ⏱  listen {t_listen:.2f}s  ·  stt {t_stt:.2f}s  ·  "
                  f"soul {t_soul:.2f}s  ·  tts {t_tts:.2f}s  ·  play {t_play:.2f}s  "
                  f"=  total {total:.2f}s")
            print()

            advance_clocks(w)
            w.daemon.save_periodic()

        except (KeyboardInterrupt, EOFError):
            print("\nStopping.")
            return 0


# ===========================================================================
# CLI
# ===========================================================================

def build_voice_parser() -> argparse.ArgumentParser:
    """`main.py`'s parser plus the inbound flags, so every text-host option —
    `--no-cloud`, `--runtime-root`, `--local-model`, `--user-entity-id` — means the
    same thing here and nothing has to be kept in sync."""
    parser = build_parser()
    parser.prog = "voice_main.py"
    parser.description = "Talk to ARIA out loud."

    group = parser.add_argument_group("hearing (inbound audio)")
    group.add_argument(
        "--vad-model",
        default=os.environ.get("ARIA_VAD_MODEL", DEFAULT_VAD_MODEL),
        help=(
            f"Silero VAD ONNX model (v4: ONNX, ~2 MB). Nothing is downloaded — "
            f"fetch it from the snakers4/silero-vad repository. Default "
            f"{DEFAULT_VAD_MODEL}"
        ),
    )
    group.add_argument(
        "--whisper-model",
        default=os.environ.get("ARIA_WHISPER_MODEL", audio_stt.SPEC_MODEL_SIZE),
        help=(
            f"Whisper size. v4 names {audio_stt.SPEC_MODEL_SIZE!r} ('Whisper base, "
            f"CPU'); a different size is a different accuracy/latency trade and "
            f"should be chosen deliberately."
        ),
    )
    group.add_argument(
        "--mic-device",
        default=os.environ.get("ARIA_MIC_DEVICE"),
        help="input device index or name. Omit for the system default; "
             "--list-devices to see them.",
    )
    group.add_argument(
        "--list-devices",
        action="store_true",
        help="print the input devices and exit",
    )
    group.add_argument(
        "--silence-hangover",
        type=float,
        default=float(os.environ.get("ARIA_SILENCE_HANGOVER", DEFAULT_HANGOVER_SECONDS)),
        help=(
            f"seconds of quiet that end an utterance (default "
            f"{DEFAULT_HANGOVER_SECONDS}). A BUILD-TIME value with no spec "
            f"authority: v4 defines no end-of-utterance boundary anywhere. Raise "
            f"it if she cuts you off mid-thought."
        ),
    )
    group.add_argument(
        "--min-speech",
        type=float,
        default=float(os.environ.get("ARIA_MIN_SPEECH", DEFAULT_MIN_SPEECH_SECONDS)),
        help=(
            f"seconds of speech before a sound counts as an utterance (default "
            f"{DEFAULT_MIN_SPEECH_SECONDS}). Also build-time — it keeps a door "
            f"closing from costing a Whisper call."
        ),
    )

    wake = parser.add_argument_group("wake word")
    wake.add_argument(
        "--porcupine-key",
        default=os.environ.get("PORCUPINE_ACCESS_KEY"),
        help="Picovoice access key (free). Without it the hotkey fallback is used "
             "— which v4 names itself, so it needs no justification.",
    )
    wake.add_argument(
        "--porcupine-keyword",
        default=os.environ.get("ARIA_PORCUPINE_KEYWORD"),
        help="path to a trained .ppn for her name. 'Aria' is not a Porcupine "
             "built-in and no substitute is guessed here.",
    )

    deferred = parser.add_argument_group("deferred, pending an architect ruling")
    deferred.add_argument(
        "--i-accept-no-speaker-verification",
        action="store_true",
        help=(
            "run without speaker verification. REQUIRED to start: v4's cited 0.75 "
            "cosine gate would otherwise reject everyone, and passing every voice "
            "instead means anyone audible is treated as you — appraised, moving "
            "PAD, written to her graph. Explicit because identity is the one thing "
            "this project treats as unrecoverable if it goes wrong."
        ),
    )
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_voice_parser().parse_args(argv)

    if args.list_devices:
        devices = list_devices()
        if not devices:
            print("no input devices (is `sounddevice` installed?)", file=sys.stderr)
            return 2
        print("Input devices:")
        for line in devices:
            print(f"  {line}")
        return 0

    # `--audio` is what `main.py` uses to opt into speaking. A voice host speaks by
    # definition, so it is set rather than required — nobody should have to ask a
    # voice interface for a voice.
    args.audio = True
    if args.kokoro_voice is None:
        args.kokoro_voice = DEFAULT_KOKORO_VOICE
    # An index must be an int for PortAudio; a name stays a string.
    if args.mic_device is not None and str(args.mic_device).isdigit():
        args.mic_device = int(args.mic_device)

    print("ARIA — voice. Ctrl+C to leave.\n", flush=True)

    local_model = resolve_local_model(args)
    if local_model is None:
        return 2
    args.local_model = local_model

    wiring = None
    try:
        wiring = VoiceWiring(args)
    except EmbeddingUnavailableError as exc:
        print(f"cannot start: {exc}", file=sys.stderr)
        return 2
    except AudioBackendUnavailable as exc:
        # A missing provider, model file or acknowledgement is a configuration
        # problem with a one-line remedy, which the raiser already put in the
        # message. A traceback would bury it under import machinery.
        print(f"cannot start: {exc}", file=sys.stderr)
        print("  --audio-preflight reports which backends are available without "
              "starting anything.", file=sys.stderr)
        return 2

    try:
        wiring.daemon.startup()
        report_voice_startup(wiring, args)
        return run_voice_loop(wiring, args)
    except LLMTransportError as exc:
        print(f"cannot start: the local voice would not load: {exc}", file=sys.stderr)
        return 2
    finally:
        # The HANDOFF contract's other half. `shutdown()` flushes PAD, Energy and
        # last_applied_valence; calling it before `startup()` would raise, and
        # there would be nothing to flush.
        if wiring is not None:
            if wiring.daemon.started:
                wiring.daemon.shutdown()
            wiring.close()


if __name__ == "__main__":
    sys.exit(main())
