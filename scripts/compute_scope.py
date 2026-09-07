#!/usr/bin/env python3
"""ShipReel scope computation: git diff → walkthrough scopes.

Usage: compute_scope.py <base-ref> <head-ref> [config-path]

Reads shipreel.yaml from the consuming repo (default: ./shipreel.yaml):

    watch:
      <scope-name>: [<path glob>, ...]   # surface name -> files that affect it
    ignore: [<path glob>, ...]           # never triggers recording (docs, CI, harness)

Rules:
  - only ignored files changed                -> SKIP  (no recording at all)
  - every changed file maps to watch scopes   -> those scopes only
  - any changed file matches nothing          -> FULL  (can't prove no user-facing impact)
  - no shipreel.yaml                          -> FULL

Prints exactly one line to stdout: SKIP | FULL | comma-separated scopes.
Stdlib only — runs on the GH runner's system python.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
import sys
from pathlib import Path


def load_config(path: Path) -> dict:
    """Minimal YAML subset parser for the shipreel.yaml shape (stdlib has no yaml).

    Supports exactly: top-level keys `watch:` (map of name -> list) and
    `ignore:` (flat list), 2-space indentation, double/single/bare scalars.
    """
    if not path.is_file():
        return {}
    watch: dict[str, list[str]] = {}
    ignore: list[str] = []
    section = None
    current_key = None
    strip_q = lambda s: s.strip().strip("\"'")
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip())
        line = raw.strip()
        if indent == 0 and line.endswith(":"):
            section = line[:-1]
            current_key = None
        elif section == "watch" and indent == 2 and ":" in line:
            key, _, rest = line.partition(":")
            current_key = strip_q(key)
            watch[current_key] = []
            rest = rest.strip()
            if rest.startswith("["):  # flow-style list: Key: ["a", "b"]
                items = rest.strip("[]")
                watch[current_key] = [strip_q(i) for i in items.split(",") if i.strip()]
        elif section == "watch" and indent >= 4 and line.startswith("-") and current_key:
            watch[current_key].append(strip_q(line[1:]))
        elif section == "ignore" and indent >= 2 and line.startswith("-"):
            ignore.append(strip_q(line[1:]))
    return {"watch": watch, "ignore": ignore}


_GLOB_CHARS = re.compile(r"(\*\*|\*|\?)")


def glob_to_regex(pattern: str) -> re.Pattern:
    """`**` crosses directories, `*`/`?` stay within one path segment."""
    parts = _GLOB_CHARS.split(pattern)
    out = []
    for p in parts:
        if p == "**":
            out.append(".*")
        elif p == "*":
            out.append("[^/]*")
        elif p == "?":
            out.append("[^/]")
        else:
            out.append(re.escape(p))
    return re.compile("^" + "".join(out) + "$")


def matches(patterns: list[str], path: str) -> bool:
    return any(glob_to_regex(g).match(path) for g in patterns)


def changed_files(base: str, head: str) -> list[str]:
    # First-push guard: all-zero base (branch creation) → diff against empty tree.
    if set(base) == {"0"}:
        base = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
    out = subprocess.run(
        # Three-dot: diff from the merge-base — the PR's own changes, matching
        # GitHub's "Files changed". Two-dot would pick up unrelated base-branch
        # movement as reverse-diffs and over-trigger FULL.
        ["git", "diff", "--name-only", f"{base}...{head}"],
        check=True, capture_output=True, text=True,
    )
    return [f for f in out.stdout.splitlines() if f.strip()]


def compute(base: str, head: str, config_path: str = "shipreel.yaml") -> str:
    if not base.strip() or not head.strip():
        return "FULL"  # e.g. manual dispatch without event SHAs
    cfg = load_config(Path(config_path))
    watch: dict[str, list[str]] = cfg.get("watch", {})
    ignore: list[str] = cfg.get("ignore", [])
    files = changed_files(base, head)
    if not files:
        return "SKIP"
    if not watch:
        return "FULL"
    scopes: set[str] = set()
    for f in files:
        if ignore and matches(ignore, f):
            continue
        hit = False
        for scope, globs in watch.items():
            if matches(globs, f):
                hit = True
                scopes.add(scope)
        if not hit:
            return "FULL"
    if not scopes:
        return "SKIP"
    # Watch-map order (= the app's nav order), not diff order.
    return ",".join(s for s in watch if s in scopes)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: compute_scope.py <base-ref> <head-ref> [config-path]")
    cfg = sys.argv[3] if len(sys.argv) > 3 else "shipreel.yaml"
    print(compute(sys.argv[1], sys.argv[2], cfg))
