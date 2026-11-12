"""Asks the user "Are you sure?" before risky actions - from a background thread.

The problem:
    Actions run on the Assistant's worker thread, but dialogs may only be shown on the
    GUI thread. So the worker can't just open a QMessageBox.

The solution (a classic pattern):
    worker thread                         GUI thread
    ask("Close Chrome?")
      ├─ create a Request with an Event
      ├─ emit confirmation_requested ───► MainWindow shows the dialog
      └─ wait on the Event (max 30 s) ◄── request.answer(True/False) sets the Event
    returns True only for an explicit "Yes". Timeout or closing the dialog = No.

Phase 8 adds answering by voice ("yes" / "no").
"""

from __future__ import annotations

import logging
import threading

from PySide6.QtCore import QObject, Signal

logger = logging.getLogger(__name__)


class ConfirmationRequest:
    def __init__(self, question: str):
        self.question = question
        self._answer = False
        self._event = threading.Event()

    def answer(self, yes: bool) -> None:
        self._answer = bool(yes)
        self._event.set()

    def wait(self, timeout: float) -> bool:
        if not self._event.wait(timeout):
            logger.info("No answer to %r within %.0f s - treating as No", self.question, timeout)
            return False
        return self._answer


class ConfirmationManager(QObject):
    confirmation_requested = Signal(object)  # ConfirmationRequest

    def __init__(self, timeout: float = 30.0, parent: QObject | None = None):
        super().__init__(parent)
        self.timeout = timeout

    def ask(self, question: str) -> bool:
        """Call from a WORKER thread. Blocks until the user answers (or the timeout)."""
        request = ConfirmationRequest(question)
        self.confirmation_requested.emit(request)
        answer = request.wait(self.timeout)
        logger.info("Confirmation %r -> %s", question, "yes" if answer else "no")
        return answer
