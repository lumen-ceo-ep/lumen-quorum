#!/usr/bin/env python3
"""Guards the synthetic demo ledger worked example (harness/build_demo_ledger.py):
it must stay deterministic and keep exercising both promote.py branches. Also a
de-facto integration test of record -> cluster -> promote against many records.
"""
import subprocess
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine" / "ledger"))


from _util import load_module as _load


record = _load("record", "engine/ledger/record.py")
cluster_mod = _load("cluster", "engine/ledger/cluster.py")

LEDGER = REPO_ROOT / "demo-project" / "ledger" / "ledger.jsonl"


class TestDemoLedger(unittest.TestCase):
    def test_regeneration_is_deterministic(self):
        before = LEDGER.read_text()
        subprocess.run([sys.executable, str(REPO_ROOT / "harness" / "build_demo_ledger.py")],
                       check=True, capture_output=True)
        self.assertEqual(LEDGER.read_text(), before,
                         "build_demo_ledger.py is not deterministic — commit churn")

    def test_committed_ledger_yields_two_clusters(self):
        clusters = cluster_mod.cluster(record.load_records(LEDGER))
        keys = {(c["category"], tuple(c["cited_refs"]), c["dominant_verdict"]) for c in clusters}
        self.assertIn(("convention", ("invariants.md#INV-2",), "corrected"), keys)
        self.assertIn(("correctness", (), "ignored"), keys)

    def test_accepted_records_do_not_cluster(self):
        clusters = cluster_mod.cluster(record.load_records(LEDGER))
        for c in clusters:
            self.assertNotEqual(c["dominant_verdict"], "accepted")


if __name__ == "__main__":
    unittest.main()
