"""Cloud transport adapter — the boundary, the mapping, and the health answer.

Three tests here are load-bearing and the rest are plumbing.

1. `test_cloud_and_local_send_the_same_text` — Resolution Log item 14 / F-9a lock
   the property that cloud and Gemma receive a BYTE-IDENTICAL prompt.
   `LLMInterface` guarantees its half by assembling once; the transports have to
   hold the other half. This asserts the two mappings agree by comparing what the
   two adapters actually put on the wire, so the shared `split_prompt` import
   cannot be quietly replaced with a second copy that drifts.

2. `test_request_body_carries_no_generation_parameters` — an adapter that set a
   temperature would be the transport deciding her register, which is Field 2's
   job and the Output Gate's to verify. Asserted as an ABSENCE, because that is
   the kind of thing someone adds later meaning well.

3. `test_reasoning_field_is_never_merged_into_the_reply` — a reasoning block
   concatenated into `content` would be spoken by TTS. The tracker's open
   `needs-ruling` row says the Output Gate structurally cannot catch a format
   defect, so this transport must not create one. It also must not STRIP
   anything (Resolution Log item 15), and that direction is asserted too.

Everything is hermetic: `urlopen` is stubbed, no key is ever needed, and no
request leaves the machine.
"""

from __future__ import annotations

import json
import urllib.error
from datetime import datetime, timedelta, timezone

import pytest

from daemon.backend_router import BackendRouter, HealthProbe
from daemon.llm_interface import (
    AssembledPrompt,
    LLMInterface,
    LLMTransportError,
    ModelTransport,
)

from adapters.transport_cloud import (
    AZURE_API_KEY_ENV,
    AZURE_DEPLOYMENT_ENV,
    AZURE_ENDPOINT_ENV,
    GROQ_API_KEY_ENV,
    GROQ_BASE_URL,
    GROQ_MODEL_ENV,
    CloudTransportError,
    OpenAICompatibleTransport,
    azure_from_env,
    env_summary,
    groq_from_env,
)
from adapters.transport_ollama import OllamaLocalTransport, TurnMetadata
from adapters.transport_unconfigured import UnconfiguredTransport

FIVE_FIELD_TEXT = (
    "Persona Anchor: you are Aria.\n"
    "Behavioral Register: warm and settled, unhurried.\n"
    "Relational Register: speak as someone who knows this person well.\n"
    "This Moment: what was just shared carries weight — engage it fully.\n"
    "Constraints: do not problem-solve, do not minimize, do not deflect."
)
SESSION_TEXT = "Recent turns:\nuser: hi\naria: hey\n\nOld topics: deploys"

PROMPT = AssembledPrompt(
    instruction_text=FIVE_FIELD_TEXT,
    user_message="I have not told anybody this before",
    kind="five_field",
    session_context=SESSION_TEXT,
)

FAKE_KEY = "sk-not-a-real-key-0000"


# ===========================================================================
# HTTP stubbing
# ===========================================================================

class _StubResponse:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self):
        return self._payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _stub(monkeypatch, handler):
    """Replace urlopen. `handler(method, url, body) -> response`.

    NOTE it patches ONE attribute for the whole process: `urllib.request` is the
    same module object imported by every adapter, so this stub is in force for the
    Ollama transport too. That is why the identical-prompt test dispatches on URL
    rather than installing a second stub.
    """
    calls = []

    def fake_urlopen(request, timeout=None):
        body = json.loads(request.data.decode("utf-8")) if request.data else None
        calls.append({
            "method": request.get_method(),
            "url": request.full_url,
            "body": body,
            "headers": dict(request.headers),
            "timeout": timeout,
        })
        return handler(request.get_method(), request.full_url, body)

    monkeypatch.setattr(
        "adapters.transport_cloud.urllib.request.urlopen", fake_urlopen
    )
    return calls


def _chat_reply(text="a real reply", extra_message=None, models=("kimi-k2",)):
    def handler(_method, url, _body):
        if url.rstrip("/").endswith("/models"):
            payload = {"data": [{"id": m} for m in models]}
        else:
            message = {"role": "assistant", "content": text}
            if extra_message:
                message.update(extra_message)
            payload = {"choices": [{"index": 0, "message": message,
                                    "finish_reason": "stop"}]}
        return _StubResponse(json.dumps(payload).encode("utf-8"))
    return handler


def _transport(**overrides) -> OpenAICompatibleTransport:
    kwargs = dict(
        tier_name="tier_1 (groq)",
        chat_url=f"{GROQ_BASE_URL}/chat/completions",
        models_url=f"{GROQ_BASE_URL}/models",
        model="kimi-k2",
        api_key=FAKE_KEY,
    )
    kwargs.update(overrides)
    return OpenAICompatibleTransport(**kwargs)


# ===========================================================================
# Structural conformance — the whole claim of "purely additive".
# ===========================================================================

def test_satisfies_model_transport_and_health_probe():
    transport = _transport()
    assert isinstance(transport, ModelTransport)
    assert isinstance(transport, HealthProbe)


def test_drops_into_the_same_constructor_slots_unchanged():
    """"Pass it in the same slot. Nothing else changes." Asserted, not assumed:
    both consumers that REQUIRE cloud slots accept it with no modification."""
    cloud = _transport()
    local = OllamaLocalTransport()
    interface = LLMInterface(cloud_transport=cloud, local_transport=local)
    router = BackendRouter(
        gemma_transport=local, groq_transport=cloud, azure_transport=cloud
    )
    assert isinstance(interface, LLMInterface)
    assert isinstance(router, BackendRouter)


def test_error_is_a_LLMTransportError_so_existing_handlers_keep_working():
    """A subclass, so `except LLMTransportError` everywhere in the soul layer and
    in main.py still catches it — that is what makes this additive."""
    assert issubclass(CloudTransportError, LLMTransportError)


# ===========================================================================
# 1. The identical-prompt property (ResLog item 14 / F-9a).
# ===========================================================================

def test_cloud_and_local_send_the_same_text(monkeypatch):
    # ONE stub for both adapters. `urllib.request` is the same module object in
    # both, so patching "adapters.transport_ollama.urllib.request.urlopen" and
    # "adapters.transport_cloud.urllib.request.urlopen" sets the SAME attribute —
    # the second patch silently replaces the first. So the handler dispatches on
    # URL instead, and the calls are separated afterwards.
    def handler(_method, url, _body):
        if "/api/generate" in url:
            payload = {"response": "ok"}
        else:
            payload = {"choices": [{"message": {"content": "ok"}}]}
        return _StubResponse(json.dumps(payload).encode("utf-8"))

    calls = _stub(monkeypatch, handler)

    _transport().generate(PROMPT)
    OllamaLocalTransport().generate(PROMPT)

    cloud = next(c for c in calls if "groq.com" in c["url"])
    local = next(c for c in calls if "/api/generate" in c["url"])

    messages = cloud["body"]["messages"]
    cloud_system = next(m["content"] for m in messages if m["role"] == "system")
    cloud_user = next(m["content"] for m in messages if m["role"] == "user")

    assert cloud_system == local["body"]["system"]
    assert cloud_user == local["body"]["prompt"]


def test_prompt_mapping_drops_nothing(monkeypatch):
    """Every character of every surface reaches the request. A mapping that lost
    `session_context` would be an adapter changing what crosses the §9 boundary,
    from the layer with the least authority to decide that."""
    calls = _stub(monkeypatch, _chat_reply())
    _transport().generate(PROMPT)

    messages = calls[0]["body"]["messages"]
    system = next(m["content"] for m in messages if m["role"] == "system")
    user = next(m["content"] for m in messages if m["role"] == "user")

    assert system == FIVE_FIELD_TEXT
    assert SESSION_TEXT in user
    assert PROMPT.user_message in user
    # Ordering matches as_text(): session context precedes the current message.
    assert user.index(SESSION_TEXT) < user.index(PROMPT.user_message)


def test_empty_session_context_sends_only_the_user_message(monkeypatch):
    calls = _stub(monkeypatch, _chat_reply())
    _transport().generate(
        AssembledPrompt(instruction_text="i", user_message="u", kind="five_field")
    )
    user = next(
        m["content"] for m in calls[0]["body"]["messages"] if m["role"] == "user"
    )
    assert user == "u"


# ===========================================================================
# 2. No generation parameters — asserted as an absence.
# ===========================================================================

def test_request_body_carries_no_generation_parameters(monkeypatch):
    calls = _stub(monkeypatch, _chat_reply())
    _transport().generate(PROMPT)
    body = calls[0]["body"]
    assert set(body) == {"model", "messages", "stream"}
    for forbidden in (
        "temperature", "top_p", "top_k", "max_tokens", "max_completion_tokens",
        "frequency_penalty", "presence_penalty", "stop", "seed",
    ):
        assert forbidden not in body


def test_reply_is_returned_verbatim(monkeypatch):
    """Resolution Log item 15: verbatim passthrough, no judgment at this layer.
    Deliberately probed with text the Output Gate would reject and with a stage
    direction — the transport is not the place either gets handled."""
    ugly = (
        "(Aria listens, her presence steady.)\n\n"
        "## Heading\n- bullet\n\nYou are ABSOLUTELY going to succeed!!!  "
    )
    _stub(monkeypatch, _chat_reply(ugly))
    assert _transport().generate(PROMPT) == ugly


# ===========================================================================
# 3. Reasoning fields — recorded, never merged, never stripped.
# ===========================================================================

@pytest.mark.parametrize("key", ["reasoning", "reasoning_content", "thinking"])
def test_reasoning_field_is_never_merged_into_the_reply(monkeypatch, key):
    _stub(monkeypatch, _chat_reply(
        "the spoken reply", extra_message={key: "let me think step by step..."}
    ))
    transport = _transport()
    text = transport.generate(PROMPT)
    assert text == "the spoken reply"
    assert "step by step" not in text
    # Recorded as an operator-visible fact, which is a diagnostic and not a
    # decision. The FORMAT-guard question it belongs to is a needs-ruling row.
    assert transport.last_reasoning_field_present is True


def test_reasoning_flag_is_false_when_the_provider_sends_none(monkeypatch):
    _stub(monkeypatch, _chat_reply("plain"))
    transport = _transport()
    transport.generate(PROMPT)
    assert transport.last_reasoning_field_present is False


def test_content_inside_the_reply_is_not_scrubbed(monkeypatch):
    """The inverse direction of the same rule: if a model puts a think tag in
    CONTENT, the adapter passes it through. Stripping would be judgment, and the
    tracker's format-guard row is explicit that the fix does not live here."""
    leaked = "<think>hmm</think>the reply"
    _stub(monkeypatch, _chat_reply(leaked))
    assert _transport().generate(PROMPT) == leaked


# ===========================================================================
# Failure contract — one exception type, and it records itself.
# ===========================================================================

def test_unkeyed_transport_never_makes_a_request(monkeypatch):
    calls = _stub(monkeypatch, _chat_reply())
    transport = _transport(api_key=None)
    with pytest.raises(LLMTransportError):
        transport.generate(PROMPT)
    assert calls == []
    assert transport.is_healthy() is False


def test_http_error_becomes_a_cloud_transport_error(monkeypatch):
    def handler(_method, url, _body):
        # Built INSIDE the handler on purpose. A constructed HTTPError passed as
        # a pytest parametrize value makes id generation reach into a tempfile
        # wrapper and the whole FILE fails at collection.
        raise urllib.error.HTTPError(url, 401, "Unauthorized", {}, None)

    _stub(monkeypatch, handler)
    with pytest.raises(CloudTransportError, match="401"):
        _transport().generate(PROMPT)


def test_url_error_becomes_a_cloud_transport_error(monkeypatch):
    def handler(*_args):
        raise urllib.error.URLError("nodename nor servname provided")

    _stub(monkeypatch, handler)
    with pytest.raises(CloudTransportError, match="unreachable"):
        _transport().generate(PROMPT)


def test_non_json_body_becomes_a_cloud_transport_error(monkeypatch):
    _stub(monkeypatch, lambda *_: _StubResponse(b"<html>502</html>"))
    with pytest.raises(CloudTransportError, match="non-JSON"):
        _transport().generate(PROMPT)


def test_missing_content_raises_rather_than_returning_empty(monkeypatch):
    """Mirrors OllamaLocalTransport exactly: a missing content field is a
    mechanical failure, not a candidate, so it must not be smoothed into "" — an
    empty reply would reach the Output Gate as if the model had answered."""
    def handler(_method, _url, _body):
        payload = {"choices": [{"message": {"role": "assistant"},
                                "finish_reason": "content_filter"}]}
        return _StubResponse(json.dumps(payload).encode("utf-8"))

    _stub(monkeypatch, handler)
    with pytest.raises(CloudTransportError, match="content_filter"):
        _transport().generate(PROMPT)


def test_no_choices_raises(monkeypatch):
    _stub(monkeypatch, lambda *_: _StubResponse(json.dumps({"choices": []}).encode()))
    with pytest.raises(CloudTransportError, match="no choices"):
        _transport().generate(PROMPT)


def test_genuinely_empty_string_is_passed_through(monkeypatch):
    """A provider that really answered with "" gets passed through — that is its
    answer, and judging it is the Output Gate's job, not the transport's."""
    _stub(monkeypatch, _chat_reply(""))
    assert _transport().generate(PROMPT) == ""


# ===========================================================================
# Health — layered, nothing optimistic, and no key ever printed.
# ===========================================================================

def test_healthy_when_keyed_and_the_model_is_listed(monkeypatch):
    _stub(monkeypatch, _chat_reply(models=("kimi-k2", "other")))
    assert _transport().is_healthy() is True


def test_unhealthy_when_the_listing_does_not_contain_the_model(monkeypatch):
    _stub(monkeypatch, _chat_reply(models=("something-else",)))
    assert _transport().is_healthy() is False


def test_reachable_but_nameless_listing_reads_as_reachable(monkeypatch):
    """An endpoint that answers without ids is reachable but silent about names.
    Inferring "your model is gone" from that would mark a working Azure
    deployment unhealthy."""
    _stub(monkeypatch, _chat_reply(models=()))
    assert _transport().is_healthy() is True


def test_probe_failure_reads_as_unhealthy_and_never_raises(monkeypatch):
    def handler(*_args):
        raise urllib.error.URLError("down")

    _stub(monkeypatch, handler)
    assert _transport().is_healthy() is False


def test_a_recorded_failure_answers_without_spending_a_request(monkeypatch):
    """The tracker's stated minimum for this row: back is_healthy() with the
    adapter's own last LLMTransportError state. Once a generate() has failed, the
    next health question is answered from that record and costs no request."""
    frozen = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)

    def handler(_method, url, _body):
        raise urllib.error.HTTPError(url, 500, "boom", {}, None)

    _stub(monkeypatch, handler)
    transport = _transport(clock=lambda: frozen)
    with pytest.raises(CloudTransportError):
        transport.generate(PROMPT)

    calls = _stub(monkeypatch, _chat_reply())   # a now-working endpoint
    assert transport.is_healthy() is False
    assert calls == [], "the cooldown must answer without a request"


def test_the_cooldown_expires_so_a_recovered_tier_becomes_selectable(monkeypatch):
    """Without expiry, a single failure would make the tier permanently
    unselectable — the router only asks transports it might select, so nothing
    would ever retry."""
    clock = {"now": datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)}

    def failing(_method, url, _body):
        raise urllib.error.HTTPError(url, 500, "boom", {}, None)

    _stub(monkeypatch, failing)
    transport = _transport(clock=lambda: clock["now"])
    with pytest.raises(CloudTransportError):
        transport.generate(PROMPT)
    assert transport.is_healthy() is False

    _stub(monkeypatch, _chat_reply())
    clock["now"] += timedelta(seconds=31)
    assert transport.is_healthy() is True


def test_a_success_clears_the_failure_record(monkeypatch):
    frozen = datetime(2026, 8, 22, 12, 0, tzinfo=timezone.utc)
    transport = _transport(clock=lambda: frozen)

    def failing(_method, url, _body):
        raise urllib.error.HTTPError(url, 500, "boom", {}, None)

    _stub(monkeypatch, failing)
    with pytest.raises(CloudTransportError):
        transport.generate(PROMPT)
    assert transport.last_failure is not None

    _stub(monkeypatch, _chat_reply())
    transport.generate(PROMPT)
    assert transport.last_failure is None
    assert transport.is_healthy() is True


def test_health_without_a_models_url_rests_on_key_plus_failure_record(monkeypatch):
    """The Azure shape. No listing is meaningful for a deployment-scoped URL, so
    health is "keyed and not known to have failed" — exactly the minimum the
    needs-adapter row names, and no more."""
    calls = _stub(monkeypatch, _chat_reply())
    transport = _transport(models_url=None)
    assert transport.is_healthy() is True
    assert calls == [], "no models URL means no probe request"


def test_the_router_folds_an_unhealthy_cloud_tier_out_of_the_healthy_set(monkeypatch):
    """End-to-end with the real BackendRouter: FLAG B's rule holds for this
    adapter — only an explicit True joins the healthy set."""
    _stub(monkeypatch, _chat_reply(models=("nothing-matching",)))
    cloud = _transport()
    router = BackendRouter(
        gemma_transport=OllamaLocalTransport(),
        groq_transport=cloud,
        azure_transport=UnconfiguredTransport(tier_name="tier_2"),
    )
    health = router.check_health()
    assert health["groq"] is False
    assert health["azure"] is False


# ===========================================================================
# Secrets never leave the object.
# ===========================================================================

def test_the_key_is_sent_in_the_header_and_nowhere_else(monkeypatch):
    calls = _stub(monkeypatch, _chat_reply())
    _transport().generate(PROMPT)
    call = calls[0]
    header_values = " ".join(str(v) for v in call["headers"].values())
    assert FAKE_KEY in header_values
    assert FAKE_KEY not in json.dumps(call["body"])
    assert FAKE_KEY not in call["url"]


def test_the_key_never_appears_in_repr_describe_or_an_error(monkeypatch):
    def handler(_method, url, _body):
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

    _stub(monkeypatch, handler)
    transport = _transport()
    assert FAKE_KEY not in repr(transport)
    assert FAKE_KEY not in transport.describe()
    with pytest.raises(CloudTransportError) as caught:
        transport.generate(PROMPT)
    assert FAKE_KEY not in str(caught.value)
    assert FAKE_KEY not in (transport.last_failure or "")


def test_azure_uses_the_api_key_header_not_bearer(monkeypatch):
    calls = _stub(monkeypatch, _chat_reply())
    transport = azure_from_env(env={
        AZURE_API_KEY_ENV: FAKE_KEY,
        AZURE_ENDPOINT_ENV: "https://example.services.ai.azure.com",
        AZURE_DEPLOYMENT_ENV: "kimi-k2",
    })
    transport.generate(PROMPT)
    headers = {k.lower(): v for k, v in calls[0]["headers"].items()}
    assert headers["Api-key".lower()] == FAKE_KEY
    assert "authorization" not in headers


# ===========================================================================
# Factories — absent beats half-configured.
# ===========================================================================

def test_groq_factory_returns_none_without_a_key():
    assert groq_from_env(env={GROQ_MODEL_ENV: "some-model"}) is None


def test_groq_factory_returns_none_without_a_model():
    """No model tag is invented. Hardcoding one would pick a model on the
    operator's behalf — the mistake `resolve_model` refuses to make locally."""
    assert groq_from_env(env={GROQ_API_KEY_ENV: FAKE_KEY}) is None


def test_groq_factory_builds_the_openai_compatible_urls():
    transport = groq_from_env(env={
        GROQ_API_KEY_ENV: FAKE_KEY, GROQ_MODEL_ENV: "some-model",
    })
    assert transport.chat_url == f"{GROQ_BASE_URL}/chat/completions"
    assert transport.model == "some-model"
    assert transport.tier_name == "tier_1 (groq)"


def test_azure_factory_returns_none_when_half_configured():
    """A half-configured cloud tier reads as ABSENT rather than as broken, so the
    caller falls back to UnconfiguredTransport and routing stays correct."""
    assert azure_from_env(env={AZURE_API_KEY_ENV: FAKE_KEY}) is None
    assert azure_from_env(env={
        AZURE_API_KEY_ENV: FAKE_KEY,
        AZURE_ENDPOINT_ENV: "https://example.services.ai.azure.com",
    }) is None
    assert azure_from_env(env={
        AZURE_DEPLOYMENT_ENV: "kimi-k2",
        AZURE_ENDPOINT_ENV: "https://example.services.ai.azure.com",
    }) is None


def test_azure_factory_builds_the_deployment_path_with_an_api_version():
    transport = azure_from_env(env={
        AZURE_API_KEY_ENV: FAKE_KEY,
        AZURE_ENDPOINT_ENV: "https://example.services.ai.azure.com/",
        AZURE_DEPLOYMENT_ENV: "kimi-k2",
    })
    assert transport.chat_url == (
        "https://example.services.ai.azure.com/openai/deployments/kimi-k2"
        "/chat/completions?api-version=2024-10-21"
    )


def test_azure_factory_accepts_a_full_url_override():
    transport = azure_from_env(env={
        AZURE_API_KEY_ENV: FAKE_KEY,
        "ARIA_AZURE_CHAT_URL": "https://x.example/openai/v1/chat/completions",
        AZURE_DEPLOYMENT_ENV: "kimi-k2",
    })
    assert transport.chat_url == "https://x.example/openai/v1/chat/completions"


def test_env_summary_reports_presence_and_never_values():
    summary = " ".join(env_summary(env={GROQ_API_KEY_ENV: FAKE_KEY}))
    assert f"{GROQ_API_KEY_ENV}=set" in summary
    assert f"{AZURE_API_KEY_ENV}=unset" in summary
    assert FAKE_KEY not in summary


def test_whitespace_only_key_counts_as_absent():
    assert groq_from_env(env={
        GROQ_API_KEY_ENV: "   ", GROQ_MODEL_ENV: "m",
    }) is None


# ===========================================================================
# Token counts — the SAME side-channel shape the local transport reports.
# ===========================================================================

def _chat_reply_with_usage(
    text="a real reply", *, prompt_tokens=1234, completion_tokens=280,
    usage_present=True,
):
    def handler(_method, url, _body):
        if url.rstrip("/").endswith("/models"):
            payload = {"data": [{"id": "kimi-k2"}]}
        else:
            payload = {"choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }]}
            if usage_present:
                usage = {}
                if prompt_tokens is not None:
                    usage["prompt_tokens"] = prompt_tokens
                if completion_tokens is not None:
                    usage["completion_tokens"] = completion_tokens
                payload["usage"] = usage
        return _StubResponse(json.dumps(payload).encode("utf-8"))
    return handler


def test_last_turn_metadata_reports_usage(monkeypatch):
    transport = _transport()
    _stub(monkeypatch, _chat_reply_with_usage())

    assert transport.last_turn_metadata() is None        # nothing served yet
    transport.generate(PROMPT)

    meta = transport.last_turn_metadata()
    assert meta is not None
    assert meta.prompt_tokens == 1234
    assert meta.gen_tokens == 280


def test_cloud_and_local_report_the_same_metadata_type(monkeypatch):
    """One `TurnMetadata`, imported rather than copied — the same reason
    `split_prompt` is shared. The Daemon reads a served turn identically
    whichever tier served it."""
    cloud = _transport()
    local = OllamaLocalTransport()

    def handler(_method, url, _body):
        if "api.groq.com" in url:
            return _chat_reply_with_usage()(_method, url, _body)
        return _StubResponse(json.dumps({
            "response": "local reply", "done": True,
            "prompt_eval_count": 1234, "eval_count": 280,
            "eval_duration": 20_000_000_000,
        }).encode("utf-8"))

    _stub(monkeypatch, handler)
    monkeypatch.setattr(
        "adapters.transport_ollama.urllib.request.urlopen",
        lambda request, timeout=None: handler(
            request.get_method(), request.full_url, None
        ),
    )

    cloud.generate(PROMPT)
    local.generate(PROMPT)

    cloud_meta = cloud.last_turn_metadata()
    local_meta = local.last_turn_metadata()
    assert type(cloud_meta) is type(local_meta) is TurnMetadata
    assert cloud_meta.prompt_tokens == local_meta.prompt_tokens == 1234
    assert cloud_meta.gen_tokens == local_meta.gen_tokens == 280


def test_no_generation_duration_crosses_from_a_cloud_tier(monkeypatch):
    """These APIs report no generation time, and timing the round trip would
    measure the network as much as the model. So `duration_ns` stays None and the
    speed-degradation signal simply never fires for a cloud turn — absent rather
    than approximated."""
    transport = _transport()
    _stub(monkeypatch, _chat_reply_with_usage())

    transport.generate(PROMPT)
    assert transport.last_turn_metadata().duration_ns is None


def test_metadata_is_none_when_there_is_no_usage_field(monkeypatch):
    transport = _transport()
    _stub(monkeypatch, _chat_reply_with_usage(usage_present=False))

    transport.generate(PROMPT)
    assert transport.last_turn_metadata() is None


def test_generate_still_returns_a_plain_string(monkeypatch):
    """`ModelTransport.generate` is UNCHANGED — asserted structurally."""
    transport = _transport()
    _stub(monkeypatch, _chat_reply_with_usage("the verbatim reply"))

    out = transport.generate(PROMPT)
    assert out == "the verbatim reply"
    assert isinstance(out, str)
    assert isinstance(transport, ModelTransport)


def test_a_later_turn_overwrites_an_earlier_one(monkeypatch):
    transport = _transport()
    _stub(monkeypatch, _chat_reply_with_usage(prompt_tokens=500))
    transport.generate(PROMPT)
    assert transport.last_turn_metadata().prompt_tokens == 500

    # A provider that stops reporting stops being quoted: the old count
    # described a different prompt.
    _stub(monkeypatch, _chat_reply_with_usage(usage_present=False))
    transport.generate(PROMPT)
    assert transport.last_turn_metadata() is None


def test_a_failed_generation_leaves_no_counts(monkeypatch):
    """Recorded only after the content check passes, matching the local
    transport: a response that was not a valid generation leaves no measurement
    behind describing it as one."""
    transport = _transport()

    def handler(_method, _url, _body):
        return _StubResponse(json.dumps({
            "choices": [{"index": 0, "message": {"role": "assistant"},
                         "finish_reason": "length"}],
            "usage": {"prompt_tokens": 4242, "completion_tokens": 0},
        }).encode("utf-8"))

    _stub(monkeypatch, handler)
    with pytest.raises(CloudTransportError, match="no message content"):
        transport.generate(PROMPT)
    assert transport.last_turn_metadata() is None


def test_a_malformed_usage_block_is_not_a_measurement(monkeypatch):
    transport = _transport()

    def handler(_method, _url, _body):
        return _StubResponse(json.dumps({
            "choices": [{"index": 0,
                         "message": {"role": "assistant", "content": "hi"},
                         "finish_reason": "stop"}],
            "usage": "1234 tokens",
        }).encode("utf-8"))

    _stub(monkeypatch, handler)
    transport.generate(PROMPT)
    assert transport.last_turn_metadata() is None
