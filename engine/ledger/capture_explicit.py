#!/usr/bin/env python3
"""Explicit-signal capture: replies and reactions on a posted review comment.

When a human replies to a Quorum inline comment or reacts to it, that's the
cheapest, highest-confidence signal we get -- and the disagreement case
(`corrected`) is the one M1's stop condition cares most about (docs/roadmap.md
M1: "the fraction later disputed as wrong").

Matching a reply back to a specific finding relies on the hidden marker
`post_review.py` embeds in every comment body:
    <!-- quorum:finding_key=<key> -->
so this module never has to fuzzy-match prose.

Pure classification only. The workflow fetches threads/reactions via the GitHub
API and hands this module a plain JSON structure; nothing here does network I/O.

Usage:
  capture_explicit.py --threads <threads.json> --repo <owner/repo> --pr <n> \
    [--run-id <id>] [--ledger <path>]

threads.json shape (what the workflow assembles from the API):
  [
    {
      "finding_key": "…",            # parsed from the comment marker
      "finding": { …the finding… },  # from the run's findings.json, by key
      "replies": ["looks right, fixing", …],
      "reactions": ["+1", "rocket", …]   # GitHub reaction "content" values
    },
    …
  ]
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record import append_records, make_record, validate_record  # noqa: E402

MARKER_RE = re.compile(r"<!--\s*quorum:finding_key=([0-9a-f]+)\s*-->")

# Coarse, deliberately conservative keyword sets. A reply that matches neither
# produces no record (absence of an explicit signal is not itself a signal --
# capture_implicit handles "merged with no reply"). Ambiguity resolves to
# `corrected`: over-counting disputes is the safer error for M1's dispute-rate
# gate than silently under-counting them.
_ACCEPT_PAT = re.compile(
    r"\b(fixed|fixing|will fix|good catch|nice catch|addressed|done|resolved|"
    r"you'?re right|agreed|makes sense|valid|thanks)\b", re.I,
)
_CORRECT_PAT = re.compile(
    r"\b(wrong|incorrect|false positive|not a bug|disagree|invalid|"
    r"this is fine|working as intended|wai|by design|nope|misread|"
    r"doesn'?t apply|out of scope)\b", re.I,
)

_ACCEPT_REACTIONS = {"+1", "hooray", "rocket", "heart"}
_CORRECT_REACTIONS = {"-1", "confused"}


def classify_reply(text: str):
    """Returns "accepted" | "corrected" | None for one reply body."""
    if not text:
        return None
    correcting = bool(_CORRECT_PAT.search(text))
    accepting = bool(_ACCEPT_PAT.search(text))
    if correcting:
        return "corrected"
    if accepting:
        return "accepted"
    return None


def classify_reactions(reactions):
    """Returns "accepted" | "corrected" | None for a bag of reaction contents.
    A thumbs-down anywhere outweighs thumbs-up (same bias-toward-dispute rule).
    """
    reactions = set(reactions or [])
    if reactions & _CORRECT_REACTIONS:
        return "corrected"
    if reactions & _ACCEPT_REACTIONS:
        return "accepted"
    return None


def parse_marker(comment_body: str):
    m = MARKER_RE.search(comment_body or "")
    return m.group(1) if m else None


def verdict_for_thread(thread: dict):
    """One verdict per thread. A `corrected` from any reply or reaction wins;
    otherwise an `accepted` from any; otherwise None (no explicit signal).
    """
    verdicts = [classify_reply(r) for r in thread.get("replies", [])]
    verdicts.append(classify_reactions(thread.get("reactions", [])))
    if "corrected" in verdicts:
        return "corrected"
    if "accepted" in verdicts:
        return "accepted"
    return None


def records_from_threads(threads: list, *, repo: str, pr: int, run_id: str = "") -> list:
    records = []
    for thread in threads:
        finding = thread.get("finding") or {}
        if not finding.get("finding_key") and thread.get("finding_key"):
            finding = dict(finding, finding_key=thread["finding_key"])
        verdict = verdict_for_thread(thread)
        if verdict is None:
            continue
        rec = make_record(
            repo=repo, pr=pr, run_id=run_id, finding=finding,
            verdict=verdict, signal="explicit",
            detail="from PR comment replies/reactions",
        )
        try:
            validate_record(rec)
        except ValueError as e:
            # A marker with no matching finding in findings.json (shouldn't
            # happen within one run) -- skip it rather than fail the whole
            # capture job on one orphan thread.
            print(f"skipping thread {thread.get('finding_key')}: {e}", file=sys.stderr)
            continue
        records.append(rec)
    return records


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--threads", required=True)
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", required=True, type=int)
    ap.add_argument("--run-id", default="")
    ap.add_argument("--ledger", default=None)
    args = ap.parse_args()

    threads = json.loads(Path(args.threads).read_text())
    records = records_from_threads(threads, repo=args.repo, pr=args.pr, run_id=args.run_id)
    if args.ledger:
        written = append_records(args.ledger, records)
        print(f"{written} explicit record(s) appended to {args.ledger} "
              f"({len(records) - written} already present)")
    else:
        print(json.dumps(records, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
