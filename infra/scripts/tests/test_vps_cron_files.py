"""The cron files under ``infra/vps/cron/`` never overlap the nightly dump.

``docs/design/retencao-e-disco-2026-09-27.md`` §6: the partition jobs take
``ACCESS EXCLUSIVE`` on a parent and the dump holds ``ACCESS SHARE`` on every
table for 80+ minutes, so a job scheduled inside the dump either queues (and
the ingestion queues behind it) or, with ``lock_timeout``, skips every night.
The README's first recipes (04:07/04:37 machine time) sat inside that window.

Both schedules are in the machine's clock (Europe/Berlin), the dump's too
(``bootstrap_vps.sh``, ``17 3 * * *``), so the distance between them does not
move with daylight saving — except on the night summer time begins, when the
skipped hour shortens every gap by 60 min (Astra, review prune-locks): the
partition jobs take seconds and the pruner refuses while a dump is connected,
the outbox prune does not lock against the dump. The dump start is read from
the bootstrap, not restated here. No Docker, no network.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]
CRON_DIR = REPO_ROOT / "infra" / "vps" / "cron"
DUMP_WINDOW_MIN = 150
"""The 26/09 dump took 81 min and grows; 150 min is the margin the jobs keep."""

_JOB = re.compile(r"^(\d+) (\d+) \* \* \* (\S+) (.+)$")


def _dump_start_minute() -> int:
    bootstrap = (REPO_ROOT / "infra" / "scripts" / "bootstrap_vps.sh").read_text(encoding="utf-8")
    match = re.search(
        r"'?\"?(\d+) (\d+) \* \* \* \$DEPLOY_USER bash \S*backup_postgres\.sh", bootstrap
    )
    assert match, "bootstrap_vps.sh no longer installs the backup cron the way this test reads it"
    return int(match[2]) * 60 + int(match[1])


def _jobs(name: str) -> list[tuple[int, str, str]]:
    jobs: list[tuple[int, str, str]] = []
    for line in (CRON_DIR / name).read_text(encoding="utf-8").splitlines():
        match = _JOB.match(line)
        if match:
            jobs.append((int(match[2]) * 60 + int(match[1]), match[3], match[4]))
    return jobs


def test_the_two_expected_files_exist_and_cron_can_read_them() -> None:
    names = sorted(p.name for p in CRON_DIR.iterdir() if p.is_file())
    assert names == ["hunter-outbox", "hunter-partitions"]
    for name in names:
        body = (CRON_DIR / name).read_text(encoding="utf-8")
        # cron.d ignores a file whose name has a dot and a last line with no newline
        assert "." not in name
        assert body.endswith("\n")
        assert "SHELL=/bin/bash\n" in body
        assert "PATH=/usr/local/bin:/usr/bin:/bin\n" in body


@pytest.mark.parametrize("name", ["hunter-outbox", "hunter-partitions"])
def test_every_job_starts_outside_the_dump_window(name: str) -> None:
    dump = _dump_start_minute()
    for start, _user, command in _jobs(name):
        after_dump_start = (start - dump) % (24 * 60)
        assert after_dump_start >= DUMP_WINDOW_MIN, (
            f"{name}: '{command[:60]}...' starts {after_dump_start} min after the dump"
        )


@pytest.mark.parametrize("name", ["hunter-outbox", "hunter-partitions"])
def test_every_job_is_the_owner_script_through_ops_under_flock(name: str) -> None:
    jobs = _jobs(name)
    assert jobs
    for _start, user, command in jobs:
        assert user == "hunter"
        assert command.startswith("cd /opt/project-hunter && flock -n /tmp/")
        assert "bash infra/vps/compose.sh ops python infra/scripts/" in command
        assert re.search(r">> /opt/backups/[a-z-]+\.log 2>&1$", command)


def test_the_partitions_file_creates_then_prunes_under_one_lock() -> None:
    jobs = _jobs("hunter-partitions")
    scripts: list[str] = [re.findall(r"infra/scripts/(\w+)\.py", cmd)[0] for _s, _u, cmd in jobs]
    assert scripts == ["create_partitions", "prune_partitions"]
    assert jobs[0][0] < jobs[1][0]
    locks: set[str] = {re.findall(r"flock -n (\S+)", cmd)[0] for _s, _u, cmd in jobs}
    assert len(locks) == 1, "create and prune must never run at the same time"
    # the pruner's own dry-run/apply contract: the cron applies, never passes --dry-run
    assert "--dry-run" not in jobs[1][2]


def test_the_outbox_file_keeps_the_contract_two_days() -> None:
    """DATABASE.md §1.3: dispatched rows are kept 2 days since 27/09/2026 — Everton's
    decision (``obsidian/06-DECISIONS/2026-09-27-retencao-de-dados-e-backup.md``, step 4;
    it was 7). Written as an explicit flag, never inherited from the script's default:
    the default stays 7 so a bare manual run deletes less, never more."""
    (job,) = _jobs("hunter-outbox")
    command = job[2]
    assert "prune_outbox_events.py" in command
    assert re.findall(r"--retention-days (\d+)", command) == ["2"]
