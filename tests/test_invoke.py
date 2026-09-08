#!/usr/bin/env python3
"""Unit tests for the shared Claude invoke helper (engine/adapters/claude/invoke.py).
No real model call -- subprocess.run is stubbed. Run with:
python3 -m unittest tests.test_invoke -v
"""
import importlib.util
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine" / "adapters"))


def _load():
    spec = importlib.util.spec_from_file_location(
        "claude_invoke", REPO_ROOT / "engine" / "adapters" / "claude" / "invoke.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


invoke_mod = _load()


class _FakeCompleted:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class TestInvokePromptChannel(unittest.TestCase):
    def setUp(self):
        self.calls = []

        def fake_run(cmd, **kwargs):
            self.calls.append((cmd, kwargs))
            return _FakeCompleted(stdout='{"result": "{}", "usage": {}}')

        self._orig = invoke_mod.subprocess.run
        invoke_mod.subprocess.run = fake_run
        self.tmp = tempfile.mkdtemp()

    def tearDown(self):
        invoke_mod.subprocess.run = self._orig

    def test_prompt_goes_to_stdin_not_argv(self):
        big = "x" * 500_000  # would blow ARG_MAX if placed in argv
        invoke_mod.invoke(big, model="claude-sonnet-5", cwd=self.tmp)
        cmd, kwargs = self.calls[0]
        self.assertNotIn(big, cmd)
        self.assertEqual(kwargs.get("input"), big)
        # sanity: the command still asks for print + json
        self.assertIn("-p", cmd)
        self.assertIn("json", cmd)

    def test_append_system_still_passed(self):
        invoke_mod.invoke("hi", model="m", cwd=self.tmp, append_system="be careful")
        cmd, _ = self.calls[0]
        self.assertIn("--append-system-prompt", cmd)
        self.assertIn("be careful", cmd)

    def test_missing_cli_is_clean_error_not_raise(self):
        def boom(*a, **k):
            raise FileNotFoundError()
        invoke_mod.subprocess.run = boom
        out = invoke_mod.invoke("hi", model="m", cwd=self.tmp)
        self.assertFalse(out["ok"])
        self.assertIn("not found", out["error"])

    def test_nonzero_exit_is_clean_error(self):
        invoke_mod.subprocess.run = lambda *a, **k: _FakeCompleted(returncode=1, stderr="bad")
        out = invoke_mod.invoke("hi", model="m", cwd=self.tmp)
        self.assertFalse(out["ok"])
        self.assertIn("exited 1", out["error"])

    def test_is_error_envelope_is_clean_error(self):
        invoke_mod.subprocess.run = lambda *a, **k: _FakeCompleted(
            stdout='{"is_error": true, "result": "nope"}')
        out = invoke_mod.invoke("hi", model="m", cwd=self.tmp)
        self.assertFalse(out["ok"])

    def test_ok_envelope_returns_text(self):
        invoke_mod.subprocess.run = lambda *a, **k: _FakeCompleted(
            stdout='{"result": "the findings", "usage": {"input_tokens": 3}}')
        out = invoke_mod.invoke("hi", model="m", cwd=self.tmp)
        self.assertTrue(out["ok"])
        self.assertEqual(out["text"], "the findings")


class TestAdapterJsonRetry(unittest.TestCase):
    """adapter.run() retries once when the model ends with prose instead of JSON."""

    def setUp(self):
        spec = importlib.util.spec_from_file_location(
            "claude_adapter", REPO_ROOT / "engine" / "adapters" / "claude" / "adapter.py")
        self.ad = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.ad)
        self.tmp = Path(tempfile.mkdtemp())
        inp = self.tmp / "input"
        inp.mkdir()
        (inp / "role.md").write_text("r")
        (inp / "diff.patch").write_text("d")
        (inp / "manifest.json").write_text('{"language":"en"}')

    def _fake_invoke(self, texts):
        seen = []

        def fake(prompt, **kw):
            seen.append(prompt)
            return {"ok": True, "text": texts[min(len(seen) - 1, len(texts) - 1)],
                    "envelope": {"usage": {}}}
        self.ad.invoke = fake
        return seen

    def test_prose_then_json_recovers(self):
        seen = self._fake_invoke(["here are the findings", '{"status":"ok","findings":[]}'])
        out = self.ad.run(self.tmp, "m")
        self.assertEqual(out["status"], "ok")
        self.assertEqual(len(seen), 2)
        self.assertIn(self.ad._RETRY_NUDGE.strip()[:15], seen[1])

    def test_prose_twice_is_clean_error_after_two_attempts(self):
        seen = self._fake_invoke(["still just prose"])
        out = self.ad.run(self.tmp, "m")
        self.assertEqual(out["status"], "error")
        self.assertEqual(len(seen), 2)
        self.assertIn("2 attempts", out["error"])

    def test_first_attempt_json_does_not_retry(self):
        seen = self._fake_invoke(['{"status":"ok","findings":[]}'])
        self.ad.run(self.tmp, "m")
        self.assertEqual(len(seen), 1)


if __name__ == "__main__":
    unittest.main()
