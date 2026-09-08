# Lessons

Concrete incidents from real usage of this project, and what changed because of
them. Not aspirational — every entry here actually happened. Grows over time;
append new entries rather than editing old ones away, unless a later entry
genuinely supersedes an earlier one (say so explicitly if it does).

## The self-review loop on a large PR: real bugs, then a timeout wall (2026-09-06)

Running `quorum-self-review.yml` on the ~4 k-line PR that built M2-M4 went
three rounds:

- **Round 1** — 1 `blocking` + 1 `major`: `${{ github.event.inputs.pr }}`
  spliced straight into `run:` scripts in `quorum-review-fanout.yml`, exactly
  the ENG-6 script-injection pattern, with a working `curl | bash` exploit
  string. A bug the author had consciously rationalised away ("dispatcher has
  write access, low risk"). Fixed: validate the input, route via `env:`.
- **Round 2** — 2 `major`: `write_slice()` / the routing fallback both reported
  `routed_docs` inaccurately (a dead `#anchor` sibling still listed; the
  whole-file fallback reported `[]`), an ENG-10 audit gap. Fixed + the
  duplicated assembly block extracted to `route.assemble_knowledge()`.
- **Round 3** — `status: error`, `claude timed out after 300s`. A real review of
  a large multi-file diff routinely runs past the hardcoded 5-minute node
  timeout once it starts reading files. `invoke.py` now defaults to 900 s
  (`QUORUM_NODE_TIMEOUT` overrides); review workflows bumped to
  `timeout-minutes: 20`.

**Takeaways**: (1) the reviewer earns its keep — two rounds of genuine bugs,
severity trending down, zero style noise. (2) A 4 k-line PR is past the
"glance and approve" size; the honest loop there is review → fix → re-review,
and that's a signal to write smaller PRs, not a reviewer failure. (3) Timeouts
sized against the tiny `demo-project/` fixture don't survive a real diff — same
lesson as the ARG_MAX bug below.

## Self-review caught its first real bug on the PR that introduced it (2026-09-06)

The moment `quorum-self-review.yml` first ran — on the PR adding self-review
itself — the node crashed: `OSError: [Errno 7] Argument list too long: 'claude'`.
The adapter (and, after the M4 refactor, `invoke.py`) passed the whole prompt —
role + constitution + routed knowledge + **the full diff** — as an argv
parameter (`claude -p "<prompt>"`). Every prior run was against a `demo-project/`
fixture whose diff is a few lines, so it never approached `ARG_MAX`. A real
engine PR's diff (thousands of lines) blew straight past it.

**Fix**: the prompt now goes on **stdin** (`subprocess.run(..., input=prompt)`),
never in argv. Regression-tested with a 500 KB prompt (`tests/test_invoke.py`).

**Takeaway**: the synthetic M0 fixture is small by design, and "small" hid a
scale bug that only a real, large diff exposes. Dogfooding on the engine's own
PRs isn't just for collecting M1/M2 data — it exercises input sizes the fixture
never will. (The Codex adapter has the same argv-prompt shape and the same latent
bug; it's unverified anyway — fix when it's next touched.)

## Vendor headless auth can't be assumed from an interactive login working (2026-08-27 to 09-01)

Tried wiring a Codex (OpenAI) adapter for a real adopting project, funded by
the adopter's ChatGPT Plus subscription — the same shape of setup that already
worked for Claude (a `claude setup-token`-derived subscription token, no
metered API key needed). It doesn't work for Codex, confirmed three
independent ways:

1. Direct reproduction: fed a real, valid, correctly-formatted access token
   into `codex login --with-access-token` and got `agent identity JWT payload
   is not valid JSON` regardless of which field (`access_token`/`id_token`)
   from a normal `codex login` session was used.
2. Source-level analysis (by the adopter's own Codex agent, reading the real
   CLI source): `CODEX_ACCESS_TOKEN` is classified by prefix — `at-` means a
   real Personal Access Token, anything else (including a normal ChatGPT
   OAuth token) is misclassified as an internal "Agent Identity JWT" and
   rejected.
3. Official docs: Codex Personal Access Tokens (`at-...`) are a ChatGPT
   **Business/Enterprise workspace-only** feature, created via an admin
   console — not available on an individual Plus (or even Pro) subscription
   at all. The only officially-supported CI path for an individual account is
   a metered `OPENAI_API_KEY`, a completely separate product/billing surface
   from a ChatGPT subscription.

**Takeaway for any future vendor adapter**: don't assume a working interactive
login implies a working headless/CI login for the same account. Check the
vendor's own docs for what CI auth actually supports for the target account
tier *before* building the adapter, not after.

**Resolution**: switched that project to the Claude adapter (already proven,
see `docs/roadmap.md` M1), funded by the adopter's own personal Claude
subscription token instead.

## Credential provenance must match who the work is actually for (2026-08-27)

Ran real paid Claude calls (backtest reruns) in a shared dev environment
without first checking which account was authenticating them. Turned out to
be an account other than the one that should have paid — discovered only after
several calls had already run.

This is the same isolation principle as keeping one context's *content* from leaking
into a personal repo (or vice versa), just applied to the *credential* axis
instead of the *content* axis — and it's easy to miss precisely because
`git remote -v` / `git config user.email` being correctly scoped to personal
doesn't say anything about which AI credential is authenticating local CLI
calls. They're separate, and both need checking.

**Rule adopted**: before the first paid call to any vendor CLI in a new or
unfamiliar environment, check which account is actually authenticated (e.g.
`claude auth status`) — same discipline, same moment, as the git identity
check before a push. And the credential's *appropriate use* isn't binary:
funding your own experimentation with a credential that isn't scoped for it is a different
question from funding a real third party's usage with one — the latter is a
much harder line to justify, since it commits resources earmarked elsewhere to
something outside their intended purpose. When genuinely unsure which
bucket a situation falls into, treat it as the stricter one.
