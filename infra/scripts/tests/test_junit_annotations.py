"""Unit tests for ``infra/scripts/junit_annotations.py`` -- the step that makes a red
``python-test`` readable through the public check-runs API.

The XML below is shaped like what pytest 9 writes (``classname``/``name``, a ``message`` on
``<failure>``/``<error>``, the traceback as the node text); no file or line attributes, which is
why the script reads them out of the traceback.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:  # the layout every script in this folder uses
    sys.path.insert(0, str(SCRIPTS_DIR))

from junit_annotations import error_commands, main  # noqa: E402  (path surgery must come first)

REPORT = """<?xml version="1.0" encoding="utf-8"?>
<testsuites><testsuite name="pytest" errors="1" failures="2" tests="5">
<testcase classname="apps.api.tests.unit.test_a.TestC" name="test_one" time="0.1">
<failure message="AssertionError: assert 1 == 2&#10;second line">def test_one(): ...
E       AssertionError: assert 1 == 2
/usr/lib/python3.12/site-packages/pluggy/_callers.py:121: in _multicall
apps/api/tests/unit/test_a.py:42: AssertionError</failure></testcase>
<testcase classname="services.meme-worker.tests.test_b" name="test_two" time="0.1">
<failure message="100% wrong, really: a,b&#10;next">no location here</failure></testcase>
<testcase classname="apps.api.tests.unit.test_a" name="test_ok" time="0.1"/>
<testcase classname="apps.api.tests.unit.test_a" name="test_skipped" time="0.1">
<skipped type="pytest.skip" message="why">x</skipped></testcase>
<testcase classname="apps.api.tests.unit.test_a" name="test_setup" time="0.1">
<error message="failed on setup with &quot;file x.py, line 5&#10;  def test_setup(nofix):&quot;">
E       fixture 'nofix' not found
&gt;       available fixtures: a, b
apps/api/tests/unit/test_a.py:5</error></testcase>
</testsuite></testsuites>"""

EXISTING = {"apps/api/tests/unit/test_a.py", "services/meme-worker/tests/test_b.py"}


def _write(tmp_path: Path, body: str = REPORT) -> Path:
    path = tmp_path / "pytest-junit.xml"
    path.write_text(body, encoding="utf-8")
    return path


def test_one_error_command_per_failed_or_errored_test_and_nothing_for_green_or_skipped(
    tmp_path: Path,
) -> None:
    lines = error_commands(_write(tmp_path), exists=EXISTING.__contains__)

    assert len(lines) == 3
    assert all(line.startswith("::error ") for line in lines)
    assert not any("test_ok" in line or "test_skipped" in line for line in lines)


def test_the_location_comes_from_the_traceback_and_library_frames_are_skipped(
    tmp_path: Path,
) -> None:
    first = error_commands(_write(tmp_path), exists=EXISTING.__contains__)[0]

    # the last frame that is a file of this checkout; pluggy's is not, so it never wins
    assert first == (
        "::error file=apps/api/tests/unit/test_a.py,line=42,"
        "title=apps.api.tests.unit.test_a.TestC.test_one::AssertionError: assert 1 == 2"
    )


def test_without_a_traceback_location_the_file_is_recovered_from_the_classname_with_hyphens(
    tmp_path: Path,
) -> None:
    second = error_commands(_write(tmp_path), exists=EXISTING.__contains__)[1]

    assert second.startswith("::error file=services/meme-worker/tests/test_b.py,line=1,")
    # only the first line of the message, with the workflow-command escapes applied
    assert second.endswith("::100%25 wrong, really: a,b")


def test_a_setup_error_reports_the_exception_not_the_pytest_preamble(tmp_path: Path) -> None:
    setup = error_commands(_write(tmp_path), exists=EXISTING.__contains__)[2]

    assert "line=5" in setup
    assert setup.endswith("::failed on setup with - fixture 'nofix' not found")


def test_the_properties_are_escaped_and_a_missing_file_drops_file_and_line(
    tmp_path: Path,
) -> None:
    body = (
        '<testsuites><testsuite><testcase classname="x.y" name="test_a[1,2]">'
        '<failure message="boom">no location</failure></testcase></testsuite></testsuites>'
    )

    [line] = error_commands(_write(tmp_path, body), exists=lambda _path: False)

    assert line == "::error title=x.y.test_a[1%2C2]::boom"


def test_the_limit_caps_the_errors_and_says_how_many_were_left_out(tmp_path: Path) -> None:
    cases = "".join(
        f'<testcase classname="c" name="t{i}"><failure message="m{i}">x</failure></testcase>'
        for i in range(7)
    )
    body = f"<testsuites><testsuite>{cases}</testsuite></testsuites>"

    lines = error_commands(_write(tmp_path, body), limit=5, exists=lambda _path: False)

    assert [line.split("::")[-1] for line in lines[:5]] == [f"m{i}" for i in range(5)]
    assert lines[5] == (
        "::warning title=python-test::2 more failed or errored tests not annotated (limit 5);"
        " see the job log"
    )


def test_a_green_report_prints_nothing_and_a_missing_one_warns_instead_of_crashing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    green = '<testsuites><testsuite><testcase classname="c" name="t"/></testsuite></testsuites>'

    assert main([str(_write(tmp_path, green))]) == 0
    assert capsys.readouterr().out == ""
    assert main([str(tmp_path / "absent.xml")]) == 0
    assert capsys.readouterr().out.startswith("::warning title=python-test::")
