"""Type text, press keys and send shortcuts - into YOUR window, never into VoiceOS."""

from __future__ import annotations

from controllers.window_controller import WindowController

SHORTCUTS = {
    "copy": ["ctrl", "c"], "paste": ["ctrl", "v"], "cut": ["ctrl", "x"], "undo": ["ctrl", "z"],
    "redo": ["ctrl", "y"], "select_all": ["ctrl", "a"], "save": ["ctrl", "s"], "find": ["ctrl", "f"],
    "refresh": ["f5"],
    # browser
    "new_tab": ["ctrl", "t"], "close_tab": ["ctrl", "w"], "next_tab": ["ctrl", "tab"],
    "previous_tab": ["ctrl", "shift", "tab"], "back": ["alt", "left"], "forward": ["alt", "right"],
}


class KeyboardController:
    def __init__(self, windows: WindowController):
        self.windows = windows
        self.api = windows.api

    def type_text(self, text: str) -> None:
        self.windows.focus_current()
        self.api.type_unicode(text)

    def press(self, key: str) -> None:
        self.windows.focus_current()
        self.api.press_keys([key])

    def shortcut(self, name: str) -> None:
        self.windows.focus_current()
        self.api.press_keys(SHORTCUTS[name])
