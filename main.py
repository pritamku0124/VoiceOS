"""VoiceOS entry point.

Run from the project folder (with the virtual environment active):
    python main.py                 -> start VoiceOS normally
    python main.py --smoke-test    -> start, wait 3 seconds, close (quick "does it launch?" check)

This file stays tiny on purpose: it reads command-line options and hands control to
core.application.VoiceOSApplication, where the real start-up logic lives.
"""

import argparse
import sys

from utils.exceptions import VoiceOSError


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="VoiceOS - voice-controlled assistant for Windows")
    parser.add_argument(
        "--smoke-test",
        nargs="?",
        const=3.0,
        type=float,
        metavar="SECONDS",
        help="open the window, then close automatically after SECONDS (default 3)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    from utils.platform_utils import require_virtualenv

    require_virtualenv()  # clear message instead of "No module named PySide6" when .venv isn't active
    # Imported inside main() so that `python main.py --help` works even if PySide6 is missing.
    from core.application import VoiceOSApplication

    try:
        app = VoiceOSApplication()
        app.setup()
        auto_close = int(args.smoke_test * 1000) if args.smoke_test else None
        return app.run(auto_close_ms=auto_close)
    except VoiceOSError as exc:
        # Expected problems (bad config, wrong OS): show a friendly message, no scary traceback.
        print(f"VoiceOS could not start: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    # sys.exit passes our return value to Windows as the process exit code (0 = success).
    sys.exit(main())
