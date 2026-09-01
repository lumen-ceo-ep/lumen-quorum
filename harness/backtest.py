#!/usr/bin/env python3
"""M0 backtest harness.

Replays a corpus of PRs through the Claude adapter twice -- once with no
project knowledge, once with the project's constitution + invariants -- and
scores each run against that PR's ground_truth.json. Prints the corpus lift,
which is the M0 stop/go gate (see docs/roadmap.md).

By default replays the synthetic corpus under demo-project/example-pr/.
Pass --corpus <dir> to replay a different corpus instead -- knowledge files
(constitution.md/invariants.md) live directly in <dir>, and PR fixture dirs
are auto-detected as any immediate subdirectory of <dir> containing a
diff.patch. This is how a real adopting project's own corpus gets replayed
without it ever needing to live under demo-project/ (or, for a company
corpus, anywhere inside this repo at all -- see the isolation note on
--corpus below). Pass --out <dir> to control where results get written;
defaults to harness/results/ for the built-in demo corpus, but an external
--corpus should always pass an explicit --out outside this repo too.
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_PROJECT = REPO_ROOT / "demo-project"
ADAPTER = REPO_ROOT / "engine" / "adapters" / "claude" / "adapter.py"
ROLE_FILE = REPO_ROOT / "harness" / "role.md"

sys.path.insert(0, str(REPO_ROOT / "engine" / "orchestrator"))
from build_review_input import load_profile, resolve_language  # noqa: E402

SEVERITY_RANK = {"nit": 0, "minor": 1, "major": 2, "blocking": 3}


def parse_diff_files(diff_text: str) -> list:
    """Extracts the changed-file list from a unified diff's own +++ headers,
    rather than needing a live `git diff` -- these are static fixture diffs,
    not a real repo's history. Lets the harness exercise the same mechanical
    coverage check (adapter.py's verify_coverage) that live CI runs get.
    """
    files = []
    for line in diff_text.splitlines():
        if line.startswith("+++ "):
            path = line[len("+++ "):].strip()
            if path.startswith("b/"):
                path = path[2:]
            if path != "/dev/null":
                files.append(path)
    return files


def build_review_dir(run_dir: Path, pr_dir: Path, with_knowledge: bool, corpus_root: Path) -> Path:
    review_dir = run_dir / "review"
    input_dir = review_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    shutil.copy(ROLE_FILE, input_dir / "role.md")
    diff_text = (pr_dir / "diff.patch").read_text()
    shutil.copy(pr_dir / "diff.patch", input_dir / "diff.patch")

    if with_knowledge:
        shutil.copy(corpus_root / "constitution.md", input_dir / "constitution.md")
        project_dir = input_dir / "project"
        project_dir.mkdir(exist_ok=True)
        shutil.copy(corpus_root / "invariants.md", project_dir / "invariants.md")

    language, _source = resolve_language(None, load_profile(corpus_root))
    (input_dir / "manifest.json").write_text(json.dumps({
        "files_in_diff": parse_diff_files(diff_text),
        "language": language,
    }))

    workspace_src = pr_dir / "workspace"
    workspace_dst = review_dir / "workspace"
    shutil.copytree(workspace_src, workspace_dst)

    return review_dir


def score(findings: list, ground_truth: dict) -> dict:
    expected = ground_truth.get("expected_findings", [])
    result = {"true_positive": 0, "false_negative": 0, "false_positive": 0, "matched_on": []}

    if not expected:
        fp = [
            f for f in findings
            if SEVERITY_RANK.get(f.get("severity", "nit"), 0) >= SEVERITY_RANK["major"]
        ]
        result["false_positive"] = len(fp)
        result["matched_on"] = [f.get("claim", "") for f in fp]
        return result

    for exp in expected:
        min_rank = SEVERITY_RANK.get(exp.get("min_severity", "minor"), 1)
        cites = [c.lower() for c in exp.get("cites", [])]
        matched = False
        for f in findings:
            if exp["file"] not in f.get("file", ""):
                continue
            if SEVERITY_RANK.get(f.get("severity", "nit"), 0) < min_rank:
                continue
            if cites:
                blob = json.dumps(f).lower()
                if not any(c in blob for c in cites):
                    continue
            matched = True
            result["matched_on"].append(f.get("claim", ""))
            break
        if matched:
            result["true_positive"] += 1
        else:
            result["false_negative"] += 1
    return result


def run_condition(pr_dir: Path, with_knowledge: bool, model: str, keep_dir: Path, corpus_root: Path) -> dict:
    label = "with_knowledge" if with_knowledge else "no_knowledge"
    run_dir = keep_dir / label
    run_dir.mkdir(parents=True, exist_ok=True)
    review_dir = build_review_dir(run_dir, pr_dir, with_knowledge, corpus_root)

    t0 = time.time()
    result = subprocess.run(
        [sys.executable, str(ADAPTER), str(review_dir), model],
        capture_output=True, text=True,
    )
    elapsed = time.time() - t0

    out_path = review_dir / "out" / "findings.json"
    if not out_path.exists():
        return {"status": "error", "error": f"adapter produced no output; stderr: {result.stderr[:1000]}",
                "findings": [], "elapsed_s": elapsed}
    findings_obj = json.loads(out_path.read_text())
    findings_obj["elapsed_s"] = round(elapsed, 1)
    return findings_obj


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("model", nargs="?", default="claude-sonnet-5")
    ap.add_argument(
        "--corpus", default=None,
        help="Path to an external corpus dir (constitution.md/invariants.md in the "
             "root, PR fixture dirs as immediate subdirs containing diff.patch). "
             "Defaults to the built-in demo-project/example-pr/ corpus. For a "
             "company/real-project corpus, always pair this with --out pointing "
             "somewhere outside this repo -- see this file's module docstring.",
    )
    ap.add_argument(
        "--out", default=None,
        help="Where to write results. Defaults to harness/results/<timestamp> for "
             "the built-in corpus; required in practice for any --corpus outside "
             "this repo, so real fixture/finding content never lands in this repo.",
    )
    args = ap.parse_args()
    model = args.model

    if args.corpus:
        corpus_root = Path(args.corpus).resolve()
        pr_dirs = sorted(p for p in corpus_root.iterdir() if (p / "diff.patch").exists())
    else:
        corpus_root = DEMO_PROJECT
        pr_dirs = sorted((DEMO_PROJECT / "example-pr").iterdir())
        pr_dirs = [p for p in pr_dirs if (p / "diff.patch").exists()]

    results_dir = Path(args.out).resolve() if args.out else REPO_ROOT / "harness" / "results" / str(int(time.time()))
    results_dir.mkdir(parents=True, exist_ok=True)

    totals = {
        "no_knowledge": {"tp": 0, "fn": 0, "fp": 0},
        "with_knowledge": {"tp": 0, "fn": 0, "fp": 0},
    }
    rows = []

    for pr_dir in pr_dirs:
        name = pr_dir.name
        ground_truth = json.loads((pr_dir / "ground_truth.json").read_text())
        keep_dir = results_dir / name
        row = {"pr": name}

        for with_knowledge, key in [(False, "no_knowledge"), (True, "with_knowledge")]:
            out = run_condition(pr_dir, with_knowledge, model, keep_dir, corpus_root)
            (keep_dir / f"{key}.json").write_text(json.dumps(out, indent=2))

            if out.get("status") != "ok":
                print(f"[{name}] {key}: ADAPTER ERROR: {out.get('error')}")
                row[key] = {"status": "error"}
                continue

            sc = score(out.get("findings", []), ground_truth)
            totals[key]["tp"] += sc["true_positive"]
            totals[key]["fn"] += sc["false_negative"]
            totals[key]["fp"] += sc["false_positive"]
            sc["cost_usd"] = out.get("usage", {}).get("total_cost_usd")
            row[key] = sc

        rows.append(row)
        print(f"[{name}] no_knowledge={row.get('no_knowledge')} with_knowledge={row.get('with_knowledge')}")

    print("\n=== Summary ===")

    def precision_recall(t):
        tp, fn, fp = t["tp"], t["fn"], t["fp"]
        precision = tp / (tp + fp) if (tp + fp) else 1.0
        recall = tp / (tp + fn) if (tp + fn) else 1.0
        return precision, recall

    p0, r0 = precision_recall(totals["no_knowledge"])
    p1, r1 = precision_recall(totals["with_knowledge"])
    print(f"no_knowledge:   precision={p0:.2f} recall={r0:.2f}  (tp={totals['no_knowledge']['tp']} fn={totals['no_knowledge']['fn']} fp={totals['no_knowledge']['fp']})")
    print(f"with_knowledge: precision={p1:.2f} recall={r1:.2f}  (tp={totals['with_knowledge']['tp']} fn={totals['with_knowledge']['fn']} fp={totals['with_knowledge']['fp']})")
    print(f"lift: precision {p1 - p0:+.2f}, recall {r1 - r0:+.2f}")

    summary = {"model": model, "totals": totals, "rows": rows,
               "lift": {"precision": p1 - p0, "recall": r1 - r0}}
    (results_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    print(f"\nfull results: {results_dir}")


if __name__ == "__main__":
    main()
