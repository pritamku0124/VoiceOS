"""Media and volume keys - the same keys as on a multimedia keyboard.

Windows sends these to whatever is playing (Spotify, YouTube in a browser, ...).
Each volume key press changes the volume by 2%. Setting an EXACT level ("70 percent")
and mute/unmute need Windows' Core Audio API - that's Phase 7.
"""

from __future__ import annotations

from integrations.windows import win32_api as default_api

STEP_PERCENT = 2


class MediaController:
    def __init__(self, api=default_api):
        self.api = api

    def play_pause(self) -> None:
        self.api.press_keys(["media_play_pause"])

    def next(self) -> None:
        self.api.press_keys(["media_next"])

    def previous(self) -> None:
        self.api.press_keys(["media_previous"])

    def change_volume(self, direction: str, amount: int = 10) -> None:
        key = "volume_up" if direction == "up" else "volume_down"
        for _ in range(max(1, round(amount / STEP_PERCENT))):
            self.api.press_keys([key])
