# Lessons

Concrete incidents from real usage of this project, and what changed because of
them. Not aspirational — every entry here actually happened. Grows over time;
append new entries rather than editing old ones away, unless a later entry
genuinely supersedes an earlier one (say so explicitly if it does).

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
be a company Team subscription, not a personal one — discovered only after
several calls had already run.

This is the same isolation principle as never letting company *content* leak
into a personal repo (or vice versa), just applied to the *credential* axis
instead of the *content* axis — and it's easy to miss precisely because
`git remote -v` / `git config user.email` being correctly scoped to personal
doesn't say anything about which AI credential is authenticating local CLI
calls. They're separate, and both need checking.

**Rule adopted**: before the first paid call to any vendor CLI in a new or
unfamiliar environment, check which account is actually authenticated (e.g.
`claude auth status`) — same discipline, same moment, as the git identity
check before a push. And the credential's *appropriate use* isn't binary:
funding your own experimentation with a company credential is a different
question from funding a real third party's usage with one — the latter is a
much harder line to justify, since it's spending company resources on
something outside company business purpose. When genuinely unsure which
bucket a situation falls into, treat it as the stricter one.
