"""Shared test helper: load an engine module by repo-relative path.

The engine scripts aren't a package (they use sys.path tricks at runtime), so
tests load them by file path. One copy of that loader, imported by every test
module, instead of the same six lines pasted into each.
"""
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_module(name: str, rel_path: str):
    spec = importlib.util.spec_from_file_location(name, REPO_ROOT / rel_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module
