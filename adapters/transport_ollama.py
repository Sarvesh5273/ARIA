"""Concrete `LocalModelTransport` adapter — the local LLM, served by Ollama.

WHAT THIS SATISFIES
-------------------
`daemon.llm_interface.LocalModelTransport`:

    def generate(self, prompt: AssembledPrompt) -> str
    @property is_loaded -> bool
    def load(self) -> None
    def unload(self) -> None

plus the OPTIONAL `daemon.backend_router.HealthProbe` (`is_healthy()`), which is
checked structurally. Implementing it is not decoration: `BackendRouter.select()`
requires `health["gemma"] AND is_loaded`, and for a transport with no probe the
router falls back to `is_loaded` alone. Answering both questions separately —
"is the daemon up and holding this model" vs "have I loaded it" — is the honest
split, and it is strictly more information than the fallback.

THE PROMPT MAPPING — WHAT CROSSES, EXACTLY
------------------------------------------
`AssembledPrompt` carries three text surfaces and `as_text()` joins them in this
order with blank lines: `instruction_text`, `session_context` (when non-empty),
`user_message`. `LLMInterface`'s own docstring sanctions the role split: "a cloud
SDK adapter typically maps instruction_text -> system role and user_message ->
the user turn; a local Gemma adapter does the same."

So:

    system = instruction_text                     (the five fields, or emergency)
    prompt = session_context + "\\n\\n" + user_message   (session first, as as_text does)

Nothing is dropped, nothing is reordered, nothing is added, and nothing is
inspected. `test_transport_ollama.py` asserts that every character of every
surface reaches the request, because a mapping that silently dropped
`session_context` would be a §9 boundary change made by an adapter — the wrong
place for it entirely.

MODEL RESIDENCY
---------------
Ollama loads a model on first use and evicts it after an idle timeout. The
architect's decision is that the local voice loads at startup and STAYS resident
(`AriaDaemon.startup()` -> `BackendRouter.ensure_local_loaded()`, and the router
never unloads it). `keep_alive=-1` on every request is how that is expressed to
Ollama: pin it indefinitely. `unload()` sends `keep_alive=0`, which evicts
immediately — it exists because the Protocol requires it, not because this
adapter ever calls it.

MODEL NAME — TWO CONSTANTS THAT NO LONGER AGREE, DELIBERATELY
--------------------------------------------------------------
v4 names "Gemma 4 E2B QAT (~2.62 GB)" in its RAM budget table. The Ollama tag
for exactly that model is `gemma4:e2b-it-qat` (4.3 GB), and it remains
`SPEC_MODEL` — the citation of what the precedence chain says.

`DEFAULT_MODEL` is `qwen3.5:9b-mlx` by architect ruling (Resolution Log item 24).
The two constants now hold DIFFERENT values for the first time, which is the
state `resolve_model()`'s ladder was written for.

It briefly was not. `gemma4:12b-it-qat` (7.2 GB) was made the default on
2026-08-22 and reverted the same day on measurement. Recorded here rather than
quietly undone, because the reasoning that chose it was plausible and someone will
reconstruct it:

  * The argument was that the local model's job is NARROW — because of the
    five-field boundary it never appraises, retrieves, computes emotion, gates
    morally or validates output, so its whole job is rendering prose in a
    specified register while honouring Field 5. Therefore reasoning is not worth
    local memory, but instruction ADHERENCE is, and adherence improves from ~4B
    to ~12B. QAT made 12B affordable: `12b-it-qat` at 7.2 GB is SMALLER than
    `e4b-it-q4_K_M` at 9.6 GB while being a 12B dense model.
  * The memory arithmetic was correct. What it never measured was tokens per
    second, or whether adherence actually improved. Measured: 12b ran 54–162 s
    per turn against e2b's 2–12 s (10–13×, rising with context), scored
    IDENTICALLY on every gate metric, and on a flattery-bait turn reflected the
    feeling back without engaging the question — arguably the deflection Field 5
    had just prohibited.
  * Why the argument failed, since the premise was right and the conclusion
    backwards: the five-field boundary makes the task SHORT as well as narrow — a
    few hundred tokens in, a few hundred out, in a specified register. A
    well-tuned small instruct model is already at ceiling there, and a 12B
    model's extra capacity goes into reasoning depth the architecture routes to
    cloud. **The same boundary that makes the job narrow is what makes a bigger
    model not pay for itself.**

Numbers and the register comparison are in `PROJECT_STATUS.md` under "Local model
latency and register measurements".

`resolve_model()`'s ladder is written in terms of "the configured default" versus
"what v4 names". Those were coincidentally equal until item 24 and are now
genuinely different, so rung 2 — fall back to v4's own model — does real work
instead of being unreachable. The ladder RETURNS a note rather than printing, so
the caller decides how loud to be.

It still never picks an arbitrary installed model. `_LOCAL_VOICE_FAMILY_PREFIXES`
is the SANCTIONED set, and it now holds two families rather than one: Gemma
because v4 names it, and Qwen 3.5 because item 24 admits it. Anything outside
that set is a model choice nobody made, and the ladder returns `None` rather
than guessing. Note that v4's own basis for "the local voice is Gemma" is its RAM
budget table naming the model, which `SPEC_MODEL` still cites; the frequently
repeated supporting claim that Addendum §1 forbids a non-Gemma voice does NOT
hold — §1 says the EMBEDDING model is "Not Gemma", which is a different seam and
does not constrain this one.

TIMEOUT: `DEFAULT_TIMEOUT_SECONDS = 120` is a deliberate CONVERSATIONAL ceiling,
not an arbitrary number. 12b tripped it, and that was the timeout working. Use
`tools/compare_local_models.py --timeout` to measure a slow model rather than
raising it here to hide the problem.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import List, Optional, Sequence, Tuple

from daemon.llm_interface import AssembledPrompt, LLMTransportError

DEFAULT_HOST = "http://localhost:11434"

#: The model v4's RAM budget table names: "Gemma 4 E2B QAT".
SPEC_MODEL = "gemma4:e2b-it-qat"      # 4.3 GB, 128K context

#: The configured default local voice — architect ruling, Resolution Log item 24.
#: DIFFERENT from `SPEC_MODEL`, which keeps citing what v4 names. Verified on the
#: target machine: 8.9 GB, 262144-token context, and it reports `vision`, `tools`
#: and `thinking` capabilities.
DEFAULT_MODEL = "qwen3.5:9b-mlx"      # 8.9 GB, 256K context

DEFAULT_TIMEOUT_SECONDS = 120.0       # TODO(build-time): generation timeout
KEEP_RESIDENT = -1                    # Ollama: pin indefinitely
EVICT_NOW = 0                         # Ollama: unload immediately

#: Model families SANCTIONED as the local voice — v4 names Gemma, and Resolution
#: Log item 24 admits Qwen 3.5. A substitution outside this set is a different
#: decision rather than a tag difference, so the ladder returns `None` instead of
#: reaching for it. Order is longest-prefix-first so `qwen3.5` is matched before a
#: future bare `qwen` would swallow it.
_LOCAL_VOICE_FAMILY_PREFIXES = ("qwen3.5", "gemma4", "gemma3", "gemma")


class OllamaLocalTransport:
    """`LocalModelTransport` + `HealthProbe` backed by a local Ollama daemon.

    Holds a host, a model tag, a timeout, and one boolean tracking whether THIS
    adapter has loaded the model. No soul state, no graph handle, no PAD.
    """

    def __init__(
        self,
        *,
        host: str = DEFAULT_HOST,
        model: str = DEFAULT_MODEL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._host = host.rstrip("/")
        self._model = model
        self._timeout = timeout
        self._loaded = False
        self.prompts_served = 0

    # -- read-only observability --------------------------------------------

    @property
    def model(self) -> str:
        return self._model

    @property
    def host(self) -> str:
        return self._host

    # -- LocalModelTransport ------------------------------------------------

    @property
    def is_loaded(self) -> bool:
        """Whether THIS adapter has loaded the model and not unloaded it.

        A local flag, matching the test doubles' semantics, because
        `BackendRouter.select()` reads this on EVERY turn and an HTTP round trip
        per turn to answer it would be a poor trade. With `keep_alive=-1` the
        flag and reality agree; `refresh_residency()` asks the daemon directly
        for callers that want ground truth.
        """
        return self._loaded

    def load(self) -> None:
        """Bring the model up and pin it resident.

        Sends an empty generation with `keep_alive=-1`, which is Ollama's way of
        warming a model without producing output. Raises `LLMTransportError` on
        failure, which `AriaDaemon.startup()` deliberately lets propagate: "a
        daemon that cannot bring up its default voice should fail loudly at
        startup, not silently degrade mid-conversation."
        """
        self._post_generate(prompt="", system=None, keep_alive=KEEP_RESIDENT)
        self._loaded = True

    def unload(self) -> None:
        """Evict the model now (`keep_alive=0`).

        Required by the Protocol. Nothing in this system calls it on the wired
        path: the router never unloads, and `LLMInterface`'s internal
        "unload on cloud restore" path is unreachable once a `BackendRouter` is
        injected, because the Daemon then always supplies a transport.
        """
        try:
            self._post_generate(prompt="", system=None, keep_alive=EVICT_NOW)
        finally:
            # The intent was to stop being resident. Recording that even if the
            # request failed keeps `is_loaded` from claiming residency we did
            # not confirm.
            self._loaded = False

    def generate(self, prompt: AssembledPrompt) -> str:
        """Serve one assembled prompt and return the model's text VERBATIM.

        No judgment, no filtering, no retry, no reformatting — F-9b / LLM
        Interface Req 5. (Formerly cited as "Resolution Log item 15"; that item
        resolves gate OWNERSHIP and does not state the passthrough rule. See
        Resolution Log item 23 — the rule is real, the citation was not.)
        Validation belongs to Soul Filter's Output Gate, which runs on whatever
        this returns.
        """
        system, user = split_prompt(prompt)
        if not user:
            # Structural guard, not judgment. An all-empty request is Ollama's
            # warm-the-model call (see `load()` and `split_prompt`), so sending
            # one here would return "" as a SUCCESS and hand an empty reply to the
            # Output Gate, which has no emptiness check. `split_prompt` already
            # prevents this by moving the instruction into `prompt`; reaching here
            # means Soul Filter assembled a prompt with no text at all, and that
            # is worth an error rather than a silent no-op turn.
            raise LLMTransportError(
                "refusing to send an empty generation request: with no prompt "
                "text this is Ollama's warm-the-model call and would return an "
                "empty reply as a success"
            )
        body = self._post_generate(
            prompt=user, system=system, keep_alive=KEEP_RESIDENT
        )
        text = body.get("response")
        if not isinstance(text, str):
            raise LLMTransportError(
                f"{self._model!r} returned no 'response' string "
                f"(got {type(text).__name__})"
            )
        self._loaded = True
        self.prompts_served += 1
        return text

    # -- HealthProbe --------------------------------------------------------

    def is_healthy(self) -> bool:
        """Is the daemon reachable AND is this model tag installed?

        Cheap: one `/api/tags` read, no generation, no token spent. The router
        caches the answer for `HEALTH_CACHE_TTL_SECONDS`. Never raises — an
        unhealthy backend is an answer, not an error, and `check_health()`
        admits only an explicit True to the healthy set.
        """
        try:
            return self._model in self.installed_models()
        except LLMTransportError:
            return False

    # -- diagnostics --------------------------------------------------------

    def installed_models(self) -> List[str]:
        """Every model tag the daemon has pulled. Raises `LLMTransportError`."""
        body = self._get("/api/tags")
        models = body.get("models")
        if not isinstance(models, list):
            raise LLMTransportError(
                f"unexpected /api/tags response from {self._host}"
            )
        return [m.get("name", "") for m in models if isinstance(m, dict)]

    def refresh_residency(self) -> bool:
        """Ask the daemon which models are actually loaded and sync `is_loaded`.

        Ground truth, at the cost of a round trip. Not called per turn.
        """
        try:
            body = self._get("/api/ps")
        except LLMTransportError:
            return self._loaded
        running = body.get("models")
        names = (
            [m.get("name", "") for m in running if isinstance(m, dict)]
            if isinstance(running, list)
            else []
        )
        self._loaded = self._model in names
        return self._loaded

    # -- provider plumbing --------------------------------------------------

    def _post_generate(
        self, *, prompt: str, system: Optional[str], keep_alive: int
    ) -> dict:
        payload = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "keep_alive": keep_alive,
        }
        if system:
            payload["system"] = system
        return self._request("/api/generate", payload)

    def _get(self, path: str) -> dict:
        return self._request(path, None)

    def _request(self, path: str, payload: Optional[dict]) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            f"{self._host}{path}",
            data=data,
            headers={"Content-Type": "application/json"} if data else {},
            method="POST" if data else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", "replace").strip()
            except Exception:  # pragma: no cover - best-effort detail only
                pass
            raise LLMTransportError(
                f"local model backend returned HTTP {exc.code} for "
                f"{self._model!r}{': ' + detail if detail else ''}"
            ) from exc
        except urllib.error.URLError as exc:
            raise LLMTransportError(
                f"local model backend unreachable at {self._host}: {exc.reason}"
            ) from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise LLMTransportError(
                f"local model backend at {self._host} returned a non-JSON body"
            ) from exc
        except OSError as exc:
            raise LLMTransportError(
                f"local model backend I/O failure at {self._host}: {exc}"
            ) from exc

        if not isinstance(body, dict):
            raise LLMTransportError(
                f"local model backend returned {type(body).__name__}, "
                f"expected an object"
            )
        return body


# ===========================================================================
# Prompt mapping — a pure function, separated so it is testable on its own.
# ===========================================================================

def split_prompt(prompt: AssembledPrompt) -> Tuple[str, str]:
    """Map one `AssembledPrompt` to Ollama's (system, prompt) pair.

    Preserves `as_text()`'s ordering exactly — instruction, then session
    context, then the user's message — while using the system/user role split
    that `LLMInterface`'s docstring names for a local adapter. Drops nothing and
    adds nothing.

    THE EMPTY-USER-TURN CASE, AND WHY IT IS NOT THE OBVIOUS MAPPING
    --------------------------------------------------------------
    There is one turn kind with NO user message: initiative. `AriaDaemon`'s
    `_route_initiative` builds an appraisal from a note and asks Soul Filter to
    respond with nothing from the user, because she is reaching out unprompted —
    so `user_message` and `session_context` are both `""` and the five fields ARE
    the whole prompt.

    The obvious mapping breaks exactly there. `/api/generate` with an empty
    `prompt` is Ollama's WARM-THE-MODEL request — it is what `load()` in this very
    file uses to bring a model up without producing output — so it returns
    `{"response": ""}` successfully. Measured: three identical calls, `''` every
    time. And an empty reply passes Soul Filter's Output Gate untouched, because
    its four checks are honesty / consistency / manipulation / care and an empty
    string violates none of them. So initiative silently produced no speech, and
    with a no-op audio pipeline that was invisible.

    So when there is no user turn, the instruction goes in `prompt` instead of
    `system`. The SAME BYTES still cross, exactly once — only the field carrying
    them changes, and only for this case. Sending it in both fields was rejected:
    that would put the five fields in front of the model twice, which is a change
    to what it sees rather than to how the request is framed.
    """
    parts = []
    if prompt.session_context:
        parts.append(prompt.session_context)
    if prompt.user_message:
        parts.append(prompt.user_message)
    user_portion = "\n\n".join(parts)
    if not user_portion:
        return "", prompt.instruction_text
    return prompt.instruction_text, user_portion


def resolve_model(
    installed: Sequence[str], preferred: str = DEFAULT_MODEL
) -> Tuple[Optional[str], str]:
    """Pick the local-voice model tag. Returns `(tag_or_None, note)`.

    A four-rung ladder, most-preferred first:

    1. `preferred` is installed -> use it, empty note. (The default is
       `DEFAULT_MODEL`; see the module docstring for why it is not `SPEC_MODEL`.)
    2. `SPEC_MODEL` is installed -> use it, with a note that this is v4's own
       model but a smaller one than the default, so weaker Field 5 adherence is
       the thing to watch. Falling back to the SPEC model is the right second
       choice: if we must deviate from the configured default, deviating TOWARD
       the precedence chain is the safe direction.
    3. exactly one other tag from a sanctioned family -> use it, with a note
       naming the substitution. A different variant is a different footprint and
       a different model; that must be visible, not absorbed.
    4. several sanctioned tags, or none -> `(None, note)`. The caller must
       choose. Guessing between two of them picks a memory footprint on the
       operator's behalf, which is not this function's call.

    Deliberately never falls back outside `_LOCAL_VOICE_FAMILY_PREFIXES`: those
    two families are the ones v4 and Resolution Log item 24 sanction, and
    "whatever is installed" is not a model choice.
    """
    tags = [t for t in installed if t]
    if preferred in tags:
        return preferred, ""

    if SPEC_MODEL in tags:
        return SPEC_MODEL, (
            f"local voice: using {SPEC_MODEL!r} because {preferred!r} is not "
            f"installed. That IS the model v4 names (\"Gemma 4 E2B QAT\"), so "
            f"this is spec-faithful — but it is the smaller model, and the "
            f"thing to watch is Field 5 adherence: more Output Gate retries and "
            f"more minimum-safe outputs. `ollama pull {preferred}` for the "
            f"configured default."
        )

    family = [
        t for t in tags
        if any(t.startswith(p) for p in _LOCAL_VOICE_FAMILY_PREFIXES)
    ]
    if len(family) == 1:
        return family[0], (
            f"local voice: using {family[0]!r} — neither the configured default "
            f"{preferred!r} nor v4's own {SPEC_MODEL!r} is installed. This is a "
            f"DIFFERENT variant with a different footprint and different "
            f"instruction adherence. `ollama pull {preferred}`, or pass "
            f"--local-model to choose deliberately."
        )
    if not family:
        return None, (
            f"no model from a sanctioned local-voice family "
            f"({', '.join(_LOCAL_VOICE_FAMILY_PREFIXES)}) is installed, so there "
            f"is no local voice. `ollama pull {preferred}` (the configured "
            f"default) or `ollama pull {SPEC_MODEL}` (v4's model), or pass "
            f"--local-model. Installed: {tags or 'nothing'}."
        )
    return None, (
        f"several sanctioned local-voice models installed ({family}) and neither "
        f"{preferred!r} nor {SPEC_MODEL!r} is among them. Pass --local-model to "
        f"choose; guessing between them would pick a footprint on your behalf."
    )
