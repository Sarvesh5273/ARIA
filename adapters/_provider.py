"""Shared plumbing for adapters that wrap a real, heavy provider.

WHY THIS EXISTS
---------------
`daemon/` has zero external dependencies, and that property is what makes the
soul suite hermetic and fast. `adapters/` is where dependencies are allowed to
live — but "allowed" must not mean "imported at module scope", because:

  * `import adapters.audio_stt` would then fail on a machine with no Whisper
    installed, so a bring-up could not even ASK what is available;
  * `tests/` imports these modules to check contract conformance, and the suite
    must not need torch on the machine to run;
  * `make check` has to stay a couple of seconds.

So every provider import happens LAZILY — inside a constructor or a method, never
at module import time — and a missing provider produces one actionable error
naming the install line rather than an ImportError traceback from three frames
deep.

THE PATTERN, AND THE ONE RULE THAT MATTERS
------------------------------------------
`require(...)` is called at CONSTRUCTION, not at first use. An audio stack that
is missing a backend should fail while the operator is still looking at the
startup output, not four turns into a conversation. That is the same reasoning
`embedding_local.preflight()` uses: two of the three `embed()` call sites in the
soul layer swallow exceptions, so a late failure is a quiet one.

`available()` is the non-raising question, for a preflight report that wants to
list what is and is not there without stopping.

NOTHING HERE DECIDES ANYTHING. No soul state, no numbers, no meaning — it is an
import with a better error message.
"""

from __future__ import annotations

import importlib
import shutil
from types import ModuleType
from typing import Optional


class AudioBackendUnavailable(Exception):
    """A provider an audio backend needs is not installed or not reachable.

    Deliberately NOT `daemon.audio_pipeline.TTSUnavailable`. That exception has a
    specific job — it is the signal `AudioPipeline._synthesize_with_fallback`
    catches to degrade cloud -> local, i.e. "this renderer cannot render right
    now". A missing dependency is a different fact: it is a configuration error
    that no fallback fixes, and dressing it as a transient render failure would
    make a broken install look like graceful degradation.

    TTS backends raise `TTSUnavailable` for a render failure and this for a
    missing provider, and those two really are different problems.
    """


def require_module(
    module_name: str, *, purpose: str, install: str
) -> ModuleType:
    """Import `module_name` or raise `AudioBackendUnavailable` naming the fix.

    `purpose` says what the caller wanted it for and `install` is the literal
    command to run — an error a reader can act on without opening this file.
    """
    try:
        return importlib.import_module(module_name)
    except ImportError as exc:
        raise AudioBackendUnavailable(
            f"{purpose} needs the {module_name!r} package, which is not "
            f"installed. Install it with:  {install}"
        ) from exc


def module_available(module_name: str) -> bool:
    """Is `module_name` importable? Never raises — this is the preflight question,
    and "no" is an answer rather than an error."""
    try:
        importlib.import_module(module_name)
    except ImportError:
        return False
    return True


def require_binary(name: str, *, purpose: str, install: str) -> str:
    """Resolve an executable on PATH or raise `AudioBackendUnavailable`.

    Returns the ABSOLUTE path, so the caller passes a resolved path to
    `subprocess` rather than re-resolving a bare name later. That matters for the
    playback backend, whose `stop()` has to be able to kill the exact process it
    started.
    """
    found = shutil.which(name)
    if not found:
        raise AudioBackendUnavailable(
            f"{purpose} needs the {name!r} executable, which is not on PATH. "
            f"Install it with:  {install}"
        )
    return found


def binary_available(name: str) -> Optional[str]:
    """The absolute path to `name`, or None. The non-raising form."""
    return shutil.which(name)
