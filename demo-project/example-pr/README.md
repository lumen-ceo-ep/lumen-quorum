# Example PRs

Synthetic PRs against the fictional task-queue described in `../invariants.md`,
each with a known-correct answer (`ground_truth.json`: which findings should
and shouldn't be raised) — the corpus `harness/backtest.py` replays with and
without the project knowledge base loaded.

| fixture | tests |
|---|---|
| `pr-01-cancelled-to-running` | INV-1 violation, single file |
| `pr-02-priority-clamp` | INV-2 violation, single file |
| `pr-03-retry-new-id` | INV-3 violation, single file |
| `pr-04-clean-refactor` | clean change, expects zero findings |
| `pr-05-dequeue-empty-crash` | general correctness bug, no invariant involved |
| `pr-06-bulk-enqueue-false-positive-trap` | structurally-different-but-correct code; expects zero findings despite looking suspicious |
| `pr-07-batch-retry-noisy-diff` | INV-3 violation again, but as the *only* defect inside a 3-file, 30-line diff alongside two unrelated correct helpers, with a docstring arguing for the violation as intentional |

The first six are **M0-sized on purpose**: one file, one obvious defect (or
none), built to answer "does project knowledge help at all" as cleanly as
possible — and they did (`docs/roadmap.md` M0 result). They're too easy to
answer M3's question, though: a generalist already catches all of them, so a
3-role fan-out has nothing left to demonstrate (`docs/roadmap.md` M3 entry,
2026-09-13, "inconclusive by corpus size").

`pr-07` exists specifically to give M3 a fixture where a generalist juggling a
whole diff and a role reading the same diff with one narrow question might
plausibly disagree — same invariant as `pr-03`, but buried instead of
standalone. Run `harness/backtest.py` (whole corpus) vs
`harness/backtest.py --roles correctness,convention,simplification` and diff
the two `summary.json`s to see whether it actually does.
