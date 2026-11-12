"""Tests the real OllamaClient HTTP code against a tiny fake Ollama server.

http.server (built into Python) runs on a free local port in a background thread and
answers like Ollama does. This tests our real networking code without needing Ollama.
"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from ai.llm_client import LLMError
from ai.ollama_client import OllamaClient


class FakeOllama(BaseHTTPRequestHandler):
    models = ["qwen2.5:1.5b"]
    chat_reply = '{"actions": [], "answer": "hi"}'
    received: list = []

    def _send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):  # noqa: N802
        if self.path == "/api/tags":
            self._send(200, {"models": [{"name": m} for m in self.models]})
        else:
            self._send(404, {"error": "not found"})

    def do_POST(self):  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        FakeOllama.received.append(body)
        if body["model"] not in self.models:
            self._send(404, {"error": f"model '{body['model']}' not found"})
        else:
            self._send(200, {"message": {"role": "assistant", "content": self.chat_reply}})

    def log_message(self, *args):  # keep test output quiet
        pass


@pytest.fixture
def server():
    httpd = HTTPServer(("127.0.0.1", 0), FakeOllama)  # port 0 = "pick any free port"
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    FakeOllama.received = []
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()


def test_available_when_model_installed(server):
    assert OllamaClient(server, "qwen2.5:1.5b").is_available()


def test_not_available_when_model_missing(server):
    assert not OllamaClient(server, "llama3.2:3b").is_available()


def test_not_available_when_ollama_not_running():
    assert not OllamaClient("http://127.0.0.1:9", "qwen2.5:1.5b").is_available()  # port 9: nothing listens


def test_chat_sends_correct_request(server):
    reply = OllamaClient(server, "qwen2.5:1.5b").chat([{"role": "user", "content": "hello"}])
    assert reply == '{"actions": [], "answer": "hi"}'
    sent = FakeOllama.received[0]
    assert sent["format"] == "json" and sent["stream"] is False and sent["options"]["temperature"] == 0


def test_chat_error_becomes_llm_error(server):
    with pytest.raises(LLMError, match="HTTP 404"):
        OllamaClient(server, "missing-model").chat([{"role": "user", "content": "x"}])


@pytest.mark.parametrize("url", ["http://example.com:11434", "http://192.168.1.20:11434", "https://ollama.ai"])
def test_only_this_computer_is_allowed(url):
    with pytest.raises(LLMError, match="this computer"):
        OllamaClient(url)
