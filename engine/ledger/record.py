#!/usr/bin/env python3
"""Feedback-ledger record: schema, key derivation, JSONL store.

The ledger is the M2 instrumentation layer (see docs/roadmap.md M2 and
docs/architecture.md sec. 9). One entry per finding-per-signal: what a
review said, and what a human -- explicitly or implicitly -- did about it.

Design constraints that shaped this file:

- **The ledger is project data, not engine data.** Like a project's
  constitution/invariants, it persists across runs and is owned by the
  adopting team, not baked into the engine (docs/architecture.md sec. 1, 5).
  The engine ships the *code* to read/write/cluster it; the file itself
  lives wherever the project keeps its knowledge.
- **Append-only, one JSON object per line.** No in-place edits, no rewrite.
  A wrong entry is superseded by a later one, never deleted -- same
  "never delete, only add with a reason" discipline as Stage 2 adjudication.
- **Two derived keys, different jobs.** `finding_key` identifies one
  specific posted finding so an explicit reply/reaction can be matched back
  to it. `cluster_key` is deliberately coarser -- it's what groups findings
  *across different PRs* so a repeated pattern (not a single incident) can
  be surfaced for a proposed knowledge-base change (see cluster.py).
"""
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

# A finding's verdict: what actually happened to it.
#   accepted  -- a human acted on it (fixed the line, or said they would).
#   corrected -- a human disputed it as wrong. This is the false-positive signal.
#   ignored   -- a blocking/major finding whose line merged unchanged, with no
#                explicit reply. A real human decision even though nobody clicked
#                anything (docs/roadmap.md M2, "implicit capture").
VERDICTS = ("accepted", "corrected", "ignored")

# How the verdict was observed.
SIGNALS = ("explicit", "implicit")

_REQUIRED_FIELDS = (
    "id", "ts", "repo", "pr", "finding_key", "cluster_key",
    "file", "category", "verdict", "signal",
)


def iso_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _norm_claim(claim: str) -> str:
    """Normalizes a claim string for hashing: strips a leading evidence-gate
    annotation (apply_evidence_gate prepends "[evidence gate: ...] "), lowercases,
    and collapses whitespace. This keeps a finding_key stable whether or not the
    gate demoted the finding, and robust to trivial wording drift between runs.
    """
    claim = re.sub(r"^\[evidence gate:[^\]]*\]\s*", "", claim or "")
    return re.sub(r"\s+", " ", claim).strip().lower()


def project_refs(finding: dict) -> list:
    """The project-knowledge references a finding cites, sorted and deduped.
    These are the anchors that matter for clustering -- e.g. "invariants.md#INV-1".
    Code refs (file:line) are deliberately excluded: they're PR-specific, so
    including them would defeat cross-PR grouping.
    """
    refs = {
        e.get("ref", "").strip()
        for e in (finding.get("evidence") or [])
        if e.get("type") == "project" and e.get("ref")
    }
    return sorted(refs)


def file_pattern(path: str) -> str:
    """Generalizes a concrete file path to a coarse pattern for clustering.
    "demo-project/codebase/queue/lifecycle.py" -> "demo-project/codebase/queue/*".
    Keeps the directory (where a rule tends to apply) and drops the specific
    filename (which varies PR to PR). A single-segment path keeps its own name.
    """
    path = (path or "").strip().lstrip("./")
    if "/" in path:
        return path.rsplit("/", 1)[0] + "/*"
    return path or "*"


def derive_finding_key(finding: dict) -> str:
    """Stable identity of one specific posted finding, for matching an explicit
    reply/reaction back to it. Derived from the concrete anchor (file+line),
    category, and a normalized hash of the claim -- stable across a re-review of
    the same unchanged code, distinct between two findings on the same line.
    """
    basis = "|".join([
        (finding.get("file") or "").strip(),
        str(finding.get("line") or 0),
        (finding.get("category") or "").strip(),
        hashlib.sha1(_norm_claim(finding.get("claim", "")).encode()).hexdigest()[:10],
    ])
    return hashlib.sha1(basis.encode()).hexdigest()[:16]


def derive_cluster_key(finding: dict) -> str:
    """Coarse key that groups findings across PRs (see cluster.py). Per the M2
    sketch: (file-pattern, category, cited invariant). Intentionally lossy --
    two findings with the same key are "the same kind of thing happening again",
    which is the bar for proposing a knowledge-base change.
    """
    basis = "|".join([
        file_pattern(finding.get("file", "")),
        (finding.get("category") or "").strip(),
        ",".join(project_refs(finding)),
    ])
    return hashlib.sha1(basis.encode()).hexdigest()[:16]


def stamp_keys(finding: dict) -> dict:
    """Adds finding_key/cluster_key/cited_refs/file_pattern to a finding in place
    and returns it. Called from the adapter's postprocess() so every findings.json
    carries the keys the ledger later needs -- computed once, at review time, from
    the pre-gate finding, so they don't drift.
    """
    finding["finding_key"] = derive_finding_key(finding)
    finding["cluster_key"] = derive_cluster_key(finding)
    finding["cited_refs"] = project_refs(finding)
    finding["file_pattern"] = file_pattern(finding.get("file", ""))
    return finding


def make_record(*, repo: str, pr: int, finding: dict, verdict: str, signal: str,
                detail: str = "", run_id: str = "", ts: str = None, id: str = None) -> dict:
    if verdict not in VERDICTS:
        raise ValueError(f"verdict must be one of {VERDICTS}, got {verdict!r}")
    if signal not in SIGNALS:
        raise ValueError(f"signal must be one of {SIGNALS}, got {signal!r}")
    return {
        "id": id or str(uuid.uuid4()),
        "ts": ts or iso_now(),
        "repo": repo,
        "pr": int(pr),
        "run_id": run_id,
        "finding_key": finding.get("finding_key") or derive_finding_key(finding),
        "cluster_key": finding.get("cluster_key") or derive_cluster_key(finding),
        "file": finding.get("file"),
        "line": finding.get("line"),
        "category": finding.get("category"),
        "severity": finding.get("severity"),
        "cited_refs": finding.get("cited_refs") or project_refs(finding),
        "file_pattern": finding.get("file_pattern") or file_pattern(finding.get("file", "")),
        "verdict": verdict,
        "signal": signal,
        "detail": detail,
    }


def validate_record(rec: dict) -> None:
    missing = [f for f in _REQUIRED_FIELDS if rec.get(f) in (None, "")]
    if missing:
        raise ValueError(f"ledger record missing required field(s): {missing}")
    if rec["verdict"] not in VERDICTS:
        raise ValueError(f"bad verdict: {rec['verdict']!r}")
    if rec["signal"] not in SIGNALS:
        raise ValueError(f"bad signal: {rec['signal']!r}")


def load_records(ledger_path) -> list:
    """Reads a JSONL ledger. A blank or missing file is an empty ledger, not an
    error -- the first run against a project has nothing yet. A single malformed
    line is skipped with the rest still loaded, rather than losing the whole
    history to one bad append.
    """
    path = Path(ledger_path)
    if not path.exists():
        return []
    records = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return records


def append_records(ledger_path, records: list) -> int:
    """Appends records as JSONL. Deduplicates against what's already on disk by
    (finding_key, verdict, signal, pr) -- re-running the capture job on the same
    PR must not double-count a signal. Returns the number actually written.
    """
    path = Path(ledger_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing = {
        (r.get("finding_key"), r.get("verdict"), r.get("signal"), r.get("pr"))
        for r in load_records(path)
    }
    fresh = []
    for rec in records:
        validate_record(rec)
        dedupe_key = (rec["finding_key"], rec["verdict"], rec["signal"], rec["pr"])
        if dedupe_key in existing:
            continue
        existing.add(dedupe_key)
        fresh.append(rec)

    if fresh:
        with path.open("a") as fh:
            for rec in fresh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return len(fresh)
