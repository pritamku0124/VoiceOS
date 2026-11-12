"""Handlers for media keys and volume up/down."""

from __future__ import annotations

from actions.action_schema import Intent


def register(router, c) -> None:
    def play_pause(i: Intent) -> str:
        c.media.play_pause()
        return "Done."  # Windows doesn't tell us whether it's now playing or paused

    def next_track(i: Intent) -> str:
        c.media.next()
        return "Next track."

    def previous_track(i: Intent) -> str:
        c.media.previous()
        return "Previous track."

    def volume(i: Intent) -> str:
        c.media.change_volume(i.params["direction"], i.params.get("amount", 10))
        return f"Volume {i.params['direction']}."

    router.register("MEDIA_PLAY_PAUSE", play_pause)
    router.register("MEDIA_NEXT", next_track)
    router.register("MEDIA_PREVIOUS", previous_track)
    router.register("CHANGE_VOLUME", volume)
