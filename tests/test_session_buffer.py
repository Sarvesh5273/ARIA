"""Tests for SessionBuffer (daemon/session_buffer.py)."""

import pytest

from daemon.session_buffer import SessionBuffer


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
    # RECENT budget = 8000 tokens = ~32,000 chars.
    # Each turn = ~1100 chars => 40 turns = ~44,000 chars = ~11,000 tokens.
    long_msg = "x" * 500
    long_reply = "y" * 500
    for i in range(40):
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


def test_fullness_state_settled_when_medium_has_items():
    buf = SessionBuffer()
    # Force promotion to MEDIUM: exceed RECENT budget (8000 tokens)
    long_msg = "x" * 1000
    long_reply = "y" * 1000
    for i in range(20):
        buf.append_turn(f"{long_msg} {i}", f"{long_reply} {i}")
    assert len(buf._medium) > 0, "precondition: MEDIUM should have items"
    assert buf.fullness_state() == "settled"


def test_fullness_state_heavy_when_old_has_items():
    buf = SessionBuffer()
    # Fill MEDIUM tier directly, then force promotion to OLD.
    # MEDIUM budget = 6000 tokens. Each summary ~100 tokens.
    # We need 60+ summaries to exceed budget. Instead of adding 600+ turns,
    # we directly populate MEDIUM and trigger promotion.
    for i in range(70):
        buf._medium.append(type('S', (), {'text': f"Summary {i}" * 50, 'turn_count': 10})())
    buf._maybe_promote_medium_to_old()
    assert len(buf._old) > 0, "precondition: OLD should have items"
    assert buf.fullness_state() == "heavy"


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