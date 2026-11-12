"""Tests for routing, replies, and the whole Assistant (with a fake AI)."""

import json

import pytest

from actions.action_schema import Intent
from ai.intent_recognition import IntentRecognizer
from ai.llm_client import LLMClient, LLMError
from core.assistant import Assistant
from core.command_router import CAPABILITIES, CommandRouter


class FakeLLM(LLMClient):
    """Pretends to be Ollama: returns a canned reply and records what it was asked."""

    model = "fake"

    def __init__(self, reply: dict | str | Exception, available=True):
        self.reply, self.available, self.calls = reply, available, []

    def is_available(self):
        return self.available

    def chat(self, messages, json_output=True):
        self.calls.append(messages)
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


def assistant(llm=None, history=None):
    return Assistant(IntentRecognizer(llm), history=history)


# ---- router ----------------------------------------------------------------------------
def test_information_actions_run_now():
    router = CommandRouter()
    result = router.route(Intent("GET_TIME"))
    assert result.status == "done" and result.message.startswith("It's ") and " 0" not in result.message
    assert router.route(Intent("HELP")).message == CAPABILITIES


def test_windows_actions_are_planned_not_executed():
    result = CommandRouter().route(Intent("OPEN_APPLICATION", {"app": "WhatsApp"}))
    assert result.status == "planned" and result.description == "open WhatsApp"


def test_failing_handler_is_contained():
    router = CommandRouter()
    router.register("MUTE", lambda i: 1 / 0)
    result = router.route(Intent("MUTE"))
    assert result.status == "failed" and result.message == "Sorry, something went wrong while trying to mute."


# ---- whole assistant ----------------------------------------------------------------------
def test_rules_handle_common_commands_without_ai():
    llm = FakeLLM({"actions": []})
    response = assistant(llm).handle("open whatsapp and minimize chrome")
    assert response.recognition.source == "rules" and llm.calls == []  # AI never asked
    # This bare router has no Windows handlers (like dry-run mode), so the actions are only "planned".
    assert response.reply == "I understood: open WhatsApp, then minimize Google Chrome, but I can't do that yet."
    assert response.status == "planned"


def test_ai_is_used_when_rules_dont_match():
    llm = FakeLLM({"actions": [{"action": "COPY_FILE",
                                "params": {"source": "Downloads\\report.pdf", "destination": "Documents"}}]})
    response = assistant(llm).handle("copy the report from downloads into my documents")
    assert response.recognition.source == "ai"
    assert [str(i) for i in response.recognition.intents] == [
        "COPY_FILE(source='Downloads\\\\report.pdf', destination='Documents')"]
    system_prompt = llm.calls[0][0]["content"]
    assert "COPY_FILE(source: text, destination: text)" in system_prompt  # allowlist is in the prompt


def test_ai_answer_is_spoken_when_no_action():
    llm = FakeLLM({"actions": [], "answer": "Python is a programming language."})
    response = assistant(llm).handle("what is python")
    assert response.reply == "Python is a programming language." and response.status == "answered"


def test_ai_cannot_sneak_in_forbidden_actions():
    llm = FakeLLM({"actions": [{"action": "RUN_POWERSHELL", "params": {"script": "Remove-Item C:\\ -Recurse"}}],
                   "answer": ""})
    response = assistant(llm).handle("do something sneaky")
    assert response.recognition.intents == [] and response.results == []
    assert "not an allowed action" in response.recognition.errors[0]


def test_knowledge_question_gets_the_answer_not_help():
    """Real model output for 'what is an embedded system': HELP + a good answer."""
    llm = FakeLLM({"actions": [{"action": "HELP", "params": {}}],
                   "answer": "An embedded system is a computer built into a device."})
    response = assistant(llm).handle("what is an embedded system")
    assert response.reply == "An embedded system is a computer built into a device."


def test_answer_next_to_actions_is_not_spoken():
    """Real model output: CHANGE_VOLUME + 'The sound has been turned down' - before anything ran!"""
    llm = FakeLLM({"actions": [{"action": "CHANGE_VOLUME", "params": {"direction": "down"}}],
                   "answer": "The sound has been turned down a bit."})
    response = assistant(llm).handle("make the sound a bit quieter")
    assert "has been" not in response.reply and response.reply.startswith("I understood: turn the volume down")


def test_rejected_action_answer_is_discarded():
    """Real model output: invented GET_SCREENSHOT + "Here's a screenshot of your screen." (false claim)."""
    llm = FakeLLM({"actions": [{"action": "GET_SCREENSHOT", "params": {}}], "answer": "Here's a screenshot of your screen."})
    response = assistant(llm).handle("show me what is on my screen")
    assert response.reply == "Sorry, I can't do that."


def test_without_ai_unknown_requests_get_a_helpful_reply():
    response = assistant(FakeLLM({}, available=False)).handle("explain quantum physics to me")
    assert response.recognition.source == "none"
    assert response.reply.startswith("Sorry, I didn't understand that.") and "AI model" in response.reply


def test_ai_errors_are_handled():
    response = assistant(FakeLLM(LLMError("timed out"))).handle("explain quantum physics")
    assert response.status == "not_understood" and response.recognition.errors == ["timed out"]


def test_follow_up_uses_conversation_context():
    a = assistant()
    a.handle("open spotify")
    response = a.handle("minimize it")
    assert str(response.recognition.intents[0]) == "MINIMIZE_WINDOW(target='Spotify')"


def test_time_question_is_answered_now():
    response = assistant().handle("what time is it")
    assert response.status == "done" and response.reply.startswith("It's ")


def test_submit_runs_in_background_and_emits(qt_app):
    from tests.test_wake_word import wait_until

    a = assistant()
    responses, busy = [], []
    a.response_ready.connect(responses.append)
    a.busy_changed.connect(busy.append)
    a.submit("hello", mode="typed")
    assert wait_until(lambda: responses and busy == [True, False], timeout=5)
    assert responses[0].reply == "Hello! How can I help you?" and responses[0].mode == "typed"
    a.shutdown()
