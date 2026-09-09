#!/usr/bin/env python3
"""Claude adapter.

Renders review/input/ into a headless Claude Code invocation, runs it
read-only against review/workspace/, and normalizes the result into
review/out/findings.json per the schema in docs/architecture.md.

The node stays strictly read-only (Read/Glob/Grep only -- the workspace is
untrusted checked-out code and a node must never be able to write to it,
docs/architecture.md sec. 8). On a real multi-file diff the model reliably ends
its turn with a prose summary instead of the bare JSON object; when that happens
the adapter does a second, tool-less "reformat this into the findings JSON" call
-- a pure text->JSON transform that can't drift the way a review turn does
(issue #9).

Usage: adapter.py <review_dir> [model]
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from common import FINDINGS_SCHEMA_HINT, SYSTEM_PROMPT, build_prompt, extract_json, postprocess  # noqa: E402
from claude.invoke import invoke, usage_of  # noqa: E402

_ZERO_USAGE = {"total_cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0}

_REFORMAT_SYSTEM = (
    "You convert a code-review analysis into one JSON object. Output ONLY the JSON "
    "object -- no prose, no markdown fences, nothing before or after it."
)


def _add_usage(usage: dict, envelope: dict) -> None:
    for k, v in usage_of(envelope).items():
        usage[k] = (usage[k] or 0) + (v or 0)


def run(review_dir: Path, model: str) -> dict:
    workspace = review_dir / "workspace"
    usage = dict(_ZERO_USAGE)

    res = invoke(build_prompt(review_dir), model=model, cwd=workspace,
                 append_system=SYSTEM_PROMPT, allowed_tools="Read Glob Grep")
    if not res["ok"]:
        return {"status": "error", "error": res["error"], "findings": [], "usage": usage}
    _add_usage(usage, res["envelope"])
    review_text = res["text"]

    try:
        findings_obj = extract_json(review_text)
    except ValueError:
        # The review happened; the model just didn't end with clean JSON. Ask a
        # fresh, tool-less call to reformat what it already produced.
        reformat_prompt = (
            "## Output contract\n" + FINDINGS_SCHEMA_HINT
            + "\n\n## Review analysis to convert\n" + review_text
        )
        # a pure text->JSON transform: no workspace, read-only tools it won't use.
        res2 = invoke(reformat_prompt, model=model, cwd=review_dir,
                      append_system=_REFORMAT_SYSTEM)
        if res2["ok"]:
            _add_usage(usage, res2["envelope"])
        try:
            findings_obj = extract_json(res2["text"] if res2["ok"] else "")
        except ValueError:
            return {"status": "error",
                    "error": "node output was not JSON and the reformat pass also failed",
                    "raw": review_text[:2000], "findings": [], "usage": usage}

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
