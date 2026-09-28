"""``infra/vps/backup_postgres.sh`` — retention by COUNT of valid dumps (27/09/2026).

The design (``docs/design/retencao-e-disco-2026-09-27.md`` §4) and the Astra review
found that ``find -mtime +N`` does not keep N dumps: it keeps N+1, and a dump that
finished *later* in the night than tonight's survives one extra night. The script
now keeps the N newest ``hunter-<UTC stamp>.dump`` by name, only after tonight's
dump passed ``pg_restore --list`` (a night that fails deletes nothing), writes to
``.partial`` until then, and dumps without ``opportunity_history``'s data.

These tests run the real script under ``bash`` (sourced: the ``main`` guard keeps
sourcing side-effect free) with ``compose``/``stat`` replaced by shell functions —
no Docker, no Postgres.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(shutil.which("bash") is None, reason="bash not on PATH"),
]

SCRIPT = Path(__file__).resolve().parents[2] / "vps" / "backup_postgres.sh"
NIGHTS = [f"hunter-202609{day:02d}T011701Z.dump" for day in (23, 24, 25, 26)]

# ``compose`` stub: records every call, answers ``ps`` with a running postgres,
# ``pg_config`` with or without zstd, and fails ``pg_dump``/``pg_restore`` on demand.
STUBS = r"""
stat() { echo 700; }
compose() {
  echo "$*" >> "$CALLS"
  case "$*" in
    "ps --status running --services") echo postgres ;;
    *"pg_config --configure"*) echo "'--with-openssl' ${PG_CONFIG_EXTRA:-}" ;;
    *" pg_dump "*) [ -z "${FAIL_DUMP:-}" ] || return 1; echo "PGDMP fake dump" ;;
    *"pg_restore --list"*) cat >/dev/null; [ -z "${FAIL_LIST:-}" ] || return 1 ;;
  esac
}
"""


def _bash(snippet: str, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", f'source "$SCRIPT"\n{STUBS}\n{snippet}'],
        capture_output=True,
        text=True,
        env={**os.environ, "SCRIPT": SCRIPT.as_posix(), **env},
        check=False,
    )


def _nights(tmp_path: Path) -> Path:
    for index, name in enumerate(NIGHTS):
        path = tmp_path / name
        path.write_text("old dump")
        # Adversarial mtimes: the OLDEST name gets the NEWEST mtime — what
        # `-mtime` looked at and what a count by name must ignore.
        stamp = 1_800_000_000 - index * 3_600
        os.utime(path, (stamp, stamp))
    (tmp_path / "archive-meme_trades_2026_09.dump").write_text("monthly archive")
    leftover = tmp_path / "hunter-20260920T011701Z.dump.partial"
    leftover.write_text("a night that died mid-dump")
    seven_hours_ago = time.time() - 7 * 3_600
    os.utime(leftover, (seven_hours_ago, seven_hours_ago))
    return tmp_path


def _dumps(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir() if path.name.endswith(".dump"))


def test_bash_parses_the_script() -> None:
    result = subprocess.run(["bash", "-n", SCRIPT.as_posix()], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize(("keep", "left"), [(3, NIGHTS[1:]), (1, NIGHTS[3:]), (9, NIGHTS)])
def test_prune_keeps_the_newest_by_name_and_touches_nothing_else(
    tmp_path: Path, keep: int, left: list[str]
) -> None:
    directory = _nights(tmp_path)

    result = _bash(f'prune_dumps "{directory.as_posix()}" {keep}')

    assert result.returncode == 0, result.stderr
    assert _dumps(directory) == sorted([*left, "archive-meme_trades_2026_09.dump"])
    assert (directory / "hunter-20260920T011701Z.dump.partial").exists()


@pytest.mark.parametrize(("raw", "expected"), [("5", "5"), ("0", "1"), ("abc", "3")])
def test_the_count_comes_from_the_environment_and_never_drops_below_one(
    raw: str, expected: str
) -> None:
    result = _bash("retention_count", HUNTER_BACKUP_RETENTION_DAYS=raw)
    assert result.stdout.strip() == expected, result.stderr


def _night(tmp_path: Path, **env: str) -> tuple[subprocess.CompletedProcess[str], list[str]]:
    directory = _nights(tmp_path / "backups")
    calls = tmp_path / "calls.txt"
    result = _bash(
        "main",
        HUNTER_BACKUP_DIR=directory.as_posix(),
        HUNTER_BACKUP_RETENTION_DAYS="3",
        CALLS=calls.as_posix(),
        **env,
    )
    return result, calls.read_text().splitlines() if calls.exists() else []


def test_a_good_night_dumps_without_the_history_data_and_keeps_three(tmp_path: Path) -> None:
    (tmp_path / "backups").mkdir()
    result, calls = _night(tmp_path, PG_CONFIG_EXTRA="'--with-zstd'")

    assert result.returncode == 0, result.stdout + result.stderr
    dumps = [name for name in _dumps(tmp_path / "backups") if name.startswith("hunter-")]
    assert len(dumps) == 3 and dumps[:2] == NIGHTS[2:]
    assert not any(path.suffix == ".partial" for path in (tmp_path / "backups").iterdir())
    (dump_call,) = [call for call in calls if " pg_dump " in call]
    assert "-Fc -Z zstd:3 --exclude-table-data-and-children=opportunity_history" in dump_call
    assert "outbox" not in dump_call


def test_without_zstd_it_falls_back_to_the_default_and_says_so(tmp_path: Path) -> None:
    (tmp_path / "backups").mkdir()
    result, calls = _night(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr
    (dump_call,) = [call for call in calls if " pg_dump " in call]
    assert "-Z" not in dump_call.split()
    assert "sem zstd" in result.stderr


@pytest.mark.parametrize("failure", ["FAIL_DUMP", "FAIL_LIST"])
def test_a_failed_night_deletes_no_dump_and_leaves_no_partial(tmp_path: Path, failure: str) -> None:
    (tmp_path / "backups").mkdir()
    result, _ = _night(tmp_path, **{failure: "1"})

    assert result.returncode == 1
    assert _dumps(tmp_path / "backups") == sorted([*NIGHTS, "archive-meme_trades_2026_09.dump"])
    # Tonight's partial is removed; the dead night's leftover (> 6 h) is swept too.
    assert not any(p.suffix == ".partial" for p in (tmp_path / "backups").iterdir())
