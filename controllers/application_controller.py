"""Open, switch to, close, and list applications.

Opening uses the Start-menu catalog (integrations/windows/windows_apps.py).
Switching/closing work on open windows (controllers/window_controller.py).
"""

from __future__ import annotations

from ai.entity_extractor import APP_ALIASES
from controllers.window_controller import WindowController, WindowNotFoundError, friendly_name
from integrations.windows.windows_apps import AppCatalog, InstalledApp, launch


def canonical(name: str) -> str:
    """Spoken nickname -> official name: 'vs code' -> 'Visual Studio Code'."""
    return APP_ALIASES.get(name.strip().lower(), name.strip())


class ApplicationController:
    def __init__(self, catalog: AppCatalog, windows: WindowController, launcher=launch):
        self.catalog = catalog
        self.windows = windows
        self._launch = launcher

    def open(self, name: str) -> InstalledApp:
        app = self.catalog.find(canonical(name))
        self._launch(app)
        return app

    def switch(self, name: str) -> str:
        window = self.windows.find(canonical(name))
        self.windows.api.bring_to_front(window.hwnd)
        return friendly_name(window)

    def close(self, name: str) -> int:
        """Ask every window of the app to close. Returns how many were asked."""
        windows = self.windows.find_all(canonical(name))
        if not windows:
            raise WindowNotFoundError(f"{canonical(name)} isn't open.")
        for window in windows:
            self.windows.api.request_close(window.hwnd)
        return len(windows)

    def running(self) -> list[str]:
        """Friendly names of open apps (VoiceOS itself excluded), front-most first, no duplicates."""
        names: list[str] = []
        own_pid = self.windows.tracker.own_pid  # one source of truth for "which process is VoiceOS"
        for window in self.windows.api.list_windows():
            if window.pid == own_pid:
                continue
            name = friendly_name(window)
            if name not in names:
                names.append(name)
        return names
