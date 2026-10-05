import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from jarvisbuddy.brain import Brain
from jarvisbuddy.config import Config
from jarvisbuddy.mailer import Mailer
from jarvisbuddy.memory import Memory
from jarvisbuddy.skills import MOODS
from jarvisbuddy.tools import ToolRunner, build_tools, resolve_path

from .conftest import FakeActions, FakeMailer


@pytest.fixture
def tools(tmp_path):
    config = Config(data_dir=tmp_path / "data")
    return build_tools(config, FakeActions(), Memory(config.memory_file), FakeMailer())


def test_risky_tools_are_marked(tools):
    risky = {name for name, t in tools.items() if t.risky}
    assert risky == {"close_app", "delete_file", "move_file", "power", "run_command",
                     "send_email", "write_text_file"}
    assert tools["delete_file"].question({"path": "downloads/old.zip"}) == "Should I delete downloads/old.zip?"


def test_runner_only_runs_risky_tools_after_yes(tools, tmp_path):
    target = tmp_path / "keep.txt"
    asked = []
    runner = ToolRunner(tools, confirm=lambda q: asked.append(q) or False)
    out, err = runner.run("write_text_file", {"path": str(target), "content": "hi"})
    assert "said no" in out and not err and not target.exists()
    assert asked == [f"Should I write to {target}?"]

    runner = ToolRunner(tools, confirm=lambda q: True)
    runner.run("write_text_file", {"path": str(target), "content": "hi"})
    assert target.read_text() == "hi"
    # Safe tools never ask.
    runner = ToolRunner(tools, confirm=lambda q: pytest.fail("asked for a safe tool"))
    assert "keep.txt" in runner.run("list_folder", {"path": str(tmp_path)})[0]


def test_file_tools(tools, tmp_path):
    runner = ToolRunner(tools, confirm=lambda q: True)
    (tmp_path / "a.txt").write_text("hello")
    runner.run("create_folder", {"path": str(tmp_path / "box")})
    runner.run("move_file", {"source": str(tmp_path / "a.txt"), "destination": str(tmp_path / "box" / "b.txt")})
    assert runner.run("read_text_file", {"path": str(tmp_path / "box" / "b.txt")})[0] == "hello"
    assert str(tmp_path / "box" / "b.txt") in runner.run("find_files", {"name": "b.t", "folder": str(tmp_path)})[0]
    out, _ = runner.run("delete_file", {"path": str(tmp_path / "box" / "b.txt")})
    assert "Recycle Bin" in out or "send2trash" in out
    assert "won't delete" in runner.run("delete_file", {"path": str(Path.home())})[0]


def test_resolve_known_folders():
    assert resolve_path("downloads") == Path.home() / "Downloads"
    assert resolve_path("Desktop/notes.txt") == (Path.home() / "Desktop" / "notes.txt").resolve()


def test_email_tool_needs_known_address(tools):
    runner = ToolRunner(tools, confirm=lambda q: True)
    assert "No email address saved" in runner.run("send_email", {"to": "bob", "body": "hi"})[0]
    assert runner.run("send_email", {"to": "bob@x.com", "body": "hi"})[0] == "Sent to bob@x.com."


def test_runner_reports_errors(tools):
    runner = ToolRunner(tools, confirm=lambda q: True)
    assert runner.run("nope", {}) == ("Unknown tool nope.", True)


# --- Claude driving the tools -------------------------------------------------

class ScriptedStream:
    def __init__(self, chunks, content, stop_reason):
        self.text_stream = iter(chunks)
        self.final = SimpleNamespace(stop_reason=stop_reason, content=content)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def get_final_message(self):
        return self.final


def test_brain_calls_tools_and_speaks_between_rounds(tmp_path):
    calls = []
    script = [
        ScriptedStream(["[excited] On it!"],
                       [SimpleNamespace(type="text", text="[excited] On it!"),
                        SimpleNamespace(type="tool_use", id="t1", name="open_app", input={"name": "notepad"})],
                       "tool_use"),
        ScriptedStream(["Notepad is open."], [SimpleNamespace(type="text", text="Notepad is open.")], "end_turn"),
    ]

    def stream(**kwargs):
        calls.append(kwargs)
        return script[len(calls) - 1]

    client = SimpleNamespace(beta=SimpleNamespace(messages=SimpleNamespace(stream=stream)))
    config = Config(data_dir=tmp_path)
    memory = Memory(config.memory_file)
    actions = FakeActions()
    runner = ToolRunner(build_tools(config, actions, memory, Mailer(config)), confirm=lambda q: True)
    brain = Brain(config, memory, client=client, moods=MOODS, tools=runner)

    heard = []
    answer = brain.ask("open notepad please", on_sentence=lambda s, m: heard.append((s, m)))
    assert heard == [("On it!", "excited"), ("Notepad is open.", "excited")]
    assert actions.apps == ["notepad"]
    assert any(t["name"] == "delete_file" for t in calls[0]["tools"])
    result = calls[1]["messages"][-1]["content"][0]
    assert result == {"type": "tool_result", "tool_use_id": "t1", "content": "Opened notepad.", "is_error": False}
    assert answer.text == "On it! Notepad is open."
    assert [m["role"] for m in brain.history] == ["user", "assistant", "user", "assistant"]


def test_trim_never_splits_tool_pairs():
    convo = []
    for i in range(25):
        convo += [{"role": "user", "content": f"q{i}"}, {"role": "assistant", "content": []},
                  {"role": "user", "content": [{"type": "tool_result"}]}, {"role": "assistant", "content": []}]
    trimmed = Brain._trim(convo)
    assert trimmed[0] == {"role": "user", "content": "q5"} and len(trimmed) == 80


def test_spoken_confirmation(jarvis):
    jarvis._read_answer = lambda: "yes do it"
    assert jarvis.ask_yes_no("Should I delete old.zip?")
    jarvis._read_answer = lambda: "hmm wait"
    assert not jarvis.ask_yes_no("Should I delete old.zip?")
    jarvis._read_answer = lambda: None  # silence
    assert not jarvis.ask_yes_no("Should I delete old.zip?")
    assert jarvis.spoken.count("Okay, I won't.") == 2


# --- MCP ----------------------------------------------------------------------

def test_mcp_server_round_trip_through_hub(tmp_path):
    from jarvisbuddy.mcp_hub import McpHub

    (tmp_path / "hello.txt").write_text("hi")
    cfg = tmp_path / "mcp_servers.json"
    cfg.write_text(json.dumps({"mcpServers": {"buddy": {
        "command": sys.executable, "args": ["-m", "jarvisbuddy.mcp_server"],
        "env": {"JARVIS_DATA_DIR": str(tmp_path / "data"), "PYTHONPATH": str(Path(__file__).parent.parent)},
    }}}))
    hub = McpHub(cfg).start()
    try:
        assert not hub.errors
        assert hub.has("buddy__list_folder") and hub.has("buddy__delete_file")
        assert not hub.is_risky("buddy__list_folder") and hub.is_risky("buddy__delete_file")
        out, err = hub.call("buddy__list_folder", {"path": str(tmp_path)})
        assert "hello.txt" in out and not err

        asked = []
        runner = ToolRunner({}, confirm=lambda q: asked.append(q) or False, extra=hub)
        out, _ = runner.run("buddy__delete_file", {"path": str(tmp_path / "hello.txt")})
        assert "said no" in out and (tmp_path / "hello.txt").exists()
        assert asked and asked[0].startswith("Should I use delete file from buddy")
    finally:
        hub.close()
