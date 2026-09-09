#!/usr/bin/env python3
"""Claude adapter.

Renders review/input/ into a headless Claude Code invocation, runs it
read-only against review/workspace/, and normalizes the result into
review/out/findings.json per the schema in docs/architecture.md.

The node writes its findings JSON to a file (review/out/node-findings.json)
with the Write tool rather than returning it as its final chat message -- on a
real multi-file diff the model reliably ends its turn with a prose summary, and
parsing that was the top cause of `status: error` (issue #9). The chat message
is now only a fallback if the file is missing/unreadable.

Usage: adapter.py <review_dir> [model]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import SYSTEM_PROMPT, build_prompt, extract_json, postprocess  # noqa: E402
from claude.invoke import invoke, usage_of  # noqa: E402

_ZERO_USAGE = {"total_cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0}


def _write_instruction(target: Path) -> str:
    return (
        f"\n\n## Deliverable\n"
        f"Write the single JSON object described in the output contract to this exact "
        f"path, using the Write tool:\n    {target}\n"
        f"That file IS the deliverable -- your chat reply is ignored. Write valid JSON "
        f"only (no markdown fences). If you cannot complete the review, write a JSON "
        f"object with \"status\": \"error\" and an \"error\" field to the same path."
    )


def _load_findings(target: Path, chat_text: str):
    """Prefer the file the node wrote; fall back to its chat message."""
    if target.exists():
        try:
            return json.loads(target.read_text())
        except json.JSONDecodeError:
            try:
                return extract_json(target.read_text())
            except ValueError:
                pass
    return extract_json(chat_text)  # raises ValueError if this also fails


def run(review_dir: Path, model: str) -> dict:
    prompt = build_prompt(review_dir)
    workspace = review_dir / "workspace"
    out_dir = review_dir / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / "node-findings.json"
    if target.exists():
        target.unlink()  # never let a previous run's file be read as this run's

    usage = dict(_ZERO_USAGE)
    findings_obj = None
    last_text = ""
    for attempt in (1, 2):
        p = prompt + _write_instruction(target)
        if attempt == 2:
            p += ("\n\nThe deliverable file was not found or was not valid JSON. "
                  "Write it now, valid JSON only.")
        res = invoke(p, model=model, cwd=workspace, append_system=SYSTEM_PROMPT,
                     allowed_tools="Read Glob Grep Write", add_dirs=[out_dir])
        if not res["ok"]:
            return {"status": "error", "error": res["error"], "findings": [], "usage": usage}
        for k, v in usage_of(res["envelope"]).items():
            usage[k] = (usage[k] or 0) + (v or 0)
        last_text = res["text"]
        try:
            findings_obj = _load_findings(target, last_text)
            break
        except ValueError:
            continue

    if findings_obj is None:
        return {"status": "error",
                "error": "node produced no parseable findings (file and chat both failed) after 2 attempts",
                "raw": last_text[:2000], "findings": [], "usage": usage}

    findings_obj = postprocess(review_dir, findings_obj)
    findings_obj["usage"] = usage
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
