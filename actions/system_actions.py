"""Handlers for GET_BATTERY, OPEN_SETTINGS, LOCK_SCREEN."""

from __future__ import annotations

from actions.action_schema import Intent


def register(router, c) -> None:
    def battery(i: Intent) -> str:
        return c.system.battery()

    def settings(i: Intent) -> str:
        page = i.params.get("page", "home")
        c.system.open_settings(page)
        return "Opening Settings." if page == "home" else f"Opening {page} settings."

    def lock(i: Intent) -> str:
        c.system.lock()
        return "Locking the computer."

    router.register("GET_BATTERY", battery)
    router.register("OPEN_SETTINGS", settings)
    router.register("LOCK_SCREEN", lock)
