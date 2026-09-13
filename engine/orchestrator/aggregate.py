#!/usr/bin/env python3
"""Stage 1 convergence: mechanical clustering of findings from several nodes.

docs/architecture.md sec. 3, Stage 1: "Findings from every node are grouped by
(file, hunk, category). Pure deduplication, fully deterministic and auditable."
No model call. No adjudication (that's Stage 2 / M4). For M3 the only judgement
this output carries is *how many roles independently raised each cluster* --
shown, not voted on.

Two rules from the architecture doc are load-bearing here:

- **A node that errored is not a clean vote.** Its status is recorded in `nodes`;
  it contributes no findings and never makes the aggregate look cleaner than it is.
  If every node errored, the aggregate status is "error", not "ok with no findings".
- **Nothing is deleted, only grouped.** Every raw finding is preserved under its
  cluster's `members`, with the role that raised it. The cluster's top-level fields
  are a *representative* (highest severity, then highest confidence), not a merge
  that loses information.

Input: an ordered list of (role_name, findings_obj) pairs -- each findings_obj is
one node's `review/out/findings.json`.
"""
import argparse
import json
import sys
from pathlib import Path

SEVERITY_RANK = {"nit": 0, "minor": 1, "major": 2, "blocking": 3}
RANK_SEVERITY = {v: k for k, v in SEVERITY_RANK.items()}
DEFAULT_PROXIMITY = 3


def _rep_sort_key(member: dict):
    f = member["finding"]
    return (
        SEVERITY_RANK.get(f.get("severity", "nit"), 0),
        f.get("confidence") or 0.0,
    )


def _merge_evidence(members: list) -> list:
    seen, out = set(), []
    for m in members:
        for e in m["finding"].get("evidence") or []:
            key = (e.get("type"), e.get("ref"))
            if key not in seen:
                seen.add(key)
                out.append(e)
    return out


def _cluster_bucket(findings_with_role: list, proximity: int) -> list:
    """One (file, category) bucket -> list of clusters, each a list of member
    dicts {"role":..., "finding":...}. A finding joins the open cluster when its
    line is within `proximity` of any line already in that cluster; otherwise it
    starts a new one. Deterministic: input is pre-sorted by line.
    """
    clusters = []
    for member in sorted(findings_with_role, key=lambda m: m["finding"].get("line") or 0):
        line = member["finding"].get("line") or 0
        placed = False
        for cl in clusters:
            if any(abs(line - (o["finding"].get("line") or 0)) <= proximity for o in cl):
                cl.append(member)
                placed = True
                break
        if not placed:
            clusters.append([member])
    return clusters


def aggregate(node_outputs: list, proximity: int = DEFAULT_PROXIMITY) -> dict:
    nodes_meta = []
    members_by_bucket = {}
    ok_nodes = 0

    for role, obj in node_outputs:
        status = obj.get("status", "ok")
        findings = obj.get("findings", []) if status == "ok" else []
        nodes_meta.append({
            "role": role,
            "status": status,
            "n_findings": len(findings),
            "error": obj.get("error") if status != "ok" else None,
        })
        if status != "ok":
            continue
        ok_nodes += 1
        for f in findings:
            bucket = (f.get("file"), f.get("category"))
            members_by_bucket.setdefault(bucket, []).append({"role": role, "finding": f})

    clusters = []
    for (file, category), members in members_by_bucket.items():
        for group in _cluster_bucket(members, proximity):
            rep = max(group, key=_rep_sort_key)["finding"]
            roles = sorted({m["role"] for m in group})
            top_rank = max(SEVERITY_RANK.get(m["finding"].get("severity", "nit"), 0) for m in group)
            clusters.append({
                "file": file,
                "line": rep.get("line"),
                "category": category,
                "severity": RANK_SEVERITY[top_rank],
                "claim": rep.get("claim"),
                "failure_scenario": rep.get("failure_scenario"),
                "evidence": _merge_evidence(group),
                "confidence": rep.get("confidence"),
                "finding_key": rep.get("finding_key"),
                "cluster_key": rep.get("cluster_key"),
                "raised_by": roles,
                "roles_count": len(roles),
                "members": [
                    {"role": m["role"],
                     "severity": m["finding"].get("severity"),
                     "claim": m["finding"].get("claim"),
                     "line": m["finding"].get("line"),
                     "confidence": m["finding"].get("confidence")}
                    for m in group
                ],
            })

    clusters.sort(key=lambda c: (
        -SEVERITY_RANK.get(c["severity"], 0),
        -c["roles_count"],
        c["file"] or "",
        c["line"] or 0,
    ))

    if ok_nodes == 0:
        status = "error"
    elif ok_nodes < len(node_outputs):
        status = "partial"
    else:
        status = "ok"

    out = {
        "status": status,
        "stage": "mechanical-cluster",
        "nodes": nodes_meta,
        "findings": clusters,
        "coverage": _merge_coverage(node_outputs),
        "usage": _sum_usage(node_outputs),
    }
    if status != "ok":
        # a top-level summary, not just per-node detail in `nodes` -- callers
        # like backtest.py print obj.get("error") on any non-"ok" status, and a
        # missing key there silently prints "None" instead of what broke.
        out["error"] = "; ".join(
            f"{n['role']}: {n['error']}" for n in nodes_meta if n["status"] != "ok"
        )
    return out


def _merge_coverage(node_outputs: list) -> dict:
    files_read, missing, reasons = set(), set(), []
    files_in_diff = 0
    for _role, obj in node_outputs:
        cov = obj.get("coverage") or {}
        files_in_diff = max(files_in_diff, cov.get("files_in_diff") or 0)
        files_read.update(cov.get("files_read") or [])
        missing.update(cov.get("mechanically_verified_missing") or [])
        if cov.get("not_read_reason"):
            reasons.append(cov["not_read_reason"])
    # a file only counts as missing if *no* node read it
    missing -= files_read
    out = {"files_in_diff": files_in_diff, "files_read": sorted(files_read)}
    if missing:
        out["mechanically_verified_missing"] = sorted(missing)
        out["not_read_reason"] = "; ".join(sorted(set(reasons))) or "no node read this file"
    return out


def _sum_usage(node_outputs: list) -> dict:
    total = {"total_cost_usd": 0.0, "input_tokens": 0, "output_tokens": 0}
    any_cost = False
    for _role, obj in node_outputs:
        u = obj.get("usage") or {}
        if u.get("total_cost_usd") is not None:
            total["total_cost_usd"] += u["total_cost_usd"]
            any_cost = True
        total["input_tokens"] += u.get("input_tokens") or 0
        total["output_tokens"] += u.get("output_tokens") or 0
    if not any_cost:
        total["total_cost_usd"] = None
    return total


def _load_pairs(specs: list) -> list:
    out = []
    for spec in specs:
        role, _, path = spec.partition("=")
        if not path:
            raise SystemExit(f"--node expects role=path, got {spec!r}")
        out.append((role, json.loads(Path(path).read_text())))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--node", action="append", required=True, metavar="ROLE=findings.json",
                    help="repeatable: one node's role name and its findings.json path")
    ap.add_argument("--proximity", type=int, default=DEFAULT_PROXIMITY)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    result = aggregate(_load_pairs(args.node), proximity=args.proximity)
    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.out:
        Path(args.out).write_text(text)
        print(f"aggregated {len(args.node)} node(s) -> {len(result['findings'])} cluster(s) "
              f"[status={result['status']}] -> {args.out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
