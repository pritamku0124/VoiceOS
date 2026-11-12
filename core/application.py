"""VoiceOSApplication: wires the pieces together and runs the Qt event loop.

Start-up order (each step depends on the one before):
    1. Check platform   - are we on Windows with a new-enough Python?
    2. Logging          - so every later step can report problems.
    3. Configuration    - read config.json.
    4. Qt application   - create QApplication, apply the stylesheet.
    5. Main window      - build and show the UI.
    6. Event loop       - app.exec() waits for clicks/keys until the window closes.

Keeping this in a class (instead of inside main.py) lets tests create the
application without launching a visible window.
"""

from __future__ import annotations

import logging
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from services.config_service import ConfigService
from services.logging_service import setup_logging
from utils.constants import APP_NAME, APP_VERSION, CONFIG_FILE, LOGS_DIR, STYLES_DIR
from utils.platform_utils import assert_supported_platform, describe_system

logger = logging.getLogger(__name__)


class VoiceOSApplication:
    def __init__(self, argv: list[str] | None = None):
        self.argv = argv if argv is not None else sys.argv
        self.config = ConfigService(CONFIG_FILE)
        self.qt_app: QApplication | None = None
        self.window = None

    def setup(self) -> None:
        assert_supported_platform()
        log_file = setup_logging(LOGS_DIR)
        self.config.load()
        logging.getLogger().setLevel(self.config.get("app.log_level", "INFO"))
        logger.info("Starting %s %s", APP_NAME, APP_VERSION)
        for key, value in describe_system().items():
            logger.info("  %-17s %s", key, value)
        logger.info("Log file: %s", log_file)

        # QApplication must exist before ANY widget is created. Only one per process.
        self.qt_app = QApplication.instance() or QApplication(self.argv)
        self.qt_app.setApplicationName(APP_NAME)
        self.qt_app.setApplicationVersion(APP_VERSION)
        self.qt_app.setFont(QFont("Segoe UI", 10))
        self.qt_app.setStyleSheet(self._load_stylesheet())

        # Imported here (not at the top) so importing this module never requires a display.
        from dashboard.main_window import MainWindow

        self.window = MainWindow(self.config)

    def _load_stylesheet(self) -> str:
        theme = self.config.get("ui.theme", "dark")
        path = STYLES_DIR / f"{theme}_theme.qss"
        if theme != "dark":
            # Light theme is built in Phase 9; fall back so the app still looks right.
            logger.warning("Theme '%s' is not available yet - using dark theme.", theme)
            path = STYLES_DIR / "dark_theme.qss"
        return path.read_text(encoding="utf-8")

    def run(self, auto_close_ms: int | None = None) -> int:
        """Show the window and run until it closes. Returns the process exit code."""
        if self.qt_app is None:
            self.setup()
        self.window.show()
        if auto_close_ms:
            # Used by `python main.py --smoke-test`: prove the app starts, then quit by itself.
            QTimer.singleShot(auto_close_ms, self.qt_app.quit)
        exit_code = self.qt_app.exec()
        logger.info("%s closed (exit code %s)", APP_NAME, exit_code)
        return exit_code
