"""Turns the AI's reply (text) into validated Intents - treating it as untrusted input.

The model is asked for:  {"actions": [{"action": "...", "params": {...}}], "answer": "..."}
but small models sometimes add ```json fences, chatter before the JSON, or invent
actions. This parser:
    1. finds the JSON object in the text,
    2. checks its shape,
    3. sends EVERY action through action_validator (the allowlist),
    4. keeps the valid ones, records why the others were rejected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from actions.action_schema import Intent
from actions.action_validator import ActionValidationError, validate_intent

MAX_ACTIONS = 5  # a single spoken sentence never needs more; protects against runaway output
MAX_ANSWER_CHARS = 400


@dataclass
class ParsedReply:
    intents: list[Intent] = field(default_factory=list)
    answer: str = ""
    errors: list[str] = field(default_factory=list)


def _extract_json_object(text: str) -> dict:
    """Return the first {...} object in text (ignores ```json fences and surrounding chatter)."""
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in the reply")
    # raw_decode parses ONE value from the start position and tells us where it ended,
    # so trailing text after the closing brace doesn't cause an error.
    obj, _ = json.JSONDecoder().raw_decode(text[start:])
    if not isinstance(obj, dict):
        raise ValueError("reply is not a JSON object")
    return obj


def parse_llm_reply(text: str) -> ParsedReply:
    result = ParsedReply()
    try:
        data = _extract_json_object(text)
    except ValueError as exc:  # json.JSONDecodeError is a subclass of ValueError
        result.errors.append(f"Unreadable AI reply: {exc}")
        return result

    answer = data.get("answer", "")
    if isinstance(answer, str):
        result.answer = " ".join(answer.split())[:MAX_ANSWER_CHARS]

    actions = data.get("actions", [])
    if not isinstance(actions, list):
        result.errors.append("'actions' is not a list")
        return result
    if len(actions) > MAX_ACTIONS:
        result.errors.append(f"Too many actions ({len(actions)}); only the first {MAX_ACTIONS} were considered")
        actions = actions[:MAX_ACTIONS]

    for item in actions:
        if not isinstance(item, dict):
            result.errors.append(f"Ignored non-object action: {item!r}"[:200])
            continue
        try:
            result.intents.append(validate_intent(item.get("action"), item.get("params") or {}))
        except ActionValidationError as exc:
            result.errors.append(str(exc))
    return result
