"""Concrete `ModelTransport` + `HealthProbe` for the two CLOUD tiers.

WHAT THIS SATISFIES, AND WHAT IT REPLACES
-----------------------------------------
`daemon.llm_interface.ModelTransport` (`generate(prompt) -> str`, raising
`LLMTransportError` and nothing else) plus the OPTIONAL
`daemon.backend_router.HealthProbe` (`is_healthy()`), checked structurally.

It is the additive replacement `adapters/transport_unconfigured.py` describes in
its own docstring: "write a real adapter, satisfy `ModelTransport` plus
`HealthProbe`, and pass it in the same slot. Nothing else changes." Nothing else
changed. `UnconfiguredTransport` is NOT deleted — it stays as the honest default
for an unkeyed tier, and it is still what `main.py` uses when no key is present.

    tier_1  Groq          `groq_from_env()`     reserved for future tools/search
    tier_2  Azure / Kimi  `azure_from_env()`    the reasoning tier, PROPOSED only

ONE CLASS, TWO TIERS — WHY
--------------------------
Both providers speak the OpenAI `chat/completions` shape, so the difference
between them is a URL, an auth header name and a model/deployment name — not a
protocol. Two classes would be two copies of the same request plumbing with two
places for a mapping bug to hide.

  * Groq is OpenAI-compatible at `https://api.groq.com/openai/v1`, Bearer auth.
    See Groq's own OpenAI-compatibility page: https://console.groq.com/docs/openai
  * Azure AI Foundry serves every model — OpenAI's and other providers' alike —
    on the Azure OpenAI path
    `https://<resource>.services.ai.azure.com/openai/deployments/<deployment>/chat/completions?api-version=<ver>`,
    with the key in an `api-key` header. Reference:
    https://learn.microsoft.com/en-us/azure/ai-foundry/foundry-models/how-to/use-chat-completions
    (Both descriptions rephrased for compliance with licensing restrictions.)

So the class takes a FULLY-BUILT chat URL and an auth header, and the two
factories know the provider-shaped details. The class itself knows no provider.

THE NETWORK POSTURE THIS CHANGES — SAY IT PLAINLY
-------------------------------------------------
Until this file existed, `main.py`'s only outbound traffic was to a localhost
Ollama daemon and NOTHING left the machine. A keyed tier changes that: on a turn
this transport serves, the assembled prompt — the five natural-language fields
plus the ephemeral session transcript plus the user's current message — is sent
to a third party.

What still does NOT cross is unchanged and is not this adapter's doing; it is
structural. This module receives an `AssembledPrompt` and has no graph, PAD,
needs, appraisal or state handle to add anything to it, so no PAD value, no graph
content, no `relational_stage` label, no need state and no appraisal output can
reach a provider through here (Addendum §9).

The opt-in is therefore deliberately explicit and deliberately loud: no key, no
adapter, and `main.py` prints the posture change when one is configured.

WHAT IS SENT IN THE REQUEST BODY — AND WHAT IS DELIBERATELY ABSENT
-----------------------------------------------------------------
`model`, `messages`, `stream: false`. That is all.

**No `temperature`, no `top_p`, no `max_tokens`, no penalties.** Not an
oversight, and not laziness: those parameters shape register — how warm, how
terse, how hedged she sounds — and register is Field 2's job and the Output
Gate's to verify. An adapter choosing a temperature would be the transport
deciding how she comes across, which is the same class of mistake as the adapter
stripping a stage direction (rejected because it is the transport judging
content; F-9b / Req 5 put verbatim passthrough at this layer — see Resolution
Log item 23 on why this is not "item 15"). It would also be an invented number
with a behavioural meaning. If a generation parameter is ever wanted, it is an
architect decision about her voice, not an adapter default.

PROMPT MAPPING — IDENTICAL TO THE LOCAL TRANSPORT, BY IMPORT
------------------------------------------------------------
`split_prompt` is imported from `adapters.transport_ollama` rather than copied.
That is the point: Resolution Log item 14 / F-9a lock the property that cloud and
Gemma receive the BYTE-IDENTICAL prompt, and `LLMInterface` guarantees its half
by assembling once. Two copies of the (system, user) mapping is precisely how the
other half of that property rots — one gets a fix, the other does not, and the
two tiers quietly diverge. So:

    system role  <- instruction_text                        (five fields, or emergency)
    user role    <- session_context + "\\n\\n" + user_message  (as_text's ordering)

`tests/test_transport_cloud.py` asserts the two transports send the same text for
the same prompt, so the coupling is checked rather than trusted.

TOKEN COUNTS — THE SAME SIDE-CHANNEL THE LOCAL TRANSPORT USES
-------------------------------------------------------------
An OpenAI-compatible response carries `usage.prompt_tokens` and
`usage.completion_tokens` — the provider's exact counts, the same ones it bills
on. They are recorded and read through `last_turn_metadata()`, returning the SAME
`TurnMetadata` the local transport returns, imported from `transport_ollama` for
the same reason `split_prompt` is: one shape, one definition, so the Daemon reads
a served turn the same way whichever tier served it.

`generate()` still returns `str`; `ModelTransport.generate` is unchanged.

**No generation duration crosses, because these APIs do not report one.**
`duration_ns` stays None on this transport, so the speed-degradation signal in
`SessionBuffer.fullness_state()` simply never fires for a cloud turn. That is the
honest outcome: a round trip over a network measures the network as much as the
model, so timing it here and calling it generation speed would be inventing a
measurement. Absent when it cannot be measured, not approximated.

REASONING / THINKING FIELDS ARE NOT MERGED IN
---------------------------------------------
Some models on both providers return a separate reasoning field alongside
`message.content`. This adapter returns `content` VERBATIM and never concatenates
a reasoning field into it — that text would go straight to TTS and be spoken. It
does not STRIP anything either; stripping is judgment and belongs to no adapter.
It records `last_reasoning_field_present` as an operator-visible fact, which is a
diagnostic counter and not a decision.

That flag is deliberately a flag: the tracker's open `needs-ruling` row says the
Output Validation Gate has no FORMAT check and Addendum §4 fixes the gate at four
comparisons, so a reasoning block reaching spoken output is a live architectural
question. This adapter surfaces it and resolves nothing.

HEALTH — LAYERED, AND NOTHING OPTIMISTIC
----------------------------------------
FLAG B established that "no answer" is not "yes". This answers in four steps,
cheapest first, and only an explicit yes is a yes:

1. **No API key -> False.** No request is made. Same reasoning as
   `UnconfiguredTransport`: "not configured" is a definite answer.
2. **A recorded `LLMTransportError` inside the cooldown -> False.** No request is
   made. This is the tracker's own stated minimum for this row: "back
   `is_healthy()` with the adapter's own last `LLMTransportError` state."
3. **A models endpoint is configured -> probe it.** One cheap GET, no generation,
   no completion tokens spent — the same trade `OllamaLocalTransport.is_healthy()`
   makes with `/api/tags`. Where the listing is authoritative about model names
   (Groq) a missing tag reads as unhealthy; where it is not (an Azure
   deployment-scoped URL names no model in a list) reachability is the answer,
   and the factory simply configures no models URL.
4. **Otherwise -> the step-2 state.** Configured, not known to have failed.

THE CONSEQUENCE OF STEP 4, STATED SO IT IS NOT A SURPRISE. A keyed tier with no
cheap probe (the Azure shape) reads healthy BEFORE its first request, so a
misconfigured endpoint costs exactly one failed turn: `LLMInterface`'s
caller-supplied-transport path calls the chosen transport directly and does not
fall back, so the turn surfaces the `LLMTransportError` and `main.py` reports it.
The failure is then recorded, the tier reads unhealthy for the cooldown, and
routing returns to Gemma on its own.

That is not avoidable by being stricter, and being stricter would be worse:
"keyed but never tried -> unhealthy" is a deadlock, because the router only asks
about transports it might select, so a tier that must succeed once to become
selectable can never become selectable. One visible failed turn, self-corrected,
beats a tier that is silently unreachable forever. For tier 2 the cost is bounded
further by the proposal flow — it is only ever reached after the user says yes.

THE COOLDOWN INTRODUCES NO NUMBER. It reuses
`daemon.backend_router.HEALTH_CACHE_TTL_SECONDS`, which is already the cadence at
which the router re-asks. Picking a second, different interval here would be an
invented number with no reason to differ from the one that already governs how
often the question is posed.

Never raises: `check_health()` admits only an explicit True to the healthy set,
and an unhealthy backend is an answer rather than an error.

SECRETS
-------
The key is held in memory, sent in one header, and never printed. `__repr__` and
every error message carry the tier name, the URL and the model — never the key.
`describe()` exists for startup reporting and reports only that a key is present.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Sequence

from daemon.backend_router import HEALTH_CACHE_TTL_SECONDS
from daemon.llm_interface import AssembledPrompt, LLMTransportError

from adapters.transport_ollama import TurnMetadata, reported_count, split_prompt

# ---------------------------------------------------------------------------
# Groq (tier 1). OpenAI-compatible; Bearer auth.
# ---------------------------------------------------------------------------
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_API_KEY_ENV = "GROQ_API_KEY"
GROQ_MODEL_ENV = "ARIA_GROQ_MODEL"
GROQ_BASE_URL_ENV = "ARIA_GROQ_BASE_URL"

# ---------------------------------------------------------------------------
# Azure AI Foundry (tier 2 — the reasoning tier; "Azure-Kimi" in the tracker).
# Every model is served on the Azure OpenAI deployment path, so the deployment
# name — not a model name — identifies what answers.
# ---------------------------------------------------------------------------
AZURE_ENDPOINT_ENV = "AZURE_AI_ENDPOINT"
AZURE_API_KEY_ENV = "AZURE_AI_API_KEY"
AZURE_DEPLOYMENT_ENV = "AZURE_AI_DEPLOYMENT"
AZURE_API_VERSION_ENV = "AZURE_AI_API_VERSION"
AZURE_CHAT_URL_ENV = "ARIA_AZURE_CHAT_URL"

#: Azure requires an explicit api-version on every request and there is no
#: sensible default to invent — a wrong one fails the call outright. This is the
#: version the Foundry documentation uses for the unified chat/completions path
#: at the time of writing; override it with AZURE_AI_API_VERSION.
AZURE_DEFAULT_API_VERSION = "2024-10-21"

#: Transport plumbing only, same category as `transport_ollama`'s generation
#: timeout and `embedding_local`'s: no soul meaning, tune freely.
DEFAULT_TIMEOUT_SECONDS = 60.0        # TODO(build-time): cloud request timeout

#: Keys a provider may use for a separate reasoning/thinking surface. Used ONLY
#: to set an observability flag — never to strip, merge, or edit output.
_REASONING_KEYS = ("reasoning", "reasoning_content", "thinking")


def _now() -> datetime:
    """Aware-UTC clock, matching the convention every dated module uses."""
    return datetime.now(timezone.utc)


class CloudTransportError(LLMTransportError):
    """A cloud tier failed. A subclass so a caller CAN tell cloud failure from
    local failure, and so that every `except LLMTransportError` already written
    in the soul layer and in `main.py` keeps working unchanged — which is what
    makes this adapter additive rather than a change."""


class OpenAICompatibleTransport:
    """`ModelTransport` + `HealthProbe` for any OpenAI-compatible chat endpoint.

    Holds a tier name, a fully-built chat URL, a model/deployment name, an API
    key, header details, a timeout, an optional models URL and the last-failure
    record. No soul state, no graph handle, no PAD — there is no constructor
    parameter through which any could arrive.
    """

    def __init__(
        self,
        *,
        tier_name: str,
        chat_url: str,
        model: str,
        api_key: Optional[str],
        auth_header: str = "Authorization",
        auth_prefix: str = "Bearer ",
        models_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        failure_cooldown_seconds: float = HEALTH_CACHE_TTL_SECONDS,
        clock: Callable[[], datetime] = _now,
    ) -> None:
        self._tier_name = tier_name
        self._chat_url = chat_url
        self._model = model
        self._api_key = api_key or None
        self._auth_header = auth_header
        self._auth_prefix = auth_prefix
        self._models_url = models_url
        self._timeout = timeout
        self._failure_cooldown = timedelta(seconds=failure_cooldown_seconds)
        self._clock = clock

        # --- observability only. Never fed back into any meaning. ---
        self.prompts_served = 0
        self.generate_attempts = 0
        self.last_reasoning_field_present = False
        self._last_failure_at: Optional[datetime] = None
        self._last_failure: Optional[str] = None

        # --- last-served-turn measurements (the SessionBuffer side-channel).
        # No `duration_ns` counterpart: these APIs report no generation time,
        # and timing the round trip would measure the network. ---------------
        self._last_prompt_tokens: Optional[int] = None
        self._last_gen_tokens: Optional[int] = None
        self._has_served_a_turn = False

    # -- read-only observability -------------------------------------------

    @property
    def tier_name(self) -> str:
        return self._tier_name

    @property
    def model(self) -> str:
        return self._model

    @property
    def chat_url(self) -> str:
        return self._chat_url

    @property
    def configured(self) -> bool:
        """Is a key present at all? The one thing worth asking before a request."""
        return self._api_key is not None

    @property
    def last_failure(self) -> Optional[str]:
        """The last transport failure message, or None. Never contains the key."""
        return self._last_failure

    def describe(self) -> str:
        """A startup-report line. Reports that a key is PRESENT, never the key."""
        return (
            f"{self._tier_name}: {self._model} at {self._chat_url} "
            f"(key {'present' if self.configured else 'MISSING'})"
        )

    def __repr__(self) -> str:  # pragma: no cover - diagnostic only
        return (
            f"{type(self).__name__}(tier_name={self._tier_name!r}, "
            f"model={self._model!r}, chat_url={self._chat_url!r}, "
            f"key={'set' if self.configured else 'unset'})"
        )

    # -- ModelTransport -----------------------------------------------------

    def generate(self, prompt: AssembledPrompt) -> str:
        """Serve one assembled prompt and return the model's text VERBATIM.

        No judgment, no filtering, no retry, no reformatting, no reasoning field
        merged in (F-9b / LLM Interface Req 5; see Resolution Log item 23).
        Validation is Soul Filter's Output Gate, which runs on whatever this
        returns.

        Raises `CloudTransportError` (a `LLMTransportError`) and nothing else —
        that single exception is the only signal the Protocol defines, so an
        unkeyed tier, an HTTP error, a timeout and an unparseable body all
        surface the same way.
        """
        self.generate_attempts += 1
        if not self.configured:
            raise self._fail(
                f"no API key configured (set the environment variable for "
                f"{self._tier_name})"
            )

        system, user = split_prompt(prompt)
        # `split_prompt` returns ("", instruction) for the one turn kind with no
        # user message — initiative, where the five fields are the whole prompt
        # (see its docstring for the Ollama warm-request bug that revealed this).
        # Empty message CONTENT is not sent: several providers reject it, and one
        # that accepts it is being asked to answer nothing. Omitting the empty role
        # sends the same bytes with one fewer meaningless field.
        messages = [
            {"role": role, "content": content}
            for role, content in (("system", system), ("user", user))
            if content
        ]
        if not messages:
            raise self._fail(
                "refusing to send a request with no prompt text at all"
            )
        payload: Dict[str, object] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
        }
        body = self._request(self._chat_url, payload)
        text = self._extract_content(body)
        # Recorded AFTER the content check, matching the local transport: a
        # response that was not a valid generation leaves no counts describing
        # it as one.
        self._record_usage(body)
        self._last_failure = None
        self._last_failure_at = None
        self.prompts_served += 1
        return text

    def _record_usage(self, body: dict) -> None:
        """Read `usage.prompt_tokens` / `usage.completion_tokens` if present.

        Assigns None when the field is absent or malformed, so a provider that
        stops reporting usage stops being quoted — the previous turn's counts
        described a different prompt.
        """
        usage = body.get("usage")
        usage = usage if isinstance(usage, dict) else {}
        self._last_prompt_tokens = reported_count(usage.get("prompt_tokens"))
        self._last_gen_tokens = reported_count(usage.get("completion_tokens"))
        self._has_served_a_turn = True

    def last_turn_metadata(self) -> Optional[TurnMetadata]:
        """The provider's own counts for the last turn `generate()` served.

        The SAME `TurnMetadata` the local transport returns, so the Daemon reads
        a served turn identically whichever tier served it. `duration_ns` is
        always None here — see the module docstring.

        None when there is nothing to report: no turn served yet, or a response
        with no `usage` field. None means "ask the estimate", which is what
        `SessionBuffer.fullness_state()` does with it; a `TurnMetadata` of Nones
        would be indistinguishable from a measurement at the call site.
        """
        if not self._has_served_a_turn:
            return None
        metadata = TurnMetadata(
            prompt_tokens=self._last_prompt_tokens,
            gen_tokens=self._last_gen_tokens,
            duration_ns=None,
        )
        return None if metadata.is_empty else metadata

    def _extract_content(self, body: dict) -> str:
        """Pull `choices[0].message.content` and return it untouched.

        Mirrors `OllamaLocalTransport.generate`'s shape check exactly: a missing
        or non-string content field is a mechanical failure, not a candidate, so
        it raises rather than being smoothed into an empty reply. An EMPTY string
        that the provider genuinely returned is passed through — that is the
        provider's answer and the Output Gate's problem, not this layer's.
        """
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise self._fail(
                f"{self._model!r} returned no choices "
                f"(keys: {sorted(body)[:6]})"
            )
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message")
        message = message if isinstance(message, dict) else {}

        # Record, do not act. See the module docstring: merging this in would
        # have it spoken; stripping anything would be judgment at the transport.
        self.last_reasoning_field_present = any(
            isinstance(message.get(key), str) and message.get(key)
            for key in _REASONING_KEYS
        )

        text = message.get("content")
        if not isinstance(text, str):
            finish = first.get("finish_reason")
            raise self._fail(
                f"{self._model!r} returned no message content "
                f"(got {type(text).__name__}"
                f"{f', finish_reason={finish!r}' if finish else ''})"
            )
        return text

    # -- HealthProbe --------------------------------------------------------

    def is_healthy(self) -> bool:
        """Four steps, cheapest first; only an explicit yes is a yes.

        See the module docstring for the full reasoning. Never raises.
        """
        # 1. Unkeyed tiers are explicitly unhealthy, with no request made.
        if not self.configured:
            return False

        # 2. A recent recorded failure answers without spending a request.
        if self._in_failure_cooldown():
            return False

        # 3. A cheap listing probe, where one is configured and meaningful.
        if self._models_url:
            try:
                available = self.available_models()
            except LLMTransportError:
                return False
            # An empty list means the endpoint answered but told us nothing
            # about names; reachability is then the honest answer.
            if available and self._model not in available:
                return False
            return True

        # 4. Configured, and not known to have failed.
        return True

    def _in_failure_cooldown(self) -> bool:
        if self._last_failure_at is None:
            return False
        return (self._clock() - self._last_failure_at) < self._failure_cooldown

    def available_models(self) -> List[str]:
        """Model ids the endpoint lists. Raises `CloudTransportError`.

        Returns `[]` when the endpoint answers with a shape that carries no ids —
        reachable, but silent about names. `is_healthy()` reads that as
        reachability rather than as a missing model, because inferring "your
        model is gone" from "this endpoint does not list models" would be wrong
        for exactly the deployment-scoped Azure case.
        """
        if not self._models_url:
            return []
        body = self._request(self._models_url, None)
        data = body.get("data")
        if not isinstance(data, list):
            return []
        return [
            entry["id"] for entry in data
            if isinstance(entry, dict) and isinstance(entry.get("id"), str)
        ]

    # -- provider plumbing --------------------------------------------------

    def _headers(self, *, json_body: bool) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self._api_key:
            headers[self._auth_header] = f"{self._auth_prefix}{self._api_key}"
        if json_body:
            headers["Content-Type"] = "application/json"
        return headers

    def _request(self, url: str, payload: Optional[dict]) -> dict:
        """One request. Every failure mode becomes `CloudTransportError`, and
        every message names the tier, the model and the URL — never the key."""
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            url,
            data=data,
            headers=self._headers(json_body=data is not None),
            method="POST" if data else "GET",
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            raise self._fail(
                f"HTTP {exc.code} from {url}"
                f"{': ' + self._read_detail(exc) if self._read_detail(exc) else ''}"
            ) from exc
        except urllib.error.URLError as exc:
            raise self._fail(f"unreachable at {url}: {exc.reason}") from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise self._fail(f"non-JSON body from {url}") from exc
        except OSError as exc:
            raise self._fail(f"I/O failure talking to {url}: {exc}") from exc

        if not isinstance(body, dict):
            raise self._fail(
                f"{url} returned {type(body).__name__}, expected an object"
            )
        return body

    @staticmethod
    def _read_detail(exc: urllib.error.HTTPError) -> str:
        """Best-effort provider error text. An HTTPError body reads once, so a
        caller must not call this twice expecting the same answer — it is called
        exactly twice in one f-string above, which is why it tolerates an empty
        second read rather than assuming content."""
        try:
            return exc.read().decode("utf-8", "replace").strip()[:400]
        except Exception:  # pragma: no cover - best-effort detail only
            return ""

    def _fail(self, detail: str) -> CloudTransportError:
        """Record the failure (so `is_healthy()` can answer without a request)
        and build the error. Recording here rather than at each raise site is
        what keeps the two in step."""
        message = f"cloud tier {self._tier_name!r} failed: {detail}"
        self._last_failure = message
        self._last_failure_at = self._clock()
        return CloudTransportError(message)


# ===========================================================================
# Factories. These know the provider-shaped details; the class above does not.
# Each returns None when no key is configured, so a caller can fall back to
# `UnconfiguredTransport` rather than holding a transport that cannot work.
# ===========================================================================

def groq_from_env(
    *,
    model: Optional[str] = None,
    env: Optional[Dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Optional[OpenAICompatibleTransport]:
    """Build the tier-1 Groq transport, or None if `GROQ_API_KEY` is unset.

    No default model is invented: Groq's catalogue changes and hardcoding a tag
    here would silently pick a model on the operator's behalf — the same mistake
    `resolve_model` refuses to make for the local voice. `ARIA_GROQ_MODEL` (or
    the `model` argument) must name it, and without one this returns None too.
    """
    env = os.environ if env is None else env
    key = (env.get(GROQ_API_KEY_ENV) or "").strip()
    if not key:
        return None
    tag = (model or env.get(GROQ_MODEL_ENV) or "").strip()
    if not tag:
        return None
    base = (env.get(GROQ_BASE_URL_ENV) or GROQ_BASE_URL).rstrip("/")
    return OpenAICompatibleTransport(
        tier_name="tier_1 (groq)",
        chat_url=f"{base}/chat/completions",
        models_url=f"{base}/models",
        model=tag,
        api_key=key,
        auth_header="Authorization",
        auth_prefix="Bearer ",
        timeout=timeout,
    )


def azure_from_env(
    *,
    env: Optional[Dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Optional[OpenAICompatibleTransport]:
    """Build the tier-2 Azure transport (the reasoning tier), or None.

    Needs `AZURE_AI_API_KEY` plus either a full `ARIA_AZURE_CHAT_URL` or the
    pair (`AZURE_AI_ENDPOINT`, `AZURE_AI_DEPLOYMENT`). Returns None if any of
    that is missing, because a half-configured cloud tier should read as absent
    rather than as broken.

    NO MODELS URL IS CONFIGURED, deliberately. The deployment-scoped path names a
    deployment, not a model, so a models listing would not answer "is my
    deployment there" — and treating a silent listing as "model missing" would
    mark a working tier unhealthy. Health therefore rests on the key plus the
    last-failure record, which is exactly the minimum the tracker's
    `needs-adapter` row names.
    """
    env = os.environ if env is None else env
    key = (env.get(AZURE_API_KEY_ENV) or "").strip()
    if not key:
        return None

    deployment = (env.get(AZURE_DEPLOYMENT_ENV) or "").strip()
    chat_url = (env.get(AZURE_CHAT_URL_ENV) or "").strip()
    if not chat_url:
        endpoint = (env.get(AZURE_ENDPOINT_ENV) or "").strip().rstrip("/")
        if not endpoint or not deployment:
            return None
        version = (
            env.get(AZURE_API_VERSION_ENV) or AZURE_DEFAULT_API_VERSION
        ).strip()
        chat_url = (
            f"{endpoint}/openai/deployments/{deployment}"
            f"/chat/completions?api-version={version}"
        )

    return OpenAICompatibleTransport(
        tier_name="tier_2 (azure/kimi)",
        chat_url=chat_url,
        models_url=None,
        model=deployment or "azure-deployment",
        api_key=key,
        # Azure's own convention for a resource key. A caller using an AAD
        # bearer token can construct the class directly with Authorization.
        auth_header="api-key",
        auth_prefix="",
        timeout=timeout,
    )


def env_summary(env: Optional[Dict[str, str]] = None) -> Sequence[str]:
    """Which cloud environment variables are set. Reports PRESENCE, never values —
    used by `main.py`'s startup report so an operator can see why a tier is
    absent without any risk of a key reaching a terminal or a log."""
    env = os.environ if env is None else env
    names = (
        GROQ_API_KEY_ENV, GROQ_MODEL_ENV, GROQ_BASE_URL_ENV,
        AZURE_API_KEY_ENV, AZURE_ENDPOINT_ENV, AZURE_DEPLOYMENT_ENV,
        AZURE_API_VERSION_ENV, AZURE_CHAT_URL_ENV,
    )
    return [f"{name}={'set' if (env.get(name) or '').strip() else 'unset'}"
            for name in names]
