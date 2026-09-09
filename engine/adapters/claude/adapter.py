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


# The model occasionally ends its turn with a prose sentence instead of the bare
# JSON object the prompt asks for (seen on a large self-review diff). One retry
# with an explicit "JSON only" nudge recovers it without failing the whole run.
_RETRY_NUDGE = (
    "\n\nReturn ONLY the single JSON object described in the output contract -- "
    "no prose, no summary, no markdown fences, nothing before or after it."
)


def run(review_dir: Path, model: str) -> dict:
    prompt = build_prompt(review_dir)
    workspace = review_dir / "workspace"

    findings_obj = None
    last_text = ""
    usage = {"total_cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0}
    for attempt in (1, 2):
        p = prompt if attempt == 1 else prompt + _RETRY_NUDGE
        res = invoke(p, model=model, cwd=workspace, append_system=SYSTEM_PROMPT)
        if not res["ok"]:
            return {"status": "error", "error": res["error"], "findings": []}
        # accumulate across every attempt -- a retry's tokens were still spent
        # (same pattern as adjudicate.py's usage merge).
        for k, v in usage_of(res["envelope"]).items():
            usage[k] = (usage[k] or 0) + (v or 0)
        last_text = res["text"]
        try:
            findings_obj = extract_json(last_text)
            break
        except ValueError:
            continue

    if findings_obj is None:
        return {"status": "error",
                "error": "could not extract JSON from model output after 2 attempts",
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
