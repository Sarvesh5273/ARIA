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