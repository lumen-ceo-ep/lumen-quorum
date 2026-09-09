#!/usr/bin/env python3
"""One headless Claude Code call, normalized.

The Claude-specific bit shared by everything that needs a model pass against the
checked-out workspace: the review node (`adapter.py`) and the Stage 2 adjudicator
(`engine/orchestrator/adjudicate.py`). Keeping it here, not in
`engine/adapters/common.py`, is ENG-2: `common.py` stays vendor-free.

Returns a plain dict, never raises for a model/CLI failure:
  {"ok": True,  "text": "<final assistant message>", "envelope": {...raw...}}
  {"ok": False, "error": "<what went wrong>"}
"""
import json
import os
import subprocess
from pathlib import Path

DEFAULT_ALLOWED_TOOLS = "Read Glob Grep"
# A real review of a large PR (the engine reviewing its own multi-file PR is the
# case that first hit this) routinely runs past 5 minutes once the node starts
# reading files. Default generously; override with QUORUM_NODE_TIMEOUT (seconds).
DEFAULT_TIMEOUT = int(os.environ.get("QUORUM_NODE_TIMEOUT") or 900)


def invoke(prompt: str, *, model: str, cwd, allowed_tools: str = DEFAULT_ALLOWED_TOOLS,
           append_system: str = None, timeout: int = DEFAULT_TIMEOUT) -> dict:
    cwd = Path(cwd)
    cwd.mkdir(parents=True, exist_ok=True)

    # The prompt goes on stdin, never in argv: a real diff (the engine reviewing
    # its own PR is the case that first hit this) easily exceeds ARG_MAX and the
    # exec fails with "Argument list too long". `claude -p` with no positional
    # reads the prompt from stdin.
    cmd = ["claude", "-p", "--output-format", "json", "--model", model]
    if allowed_tools:
        cmd += ["--allowedTools", allowed_tools]
    if append_system:
        cmd += ["--append-system-prompt", append_system]

    try:
        result = subprocess.run(
            cmd, input=prompt, cwd=str(cwd),
            capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"claude timed out after {timeout}s"}
    except FileNotFoundError:
        return {"ok": False, "error": "claude CLI not found on PATH"}

    if result.returncode != 0:
        return {"ok": False, "error": f"claude exited {result.returncode}: {result.stderr[:2000]}"}

    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "error": f"non-JSON envelope: {result.stdout[:2000]}"}

    if envelope.get("is_error"):
        return {"ok": False, "error": f"claude reported an error: {envelope.get('result', '')[:2000]}"}

    return {"ok": True, "text": envelope.get("result", ""), "envelope": envelope}


def usage_of(envelope: dict) -> dict:
    u = envelope.get("usage", {}) or {}
    return {
        "total_cost_usd": envelope.get("total_cost_usd"),
        "input_tokens": u.get("input_tokens"),
        "output_tokens": u.get("output_tokens"),
        "cache_read_tokens": u.get("cache_read_input_tokens"),
    }
