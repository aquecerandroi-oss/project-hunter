"""Marker-preserving writer tests — brief T3.20 item 5: hand-written text below
the block survives, and a second run with the same inputs is a no-op.

Run: ``uv run pytest infra/scripts/tests/test_obsidian_marker_writer.py -q``
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from obsidian_marker_writer import (  # noqa: E402
    GENERATED_END,
    GENERATED_START,
    MarkerError,
    apply_write,
    plan_write,
)

FRONTMATTER = "---\nstrategy: momentum\n---\n"


def test_creates_a_missing_page_with_a_notes_stub(tmp_path: Path) -> None:
    path = tmp_path / "momentum-v2.md"

    diff = plan_write(path, FRONTMATTER, "momentum v2", "## Parâmetros\n\nsomething")

    assert diff.action == "create"
    assert diff.before is None
    assert GENERATED_START in diff.after
    assert GENERATED_END in diff.after
    assert diff.after.endswith("## Notas\n\n")
    apply_write(diff, dry_run=False)
    assert path.read_text(encoding="utf-8") == diff.after


def test_dry_run_never_touches_disk(tmp_path: Path) -> None:
    path = tmp_path / "momentum-v2.md"
    diff = plan_write(path, FRONTMATTER, "momentum v2", "body")

    apply_write(diff, dry_run=True)

    assert not path.exists()


def test_second_run_with_identical_inputs_is_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "momentum-v2.md"
    first = plan_write(path, FRONTMATTER, "momentum v2", "## Parâmetros\n\nsomething")
    apply_write(first, dry_run=False)

    second = plan_write(path, FRONTMATTER, "momentum v2", "## Parâmetros\n\nsomething")

    assert second.action == "unchanged"
    assert second.after == first.after


def test_hand_written_notes_below_the_marker_survive_a_regenerated_body(tmp_path: Path) -> None:
    path = tmp_path / "momentum-v2.md"
    first = plan_write(path, FRONTMATTER, "momentum v2", "## Parâmetros\n\nold value")
    apply_write(first, dry_run=False)

    # Sexta-feira writes something by hand below the generated block.
    hand_written = "\n\n## Notas\n\nAstra concorda com o piso de custo.\n"
    path.write_text(
        first.after.split(GENERATED_END)[0] + GENERATED_END + hand_written, encoding="utf-8"
    )

    second = plan_write(path, FRONTMATTER, "momentum v2", "## Parâmetros\n\nnew value")
    apply_write(second, dry_run=False)

    written = path.read_text(encoding="utf-8")
    assert "new value" in written
    assert "old value" not in written
    assert "Astra concorda com o piso de custo." in written


def test_missing_markers_on_an_existing_page_refuses_instead_of_guessing(tmp_path: Path) -> None:
    path = tmp_path / "momentum-v2.md"
    path.write_text("---\nstrategy: momentum\n---\n# hand-written, no markers\n", encoding="utf-8")

    with pytest.raises(MarkerError):
        plan_write(path, FRONTMATTER, "momentum v2", "body")


def test_never_deletes_a_page_outside_this_runs_roster(tmp_path: Path) -> None:
    untouched = tmp_path / "breakout-v1.md"
    untouched.write_text("keep me", encoding="utf-8")

    path = tmp_path / "momentum-v2.md"
    apply_write(plan_write(path, FRONTMATTER, "momentum v2", "body"), dry_run=False)

    assert untouched.read_text(encoding="utf-8") == "keep me"
