"""breeze_poc/castle_dispatcher.py - Castle dispatch wrapper (skeleton)

Voice Path v2.0 Phase 1 PoC. Day 3 ship: skeleton + 1 trace example.
Day 5-7 real runtime: hook into Claude Code CLI via subprocess.
"""
import json
import os
import sys
import pathlib
import subprocess
import time

try:
    from anthropic import Anthropic
    HAS_ANTHROPIC = True
except ImportError:
    HAS_ANTHROPIC = False

TOOLS_PATH = pathlib.Path(__file__).parent / "castle_dispatch_tools.json"
CASTLE_AGENTS_PATH = pathlib.Path.home() / ".claude" / "agents"


def load_tools():
    with open(TOOLS_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["tools"]


def dispatch_subagent(agent, task, expect_format="short_answer", timeout_sec=60):
    agent_md = CASTLE_AGENTS_PATH / (agent + ".md")
    if not agent_md.exists():
        return {"status": "error", "error": "agent not found: " + agent}
    return {
        "status": "stub",
        "agent": agent,
        "task_preview": task[:80],
        "note": "Real dispatch pending Day 5-7. See CASTLE-DISPATCH-DEMO.md.",
        "agent_spec_exists": True,
    }


def transcribe_bytes(audio_bytes):
    import tempfile
    from client import transcribe
    with tempfile.NamedTemporaryFile(suffix=".bin", delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name
    try:
        return transcribe(tmp_path, language="zh")
    finally:
        try:
            os.remove(tmp_path)
        except OSError:
            pass


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: py castle_dispatcher.py tools | stub <agent> <task>")
        sys.exit(1)
    cmd = sys.argv[1]
    if cmd == "tools":
        print(json.dumps(load_tools(), indent=2, ensure_ascii=False))
    elif cmd == "stub":
        if len(sys.argv) < 4:
            print("Need: stub <agent> <task...>"); sys.exit(1)
        agent = sys.argv[2]
        task = " ".join(sys.argv[3:])
        r = dispatch_subagent(agent, task)
        print(json.dumps(r, indent=2, ensure_ascii=False))
    else:
        print("Unknown:", cmd); sys.exit(1)
