"""The Assistant: one request in, one response out.

    "open whatsapp and minimize chrome"
        │  IntentRecognizer   rules first, AI fallback          -> [Intent, Intent]   (validated)
        │  CommandRouter      run what's runnable               -> [ActionResult, ...]
        │  build_reply        sentence to speak                 -> "I understood: open WhatsApp, then ..."
        │  ConversationContext remember for "it" / follow-ups
        └─ HistoryService     save to SQLite (if enabled)
        → AssistantResponse  (emitted as a Qt signal)

Threading: the AI can take several seconds on a CPU, so requests run on a single
background worker (ThreadPoolExecutor with max_workers=1). One worker means requests
are handled strictly in order, never two at once. Results come back as a Qt signal.
"""

from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from PySide6.QtCore import QObject, Signal

from actions.action_registry import get_spec
from ai.conversation_manager import ConversationContext
from ai.intent_recognition import IntentRecognizer, Recognition
from ai.response_generator import build_reply
from core.command_router import ActionResult, CommandRouter

logger = logging.getLogger(__name__)


@dataclass
class AssistantResponse:
    text: str  # what the user said/typed
    mode: str  # "voice" or "typed"
    recognition: Recognition
    results: list[ActionResult] = field(default_factory=list)
    reply: str = ""

    @property
    def status(self) -> str:
        statuses = {r.status for r in self.results}
        if not self.results:
            return "answered" if self.recognition.answer else "not_understood"
        for s in ("failed", "cancelled", "planned"):
            if s in statuses:
                return s
        return "done"

    def interpretation_lines(self) -> list[str]:
        """For the UI: one line per action, e.g. 'Open WhatsApp - planned (Phase 6)'."""
        lines = []
        for r in self.results:
            spec = get_spec(r.intent.action)
            state = {"done": "done", "failed": f"failed: {r.message}", "cancelled": "cancelled (not confirmed)"}.get(
                r.status, f"understood, not available until Phase {spec.phase}")
            lines.append(f"{r.description[:1].upper()}{r.description[1:]}  -  {state}")
        return lines


class Assistant(QObject):
    response_ready = Signal(object)  # AssistantResponse
    busy_changed = Signal(bool)

    def __init__(self, recognizer: IntentRecognizer, router: CommandRouter | None = None, history=None,
                 parent: QObject | None = None):
        super().__init__(parent)
        self.recognizer = recognizer
        self.router = router or CommandRouter()
        self.history = history
        self.context = ConversationContext()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="Assistant")
        # _pending is changed from two threads (GUI: +1, worker: -1). "x += 1" is really
        # read-add-write, so without a lock two threads can interleave and lose an update.
        self._pending = 0
        self._pending_lock = threading.Lock()

    def submit(self, text: str, mode: str = "voice") -> None:
        """Handle `text` in the background; response_ready fires when done. Call from the GUI thread."""
        with self._pending_lock:
            self._pending += 1
            first = self._pending == 1
        if first:
            self.busy_changed.emit(True)
        future = self._executor.submit(self.handle, text, mode)
        future.add_done_callback(self._done)

    def _done(self, future) -> None:  # runs on the worker thread
        response = None
        if not future.cancelled():  # cancelled = app closing with requests still queued: normal, not a crash
            try:
                response = future.result()
            except Exception:
                logger.exception("Assistant crashed while handling a request")
        if response is not None:
            self.response_ready.emit(response)
        with self._pending_lock:
            self._pending -= 1
            last = self._pending == 0
        if last:
            self.busy_changed.emit(False)

    def handle(self, text: str, mode: str = "voice") -> AssistantResponse:
        """Synchronous version (used by submit and by tests)."""
        recognition = self.recognizer.recognize(text, self.context)
        results = [self.router.route(intent) for intent in recognition.intents]
        reply = build_reply(recognition, results, ai_installed=self.recognizer.ai_available)
        self.context.remember(text, recognition.intents)
        response = AssistantResponse(text, mode, recognition, results, reply)
        logger.info("%r -> %s via %s -> %r", text, [str(i) for i in recognition.intents], recognition.source, reply)
        if self.history is not None:
            try:
                self.history.add(text, mode, recognition.source,
                                 [{"action": r.intent.action, "params": r.intent.params, "status": r.status}
                                  for r in results], reply, response.status)
            except Exception:
                logger.exception("Could not save history")  # history must never break the assistant
        return response

    def warm_up(self) -> None:
        """Load the AI model in the background at start-up (first answer: ~5 s instead of ~20 s).

        Its own thread, NOT the request queue: on the queue it blocked even instant rule-based
        commands like "hello" for up to 20 s while the model loaded.
        """
        threading.Thread(target=self.recognizer.warm_up, name="AIWarmUp", daemon=True).start()

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)
