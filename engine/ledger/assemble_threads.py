#!/usr/bin/env python3
"""Assembles the threads.json that capture_explicit.py consumes, from the GitHub
review-comment API. Network I/O only -- all classification lives in
capture_explicit.py so it stays unit-testable.

For each inline review comment that carries a `<!-- quorum:finding_key=... -->`
marker (posted by post_review.py), collects its reply bodies and its reaction
contents, and pairs it with the matching finding from the run's findings.json.

Same urllib / --api-base approach as post_review.py and resolve_pr.py, so it
works on github.com and GHES alike.

NOTE: not yet exercised against a live API (see docs/roadmap.md M2 open items).
The comment/reply/reaction endpoint shapes follow the documented REST v3 API.

Usage:
  assemble_threads.py --findings <findings.json> --repo <owner/repo> --pr <n> \
    --out <threads.json> [--api-base <url>] [--token <tok>]
"""
import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from capture_explicit import parse_marker  # noqa: E402


def _get(url: str, token: str) -> list:
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
    })
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"GET {url} -> {e.code}: {e.read().decode()[:300]}") from e


def _paginate(base_url: str, token: str) -> list:
    out, page = [], 1
    while True:
        sep = "&" if "?" in base_url else "?"
        batch = _get(f"{base_url}{sep}per_page=100&page={page}", token)
        if not batch:
            break
        out.extend(batch)
        if len(batch) < 100:
            break
        page += 1
    return out


def assemble(findings_obj: dict, repo: str, pr: int, token: str,
             api_base: str = "https://api.github.com") -> list:
    findings_by_key = {
        f.get("finding_key"): f
        for f in findings_obj.get("findings", [])
        if f.get("finding_key")
    }
    comments = _paginate(f"{api_base}/repos/{repo}/pulls/{pr}/comments", token)

    # marker comment id -> finding_key
    marker_comments = {}
    for c in comments:
        key = parse_marker(c.get("body", ""))
        if key:
            marker_comments[c["id"]] = key

    threads = []
    for comment_id, finding_key in marker_comments.items():
        replies = [
            c.get("body", "") for c in comments
            if c.get("in_reply_to_id") == comment_id
        ]
        try:
            reactions = [
                r.get("content")
                for r in _get(f"{api_base}/repos/{repo}/pulls/comments/{comment_id}/reactions", token)
            ]
        except RuntimeError:
            reactions = []
        threads.append({
            "finding_key": finding_key,
            "finding": findings_by_key.get(finding_key, {"finding_key": finding_key}),
            "replies": replies,
            "reactions": reactions,
        })
    return threads


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--findings", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", required=True, type=int)
    ap.add_argument("--out", required=True)
    ap.add_argument("--api-base", default="https://api.github.com")
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
    args = ap.parse_args()

    if not args.token:
        print("no GITHUB_TOKEN / GH_TOKEN available; skipping explicit capture", file=sys.stderr)
        Path(args.out).write_text("[]")
        return

    findings_obj = json.loads(Path(args.findings).read_text())
    threads = assemble(findings_obj, args.repo, args.pr, args.token, args.api_base)
    Path(args.out).write_text(json.dumps(threads, indent=2, ensure_ascii=False))
    print(f"assembled {len(threads)} marker thread(s) -> {args.out}")


if __name__ == "__main__":
    main()
