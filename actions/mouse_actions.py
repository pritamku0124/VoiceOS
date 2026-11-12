"""Handlers for MOUSE_CLICK, MOUSE_SCROLL, MOUSE_MOVE."""

from __future__ import annotations

from actions.action_schema import Intent


def register(router, c) -> None:
    def click(i: Intent) -> str:
        button = i.params.get("button", "left")
        c.mouse.click(button)
        return "Double-clicked." if button == "double" else f"{button.capitalize()}-clicked."

    def scroll(i: Intent) -> str:
        c.mouse.scroll(i.params["direction"], i.params.get("amount", 5))
        return f"Scrolled {i.params['direction']}."

    def move(i: Intent) -> str:
        c.mouse.move(i.params["direction"], i.params.get("distance", 100))
        return f"Moved the mouse {i.params['direction']}."

    router.register("MOUSE_CLICK", click)
    router.register("MOUSE_SCROLL", scroll)
    router.register("MOUSE_MOVE", move)
