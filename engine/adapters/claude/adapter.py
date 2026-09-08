#!/usr/bin/env python3
"""Claude adapter.

Renders review/input/ into a headless Claude Code invocation, runs it
read-only against review/workspace/, and normalizes the result into
review/out/findings.json per the schema in docs/architecture.md.

Usage: adapter.py <review_dir> [model]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import SYSTEM_PROMPT, build_prompt, extract_json, postprocess  # noqa: E402
from claude.invoke import invoke, usage_of  # noqa: E402


def run(review_dir: Path, model: str) -> dict:
    prompt = build_prompt(review_dir)
    workspace = review_dir / "workspace"

    res = invoke(prompt, model=model, cwd=workspace, append_system=SYSTEM_PROMPT)
    if not res["ok"]:
        return {"status": "error", "error": res["error"], "findings": []}

    try:
        findings_obj = extract_json(res["text"])
    except ValueError as e:
        return {"status": "error", "error": str(e), "raw": res["text"][:2000], "findings": []}

    findings_obj = postprocess(review_dir, findings_obj)
    findings_obj["usage"] = usage_of(res["envelope"])
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
