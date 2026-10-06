#!/usr/bin/env python3
"""Turn a pytest JUnit XML into GitHub ``::error`` workflow commands.

Why it exists: the log of a failed CI job needs a login, but the **annotations** of a check run
are public (``GET /repos/{owner}/{repo}/check-runs/{id}/annotations``). Run on failure, this prints
one ``::error file=<path>,line=<line>,title=<test id>::<first line of the message>`` per failed or
errored test, so a red ``python-test`` says *which* tests failed and why without anybody opening
the log.

Stdlib only, no repository imports: the job that runs it has just failed and must not depend on
anything that might be the reason it failed.

Usage:
    python infra/scripts/junit_annotations.py pytest-junit.xml [--limit 50]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET  # nosec B405 -- our own pytest output, not remote input
from collections.abc import Callable
from pathlib import Path

DEFAULT_LIMIT = 50
"""GitHub shows at most ten annotations per step in the summary but stores up to fifty per
check-run update; more than this is noise."""

MESSAGE_CHARS = 300
_TRACE_LOCATION = re.compile(r"^(?P<path>[\w./\\-]+\.py):(?P<line>\d+)(?::|$)")
_SETUP_PREFIXES = ("failed on setup", "failed on teardown")
_QUOTE = '"'


def _escape_data(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(value: str) -> str:
    return _escape_data(value).replace(":", "%3A").replace(",", "%2C")


def _location(text: str, exists: Callable[[str], bool]) -> tuple[str | None, int | None]:
    """The last ``path.py:line`` of the traceback that is a file of this checkout.

    pytest ends a failure with ``<path>:<line>: <Error>``; on the runner the path is relative to
    the workspace, which is what ``file=`` wants. Anything that does not exist here (a library
    frame, an absolute path from another machine) is skipped, not guessed.
    """
    for raw in reversed(text.splitlines()):
        match = _TRACE_LOCATION.match(raw.strip())
        if match is None:
            continue
        path = match["path"].replace("\\", "/")
        if exists(path):
            return path, int(match["line"])
    return None, None


def _file_from_classname(classname: str, exists: Callable[[str], bool]) -> str | None:
    """``apps.api.tests.unit.test_x.TestC`` -> ``apps/api/tests/unit/test_x.py``.

    Directory names carry hyphens (``services/meme-worker``), so the dots are only a hint: try the
    longest dotted prefix first and give up quietly when nothing matches.
    """
    parts = classname.split(".")
    for end in range(len(parts), 0, -1):
        candidate = "/".join(parts[:end]) + ".py"
        if exists(candidate):
            return candidate
    return None


def _first_line(message: str, text: str) -> str:
    line = next((raw.strip() for raw in message.splitlines() if raw.strip()), "")
    if line.lower().startswith(_SETUP_PREFIXES):
        # "failed on setup with <whole fixture traceback>": the useful part is the exception.
        errors = [raw[1:].strip() for raw in text.splitlines() if raw.startswith("E ")]
        if errors:
            line = f"{line.split(_QUOTE)[0].strip()} - {errors[-1]}"
    return line[:MESSAGE_CHARS] or "(no message)"


def error_commands(
    xml_path: str | Path,
    *,
    limit: int = DEFAULT_LIMIT,
    exists: Callable[[str], bool] = os.path.exists,
) -> list[str]:
    """One workflow command per failed or errored test, at most ``limit``, plus a note if capped."""
    root = ET.parse(xml_path).getroot()  # nosec B314 -- our own pytest output
    problems: list[tuple[str, str, str, str]] = []
    for case in root.iter("testcase"):
        for kind in ("failure", "error"):
            node = case.find(kind)
            if node is None:
                continue
            classname = case.get("classname", "")
            test_id = f"{classname}.{case.get('name', '?')}".strip(".")
            problems.append((classname, test_id, node.get("message", ""), node.text or ""))
            break
    lines: list[str] = []
    for classname, test_id, message, text in problems[:limit]:
        path, line = _location(text, exists)
        if path is None:
            path = _file_from_classname(classname, exists)
        properties: list[str] = []
        if path is not None:
            properties.append(f"file={_escape_property(path)}")
            properties.append(f"line={line or 1}")
        properties.append(f"title={_escape_property(test_id)}")
        lines.append(f"::error {','.join(properties)}::{_escape_data(_first_line(message, text))}")
    if len(problems) > limit:
        lines.append(
            f"::warning title=python-test::{len(problems) - limit} more failed or errored tests "
            f"not annotated (limit {limit}); see the job log"
        )
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("xml", help="pytest --junitxml output")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    args = parser.parse_args(argv)
    if not Path(args.xml).is_file():
        # The run died before pytest wrote the report (collection error, killed runner).
        sys.stdout.write(f"::warning title=python-test::{args.xml} was not produced\n")
        return 0
    for command in error_commands(args.xml, limit=args.limit):
        sys.stdout.write(command + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
