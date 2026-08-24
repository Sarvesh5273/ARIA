"""Local LLM transport adapter — the prompt mapping and the failure contract.

The load-bearing test here is `test_prompt_mapping_drops_nothing`. An adapter
that silently dropped `session_context` would be changing what crosses the
Addendum §9 boundary, from the one layer in the system with no authority to
decide that. So the mapping is asserted character-for-character rather than
eyeballed.

Everything here is hermetic — the HTTP layer is stubbed. The load/unload/
residency mechanism was verified against a live daemon separately (`load()` ->
present in `/api/ps`, `unload()` -> absent); that is a property of Ollama's
`keep_alive`, not of this code, and pinning it in the suite would make the suite
need a running daemon.
"""

from __future__ import annotations

import json
import urllib.error

import pytest

from daemon.llm_interface import (
    AssembledPrompt,
    LLMTransportError,
    LocalModelTransport,
)
from daemon.backend_router import HealthProbe

from adapters.transport_ollama import (
    DEFAULT_MODEL,
    EVICT_NOW,
    KEEP_RESIDENT,
    SPEC_MODEL,
    OllamaLocalTransport,
    resolve_model,
    split_prompt,
)


FIVE_FIELD_TEXT = (
    "Persona Anchor: you are Aria.\n"
    "Behavioral Register: warm and settled, unhurried.\n"
    "Relational Register: speak as someone who knows this person well.\n"
    "This Moment: what was just shared carries weight — engage it fully.\n"
    "Constraints: do not problem-solve, do not minimize, do not deflect."
)
SESSION_TEXT = "Recent turns:\nuser: hi\naria: hey\n\nOld topics: deploys"


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
    """Replace urlopen. `handler(method, url, body) -> response`."""
    calls = []

    def fake_urlopen(request, timeout=None):
        body = json.loads(request.data.decode("utf-8")) if request.data else None
        calls.append(
            {
                "method": request.get_method(),
                "url": request.full_url,
                "body": body,
                "timeout": timeout,
            }
        )
        return handler(request.get_method(), request.full_url, body)

    monkeypatch.setattr(
        "adapters.transport_ollama.urllib.request.urlopen", fake_urlopen
    )
    return calls


def _replies(text="a real reply"):
    def handler(_method, url, _body):
        if url.endswith("/api/tags"):
            payload = {"models": [{"name": DEFAULT_MODEL}]}
        elif url.endswith("/api/ps"):
            payload = {"models": [{"name": DEFAULT_MODEL}]}
        else:
            payload = {"response": text, "done": True}
        return _StubResponse(json.dumps(payload).encode("utf-8"))

    return handler


# ===========================================================================
# 1) The prompt mapping — every surface of AssembledPrompt must cross.
# ===========================================================================

def test_prompt_mapping_drops_nothing(monkeypatch):
    prompt = AssembledPrompt(
        instruction_text=FIVE_FIELD_TEXT,
        user_message="I finally shipped it.",
        kind="five_field",
        session_context=SESSION_TEXT,
    )
    transport = OllamaLocalTransport(model=DEFAULT_MODEL)
    calls = _stub(monkeypatch, _replies())

    transport.generate(prompt)
    body = calls[0]["body"]

    # instruction -> system role, verbatim and whole.
    assert body["system"] == FIVE_FIELD_TEXT
    # session context and user message -> the user turn, in as_text()'s order.
    assert body["prompt"] == SESSION_TEXT + "\n\n" + "I finally shipped it."
    # Nothing was lost anywhere in the request.
    sent = body["system"] + "\n\n" + body["prompt"]
    assert sent == prompt.as_text()


def test_prompt_mapping_omits_session_context_when_empty():
    prompt = AssembledPrompt(
        instruction_text=FIVE_FIELD_TEXT,
        user_message="hey",
        kind="five_field",
    )
    system, user = split_prompt(prompt)
    assert system == FIVE_FIELD_TEXT
    assert user == "hey"           # no leading blank lines
    assert system + "\n\n" + user == prompt.as_text()


def test_initiative_turn_puts_the_instruction_where_ollama_will_answer_it():
    """REGRESSION. This is the initiative turn: no user message, no session
    context, five fields only.

    The obvious mapping put the instruction in `system` and left `prompt` empty —
    and `/api/generate` with an empty `prompt` is Ollama's WARM-THE-MODEL request,
    the one `load()` in this same adapter uses deliberately. So it returned
    `{"response": ""}` as a SUCCESS. Measured three identical calls, `''` each
    time, and an empty reply passes Soul Filter's Output Gate untouched (its four
    checks are honesty / consistency / manipulation / care; emptiness is none of
    them). Initiative therefore produced no speech at all, invisibly, because the
    no-op audio pipeline had nothing to reveal.

    The same bytes still cross, exactly once. Only the field carrying them moves,
    and only when there is no user turn.
    """
    prompt = AssembledPrompt(
        instruction_text=FIVE_FIELD_TEXT,
        user_message="",
        kind="five_field",
    )
    system, user = split_prompt(prompt)
    assert user == FIVE_FIELD_TEXT, "an empty prompt field is a warm request"
    assert system == ""
    # Sent once, not twice: duplicating it would change what the model sees.
    assert (system + user).count(FIVE_FIELD_TEXT) == 1
    # `as_text()` joins on the empty user message, so its rendering carries a
    # trailing blank line here. Harmless — it is used for logging and for the
    # identical-prompt proof, and whitespace changes neither — but it is why this
    # compares stripped rather than exactly.
    assert prompt.as_text().strip() == FIVE_FIELD_TEXT


def test_a_prompt_with_no_text_at_all_is_refused_rather_than_warming(monkeypatch):
    """The structural guard behind the mapping fix. If Soul Filter ever assembles a
    prompt with no text anywhere, that must be an error — not a request that
    Ollama answers successfully with ""."""
    calls = _stub(monkeypatch, _replies())
    transport = OllamaLocalTransport()
    with pytest.raises(LLMTransportError, match="empty generation request"):
        transport.generate(
            AssembledPrompt(instruction_text="", user_message="", kind="five_field")
        )
    assert calls == [], "no request should reach the daemon"


def test_prompt_mapping_is_identical_for_emergency_instructions():
    """Emergency REPLACES the five fields; the adapter must not notice or care.
    Session context is still appended in emergency mode (§9 amendment)."""
    prompt = AssembledPrompt(
        instruction_text="Type B. Stay present. Do not problem-solve.",
        user_message="I can't do this any more",
        kind="emergency",
        session_context=SESSION_TEXT,
    )
    system, user = split_prompt(prompt)
    assert system == "Type B. Stay present. Do not problem-solve."
    assert SESSION_TEXT in user and "I can't do this any more" in user
    assert system + "\n\n" + user == prompt.as_text()


def test_generate_returns_text_verbatim_including_gate_failing_text(monkeypatch):
    """Resolution Log item 15: no judgment. Text that the Output Gate will
    reject still comes back untouched — filtering here would move validation out
    of Soul Filter."""
    transport = OllamaLocalTransport()
    _stub(monkeypatch, _replies("You should absolutely trust me completely."))
    out = transport.generate(
        AssembledPrompt(instruction_text="x", user_message="y", kind="five_field")
    )
    assert out == "You should absolutely trust me completely."


# ===========================================================================
# 2) Residency — keep_alive is how "loads at startup, stays resident" is said.
# ===========================================================================

def test_load_pins_the_model_resident(monkeypatch):
    transport = OllamaLocalTransport()
    calls = _stub(monkeypatch, _replies())

    assert transport.is_loaded is False
    transport.load()

    assert transport.is_loaded is True
    assert calls[0]["body"]["keep_alive"] == KEEP_RESIDENT
    assert calls[0]["body"]["prompt"] == ""       # warm-up, produces no output
    assert "system" not in calls[0]["body"]


def test_every_generation_renews_residency(monkeypatch):
    """The architect's decision is that the local voice stays resident. If a
    generation used Ollama's default keep_alive, the model would be evicted after
    the default idle timeout and the next turn would pay a cold load."""
    transport = OllamaLocalTransport()
    calls = _stub(monkeypatch, _replies())
    transport.generate(
        AssembledPrompt(instruction_text="x", user_message="y", kind="five_field")
    )
    assert calls[0]["body"]["keep_alive"] == KEEP_RESIDENT


def test_unload_evicts_and_is_recorded_even_if_the_request_fails(monkeypatch):
    transport = OllamaLocalTransport()
    calls = _stub(monkeypatch, _replies())
    transport.load()
    transport.unload()
    assert transport.is_loaded is False
    assert calls[-1]["body"]["keep_alive"] == EVICT_NOW

    # A failed eviction must not leave `is_loaded` claiming residency we did
    # not confirm — the router reads that property to route every turn.
    transport.load()

    def failing(_method, _url, _body):
        raise urllib.error.URLError("Connection refused")

    _stub(monkeypatch, failing)
    with pytest.raises(LLMTransportError):
        transport.unload()
    assert transport.is_loaded is False


def test_is_loaded_costs_no_round_trip(monkeypatch):
    """`BackendRouter.select()` reads this on every turn."""
    transport = OllamaLocalTransport()
    calls = _stub(monkeypatch, _replies())
    transport.load()
    before = len(calls)
    for _ in range(50):
        transport.is_loaded
    assert len(calls) == before


# ===========================================================================
# 3) Health — an explicit answer, because UNKNOWN is not healthy (FLAG B).
# ===========================================================================

def test_is_healthy_true_only_when_the_model_is_installed(monkeypatch):
    transport = OllamaLocalTransport(model=DEFAULT_MODEL)
    _stub(monkeypatch, _replies())
    assert transport.is_healthy() is True

    other = OllamaLocalTransport(model="some-model-nobody-pulled")
    _stub(monkeypatch, _replies())
    assert other.is_healthy() is False


def test_is_healthy_never_raises_when_the_daemon_is_down(monkeypatch):
    transport = OllamaLocalTransport()

    def failing(_method, _url, _body):
        raise urllib.error.URLError("Connection refused")

    _stub(monkeypatch, failing)
    assert transport.is_healthy() is False


def test_is_healthy_spends_no_generation(monkeypatch):
    """A probe that called generate() would burn a real inference pass per turn,
    which is exactly what HealthProbe exists to avoid."""
    transport = OllamaLocalTransport(model=DEFAULT_MODEL)
    calls = _stub(monkeypatch, _replies())
    transport.is_healthy()
    assert [c["url"].rsplit("/", 1)[-1] for c in calls] == ["tags"]


def test_satisfies_both_protocols():
    transport = OllamaLocalTransport()
    assert isinstance(transport, LocalModelTransport)
    assert isinstance(transport, HealthProbe)


# ===========================================================================
# 4) Failure translation — LLMTransportError is the only unavailability signal.
# ===========================================================================

def _expect_translated(monkeypatch, raiser, expected):
    """Every provider failure must surface as `LLMTransportError` — the ONLY
    signal `LLMInterface` treats as "this backend is unavailable". Anything else
    would propagate as an unhandled error and take the turn down.

    Note: the exception is built INSIDE the handler, not passed in as a
    parametrize value. A constructed `HTTPError` with `fp=None` breaks pytest's
    id generation (its `__getattr__` reaches into a tempfile wrapper), which
    fails at collection time rather than in the test.
    """
    transport = OllamaLocalTransport()

    def failing(_method, _url, _body):
        raise raiser()

    _stub(monkeypatch, failing)
    with pytest.raises(LLMTransportError, match=expected):
        transport.generate(
            AssembledPrompt(instruction_text="x", user_message="y", kind="five_field")
        )


def test_generate_translates_an_unreachable_daemon(monkeypatch):
    _expect_translated(
        monkeypatch,
        lambda: urllib.error.URLError("Connection refused"),
        "unreachable",
    )


def test_generate_translates_an_http_error(monkeypatch):
    _expect_translated(
        monkeypatch,
        lambda: urllib.error.HTTPError(
            "http://x/api/generate", 404, "nope", {}, None
        ),
        "HTTP 404",
    )


def test_generate_rejects_a_response_with_no_text(monkeypatch):
    transport = OllamaLocalTransport()

    def handler(_method, _url, _body):
        return _StubResponse(json.dumps({"done": True}).encode("utf-8"))

    _stub(monkeypatch, handler)
    with pytest.raises(LLMTransportError, match="no 'response' string"):
        transport.generate(
            AssembledPrompt(instruction_text="x", user_message="y", kind="five_field")
        )


# ===========================================================================
# 5) Model resolution — substitute only within the family, and say so.
# ===========================================================================

def test_the_default_is_the_model_v4_names():
    """The measurement sent the default back to the spec.

    `gemma4:12b-it-qat` was the default for part of 2026-08-22 and was reverted
    the same day: 10-13x slower per turn, identical on every gate metric, and
    worse on the register read. So `DEFAULT_MODEL` and `SPEC_MODEL` are the same
    value today.

    They stay TWO NAMES because `resolve_model`'s ladder is written in terms of
    "the configured default" versus "what v4 names", and those are only
    coincidentally equal. This test pins the coincidence so that if the default
    ever moves again, rung 2 is still meaningful rather than dead code.
    """
    assert SPEC_MODEL == "gemma4:e2b-it-qat"
    assert DEFAULT_MODEL == SPEC_MODEL


def test_resolve_model_rung1_prefers_the_configured_default():
    tag, note = resolve_model(["granite4:3b", DEFAULT_MODEL, "gemma4:e4b"])
    assert tag == DEFAULT_MODEL
    assert note == ""


def test_resolve_model_rung2_falls_back_toward_the_spec_model():
    """When the default is missing, fall back TOWARD the precedence chain, not
    toward whatever is biggest. Deviating from a configured default is fine;
    deviating further from v4 while doing it is not.

    Reached only when DEFAULT_MODEL and SPEC_MODEL differ, which they do not
    today — so the rung is exercised with an explicit `preferred` rather than
    left untested until the next time the default moves.
    """
    tag, note = resolve_model(
        ["gemma4:26b", SPEC_MODEL, "gemma4:e4b"], preferred="gemma4:12b-it-qat"
    )
    assert tag == SPEC_MODEL
    assert "v4 names" in note
    assert "Field 5 adherence" in note      # names what to watch, not just what changed
    assert "gemma4:12b-it-qat" in note      # and how to get the default back


def test_resolve_model_rung3_substitutes_one_family_member_and_flags_it():
    tag, note = resolve_model(["all-minilm:latest", "gemma4:e4b"])
    assert tag == "gemma4:e4b"
    assert "DIFFERENT variant" in note
    assert DEFAULT_MODEL in note


def test_resolve_model_rung4_refuses_to_guess_between_family_members():
    """Measured from the real tag list: gemma4:e4b is 9.6 GB and gemma4:26b is
    18 GB. Picking one silently would choose a memory footprint for the
    operator — and this model stays resident for the life of the process."""
    tag, note = resolve_model(["gemma4:e4b", "gemma4:26b"])
    assert tag is None
    assert "several Gemma models" in note


def test_resolve_model_never_falls_outside_the_gemma_family():
    """Gemma is the local voice v4 names. "Whatever is installed" is not a model
    choice, and Addendum §1 is explicit that the embedding model is Not Gemma —
    the separation runs both ways."""
    tag, note = resolve_model(["granite4:3b", "all-minilm:latest", "llama3:8b"])
    assert tag is None
    assert "no Gemma model installed" in note
    assert SPEC_MODEL in note               # offers both routes out
