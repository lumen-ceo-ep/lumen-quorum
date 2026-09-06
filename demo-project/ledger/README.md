# demo-project feedback ledger

`ledger.jsonl` — append-only, one JSON record per finding-per-signal, written by
`.github/workflows/quorum-ledger.yml` when a PR touching `../codebase/` merges.
`proposals.md` — regenerated each run: clusters of repeated `ignored`/`corrected`
verdicts, as **proposed** (never auto-applied) changes to `../invariants.md` /
`../constitution.md`.

For this demo the ledger lives on the trunk of the repo under review — a
deliberate M2-demo shortcut. A real adopting team keeps its ledger in its own
knowledge repo, separate from any one review run and from the engine
(`docs/architecture.md` sec. 1, 5).

Schema and semantics: `engine/ledger/README.md`.
