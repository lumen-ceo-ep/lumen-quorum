# engine-knowledge

The project knowledge base Quorum loads when it **reviews changes to itself** —
`engine/`, `harness/`, `.github/workflows/`. Quorum is its own first real adopter,
so its own PR flow (this repo's PRs) is a live M1/M2 data source instead of a
synthetic one.

| file | role |
|---|---|
| `constitution.md` | Tier 1 — the engine's own review rubric and design intent |
| `invariants.md` | `ENG-1`..`ENG-10` — checkable claims a reviewer cites |
| `routes.yaml` | changed-file pattern → relevant invariants (Tier 2) |
| `profile.yaml` | output conventions |

This is *data*, exactly like `demo-project/` — read at review time, versioned next
to the code, separate from the engine mechanism. The difference from
`demo-project/`: that one is a deliberately knowledge-free M0 fixture and stays
that way (`ENG-9`); this one is real.

Wired via `.github/workflows/quorum-self-review.yml` (`--project engine-knowledge`)
and the `engine/**` path filter in `quorum-ledger.yml`.
