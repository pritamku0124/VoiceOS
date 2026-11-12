"""Handlers for OPEN_APPLICATION, SWITCH_APPLICATION, CLOSE_APPLICATION, LIST_APPLICATIONS.

A handler receives a validated Intent and returns the sentence VoiceOS says afterwards.
Problems are raised as VoiceOSError subclasses with a message meant for the user
("I couldn't find an app called Spotify."), which the router speaks as-is.
"""

from __future__ import annotations

from actions.action_schema import Intent


def register(router, c) -> None:  # c = core.action_manager.Controllers
    def open_app(i: Intent) -> str:
        app = c.apps.open(i.params["app"])
        return f"Opening {app.name}."

    def switch_app(i: Intent) -> str:
        return f"Switched to {c.apps.switch(i.params['app'])}."

    def close_app(i: Intent) -> str:
        count = c.apps.close(i.params["app"])
        windows = "window" if count == 1 else f"{count} windows"
        return f"Closing {i.params['app']} ({windows})."

    def list_apps(i: Intent) -> str:
        names = c.apps.running()
        if not names:
            return "No other applications are open."
        shown = names[:6]
        more = f", and {len(names) - 6} more" if len(names) > 6 else ""
        return f"{len(names)} open: {', '.join(shown)}{more}."

    router.register("OPEN_APPLICATION", open_app)
    router.register("SWITCH_APPLICATION", switch_app)
    router.register("CLOSE_APPLICATION", close_app)
    router.register("LIST_APPLICATIONS", list_apps)
