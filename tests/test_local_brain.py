import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from jarvisbuddy.config import Config
from jarvisbuddy.local_brain import OllamaBrain, make_brain
from jarvisbuddy.memory import Memory
from jarvisbuddy.skills import MOODS
from jarvisbuddy.tools import ToolRunner, build_tools

from .conftest import FakeActions, FakeMailer


@pytest.fixture
def ollama():
    """A fake Ollama server: first asks to open notepad, then answers."""
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'{"models": [{"name": "llama3.2:latest"}]}')

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            requests.append(body)
            self.send_response(200)
            self.end_headers()
            if len([r for r in requests if "messages" in r]) == 1:
                lines = [{"message": {"content": "[excited] On it! "}},
                         {"message": {"content": "", "tool_calls": [
                             {"function": {"name": "open_app", "arguments": {"name": "notepad"}}}]}},
                         {"done": True}]
            else:
                lines = [{"message": {"content": "Notepad is open."}}, {"done": True}]
            self.wfile.write("\n".join(json.dumps(x) for x in lines).encode())

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}", requests
    server.shutdown()


def test_ollama_brain_streams_and_uses_tools(ollama, tmp_path):
    url, requests = ollama
    config = Config(data_dir=tmp_path)
    memory = Memory(config.memory_file)
    actions = FakeActions()
    runner = ToolRunner(build_tools(config, actions, memory, FakeMailer()), confirm=lambda q: True)
    brain = OllamaBrain(config, memory, moods=MOODS, tools=runner, url=url)
    heard = []
    answer = brain.ask("open notepad", on_sentence=lambda s, m: heard.append((s, m)))
    assert heard == [("On it!", "excited"), ("Notepad is open.", "excited")]
    assert actions.apps == ["notepad"]
    assert requests[0]["model"] == "llama3.2" and requests[0]["tools"]
    assert requests[1]["messages"][-1] == {"role": "tool", "content": "Opened notepad.", "tool_name": "open_app"}
    assert answer.spoken


def test_brain_choice(ollama, tmp_path, monkeypatch):
    url, _ = ollama
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    config = Config(data_dir=tmp_path, ollama_url=url)
    memory = Memory(config.memory_file)
    assert isinstance(make_brain(config, memory, MOODS), OllamaBrain)  # no key -> offline brain
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    brain = make_brain(config, memory, MOODS)
    assert not isinstance(brain, OllamaBrain) and isinstance(brain.backup, OllamaBrain)


def test_ollama_not_running(tmp_path):
    brain = OllamaBrain(Config(data_dir=tmp_path), Memory(tmp_path / "m.json"), url="http://127.0.0.1:9")
    assert "isn't running" in brain.ask("hi").text
