#!/usr/bin/env python3
"""Tier 2 routing: changed-file patterns -> the knowledge slice relevant to them.

docs/architecture.md sec. 1-2 splits a project's knowledge into three tiers:

  Tier 1  constitution.md         always loaded, byte-identical across nodes
  Tier 2  project/  (routed)      only the doc sections a route matched for this diff
  Tier 3  project-full/           the whole KB, for the node to search on demand

Until now `build_review_input.py` copied the entire `invariants.md` into Tier 2 --
"routed" in name only. This module does the real thing: read `routes.yaml`, match
each changed file against its glob patterns, and assemble only the cited sections
(anchor-addressable, e.g. `invariants.md#INV-2`) into the routed slice.

Pure except for `load_routes` / `write_routed_slice`; the matching and the
markdown section extraction are unit-tested with no filesystem.
"""
import fnmatch
import re
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - yaml is a declared dep, this is belt-and-braces
    yaml = None


def load_routes(project_dir) -> dict:
    """Parses `routes.yaml`. A missing/broken file yields {} -- routing then
    degrades to "everything is always-loaded", never an error that stops a run.
    """
    path = Path(project_dir) / "routes.yaml"
    if not path.exists() or yaml is None:
        return {}
    try:
        return yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError:
        return {}


def _basename_variants(changed_file: str):
    """A route pattern like "queue/lifecycle*" is written against the project's
    own layout, but a real `git diff` path is repo-relative
    ("demo-project/codebase/queue/lifecycle.py"). Yield the full path and every
    suffix so a pattern can match at whatever depth it was written for.
    """
    parts = changed_file.strip().lstrip("./").split("/")
    for i in range(len(parts)):
        yield "/".join(parts[i:])


def match_docs(changed_files, routes: dict) -> list:
    """Returns the sorted, de-duplicated list of doc refs relevant to this diff:
    every `always` entry, plus every `docs` entry whose `match` glob hits at
    least one changed file (at any path depth).
    """
    refs = set(routes.get("always") or [])
    for rule in routes.get("routes") or []:
        pattern = rule.get("match")
        if not pattern:
            continue
        for cf in changed_files:
            if any(fnmatch.fnmatch(v, pattern) for v in _basename_variants(cf)):
                refs.update(rule.get("docs") or [])
                break
    return sorted(refs)


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.strip().lower()).strip("-")


def extract_section(markdown: str, anchor: str) -> str:
    """Returns the markdown section whose heading slug matches `anchor`, from its
    heading line down to (but not including) the next heading at the same or a
    higher level. Anchor match is slug-based and case-insensitive, so
    `#INV-2`, `#inv-2` and `## INV-2` all line up. Returns "" if no heading matches.
    """
    want = _slug(anchor)
    lines = markdown.splitlines()
    out, capturing, start_level = [], False, 0
    for line in lines:
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level, title = len(m.group(1)), m.group(2)
            if capturing and level <= start_level:
                break
            if not capturing and _slug(title) == want:
                capturing, start_level = True, level
        if capturing:
            out.append(line)
    return "\n".join(out).strip()


def slice_ref(project_dir, ref: str):
    """Resolves one doc ref to (output_filename, content). `foo.md` -> the whole
    file; `foo.md#anchor` -> just that section. A ref to a missing file or a
    missing anchor yields (filename, "") -- the caller decides whether an empty
    slice is worth writing.
    """
    project_dir = Path(project_dir)
    if "#" in ref:
        filename, anchor = ref.split("#", 1)
    else:
        filename, anchor = ref, None
    src = project_dir / filename
    if not src.exists():
        return filename, ""
    text = src.read_text()
    if anchor is None:
        return filename, text.strip()
    return filename, extract_section(text, anchor)


def assemble_slices(project_dir, refs) -> dict:
    """Groups refs by target file and concatenates the selected sections, so a
    diff that routes to `invariants.md#INV-1` and `invariants.md#INV-2` produces
    one `invariants.md` holding just those two sections in file order. If a file
    is referenced whole (no `#anchor`) anywhere in `refs`, that wins and any
    anchor refs to the same file are dropped.
    """
    whole_file = {r for r in refs if "#" not in r}
    by_file = {}
    for ref in refs:
        filename = ref.split("#", 1)[0]
        if "#" in ref and filename in whole_file:
            continue  # whole-file ref already covers this
        _, content = slice_ref(project_dir, ref)
        if not content:
            continue
        chunks = by_file.setdefault(filename, [])
        if content not in chunks:
            chunks.append(content)

    return {fn: "\n\n".join(chunks).strip() + "\n" for fn, chunks in by_file.items()}


# Refs handled elsewhere in the input layout, so they're dropped from the Tier 2
# slice even when a route names them: the constitution is Tier 1 (copied whole,
# byte-stable), and profile.yaml is output config, not review knowledge.
_NOT_KNOWLEDGE = {"constitution.md", "profile.yaml", "routes.yaml"}


def routed_refs(project_dir, changed_files) -> list:
    """The doc refs a diff routes to, minus the ones handled outside Tier 2.
    Empty when there's no usable `routes.yaml` -- the caller then falls back to
    the full KB, preserving today's behaviour for un-routed projects.
    """
    routes = load_routes(project_dir)
    if not routes:
        return []
    return [r for r in match_docs(changed_files, routes)
            if r.split("#", 1)[0] not in _NOT_KNOWLEDGE]


def write_slice(project_dir, refs, out_dir) -> list:
    """Writes the assembled sections for `refs` into `out_dir`, one file per
    target doc. Returns the refs actually written (a ref whose file/anchor
    resolved to nothing is skipped).
    """
    assembled = assemble_slices(project_dir, refs)
    if not assembled:
        return []
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for filename, content in assembled.items():
        (out_dir / Path(filename).name).write_text(content)
    # report which refs contributed, in input order
    contributing = {r.split("#", 1)[0] for r in refs} & set(assembled)
    for r in refs:
        if r.split("#", 1)[0] in contributing:
            written.append(r)
    return written
