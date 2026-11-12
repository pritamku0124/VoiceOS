"""Battery, Windows Settings pages, and locking the PC."""

from __future__ import annotations

import os

from integrations.windows import win32_api as default_api

# "ms-settings:" links open a specific page of the Settings app.
SETTINGS_PAGES = {
    "home": "ms-settings:", "display": "ms-settings:display", "sound": "ms-settings:sound",
    "bluetooth": "ms-settings:bluetooth", "wifi": "ms-settings:network-wifi", "apps": "ms-settings:appsfeatures",
    "privacy": "ms-settings:privacy", "update": "ms-settings:windowsupdate",
}


class SystemController:
    def __init__(self, api=default_api, opener=os.startfile):
        self.api = api
        self._open = opener

    def battery(self) -> str:
        percent, plugged_in = self.api.battery_status()
        if percent is None:
            return "This computer doesn't report a battery."
        charging = " and charging" if plugged_in else ""
        return f"The battery is at {percent} percent{charging}."

    def open_settings(self, page: str = "home") -> None:
        self._open(SETTINGS_PAGES[page])  # fixed list: no user text reaches the URI

    def lock(self) -> None:
        self.api.lock_workstation()
