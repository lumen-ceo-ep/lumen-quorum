#!/usr/bin/env python3
"""Codex adapter.

Renders review/input/ into a headless `codex exec` invocation, runs it
read-only against review/workspace/, and normalizes the result into
review/out/findings.json per the schema in docs/architecture.md.

Auth: reads CODEX_ACCESS_TOKEN (a ChatGPT-plan-derived token) or
OPENAI_API_KEY from the environment and feeds it to `codex login
--with-access-token`/`--with-api-key` before running -- codex exec itself
takes no auth flag, it reads whatever `codex login` last wrote to
~/.codex/auth.json (see `codex login --help`). If neither env var is set,
assumes the environment is already logged in (e.g. local interactive use).

NOTE: unlike the Claude adapter, this has not yet been exercised against a
real Codex backend end-to-end -- built against `codex exec --help`'s
documented interface, not verified live. Treat findings from this adapter
as unverified until a real run confirms the output actually parses as
expected. See docs/roadmap.md.

Usage: adapter.py <review_dir> [model]
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import SYSTEM_PROMPT, build_prompt, extract_json, postprocess  # noqa: E402

OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "status": {"type": "string"},
        "error": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "file": {"type": "string"},
                    "line": {"type": "integer"},
                    "category": {
                        "type": "string",
                        "enum": ["correctness", "convention", "simplification"],
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["blocking", "major", "minor", "nit"],
                    },
                    "claim": {"type": "string"},
                    "evidence": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {"type": "string"},
                                "ref": {"type": "string"},
                            },
                        },
                    },
                    "failure_scenario": {"type": ["string", "null"]},
                    "confidence": {"type": "number"},
                },
                "required": ["file", "line", "category", "severity", "claim"],
            },
        },
        "coverage": {
            "type": "object",
            "properties": {
                "files_in_diff": {"type": "integer"},
                "files_read": {"type": "array", "items": {"type": "string"}},
                "not_read_reason": {"type": ["string", "null"]},
            },
        },
    },
    "required": ["status"],
}


def _ensure_login() -> str | None:
    """Feeds CODEX_ACCESS_TOKEN or OPENAI_API_KEY into `codex login` if
    present. Returns an error string on failure, None on success/no-op.
    """
    access_token = os.environ.get("CODEX_ACCESS_TOKEN")
    api_key = os.environ.get("OPENAI_API_KEY")
    if access_token:
        flag, value = "--with-access-token", access_token
    elif api_key:
        flag, value = "--with-api-key", api_key
    else:
        return None  # assume already logged in (local/interactive use)

    result = subprocess.run(
        ["codex", "login", flag],
        input=value, capture_output=True, text=True, timeout=60,
    )
    if result.returncode != 0:
        return f"codex login {flag} failed: {result.stderr[:1000]}"
    return None


def _try_extract_usage(stdout_jsonl: str) -> dict:
    """Best-effort scan of the --json event stream for a token-usage event.
    Not verified against a real event stream yet (see module docstring) --
    returns all-None fields rather than raising if the shape doesn't match
    what's guessed here, since usage metadata is informational, not
    load-bearing for the review itself.
    """
    usage = {"total_cost_usd": None, "input_tokens": None, "output_tokens": None}
    for line in stdout_jsonl.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        for key in ("token_usage", "usage"):
            if isinstance(event.get(key), dict):
                u = event[key]
                usage["input_tokens"] = u.get("input_tokens", usage["input_tokens"])
                usage["output_tokens"] = u.get("output_tokens", usage["output_tokens"])
                usage["total_cost_usd"] = u.get("total_cost_usd", usage["total_cost_usd"])
    return usage


def run(review_dir: Path, model: str) -> dict:
    login_error = _ensure_login()
    if login_error:
        return {"status": "error", "error": login_error, "findings": []}

    prompt = SYSTEM_PROMPT + "\n\n" + build_prompt(review_dir)
    workspace = review_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        schema_path = Path(tmp) / "schema.json"
        schema_path.write_text(json.dumps(OUTPUT_SCHEMA))
        last_msg_path = Path(tmp) / "last_message.txt"

        cmd = [
            "codex", "exec", prompt,
            "--sandbox", "read-only",
            "-C", str(workspace),
            "--skip-git-repo-check",
            "--output-schema", str(schema_path),
            "--output-last-message", str(last_msg_path),
            "--json",
        ]
        if model:
            cmd += ["--model", model]

        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=300
        )
        if result.returncode != 0:
            return {
                "status": "error",
                "error": f"codex exited {result.returncode}: {result.stderr[:2000]}",
                "findings": [],
            }

        if not last_msg_path.exists():
            return {
                "status": "error",
                "error": f"codex produced no last-message file; stdout: {result.stdout[:2000]}",
                "findings": [],
            }
        final_text = last_msg_path.read_text()
        usage = _try_extract_usage(result.stdout)

    try:
        findings_obj = extract_json(final_text)
    except ValueError as e:
        return {
            "status": "error",
            "error": str(e),
            "raw": final_text[:2000],
            "findings": [],
        }

    findings_obj = postprocess(review_dir, findings_obj)
    findings_obj["usage"] = usage
    return findings_obj


def main():
    review_dir = Path(sys.argv[1])
    model = sys.argv[2] if len(sys.argv) > 2 else ""
    out = run(review_dir, model)
    out_dir = review_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "findings.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
