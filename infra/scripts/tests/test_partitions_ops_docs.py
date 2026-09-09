"""T3.15e (HIGH-B): the daily partitions/prune runbook must invoke `ops`, never `api`.

`create_partitions.py`/`prune_partitions.py` connect with `DATABASE_URL_MIGRATIONS`
(the schema owner's DSN, `migration_url()`); since T3.15d that DSN only lives in
`migrate`'s and `ops`'s environment (`x-owner-env`/`x-prod-owner-env` in
`infra/docker/docker-compose.yml`/`infra/vps/docker-compose.prod.yml`) — `api`
lost it. A doc (or cron template) that still tells the operator to run either
script through `HUNTER_COMMAND=partitions api`/`... api python
infra/scripts/{create,prune}_partitions.py` would fail every time it runs
(`SystemExit("DATABASE_URL_MIGRATIONS is not configured")`), including at
04:07 in a cron nobody is watching.

No Docker, no network — reads the actual docs/scripts committed in this
worktree. Run: ``uv run pytest infra/scripts/tests/test_partitions_ops_docs.py -q``
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]

# Any shell command (continuation lines joined on a trailing `\`) that both
# selects the partitions command and names the `api` service as the
# `docker compose run`/`up` target — `api` as a bare word immediately
# followed by end of command, a shell operator, redirection or a comment,
# never as part of a longer path/word (`apibase`, `.../api/...`).
_BROKEN_ON_API = re.compile(
    r"HUNTER_COMMAND=partitions\b.*?\bapi\b(?=\s*($|[|&;>#]))", re.MULTILINE
)
# The scripts themselves need the owner DSN regardless of how they are
# invoked — a doc that ever runs them via a bare `api` container (without
# HUNTER_COMMAND) is exactly as broken.
_SCRIPT_ON_API = re.compile(
    r"(run --rm[^\n]*\bapi\b|exec (-\S+ )*(api|hunter-api-1)\b)[^\n]*"
    r"python infra/scripts/(create|prune)_partitions\.py"
)


def _joined_lines(text: str) -> str:
    """Collapse ``... \\\n  ...`` shell line continuations into one line.

    Docs wrap long `docker compose run` invocations across lines with a
    trailing backslash; the forbidden pattern (`HUNTER_COMMAND=partitions`
    ... `api`) can straddle that break, exactly as it used to.
    """
    return re.sub(r"\\\s*\n\s*", " ", text)


DOCS_TO_CHECK = [
    REPO_ROOT / "infra" / "vps" / "README.md",
    REPO_ROOT / "docs" / "DEPLOYMENT.md",
]


@pytest.mark.parametrize("doc_path", DOCS_TO_CHECK, ids=lambda p: p.name)
def test_partitions_cron_never_targets_the_api_service(doc_path: Path) -> None:
    text = _joined_lines(doc_path.read_text(encoding="utf-8"))
    broken = _BROKEN_ON_API.findall(text)
    assert not broken, (
        f"{doc_path} still tells the operator to run the partitions job via "
        "HUNTER_COMMAND=partitions on the `api` service, which has not carried "
        "DATABASE_URL_MIGRATIONS since T3.15d and would fail every run "
        "(SystemExit: DATABASE_URL_MIGRATIONS is not configured). Use the `ops` "
        "service instead: `bash infra/vps/compose.sh run --rm ops python "
        "infra/scripts/create_partitions.py` (docs/DEPLOYMENT.md §3.4)."
    )


@pytest.mark.parametrize("doc_path", DOCS_TO_CHECK, ids=lambda p: p.name)
def test_create_and_prune_partitions_never_run_on_the_api_service(doc_path: Path) -> None:
    text = _joined_lines(doc_path.read_text(encoding="utf-8"))
    broken = _SCRIPT_ON_API.findall(text)
    assert not broken, (
        f"{doc_path} runs create_partitions.py/prune_partitions.py through the "
        "`api` service — both need DATABASE_URL_MIGRATIONS (migration_url()), "
        "which `api` does not carry since T3.15d. Use `ops` instead."
    )


def test_no_dedicated_cron_template_file_exists_uncovered() -> None:
    """Guards against a future ``infra/vps/*.cron``/crontab template file that
    this test would not otherwise scan — today the only schedule is the
    inline ``printf`` block in ``infra/vps/README.md``, already covered above.
    If a dedicated template file appears, it must be added to ``DOCS_TO_CHECK``.
    """
    vps_dir = REPO_ROOT / "infra" / "vps"
    candidates = [
        p
        for p in vps_dir.iterdir()
        if p.is_file() and ("cron" in p.name.lower()) and p.suffix != ".md"
    ]
    assert candidates == [], (
        f"found cron template file(s) not covered by this lint: {candidates} — "
        "add them to DOCS_TO_CHECK in this test."
    )


@pytest.mark.parametrize(
    "line",
    [
        "docker exec hunter-api-1 python infra/scripts/create_partitions.py",
        "docker exec -it hunter-api-1 python infra/scripts/prune_partitions.py --yes",
        "bash infra/vps/compose.sh exec api python infra/scripts/create_partitions.py",
        "bash infra/vps/compose.sh run --rm api python infra/scripts/create_partitions.py",
    ],
)
def test_the_lint_catches_every_spelling_of_running_the_scripts_on_api(line: str) -> None:
    """The security review of T3.15e showed the first regex only knew the
    ``run --rm ... api`` form; ``docker exec hunter-api-1 ...`` (the spelling
    the docs used before this task) slipped through."""
    assert _SCRIPT_ON_API.search(line), line


def test_the_lint_leaves_the_ops_form_alone() -> None:
    assert not _SCRIPT_ON_API.search(
        "bash infra/vps/compose.sh run --rm ops python infra/scripts/create_partitions.py"
    )
