# Claude adapter

**Live** (M0-validated, M1 live-fire). Renders `review/input/` into a headless
Claude Code invocation (`claude -p … --allowedTools "Read Glob Grep"`, strictly
read-only against `review/workspace/`), then normalizes the result into
`review/out/findings.json` per the schema in `docs/architecture.md`.

On a real multi-file diff the model often ends its turn with a prose summary
instead of the bare JSON object, which was the top cause of `status: error`
(issue #9). When the first parse fails the adapter runs a second, **tool-less**
`invoke()` that just reformats the analysis it already produced into the findings
JSON — a pure text→JSON transform. The node itself never gets a Write tool.

- Auth: `ANTHROPIC_API_KEY` (metered) **or** `CLAUDE_CODE_OAUTH_TOKEN` (from
  `claude setup-token`, a subscription). Either works; only one needs to be set.
- Vendor-agnostic post-processing (evidence gate, coverage verification, ledger
  key stamping, language) lives in `../common.py`, not here — this file is only
  the Claude-specific invocation and output-envelope parsing.

Usage: `adapter.py <review_dir> [model]` (default model `claude-sonnet-5`).
