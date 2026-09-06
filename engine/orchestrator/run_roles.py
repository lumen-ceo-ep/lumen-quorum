#!/usr/bin/env python3
"""M3 fan-out: run one vendor node per role against a prebuilt review dir, then
Stage 1 mechanical aggregation. No adjudication (that's M4).

This is the sequential local runner. The CI shape (docs/architecture.md sec. 5)
is a dynamic matrix -- one isolated job per role, each with its own credential
scope and timeout -- with this script's aggregation step as the fan-in job. Until
that workflow exists, this runs the roles in-process so the harness and a manual
run share one code path.

Each role gets its own review dir: the shared `input/` is reused, only `role.md`
is swapped for `engine/roles/<role>.md`, and `workspace/` points at the same
checked-out tree. So the roles differ *only* in persona -- same diff, same
knowledge, same code -- which is what makes "did this role find something no
other role did" a fair question.

Usage:
  run_roles.py --review-dir <dir> --roles correctness,convention,simplification \
    [--model claude-sonnet-5] [--adapter <path>] --out <aggregate.json>
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENGINE_ROOT = HERE.parent
ROLES_DIR = ENGINE_ROOT / "roles"
DEFAULT_ADAPTER = ENGINE_ROOT / "adapters" / "claude" / "adapter.py"

sys.path.insert(0, str(HERE))
from aggregate import aggregate  # noqa: E402


def _link_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists() or dst.is_symlink():
        return
    try:
        dst.symlink_to(src, target_is_directory=src.is_dir())
    except OSError:
        import shutil
        (shutil.copytree if src.is_dir() else shutil.copy)(src, dst)


def build_role_dir(review_dir: Path, role: str) -> Path:
    role_src = ROLES_DIR / f"{role}.md"
    if not role_src.exists():
        raise SystemExit(f"unknown role {role!r}; have "
                         f"{sorted(p.stem for p in ROLES_DIR.glob('*.md'))}")

    role_dir = review_dir / "roles" / role
    (role_dir / "input").mkdir(parents=True, exist_ok=True)

    for item in (review_dir / "input").iterdir():
        if item.name == "role.md":
            continue
        _link_or_copy(item, role_dir / "input" / item.name)
    (role_dir / "input" / "role.md").write_text(role_src.read_text())

    _link_or_copy(review_dir / "workspace", role_dir / "workspace")
    return role_dir


def run(review_dir: Path, roles: list, model: str, adapter: Path) -> dict:
    node_outputs = []
    for role in roles:
        role_dir = build_role_dir(review_dir, role)
        proc = subprocess.run(
            [sys.executable, str(adapter), str(role_dir), model],
            capture_output=True, text=True, env={**os.environ},
        )
        out_path = role_dir / "out" / "findings.json"
        if out_path.exists():
            obj = json.loads(out_path.read_text())
        else:
            obj = {"status": "error", "findings": [],
                   "error": f"adapter produced no output (exit {proc.returncode}): "
                            f"{proc.stderr[:1000]}"}
        node_outputs.append((role, obj))

    return aggregate(node_outputs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--review-dir", required=True)
    ap.add_argument("--roles", required=True, help="comma-separated role names")
    ap.add_argument("--model", default="claude-sonnet-5")
    ap.add_argument("--adapter", default=str(DEFAULT_ADAPTER))
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    result = run(Path(args.review_dir), roles, args.model, Path(args.adapter))
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"{len(roles)} role(s) -> status={result['status']}, "
          f"{len(result['findings'])} cluster(s) -> {args.out}")


if __name__ == "__main__":
    main()
