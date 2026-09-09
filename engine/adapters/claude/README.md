# Claude adapter

**Live** (M0-validated, M1 live-fire). Renders `review/input/` into a headless
Claude Code invocation (`claude -p … --allowedTools "Read Glob Grep Write"`,
read-only against `review/workspace/` plus write access to `review/out/` only),
then normalizes the result into `review/out/findings.json` per the schema in
`docs/architecture.md`.

The node **writes its findings JSON to `review/out/node-findings.json`** with the
Write tool; the adapter reads that file (issue #9). On a real multi-file diff the
model reliably ends its turn with a prose summary, so parsing the chat message
was the top cause of `status: error` — the chat message is now a fallback only,
with one retry if neither the file nor the message parses.

- Auth: `ANTHROPIC_API_KEY` (metered) **or** `CLAUDE_CODE_OAUTH_TOKEN` (from
  `claude setup-token`, a subscription). Either works; only one needs to be set.
- Vendor-agnostic post-processing (evidence gate, coverage verification, ledger
  key stamping, language) lives in `../common.py`, not here — this file is only
  the Claude-specific invocation and output-envelope parsing.

Usage: `adapter.py <review_dir> [model]` (default model `claude-sonnet-5`).
