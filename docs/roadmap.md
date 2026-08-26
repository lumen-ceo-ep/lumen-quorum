# Roadmap

Each milestone has an explicit stop condition. The point of writing these down now is
so that "this isn't working, stop and fix the layer below" is a decision made in
advance, not one made under sunk-cost pressure later.

## M0 — Backtest harness (no CI, no live posting)

Replay a set of historical, already-resolved PRs from the synthetic `demo-project/`
through a single node, twice: once with no project knowledge, once with the project's
constitution + routed knowledge. Compare precision and recall-by-proxy (does it match
what the demo project's own historical review comments caught) between the two runs.

**Stop condition: if feeding project knowledge doesn't measurably beat the unaided
baseline, stop here.** Fix the knowledge layer, not the orchestration or the consensus
mechanism — those only matter once the base case is proven.

**Result (2026-08-24, `harness/results/1787552176/summary.json`): passed.**
6 synthetic PRs (3 documented-invariant violations, 1 clean refactor, 1 general
correctness bug unrelated to any documented rule, 1 correct-but-differently-structured
function as a false-positive trap), `claude-sonnet-5`, real headless invocations.

| condition | precision | recall | tp | fn | fp |
|---|---|---|---|---|---|
| no project knowledge | 1.00 | 0.25 | 1 | 3 | 0 |
| with project knowledge | 1.00 | 1.00 | 4 | 0 | 0 |

Lift: **recall +0.75**, precision unchanged (already 1.00 in both — the false-positive
trap and the clean refactor were both correctly left unflagged even without knowledge).
Without the knowledge base, all three documented-invariant violations were missed
entirely; with it, all three were caught, correctly cited, and nothing spurious was
added. Total cost for the 12-invocation run: ~$1.18.

Caught and fixed one flawed run before this one: the first attempt embedded the
invariant rationale directly in the demo codebase's own docstrings, so the "no
knowledge" condition wasn't actually blind — see the `1787551632` run for the record.
Also surfaced that the original false-positive-trap fixture had a genuine latent bug
(`enqueue_bulk` iterated a generator argument twice); the model was right, the fixture
was wrong, and the fixture was corrected rather than the result being discarded.

**-> M1 is unblocked.**

## M1 — Single node, live

The M0-validated node runs for real: a reusable GitHub Actions workflow, real inline PR
comments, a full run manifest recorded on every execution (corpus/prompt/diff hashes,
model id, token usage) so every verdict is reproducible.

**Stop condition:** track two numbers for two weeks — the fraction of posted findings a
human actually acts on, and the fraction later disputed as wrong. If the first is low or
the second is high, the knowledge/prompt layer isn't ready for more nodes yet.

**First live-fire (2026-08-25): passed.** Validated on a company-infrastructure mirror
first (`review-engine-poc`, GHES) rather than this repo directly, to keep company and
personal resource use separated — see `docs/architecture.md` section 6 and the isolation
note this project runs under. A real GitHub Actions run, authenticated via a Claude
subscription OAuth token (`claude setup-token`, not a metered API key — confirms M1 does
not require paid API access to run at all), correctly found the seeded invariant
violation, cited both the code line and the specific knowledge-doc anchor
(`invariants.md#INV-1`), gave a concrete failure scenario, and posted a real inline PR
comment via the GitHub Review API. Cost: $0.10.

Three infrastructure bugs surfaced and were fixed, all portable fixes now in this repo
too: (1) `post_review.py` hardcoded `api.github.com` instead of using the actual API base
URL for whatever server the workflow runs on — fixed via `github.api_url`, which resolves
correctly on both github.com and GHES; (2) the Claude node's auth was API-key-only — added
`CLAUDE_CODE_OAUTH_TOKEN` as an equally-supported alternative, so a node can be funded by
either a metered key or a subscription; (3) a GHES-only issue (`upload-artifact@v4`
unsupported there) was *not* carried back here since this repo runs on real GitHub, where
v4 is correct — a reminder that not every fix from a mirror environment is portable.

The 2-week action-rate/dispute-rate tracking itself has not started — that requires
sustained real usage on a repo with real ongoing PR traffic, which neither this repo nor
`review-engine-poc` has yet (both are demo/PoC repos). **M1's mechanism is proven; M1's
own quality bar is not yet measured.**

**Hardening pass (2026-08-26), still within M1's scope — no new milestone, closing gaps
in what M1 already claimed:**

- **Selectable output language, for real.** `profile.yaml`'s `output.language` was
  declared in the schema since the start but never actually read by any code. Now
  wired end-to-end: a project's default, plus a per-run override via commenting
  `/review lang=ko` on a PR (a new `quorum-review-command.yml` workflow). Verified with
  a real model call — natural, correctly-registered Korean output (not a stiff literal
  translation), structural fields (`category`/`severity`) correctly left in English.
  Building this surfaced and fixed a real script-injection vulnerability in the new
  workflow (a PR comment's raw text was headed for direct `${{ }}` interpolation into a
  shell script) before it ever shipped — see the workflow file's own security note.
- **The evidence gate is now actually mechanical, not just a prompt request.** The
  architecture doc already claimed findings without required evidence get "mechanically
  demoted" — that was aspirational, not true, until today. `apply_evidence_gate()` now
  enforces it in code: nothing is silently dropped, a finding that fails the gate stays
  visible at `nit` severity with the reason recorded.
- **Coverage is mechanically cross-checked, not just self-reported.** A model that
  silently skips a diff file without noticing now gets caught regardless — the real
  file list (`git diff --name-only`, not parsed from prose) is compared against
  `files_read` in code.
- **Real automated tests exist now.** 29 unit tests (`tests/test_review_pipeline.py`,
  wired into a new `test.yml` CI workflow) cover all of the above with no API calls, plus
  the harness itself was updated to build a proper `manifest.json` so M0 backtests get
  the same mechanical coverage check live CI runs do.
- **Full M0 regression check**, run after all of the above landed: identical result to
  the original validation (recall 0.25 -> 1.00, 0 false positives either way) — none of
  this hardening changed the actual review behavior, confirming it as pure robustness
  work, not a quality regression.

**Still open from the hardening pass, not yet closed out:**

- `quorum-review-command.yml` (the `/review lang=<x>` comment trigger) has only been
  tested in isolation (the regex-matching logic, locally) — the full workflow
  (checkout-by-PR-ref, `resolve_pr.py`, the pipeline end to end) has never run against a
  real PR comment event.
- `test.yml` has never been confirmed to actually run green on real github.com Actions —
  no `gh` auth to github.com was available to check a run's status; the workflow itself
  follows standard, well-trodden steps, but that's an inference, not a check.

## M2 — Feedback ledger

Capture disagreement with as little friction as possible: an explicit correction, and
just as importantly, the *implicit* signal of a "blocking" finding whose line never
changed before merge — a real human decision, even though no one clicked anything.
Cluster repeated signals into proposed knowledge-base updates; a human still approves
every change to the knowledge base. No signal becomes a rule on its own — clustering by
repeated signal (not a single incident) is the deliberate bar against overfitting the
knowledge base to one bad day.

**Why M2 is next, not "wait for M1's 2-week window first":** M1's own stop condition
(action-rate/dispute-rate over 2 weeks of real traffic) hasn't started, because no repo
running this engine has real ongoing PR traffic yet. M2 is not a feature bolted onto a
finished M1 — it's the instrumentation that 2-week measurement actually needs. Building
it now means the moment real traffic exists, the data collects itself instead of
requiring a human to keep score by hand.

**Design sketch:**

- **Ledger record** — one entry per finding: id, file/line/category, verdict
  (`accepted` / `corrected` / `ignored`), signal source (`explicit` / `implicit`), PR,
  timestamp.
- **Explicit capture** — a workflow step reads replies/reactions on the posted review
  comment.
- **Implicit capture** — a post-merge job diffs each `blocking`/`major` finding's line
  range against the merged state; unchanged = a real "ignored" signal even though no one
  clicked anything.
- **Clustering** — group by (file-pattern, category, cited invariant) across *repeated*
  occurrences only, never a single incident.
- **Promotion** — a cluster becomes a proposed PR against the project's own
  `invariants.md`/`constitution.md`. Never an automatic edit; a human approves every
  change to the knowledge base.

**Stop condition:** at least a meaningful sample of labeled outcomes before moving on —
building a consensus layer without any data on what "correct" looks like in practice is
building something that can't be tuned.

## M3 — Multiple roles, one vendor

Fan out to several role-specialized nodes (correctness, convention-vs-knowledge-base,
simplification/duplication) using the same vendor, combined via Stage 1 mechanical
clustering only — no adjudication yet, findings are shown grouped by how many roles
raised them.

**Stop condition:** measure each role's marginal contribution (findings that role alone
surfaced, later confirmed correct). Drop roles that don't earn their cost before adding
more.

## M4 — Adjudication

Add the Stage 2 adjudicator and the three-bucket (verified/contested/refuted) output.

**Stop condition:** precision should rise versus M3 *and* recall of previously-verified
findings should not drop. A recall drop means the adjudicator is suppressing real
findings — exactly the bias problem this project exists to avoid — and is a rollback
trigger, not a tuning problem.

## M5 — Second vendor

Add a second vendor's adapter, route the automated/fan-out case to metered credentials,
subscription credentials to explicitly human-triggered runs only, add the disclosure
footer (which credential ran which node, whose budget it counted against).

**Stop condition:** measure whether the second vendor's findings actually decorrelate
from the first's, on the same inputs. If they don't, the honest conclusion is that
multi-vendor's benefit here is fairness/billing flexibility, not bias reduction — real
information either way, not a failure.

## M6+ — Generalize

A second real adopting project. Only after that: a non-GitHub VCS adapter, then
evaluate open-sourcing the engine itself.
