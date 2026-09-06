#!/usr/bin/env python3
"""Unit tests for Stage 1 mechanical aggregation (engine/orchestrator/aggregate.py).
Pure logic -- run with: python3 -m unittest tests.test_aggregate -v
"""
import importlib.util
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine" / "orchestrator"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


agg_mod = _load("aggregate", "engine/orchestrator/aggregate.py")
aggregate = agg_mod.aggregate


def _node(findings, status="ok", **extra):
    return dict({"status": status, "findings": findings}, **extra)


def _f(file="queue/lifecycle.py", line=18, category="correctness", severity="blocking",
       claim="c", **kw):
    return dict({"file": file, "line": line, "category": category, "severity": severity,
                 "claim": claim, "failure_scenario": "x", "confidence": 0.9}, **kw)


class TestClustering(unittest.TestCase):
    def test_same_issue_from_two_roles_becomes_one_cluster(self):
        out = aggregate([
            ("correctness", _node([_f(line=18)])),
            ("convention", _node([_f(line=19, category="correctness", severity="major")])),
        ])
        self.assertEqual(len(out["findings"]), 1)
        c = out["findings"][0]
        self.assertEqual(c["raised_by"], ["convention", "correctness"])
        self.assertEqual(c["roles_count"], 2)
        self.assertEqual(c["severity"], "blocking")  # max across members
        self.assertEqual(len(c["members"]), 2)

    def test_different_category_same_line_stays_separate(self):
        out = aggregate([
            ("correctness", _node([_f(line=18, category="correctness")])),
            ("convention", _node([_f(line=18, category="convention",
                                     evidence=[{"type": "project", "ref": "invariants.md#INV-1"}])])),
        ])
        self.assertEqual(len(out["findings"]), 2)

    def test_far_apart_lines_same_file_stay_separate(self):
        out = aggregate([("correctness", _node([_f(line=5), _f(line=80)]))], proximity=3)
        self.assertEqual(len(out["findings"]), 2)

    def test_one_role_raising_twice_in_cluster_counts_once(self):
        out = aggregate([("correctness", _node([_f(line=18), _f(line=19)]))], proximity=3)
        self.assertEqual(len(out["findings"]), 1)
        self.assertEqual(out["findings"][0]["roles_count"], 1)

    def test_evidence_is_unioned_and_deduped(self):
        out = aggregate([
            ("a", _node([_f(evidence=[{"type": "code", "ref": "x.py:1"}])])),
            ("b", _node([_f(line=19, evidence=[{"type": "code", "ref": "x.py:1"},
                                               {"type": "project", "ref": "invariants.md#INV-1"}])])),
        ])
        refs = {(e["type"], e["ref"]) for e in out["findings"][0]["evidence"]}
        self.assertEqual(refs, {("code", "x.py:1"), ("project", "invariants.md#INV-1")})

    def test_representative_is_highest_severity(self):
        out = aggregate([
            ("a", _node([_f(line=18, severity="nit", claim="minor take")])),
            ("b", _node([_f(line=18, severity="blocking", claim="the real problem")])),
        ])
        self.assertEqual(out["findings"][0]["claim"], "the real problem")

    def test_sorted_by_severity_then_roles_count(self):
        out = aggregate([
            ("a", _node([_f(file="a.py", line=1, severity="minor"),
                         _f(file="b.py", line=1, severity="blocking")])),
            ("b", _node([_f(file="a.py", line=1, severity="minor")])),
        ])
        # blocking (1 role) should rank above minor (2 roles)
        self.assertEqual(out["findings"][0]["file"], "b.py")


class TestNodeStatus(unittest.TestCase):
    def test_errored_node_does_not_count_as_clean(self):
        out = aggregate([
            ("correctness", _node([], status="error", error="crashed")),
            ("convention", _node([_f(category="convention",
                                     evidence=[{"type": "project", "ref": "invariants.md#INV-1"}])])),
        ])
        self.assertEqual(out["status"], "partial")
        err = [n for n in out["nodes"] if n["role"] == "correctness"][0]
        self.assertEqual(err["status"], "error")
        self.assertEqual(err["error"], "crashed")

    def test_all_nodes_errored_is_error_not_empty_ok(self):
        out = aggregate([
            ("a", _node([], status="error")),
            ("b", _node([], status="error")),
        ])
        self.assertEqual(out["status"], "error")
        self.assertEqual(out["findings"], [])

    def test_all_ok_is_ok(self):
        out = aggregate([("a", _node([])), ("b", _node([]))])
        self.assertEqual(out["status"], "ok")

    def test_errored_node_findings_are_ignored(self):
        out = aggregate([
            ("a", _node([_f(claim="should not appear")], status="error")),
        ])
        self.assertEqual(out["findings"], [])


class TestMergeCoverageAndUsage(unittest.TestCase):
    def test_file_missed_by_all_nodes_is_flagged(self):
        out = aggregate([
            ("a", _node([], coverage={"files_in_diff": 2, "files_read": ["x.py"]})),
            ("b", _node([], coverage={"files_in_diff": 2, "files_read": ["x.py"],
                                      "mechanically_verified_missing": ["y.py"]})),
        ])
        self.assertEqual(out["coverage"]["mechanically_verified_missing"], ["y.py"])

    def test_file_read_by_one_node_is_not_missing(self):
        out = aggregate([
            ("a", _node([], coverage={"files_in_diff": 2, "files_read": ["x.py"],
                                      "mechanically_verified_missing": ["y.py"]})),
            ("b", _node([], coverage={"files_in_diff": 2, "files_read": ["x.py", "y.py"]})),
        ])
        self.assertNotIn("mechanically_verified_missing", out["coverage"])

    def test_usage_is_summed(self):
        out = aggregate([
            ("a", _node([], usage={"total_cost_usd": 0.10, "input_tokens": 5, "output_tokens": 7})),
            ("b", _node([], usage={"total_cost_usd": 0.05, "input_tokens": 3, "output_tokens": 2})),
        ])
        self.assertAlmostEqual(out["usage"]["total_cost_usd"], 0.15)
        self.assertEqual(out["usage"]["input_tokens"], 8)


if __name__ == "__main__":
    unittest.main()
