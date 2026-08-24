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

## M1 — Single node, live

The M0-validated node runs for real: a reusable GitHub Actions workflow, real inline PR
comments, a full run manifest recorded on every execution (corpus/prompt/diff hashes,
model id, token usage) so every verdict is reproducible.

**Stop condition:** track two numbers for two weeks — the fraction of posted findings a
human actually acts on, and the fraction later disputed as wrong. If the first is low or
the second is high, the knowledge/prompt layer isn't ready for more nodes yet.

## M2 — Feedback ledger

Capture disagreement with as little friction as possible: an explicit correction, and
just as importantly, the *implicit* signal of a "blocking" finding whose line never
changed before merge — a real human decision, even though no one clicked anything.
Cluster repeated signals into proposed knowledge-base updates; a human still approves
every change to the knowledge base. No signal becomes a rule on its own — clustering by
repeated signal (not a single incident) is the deliberate bar against overfitting the
knowledge base to one bad day.

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
