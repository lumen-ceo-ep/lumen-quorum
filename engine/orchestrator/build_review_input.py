#!/usr/bin/env python3
"""Builds a review/ input directory (see docs/architecture.md sec. 2) for a single
PR against a given project directory, ready to hand to a node adapter.

Usage:
  build_review_input.py --base <sha> --head <sha> --project <dir> --out <dir> [--lang <code>]
"""
import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
ROLE_FILE = REPO_ROOT / "harness" / "role.md"
DEFAULT_LANGUAGE = "en"


def load_profile(project_dir: Path) -> dict:
    profile_path = project_dir / "profile.yaml"
    if not profile_path.exists() or yaml is None:
        return {}
    try:
        return yaml.safe_load(profile_path.read_text()) or {}
    except yaml.YAMLError:
        return {}


def resolve_language(override: str, profile: dict) -> tuple:
    """Precedence: explicit override > project's profile.yaml > default.

    Pure function (no filesystem access) so it's unit-testable without a real
    profile.yaml on disk -- see tests/test_language.py.
    """
    profile_language = (profile.get("output") or {}).get("language")
    if override:
        return override, "override"
    if profile_language:
        return profile_language, "profile"
    return DEFAULT_LANGUAGE, "default"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", required=True)
    ap.add_argument("--head", required=True)
    ap.add_argument("--project", required=True, help="path to a project dir with constitution.md/invariants.md/profile.yaml")
    ap.add_argument("--out", required=True)
    ap.add_argument(
        "--lang",
        default=None,
        help="Output language override (e.g. 'ko', 'Korean', '한국어'). "
             "Takes priority over the project's profile.yaml output.language, "
             "which itself takes priority over the default (%(default)s)." % {"default": DEFAULT_LANGUAGE},
    )
    args = ap.parse_args()

    out = Path(args.out)
    input_dir = out / "input"
    input_dir.mkdir(parents=True, exist_ok=True)

    diff = subprocess.run(
        ["git", "diff", f"{args.base}...{args.head}"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, check=True,
    ).stdout
    (input_dir / "diff.patch").write_text(diff)
    diff_sha = hashlib.sha256(diff.encode()).hexdigest()[:12]

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

    profile = load_profile(project_dir)
    language, language_source = resolve_language(args.lang, profile)

    # manifest.json is the run's audit record (docs/architecture.md sec. 7):
    # what corpus/diff/settings actually produced this run's verdict, so a later
    # "why did this differ from last time" question has a real answer instead of
    # a guess.
    manifest = {
        "base": args.base,
        "head": args.head,
        "diff_sha": diff_sha,
        "language": language,
        "language_source": language_source,
    }
    (input_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

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

    print(f"review input built at {out} (language={language}, source={manifest['language_source']})")
    if not diff.strip():
        print("warning: empty diff between base and head")


if __name__ == "__main__":
    main()
