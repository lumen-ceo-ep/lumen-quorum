# Invariants — the Quorum engine

Checkable claims about `engine/`, `harness/`, and `.github/workflows/`. Each is
something a reviewer can verify against the diff plus the checked-out tree. Cite
the `INV-*` id in a finding's `evidence` as `{"type": "project", "ref":
"invariants.md#ENG-N"}`.

## ENG-1
Every adapter must produce its `review/out/findings.json` by passing the parsed
model output through `common.postprocess()`. `postprocess()` is the single choke
point that stamps ledger keys, runs `apply_evidence_gate()`, and (when a manifest
exists) `verify_coverage()`. An adapter that writes findings.json from its own
assembled dict, bypassing `postprocess()`, defeats all three at once.
(source: `docs/architecture.md` sec. 2; `engine/adapters/common.py`)

## ENG-2
`engine/adapters/common.py` must contain no vendor-specific logic — no vendor
name, CLI flag, auth scheme, or output-envelope shape. Per-vendor code lives only
in `engine/adapters/<vendor>/`. Shared post-processing must behave identically
regardless of which model produced the findings.
(source: `docs/architecture.md` sec. 2)

## ENG-3
No pipeline stage deletes a finding. The evidence gate, Stage 1 aggregation, and
Stage 2 adjudication may only lower severity / re-bucket, and must record the
reason (`evidence_gate_demotions`, a cluster's `members`, an `adjudication`
block). A stage that drops entries from a list instead of demoting them violates
this.
(source: `docs/architecture.md` sec. 2-3)

## ENG-4
A findings object always has a `status`. A node that fails sets `status:
"error"` with an `error` field and `findings: []` — never a bare empty
`findings` array, which downstream would read as "reviewed, nothing wrong".
Aggregation of an all-errored set is `status: "error"`, a partial set is
`"partial"`.
(source: `docs/architecture.md` sec. 2-3; `engine/orchestrator/aggregate.py`)

## ENG-5
The step that posts to GitHub uses a repo-scoped token (`GITHUB_TOKEN` /
`github.token`), never a node's vendor credential, and runs in a job separate
from any node job. A node's job holds `contents: read` only. No adapter or node
code path calls a GitHub write endpoint.
(source: `docs/architecture.md` sec. 5, 8)

## ENG-6
In a workflow, any value derived from `github.event.*.body`, `github.event.*.title`,
`github.event.comment.body`, or a diff is passed to a `run:` script through
`env:` and referenced as a shell variable — never interpolated via `${{ }}`
directly into the script text. GitHub-controlled context
(`github.repository`, `github.api_url`, `github.event.*.number`) is exempt.
(source: `docs/architecture.md` sec. 8.1)

## ENG-7
A new vendor adapter is not relied on until the vendor's *headless / CI* auth has
been confirmed for the target account tier — a working interactive login does not
imply it. The adapter's module docstring states the verification status.
(source: `docs/lessons.md`, "Vendor headless auth can't be assumed")

## ENG-8
Pure logic — output parsing, the evidence gate, coverage verification, routing,
Stage 1 clustering, ledger record/cluster/promote, adjudication bucket rules —
has unit tests under `tests/` that run with no network and no model call, wired
into `.github/workflows/test.yml`. A change to any of these ships with a test.
(source: `docs/roadmap.md` M1 hardening; `tests/`)

## ENG-9
`demo-project/` stays a synthetic, self-contained M0 fixture. It must not gain
real project rules, real repo names, or dependencies on `engine-knowledge/`.
The two knowledge bases are separate adopters.
(source: `docs/architecture.md` sec. 1; `demo-project/constitution.md`)

## ENG-10
A run's `manifest.json` records what produced the result: diff hash, the real
changed-file list (`git diff --name-only`, not parsed from prose), routed doc
refs, resolved language + its source, model id, and node role. A change that
drops a manifest field removes audit ability.
(source: `docs/architecture.md` sec. 2, 7)
