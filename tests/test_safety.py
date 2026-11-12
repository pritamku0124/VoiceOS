"""Tests for the safety rules applied to AI plans (safety/command_filter.py).

Each case below is something the REAL local model (qwen2.5:1.5b) actually produced
during Phase 5 testing. Phase 8 extends this file with confirmations and risk levels.
"""

from actions.action_schema import Intent
from safety.command_filter import filter_ai_plan


def test_ai_cannot_type_words_you_did_not_say():
    plan = [Intent("OPEN_APPLICATION", {"app": "WhatsApp"}), Intent("TYPE_TEXT", {"text": "Hello Rahul, I am here."})]
    kept, removed = filter_ai_plan(plan, "send a message to rahul on whatsapp saying hello")
    assert [i.action for i in kept] == ["OPEN_APPLICATION"]
    assert "didn't dictate" in removed[0]


def test_ai_may_type_what_you_dictated():
    plan = [Intent("TYPE_TEXT", {"text": "Dear team, the build is green."})]
    kept, removed = filter_ai_plan(plan, "write dear team the build is green in the editor")
    assert kept == plan and removed == []


def test_ai_cannot_open_command_shells():
    for app in ("Command Prompt", "PowerShell", "Terminal", "Registry Editor"):
        kept, removed = filter_ai_plan([Intent("OPEN_APPLICATION", {"app": app})], "run the command format c drive")
        assert kept == [] and "may not open" in removed[0], app


def test_ordinary_ai_plans_pass_untouched():
    plan = [Intent("OPEN_APPLICATION", {"app": "Spotify"}), Intent("MINIMIZE_WINDOW", {"target": "Google Chrome"})]
    assert filter_ai_plan(plan, "fire up spotify and make chrome smaller") == (plan, [])
