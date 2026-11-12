"""Sets up Python's logging so every module writes to the console AND logs/voiceos.log.

Why logging instead of print()?
    - Each message gets a time, a level (DEBUG/INFO/WARNING/ERROR) and the module name.
    - We can change how much detail we see from config.json without touching code.
    - The log file survives after the app closes, which is essential for debugging
      problems like "it opened the wrong window five minutes ago".

How other files use it:
    import logging
    logger = logging.getLogger(__name__)   # __name__ is e.g. "core.application"
    logger.info("Something happened")
"""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"


def setup_logging(log_dir: Path, level: str = "INFO") -> Path:
    """Configure the root logger once at start-up. Returns the log file path."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "voiceos.log"

    root = logging.getLogger()
    root.setLevel(level.upper())
    # Remove handlers from a previous call (important in tests that call this repeatedly).
    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(LOG_FORMAT, datefmt="%Y-%m-%d %H:%M:%S")

    # RotatingFileHandler: when the file reaches 1 MB it is renamed voiceos.log.1 and a
    # new one starts, keeping at most 3 old files. The log can never fill your disk.
    file_handler = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root.addHandler(file_handler)
    root.addHandler(console_handler)
    return log_file
