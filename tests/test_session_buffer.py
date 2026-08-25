"""Tests for SessionBuffer (daemon/session_buffer.py)."""

import pytest

from daemon.session_buffer import (
    _CRITICAL_PRESSURE_INSTRUCTION,
    _HEAVY_PRESSURE_INSTRUCTION,
    _MEDIUM_TOKEN_BUDGET,
    _OLD_TOKEN_BUDGET,
    _RECENT_TOKEN_BUDGET,
    _SLOW_GENERATION_TOK_S,
    _TOTAL_TOKEN_BUDGET,
    SessionBuffer,
)


def test_empty_buffer_returns_empty_context():
    buf = SessionBuffer()
    assert buf.get_context() == ""
    assert buf.fullness_state() == "light"


def test_append_turn_adds_to_recent():
    buf = SessionBuffer()
    buf.append_turn("Hello", "Hi there")
    ctx = buf.get_context()
    assert "User: Hello" in ctx
    assert "Aria: Hi there" in ctx


def test_meta_command_rest_detected():
    buf = SessionBuffer()
    assert buf.is_meta_command("I need to rest") == "rest"
    assert buf.is_meta_command("Take a break") == "rest"
    assert buf.is_meta_command("clear your head") == "rest"


def test_meta_command_focus_detected():
    buf = SessionBuffer()
    assert buf.is_meta_command("focus") == "focus"
    assert buf.is_meta_command("be here now") == "focus"


def test_meta_command_unfocus_detected():
    buf = SessionBuffer()
    assert buf.is_meta_command("unfocus") == "unfocus"
    assert buf.is_meta_command("full memory") == "unfocus"


def test_meta_command_none_for_normal_text():
    buf = SessionBuffer()
    assert buf.is_meta_command("How are you?") is None
    assert buf.is_meta_command("restaurant") is None  # substring, not match


def test_clear_wipes_all_tiers():
    buf = SessionBuffer()
    for i in range(25):
        buf.append_turn(f"msg {i}", f"reply {i}")
    buf.clear()
    assert buf.get_context() == ""
    assert buf.fullness_state() == "light"


def test_focus_mode_drops_medium_and_old():
    buf = SessionBuffer()
    # Fill RECENT enough to trigger promotion to MEDIUM.
    # RECENT budget = 12000 tokens = ~48,000 chars.
    # Each turn = ~1040 chars => 60 turns = ~62,000 chars = ~15,500 tokens.
    # (40 turns was enough at the old 8000 budget and is not enough now.)
    long_msg = "x" * 500
    long_reply = "y" * 500
    for i in range(60):
        buf.append_turn(f"{long_msg} turn {i}", f"{long_reply} turn {i}")
    # Verify promotion actually happened
    assert len(buf._medium) > 0, "MEDIUM tier should have items -- test precondition failed"
    buf.set_focus_mode(True)
    ctx = buf.get_context()
    assert "[Recent]" in ctx
    assert "[Earlier" not in ctx  # medium and old hidden
    buf.set_focus_mode(False)
    ctx2 = buf.get_context()
    assert "[Earlier" in ctx2  # restored


def test_fullness_state_light():
    buf = SessionBuffer()
    buf.append_turn("hi", "hello")
    assert buf.fullness_state() == "light"


def test_budgets_are_the_resized_set():
    """24K total (12K+8K+4K). Pinned because the band boundaries are FRACTIONS
    of the total — a budget change silently moves every band with it, so the
    number the bands are computed from should not drift unnoticed."""
    assert _RECENT_TOKEN_BUDGET == 12000
    assert _MEDIUM_TOKEN_BUDGET == 8000
    assert _OLD_TOKEN_BUDGET == 4000
    assert _TOTAL_TOKEN_BUDGET == 24000


def test_fullness_state_settled_when_medium_has_items():
    buf = SessionBuffer()
    # Force promotion to MEDIUM: exceed RECENT budget (12000 tokens).
    # ~2020 chars/turn => 30 turns = ~60,000 chars = ~15,000 tokens.
    long_msg = "x" * 1000
    long_reply = "y" * 1000
    for i in range(30):
        buf.append_turn(f"{long_msg} {i}", f"{long_reply} {i}")
    assert len(buf._medium) > 0, "precondition: MEDIUM should have items"
    # ~10.2K of a 24K budget — the band is read from SIZE, and this size is
    # settled. That it also happens to have a MEDIUM tier is incidental now;
    # see test_tier_occupancy_no_longer_decides_the_band.
    assert buf.fullness_state() == "settled"


def test_tier_occupancy_no_longer_decides_the_band():
    """Documents the change of signal. Under the old logic "OLD has items" WAS
    "heavy". It is not any more, and this case is why: promotion COMPRESSES, so
    a buffer deep enough to have archived topic tags can be holding less than a
    third of the budget. Reporting that as heavy overstated the load."""
    buf = SessionBuffer()
    # Fill MEDIUM directly, then force promotion to OLD (cheaper than the
    # hundreds of real turns it would take).
    for i in range(70):
        buf._medium.append(type('S', (), {'text': f"Summary {i}" * 50, 'turn_count': 10})())
    buf._maybe_promote_medium_to_old()
    assert len(buf._old) > 0, "precondition: OLD should have items"
    assert buf._total_token_estimate() < _TOTAL_TOKEN_BUDGET * 0.5
    assert buf.fullness_state() == "settled"


# ===========================================================================
# Actual token counts — the provider's own numbers, not chars // 4.
# ===========================================================================

@pytest.mark.parametrize(
    "prompt_tokens,expected",
    [
        (0, "light"),
        (5_999, "light"),          # just under 25% of 24K
        (6_000, "settled"),        # exactly 25%
        (11_999, "settled"),
        (12_000, "heavy"),         # exactly 50%
        (17_999, "heavy"),
        (18_000, "critical"),      # exactly 75%
        (40_000, "critical"),      # over budget entirely
    ],
)
def test_fullness_bands_are_percentages_of_the_budget(prompt_tokens, expected):
    buf = SessionBuffer()
    buf.record_actual_tokens(prompt_tokens=prompt_tokens)
    assert buf.fullness_state() == expected


def test_actual_tokens_beat_the_estimate():
    """The whole point of the side-channel: when the provider has counted, the
    guess is not consulted."""
    buf = SessionBuffer()
    for i in range(30):
        buf.append_turn("x" * 1000, "y" * 1000)
    assert buf.fullness_state() == "settled"       # from the estimate

    buf.record_actual_tokens(prompt_tokens=20_000)
    assert buf.fullness_state() == "critical"      # from the real count
    assert buf._total_token_estimate() < 12_000    # estimate unchanged, ignored


def test_no_report_falls_back_to_the_estimate():
    """No BackendRouter wired, or a provider that reports no usage: the buffer
    keeps using chars // 4 rather than pretending to know."""
    buf = SessionBuffer()
    assert buf._actual_prompt_tokens is None
    assert buf.fullness_state() == "light"

    buf.record_actual_tokens(prompt_tokens=20_000)
    assert buf.fullness_state() == "critical"

    # A later turn that reports NOTHING must not keep quoting the old number —
    # it described a different prompt.
    buf.record_actual_tokens()
    assert buf._actual_prompt_tokens is None
    assert buf.fullness_state() == "light"


def test_record_actual_tokens_computes_generation_speed():
    buf = SessionBuffer()
    buf.record_actual_tokens(
        prompt_tokens=1_000, gen_tokens=280, gen_duration_ms=20_000
    )
    assert buf._actual_gen_tokens == 280
    assert buf._last_gen_speed_tok_s == pytest.approx(14.0)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"gen_tokens": 100},                              # no duration (cloud)
        {"gen_duration_ms": 5_000},                       # no token count
        {"gen_tokens": 100, "gen_duration_ms": 0},        # zero duration
        {"gen_tokens": 100, "gen_duration_ms": -5},       # nonsense duration
    ],
)
def test_speed_stays_unknown_rather_than_invented(kwargs):
    buf = SessionBuffer()
    buf.record_actual_tokens(prompt_tokens=1_000, **kwargs)
    assert buf._last_gen_speed_tok_s is None


# ===========================================================================
# Speed degradation IS context pressure.
# ===========================================================================

def test_slow_generation_bumps_the_band_one_step():
    buf = SessionBuffer()
    # 8K of 24K = 33% => settled on count alone.
    buf.record_actual_tokens(prompt_tokens=8_000)
    assert buf.fullness_state() == "settled"

    # Same count, but 60 tokens in 20s = 3 tok/s.
    buf.record_actual_tokens(
        prompt_tokens=8_000, gen_tokens=60, gen_duration_ms=20_000
    )
    assert buf._last_gen_speed_tok_s < _SLOW_GENERATION_TOK_S
    assert buf.fullness_state() == "heavy"


def test_healthy_speed_does_not_bump():
    buf = SessionBuffer()
    buf.record_actual_tokens(
        prompt_tokens=8_000, gen_tokens=280, gen_duration_ms=20_000  # 14 tok/s
    )
    assert buf._last_gen_speed_tok_s >= _SLOW_GENERATION_TOK_S
    assert buf.fullness_state() == "settled"


def test_the_bump_saturates_at_critical():
    """No fifth band gets invented."""
    buf = SessionBuffer()
    buf.record_actual_tokens(
        prompt_tokens=23_000, gen_tokens=10, gen_duration_ms=20_000  # 0.5 tok/s
    )
    assert buf.fullness_state() == "critical"


def test_the_bump_can_lift_light_to_settled():
    buf = SessionBuffer()
    buf.record_actual_tokens(
        prompt_tokens=500, gen_tokens=10, gen_duration_ms=20_000
    )
    assert buf.fullness_state() == "settled"


def test_clear_drops_the_measured_token_record():
    """Those counts described a prompt built from content that no longer exists.
    Keeping them would have an EMPTY buffer reporting critical."""
    buf = SessionBuffer()
    buf.append_turn("hi", "hello")
    buf.record_actual_tokens(
        prompt_tokens=20_000, gen_tokens=10, gen_duration_ms=20_000
    )
    assert buf.fullness_state() == "critical"

    buf.clear()
    assert buf._actual_prompt_tokens is None
    assert buf._actual_gen_tokens is None
    assert buf._last_gen_speed_tok_s is None
    assert buf.fullness_state() == "light"


# ===========================================================================
# express_pressure() — the loaded bands as an instruction. NOT WIRED to the
# LLM; see the method's docstring for the two rulings that gates it.
# ===========================================================================

def test_express_pressure_is_silent_when_not_loaded():
    buf = SessionBuffer()
    buf.record_actual_tokens(prompt_tokens=1_000)      # light
    assert buf.express_pressure() is None
    buf.record_actual_tokens(prompt_tokens=8_000)      # settled
    assert buf.express_pressure() is None


def test_express_pressure_heavy_speaks_once_per_session():
    buf = SessionBuffer()
    buf.record_actual_tokens(prompt_tokens=13_000)     # heavy
    assert buf.express_pressure() == _HEAVY_PRESSURE_INSTRUCTION
    # Saying it every turn would be performance, not expression.
    assert buf.express_pressure() is None
    assert buf.express_pressure() is None


def test_rest_re_arms_the_heavy_pressure_latch():
    """Resolution Log item 29. "rest" is a cognitive reset — start fresh — so the
    latch re-arms with the tiers. Arriving at heaviness a second time after a rest
    is a new arrival, and she can say so again."""
    buf = SessionBuffer()
    buf.record_actual_tokens(prompt_tokens=13_000)      # heavy
    assert buf.express_pressure() == _HEAVY_PRESSURE_INSTRUCTION
    assert buf.express_pressure() is None              # latched

    buf.clear()                                        # "rest"
    assert buf._heavy_pressure_expressed is False

    buf.record_actual_tokens(prompt_tokens=13_000)      # heavy again
    assert buf.express_pressure() == _HEAVY_PRESSURE_INSTRUCTION
    assert buf.express_pressure() is None              # and latches again


def test_express_pressure_critical_holds_every_turn():
    buf = SessionBuffer()
    buf.record_actual_tokens(prompt_tokens=19_000)     # critical
    assert buf.express_pressure() == _CRITICAL_PRESSURE_INSTRUCTION
    assert buf.express_pressure() == _CRITICAL_PRESSURE_INSTRUCTION


def test_express_pressure_carries_no_number_and_no_band_label():
    """Field-5 shaped: the instruction crosses, the measurement does not — the
    same split the Energy gate already uses in SoulFilter._derive_constraints."""
    for text in (_HEAVY_PRESSURE_INSTRUCTION, _CRITICAL_PRESSURE_INSTRUCTION):
        assert not any(ch.isdigit() for ch in text)
        low = text.lower()
        assert "token" not in low
        for band in ("light", "settled", "heavy", "critical"):
            assert band not in low


def test_express_pressure_reflects_the_speed_bump():
    """Pressure she can feel but the token count alone would not show."""
    buf = SessionBuffer()
    # 11K of 24K is settled on count; a 1 tok/s generation makes it heavy.
    buf.record_actual_tokens(
        prompt_tokens=11_000, gen_tokens=20, gen_duration_ms=20_000
    )
    assert buf.fullness_state() == "heavy"
    assert buf.express_pressure() == _HEAVY_PRESSURE_INSTRUCTION


def test_express_pressure_is_not_wired_to_the_llm_yet():
    """Guard on a deliberate gap. Wiring this into Field 5 needs an architect
    ruling (who appends it, given Addendum §9's MAX-3 cap; and whether the
    state-claim first sentence may cross at all). If a caller appears, this test
    should be deleted BY the change that adds it — not left passing by accident."""
    import daemon.aria_daemon as aria_daemon
    import daemon.soul_filter as soul_filter
    import inspect

    for module in (aria_daemon, soul_filter):
        assert "express_pressure" not in inspect.getsource(module)


def test_rule_based_summary_extracts_topic_and_emotion():
    buf = SessionBuffer()
    # Manually create a chunk that will be summarized
    turns = [
        ("I am frustrated with work", "That sounds hard"),
        ("My boss yelled at me", "I'm sorry"),
        ("I feel overwhelmed", "I'm here"),
    ]
    for u, a in turns:
        buf.append_turn(u, a)
    summary = buf._summarize_turns([type('T', (), {'user_text': u, 'aria_text': a})() for u, a in turns])
    assert "frustrated" in summary or "overwhelmed" in summary
    assert "3 turns" in summary


def test_get_context_format_has_sections():
    buf = SessionBuffer()
    for i in range(50):
        buf.append_turn(f"msg {i}", f"reply {i}")
    ctx = buf.get_context()
    # Should have at least one section header
    assert "[Recent]" in ctx or "[Earlier" in ctx



# ===========================================================================
# Item 22's compounding loop: her own markers are stripped from the RENDERING,
# never from the stored record. Same shape as item 25's speech-surface ruling.
# ===========================================================================

def test_get_context_strips_format_markers_from_aria_replies():
    """Stage directions in her stored replies are stripped from the context
    string, so they do not re-enter and teach her the syntax. Item 22 measured
    that loop: 4/8 -> 8/8 across two rounds."""
    buf = SessionBuffer()
    buf.append_turn("How are you?", "[I pause briefly.]\nI am well. And you?")
    buf.append_turn("Good.", "(A small smile.)\nThat is good to hear.")
    context = buf.get_context()

    assert "[I pause briefly.]" not in context
    assert "(A small smile.)" not in context
    assert "I am well. And you?" in context
    assert "That is good to hear." in context


def test_the_stored_record_is_still_verbatim_after_rendering():
    """The load-bearing half. `get_context` edits a RENDERING; `append_turn` keeps
    her reply byte-for-byte, because the graph, the printed transcript, the Visual
    Layer and the TTS path all read the stored text. Editing the record would be
    deciding what she said — the option items 22 and 25 both refuse."""
    buf = SessionBuffer()
    original = "[I lean forward.]\nI hear you."
    buf.append_turn("hi", original)

    buf.get_context()   # rendering must not mutate anything
    assert buf._recent[0].aria_text == original
    assert buf.get_context().count("[I lean forward.]") == 0
    assert buf._recent[0].aria_text == original   # still verbatim after a 2nd render


def test_get_context_does_not_strip_user_text():
    """User text is never filtered — it is not hers to edit, she is not learning
    her voice from it, and a parenthetical the user wrote is information."""
    buf = SessionBuffer()
    buf.append_turn("I went to the store (the big one)", "Interesting.")
    context = buf.get_context()
    assert "(the big one)" in context


def test_her_own_mid_sentence_parentheticals_survive():
    """The anchoring is load-bearing AT THIS SURFACE SPECIFICALLY, more than it was
    at the speech surface. An unanchored strip would delete real content she had
    already said, and the buffer is the record she reasons from on the NEXT turn —
    so she could contradict herself from her own edited transcript. Removing a
    marker is a rendering decision; removing a fact is not."""
    buf = SessionBuffer()
    buf.append_turn(
        "when is it?",
        "The meeting is at three (Tuesday, not Monday) so you have time.",
    )
    context = buf.get_context()
    assert "(Tuesday, not Monday)" in context


def test_list_content_survives_only_the_bullet_marker_goes():
    """Same reason: "- call the bank" must keep "call the bank". A strip that
    deleted whole bullet LINES would lose things she had already told him."""
    buf = SessionBuffer()
    buf.append_turn("what next?", "Two things:\n- call the bank\n- send the form")
    context = buf.get_context()
    assert "call the bank" in context
    assert "send the form" in context


def test_reasoning_trace_TAGS_go_but_their_content_stays_a_recorded_residual():
    """MEASURED, and it is a residual rather than a fix — recorded here because the
    obvious assumption is wrong.

    The shared pattern removes `<think>` / `</think>` as MARKERS; it does not
    remove the text between them. That is the same behaviour already recorded on
    the speech path, where macOS `say` "silently drops the TAGS and speaks the
    CONTENT as ordinary prose" — the trace does not sound like a malfunction, it
    sounds like her thinking out loud.

    So at THIS surface a reasoning trace still re-enters as context. ResLog 24
    flags that as live, because `qwen3.5:9b-mlx` reports a `thinking` capability.

    NOT fixed by widening the regex, deliberately. Item 22's measurements are
    expressed in terms of this exact pattern, and a strip that removed more than
    the detector reports would make the 3/16 figure describe something that no
    longer exists — the same detector/defect mismatch that nearly put "prompt
    mitigation is sufficient" into the Resolution Log. Removing trace CONTENT is a
    separate decision with its own reasoning, so it is flagged, not invented.
    """
    buf = SessionBuffer()
    buf.append_turn("hi", "<think>they seem tired</think>\nHow was your day?")
    context = buf.get_context()

    assert "<think>" not in context          # the tags go
    assert "they seem tired" in context      # the content does NOT — residual
    assert "How was your day?" in context


def test_an_all_narration_reply_renders_empty_and_is_counted():
    """No substitute sentence is invented (item 21's terminal case: writing one
    would be putting words in her mouth). So the case must be VISIBLE, or an empty
    `Aria:` line reads as her having said nothing when she said only narration."""
    buf = SessionBuffer()
    buf.append_turn("hi", "[I hold the silence, my gaze steady.]")
    context = buf.get_context()

    assert "Aria:" in context
    assert "gaze steady" not in context
    assert buf.all_narration_replies == 1
    # Derived, not accumulated: rendering twice must not double it.
    buf.get_context()
    assert buf.all_narration_replies == 1


def test_ordinary_replies_are_not_counted_as_narration():
    """Non-vacuous guard on the property above."""
    buf = SessionBuffer()
    buf.append_turn("hi", "Hello. How are you?")
    buf.get_context()
    assert buf.all_narration_replies == 0


def test_the_tier_scaffolding_survives_the_strip():
    """"[Earlier today]" and "- tag" are bracket and bullet syntax the pattern
    WOULD match. They are the buffer's own framing, added after the strip. Anyone
    stripping the assembled string instead of the per-reply text deletes them."""
    buf = SessionBuffer()
    # Enough volume to actually cross the 12K recent budget and promote, so the
    # medium-tier header is really present rather than assumed. (80 short turns
    # did not — the first version of this test passed its `[Recent]` assertion and
    # proved nothing about the tier headers.)
    filler = "and some additional length so the recent budget is genuinely crossed"
    for i in range(600):
        buf.append_turn(f"message number {i} {filler}", f"reply number {i} {filler}")
    context = buf.get_context()
    assert "[Recent]" in context
    assert "[Earlier in this conversation]" in context


def test_the_buffer_and_the_speech_path_share_ONE_pattern():
    """The whole reason the pattern moved into `daemon/`. Item 22's near-miss was a
    detector/defect MISMATCH, so two copies drifting apart is the precise failure
    the measurement already survived once. Object identity, not equal behaviour."""
    from daemon.format_markers import strip_format_markers as shared
    from daemon import session_buffer as sb
    import adapters.audio_tts as tts

    assert sb.strip_format_markers is shared
    assert tts.strip_format_markers is shared
    assert tts._FORMAT_MARKER_RE is __import__(
        "daemon.format_markers", fromlist=["FORMAT_MARKER_RE"]
    ).FORMAT_MARKER_RE


def test_daemon_still_imports_nothing_from_adapters_after_the_move():
    """The one-way arrow is the reason this went DOWN into `daemon/` rather than
    being imported UP from `adapters/`. Restated here because this change is the
    one that would have broken it."""
    import ast
    import pathlib

    for path in sorted(pathlib.Path("daemon").glob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("adapters"), path.name
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    assert not alias.name.startswith("adapters"), path.name
