# Orchestrator

Turns `review/input/` into posted findings. What's built vs. planned tracks the
roadmap (`docs/roadmap.md`).

| script | stage | status |
|---|---|---|
| `build_review_input.py` | build the input layout for one PR (diff, manifest, Tier 1/2/3 knowledge) | **live** (M1) |
| `route.py` | Tier 2 routing — changed-file globs → the cited knowledge sections | **live** |
| `resolve_pr.py` | PR number → base/head SHAs (for `issue_comment` triggers) | **live** (M1) |
| `post_review.py` | findings.json → one GitHub review with inline comments | **live** (M1) |
| `aggregate.py` | Stage 1 mechanical clustering of multi-node findings | **live** (M3) |
| `run_roles.py` | sequential local fan-out runner (aggregate, optionally adjudicate) | **live** (M3/M4) |
| `adjudicate.py` | Stage 2 verified/contested/refuted, counter-reference rule in code | **live** (M4) |

Fan-in for M3 is `aggregate.py` (mechanical only — no model call, no adjudication).
The single combined GitHub post still goes through `post_review.py`.

M0 doesn't use any of this — the backtest harness (`harness/`) runs a node directly.
