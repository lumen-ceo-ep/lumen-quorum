# Roles

One `role.md` per reviewer persona. `build_review_input.py` / `run_roles.py` copy
exactly one of these into a node's `review/input/role.md` (the node contract,
`docs/architecture.md` sec. 2).

| role | scope | milestone |
|---|---|---|
| `generalist` | correctness + convention + simplification in one pass | M0 / M1 (single node) |
| `correctness` | wrong behaviour on a concrete input; every finding needs a `failure_scenario` | M3 fan-out |
| `convention` | contradicts a **cited** project rule; no citation → not a finding | M3 fan-out |
| `simplification` | clear duplication of logic that already exists in the workspace | M3 fan-out |

The three specialists each tell the node it is one of several independent reviewers
and to stay in its lane, so their findings are genuinely separable — which is what
makes "did this role surface something no other role did" (M3's stop condition) a
fair question.

Adding a role: drop in `<name>.md`, then `--roles …,<name>` picks it up. Measure its
marginal contribution before keeping it.
