"""Thin Python wrappers around Windows' own functions (user32.dll, kernel32.dll, dwmapi.dll).

We use ctypes - part of Python itself - to call these DLL functions directly, instead
of installing pywin32. Fewer native packages = nothing for Smart App Control to block,
and you can see exactly which Windows functions VoiceOS uses.

Key ideas:
    HWND        "handle to a window": a number Windows uses to identify one window.
    PID         process id: which running program owns the window.
    ShowWindow  minimise / maximise / restore a window by its HWND.
    SendInput   inject keyboard and mouse events as if the user typed/clicked.

Everything here is low level and does no decision-making. The controllers decide
WHICH window to act on.
"""

from __future__ import annotations

import ctypes
import os
import time
from ctypes import wintypes
from dataclasses import dataclass

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")

# ---- constants (values from the Windows SDK headers) ---------------------------------------
SW_MINIMIZE, SW_MAXIMIZE, SW_RESTORE = 6, 3, 9
WM_CLOSE = 0x0010
GWL_EXSTYLE = -20
WS_EX_TOOLWINDOW = 0x00000080
GW_OWNER = 4
DWMWA_CLOAKED = 14
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000

INPUT_MOUSE, INPUT_KEYBOARD = 0, 1
KEYEVENTF_KEYUP, KEYEVENTF_UNICODE, KEYEVENTF_EXTENDEDKEY = 0x0002, 0x0004, 0x0001
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP = 0x0008, 0x0010
MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP = 0x0020, 0x0040
MOUSEEVENTF_WHEEL = 0x0800
WHEEL_DELTA = 120

# Virtual-key codes: https://learn.microsoft.com/windows/win32/inputdev/virtual-key-codes
VK = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "shift": 0x10, "ctrl": 0x11, "alt": 0x12, "escape": 0x1B,
    "space": 0x20, "page_up": 0x21, "page_down": 0x22, "end": 0x23, "home": 0x24, "left": 0x25, "up": 0x26,
    "right": 0x27, "down": 0x28, "delete": 0x2E, "win": 0x5B, "f5": 0x74,
    "volume_mute": 0xAD, "volume_down": 0xAE, "volume_up": 0xAF, "media_next": 0xB0, "media_previous": 0xB1,
    "media_play_pause": 0xB3,
    **{chr(c).lower(): c for c in range(ord("A"), ord("Z") + 1)},
}
EXTENDED_KEYS = {"left", "up", "right", "down", "home", "end", "page_up", "page_down", "delete"}


# ---- SendInput structures (must match the C layout exactly) --------------------------------
class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class _INPUTUNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("padding", ctypes.c_byte * 32)]


class INPUT(ctypes.Structure):
    _fields_ = [("type", wintypes.DWORD), ("u", _INPUTUNION)]


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
user32.EnumWindows.argtypes = (WNDENUMPROC, wintypes.LPARAM)
user32.GetWindowTextW.argtypes = (wintypes.HWND, wintypes.LPWSTR, ctypes.c_int)
user32.GetWindowTextLengthW.argtypes = (wintypes.HWND,)
user32.GetWindowThreadProcessId.argtypes = (wintypes.HWND, ctypes.POINTER(wintypes.DWORD))
user32.GetWindowLongW.argtypes = (wintypes.HWND, ctypes.c_int)
user32.GetWindow.argtypes = (wintypes.HWND, wintypes.UINT)
user32.GetWindow.restype = wintypes.HWND
user32.GetForegroundWindow.restype = wintypes.HWND
user32.ShowWindow.argtypes = (wintypes.HWND, ctypes.c_int)
user32.SetForegroundWindow.argtypes = (wintypes.HWND,)
user32.IsWindowVisible.argtypes = (wintypes.HWND,)
user32.IsIconic.argtypes = (wintypes.HWND,)
user32.IsZoomed.argtypes = (wintypes.HWND,)
user32.IsWindow.argtypes = (wintypes.HWND,)
user32.PostMessageW.argtypes = (wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
kernel32.OpenProcess.restype = wintypes.HANDLE
kernel32.QueryFullProcessImageNameW.argtypes = (wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                ctypes.POINTER(wintypes.DWORD))
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)


@dataclass(frozen=True)
class WindowInfo:
    hwnd: int
    title: str
    pid: int
    process: str  # executable name, e.g. "chrome.exe"
    minimized: bool
    maximized: bool


# ---- reading windows ---------------------------------------------------------------------------
def window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    buffer = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buffer, length + 1)
    return buffer.value


def window_pid(hwnd: int) -> int:
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def process_name(pid: int) -> str:
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = wintypes.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(size.value)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return os.path.basename(buffer.value)
        return ""
    finally:
        kernel32.CloseHandle(handle)


def _is_cloaked(hwnd: int) -> bool:
    """'Cloaked' windows exist but are hidden by Windows (e.g. suspended Store apps)."""
    cloaked = wintypes.DWORD()
    dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked))
    return bool(cloaked.value)


def _is_app_window(hwnd: int) -> bool:
    """True for the windows you see in the taskbar / Alt+Tab, not hidden helper windows."""
    if not user32.IsWindowVisible(hwnd) or user32.GetWindowTextLengthW(hwnd) == 0:
        return False
    if user32.GetWindow(hwnd, GW_OWNER):  # owned windows are dialogs/popups of another window
        return False
    if user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOOLWINDOW:
        return False
    return not _is_cloaked(hwnd)


def describe(hwnd: int) -> WindowInfo:
    pid = window_pid(hwnd)
    return WindowInfo(int(hwnd), window_title(hwnd), pid, process_name(pid),
                      bool(user32.IsIconic(hwnd)), bool(user32.IsZoomed(hwnd)))


def list_windows() -> list[WindowInfo]:
    """All app windows, front-most first (EnumWindows returns them in z-order)."""
    found: list[int] = []

    @WNDENUMPROC
    def callback(hwnd, _lparam):  # Windows calls this once per top-level window
        if _is_app_window(hwnd):
            found.append(hwnd)
        return True  # keep going

    user32.EnumWindows(callback, 0)
    return [describe(h) for h in found]


def foreground_window() -> int:
    return int(user32.GetForegroundWindow() or 0)


def is_window(hwnd: int) -> bool:
    return bool(user32.IsWindow(hwnd))


# ---- changing windows -----------------------------------------------------------------------------
def show_window(hwnd: int, command: int) -> None:
    user32.ShowWindow(hwnd, command)


def bring_to_front(hwnd: int) -> bool:
    """Restore if minimised, then focus it.

    Windows only lets the program the user is currently using change the focus (so ads
    can't steal it). Tapping Alt first is the widely used, harmless way to satisfy that rule.
    """
    if user32.IsIconic(hwnd):
        user32.ShowWindow(hwnd, SW_RESTORE)
    press_keys(["alt"])
    ok = bool(user32.SetForegroundWindow(hwnd))
    time.sleep(0.15)  # give Windows a moment to switch focus before typing into it
    return ok


def request_close(hwnd: int) -> None:
    """Politely ask a window to close (like clicking X). The app may still ask to save work."""
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)


# ---- simulated input --------------------------------------------------------------------------
def _send(inputs: list[INPUT]) -> None:
    array = (INPUT * len(inputs))(*inputs)
    if user32.SendInput(len(inputs), array, ctypes.sizeof(INPUT)) != len(inputs):
        raise OSError(ctypes.get_last_error(), "SendInput was blocked (is an admin window focused?)")


def _key(vk: int, up: bool, extended: bool = False) -> INPUT:
    flags = (KEYEVENTF_KEYUP if up else 0) | (KEYEVENTF_EXTENDEDKEY if extended else 0)
    return INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=KEYBDINPUT(vk, 0, flags, 0, 0)))


def press_keys(keys: list[str]) -> None:
    """Press keys together, then release in reverse order: ["ctrl", "c"] = Ctrl+C."""
    codes = [(VK[k], k in EXTENDED_KEYS) for k in keys]
    _send([_key(vk, False, ext) for vk, ext in codes] + [_key(vk, True, ext) for vk, ext in reversed(codes)])


def type_unicode(text: str) -> None:
    """Type any text (any language, emoji too) using Unicode key events."""
    events = []
    for char in text.replace("\r\n", "\n"):
        if char == "\n":
            events += [_key(VK["enter"], False), _key(VK["enter"], True)]
            continue
        for unit in _utf16_units(char):  # emoji etc. need two UTF-16 "units"
            events.append(INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=KEYBDINPUT(0, unit, KEYEVENTF_UNICODE, 0, 0))))
            events.append(INPUT(INPUT_KEYBOARD, _INPUTUNION(ki=KEYBDINPUT(0, unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0))))
    for start in range(0, len(events), 200):  # send in batches
        _send(events[start:start + 200])


def _utf16_units(char: str) -> list[int]:
    data = char.encode("utf-16-le")
    return [int.from_bytes(data[i:i + 2], "little") for i in range(0, len(data), 2)]


class POINT(ctypes.Structure):
    _fields_ = [("x", wintypes.LONG), ("y", wintypes.LONG)]


def cursor_position() -> tuple[int, int]:
    point = POINT()
    user32.GetCursorPos(ctypes.byref(point))
    return point.x, point.y


def move_cursor(x: int, y: int) -> None:
    user32.SetCursorPos(int(x), int(y))


def _mouse(flags: int, data: int = 0) -> INPUT:
    return INPUT(INPUT_MOUSE, _INPUTUNION(mi=MOUSEINPUT(0, 0, ctypes.c_uint32(data).value, flags, 0, 0)))


MOUSE_BUTTONS = {"left": (MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP),
                 "right": (MOUSEEVENTF_RIGHTDOWN, MOUSEEVENTF_RIGHTUP),
                 "middle": (MOUSEEVENTF_MIDDLEDOWN, MOUSEEVENTF_MIDDLEUP)}


def click(button: str = "left", times: int = 1) -> None:
    down, up = MOUSE_BUTTONS[button]
    _send([_mouse(f) for _ in range(times) for f in (down, up)])


def scroll(notches: int) -> None:
    """Positive = up, negative = down. One notch = one click of the mouse wheel."""
    _send([_mouse(MOUSEEVENTF_WHEEL, notches * WHEEL_DELTA)])


class SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [("ACLineStatus", ctypes.c_byte), ("BatteryFlag", ctypes.c_byte), ("BatteryLifePercent", ctypes.c_byte),
                ("SystemStatusFlag", ctypes.c_byte), ("BatteryLifeTime", wintypes.DWORD),
                ("BatteryFullLifeTime", wintypes.DWORD)]


def battery_status() -> tuple[int | None, bool]:
    """(percent or None if no battery, plugged_in)."""
    status = SYSTEM_POWER_STATUS()
    kernel32.GetSystemPowerStatus(ctypes.byref(status))
    percent = status.BatteryLifePercent & 0xFF
    return (None if percent == 255 else percent), status.ACLineStatus == 1


def lock_workstation() -> None:
    user32.LockWorkStation()
