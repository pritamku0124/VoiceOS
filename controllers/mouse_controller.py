"""Click, scroll and move the real mouse pointer."""

from __future__ import annotations

from controllers.window_controller import WindowController

DIRECTIONS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


class MouseController:
    def __init__(self, windows: WindowController):
        self.windows = windows
        self.api = windows.api

    def click(self, button: str = "left") -> None:
        # If VoiceOS is in front (you just clicked its mic), the click would land on VoiceOS.
        self.windows.focus_current()
        if button == "double":
            self.api.click("left", times=2)
        else:
            self.api.click(button)

    def scroll(self, direction: str, amount: int) -> None:
        """Scrolls whatever is under the pointer, like the wheel. amount = wheel notches."""
        self.windows.focus_current()
        self.api.scroll(amount if direction == "up" else -amount)

    def move(self, direction: str, distance: int) -> None:
        x, y = self.api.cursor_position()
        dx, dy = DIRECTIONS[direction]
        self.api.move_cursor(x + dx * distance, y + dy * distance)
