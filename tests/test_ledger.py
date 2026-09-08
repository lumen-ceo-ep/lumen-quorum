#!/usr/bin/env python3
"""Unit tests for the M2 feedback ledger (engine/ledger/*). Pure logic, no
network, no git -- run with: python3 -m unittest tests.test_ledger -v
"""
import contextlib
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LEDGER_DIR = REPO_ROOT / "engine" / "ledger"
sys.path.insert(0, str(LEDGER_DIR))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


record = _load("record", "engine/ledger/record.py")
cluster_mod = _load("cluster", "engine/ledger/cluster.py")
capture_implicit = _load("capture_implicit", "engine/ledger/capture_implicit.py")
capture_explicit = _load("capture_explicit", "engine/ledger/capture_explicit.py")
promote = _load("promote", "engine/ledger/promote.py")


def _finding(**kw):
    base = {
        "file": "queue/lifecycle.py", "line": 18, "category": "correctness",
        "severity": "blocking", "claim": "CANCELLED can transition to RUNNING",
        "evidence": [{"type": "project", "ref": "invariants.md#INV-1"},
                     {"type": "code", "ref": "queue/lifecycle.py:18"}],
    }
    base.update(kw)
    return base


class TestKeyDerivation(unittest.TestCase):
    def test_finding_key_stable_across_calls(self):
        self.assertEqual(record.derive_finding_key(_finding()),
                         record.derive_finding_key(_finding()))

    def test_finding_key_survives_evidence_gate_annotation(self):
        plain = _finding()
        demoted = _finding(claim="[evidence gate: no failure_scenario] " + plain["claim"])
        self.assertEqual(record.derive_finding_key(plain),
                         record.derive_finding_key(demoted))

    def test_finding_key_differs_by_line(self):
        self.assertNotEqual(record.derive_finding_key(_finding(line=18)),
                            record.derive_finding_key(_finding(line=42)))

    def test_cluster_key_ignores_line_and_code_ref(self):
        a = _finding(line=18)
        b = _finding(line=99, evidence=[{"type": "project", "ref": "invariants.md#INV-1"},
                                        {"type": "code", "ref": "queue/lifecycle.py:99"}])
        self.assertEqual(record.derive_cluster_key(a), record.derive_cluster_key(b))

    def test_cluster_key_differs_by_cited_rule(self):
        a = _finding(evidence=[{"type": "project", "ref": "invariants.md#INV-1"}])
        b = _finding(evidence=[{"type": "project", "ref": "invariants.md#INV-2"}])
        self.assertNotEqual(record.derive_cluster_key(a), record.derive_cluster_key(b))

    def test_file_pattern_generalizes_path(self):
        self.assertEqual(record.file_pattern("demo-project/codebase/queue/lifecycle.py"),
                         "demo-project/codebase/queue/*")
        self.assertEqual(record.file_pattern("lifecycle.py"), "lifecycle.py")

    def test_path_suffix_match(self):
        m = record.path_suffix_match
        self.assertTrue(m("queue/lifecycle.py", "demo-project/codebase/queue/lifecycle.py"))
        self.assertTrue(m("demo-project/codebase/queue/lifecycle.py", "queue/lifecycle.py"))
        self.assertTrue(m("a/b.py", "a/b.py"))
        self.assertFalse(m("queue/enqueue.py", "queue/lifecycle.py"))
        self.assertFalse(m("lifecycle.py", "notlifecycle.py"))  # not a component boundary
        self.assertFalse(m("", "a.py"))

    def test_stamp_keys_is_in_place_and_complete(self):
        f = _finding()
        out = record.stamp_keys(f)
        self.assertIs(out, f)
        for k in ("finding_key", "cluster_key", "cited_refs", "file_pattern"):
            self.assertIn(k, f)
        self.assertEqual(f["cited_refs"], ["invariants.md#INV-1"])


class TestRecordStore(unittest.TestCase):
    def test_make_record_rejects_bad_enums(self):
        with self.assertRaises(ValueError):
            record.make_record(repo="o/r", pr=1, finding=_finding(), verdict="nope", signal="explicit")
        with self.assertRaises(ValueError):
            record.make_record(repo="o/r", pr=1, finding=_finding(), verdict="ignored", signal="psychic")

    def test_append_and_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sub" / "ledger.jsonl"
            rec = record.make_record(repo="o/r", pr=1, finding=record.stamp_keys(_finding()),
                                     verdict="ignored", signal="implicit")
            self.assertEqual(record.append_records(path, [rec]), 1)
            loaded = record.load_records(path)
            self.assertEqual(len(loaded), 1)
            self.assertEqual(loaded[0]["verdict"], "ignored")

    def test_missing_ledger_is_empty_not_error(self):
        self.assertEqual(record.load_records(Path("/no/such/ledger.jsonl")), [])

    def test_malformed_line_skipped_rest_loaded(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            good = record.make_record(repo="o/r", pr=1, finding=record.stamp_keys(_finding()),
                                      verdict="ignored", signal="implicit")
            path.write_text("{bad json\n" + json.dumps(good) + "\n")
            self.assertEqual(len(record.load_records(path)), 1)

    def test_append_dedupes_same_signal_on_rerun(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            f = record.stamp_keys(_finding())
            rec1 = record.make_record(repo="o/r", pr=7, finding=f, verdict="ignored", signal="implicit")
            rec2 = record.make_record(repo="o/r", pr=7, finding=f, verdict="ignored", signal="implicit")
            self.assertEqual(record.append_records(path, [rec1]), 1)
            self.assertEqual(record.append_records(path, [rec2]), 0)  # dedup: same key/verdict/signal/pr
            self.assertEqual(len(record.load_records(path)), 1)

    def test_append_keeps_distinct_verdicts_on_same_finding(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "ledger.jsonl"
            f = record.stamp_keys(_finding())
            imp = record.make_record(repo="o/r", pr=7, finding=f, verdict="ignored", signal="implicit")
            exp = record.make_record(repo="o/r", pr=7, finding=f, verdict="corrected", signal="explicit")
            record.append_records(path, [imp, exp])
            self.assertEqual(len(record.load_records(path)), 2)


class TestChangedLines(unittest.TestCase):
    DIFF = """--- a/queue/lifecycle.py
+++ b/queue/lifecycle.py
@@ -15,7 +15,7 @@
     context line
-    TaskState.CANCELLED: {TaskState.RUNNING},
+    TaskState.CANCELLED: set(),
     another context line
"""

    def test_added_line_number_tracked(self):
        changed = capture_implicit.changed_lines_by_file(self.DIFF)
        self.assertIn("queue/lifecycle.py", changed)
        # hunk right-side starts at 15; one context line (15) then the -/+ pair,
        # so the change sits at right-side line 16.
        self.assertIn(16, changed["queue/lifecycle.py"])

    def test_file_with_no_additions_still_present(self):
        diff = "--- a/x.py\n+++ b/x.py\n@@ -1,2 +1,1 @@\n line one\n-line two\n"
        self.assertIn("x.py", capture_implicit.changed_lines_by_file(diff))


class TestDetectIgnored(unittest.TestCase):
    def _diff(self, path, right_start, changed_body):
        return (f"--- a/{path}\n+++ b/{path}\n@@ -{right_start},3 +{right_start},3 @@\n"
                f" ctx\n-old\n+{changed_body}\n ctx\n")

    def test_blocking_finding_on_unchanged_file_is_ignored(self):
        findings = [record.stamp_keys(_finding(line=18))]
        other_file_diff = self._diff("queue/enqueue.py", 40, "new")
        got = capture_implicit.detect_ignored(findings, other_file_diff)
        self.assertEqual(len(got), 1)

    def test_blocking_finding_whose_line_changed_is_not_ignored(self):
        findings = [record.stamp_keys(_finding(line=18))]
        diff = self._diff("queue/lifecycle.py", 17, "fixed line")  # right line 18 changed
        self.assertEqual(capture_implicit.detect_ignored(findings, diff), [])

    def test_minor_finding_never_counts_as_ignored(self):
        findings = [record.stamp_keys(_finding(severity="minor", line=18))]
        diff = self._diff("queue/enqueue.py", 40, "new")
        self.assertEqual(capture_implicit.detect_ignored(findings, diff), [])

    def test_window_absorbs_off_by_one_citation(self):
        findings = [record.stamp_keys(_finding(line=18))]
        diff = self._diff("queue/lifecycle.py", 18, "fixed")  # changes right line 19; finding says 18
        self.assertEqual(capture_implicit.detect_ignored(findings, diff, window=2), [])

    def test_suffix_path_match_repo_relative_vs_workspace_relative(self):
        findings = [record.stamp_keys(_finding(file="queue/lifecycle.py", line=18))]
        diff = self._diff("demo-project/codebase/queue/lifecycle.py", 17, "fixed")
        self.assertEqual(capture_implicit.detect_ignored(findings, diff), [])

    def test_records_for_produces_valid_ledger_records(self):
        findings = [record.stamp_keys(_finding(line=18))]
        diff = self._diff("queue/enqueue.py", 40, "new")
        recs = capture_implicit.records_for(findings, diff, repo="o/r", pr=5)
        self.assertEqual(recs[0]["verdict"], "ignored")
        self.assertEqual(recs[0]["signal"], "implicit")
        record.validate_record(recs[0])


class TestExplicitClassification(unittest.TestCase):
    def test_accept_phrases(self):
        for t in ["good catch, fixing now", "you're right", "done", "thanks, addressed"]:
            self.assertEqual(capture_explicit.classify_reply(t), "accepted", t)

    def test_correct_phrases(self):
        for t in ["this is a false positive", "nope, working as intended", "the rule doesn't apply here"]:
            self.assertEqual(capture_explicit.classify_reply(t), "corrected", t)

    def test_neutral_reply_no_signal(self):
        self.assertIsNone(capture_explicit.classify_reply("looking into it"))
        self.assertIsNone(capture_explicit.classify_reply(""))

    def test_dispute_beats_accept_in_same_thread(self):
        thread = {"replies": ["good catch", "actually no, this is by design"], "reactions": []}
        self.assertEqual(capture_explicit.verdict_for_thread(thread), "corrected")

    def test_reactions_classified(self):
        self.assertEqual(capture_explicit.classify_reactions(["+1", "rocket"]), "accepted")
        self.assertEqual(capture_explicit.classify_reactions(["+1", "-1"]), "corrected")
        self.assertIsNone(capture_explicit.classify_reactions([]))

    def test_marker_parsing(self):
        body = "🔴 **BLOCKING** -- bad\n\n<!-- quorum:finding_key=abc123def456 -->"
        self.assertEqual(capture_explicit.parse_marker(body), "abc123def456")
        self.assertIsNone(capture_explicit.parse_marker("no marker here"))

    def test_records_from_threads_skips_no_signal(self):
        f = record.stamp_keys(_finding())
        threads = [
            {"finding": f, "replies": ["hmm"], "reactions": []},                 # no signal
            {"finding": f, "replies": ["false positive"], "reactions": []},      # corrected
        ]
        recs = capture_explicit.records_from_threads(threads, repo="o/r", pr=3)
        self.assertEqual(len(recs), 1)
        self.assertEqual(recs[0]["verdict"], "corrected")
        self.assertEqual(recs[0]["signal"], "explicit")

    def test_orphan_thread_with_signal_but_no_finding_is_skipped_not_raised(self):
        # marker present, verdict present, but no matching finding fields
        threads = [{"finding_key": "orphan", "finding": {"finding_key": "orphan"},
                    "replies": ["false positive"], "reactions": []}]
        with contextlib.redirect_stderr(io.StringIO()):
            recs = capture_explicit.records_from_threads(threads, repo="o/r", pr=3)
        self.assertEqual(recs, [])


class TestClustering(unittest.TestCase):
    def _recs(self, n_prs, verdict="ignored", ref="invariants.md#INV-1"):
        f = record.stamp_keys(_finding(evidence=[{"type": "project", "ref": ref}]))
        return [record.make_record(repo="o/r", pr=100 + i, finding=f, verdict=verdict,
                                   signal="implicit", ts=f"2026-09-0{i+1}T00:00:00Z")
                for i in range(n_prs)]

    def test_below_threshold_not_clustered(self):
        self.assertEqual(cluster_mod.cluster(self._recs(2), min_occurrences=3), [])

    def test_at_threshold_clustered(self):
        clusters = cluster_mod.cluster(self._recs(3), min_occurrences=3)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0]["occurrence_count"], 3)
        self.assertEqual(clusters[0]["dominant_verdict"], "ignored")

    def test_multiple_records_same_pr_count_once(self):
        recs = self._recs(1) * 5  # same pr, five times
        self.assertEqual(cluster_mod.cluster(recs, min_occurrences=3), [])

    def test_accepted_verdict_excluded_by_default(self):
        self.assertEqual(cluster_mod.cluster(self._recs(4, verdict="accepted"), min_occurrences=3), [])

    def test_distinct_rules_do_not_merge(self):
        recs = self._recs(2, ref="invariants.md#INV-1") + self._recs(2, ref="invariants.md#INV-2")
        # 2 + 2, neither reaches 3
        self.assertEqual(cluster_mod.cluster(recs, min_occurrences=3), [])


class TestPromote(unittest.TestCase):
    def _cluster(self, verdict, refs):
        f = record.stamp_keys(_finding(
            evidence=[{"type": "project", "ref": r} for r in refs]))
        recs = [record.make_record(repo="o/r", pr=200 + i, finding=f, verdict=verdict,
                                   signal="implicit", ts=f"2026-09-0{i+1}T00:00:00Z")
                for i in range(3)]
        return cluster_mod.cluster(recs, min_occurrences=3)[0]

    def test_ignored_with_rule_recommends_reviewing_the_rule(self):
        text = promote.recommend(self._cluster("ignored", ["invariants.md#INV-1"]))
        self.assertIn("INV-1", text)
        self.assertIn("too strict", text)

    def test_corrected_without_rule_recommends_constitution_note(self):
        text = promote.recommend(self._cluster("corrected", []))
        self.assertIn("constitution.md", text)

    def test_document_renders_and_flags_no_auto_apply(self):
        doc = promote.render_document([self._cluster("corrected", ["invariants.md#INV-2"])])
        self.assertIn("Nothing "
                      "here is applied automatically", doc)
        self.assertIn("INV-2", doc)
        self.assertIn("signal trail", doc)

    def test_empty_document_is_valid(self):
        self.assertIn("No clusters", promote.render_document([]))


if __name__ == "__main__":
    unittest.main()
