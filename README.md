# Quorum

Quorum is a code-review engine, not a code reviewer. It doesn't know anything about
your codebase on its own — every team that runs it feeds it their own knowledge (a
"project": conventions, architecture decisions, invariants) and gets reviews that are
grounded in that knowledge instead of a generic model prior. The engine itself never
absorbs or retains a project's content between runs; it's read as input at review time.

Two failure modes motivated this, both observed firsthand in real AI-assisted review
work: a single reviewer's verdict is only as good as its grasp of project-specific
context, and it's easy to trust one agent's take as the only source of truth when it
isn't. Quorum's answer is structural, not a bigger prompt: independent review passes,
evidence-gated findings (a claim without a cited code/rule reference doesn't survive),
and disagreement that stays visible instead of getting averaged away.

## What it is

- A **reviewer node contract**: a filesystem-based input/output boundary any AI coding
  agent can implement — feed it a diff, a project's knowledge base, and a role; get back
  structured, evidence-cited findings. Vendor-agnostic by construction.
- A **project knowledge layer**: your team's conventions and invariants, kept as plain
  versioned markdown, separate from the engine and separate from any one review run.
- A **convergence stage**: independent findings get mechanically deduplicated, then
  checked against actual code and actual rules — not popularity-voted. Findings that
  can't be verified either way stay visibly unresolved rather than being forced to a
  false consensus.
- A **CI-native surface**: runs as a reusable GitHub Actions workflow, posts real inline
  PR comments, and never claims a merge decision — that stays with a human, always.

## What it deliberately doesn't do (yet)

- It doesn't approve or reject PRs. It surfaces findings; humans decide.
- It doesn't fine-tune or retrain anything. Growth happens through a reviewed,
  human-approved knowledge base, not model weights.
- It doesn't assume multiple AI vendors are independent of each other. That's an
  empirical question the project measures rather than assumes — see `docs/`.

## Status

Pre-MVP. Currently validating whether feeding a project's own knowledge into a single
review pass produces a measurable accuracy improvement over an unaided reviewer, against
a synthetic demo project (`demo-project/`) before anything else gets built. See
`docs/roadmap.md`.

## License

[Business Source License 1.1](LICENSE) — source-available now, free to use and
self-host (including internal commercial use), with the sole restriction that nobody
may offer this as a competing hosted/managed review service. Converts automatically to
Apache License 2.0 on 2030-08-26.
