# Claude adapter

**Live** (M0-validated, M1 live-fire). Renders `review/input/` into a headless
Claude Code invocation (`claude -p … --allowedTools "Read Glob Grep"`, read-only
against `review/workspace/`), then normalizes the result into
`review/out/findings.json` per the schema in `docs/architecture.md`.

- Auth: `ANTHROPIC_API_KEY` (metered) **or** `CLAUDE_CODE_OAUTH_TOKEN` (from
  `claude setup-token`, a subscription). Either works; only one needs to be set.
- Vendor-agnostic post-processing (evidence gate, coverage verification, ledger
  key stamping, language) lives in `../common.py`, not here — this file is only
  the Claude-specific invocation and output-envelope parsing.

Usage: `adapter.py <review_dir> [model]` (default model `claude-sonnet-5`).
