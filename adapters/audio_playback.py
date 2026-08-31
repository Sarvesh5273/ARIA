"""Concrete `PlaybackBackend` — v4: "pw-play / PyQt6 audio", plus F4's stop.

WHAT THIS SATISFIES
-------------------
`daemon.audio_pipeline.PlaybackBackend`:

    def play(self, wav: bytes) -> None
    def play_cached(self, key: str) -> None
    def stop(self) -> None

THE MOST CONSTRAINED METHOD IN THE PROJECT IS `stop()`
-----------------------------------------------------
`AudioPipeline.stop_playback()`'s entire body is `self._playback.stop()`, and
Addendum §5 makes F4 and pause-based barge-in "a functional audio stop mechanism
only ... No PAD effect, no appraisable event, no graph write, nothing." The v4
constants-table row giving F4 a PAD effect is REMOVED by §5.

So this class holds a subprocess handle and nothing else. It has no PAD handle, no
graph handle, no appraisal handle, no state handle — there is no constructor
parameter through which one could arrive, which is what makes "F4 has zero
internal effect" structural here rather than a promise. `stop()` terminates a
process. That is the whole mechanism.

WHY A SUBPROCESS PLAYER AND NOT A LIBRARY
-----------------------------------------
v4 names `pw-play`, which IS a command-line player, so a subprocess is the shape
v4 describes rather than a shortcut around one. It also buys the property `stop()`
needs most: a separately-scheduled process can be killed instantly, from the
calling thread, with no cooperation from the audio library and no waiting on a
callback to notice a flag. A barge-in that has to wait for a buffer to drain is
not a barge-in.

`afplay` is used on macOS. That is a PLAYER substitution, not an architecture one —
v4's `pw-play` is PipeWire and does not exist here, and both are "hand a WAV to
the OS and let it play". The player is chosen by what is on PATH, in a documented
order, and the choice is reported.

PRE-CACHED CLIPS ARE REGISTERED, NEVER SYNTHESISED
--------------------------------------------------
`play_cached(key)` is v4's thinking sounds and the reconsideration sound: "a
breath, a pause", pre-recorded clips, chosen by the Daemon and by Soul Filter's
retry path. This class maps a key to a file and plays it. It does NOT synthesise a
missing clip — the whole point of a pre-cached clip is that it costs no generation
time, and quietly rendering one through TTS would put a network round trip inside
the gap that clip exists to cover.

A MISSING CLIP IS A NO-OP, DELIBERATELY
---------------------------------------
`play_cached` on an unregistered key records the miss and returns. It does not
raise, and that asymmetry with `play()` is the point: the caller is
`AudioPipeline.play_thinking_sound`, which the Daemon calls BEFORE generation on a
normal turn. An exception there would abort a turn that was otherwise fine — a
missing comfort noise would cost her the answer. Real speech failing is different
and does raise.

ONE PROCESS AT A TIME
---------------------
`play()` stops whatever is already playing before starting. Two overlapping
players talking over each other is never wanted, and it would also make `stop()`
ambiguous about which process F4 was meant to kill.
"""

from __future__ import annotations

import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from adapters._provider import AudioBackendUnavailable, binary_available, require_binary

#: Player preference order. `afplay` first on macOS because it is always present;
#: `pw-play` is v4's named tool and is preferred where PipeWire exists; `aplay`
#: and `ffplay` are common fallbacks. First one found wins, and the choice is
#: reported by `describe()` rather than being silent.
PLAYER_CANDIDATES: Sequence[str] = ("afplay", "pw-play", "aplay", "ffplay")

#: Extra flags some players need to be usable here: no window, no keyboard
#: handling, exit when the clip ends. Nothing about audio content.
_PLAYER_FLAGS: Dict[str, Sequence[str]] = {
    "ffplay": ("-nodisp", "-autoexit", "-loglevel", "quiet"),
}

_INSTALL = (
    "macOS has afplay built in; on Linux install pipewire-utils (pw-play, v4's "
    "named player) or alsa-utils (aplay)"
)


class CommandLinePlayback:
    """`PlaybackBackend` driving an OS audio player as a subprocess.

    Holds a player path, a clip registry, one process handle and a lock. Nothing
    else — see the module docstring on why the absence of any other handle is what
    makes F4's zero-effect guarantee structural.
    """

    def __init__(
        self,
        *,
        player: Optional[str] = None,
        cached_clips: Optional[Dict[str, str]] = None,
        clip_dir: Optional[str] = None,
    ) -> None:
        self._player = self._resolve_player(player)
        self._flags = list(_PLAYER_FLAGS.get(Path(self._player).name, ()))
        self._clips: Dict[str, Path] = {}
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen] = None
        self._tempfiles: List[Path] = []

        if clip_dir:
            self.register_clip_dir(clip_dir)
        for key, path in (cached_clips or {}).items():
            self.register_clip(key, path)

        # Observability only. Never read back into any decision.
        self.plays = 0
        self.cached_plays: List[str] = []
        self.missing_clips: List[str] = []
        self.stops = 0

    @staticmethod
    def _resolve_player(preferred: Optional[str]) -> str:
        if preferred:
            return require_binary(
                preferred, purpose="audio playback", install=_INSTALL
            )
        for candidate in PLAYER_CANDIDATES:
            found = binary_available(candidate)
            if found:
                return found
        raise AudioBackendUnavailable(
            f"no audio player found on PATH (tried {list(PLAYER_CANDIDATES)}). "
            f"{_INSTALL}"
        )

    @property
    def player(self) -> str:
        return self._player

    def describe(self) -> str:
        """Startup-report line. Names the player actually chosen, because a
        substituted player is a real difference and should not be inferred."""
        name = Path(self._player).name
        note = "" if name == "pw-play" else "  (v4 names pw-play; substituted)"
        return f"playback: {name}{note}  clips={sorted(self._clips)}"

    # -- pre-cached clip registry -------------------------------------------

    def register_clip(self, key: str, path: str) -> None:
        """Map a clip key to a file. Missing files are refused HERE, at wiring
        time, rather than at the moment she needs the sound."""
        resolved = Path(path).expanduser()
        if not resolved.is_file():
            raise AudioBackendUnavailable(
                f"pre-cached clip {key!r} not found at {resolved}"
            )
        self._clips[key] = resolved

    def register_clip_dir(self, directory: str) -> None:
        """Register every WAV in a directory under its stem as the key — so
        `reconsideration.wav` becomes the key `RECONSIDERATION_SOUND_KEY` uses."""
        root = Path(directory).expanduser()
        if not root.is_dir():
            raise AudioBackendUnavailable(f"clip directory not found: {root}")
        for candidate in sorted(root.glob("*.wav")):
            self._clips[candidate.stem] = candidate

    @property
    def clip_keys(self) -> Sequence[str]:
        return sorted(self._clips)

    # -- PlaybackBackend ----------------------------------------------------

    def play(self, wav: bytes) -> None:
        """Play WAV bytes. Stops any current playback first.

        The bytes are written to a temp file because every player named here takes
        a path. The file is cleaned up on the NEXT play or on `close()`, not
        immediately — deleting it while the player still has it open would cut the
        audio off mid-sentence on some platforms.
        """
        if not wav:
            raise ValueError("nothing to play: empty WAV")
        handle = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        try:
            handle.write(wav)
        finally:
            handle.close()
        path = Path(handle.name)
        self._start([self._player, *self._flags, str(path)])
        self._tempfiles.append(path)
        self.plays += 1

    def play_cached(self, key: str) -> None:
        """Play a registered clip. A missing key is a recorded NO-OP.

        See the module docstring: the caller is on the pre-generation path of an
        otherwise-fine turn, so raising here would cost her the answer over a
        missing comfort noise.
        """
        clip = self._clips.get(key)
        if clip is None:
            self.missing_clips.append(key)
            return
        self._start([self._player, *self._flags, str(clip)])
        self.cached_plays.append(key)

    def stop(self) -> None:
        """Stop playback. F4 / barge-in — Addendum §5, audio ONLY.

        Terminates the player process and returns. There is no PAD read or write,
        no appraisal, no graph write, no need change, no persisted-state write, and
        no way to reach any of those from here. Safe to call when nothing is
        playing.
        """
        self.stops += 1
        with self._lock:
            process, self._process = self._process, None
        _terminate(process)

    # -- process handling ---------------------------------------------------

    def _start(self, command: List[str]) -> None:
        with self._lock:
            previous, self._process = self._process, None
        _terminate(previous)
        self._sweep_tempfiles()
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError as exc:
            raise AudioBackendUnavailable(
                f"could not start the audio player {command[0]!r}: {exc}"
            ) from exc
        with self._lock:
            self._process = process

    @property
    def is_playing(self) -> bool:
        with self._lock:
            process = self._process
        return process is not None and process.poll() is None

    def wait(self, timeout: Optional[float] = None) -> None:
        """Block until the current clip finishes. NOT used on the wired path —
        `speak()` is fire-and-forget so a barge-in can interrupt it — but a
        bring-up that wants to hear a clip end needs it."""
        with self._lock:
            process = self._process
        if process is not None:
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                pass

    def _sweep_tempfiles(self) -> None:
        """Delete temp WAVs from previous plays. Runs when a new play starts, by
        which point the old player is already terminated."""
        for path in self._tempfiles:
            try:
                path.unlink(missing_ok=True)
            except OSError:  # pragma: no cover - best effort cleanup
                pass
        self._tempfiles.clear()

    def close(self) -> None:
        """Stop and clean up. Idempotent."""
        self.stop()
        self._sweep_tempfiles()

    def __enter__(self) -> "CommandLinePlayback":
        return self

    def __exit__(self, *exc) -> bool:
        self.close()
        return False


def _terminate(process: Optional[subprocess.Popen]) -> None:
    """Stop a player process now.

    `terminate()` then a short `wait()`, then `kill()` — the escalation matters
    because a player that ignores SIGTERM would otherwise keep talking over her
    next sentence, and F4 means stop.
    """
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
        try:
            process.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=0.5)
    except OSError:  # pragma: no cover - process already gone
        pass


def available() -> bool:
    return any(binary_available(name) for name in PLAYER_CANDIDATES)


def install_hint() -> str:
    return _INSTALL
