"""Facts about the computer VoiceOS is running on.

VoiceOS automates *Windows*. Most later modules (pywin32, Core Audio) simply cannot
work on macOS/Linux, so we check early and fail with a clear message instead of a
confusing crash deep inside a library.
"""

import platform
import sys

from utils.constants import MIN_PYTHON
from utils.exceptions import EnvironmentCheckError


def is_windows() -> bool:
    return sys.platform == "win32"


def python_version_ok() -> bool:
    # sys.version_info is a tuple like (3, 14, 10, 'final', 0); tuples compare item by item.
    return sys.version_info[:2] >= MIN_PYTHON


def describe_system() -> dict[str, str]:
    """Return a small summary used in logs and the environment check script."""
    return {
        "os": f"{platform.system()} {platform.release()} (build {platform.version()})",
        "machine": platform.machine(),
        "python": platform.python_version(),
        "python_executable": sys.executable,
    }


def in_virtualenv() -> bool:
    # Inside a venv, sys.prefix points at .venv while sys.base_prefix points at the global Python.
    return sys.prefix != sys.base_prefix


def require_virtualenv() -> None:
    """Exit with clear instructions if started with the global Python instead of .venv.

    Without this, the user sees a confusing "ModuleNotFoundError: sounddevice" traceback,
    because the packages are installed only inside .venv.
    """
    if in_virtualenv():
        return
    script = " ".join(sys.argv) or "main.py"
    sys.exit(
        "\nVoiceOS must run with its virtual environment (.venv), but this is the global Python:\n"
        f"    {sys.executable}\n\n"
        "Fix - EITHER activate it once per terminal (prompt then starts with (.venv)):\n"
        "    .\\.venv\\Scripts\\Activate.ps1\n"
        f"    python {script}\n\n"
        "OR call the venv's Python directly:\n"
        f"    .\\.venv\\Scripts\\python.exe {script}\n"
    )


def assert_supported_platform() -> None:
    """Raise EnvironmentCheckError if VoiceOS cannot run here."""
    if not is_windows():
        raise EnvironmentCheckError("VoiceOS controls Windows and only runs on Windows 10/11.")
    if not python_version_ok():
        need = ".".join(map(str, MIN_PYTHON))
        raise EnvironmentCheckError(f"Python {need}+ is required, found {platform.python_version()}.")
