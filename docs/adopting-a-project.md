# Adopting Quorum for a new project

Everything here has been done twice so far — once for `demo-project/` (M0's
synthetic fixture) and once for `engine-knowledge/` (the engine reviewing
itself). Both times it was done by hand, in an ad-hoc order. This is that
process written down, so the next adopter (M6) doesn't have to reconstruct it.

The engine never changes for a new adopter (`docs/architecture.md` sec. 1) —
everything below is *data* you create, plus a couple of config lines.

## 0. Before you start

- A repo to review (can be the same repo Quorum lives in, or a different one —
  `engine/orchestrator/build_review_input.py`'s cross-repo note covers both).
- Write access to add a GitHub Actions secret.
- Either `ANTHROPIC_API_KEY` (metered) or a `claude setup-token`-derived
  subscription token. Check which account is authenticating it first
  (`docs/lessons.md`, "Credential provenance") — especially if this is a
  personal project and your default CLI login is a work account, or vice versa.

## 1. Write the project knowledge base

Create a directory (anywhere — it doesn't need to live in this repo) with:

```
your-project/
  constitution.md   # Tier 1: universal review rubric for this project
  invariants.md      # checkable claims, one ## heading per claim (anchor-addressable)
  routes.yaml        # changed-file pattern -> which invariants.md anchors apply
  profile.yaml        # output language / severity vocab / scope
```

Use `demo-project/` (synthetic, deliberately simple) or `engine-knowledge/`
(real, `ENG-1`..`ENG-10`) as templates for shape and tone. The bar for a good
`invariants.md` entry: **a reviewer (human or model) could confirm or refute it
against the diff alone.** "Write clean code" is not checkable; "a retry must
reuse the original `task_id`" is.

Keep `routes.yaml` honest — a rule with no matching files in the real tree is a
dead route nobody notices (`tests/test_engine_knowledge.py` is the mechanical
guard against this for the two knowledge bases in this repo; add the same
check for yours if it's not colocated here).

## 2. Validate offline before going live (the M0 discipline)

**Do not skip this.** The whole reason this project exists is the empirical
finding that project knowledge measurably improves review quality *on this
project's own code* — that's not guaranteed to transfer to a different
codebase's conventions, and the only way to know is to check, the same way M0
did.

Build a small corpus (5-10 fixtures is enough to start) of your project's own
past PRs — ideally ones with a documented invariant violation you already know
about, plus at least one clean PR and one PR that looks like a violation but
isn't (the false-positive-trap shape). Each fixture needs:

```
your-corpus/pr-01-something/
  diff.patch
  ground_truth.json   # {"expected_findings": [...]}  (see demo-project/example-pr/*/ground_truth.json)
  workspace/           # the codebase at that PR's head
```

Then:

```
python3 harness/backtest.py --corpus /path/to/your-corpus --out /path/outside/this/repo
```

**Always pass `--out` pointing outside this repo for a real project's corpus**
— fixture content and findings from someone else's codebase must never land in
this (or any other) engine repo (`harness/backtest.py`'s own module docstring).

Read the lift the same way M0's roadmap entry does: did `with_knowledge` catch
more of the seeded violations than `no_knowledge`, at the same precision? If
not, the knowledge base needs work — fix that before wiring up CI, not after.

## 3. Wire the live workflow

Copy `.github/workflows/quorum-review.yml` (or `quorum-self-review.yml` if
you're adding a second project to *this* repo) into your project's
`.github/workflows/`, and change:

- `--project demo-project` → `--project <path to your knowledge dir>`
- the `paths:` filter under `on: pull_request` → whatever subset of your repo
  this project's rules apply to
- the artifact/job names, so they don't collide if you're running more than
  one project's review in one repo (see how `quorum-review.yml` and
  `quorum-self-review.yml` coexist here)

Add the secret: `ANTHROPIC_API_KEY` or `CLAUDE_CODE_OAUTH_TOKEN`, repo settings
→ Secrets and variables → Actions. Either name works; the adapter checks both.

## 4. Go live, then watch, don't assume

- First few PRs: read every posted finding yourself. Confirm the citations are
  real, the severities make sense, nothing sounds like it's reviewing a
  different project's conventions.
- Wire `quorum-ledger.yml` the same way, so M1's action/dispute rate and M2's
  ledger start accumulating from day one instead of needing a second pass later.
- Expect the self-review pattern this repo hit: on a real PR, the mechanism
  will find edge cases the synthetic corpus never exercised (large diffs,
  timeouts, output-format hiccups). `docs/lessons.md` has the ones already
  fixed here; a new project may still find its own.
