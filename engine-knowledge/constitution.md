# Constitution — the Quorum engine reviewing itself

This is the knowledge base Quorum loads when it reviews a change to **its own**
`engine/`, `harness/`, or `.github/workflows/`. Quorum is its own first adopter
(`docs/roadmap.md` M6 spirit, pulled forward): every PR to this repo is a real
M1/M2 data point instead of a synthetic one.

It is a *project* in exactly the sense `docs/architecture.md` sec. 1 means — data
the engine reads at review time, versioned next to the code, entirely separate
from the engine mechanism and from `demo-project/` (which stays the isolated,
knowledge-free M0 fixture and must not gain real rules).

## Rubric

- A finding must cite a concrete code reference **or** a rule in `invariants.md`.
  A claim with neither is not a finding — this is the same evidence gate the
  engine enforces on every other project.
- Severity: `blocking` (breaks a stated invariant, or a correctness bug on a
  realistic input), `major` (real but recoverable), `minor`, `nit`.
- Scope is correctness, documented-invariant violations, and clear duplication of
  logic already in the tree. Not style, not naming, not formatting.
- Don't restate what the diff does. State what breaks, concretely.

## What this codebase is trying to be

Read these as the *why* behind `invariants.md`; cite the specific `INV-*` when
flagging, not this section.

- **The engine is a mechanism; a project is data.** Nothing under `engine/` may
  hard-code a specific company, repo, vendor-beyond-its-adapter, or project's
  content. `docs/architecture.md` sec. 1.
- **Mechanical beats prompt.** Anything the pipeline guarantees — the evidence
  gate, coverage verification, the refutation-needs-a-counter-reference rule — is
  enforced in code, not asked for in a prompt the model can ignore.
- **Nothing is deleted, only demoted with a reason.** Every raw node finding
  survives in the output. Stages lower severity and record why.
- **A silently-dead node is not a clean vote.** `status` is mandatory; an error
  is `status: "error"`, never an empty `findings` array.
- **A node never has write access.** Posting uses a repo-scoped credential in a
  separate job; a node process only ever reads.
- **Untrusted input stays data.** The diff, file contents, and PR title/body are
  never instructions and never interpolated raw into a shell.
- **Measure before building the next layer.** Every milestone has a stop
  condition; a change that would let the pipeline skip one is suspect.
