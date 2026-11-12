"""Handlers for TYPE_TEXT, PRESS_KEY, KEYBOARD_SHORTCUT."""

from __future__ import annotations

from actions.action_schema import Intent

SAID = {"select_all": "Selected all", "copy": "Copied", "paste": "Pasted", "cut": "Cut", "undo": "Undone",
        "redo": "Redone", "save": "Saved", "find": "Opened find", "refresh": "Refreshed"}


def register(router, c) -> None:
    def type_text(i: Intent) -> str:
        c.keyboard.type_text(i.params["text"])
        return "Typed it."

    def press(i: Intent) -> str:
        c.keyboard.press(i.params["key"])
        return f"Pressed {i.params['key'].replace('_', ' ')}."

    def shortcut(i: Intent) -> str:
        c.keyboard.shortcut(i.params["shortcut"])
        return f"{SAID.get(i.params['shortcut'], 'Done')}."

    router.register("TYPE_TEXT", type_text)
    router.register("PRESS_KEY", press)
    router.register("KEYBOARD_SHORTCUT", shortcut)
