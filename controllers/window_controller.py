"""Finds and manipulates windows: minimise, maximise, restore, close, snap, focus.

"This window" problem:
    When you CLICK VoiceOS's mic, VoiceOS becomes the active window. "Minimise this
    window" must not minimise VoiceOS itself. FocusTracker checks the active window a
    few times per second and remembers the last one that ISN'T VoiceOS - that's what
    "current" / "this window" means, and where typing and clicks are sent.
"""

from __future__ import annotations

import logging
import os
import re
import threading

from integrations.windows import win32_api as default_api
from integrations.windows.win32_api import WindowInfo
from utils.exceptions import VoiceOSError

logger = logging.getLogger(__name__)


class WindowNotFoundError(VoiceOSError):
    pass


def simplify(name: str) -> str:
    name = re.sub(r"^(microsoft|google|the)\s+", "", name.lower())
    return re.sub(r"[^a-z0-9]", "", name)


class FocusTracker:
    """Remembers the most recent active window that doesn't belong to VoiceOS."""

    def __init__(self, api=default_api, own_pid: int | None = None, interval: float = 0.4):
        self.api = api
        self.own_pid = own_pid if own_pid is not None else os.getpid()
        self.interval = interval
        self._last: int | None = None
        self._stop = threading.Event()

    def start(self) -> None:
        threading.Thread(target=self._run, name="FocusTracker", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def poll(self) -> None:
        hwnd = self.api.foreground_window()
        if hwnd and self.api.window_pid(hwnd) != self.own_pid:
            self._last = hwnd

    def _run(self) -> None:
        while not self._stop.wait(self.interval):
            try:
                self.poll()
            except OSError:
                pass

    def last_external(self) -> int | None:
        self.poll()  # the active window right now may already be the right one
        if self._last and self.api.is_window(self._last):
            return self._last
        return None


class WindowController:
    def __init__(self, api=default_api, tracker: FocusTracker | None = None):
        self.api = api
        self.tracker = tracker or FocusTracker(api)

    # ---- finding ------------------------------------------------------------------------------
    def find_all(self, name: str) -> list[WindowInfo]:
        """Windows whose program or title matches the name, front-most first."""
        wanted = simplify(name)
        if not wanted:
            return []
        matches = []
        for window in self.api.list_windows():
            process = simplify(window.process.rsplit(".", 1)[0])  # "chrome.exe" -> "chrome"
            title = simplify(window.title)
            # "Google Chrome" matches process chrome.exe; "Visual Studio Code" matches the title suffix.
            if wanted == process or wanted in title or (len(process) >= 4 and process in wanted):
                matches.append(window)
        return matches

    def find(self, name: str) -> WindowInfo:
        matches = self.find_all(name)
        if not matches:
            raise WindowNotFoundError(f"I can't find an open {name} window.")
        return matches[0]

    def resolve(self, target: str | None) -> WindowInfo:
        """'current' -> the window you were using; otherwise find it by name."""
        if target in (None, "", "current"):
            hwnd = self.tracker.last_external()
            if hwnd is None:
                raise WindowNotFoundError("I'm not sure which window you mean. Click it first, or say its name.")
            return self.api.describe(hwnd)
        return self.find(target)

    # ---- acting -------------------------------------------------------------------------------
    def minimize(self, target: str | None) -> WindowInfo:
        window = self.resolve(target)
        self.api.show_window(window.hwnd, self.api.SW_MINIMIZE)
        return window

    def maximize(self, target: str | None) -> WindowInfo:
        window = self.resolve(target)
        self.api.show_window(window.hwnd, self.api.SW_MAXIMIZE)
        self.api.bring_to_front(window.hwnd)
        return window

    def restore(self, target: str | None) -> WindowInfo:
        window = self.resolve(target)
        self.api.show_window(window.hwnd, self.api.SW_RESTORE)
        self.api.bring_to_front(window.hwnd)
        return window

    def focus(self, target: str | None) -> WindowInfo:
        window = self.resolve(target)
        self.api.bring_to_front(window.hwnd)
        return window

    def close(self, target: str | None) -> WindowInfo:
        window = self.resolve(target)
        self.api.request_close(window.hwnd)
        return window

    def snap(self, target: str | None, position: str) -> WindowInfo:
        """Uses Windows' own snap shortcut (Win + arrow) on the focused window."""
        window = self.focus(target)
        self.api.press_keys(["win", position if position in ("left", "right", "up", "down") else
                             {"top": "up", "bottom": "down"}[position]])
        return window

    def focus_current(self) -> None:
        """Before typing/clicking: make sure the keys go to YOUR window, not to VoiceOS."""
        hwnd = self.tracker.last_external()
        if hwnd and self.api.foreground_window() != hwnd:
            self.api.bring_to_front(hwnd)


def friendly_name(window: WindowInfo) -> str:
    """'Inbox - Gmail - Google Chrome' -> 'Google Chrome'; 'WhatsApp' -> 'WhatsApp'."""
    parts = [p.strip() for p in re.split(r"\s+[-–—]\s+", window.title) if p.strip()]
    return parts[-1] if parts else window.process
