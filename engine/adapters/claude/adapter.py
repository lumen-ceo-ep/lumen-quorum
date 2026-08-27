#!/usr/bin/env python3
"""Claude adapter.

Renders review/input/ into a headless Claude Code invocation, runs it
read-only against review/workspace/, and normalizes the result into
review/out/findings.json per the schema in docs/architecture.md.

Usage: adapter.py <review_dir> [model]
"""
import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import SYSTEM_PROMPT, build_prompt, extract_json, postprocess  # noqa: E402


def run(review_dir: Path, model: str) -> dict:
    prompt = build_prompt(review_dir)
    workspace = review_dir / "workspace"
    workspace.mkdir(parents=True, exist_ok=True)

    cmd = [
        "claude",
        "-p", prompt,
        "--output-format", "json",
        "--model", model,
        "--allowedTools", "Read Glob Grep",
        "--append-system-prompt", SYSTEM_PROMPT,
    ]
    result = subprocess.run(
        cmd, cwd=str(workspace), capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        return {
            "status": "error",
            "error": f"claude exited {result.returncode}: {result.stderr[:2000]}",
            "findings": [],
        }

    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "status": "error",
            "error": f"non-JSON envelope: {result.stdout[:2000]}",
            "findings": [],
        }

    if envelope.get("is_error"):
        return {
            "status": "error",
            "error": f"claude reported an error: {envelope.get('result', '')[:2000]}",
            "findings": [],
        }

    final_text = envelope.get("result", "")
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
    findings_obj["usage"] = {
        "total_cost_usd": envelope.get("total_cost_usd"),
        "input_tokens": envelope.get("usage", {}).get("input_tokens"),
        "output_tokens": envelope.get("usage", {}).get("output_tokens"),
        "cache_read_tokens": envelope.get("usage", {}).get("cache_read_input_tokens"),
    }
    return findings_obj


def main():
    review_dir = Path(sys.argv[1])
    model = sys.argv[2] if len(sys.argv) > 2 else "claude-sonnet-5"
    out = run(review_dir, model)
    out_dir = review_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "findings.json").write_text(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
