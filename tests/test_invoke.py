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


class TestAdapterFileFirst(unittest.TestCase):
    """adapter.run() reads the node-findings.json file the node writes; the chat
    message is only a fallback, and it retries once if neither parses."""

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
        self.target = self.tmp / "out" / "node-findings.json"

    def _fake_invoke(self, behaviours):
        """behaviours[i] is called for attempt i+1; it may write self.target and
        returns the chat text to hand back."""
        seen = []

        def fake(prompt, **kw):
            seen.append(prompt)
            return {"ok": True, "text": behaviours[min(len(seen) - 1, len(behaviours) - 1)](),
                    "envelope": {"usage": {}}}
        self.ad.invoke = fake
        return seen

    def test_file_is_used_over_chat_text(self):
        def write_file_and_ramble():
            self.target.write_text('{"status":"ok","findings":[{"file":"a","line":1,'
                                   '"category":"correctness","severity":"nit","claim":"c"}]}')
            return "I wrote the findings to the file, here's a summary..."
        seen = self._fake_invoke([write_file_and_ramble])
        out = self.ad.run(self.tmp, "m")
        self.assertEqual(out["status"], "ok")
        self.assertEqual(len(out["findings"]), 1)
        self.assertEqual(len(seen), 1)

    def test_falls_back_to_chat_text_when_no_file(self):
        seen = self._fake_invoke([lambda: '{"status":"ok","findings":[]}'])
        out = self.ad.run(self.tmp, "m")
        self.assertEqual(out["status"], "ok")
        self.assertEqual(len(seen), 1)

    def test_stale_file_from_prior_run_is_cleared(self):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text('{"status":"ok","findings":[{"file":"STALE","line":1,'
                               '"category":"correctness","severity":"nit","claim":"old"}]}')
        seen = self._fake_invoke([lambda: '{"status":"ok","findings":[]}'])  # writes nothing
        out = self.ad.run(self.tmp, "m")
        self.assertEqual(out["findings"], [])  # not the stale one

    def test_retry_when_file_and_text_both_bad_then_error(self):
        seen = self._fake_invoke([lambda: "just prose, no file"])
        out = self.ad.run(self.tmp, "m")
        self.assertEqual(out["status"], "error")
        self.assertEqual(len(seen), 2)
        self.assertIn("2 attempts", out["error"])

    def test_retry_recovers_on_second_attempt(self):
        calls = {"n": 0}

        def maybe_write():
            calls["n"] += 1
            if calls["n"] == 2:
                self.target.write_text('{"status":"ok","findings":[]}')
            return "prose"
        seen = self._fake_invoke([maybe_write])
        out = self.ad.run(self.tmp, "m")
        self.assertEqual(out["status"], "ok")
        self.assertEqual(len(seen), 2)


if __name__ == "__main__":
    unittest.main()
