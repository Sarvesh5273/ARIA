"""Concrete `VideoWindow` — v4's `ui/aria_window.py`: PyQt6 frameless, libmpv.

WHAT THIS SATISFIES
-------------------
`daemon.visual_layer.VideoWindow`, a one-method Protocol:

    def play_loop(self, loop: ZoneLoop) -> None

Two implementations:

    MpvVideoWindow      v4's real window — PyQt6 frameless always-on-top, libmpv
                        embedded, lazily imported.
    LoggingVideoWindow  headless. Records the loop signals and plays nothing.

THE WINDOW OWNS THE ONE THING THE MODULE DELIBERATELY DOES NOT
--------------------------------------------------------------
The Protocol's docstring is explicit: the window "owns 'finishing the current
loop cycle before switching -- no jarring cuts' (v4 'Transition Logic'). This
module only signals WHICH loop."

So `Module 10` hands over a target and walks away. If this adapter switched files
the instant it was told to, v4's no-jarring-cuts rule would be implemented
nowhere — the Visual Layer cannot do it (it has no notion of playback position)
and would be wrong to try, since that is presentation timing rather than zone
selection.

`MpvVideoWindow` therefore keeps a PENDING target and applies it when the current
loop reaches its own boundary, watching mpv's own end-of-file signal for a
looping file. Two consequences worth stating:

  * The 8-second stability gate and this are DIFFERENT mechanisms at different
    layers. The gate decides whether a zone CHANGE is allowed at all (v4's
    anti-flicker rule, Module 10's job). This decides when an allowed change is
    rendered (v4's no-jarring-cuts rule, the window's job). Neither substitutes
    for the other.
  * A newer pending target REPLACES an older one rather than queueing. If PAD
    moved twice before a boundary arrived, showing the intermediate zone would
    display a state she is no longer in — so the queue depth is one, by design.

TWO SIGNALS BYPASS THE BOUNDARY WAIT, AND BOTH ARE FROM THE MODULE'S OWN RULES
-----------------------------------------------------------------------------
Module 10 renders promptly (ungated) in two cases, and the window must not
re-introduce a delay it deliberately skipped:

  * a VARIANT change within the same zone — the mouth tracking the voice ("a
    talking<->idle change alters only the VARIANT ... and is NOT subject to the
    8-second zone gate"). Waiting for a loop boundary would leave her mouth still
    while she talks.
  * entering INWARD_WAITING — "a failure is not zone flicker -> ungated".

Both are applied immediately. Everything else waits for the boundary.

THREAD SAFETY IS NOT OPTIONAL HERE
----------------------------------
Qt requires its event loop and all widget calls on ONE thread, and
`VisualLayer.refresh()` is called by whatever drives the visual loop — in
practice not that thread. So `play_loop` never touches mpv directly: it records
the target under a lock, and the Qt thread picks it up on its own timer. That is
also why `play_loop` cannot raise a playback error: it has not tried to play
anything yet.

A MISSING LOOP FILE IS RECORDED, NOT RAISED
-------------------------------------------
`play_loop` is called from inside `VisualLayer.refresh()`, which the driver calls
on a timer — and in the wired REPL that timer is the turn loop. An exception
there would take down a conversation because a video file was absent. So a
missing file is recorded in `missing_loops` and the current loop keeps playing:
the face going stale is the correct failure for a leaf, and it is visible.

`missing_loop_files()` exists so the absence is caught at WIRING time instead,
which is where it should be noticed.

v4 NAMES 16 FILES PLUS ONE
--------------------------
"16 video loop files (8 zones x 2 states: idle + talking)" plus the separate
inward/waiting loop = 17 keys, and `ZoneLoop.loop_id` produces exactly those:
`neutral_idle_idle`, `engaged_talking`, ..., and `inward_waiting` (which
normalises to a single variant at construction, because v4 names it in the
singular). `expected_loop_ids()` enumerates them so a catalogue can be checked
rather than assumed.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from daemon.visual_layer import PAD_ZONES, SpeakingState, Zone, ZoneLoop

from adapters._provider import AudioBackendUnavailable, module_available, require_module

_PYQT = "PyQt6.QtWidgets"
_MPV = "mpv"
_INSTALL_QT = "pip install PyQt6"
_INSTALL_MPV = "pip install mpv   (needs libmpv: brew install mpv)"

#: How often the Qt thread checks for a pending target. Presentation plumbing,
#: not a spec value — small enough that a variant change looks immediate, large
#: enough to cost nothing.
DEFAULT_POLL_MS = 100          # TODO(build-time): window poll interval

#: Video container extensions looked for when resolving a loop key to a file.
LOOP_EXTENSIONS: Sequence[str] = (".mp4", ".mov", ".webm", ".mkv")


def expected_loop_ids() -> Tuple[str, ...]:
    """The 17 loop keys v4's catalogue implies: 8 zones x 2 variants, plus the
    single inward/waiting loop. Derived from `ZoneLoop.loop_id` rather than
    written out, so a change to the naming cannot leave this stale."""
    ids = [
        ZoneLoop(zone, variant).loop_id
        for zone in PAD_ZONES
        for variant in (SpeakingState.IDLE, SpeakingState.TALKING)
    ]
    ids.append(ZoneLoop(Zone.INWARD_WAITING).loop_id)
    return tuple(ids)


def resolve_loop_files(directory: str) -> Dict[str, Path]:
    """Map each expected loop key to a file in `directory`, where one exists."""
    root = Path(directory).expanduser()
    found: Dict[str, Path] = {}
    for loop_id in expected_loop_ids():
        for extension in LOOP_EXTENSIONS:
            candidate = root / f"{loop_id}{extension}"
            if candidate.is_file():
                found[loop_id] = candidate
                break
    return found


def missing_loop_files(directory: str) -> Tuple[str, ...]:
    """Which of the 17 keys have no file. For a wiring-time check."""
    present = resolve_loop_files(directory)
    return tuple(k for k in expected_loop_ids() if k not in present)


class LoggingVideoWindow:
    """`VideoWindow` that records loop signals and displays nothing.

    Legitimate for the same reason `audio_noop.py` is: the Visual Layer is a LEAF.
    `play_loop` returns None, Module 10 ignores the result, and no soul state
    depends on what was displayed — so substituting the display changes no
    behaviour inside the system.

    It earns its place beyond that, though. PyQt6 and libmpv are absent on a bare
    machine, so this is the only way the zone machinery — the categorical mapping,
    the 8-second gate, the variant tracking, the degradation override — can be
    driven and OBSERVED for real rather than only unit-tested.
    """

    def __init__(self, *, on_change=None) -> None:
        self.loops: List[ZoneLoop] = []
        self.loop_ids: List[str] = []
        self._on_change = on_change

    def play_loop(self, loop: ZoneLoop) -> None:
        self.loops.append(loop)
        self.loop_ids.append(loop.loop_id)
        if self._on_change is not None:
            self._on_change(loop)

    @property
    def current_loop_id(self) -> Optional[str]:
        return self.loop_ids[-1] if self.loop_ids else None


class MpvVideoWindow:
    """`VideoWindow` backed by a PyQt6 frameless always-on-top window with libmpv
    embedded — v4's `ui/aria_window.py`.

    Holds a widget, an mpv handle, the loop catalogue, and the pending target
    under a lock. No soul state, no PAD handle: this receives a `ZoneLoop` and
    plays a file, and there is no parameter through which anything else could
    arrive.
    """

    def __init__(
        self,
        *,
        loop_dir: str,
        width: int = 480,
        height: int = 480,
        poll_ms: int = DEFAULT_POLL_MS,
        require_all_loops: bool = False,
    ) -> None:
        self._loops = resolve_loop_files(loop_dir)
        if not self._loops:
            raise AudioBackendUnavailable(
                f"no video loops found in {loop_dir!r}. Expected files named "
                f"{expected_loop_ids()[0]}.mp4 and so on — "
                f"{len(expected_loop_ids())} keys in total."
            )
        missing = missing_loop_files(loop_dir)
        if missing and require_all_loops:
            raise AudioBackendUnavailable(
                f"{len(missing)} of {len(expected_loop_ids())} video loops are "
                f"missing from {loop_dir!r}: {list(missing)}"
            )
        self.missing_at_startup = missing

        widgets = require_module(
            _PYQT, purpose="the video window", install=_INSTALL_QT
        )
        core = require_module(
            "PyQt6.QtCore", purpose="the video window", install=_INSTALL_QT
        )
        mpv_module = require_module(
            _MPV, purpose="video loop playback", install=_INSTALL_MPV
        )
        self._qt = core
        self._app = widgets.QApplication.instance() or widgets.QApplication([])

        # Frameless, always-on-top, no window chrome (v4: "a PyQt6 frameless
        # always-on-top window"). Her face is a presence on the desktop, not an
        # application window with a title bar.
        flags = (
            core.Qt.WindowType.FramelessWindowHint
            | core.Qt.WindowType.WindowStaysOnTopHint
            | core.Qt.WindowType.Tool
        )
        self._widget = widgets.QWidget(flags=flags)
        self._widget.resize(width, height)
        self._widget.setAttribute(core.Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self._widget.show()

        try:
            self._mpv = mpv_module.MPV(
                wid=str(int(self._widget.winId())),
                # The loop plays continuously — that is what a "loop" is here.
                loop_file="inf",
                # No UI of mpv's own: this is her face, not a media player.
                osc=False,
                input_default_bindings=False,
                input_vo_keyboard=False,
                # Video only. Every sound in this system comes from Module 7, and
                # a loop file with an audio track would otherwise talk over her.
                audio="no",
            )
        except Exception as exc:
            raise AudioBackendUnavailable(
                f"could not start libmpv in the window: {exc}"
            ) from exc

        self._lock = threading.Lock()
        self._pending: Optional[ZoneLoop] = None
        self._pending_immediate = False
        self._current: Optional[ZoneLoop] = None
        self._boundary_reached = True     # nothing playing yet, so free to start
        self.missing_loops: List[str] = []
        self.switches = 0
        self.deferred_switches = 0

        # mpv fires this each time a looping file restarts, which is exactly the
        # loop boundary v4's no-jarring-cuts rule refers to.
        @self._mpv.event_callback("playback-restart")
        def _on_restart(_event):    # pragma: no cover - provider callback
            with self._lock:
                self._boundary_reached = True

        self._timer = core.QTimer()
        self._timer.timeout.connect(self._apply_pending)
        self._timer.start(poll_ms)

    # -- VideoWindow --------------------------------------------------------

    def play_loop(self, loop: ZoneLoop) -> None:
        """Record the target loop. Thread-safe; touches no widget and no mpv.

        Applied by the Qt thread — immediately for a variant change or for
        INWARD_WAITING, otherwise at the next loop boundary. See the module
        docstring for why those two bypass the wait and why the queue depth is
        one.

        Never raises. A missing file is recorded and the current loop keeps
        playing; the caller is inside `VisualLayer.refresh()` on the driver's
        timer, and taking down a conversation over a missing video file would be
        the wrong trade for a leaf.
        """
        with self._lock:
            self._pending = loop
            self._pending_immediate = (
                loop.zone is Zone.INWARD_WAITING
                or (
                    self._current is not None
                    and loop.zone is self._current.zone
                    and loop.variant is not self._current.variant
                )
            )

    # -- read-only observability -------------------------------------------

    @property
    def current_loop_id(self) -> Optional[str]:
        with self._lock:
            return self._current.loop_id if self._current else None

    @property
    def pending_loop_id(self) -> Optional[str]:
        with self._lock:
            return self._pending.loop_id if self._pending else None

    def describe(self) -> str:
        have = len(self._loops)
        total = len(expected_loop_ids())
        tail = (
            f"  MISSING {len(self.missing_at_startup)}: "
            f"{list(self.missing_at_startup)[:4]}..."
            if self.missing_at_startup else ""
        )
        return f"video: PyQt6 + libmpv, {have}/{total} loops{tail}"

    # -- Qt thread ----------------------------------------------------------

    def pump(self, ms: int = 0) -> None:
        """Run the Qt event loop briefly.

        The caller owns the event loop, because a driver that blocked in
        `QApplication.exec()` could never advance the soul clocks. A REPL calls
        this alongside `run_scheduler_step()`.
        """
        self._app.processEvents()
        if ms:
            self._qt.QThread.msleep(ms)
            self._app.processEvents()

    def _apply_pending(self) -> None:
        """Swap to the pending loop if it is time. Runs on the Qt thread only."""
        with self._lock:
            target = self._pending
            immediate = self._pending_immediate
            if target is None:
                return
            if target == self._current:
                self._pending = None
                return
            if not (immediate or self._boundary_reached):
                self.deferred_switches += 1
                return
            self._pending = None
            self._boundary_reached = False

        path = self._loops.get(target.loop_id)
        if path is None:
            # Recorded, not raised — and the previous loop keeps playing, so her
            # face goes stale rather than dark.
            if target.loop_id not in self.missing_loops:
                self.missing_loops.append(target.loop_id)
            return
        try:
            self._mpv.play(str(path))
        except Exception:   # pragma: no cover - provider failure at runtime
            # Same reasoning: a playback failure must not propagate into the
            # driver's timer. Leaving `_current` alone means the next tick
            # retries.
            return
        with self._lock:
            self._current = target
            self.switches += 1

    def close(self) -> None:
        """Stop the timer, terminate mpv, hide the window. Idempotent."""
        timer, self._timer = getattr(self, "_timer", None), None
        if timer is not None:
            timer.stop()
        player, self._mpv = getattr(self, "_mpv", None), None
        if player is not None:
            try:
                player.terminate()
            except Exception:   # pragma: no cover - provider teardown
                pass
        widget, self._widget = getattr(self, "_widget", None), None
        if widget is not None:
            widget.hide()

    def __enter__(self) -> "MpvVideoWindow":
        return self

    def __exit__(self, *exc) -> bool:
        self.close()
        return False


def available() -> bool:
    """Are both providers importable? Both are required — a window with no
    player shows nothing, and a player with no window has nowhere to draw."""
    return module_available(_PYQT) and module_available(_MPV)


def install_hint() -> str:
    return f"{_INSTALL_QT}  and  {_INSTALL_MPV}"


def preflight_report(loop_dir: Optional[str] = None) -> str:
    """What the visual layer would need, as text a human reads."""
    lines = [
        f"  {'ok     ' if module_available(_PYQT) else 'MISSING'} PyQt6",
        f"  {'ok     ' if module_available(_MPV) else 'MISSING'} python-mpv (libmpv)",
    ]
    if not available():
        lines.append(f"    {install_hint()}")
    if loop_dir:
        present = resolve_loop_files(loop_dir)
        missing = missing_loop_files(loop_dir)
        lines.append(
            f"  loops    {len(present)}/{len(expected_loop_ids())} found in "
            f"{loop_dir}"
        )
        if missing:
            lines.append(f"    missing: {list(missing)}")
    else:
        lines.append(
            f"  loops    no --loop-dir given; v4 names "
            f"{len(expected_loop_ids())} files "
            f"(8 zones x 2 variants, plus inward_waiting)"
        )
    return "\n".join(lines)
