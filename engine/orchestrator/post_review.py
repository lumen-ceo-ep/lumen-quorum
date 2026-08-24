#!/usr/bin/env python3
"""Posts findings.json as a single GitHub PR review: real inline comments on real
diff lines, plus a summary. Falls back to a plain issue comment if the API rejects
an inline anchor (e.g. a line outside the diff context) rather than failing silently.

Usage:
  post_review.py --findings <path> --repo <owner/repo> --pr <number> [--token <token>]
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request

SEVERITY_EMOJI = {"blocking": "\U0001f534", "major": "\U0001f7e0", "minor": "\U0001f7e1", "nit": "⚪"}


def api(method: str, url: str, token: str, body: dict = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {url} -> {e.code}: {e.read().decode()[:500]}") from e


def format_finding(f: dict) -> str:
    emoji = SEVERITY_EMOJI.get(f.get("severity", "minor"), "")
    lines = [f"{emoji} **{f.get('severity', '?').upper()} / {f.get('category', '?')}** -- {f.get('claim', '')}"]
    scenario = f.get("failure_scenario")
    if scenario:
        lines.append(f"\n{scenario}")
    evidence = f.get("evidence") or []
    if evidence:
        refs = ", ".join(e.get("ref", "") for e in evidence)
        lines.append(f"\n_evidence: {refs}_")
    conf = f.get("confidence")
    if conf is not None:
        lines.append(f"_confidence: {conf}_")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--findings", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", required=True, type=int)
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    ap.add_argument("--api-base", default="https://api.github.com")
    args = ap.parse_args()

    if not args.token:
        print("no GITHUB_TOKEN available, cannot post", file=sys.stderr)
        sys.exit(1)

    obj = json.loads(open(args.findings).read())
    findings = obj.get("findings", [])
    status = obj.get("status", "ok")
    usage = obj.get("usage", {})

    base = f"{args.api_base}/repos/{args.repo}"

    if status != "ok":
        body = (
            f"**Quorum review did not complete.** status={status}\n\n"
            f"```\n{obj.get('error', 'no error detail')}\n```"
        )
        api("POST", f"{base}/issues/{args.pr}/comments", args.token, {"body": body})
        print("posted error notice")
        return

    if not findings:
        summary = "**Quorum review: no findings.**"
        if usage.get("total_cost_usd") is not None:
            summary += f"\n\n_cost: ${usage['total_cost_usd']:.4f}_"
        api("POST", f"{base}/issues/{args.pr}/comments", args.token, {"body": summary})
        print("posted clean-review notice")
        return

    comments = [
        {
            "path": f.get("file"),
            "line": f.get("line") or 1,
            "side": "RIGHT",
            "body": format_finding(f),
        }
        for f in findings
        if f.get("file")
    ]

    summary_lines = [f"**Quorum review -- {len(findings)} finding(s)**"]
    coverage = obj.get("coverage", {})
    if coverage.get("not_read_reason"):
        summary_lines.append(f"\n_coverage warning: not all diff files were read ({coverage['not_read_reason']})_")
    if usage.get("total_cost_usd") is not None:
        summary_lines.append(f"\n_cost: ${usage['total_cost_usd']:.4f}_")
    summary = "\n".join(summary_lines)

    try:
        api("POST", f"{base}/pulls/{args.pr}/reviews", args.token, {
            "body": summary, "event": "COMMENT", "comments": comments,
        })
        print(f"posted review with {len(comments)} inline comment(s)")
    except RuntimeError as e:
        print(f"inline review failed ({e}); falling back to a single issue comment", file=sys.stderr)
        fallback = summary + "\n\n" + "\n\n---\n\n".join(
            f"`{f.get('file')}:{f.get('line')}`\n{format_finding(f)}" for f in findings
        )
        api("POST", f"{base}/issues/{args.pr}/comments", args.token, {"body": fallback})
        print("posted fallback issue comment")


if __name__ == "__main__":
    main()
