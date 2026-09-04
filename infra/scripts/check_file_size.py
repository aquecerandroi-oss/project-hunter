#!/usr/bin/env python3
"""File-size gate for Python modules — the same 350-line budget the ESLint side
enforces with quality/max-lines (vibe-coding-toolkit).

Measures, never fixes. Exit 1 when any production module exceeds the budget.

Usage:
    python infra/scripts/check_file_size.py               # default budget 350
    python infra/scripts/check_file_size.py --max 350 --baseline infra/scripts/file_size_baseline.txt

A baseline file lists known offenders (one relative path per line) that are
reported as warnings instead of failures, exactly like the `ignore` option of
the ESLint rule. Shrink the baseline; never raise the budget.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOTS = ("apps", "services", "packages", "infra/scripts")
SKIP_DIRS = {
    ".venv", "node_modules", "__pycache__", "migrations", "generated", "__generated__",
    "fixtures", "mocks", "__mocks__", "tests", "__tests__", ".git", "dist", "build",
}
SKIP_NAMES = {"__init__.py", "conftest.py", "types.py", "constants.py", "enums.py"}


def is_checkable(path: Path) -> bool:
    if path.suffix != ".py" or path.name in SKIP_NAMES:
        return False
    if path.name.endswith(("_test.py", "_spec.py")) or path.name.startswith("test_"):
        return False
    return not any(part in SKIP_DIRS for part in path.parts)


def count_lines(path: Path) -> int:
    with path.open("rb") as fh:
        return sum(1 for _ in fh)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--max", type=int, default=350, help="line budget per file (default 350)")
    parser.add_argument("--baseline", type=Path, default=None, help="file with known offenders, one path per line")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="repository root")
    args = parser.parse_args()

    baseline: set[str] = set()
    if args.baseline and args.baseline.exists():
        baseline = {line.strip().replace("\\", "/") for line in args.baseline.read_text().splitlines() if line.strip()}

    offenders: list[tuple[int, str]] = []
    grandfathered: list[tuple[int, str]] = []
    scanned = 0
    for root in ROOTS:
        base = args.root / root
        if not base.exists():
            continue
        for path in base.rglob("*.py"):
            if not is_checkable(path.relative_to(args.root)):
                continue
            scanned += 1
            lines = count_lines(path)
            if lines > args.max:
                rel = path.relative_to(args.root).as_posix()
                (grandfathered if rel in baseline else offenders).append((lines, rel))

    for lines, rel in sorted(grandfathered, reverse=True):
        print(f"warn  {lines:5d} > {args.max}  {rel}  (baseline)")
    for lines, rel in sorted(offenders, reverse=True):
        print(f"error {lines:5d} > {args.max}  {rel}")
    print(f"scanned {scanned} files; {len(offenders)} over budget, {len(grandfathered)} grandfathered")
    return 1 if offenders else 0


if __name__ == "__main__":
    sys.exit(main())
