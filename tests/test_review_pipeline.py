#!/usr/bin/env python3
"""Unit tests for the language-selection feature. Pure logic, no API calls --
run with: python3 -m unittest tests/test_language.py -v
"""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(module_name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(module_name, REPO_ROOT / rel_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


build_review_input = _load("build_review_input", "engine/orchestrator/build_review_input.py")
adapter = _load("claude_adapter", "engine/adapters/claude/adapter.py")


class TestResolveLanguage(unittest.TestCase):
    def test_override_wins_over_everything(self):
        profile = {"output": {"language": "ja"}}
        lang, source = build_review_input.resolve_language("ko", profile)
        self.assertEqual(lang, "ko")
        self.assertEqual(source, "override")

    def test_profile_wins_over_default_when_no_override(self):
        profile = {"output": {"language": "ja"}}
        lang, source = build_review_input.resolve_language(None, profile)
        self.assertEqual(lang, "ja")
        self.assertEqual(source, "profile")

    def test_falls_back_to_default_when_nothing_set(self):
        lang, source = build_review_input.resolve_language(None, {})
        self.assertEqual(lang, build_review_input.DEFAULT_LANGUAGE)
        self.assertEqual(source, "default")

    def test_falls_back_to_default_when_profile_has_no_output_key(self):
        lang, source = build_review_input.resolve_language(None, {"severity_vocab": []})
        self.assertEqual(lang, build_review_input.DEFAULT_LANGUAGE)
        self.assertEqual(source, "default")

    def test_empty_string_override_does_not_win(self):
        # An empty string is falsy -- argparse gives None when --lang is omitted,
        # but defensively confirm "" behaves the same as not-set rather than
        # silently becoming the language.
        profile = {"output": {"language": "ja"}}
        lang, source = build_review_input.resolve_language("", profile)
        self.assertEqual(lang, "ja")
        self.assertEqual(source, "profile")


class TestLoadProfile(unittest.TestCase):
    def test_missing_file_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(build_review_input.load_profile(Path(d)), {})

    def test_valid_profile_parses(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "profile.yaml").write_text("output:\n  language: ko\n")
            profile = build_review_input.load_profile(Path(d))
            self.assertEqual(profile["output"]["language"], "ko")

    def test_malformed_yaml_returns_empty_dict_not_raise(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "profile.yaml").write_text("output:\n  language: [unclosed\n")
            # Must not raise -- a broken profile.yaml should degrade to defaults,
            # not take down the whole review run.
            self.assertEqual(build_review_input.load_profile(Path(d)), {})

    def test_empty_file_returns_empty_dict(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "profile.yaml").write_text("")
            self.assertEqual(build_review_input.load_profile(Path(d)), {})


class TestLanguageInstruction(unittest.TestCase):
    def test_english_produces_no_instruction_block(self):
        self.assertEqual(adapter.language_instruction("en"), "")
        self.assertEqual(adapter.language_instruction("English"), "")
        self.assertEqual(adapter.language_instruction("EN"), "")

    def test_non_english_produces_instruction_naming_the_language(self):
        block = adapter.language_instruction("ko")
        self.assertIn("ko", block)
        self.assertIn("literal", block.lower())  # "not a literal translation"

    def test_instruction_preserves_structural_fields(self):
        block = adapter.language_instruction("Korean")
        # The instruction must explicitly say enum values / field names stay
        # English, or a model could plausibly "helpfully" translate them too.
        self.assertIn("category", block)
        self.assertIn("severity", block)


class TestLoadLanguage(unittest.TestCase):
    def test_missing_manifest_defaults_to_english(self):
        with tempfile.TemporaryDirectory() as d:
            review_dir = Path(d)
            (review_dir / "input").mkdir()
            self.assertEqual(adapter.load_language(review_dir), "en")

    def test_reads_language_from_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            review_dir = Path(d)
            input_dir = review_dir / "input"
            input_dir.mkdir()
            (input_dir / "manifest.json").write_text(json.dumps({"language": "ja"}))
            self.assertEqual(adapter.load_language(review_dir), "ja")

    def test_malformed_manifest_defaults_to_english_not_raise(self):
        with tempfile.TemporaryDirectory() as d:
            review_dir = Path(d)
            input_dir = review_dir / "input"
            input_dir.mkdir()
            (input_dir / "manifest.json").write_text("{not valid json")
            self.assertEqual(adapter.load_language(review_dir), "en")

    def test_manifest_without_language_key_defaults_to_english(self):
        with tempfile.TemporaryDirectory() as d:
            review_dir = Path(d)
            input_dir = review_dir / "input"
            input_dir.mkdir()
            (input_dir / "manifest.json").write_text(json.dumps({"base": "abc"}))
            self.assertEqual(adapter.load_language(review_dir), "en")


class TestVerifyCoverage(unittest.TestCase):
    def _review_dir_with_manifest(self, tmpdir, files_in_diff):
        review_dir = Path(tmpdir)
        input_dir = review_dir / "input"
        input_dir.mkdir()
        (input_dir / "manifest.json").write_text(json.dumps({"files_in_diff": files_in_diff}))
        return review_dir

    def test_no_manifest_returns_coverage_unchanged(self):
        with tempfile.TemporaryDirectory() as d:
            review_dir = Path(d)
            (review_dir / "input").mkdir()
            coverage = {"files_read": ["a.py"]}
            self.assertEqual(adapter.verify_coverage(review_dir, coverage), coverage)

    def test_full_coverage_produces_no_warning(self):
        with tempfile.TemporaryDirectory() as d:
            review_dir = self._review_dir_with_manifest(d, ["queue/lifecycle.py"])
            coverage = {"files_read": ["queue/lifecycle.py"], "not_read_reason": None}
            result = adapter.verify_coverage(review_dir, coverage)
            self.assertNotIn("mechanically_verified_missing", result)
            self.assertIsNone(result["not_read_reason"])

    def test_missed_file_is_mechanically_detected_even_without_self_report(self):
        with tempfile.TemporaryDirectory() as d:
            review_dir = self._review_dir_with_manifest(d, ["queue/lifecycle.py", "queue/enqueue.py"])
            # Model only reported reading one file and didn't flag anything wrong.
            coverage = {"files_read": ["queue/lifecycle.py"], "not_read_reason": None}
            result = adapter.verify_coverage(review_dir, coverage)
            self.assertEqual(result["mechanically_verified_missing"], ["queue/enqueue.py"])
            self.assertIsNotNone(result["not_read_reason"])

    def test_self_reported_reason_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as d:
            review_dir = self._review_dir_with_manifest(d, ["queue/lifecycle.py", "queue/enqueue.py"])
            coverage = {"files_read": ["queue/lifecycle.py"], "not_read_reason": "budget"}
            result = adapter.verify_coverage(review_dir, coverage)
            self.assertEqual(result["not_read_reason"], "budget")
            self.assertEqual(result["mechanically_verified_missing"], ["queue/enqueue.py"])

    def test_suffix_matching_handles_different_relative_path_forms(self):
        with tempfile.TemporaryDirectory() as d:
            # files_in_diff is repo-relative; files_read is workspace-relative.
            review_dir = self._review_dir_with_manifest(d, ["demo-project/codebase/queue/lifecycle.py"])
            coverage = {"files_read": ["queue/lifecycle.py"]}
            result = adapter.verify_coverage(review_dir, coverage)
            self.assertNotIn("mechanically_verified_missing", result)


class TestApplyEvidenceGate(unittest.TestCase):
    def test_convention_finding_with_project_evidence_passes_through(self):
        findings = [{
            "category": "convention", "severity": "blocking",
            "evidence": [{"type": "project", "ref": "invariants.md#INV-1"}],
            "claim": "violates INV-1",
        }]
        gated, demotions = adapter.apply_evidence_gate(findings)
        self.assertEqual(gated[0]["severity"], "blocking")
        self.assertEqual(demotions, [])

    def test_convention_finding_without_project_evidence_is_demoted(self):
        findings = [{
            "category": "convention", "severity": "blocking",
            "evidence": [{"type": "code", "ref": "x.py:1"}],  # code evidence, no project evidence
            "claim": "seems wrong",
        }]
        gated, demotions = adapter.apply_evidence_gate(findings)
        self.assertEqual(gated[0]["severity"], "nit")
        self.assertIn("evidence gate", gated[0]["claim"])
        self.assertEqual(len(demotions), 1)

    def test_convention_finding_with_no_evidence_at_all_is_demoted(self):
        findings = [{"category": "convention", "severity": "major", "claim": "x"}]
        gated, demotions = adapter.apply_evidence_gate(findings)
        self.assertEqual(gated[0]["severity"], "nit")
        self.assertEqual(len(demotions), 1)

    def test_correctness_finding_with_failure_scenario_passes_through(self):
        findings = [{
            "category": "correctness", "severity": "blocking",
            "failure_scenario": "calling f(-1) raises instead of returning 0",
            "claim": "off-by-one",
        }]
        gated, demotions = adapter.apply_evidence_gate(findings)
        self.assertEqual(gated[0]["severity"], "blocking")
        self.assertEqual(demotions, [])

    def test_correctness_finding_without_failure_scenario_is_demoted(self):
        findings = [{"category": "correctness", "severity": "blocking", "claim": "looks buggy"}]
        gated, demotions = adapter.apply_evidence_gate(findings)
        self.assertEqual(gated[0]["severity"], "nit")
        self.assertEqual(len(demotions), 1)

    def test_simplification_category_is_not_gated(self):
        # Only convention and correctness have a defined evidence requirement --
        # simplification findings aren't held to either rule.
        findings = [{"category": "simplification", "severity": "minor", "claim": "duplicate helper"}]
        gated, demotions = adapter.apply_evidence_gate(findings)
        self.assertEqual(gated[0]["severity"], "minor")
        self.assertEqual(demotions, [])

    def test_nothing_dropped_only_demoted(self):
        findings = [
            {"category": "convention", "severity": "blocking", "claim": "a"},
            {"category": "correctness", "severity": "blocking", "claim": "b"},
        ]
        gated, demotions = adapter.apply_evidence_gate(findings)
        self.assertEqual(len(gated), 2)  # both stay in the list
        self.assertEqual(len(demotions), 2)

    def test_original_findings_list_not_mutated(self):
        original = [{"category": "convention", "severity": "blocking", "claim": "a"}]
        adapter.apply_evidence_gate(original)
        self.assertEqual(original[0]["severity"], "blocking")  # unchanged


if __name__ == "__main__":
    unittest.main()
