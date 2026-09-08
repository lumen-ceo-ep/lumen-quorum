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
    raised_by = f.get("raised_by")
    if raised_by:
        lines.append(f"\n_raised independently by {f.get('roles_count', len(raised_by))} "
                     f"role(s): {', '.join(raised_by)}_")
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
    adj = f.get("adjudication")
    if adj:
        rationale = adj.get("rationale", "")
        ce = adj.get("counter_evidence") or []
        ce_txt = (" — counter-ref: " + ", ".join(e.get("ref", "") for e in ce)) if ce else ""
        lines.append(f"\n_adjudicator: **{adj.get('verdict', '?')}**{ce_txt}_")
        if rationale:
            lines.append(f"_{rationale}_")
    # Hidden marker: lets the M2 feedback ledger's explicit-capture step map a
    # human reply/reaction on this comment back to the exact finding, without
    # fuzzy-matching prose (see engine/ledger/capture_explicit.py). Invisible in
    # rendered Markdown; harmless if the ledger is never run.
    key = f.get("finding_key")
    if key:
        lines.append(f"\n<!-- quorum:finding_key={key} -->")
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

    # "partial" comes from aggregate.py: some nodes ran, at least one errored.
    # Post the findings that did come back, but say so -- a silently-dead node
    # must never look like a clean vote (docs/architecture.md sec. 2, 3).
    node_note = ""
    if obj.get("nodes"):
        failed = [n for n in obj["nodes"] if n.get("status") != "ok"]
        if failed:
            node_note = (
                "\n\n_node warning: " + ", ".join(f"`{n['role']}` ({n['status']})" for n in failed)
                + " did not complete; findings below are from the remaining node(s) only._"
            )

    if status == "error" or (status != "ok" and status != "partial"):
        body = (
            f"**Quorum review did not complete.** status={status}\n\n"
            f"```\n{obj.get('error', 'no error detail')}\n```"
        )
        api("POST", f"{base}/issues/{args.pr}/comments", args.token, {"body": body})
        print("posted error notice")
        return

    # Stage 2 (docs/architecture.md sec. 4): verified -> inline; contested -> a
    # visible, separately-labelled block, not blocking, not hidden; refuted ->
    # kept for audit, not posted as noise. Pre-adjudication output (no `stage`)
    # posts every finding inline, as before.
    adjudicated = obj.get("stage") == "adjudicated"
    if adjudicated:
        def verdict(f):
            return (f.get("adjudication") or {}).get("verdict", "contested")
        inline = [f for f in findings if verdict(f) == "verified"]
        contested = [f for f in findings if verdict(f) == "contested"]
        refuted = [f for f in findings if verdict(f) == "refuted"]
    else:
        inline, contested, refuted = findings, [], []

    # Truly nothing to report only when there are also no refuted findings --
    # a run where the adjudicator refuted everything still has to render the
    # audit block below (ENG-3: nothing is dropped without its reason on record).
    if not findings or (adjudicated and not inline and not contested and not refuted):
        summary = "**Quorum review: no findings.**" + node_note
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
        for f in inline
        if f.get("file")
    ]

    headline = (f"**Quorum review -- {len(inline)} verified" if adjudicated
               else f"**Quorum review -- {len(findings)} finding(s)")
    summary_lines = [headline + ("**" if not adjudicated else
                    f", {len(contested)} contested, {len(refuted)} refuted**") + node_note]
    if adjudicated and contested:
        summary_lines.append("\n### ⚖️ Contested — a human decides\n"
                             "_The adjudicator could not resolve these either way. Not blocking._\n")
        for f in contested:
            summary_lines.append(f"- `{f.get('file')}:{f.get('line')}` — {format_finding(f)}\n")
    if adjudicated and refuted:
        summary_lines.append("\n<details><summary>"
                             f"{len(refuted)} refuted finding(s) (audit log, not shown as review comments)"
                             "</summary>\n")
        for f in refuted:
            summary_lines.append(f"- `{f.get('file')}:{f.get('line')}` — {f.get('claim')}  \n"
                                 f"  _{(f.get('adjudication') or {}).get('rationale', '')}_")
        summary_lines.append("\n</details>")
    coverage = obj.get("coverage", {})
    if coverage.get("not_read_reason"):
        summary_lines.append(f"\n_coverage warning: not all diff files were read ({coverage['not_read_reason']})_")
    if usage.get("total_cost_usd") is not None:
        summary_lines.append(f"\n_cost: ${usage['total_cost_usd']:.4f}_")
    summary = "\n".join(summary_lines)

    if not comments:
        # only refuted (and/or contested) findings -- nothing to anchor inline.
        # Post the summary (which carries the contested block + the refuted audit
        # <details>) as one issue comment.
        api("POST", f"{base}/issues/{args.pr}/comments", args.token, {"body": summary})
        print(f"posted summary-only review ({len(refuted)} refuted, {len(contested)} contested)")
        return

    try:
        api("POST", f"{base}/pulls/{args.pr}/reviews", args.token, {
            "body": summary, "event": "COMMENT", "comments": comments,
        })
        print(f"posted review with {len(comments)} inline comment(s)")
    except RuntimeError as e:
        print(f"inline review failed ({e}); falling back to a single issue comment", file=sys.stderr)
        fallback = summary + "\n\n" + "\n\n---\n\n".join(
            f"`{f.get('file')}:{f.get('line')}`\n{format_finding(f)}" for f in inline
        )
        api("POST", f"{base}/issues/{args.pr}/comments", args.token, {"body": fallback})
        print("posted fallback issue comment")


if __name__ == "__main__":
    main()
