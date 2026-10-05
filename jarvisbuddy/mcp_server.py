"""Jarvis's laptop tools as an MCP server, so other apps (Claude Desktop, Claude Code...) can
control your laptop through Jarvis.

Run:  python -m jarvisbuddy.mcp_server

Claude Desktop config (Settings > Developer > Edit Config):

    {"mcpServers": {"jarvisbuddy": {
        "command": "C:\\\\path\\\\to\\\\JarvisBuddy\\\\.venv\\\\Scripts\\\\python.exe",
        "args": ["-m", "jarvisbuddy.mcp_server"],
        "cwd": "C:\\\\path\\\\to\\\\JarvisBuddy"}}}

Risky tools (email, delete, move, shutdown, commands...) pop up a Yes/No box on the laptop
before running, even if the app calling them already approved. Set JARVIS_MCP_CONFIRM=0 to
rely on the calling app's own approval instead.
"""

from __future__ import annotations

import functools
import inspect
import os

from .actions import Actions
from .config import Config
from .mailer import Mailer
from .memory import Memory
from .tools import Tool, build_tools


def ask_on_screen(question: str) -> bool:
    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        answer = messagebox.askyesno("JarvisBuddy", question, parent=root)
        root.destroy()
        return bool(answer)
    except Exception:
        return False  # no way to ask, so don't do it


def guarded(tool: Tool, confirm: bool):
    """The tool's function, with a Yes/No check in front when it's risky."""
    @functools.wraps(tool.func)
    def run(**kwargs):
        if tool.risky and confirm and not ask_on_screen(tool.question(kwargs)):
            return "The user said no on the laptop, so this wasn't done."
        return tool.func(**kwargs)

    run.__signature__ = inspect.signature(tool.func)  # type: ignore[attr-defined]
    return run


def build_server(config: Config | None = None):
    from mcp.server.fastmcp import FastMCP
    from mcp.types import ToolAnnotations

    config = config or Config.from_env()
    memory = Memory(config.memory_file)
    tools = build_tools(config, Actions(), memory, Mailer(config))
    confirm = os.environ.get("JARVIS_MCP_CONFIRM", "1") != "0"

    server = FastMCP("JarvisBuddy", instructions=(
        f"Tools to control {memory.name or config.user_name}'s Windows laptop: apps, windows, keyboard, "
        "files, volume, brightness, media, power, email, memory and PowerShell."))
    for tool in tools.values():
        server.add_tool(
            guarded(tool, confirm), name=tool.name, description=tool.schema()["description"],
            annotations=ToolAnnotations(readOnlyHint=tool.read_only, destructiveHint=tool.risky),
        )
    return server


def main() -> None:
    build_server().run()


if __name__ == "__main__":
    main()
