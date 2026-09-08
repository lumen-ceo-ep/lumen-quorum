#!/usr/bin/env python3
"""Unit tests for Stage 2 adjudication (engine/orchestrator/adjudicate.py).
Pure logic only -- the model call is not exercised here. Run with:
python3 -m unittest tests.test_adjudicate -v
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine" / "orchestrator"))
sys.path.insert(0, str(REPO_ROOT / "engine" / "adapters"))


def _load(name, rel):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


adj = _load("adjudicate", "engine/orchestrator/adjudicate.py")


def _cluster(i, sev="blocking", file="q.py"):
    return {"file": file, "line": 10 + i, "category": "correctness", "severity": sev,
            "claim": f"claim {i}", "failure_scenario": "x", "evidence": [],
            "raised_by": ["correctness"], "finding_key": f"k{i}"}


def _agg(n):
    return {"status": "ok", "stage": "mechanical-cluster",
            "findings": [_cluster(i) for i in range(n)],
            "nodes": [], "coverage": {}, "usage": {"total_cost_usd": 0.1}}


class TestParseAdjudication(unittest.TestCase):
    def test_well_formed(self):
        text = json.dumps([
            {"cluster": 0, "verdict": "verified", "rationale": "matches INV-1", "counter_evidence": []},
            {"cluster": 1, "verdict": "refuted", "rationale": "wrong",
             "counter_evidence": [{"type": "code", "ref": "q.py:5"}]},
        ])
        got = adj.parse_adjudication(text, 2)
        self.assertEqual(got[0]["verdict"], "verified")
        self.assertEqual(got[1]["verdict"], "refuted")

    def test_missing_entry_defaults_contested(self):
        got = adj.parse_adjudication(json.dumps([{"cluster": 0, "verdict": "verified"}]), 3)
        self.assertEqual(got[1]["verdict"], "contested")
        self.assertEqual(got[2]["verdict"], "contested")

    def test_unknown_verdict_becomes_contested(self):
        got = adj.parse_adjudication(json.dumps([{"cluster": 0, "verdict": "definitely-a-bug"}]), 1)
        self.assertEqual(got[0]["verdict"], "contested")

    def test_out_of_range_index_ignored(self):
        got = adj.parse_adjudication(json.dumps([{"cluster": 9, "verdict": "verified"}]), 1)
        self.assertEqual(got[0]["verdict"], "contested")

    def test_garbage_text_all_contested(self):
        got = adj.parse_adjudication("not json at all", 2)
        self.assertEqual([g["verdict"] for g in got], ["contested", "contested"])

    def test_prose_wrapped_json_still_parsed(self):
        got = adj.parse_adjudication('here you go:\n[{"cluster":0,"verdict":"verified"}]\nthanks', 1)
        self.assertEqual(got[0]["verdict"], "verified")


class TestEnforceCounterReference(unittest.TestCase):
    def test_refuted_without_counter_evidence_downgraded(self):
        v = adj.enforce_counter_reference([{"verdict": "refuted", "rationale": "nah", "counter_evidence": []}])
        self.assertEqual(v[0]["verdict"], "contested")
        self.assertIn("downgraded", v[0]["rationale"])

    def test_refuted_with_counter_evidence_kept(self):
        v = adj.enforce_counter_reference([
            {"verdict": "refuted", "rationale": "see line 5", "counter_evidence": [{"type": "code", "ref": "q.py:5"}]}
        ])
        self.assertEqual(v[0]["verdict"], "refuted")

    def test_verified_and_contested_untouched(self):
        v = adj.enforce_counter_reference([
            {"verdict": "verified", "counter_evidence": []},
            {"verdict": "contested", "counter_evidence": []},
        ])
        self.assertEqual([x["verdict"] for x in v], ["verified", "contested"])


class TestApplyAdjudication(unittest.TestCase):
    def test_nothing_dropped_and_bucketed(self):
        agg = _agg(3)
        verdicts = [
            {"verdict": "verified", "rationale": "", "counter_evidence": []},
            {"verdict": "refuted", "rationale": "wrong", "counter_evidence": [{"type": "code", "ref": "q.py:1"}]},
            {"verdict": "contested", "rationale": "", "counter_evidence": []},
        ]
        out = adj.apply_adjudication(agg, verdicts)
        self.assertEqual(len(out["findings"]), 3)
        self.assertEqual(out["bucket_counts"], {"verified": 1, "contested": 1, "refuted": 1})
        self.assertEqual(out["buckets"]["verified"], [0])
        self.assertEqual(out["buckets"]["refuted"], [1])
        self.assertEqual(out["stage"], "adjudicated")

    def test_refuted_without_ce_lands_in_contested_bucket(self):
        out = adj.apply_adjudication(_agg(1), [{"verdict": "refuted", "rationale": "x", "counter_evidence": []}])
        self.assertEqual(out["bucket_counts"], {"verified": 0, "contested": 1, "refuted": 0})

    def test_findings_sorted_verified_then_contested_then_refuted(self):
        out = adj.apply_adjudication(_agg(3), [
            {"verdict": "refuted", "rationale": "", "counter_evidence": [{"type": "code", "ref": "a:1"}]},
            {"verdict": "verified", "rationale": "", "counter_evidence": []},
            {"verdict": "contested", "rationale": "", "counter_evidence": []},
        ])
        order = [f["adjudication"]["verdict"] for f in out["findings"]]
        self.assertEqual(order, ["verified", "contested", "refuted"])

    def test_each_finding_gets_adjudication_block_and_orig_index(self):
        out = adj.apply_adjudication(_agg(2), [
            {"verdict": "verified", "rationale": "ok", "counter_evidence": []},
            {"verdict": "verified", "rationale": "ok2", "counter_evidence": []},
        ])
        for f in out["findings"]:
            self.assertIn("adjudication", f)
            self.assertIn("orig_index", f)


class TestAdjudicateNoClusters(unittest.TestCase):
    def test_empty_returns_adjudicated_with_empty_buckets(self):
        with tempfile.TemporaryDirectory() as d:
            out = adj.adjudicate({"status": "ok", "findings": []}, Path(d), "claude-sonnet-5")
        self.assertEqual(out["stage"], "adjudicated")
        self.assertEqual(out["bucket_counts"], {"verified": 0, "contested": 0, "refuted": 0})


class TestBuildPrompt(unittest.TestCase):
    def test_prompt_has_clusters_and_contract(self):
        with tempfile.TemporaryDirectory() as d:
            rd = Path(d)
            (rd / "input").mkdir()
            (rd / "input" / "diff.patch").write_text("--- a/q.py\n+++ b/q.py\n@@ -1 +1 @@\n-a\n+b\n")
            p = adj.build_prompt(_agg(2), rd)
        self.assertIn("[0]", p)
        self.assertIn("[1]", p)
        self.assertIn("counter_evidence", p)
        self.assertIn("```diff", p)


if __name__ == "__main__":
    unittest.main()
