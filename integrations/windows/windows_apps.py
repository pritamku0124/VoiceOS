"""Finds installed apps (the Start menu list) and launches them.

Where the list comes from:
    PowerShell's  Get-StartApps  returns every Start-menu entry with a Name and an AppID,
    e.g.  WhatsApp -> 5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App   (a Store app)
          Google Chrome -> Chrome                                 (a classic .exe app)
    Opening  shell:AppsFolder\\<AppID>  launches it exactly like clicking it in Start.

Safety by design:
    VoiceOS can only launch entries from YOUR Start menu, never an arbitrary file path
    or command. "open format c:" simply finds no matching app.
"""

from __future__ import annotations

import difflib
import json
import logging
import os
import re
import subprocess
import threading
from dataclasses import dataclass

from utils.exceptions import VoiceOSError

logger = logging.getLogger(__name__)


class AppNotFoundError(VoiceOSError):
    """No installed app matches the spoken name."""


@dataclass(frozen=True)
class InstalledApp:
    name: str
    app_id: str


def _simplify(name: str) -> str:
    """'Microsoft Visual Studio Code' / 'visual-studio code' -> 'visualstudiocode'."""
    name = name.lower()
    name = re.sub(r"^(microsoft|google|the)\s+", "", name)
    return re.sub(r"[^a-z0-9]", "", name)


def load_start_apps() -> list[InstalledApp]:
    """Ask Windows for the Start-menu app list (~1 s, so the result is cached by AppCatalog)."""
    command = "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"
    # CREATE_NO_WINDOW: don't flash a black console window on screen.
    done = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", command],
                          capture_output=True, text=True, encoding="utf-8", timeout=30,
                          creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if done.returncode != 0:
        raise VoiceOSError(f"Could not read the Start menu app list: {done.stderr.strip()[:200]}")
    data = json.loads(done.stdout or "[]")
    if isinstance(data, dict):  # a single app comes back as an object, not a list
        data = [data]
    return [InstalledApp(item["Name"], item["AppID"]) for item in data if item.get("Name") and item.get("AppID")]


class AppCatalog:
    """Installed apps with fuzzy name matching. Loaded once, in the background."""

    def __init__(self, apps: list[InstalledApp] | None = None, loader=load_start_apps):
        self._apps = apps
        self._loader = loader
        self._lock = threading.Lock()

    def preload(self) -> None:
        threading.Thread(target=self.apps, name="AppCatalogLoad", daemon=True).start()

    def apps(self) -> list[InstalledApp]:
        with self._lock:  # if two threads ask at once, load only once
            if self._apps is None:
                self._apps = self._loader()
                logger.info("Found %d Start-menu apps", len(self._apps))
            return self._apps

    def refresh(self) -> None:
        with self._lock:
            self._apps = None

    def find(self, spoken: str) -> InstalledApp:
        """Best match for a spoken name, or AppNotFoundError with suggestions."""
        apps = self.apps()
        wanted = _simplify(spoken)
        if not wanted:
            raise AppNotFoundError("Which app should I open?")
        by_key = {_simplify(a.name): a for a in apps}

        if wanted in by_key:  # 1. exact: "notepad"
            return by_key[wanted]
        starts = [a for k, a in by_key.items() if k.startswith(wanted)]  # 2. "visual" -> "Visual Studio Code"
        if starts:
            return min(starts, key=lambda a: len(a.name))
        contains = [a for k, a in by_key.items() if wanted in k and len(wanted) >= 4]  # 3. "studio code"
        if contains:
            return min(contains, key=lambda a: len(a.name))
        close = difflib.get_close_matches(wanted, list(by_key), n=1, cutoff=0.75)  # 4. misheard: "whatapp"
        if close:
            return by_key[close[0]]

        hints = difflib.get_close_matches(wanted, list(by_key), n=3, cutoff=0.5)
        suggestion = f" Did you mean {', '.join(by_key[h].name for h in hints)}?" if hints else ""
        raise AppNotFoundError(f"I couldn't find an app called {spoken}.{suggestion}")


def launch(app: InstalledApp) -> None:
    """Open the app the same way the Start menu does."""
    os.startfile(f"shell:AppsFolder\\{app.app_id}")  # noqa: S606 - AppID comes from Windows' own list
