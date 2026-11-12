"""Talks to the local Ollama server over HTTP (only on this computer).

Ollama runs AI models locally and offers a small web API on http://localhost:11434.
We use two endpoints:
    GET  /api/tags   -> which models are installed (also tells us Ollama is running)
    POST /api/chat   -> send messages, get the model's reply

We use Python's built-in urllib instead of the `ollama` package: two HTTP calls don't
justify an extra dependency.

Privacy: base_url must point at THIS computer (localhost / 127.0.0.1 / ::1). That
guarantees your commands never leave the machine, even if config.json is edited.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse

from ai.llm_client import LLMClient, LLMError

logger = logging.getLogger(__name__)

LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class OllamaClient(LLMClient):
    AVAILABILITY_CACHE_SECONDS = 15

    def __init__(self, base_url: str = "http://localhost:11434", model: str = "qwen2.5:1.5b", timeout: float = 30):
        host = urlparse(base_url).hostname
        if host not in LOCAL_HOSTS:
            raise LLMError(f"Ollama address must be on this computer (localhost), got {base_url!r}")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._available: tuple[float, bool] | None = None  # (checked_at, result)

    # ---- HTTP helpers -------------------------------------------------------------------------------
    def _request(self, path: str, payload: dict | None = None, timeout: float | None = None) -> dict:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path, data=data, headers={"Content-Type": "application/json"},
            method="GET" if data is None else "POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout or self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            raise LLMError(f"Ollama returned HTTP {exc.code}: {detail}") from exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            raise LLMError(f"Could not reach Ollama at {self.base_url}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise LLMError("Ollama sent a response that isn't JSON") from exc

    # ---- public API -----------------------------------------------------------------------------------
    def installed_models(self) -> list[str]:
        return [m.get("name", "") for m in self._request("/api/tags", timeout=2).get("models", [])]

    def is_available(self) -> bool:
        """Running and the model is installed. Cached for a few seconds: this is asked per command."""
        now = time.monotonic()
        if self._available and now - self._available[0] < self.AVAILABILITY_CACHE_SECONDS:
            return self._available[1]
        try:
            names = self.installed_models()
            wanted = self.model if ":" in self.model else f"{self.model}:latest"
            result = wanted in names
            if not result:
                logger.warning("Ollama is running but model %s is not installed (have: %s)", self.model, names)
        except LLMError as exc:
            logger.info("Ollama not available: %s", exc)
            result = False
        self._available = (now, result)
        return result

    def chat(self, messages: list[dict], json_output: bool = True) -> str:
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,  # one complete answer instead of word-by-word chunks
            "keep_alive": "15m",  # keep the model in memory between commands (faster next time)
            "options": {"temperature": 0},  # 0 = most predictable output, best for structured data
        }
        if json_output:
            payload["format"] = "json"  # Ollama forces the reply to be valid JSON
        started = time.perf_counter()
        reply = self._request("/api/chat", payload)
        content = reply.get("message", {}).get("content")
        if not isinstance(content, str):
            raise LLMError("Ollama reply had no message content")
        logger.info("Ollama %s answered in %.1f s", self.model, time.perf_counter() - started)
        return content


def create_llm_client(config) -> OllamaClient | None:
    if not config.get("ai.enabled", True):
        return None
    return OllamaClient(config.get("ai.base_url"), config.get("ai.model"), config.get("ai.timeout_seconds"))
