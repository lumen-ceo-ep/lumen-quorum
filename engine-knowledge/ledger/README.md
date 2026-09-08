# engine self-review ledger

`ledger.jsonl` / `proposals.md` — written by `.github/workflows/quorum-ledger.yml`
when a merged PR touched `engine/**` (or `harness/**`, `engine-knowledge/**`) and
the self-reviewer had posted findings on it. Records what the humans did with each
finding, and clusters repeated `ignored` / `corrected` verdicts into proposed
changes to `../invariants.md` / `../constitution.md`.

Same schema and semantics as `demo-project/ledger/` — see `engine/ledger/README.md`.
Real data (not a synthetic fixture): this fills up as the repo's own PRs merge.
