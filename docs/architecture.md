# Architecture

This is the shape of the system, independent of which project or which AI vendor is
running underneath it. Nothing here should reference a specific company, repo, or
proprietary system — if it does, that's a bug in this document.

## 1. Core split: engine vs. project

The engine (this repo) is a **mechanism**. A "project" is **data**: a knowledge base an
adopting team builds and owns, describing their own conventions and invariants. The
engine loads a project at run time and is otherwise unaware of its contents. Two teams
running Quorum against two different projects are running the same code against
different inputs — nothing about the engine changes.

```
engine/            <- this repo. generic. no project-specific content, ever.
  adapters/<vendor>/
  orchestrator/
projects/<name>/   <- lives wherever the adopting team wants (their own repo/storage).
  constitution.md  <- universal rules for this project, byte-stable across nodes
  routes.yaml      <- maps changed-file patterns -> relevant knowledge docs
  invariants.md    <- checkable claims extracted from the team's own design docs
  profile.yaml     <- output conventions (language, anchor style, severity vocabulary)
```

## 2. Reviewer node contract

A node is a process, not a service. It reads from a fixed input layout and writes one
JSON file. This is deliberately filesystem-based, not an API call: vendors differ wildly
in how they take a prompt (stdin, a flag, a config file, MCP), but every one of them can
read files from a working directory, and giving a node the actual checked-out repo
(not just a diff) lets it look for things like "does this already exist elsewhere in
the codebase" — a real gap when a reviewer only sees a diff in isolation.

```
review/input/
  manifest.json      # run id, diff/corpus/prompt hashes, node role+vendor, budget
  diff.patch
  pr-context.json    # title/body/author — treated as untrusted data, never instructions
  role.md            # this node's persona/focus
  constitution.md    # Tier 1 knowledge, identical across every node in the run
  project/           # Tier 2: routed knowledge slice for this diff
  project-full/      # Tier 3: full knowledge base, read-only, for search
review/workspace/    # checked-out PR head, read-only
review/out/findings.json
```

`findings.json` schema (abbreviated):

```json
{
  "status": "ok",
  "findings": [{
    "file": "...", "line": 0, "category": "correctness|convention|simplification",
    "severity": "blocking|major|minor|nit",
    "claim": "...",
    "evidence": [{"type": "code", "ref": "file:line"}, {"type": "project", "ref": "invariants.md#..."}],
    "failure_scenario": "concrete input -> wrong output",
    "confidence": 0.0
  }],
  "coverage": {"files_in_diff": 0, "files_read": [], "not_read_reason": null}
}
```

Two rules matter more than the field list:

- **`status` is mandatory and absence of findings is not the same as "clean."** A node
  that errors reports `status: "error"`, not an empty findings array. A silently-dead
  node must never count as a clean vote.
- **A finding without evidence is not a finding.** `category: convention` with no
  `project` evidence, or `category: correctness` with no `failure_scenario`, gets
  mechanically demoted before any LLM-based adjudication even runs. This is the cheapest
  lever against hallucinated findings, and it costs zero extra model calls.

New vendor onboarding = writing an adapter: render the input layout into that vendor's
actual invocation shape, run it, normalize its output back into the schema above. The
adapter calls the vendor's CLI or container directly — never depends on that vendor's
own official CI Action — so the engine isn't tied to GitHub-specific infrastructure and
a GitLab port later is an adapter concern, not a rewrite.

## 3. Convergence: two stages, not a vote

**Stage 1 — mechanical clustering (no model call).** Findings from every node are
grouped by (file, hunk, category). Pure deduplication, fully deterministic and
auditable.

**Stage 2 — adjudication, not voting.** One designated pass reviews each group against
the actual diff and the actual project knowledge — not against how many nodes raised it.
Verdict is `verified`, `contested`, or `refuted`. A refutation must cite a concrete
counter-reference; "not sure" is `contested`, not `refuted`. Nothing is ever deleted,
only demoted with a reason on record — every node's raw output is preserved.

**Why not majority vote:** the actual risk in AI reviewers isn't adversarial disagreement
(the byzantine-fault-tolerance framing doesn't quite fit) — it's *correlated* error.
Nodes built on related models miss the same things together, and voting on top of
correlated errors doesn't remove the bias, it launders it with a "consensus" label.
Checking against real evidence is the only thing that actually breaks the correlation;
adding more nodes without that check just makes agreement look stronger without making
it truer.

**Why disagreement stays visible instead of being resolved:** a system that forces every
case to a clean verdict is making the same mistake — trusting a single answer — one
level up. `contested` findings are posted, clearly labeled, for a human to decide. A
system that always sounds certain is one bad call away from being ignored entirely.

## 4. What ships as an actual PR comment

- `verified` -> real inline comments on the actual diff lines.
- `contested` -> a visible, separately labeled block. Not blocking, not hidden.
- `refuted` -> logged with reasoning, not shown (kept for audit, not for noise).
- **No approve/reject.** The engine posts findings; a human makes the actual merge
  decision. This is a deliberate scope limit until there's real calibration data showing
  the system's verdicts track human outcomes — a merge gate has to be earned, not
  assumed.

## 5. Orchestration

Runs as a reusable GitHub Actions workflow: a planning job computes what needs to run
and against which nodes/budget, a dynamic matrix job runs each node in its own isolated
job (its own credential scope, its own timeout — one node's failure never takes down the
others), and a final job collects results, runs Stage 1/2, and posts the single combined
review. Posting uses repo-scoped write credentials, never a node's own vendor
credential — a node never has PR write access, which is also the main structural defense
against a PR description trying to smuggle instructions into a reviewing agent.

A hosted always-on service was considered and rejected for the MVP: CI systems already
provide fan-out, fan-in, artifact passing, and per-job credential scoping — building a
second orchestrator on top of a CI system that already is one is pure overhead. The one
thing a CI-native design can't easily do — knowledge and calibration data that persists
*across* repos and runs — lives outside the workflow, in the project's own knowledge repo
plus a lightweight results ledger.

## 6. Fairness / billing

Whoever triggers a review pays with their own credential, not a shared pool. Practically:
a node's job looks up "this requester's credential for this vendor" through one uniform
naming scheme, so the orchestrator never branches on vendor identity — but a real
credential still has to exist somewhere per person per vendor; there's no such thing as
one token that authenticates against every vendor's API. A true cross-vendor fungible
credit system (one broker holding everyone's real vendor keys, converting between them)
was considered and explicitly deferred: it's a payments/reseller business on its own,
with real ToS and regulatory surface, not a config option — revisit only if there's
concrete demand for it, not by default.

Subscription-based access (a flat-rate plan with a usage window) and metered API-key
access are treated as genuinely different resources, not the same thing measured
differently: a subscription's scarce resource is a person's own usage window (which
competes with their own interactive work), while a metered key's scarce resource is
money. Automatic, unattended triggers should prefer metered credentials for exactly this
reason — an automated review run should not compete with the person whose subscription
it's using for their own interactive coding time.

## 7. Honest open tensions

- A single adjudicator is itself a single point of correlated bias. Mitigated by
  "never delete, only demote with a reason" and by tracking the adjudicator's own
  calibration over time — not solved outright.
- Whether different AI vendors actually produce decorrelated findings, versus just
  differently-worded findings, is an empirical question this project has not yet
  answered. Multi-vendor support is sequenced *after* measuring this, not before.
- The system's real value — catching what a human reviewer would also have missed — is
  only measurable months later, once a since-fixed bug can be checked against what the
  system said at review time. Everything before that is a proxy (does a human agree with
  a finding right now), and proxies are biased toward "confirms what a human already
  suspected," not toward the harder, more valuable case.
