#!/usr/bin/env python3
"""Unit tests for Tier 2 routing (engine/orchestrator/route.py). Pure logic --
run with: python3 -m unittest tests.test_routing -v
"""
import importlib.util
import sys
import tempfile
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


route = _load("route", "engine/orchestrator/route.py")

ROUTES = {
    "routes": [
        {"match": "queue/lifecycle*", "docs": ["invariants.md#INV-1"]},
        {"match": "queue/enqueue*", "docs": ["invariants.md#INV-2"]},
        {"match": "queue/retry*", "docs": ["invariants.md#INV-3"]},
    ],
    "always": ["constitution.md", "profile.yaml"],
}

INVARIANTS_MD = """# Invariants

## INV-1
A CANCELLED task must never transition to RUNNING.

## INV-2
enqueue() must reject out-of-range priority, not clamp it.

## INV-3
Retry must reuse the original task_id.
"""


class TestMatchDocs(unittest.TestCase):
    def test_matches_at_repo_relative_depth(self):
        got = route.match_docs(["demo-project/codebase/queue/lifecycle.py"], ROUTES)
        self.assertIn("invariants.md#INV-1", got)

    def test_matches_at_project_relative_depth(self):
        got = route.match_docs(["queue/enqueue.py"], ROUTES)
        self.assertIn("invariants.md#INV-2", got)

    def test_always_docs_included_regardless(self):
        got = route.match_docs(["totally/unrelated/file.py"], ROUTES)
        self.assertEqual(got, ["constitution.md", "profile.yaml"])

    def test_only_relevant_invariant_routed(self):
        got = route.match_docs(["queue/retry.py"], ROUTES)
        self.assertIn("invariants.md#INV-3", got)
        self.assertNotIn("invariants.md#INV-1", got)
        self.assertNotIn("invariants.md#INV-2", got)

    def test_multiple_changed_files_union(self):
        got = route.match_docs(["queue/lifecycle.py", "queue/retry.py"], ROUTES)
        self.assertIn("invariants.md#INV-1", got)
        self.assertIn("invariants.md#INV-3", got)

    def test_empty_routes_returns_empty(self):
        self.assertEqual(route.match_docs(["queue/lifecycle.py"], {}), [])


class TestExtractSection(unittest.TestCase):
    def test_extracts_single_section(self):
        sec = route.extract_section(INVARIANTS_MD, "INV-2")
        self.assertIn("## INV-2", sec)
        self.assertIn("reject out-of-range", sec)
        self.assertNotIn("INV-1", sec)
        self.assertNotIn("INV-3", sec)

    def test_anchor_match_is_slug_and_case_insensitive(self):
        self.assertTrue(route.extract_section(INVARIANTS_MD, "inv-2"))
        self.assertTrue(route.extract_section(INVARIANTS_MD, "INV-2"))

    def test_last_section_runs_to_end(self):
        sec = route.extract_section(INVARIANTS_MD, "INV-3")
        self.assertIn("reuse the original task_id", sec)

    def test_missing_anchor_returns_empty(self):
        self.assertEqual(route.extract_section(INVARIANTS_MD, "INV-9"), "")

    def test_nested_lower_heading_does_not_end_section(self):
        md = "## A\ntext\n### A.1\nmore\n## B\nother\n"
        sec = route.extract_section(md, "A")
        self.assertIn("### A.1", sec)
        self.assertIn("more", sec)
        self.assertNotIn("other", sec)


class TestAssembleAndWrite(unittest.TestCase):
    def _project(self, d):
        (Path(d) / "invariants.md").write_text(INVARIANTS_MD)
        (Path(d) / "constitution.md").write_text("# Constitution\nrubric\n")
        return Path(d)

    def test_assemble_groups_by_file_in_order(self):
        with tempfile.TemporaryDirectory() as d:
            proj = self._project(d)
            out = route.assemble_slices(proj, ["invariants.md#INV-3", "invariants.md#INV-1"])
            self.assertIn("invariants.md", out)
            body = out["invariants.md"]
            self.assertIn("INV-1", body)
            self.assertIn("INV-3", body)
            self.assertNotIn("INV-2", body)

    def test_whole_file_ref_dedupes_against_anchor_ref(self):
        with tempfile.TemporaryDirectory() as d:
            proj = self._project(d)
            out = route.assemble_slices(proj, ["invariants.md", "invariants.md#INV-1"])
            # whole file already contains INV-1; must not be doubled
            self.assertEqual(out["invariants.md"].count("A CANCELLED task"), 1)

    def test_routed_refs_drops_constitution_and_profile(self):
        with tempfile.TemporaryDirectory() as d:
            proj = self._project(d)
            (proj / "routes.yaml").write_text(
                "routes:\n"
                "  - match: 'queue/enqueue*'\n"
                "    docs: [invariants.md#INV-2]\n"
                "always: [constitution.md, profile.yaml]\n"
            )
            refs = route.routed_refs(proj, ["queue/enqueue.py"])
            self.assertEqual(refs, ["invariants.md#INV-2"])

    def test_write_slice_emits_only_routed_section(self):
        with tempfile.TemporaryDirectory() as d:
            proj = self._project(d)
            out_dir = proj / "out"
            written = route.write_slice(proj, ["invariants.md#INV-2"], out_dir)
            self.assertEqual(written, ["invariants.md#INV-2"])
            content = (out_dir / "invariants.md").read_text()
            self.assertIn("INV-2", content)
            self.assertNotIn("INV-1", content)

    def test_no_routes_yaml_gives_empty_routed_refs(self):
        with tempfile.TemporaryDirectory() as d:
            proj = self._project(d)  # no routes.yaml written
            self.assertEqual(route.routed_refs(proj, ["queue/enqueue.py"]), [])


if __name__ == "__main__":
    unittest.main()
