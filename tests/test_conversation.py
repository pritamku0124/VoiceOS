"""Tests for short-term conversation memory."""

from actions.action_schema import Intent
from ai.conversation_manager import ConversationContext


def test_remembers_last_app_from_open_switch_and_window_actions():
    ctx = ConversationContext()
    assert ctx.resolve_target("it") == "current"  # nothing mentioned yet -> active window
    ctx.remember("open spotify", [Intent("OPEN_APPLICATION", {"app": "Spotify"})])
    assert ctx.resolve_target("it") == "Spotify"
    ctx.remember("minimize chrome", [Intent("MINIMIZE_WINDOW", {"target": "Google Chrome"})])
    assert ctx.resolve_target("that") == "Google Chrome"
    ctx.remember("minimize this window", [Intent("MINIMIZE_WINDOW", {"target": "current"})])
    assert ctx.resolve_target("it") == "Google Chrome"  # "current" doesn't overwrite the memory


def test_keeps_only_recent_turns_for_the_prompt():
    ctx = ConversationContext()
    for n in range(10):
        ctx.remember(f"command {n}", [])
    summary = ctx.summary_for_prompt()
    assert "command 9" in summary and "command 5" not in summary and summary.count("\n") == 3
