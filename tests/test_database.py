"""Tests for the SQLite command history."""

from core.assistant import Assistant
from ai.intent_recognition import IntentRecognizer
from services.database_service import Database
from services.history_service import HistoryService


def make_history(tmp_path, enabled=True):
    return HistoryService(Database(tmp_path / "test.db"), enabled=enabled)


def test_add_and_read_back(tmp_path):
    history = make_history(tmp_path)
    history.add("open notepad", "voice", "rules", [{"action": "OPEN_APPLICATION"}], "I understood...", "planned")
    history.add("hello", "typed", "rules", [], "Hello!", "done")
    entries = history.recent()
    assert [e.input_text for e in entries] == ["hello", "open notepad"]  # newest first
    assert entries[1].intents == [{"action": "OPEN_APPLICATION"}]


def test_search(tmp_path):
    history = make_history(tmp_path)
    for text in ("open notepad", "open chrome", "what time is it"):
        history.add(text, "voice", "rules", [], "", "done")
    assert [e.input_text for e in history.recent(search="open")] == ["open chrome", "open notepad"]


def test_sql_injection_is_harmless(tmp_path):
    history = make_history(tmp_path)
    evil = "x'); DROP TABLE command_history; --"
    history.add(evil, "typed", "none", [], "", "not_understood")
    assert history.recent(search=evil)[0].input_text == evil  # stored as plain text, table still there


def test_disabled_history_saves_nothing(tmp_path):
    history = make_history(tmp_path, enabled=False)
    history.add("secret", "voice", "rules", [], "", "done")
    assert history.recent() == []


def test_assistant_records_every_request(tmp_path):
    history = make_history(tmp_path)
    assistant = Assistant(IntentRecognizer(), history=history)
    assistant.handle("open whatsapp and minimize chrome", mode="typed")
    entry = history.recent()[0]
    assert entry.input_mode == "typed" and entry.source == "rules" and entry.status == "planned"
    assert [i["action"] for i in entry.intents] == ["OPEN_APPLICATION", "MINIMIZE_WINDOW"]


def test_history_survives_restart(tmp_path):
    make_history(tmp_path).add("persist me", "voice", "rules", [], "", "done")
    assert make_history(tmp_path).recent()[0].input_text == "persist me"
