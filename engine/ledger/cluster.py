#!/usr/bin/env python3
"""Cluster ledger records into repeated patterns worth acting on.

The M2 bar (docs/roadmap.md M2): "group by (file-pattern, category, cited
invariant) across *repeated* occurrences only, never a single incident." One
reviewer disputing one finding on one bad day is noise. The same kind of finding
being disputed -- or ignored -- across several independent PRs is signal that the
knowledge base, not the reviewer, needs a change.

Counting rule: a cluster's weight is the number of **distinct PRs** with a
qualifying verdict, not the number of records. Three replies on one PR is still
one incident.

Pure functions only -- takes records, returns clusters. No I/O except the CLI.

Usage:
  cluster.py --ledger <path> [--min-occurrences 3] [--verdicts corrected,ignored] [--json]
"""
import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from record import load_records  # noqa: E402

DEFAULT_MIN_OCCURRENCES = 3
# Verdicts that indicate the knowledge base may be off. `accepted` is deliberately
# excluded: a finding that keeps getting accepted is the system working, not a
# reason to change a rule.
DEFAULT_VERDICTS = ("corrected", "ignored")


def cluster(records: list, *, min_occurrences: int = DEFAULT_MIN_OCCURRENCES,
            verdicts=DEFAULT_VERDICTS) -> list:
    verdicts = set(verdicts)
    by_key = defaultdict(list)
    for r in records:
        if r.get("verdict") in verdicts:
            by_key[r.get("cluster_key")].append(r)

    clusters = []
    for key, recs in by_key.items():
        distinct_prs = {r.get("pr") for r in recs}
        if len(distinct_prs) < min_occurrences:
            continue
        verdict_counts = Counter(r["verdict"] for r in recs)
        sample = recs[0]
        clusters.append({
            "cluster_key": key,
            "category": sample.get("category"),
            "file_pattern": sample.get("file_pattern"),
            "cited_refs": sample.get("cited_refs") or [],
            "distinct_prs": sorted(p for p in distinct_prs if p is not None),
            "occurrence_count": len(distinct_prs),
            "verdict_counts": dict(verdict_counts),
            "dominant_verdict": verdict_counts.most_common(1)[0][0],
            "occurrences": sorted(
                ({
                    "pr": r.get("pr"), "verdict": r.get("verdict"),
                    "signal": r.get("signal"), "file": r.get("file"),
                    "line": r.get("line"), "finding_key": r.get("finding_key"),
                    "ts": r.get("ts"),
                } for r in recs),
                key=lambda o: (o["pr"] or 0, o["ts"] or ""),
            ),
        })
    clusters.sort(key=lambda c: (-c["occurrence_count"], c["cluster_key"]))
    return clusters


def format_text(clusters: list) -> str:
    if not clusters:
        return "no clusters at or above the occurrence threshold"
    out = []
    for c in clusters:
        refs = ", ".join(c["cited_refs"]) or "(no cited project rule)"
        out.append(
            f"* {c['file_pattern']} / {c['category']} / {refs}\n"
            f"    {c['occurrence_count']} distinct PRs "
            f"({', '.join(f'{v}×{n}' for v, n in c['verdict_counts'].items())}), "
            f"dominant: {c['dominant_verdict']}\n"
            f"    PRs: {', '.join(f'#{p}' for p in c['distinct_prs'])}"
        )
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", required=True)
    ap.add_argument("--min-occurrences", type=int, default=DEFAULT_MIN_OCCURRENCES)
    ap.add_argument("--verdicts", default=",".join(DEFAULT_VERDICTS),
                    help="comma-separated verdicts that count toward a cluster")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    records = load_records(args.ledger)
    clusters = cluster(
        records,
        min_occurrences=args.min_occurrences,
        verdicts=tuple(v.strip() for v in args.verdicts.split(",") if v.strip()),
    )
    if args.json:
        print(json.dumps(clusters, indent=2, ensure_ascii=False))
    else:
        print(format_text(clusters))


if __name__ == "__main__":
    main()
