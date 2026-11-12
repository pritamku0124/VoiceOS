"""Tests for understanding commands: rules, entities, validation, and parsing AI replies."""

import pytest

from actions.action_registry import ACTIONS, REGISTRY, catalog_for_prompt
from actions.action_validator import ActionValidationError, validate_intent
from ai.conversation_manager import ConversationContext
from ai.entity_extractor import normalize_location, website_url, words_to_number
from ai.intent_parser import parse_llm_reply
from ai.intent_recognition import RuleBasedRecognizer, normalize


def recognize(text, ctx=None):
    intents = RuleBasedRecognizer().recognize(text, ctx or ConversationContext())
    return None if intents is None else [(i.action, i.params) for i in intents]


# ---- rules: the commands from the project brief and more -------------------------------
@pytest.mark.parametrize(
    "said, expected",
    [
        ("open whatsapp", [("OPEN_APPLICATION", {"app": "WhatsApp"})]),
        ("Open Visual Studio Code", [("OPEN_APPLICATION", {"app": "Visual Studio Code"})]),
        ("please open notepad for me", [("OPEN_APPLICATION", {"app": "Notepad"})]),
        ("minimize the current window", [("MINIMIZE_WINDOW", {"target": "current"})]),
        ("minimize this window", [("MINIMIZE_WINDOW", {"target": "current"})]),
        ("switch to chrome", [("SWITCH_APPLICATION", {"app": "Google Chrome"})]),
        ("open whatsapp and minimize chrome",
         [("OPEN_APPLICATION", {"app": "WhatsApp"}), ("MINIMIZE_WINDOW", {"target": "Google Chrome"})]),
        ("open youtube and search for embedded systems",
         [("WEB_SEARCH", {"query": "embedded systems", "site": "youtube"})]),
        ("search youtube for embedded systems", [("WEB_SEARCH", {"query": "embedded systems", "site": "youtube"})]),
        ("search for salt and pepper", [("WEB_SEARCH", {"query": "salt and pepper", "site": "google"})]),
        ("google python tutorials", [("WEB_SEARCH", {"query": "python tutorials", "site": "google"})]),
        ("create a folder named electronics on my d drive",
         [("CREATE_FOLDER", {"name": "electronics", "location": "D:\\"})]),
        ("make a new folder called notes", [("CREATE_FOLDER", {"name": "notes", "location": "Desktop"})]),
        ("find my handos project", [("FIND_FILE", {"query": "handos project"})]),
        ("take a screenshot", [("TAKE_SCREENSHOT", {})]),
        ("increase the volume to seventy percent", [("SET_VOLUME", {"level": 70})]),
        ("set the volume to 35 percent", [("SET_VOLUME", {"level": 35})]),
        ("turn the volume down", [("CHANGE_VOLUME", {"direction": "down", "amount": 10})]),
        ("mute", [("MUTE", {})]),
        ("scroll down", [("MOUSE_SCROLL", {"direction": "down", "amount": 5})]),
        ("scroll up a lot", [("MOUSE_SCROLL", {"direction": "up", "amount": 15})]),
        ("double click", [("MOUSE_CLICK", {"button": "double"})]),
        ("type hello world", [("TYPE_TEXT", {"text": "hello world"})]),
        ("press enter", [("PRESS_KEY", {"key": "enter"})]),
        ("copy this", [("KEYBOARD_SHORTCUT", {"shortcut": "copy"})]),
        ("select all", [("KEYBOARD_SHORTCUT", {"shortcut": "select_all"})]),
        ("which applications are currently running", [("LIST_APPLICATIONS", {})]),
        ("close this window", [("CLOSE_WINDOW", {"target": "current"})]),
        ("close chrome", [("CLOSE_APPLICATION", {"app": "Google Chrome"})]),
        ("open github dot com", [("OPEN_WEBSITE", {"url": "https://github.com"})]),
        ("go back", [("BROWSER_BACK", {})]),
        ("open a new tab", [("NEW_TAB", {})]),
        ("lock the computer", [("LOCK_SCREEN", {})]),
        ("open bluetooth settings", [("OPEN_SETTINGS", {"page": "bluetooth"})]),
        ("what time is it", [("GET_TIME", {})]),
        ("what can you do", [("HELP", {})]),
        ("hello there", [("GREETING", {})]),
        ("snap this window to the left", [("SNAP_WINDOW", {"target": "current", "position": "left"})]),
    ],
)
def test_rules(said, expected):
    assert recognize(said) == expected


@pytest.mark.parametrize("said", [
    "explain what is displayed on my screen",  # needs AI (Phase 10)
    "open my handos project and explain how it works",
    "copy this file and move it to another folder",  # vague -> AI
    "show me what is on my screen",  # used to become SWITCH_APPLICATION('What Is On My Screen')
    "",
])
def test_rules_leave_hard_requests_to_the_ai(said):
    assert recognize(said) is None


def test_it_refers_to_the_last_app():
    ctx = ConversationContext()
    ctx.remember("open chrome", [validate_intent("OPEN_APPLICATION", {"app": "Google Chrome"})])
    assert recognize("minimize it", ctx) == [("MINIMIZE_WINDOW", {"target": "Google Chrome"})]


def test_normalize_removes_politeness_and_wake_words():
    assert normalize("Jarvis, please can you open notepad for me?".replace(",", "")) == "open notepad"


# ---- entities -------------------------------------------------------------------------
@pytest.mark.parametrize("words, number", [
    ("70", 70), ("seventy", 70), ("seventy five", 75), ("seventy-five percent", 75), ("one hundred", 100),
    ("a hundred", 100), ("half", 50), ("zero", 0), ("loud", None), ("", None),
])
def test_words_to_number(words, number):
    assert words_to_number(words) == number


@pytest.mark.parametrize("spoken, url", [
    ("youtube", "https://www.youtube.com"), ("github dot com", "https://github.com"),
    ("the youtube website", "https://www.youtube.com"), ("notepad", None),
])
def test_website_url(spoken, url):
    assert website_url(spoken) == url


@pytest.mark.parametrize("spoken, location", [
    ("my d drive", "D:\\"), ("drive c", "C:\\"), ("the desktop", "Desktop"), ("downloads folder", "Downloads"),
])
def test_normalize_location(spoken, location):
    assert normalize_location(spoken) == location


# ---- validator (the allowlist gate) ----------------------------------------------------
def test_unknown_action_is_rejected():
    with pytest.raises(ActionValidationError, match="not an allowed action"):
        validate_intent("RUN_SHELL_COMMAND", {"command": "format c:"})


@pytest.mark.parametrize("action, params, message", [
    ("OPEN_APPLICATION", {}, "needs 'app'"),
    ("OPEN_APPLICATION", {"app": "x", "args": "--evil"}, "does not accept"),
    ("SET_VOLUME", {"level": 150}, "between 0 and 100"),
    ("SET_VOLUME", {"level": "loud"}, "must be a number"),
    ("SET_VOLUME", {"level": True}, "must be a number"),
    ("MOUSE_SCROLL", {"direction": "sideways"}, "must be one of"),
    ("OPEN_WEBSITE", {"url": "file:///C:/Windows/System32"}, "web address"),
    ("OPEN_WEBSITE", {"url": "javascript:alert(1)"}, "web address"),  # was accepted before the fix!
    ("OPEN_WEBSITE", {"url": "mailto:someone@example.com"}, "web address"),
    ("OPEN_WEBSITE", {"url": "ms-settings:privacy"}, "web address"),
    ("OPEN_WEBSITE", {"url": "https://evil.com@bank.com"}, "web address"),  # "user@host" disguise
    ("TYPE_TEXT", {"text": "x" * 1001}, "too long"),
    ("OPEN_APPLICATION", {"app": "   "}, "needs 'app'"),
])
def test_invalid_params_are_rejected(action, params, message):
    with pytest.raises(ActionValidationError, match=message):
        validate_intent(action, params)


def test_validator_cleans_values():
    intent = validate_intent("open_application", {"app": "  What\x1bsApp\n  "})
    assert intent.action == "OPEN_APPLICATION" and intent.params == {"app": "WhatsApp"}
    assert validate_intent("SET_VOLUME", {"level": "70"}).params == {"level": 70}
    assert validate_intent("OPEN_WEBSITE", {"url": "github.com"}).params == {"url": "https://github.com"}


def test_every_action_is_documented():
    for spec in ACTIONS:
        assert spec.name.isupper() and spec.description and spec.summary, spec.name
    assert len(REGISTRY) == len(ACTIONS), "duplicate action names"
    assert "OPEN_APPLICATION(app: text)" in catalog_for_prompt()


# ---- parsing AI replies (untrusted input) ----------------------------------------------
def test_parse_good_reply():
    reply = parse_llm_reply('{"actions": [{"action": "OPEN_APPLICATION", "params": {"app": "Spotify"}}], "answer": ""}')
    assert [str(i) for i in reply.intents] == ["OPEN_APPLICATION(app='Spotify')"] and not reply.errors


def test_parse_reply_wrapped_in_chatter_and_fences():
    reply = parse_llm_reply('Sure!\n```json\n{"actions": [{"action": "MUTE", "params": {}}]}\n```\nDone.')
    assert [i.action for i in reply.intents] == ["MUTE"]


def test_parse_keeps_valid_actions_and_reports_invalid_ones():
    reply = parse_llm_reply('{"actions": [{"action": "MUTE"}, {"action": "DELETE_EVERYTHING", "params": {}},'
                            ' {"action": "SET_VOLUME", "params": {"level": 900}}]}')
    assert [i.action for i in reply.intents] == ["MUTE"]
    assert len(reply.errors) == 2


def test_parse_answer_only():
    reply = parse_llm_reply('{"actions": [], "answer": "Python is a programming language."}')
    assert reply.intents == [] and reply.answer == "Python is a programming language."


@pytest.mark.parametrize("garbage", ["", "I think you want Chrome", "[1, 2, 3]", '{"actions": "MUTE"}', "{broken"])
def test_parse_garbage_never_crashes(garbage):
    reply = parse_llm_reply(garbage)
    assert reply.intents == [] and reply.errors


def test_parse_limits_number_of_actions():
    many = ",".join('{"action": "MUTE"}' for _ in range(20))
    assert len(parse_llm_reply('{"actions": [' + many + "]}").intents) == 5
