# Orchestrator

Not yet implemented. Will hold: `plan` (triage + budget + cache check), `aggregate`
(Stage 1 mechanical clustering), `adjudicate` (Stage 2), and `post` (single combined
GitHub review via the Review API, repo-scoped credentials only — never a node's own
vendor credential). See `docs/architecture.md` sections 3–5.

M0 doesn't need this at all — the backtest harness runs a single node directly, no
orchestration required, by design (see `docs/roadmap.md`).
