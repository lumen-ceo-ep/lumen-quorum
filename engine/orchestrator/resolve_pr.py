#!/usr/bin/env python3
"""Resolves a PR number to its base/head SHAs via the REST API.

issue_comment events (unlike pull_request events) don't carry base/head SHAs
directly -- a comment on a PR only gives you the PR number. This looks the rest
up, same API-base-aware approach as post_review.py.

Usage: resolve_pr.py --repo <owner/repo> --pr <number> [--api-base <url>] [--token <token>]
Prints two lines to stdout: BASE_SHA=<sha> and HEAD_SHA=<sha>, meant to be
consumed by `$GITHUB_ENV` in a workflow step.
"""
import argparse
import json
import os
import urllib.request


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", required=True, type=int)
    ap.add_argument("--token", default=os.environ.get("GITHUB_TOKEN"))
    ap.add_argument("--api-base", default="https://api.github.com")
    args = ap.parse_args()

    url = f"{args.api_base}/repos/{args.repo}/pulls/{args.pr}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {args.token}",
        "Accept": "application/vnd.github+json",
    })
    with urllib.request.urlopen(req) as resp:
        pr = json.loads(resp.read())

    print(f"BASE_SHA={pr['base']['sha']}")
    print(f"HEAD_SHA={pr['head']['sha']}")


if __name__ == "__main__":
    main()
