# Codex adapter

**Written, not validated live.** Renders `review/input/` into a headless
`codex exec --sandbox read-only` invocation with a JSON `--output-schema`, and
normalizes the result through the same `../common.py` post-processing as the
Claude adapter.

Status caveats (see `docs/lessons.md` and `docs/roadmap.md` M5):

- Never exercised against a real Codex backend end to end — built against
  `codex exec --help`, not a live run. Treat its findings as unverified until one.
- A ChatGPT **Plus/Pro** subscription cannot drive `codex` headlessly: only a
  workspace-issued `at-…` PAT or a metered `OPENAI_API_KEY` works. The adapter
  reads `CODEX_ACCESS_TOKEN` / `OPENAI_API_KEY` and feeds `codex login`.

Multi-vendor is sequenced **after** M5 measures whether a second vendor's findings
actually decorrelate from the first's, rather than assuming they do.
