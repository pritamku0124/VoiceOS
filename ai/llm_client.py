"""Interface for any language-model backend (Ollama today; others could be added later).

Same pattern as SpeechRecognizer and TTSEngine: the rest of VoiceOS talks to LLMClient,
never to Ollama directly, so tests can use a fake and backends can be swapped.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from utils.exceptions import VoiceOSError


class LLMError(VoiceOSError):
    """The language model is unavailable, timed out, or returned an unusable response."""


class LLMClient(ABC):
    model: str

    @abstractmethod
    def is_available(self) -> bool:
        """True if the backend is running AND the configured model is installed."""

    @abstractmethod
    def chat(self, messages: list[dict], json_output: bool = True) -> str:
        """Send chat messages [{"role": "system"|"user"|"assistant", "content": str}], return the reply text."""
