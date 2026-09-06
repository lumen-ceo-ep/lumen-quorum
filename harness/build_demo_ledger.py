#!/usr/bin/env python3
"""Builds a synthetic-but-realistic feedback ledger for demo-project, so the M2
pipeline (engine/ledger/) has a concrete worked example in the repo.

Everything here is invented — the same way demo-project/invariants.md and the
example PRs are invented — purely to exercise the engine. The scenario below is
written to hit both of promote.py's recommendation branches:

  * INV-2 (priority clamp): reviewers keep citing it, humans keep replying "we
    clamp on purpose now" -> a `corrected` cluster -> proposal to re-examine the
    rule.
  * a bulk-enqueue false-positive pattern with no cited rule: a blocking
    correctness finding that keeps merging unchanged -> an `ignored` cluster ->
    proposal for a constitution note.
  * INV-1 (cancelled->running): findings that keep getting fixed -> `accepted`
    records that correctly do NOT cluster (the system working).

Run: python3 harness/build_demo_ledger.py   (writes demo-project/ledger/)
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine" / "ledger"))
from record import append_records, load_records, make_record, stamp_keys  # noqa: E402
from cluster import cluster  # noqa: E402
from promote import render_document  # noqa: E402

LEDGER_DIR = REPO_ROOT / "demo-project" / "ledger"
LEDGER = LEDGER_DIR / "ledger.jsonl"
PROPOSALS = LEDGER_DIR / "proposals.md"
REPO = "lumen-ceo-ep/lumen-quorum"


def f(file, line, category, refs):
    # stamp keys the way the adapter's postprocess would
    return stamp_keys({
        "file": file, "line": line, "category": category, "severity": "blocking",
        "claim": f"synthetic {category} finding on {file}:{line}",
        "evidence": [{"type": "project", "ref": r} for r in refs],
    })


# (pr, finding, verdict, signal, detail)
SCENARIO = [
    # INV-2 disputed across 4 PRs -> corrected cluster
    (301, f("demo-project/codebase/queue/enqueue.py", 22, "convention", ["invariants.md#INV-2"]),
     "corrected", "explicit", "reply: we clamp on purpose since the scheduler rework"),
    (309, f("demo-project/codebase/queue/enqueue.py", 24, "convention", ["invariants.md#INV-2"]),
     "corrected", "explicit", "reply: working as intended, clamp is deliberate"),
    (317, f("demo-project/codebase/queue/enqueue.py", 21, "convention", ["invariants.md#INV-2"]),
     "corrected", "explicit", "reply: this rule is stale"),
    (326, f("demo-project/codebase/queue/enqueue.py", 23, "convention", ["invariants.md#INV-2"]),
     "corrected", "explicit", "reply: not a bug, see scheduler ADR"),

    # bulk-enqueue false-positive pattern, no cited rule, merged unchanged x3 -> ignored cluster
    (305, f("demo-project/codebase/queue/enqueue.py", 40, "correctness", []),
     "ignored", "implicit", "blocking correctness finding; cited line unchanged at merge"),
    (312, f("demo-project/codebase/queue/enqueue.py", 41, "correctness", []),
     "ignored", "implicit", "blocking correctness finding; cited line unchanged at merge"),
    (321, f("demo-project/codebase/queue/enqueue.py", 39, "correctness", []),
     "ignored", "implicit", "blocking correctness finding; cited line unchanged at merge"),

    # INV-1 findings that got fixed -> accepted, should NOT cluster
    (302, f("demo-project/codebase/queue/lifecycle.py", 18, "convention", ["invariants.md#INV-1"]),
     "accepted", "explicit", "reply: good catch, reverting the transition"),
    (310, f("demo-project/codebase/queue/lifecycle.py", 18, "convention", ["invariants.md#INV-1"]),
     "accepted", "explicit", "reply: fixed"),
    (319, f("demo-project/codebase/queue/lifecycle.py", 19, "convention", ["invariants.md#INV-1"]),
     "accepted", "explicit", "reply: addressed in a follow-up commit"),
]


def main():
    LEDGER_DIR.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text("")  # rebuild from scratch each run — this is a fixture

    records = [
        make_record(repo=REPO, pr=pr, finding=finding, verdict=verdict,
                    signal=signal, detail=detail, run_id=f"synthetic-{pr}",
                    ts=f"2026-{7 + i // 28:02d}-{(i % 28) + 1:02d}T12:00:00Z",
                    id=f"synthetic-{pr}-{verdict}")  # deterministic: this is a committed fixture
        for i, (pr, finding, verdict, signal, detail) in enumerate(sorted(SCENARIO))
    ]
    written = append_records(LEDGER, records)

    clusters = cluster(load_records(LEDGER))
    PROPOSALS.write_text(render_document(clusters))

    print(f"wrote {written} records -> {LEDGER}")
    print(f"wrote {len(clusters)} cluster proposal(s) -> {PROPOSALS}")
    for c in clusters:
        print(f"  - {c['file_pattern']} / {c['category']} / "
              f"{', '.join(c['cited_refs']) or 'no rule'}: {c['dominant_verdict']} "
              f"x{c['occurrence_count']} PRs")


if __name__ == "__main__":
    main()
