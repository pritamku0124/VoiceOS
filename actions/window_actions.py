"""Handlers for MINIMIZE/MAXIMIZE/RESTORE/CLOSE/SNAP_WINDOW."""

from __future__ import annotations

from actions.action_schema import Intent
from controllers.window_controller import friendly_name


def register(router, c) -> None:
    def simple(method: str, done: str):
        def handler(i: Intent) -> str:
            window = getattr(c.windows, method)(i.params.get("target"))
            return f"{friendly_name(window)} {done}."
        return handler

    def snap(i: Intent) -> str:
        window = c.windows.snap(i.params.get("target"), i.params["position"])
        return f"Snapped {friendly_name(window)} to the {i.params['position']}."

    router.register("MINIMIZE_WINDOW", simple("minimize", "minimized"))
    router.register("MAXIMIZE_WINDOW", simple("maximize", "maximized"))
    router.register("RESTORE_WINDOW", simple("restore", "restored"))
    router.register("CLOSE_WINDOW", simple("close", "is closing"))
    router.register("SNAP_WINDOW", snap)
