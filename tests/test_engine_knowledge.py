#!/usr/bin/env python3
"""Validates the two in-repo project knowledge bases (demo-project/ and
engine-knowledge/) against the routing engine: routes.yaml parses, every doc ref
a route points at resolves to a real section, and the always-list is sane. Cheap
guard against a typo'd anchor silently routing nothing.
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine" / "orchestrator"))


from _util import load_module as _load


route = _load("route", "engine/orchestrator/route.py")

PROJECTS = ["demo-project", "engine-knowledge"]


class TestKnowledgeBases(unittest.TestCase):
    def test_routes_yaml_parses(self):
        for proj in PROJECTS:
            routes = route.load_routes(REPO_ROOT / proj)
            self.assertTrue(routes, f"{proj}/routes.yaml did not parse")
            self.assertIn("routes", routes)

    def test_every_routed_ref_resolves(self):
        for proj in PROJECTS:
            proj_dir = REPO_ROOT / proj
            routes = route.load_routes(proj_dir)
            refs = set(routes.get("always") or [])
            for rule in routes["routes"]:
                refs.update(rule.get("docs") or [])
            for ref in sorted(refs):
                filename, content = route.slice_ref(proj_dir, ref)
                self.assertTrue(
                    content,
                    f"{proj}: route ref {ref!r} resolves to nothing "
                    f"(missing file or bad #anchor)",
                )

    def test_always_list_has_constitution(self):
        for proj in PROJECTS:
            routes = route.load_routes(REPO_ROOT / proj)
            self.assertIn("constitution.md", routes.get("always") or [])

    def test_engine_knowledge_routes_cover_the_real_tree(self):
        # Each route.match should be plausible against something that exists now,
        # so a rename doesn't leave a dead route unnoticed. (A route for a
        # not-yet-created file like adjudicate.py is allowed to miss.)
        proj_dir = REPO_ROOT / "engine-knowledge"
        routes = route.load_routes(proj_dir)
        known_future = {"engine/orchestrator/adjudicate.py", "engine/adapters/*/invoke.py"}
        for rule in routes["routes"]:
            pat = rule["match"]
            if pat in known_future:
                continue
            hits = list(REPO_ROOT.glob(pat))
            self.assertTrue(hits, f"engine-knowledge route {pat!r} matches nothing in the tree")


if __name__ == "__main__":
    unittest.main()
