#!/usr/bin/env python3
"""Builds a review/ input directory (see docs/architecture.md sec. 2) for a single
PR against a given project directory, ready to hand to a node adapter.

Usage:
  build_review_input.py --base <sha> --head <sha> --project <dir> --out <dir>
"""
import argparse
import shutil
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROLE_FILE = REPO_ROOT / "harness" / "role.md"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--project", required=True, help="path to a project dir with constitution.md/invariants.md")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    out = Path(args.out)
    input_dir = out / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    diff = subprocess.run(
        ["git", "diff", f"{args.base}...{args.head}"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, check=True,
    ).stdout
    (input_dir / "diff.patch").write_text(diff)

    shutil.copy(ROLE_FILE, input_dir / "role.md")

    project_dir = Path(args.project)
    constitution = project_dir / "constitution.md"
    if constitution.exists():
        shutil.copy(constitution, input_dir / "constitution.md")

    invariants = project_dir / "invariants.md"
    if invariants.exists():
        proj_out = input_dir / "project"
        proj_out.mkdir(exist_ok=True)
        shutil.copy(invariants, proj_out / "invariants.md")

    # The workspace is the whole checked-out repo at HEAD (the workflow's own
    # actions/checkout step already puts the runner there, at the PR head sha) --
    # not just the project's codebase subdirectory. This matters: diff.patch above
    # is a real `git diff`, so every path in it is repo-relative (e.g.
    # "demo-project/codebase/queue/lifecycle.py"). A node reading files to check
    # context needs that same repo-relative view, or it has to silently reconcile a
    # path-prefix mismatch itself -- which it may not always get right.
    workspace_dst = out / "workspace"
    if workspace_dst.is_symlink() or workspace_dst.exists():
        if workspace_dst.is_dir() and not workspace_dst.is_symlink():
            shutil.rmtree(workspace_dst)
        else:
            workspace_dst.unlink()
    workspace_dst.symlink_to(REPO_ROOT, target_is_directory=True)

    print(f"review input built at {out}")
    if not diff.strip():
        print("warning: empty diff between base and head")


if __name__ == "__main__":
    main()
