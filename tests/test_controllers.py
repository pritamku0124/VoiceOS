"""Tests for Windows control (Phase 6).

Almost everything uses FakeWin32, which records what WOULD have happened, so tests never
open apps or move your real windows. Only the "read-only" tests at the bottom call real
Windows functions, and they only read (list windows, Start menu, battery).
"""

import pytest

from actions.action_registry import ACTIONS
from controllers.application_controller import ApplicationController
from controllers.browser_controller import search_url
from controllers.window_controller import FocusTracker, WindowController, friendly_name
from core.action_manager import Controllers, build_router
from integrations.windows.win32_api import WindowInfo
from integrations.windows.windows_apps import AppCatalog, AppNotFoundError, InstalledApp

OWN_PID = 999  # pretend VoiceOS runs as process 999


class FakeWin32:
    SW_MINIMIZE, SW_MAXIMIZE, SW_RESTORE = 6, 3, 9

    def __init__(self):
        self.windows = [
            WindowInfo(1, "VoiceOS 0.6.0", OWN_PID, "python.exe", False, False),
            WindowInfo(2, "Inbox - Gmail - Google Chrome", 10, "chrome.exe", False, False),
            WindowInfo(3, "main.py - VoiceOS - Visual Studio Code", 11, "Code.exe", False, True),
            WindowInfo(4, "WhatsApp", 12, "WhatsApp.Root.exe", True, False),
        ]
        self.foreground = 2
        self.calls = []
        self.battery = (88, True)

    # reading
    def list_windows(self): return list(self.windows)
    def foreground_window(self): return self.foreground
    def window_pid(self, hwnd): return next(w.pid for w in self.windows if w.hwnd == hwnd)
    def is_window(self, hwnd): return any(w.hwnd == hwnd for w in self.windows)
    def describe(self, hwnd): return next(w for w in self.windows if w.hwnd == hwnd)
    def cursor_position(self): return (500, 500)
    def battery_status(self): return self.battery

    # acting (recorded)
    def show_window(self, hwnd, cmd): self.calls.append(("show", hwnd, cmd))
    def bring_to_front(self, hwnd): self.calls.append(("front", hwnd)); self.foreground = hwnd; return True
    def request_close(self, hwnd): self.calls.append(("close", hwnd))
    def press_keys(self, keys): self.calls.append(("keys", tuple(keys)))
    def type_unicode(self, text): self.calls.append(("type", text))
    def click(self, button, times=1): self.calls.append(("click", button, times))
    def scroll(self, notches): self.calls.append(("scroll", notches))
    def move_cursor(self, x, y): self.calls.append(("move", x, y))
    def lock_workstation(self): self.calls.append(("lock",))


APPS = [InstalledApp("WhatsApp", "5319275A.WhatsAppDesktop_cv1g1gvanyjgm!App"),
        InstalledApp("Google Chrome", "Chrome"), InstalledApp("Visual Studio Code", "Microsoft.VisualStudioCode"),
        InstalledApp("Notepad", "Microsoft.WindowsNotepad_8wekyb3d8bbwe!App"),
        InstalledApp("Visual Studio Installer", "VSInstaller"), InstalledApp("Settings", "windows.settings")]


@pytest.fixture
def env():
    """A complete set of controllers wired to fakes. Returns (api, launched, opened_urls, controllers)."""
    from controllers.keyboard_controller import KeyboardController
    from controllers.media_controller import MediaController
    from controllers.mouse_controller import MouseController
    from controllers.system_controller import SystemController
    from controllers.browser_controller import BrowserController

    api = FakeWin32()
    windows = WindowController(api, FocusTracker(api, own_pid=OWN_PID))
    launched, opened = [], []
    c = Controllers(
        apps=ApplicationController(AppCatalog(APPS), windows, launcher=launched.append), windows=windows,
        keyboard=KeyboardController(windows), mouse=MouseController(windows),
        browser=BrowserController(opener=opened.append), media=MediaController(api),
        system=SystemController(api, opener=opened.append),
    )
    return api, launched, opened, c


def run(c, intent_action, confirm=lambda q: True, **params):
    from actions.action_validator import validate_intent

    return build_router(c, confirm=confirm).route(validate_intent(intent_action, params))


# ---- finding apps ------------------------------------------------------------------------------
@pytest.mark.parametrize("spoken, expected", [
    ("WhatsApp", "WhatsApp"), ("whats app", "WhatsApp"), ("whatapp", "WhatsApp"), ("chrome", "Google Chrome"),
    ("visual studio code", "Visual Studio Code"), ("notepad", "Notepad"),
])
def test_catalog_matching(spoken, expected):
    assert AppCatalog(APPS).find(spoken).name == expected


def test_app_that_is_not_installed():
    with pytest.raises(AppNotFoundError, match="couldn't find an app called Spotify"):
        AppCatalog(APPS).find("Spotify")


def test_weak_match_is_suggested_not_opened():
    # Measured: "notebook" vs "notepad" similarity = 0.53, below the 0.75 needed to open it.
    with pytest.raises(AppNotFoundError, match="Did you mean Notepad"):
        AppCatalog(APPS).find("note book")


def test_catalog_loads_only_once():
    calls = []
    catalog = AppCatalog(loader=lambda: calls.append(1) or APPS)
    catalog.find("notepad"), catalog.find("chrome")
    assert calls == [1]


# ---- applications ---------------------------------------------------------------------------
def test_open_whatsapp_launches_the_right_app(env):
    api, launched, _, c = env
    result = run(c, "OPEN_APPLICATION", app="WhatsApp")
    assert result.status == "done" and result.message == "Opening WhatsApp."
    assert launched == [APPS[0]]


def test_open_vs_code_nickname(env):
    _, launched, _, c = env
    assert run(c, "OPEN_APPLICATION", app="vs code").message == "Opening Visual Studio Code."


def test_open_missing_app_fails_politely(env):
    _, launched, _, c = env
    result = run(c, "OPEN_APPLICATION", app="Spotify")
    assert result.status == "failed" and "couldn't find an app called Spotify" in result.message
    assert launched == []


def test_switch_to_app(env):
    api, _, _, c = env
    assert run(c, "SWITCH_APPLICATION", app="WhatsApp").message == "Switched to WhatsApp."
    assert ("front", 4) in api.calls


def test_list_running_apps_excludes_voiceos(env):
    _, _, _, c = env
    assert run(c, "LIST_APPLICATIONS").message == "3 open: Google Chrome, Visual Studio Code, WhatsApp."


# ---- windows & "this window" ----------------------------------------------------------------
def test_minimize_named_window(env):
    api, _, _, c = env
    assert run(c, "MINIMIZE_WINDOW", target="Google Chrome").message == "Google Chrome minimized."
    assert ("show", 2, FakeWin32.SW_MINIMIZE) in api.calls


def test_this_window_means_your_window_not_voiceos(env):
    api, _, _, c = env
    c.windows.tracker.poll()  # Chrome (2) is active...
    api.foreground = 1  # ...then you click VoiceOS's mic, so VoiceOS is active
    run(c, "MINIMIZE_WINDOW", target="current")
    assert ("show", 2, FakeWin32.SW_MINIMIZE) in api.calls  # Chrome, not VoiceOS
    assert all(call[1] != 1 for call in api.calls if call[0] == "show")


def test_typing_goes_to_your_window(env):
    api, _, _, c = env
    c.windows.tracker.poll()
    api.foreground = 1  # VoiceOS in front
    run(c, "TYPE_TEXT", text="hello world")
    assert api.calls == [("front", 2), ("type", "hello world")]  # Chrome focused FIRST, then typed


def test_snap_uses_windows_shortcut(env):
    api, _, _, c = env
    run(c, "SNAP_WINDOW", target="Google Chrome", position="left")
    assert api.calls[-1] == ("keys", ("win", "left"))


# ---- confirmations ----------------------------------------------------------------------------
def test_closing_an_app_asks_first_and_respects_no(env):
    api, _, _, c = env
    questions = []
    result = run(c, "CLOSE_APPLICATION", confirm=lambda q: questions.append(q) or False, app="Google Chrome")
    assert questions == ["Do you want me to close Google Chrome?"]
    assert result.status == "cancelled" and result.message == "Okay, I won't close Google Chrome."
    assert not any(call[0] == "close" for call in api.calls)


def test_closing_after_yes(env):
    api, _, _, c = env
    result = run(c, "CLOSE_APPLICATION", confirm=lambda q: True, app="Google Chrome")
    assert result.status == "done" and ("close", 2) in api.calls


def test_without_a_way_to_ask_risky_actions_never_run(env):
    api, _, _, c = env
    result = build_router(c, confirm=None).route(__import__("actions.action_validator", fromlist=["x"]).validate_intent(
        "LOCK_SCREEN", {}))
    assert result.status == "cancelled" and ("lock",) not in api.calls


def test_high_risk_always_asks_even_if_medium_questions_are_off(env):
    api, _, _, c = env
    from actions.action_validator import validate_intent

    asked = []
    router = build_router(c, confirm=lambda q: asked.append(q) or True, confirm_medium=False)
    router.route(validate_intent("CLOSE_APPLICATION", {"app": "Google Chrome"}))  # MEDIUM: no question
    router.route(validate_intent("LOCK_SCREEN", {}))  # HIGH: question
    assert asked == ["Do you want me to lock the computer?"]


# ---- browser, media, system -------------------------------------------------------------------
def test_search_url_is_encoded():
    assert search_url("c++ & you", "youtube") == "https://www.youtube.com/results?search_query=c%2B%2B+%26+you"


def test_web_search_opens_browser(env):
    _, _, opened, c = env
    assert run(c, "WEB_SEARCH", query="embedded systems", site="youtube").message == \
        "Searching Youtube for embedded systems."
    assert opened == ["https://www.youtube.com/results?search_query=embedded+systems"]


def test_volume_down_presses_key_five_times_for_ten_percent(env):
    api, _, _, c = env
    run(c, "CHANGE_VOLUME", direction="down")
    assert api.calls.count(("keys", ("volume_down",))) == 5


def test_battery(env):
    _, _, _, c = env
    assert run(c, "GET_BATTERY").message == "The battery is at 88 percent and charging."


def test_settings_page_uses_fixed_link(env):
    _, _, opened, c = env
    run(c, "OPEN_SETTINGS", page="bluetooth")
    assert opened == ["ms-settings:bluetooth"]


def test_every_phase_6_action_has_a_handler(env):
    _, _, _, c = env
    router = build_router(c)
    missing = [a.name for a in ACTIONS if a.phase <= 6 and a.name not in router.handlers]
    assert missing == []


def test_dry_run_router_executes_nothing():
    from actions.action_validator import validate_intent

    result = build_router(None).route(validate_intent("OPEN_APPLICATION", {"app": "WhatsApp"}))
    assert result.status == "planned"


def test_friendly_name():
    assert friendly_name(WindowInfo(1, "Inbox - Gmail - Google Chrome", 1, "chrome.exe", False, False)) == "Google Chrome"


# ---- whole assistant with fakes --------------------------------------------------------------
def test_assistant_runs_the_project_brief_example(env):
    from ai.intent_recognition import IntentRecognizer
    from core.assistant import Assistant

    api, launched, _, c = env
    response = Assistant(IntentRecognizer(), router=build_router(c)).handle("open whatsapp and minimize chrome")
    assert response.reply == "Opening WhatsApp. Google Chrome minimized."
    assert response.status == "done" and launched == [APPS[0]] and ("show", 2, FakeWin32.SW_MINIMIZE) in api.calls


# ---- real Windows, READ-ONLY ------------------------------------------------------------------
def test_real_window_list_is_readable():
    from integrations.windows import win32_api

    windows = win32_api.list_windows()
    assert isinstance(windows, list) and all(isinstance(w, WindowInfo) for w in windows)


def test_real_start_menu_has_common_apps():
    from integrations.windows.windows_apps import load_start_apps

    names = {a.name for a in load_start_apps()}
    assert {"Settings", "File Explorer"} <= names


def test_real_battery_reading():
    from integrations.windows import win32_api

    percent, plugged = win32_api.battery_status()
    assert percent is None or 0 <= percent <= 100
    assert isinstance(plugged, bool)
