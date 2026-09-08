# Feedback ledger (M2)

The instrumentation layer: one append-only JSONL record per finding-per-signal,
capturing what a human did with each posted review finding. This is what M1's
stop condition (action-rate / dispute-rate over real traffic) actually measures,
and what M2's promotion step clusters into proposed knowledge-base changes. See
`docs/roadmap.md` M2 and `docs/architecture.md` sec. 9.

## Split

Pure, unit-tested (`tests/test_ledger.py`), no network:

| file | does |
|---|---|
| `record.py` | record schema, `finding_key` / `cluster_key` derivation, JSONL load/append (dedup-aware) |
| `capture_implicit.py` | `blocking`/`major` finding whose cited line merged unchanged → `ignored` |
| `capture_explicit.py` | classify replies / reactions on a posted comment → `accepted` / `corrected` |
| `cluster.py` | group records by `cluster_key` across **distinct PRs**; surface only repeated patterns |
| `promote.py` | render a cluster into a **proposed** (never auto-applied) knowledge-base change |

Network I/O, kept thin and out of the tested core:

| file | does |
|---|---|
| `assemble_threads.py` | builds `capture_explicit`'s input from the GitHub review-comment API |

The workflow shell is `.github/workflows/quorum-ledger.yml`.

## Verdicts

- **accepted** — a human acted on the finding, or replied that they would.
- **corrected** — a human disputed the finding as wrong. The false-positive signal.
- **ignored** — a `blocking`/`major` finding whose line merged unchanged, no reply.
  A real decision even though nobody clicked anything.

## The two keys

- `finding_key` — identity of one specific posted finding. Stable across a
  re-review of unchanged code; survives the evidence gate's claim annotation.
  Embedded in each posted comment as `<!-- quorum:finding_key=… -->` so an
  explicit reply maps back with no prose matching.
- `cluster_key` — deliberately coarse: `(file-pattern, category, cited rule)`.
  What groups findings *across PRs* so a repeated pattern — not one bad day — can
  be proposed as a rule change.

## Clustering bar

A cluster's weight is the number of **distinct PRs** with a qualifying verdict
(`corrected` / `ignored` by default), not the record count. Default threshold is
3 distinct PRs. `accepted` is excluded — a finding that keeps being accepted is
the system working.
