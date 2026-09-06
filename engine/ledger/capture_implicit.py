#!/usr/bin/env python3
"""Implicit-signal capture: a blocking/major finding whose line merged unchanged.

The M2 insight (docs/roadmap.md M2): the most common human response to a review
finding isn't a reply or a reaction -- it's merging anyway. If a `blocking` or
`major` finding pointed at a line, and that line's neighbourhood is byte-identical
between the reviewed head and the merged commit, a human looked at it and decided
it didn't need to change. That's a real "ignored" verdict even though nobody
clicked anything.

This module is pure: it takes a findings list and a post-review diff, and returns
ledger records. Fetching the diff (git) and writing the ledger (record.append_*)
is the caller's job, so the classification logic is unit-testable with no git and
no network.

Usage:
  capture_implicit.py --findings <findings.json> --merge-diff <diff.patch> \
    --repo <owner/repo> --pr <n> [--run-id <id>] [--ledger <path>] \
    [--min-severity major] [--window 2]
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record import SIGNALS, append_records, make_record  # noqa: E402,F401

SEVERITY_RANK = {"nit": 0, "minor": 1, "major": 2, "blocking": 3}

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def changed_lines_by_file(diff_text: str) -> dict:
    """Parses a unified diff and returns {file: set(right-side line numbers that
    were added or are context-adjacent to a removal)}. These are the lines that
    "moved" between the two trees. A file that appears in the diff but with no
    added lines (pure deletion) still gets an entry (an empty set means "touched
    but nothing added" -- callers treat presence-in-diff as "changed").
    """
    changed = {}
    current = None
    right_line = 0
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[4:].strip()
            if path.startswith("b/"):
                path = path[2:]
            current = None if path == "/dev/null" else path
            if current is not None:
                changed.setdefault(current, set())
            continue
        if current is None:
            continue
        m = _HUNK_RE.match(line)
        if m:
            right_line = int(m.group(1))
            continue
        if line.startswith("+") and not line.startswith("+++"):
            changed[current].add(right_line)
            right_line += 1
        elif line.startswith("-") and not line.startswith("---"):
            # a removal doesn't advance the right-side cursor, but it does mean
            # the line *at* the current right position changed
            changed[current].add(right_line)
        elif not line.startswith("\\"):  # context line ("\ No newline at end of file" excluded)
            right_line += 1
    return changed


def _file_matches(finding_file: str, diff_files) -> str:
    """Findings use workspace-relative paths ("queue/lifecycle.py"); a real git
    merge diff uses repo-relative paths ("demo-project/codebase/queue/lifecycle.py").
    Match by suffix, same convention as the adapter's coverage check.
    """
    ff = (finding_file or "").strip()
    for df in diff_files:
        if df == ff or df.endswith("/" + ff) or ff.endswith("/" + df):
            return df
    return ""


def detect_ignored(findings: list, diff_text: str, *, min_severity: str = "major",
                   window: int = 2) -> list:
    """Returns the subset of findings that qualify as an implicit "ignored"
    signal: severity >= min_severity, and the finding's line is not within
    `window` lines of any changed line in the merged diff for that file.

    `window` absorbs the normal drift between "the line the model cited" and
    "the line a fix would touch" -- an off-by-two citation shouldn't read as
    "ignored" when the surrounding code clearly did change.
    """
    min_rank = SEVERITY_RANK.get(min_severity, 2)
    changed = changed_lines_by_file(diff_text)
    ignored = []
    for f in findings:
        if SEVERITY_RANK.get(f.get("severity", "nit"), 0) < min_rank:
            continue
        matched = _file_matches(f.get("file"), changed.keys())
        line = f.get("line") or 0
        if not matched:
            # the finding's file wasn't touched at all between review and merge
            ignored.append(f)
            continue
        near = any(abs(line - cl) <= window for cl in changed[matched])
        if not near:
            ignored.append(f)
    return ignored


def records_for(findings: list, diff_text: str, *, repo: str, pr: int,
                run_id: str = "", **kw) -> list:
    return [
        make_record(
            repo=repo, pr=pr, run_id=run_id, finding=f,
            verdict="ignored", signal="implicit",
            detail="blocking/major finding; cited line unchanged at merge",
        )
        for f in detect_ignored(findings, diff_text, **kw)
    ]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--findings", required=True)
    ap.add_argument("--merge-diff", required=True,
                    help="unified diff between the reviewed head and the merged commit")
    ap.add_argument("--repo", required=True)
    ap.add_argument("--pr", required=True, type=int)
    ap.add_argument("--run-id", default="")
    ap.add_argument("--ledger", default=None,
                    help="JSONL ledger to append to; if omitted, records are printed only")
    ap.add_argument("--min-severity", default="major")
    ap.add_argument("--window", type=int, default=2)
    args = ap.parse_args()

    obj = json.loads(Path(args.findings).read_text())
    if obj.get("status") != "ok":
        print(f"findings status={obj.get('status')}, nothing to capture")
        return
    diff_text = Path(args.merge_diff).read_text()

    records = records_for(
        obj.get("findings", []), diff_text,
        repo=args.repo, pr=args.pr, run_id=args.run_id,
        min_severity=args.min_severity, window=args.window,
    )
    if args.ledger:
        written = append_records(args.ledger, records)
        print(f"{written} implicit record(s) appended to {args.ledger} "
              f"({len(records) - written} already present)")
    else:
        print(json.dumps(records, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
