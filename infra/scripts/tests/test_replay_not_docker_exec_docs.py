"""T3.80: no doc may tell the operator to run a replay via `docker exec` into
the live strategy-worker's own container.

T3.76 did exactly that (`docker exec hunter-strategy-worker-1 python -m
hunter_strategy_worker.replay.run ...`) and the live lane's own decision lag
climbed from a 26 s to a 90 s median (p95 171 s) for the duration, sharing the
container's CPU and DB pool with the process that has to stay instant. The
replay lane now runs in its own compose service (`replay-worker`, `compose.sh
replay ...`), and `replay/run.py`'s own guard refuses outright if
`HUNTER_ROLE=strategy` is ever set on it — but a doc (or a runbook someone
pastes into a terminal at 04:07) that still spells the old command would
recreate the exact interference this task closes, guard or no guard.

Same shape as `infra/scripts/tests/test_partitions_ops_docs.py`: reads the
actual docs committed in this worktree, no Docker, no network.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[3]

# `docker exec` (any flags) into any spelling of the live strategy-worker
# container, followed anywhere later on the same logical line by a replay
# invocation -- `python -m hunter_strategy_worker.replay.run`, the module the
# brief and this task both name.
_REPLAY_VIA_DOCKER_EXEC = re.compile(
    r"docker exec (-\S+ )*\S*strategy-worker\S*[^\n]*"
    r"hunter_strategy_worker\.replay\.run"
)

DOCS_TO_CHECK = [
    REPO_ROOT / "docs" / "DEPLOYMENT.md",
    REPO_ROOT / "docs" / "ACTIVATION.md",
    REPO_ROOT / "docs" / "PIPELINE.md",
    REPO_ROOT / "infra" / "vps" / "README.md",
]


def _joined_lines(text: str) -> str:
    """Collapse ``... \\\n  ...`` shell line continuations, exactly like
    ``test_partitions_ops_docs.py`` — a long ``docker exec`` invocation can
    straddle a line break in a doc's fenced code block."""
    return re.sub(r"\\\s*\n\s*", " ", text)


@pytest.mark.parametrize("doc_path", DOCS_TO_CHECK, ids=lambda p: p.name)
def test_no_doc_runs_a_replay_via_docker_exec_into_the_live_worker(doc_path: Path) -> None:
    if not doc_path.exists():
        pytest.skip(f"{doc_path} does not exist")
    text = _joined_lines(doc_path.read_text(encoding="utf-8"))
    broken = _REPLAY_VIA_DOCKER_EXEC.findall(text)
    assert not broken, (
        f"{doc_path} still tells the operator to run a replay via `docker exec` "
        "into the live strategy-worker's own container (T3.76: measured decision "
        "lag climbing from a 26 s to a 90 s median while it ran there). Use "
        "`bash infra/vps/compose.sh replay python -m "
        "hunter_strategy_worker.replay.run ...` instead (docs/DEPLOYMENT.md §5.2)."
    )


def test_the_lint_catches_the_exact_command_t376_ran() -> None:
    line = (
        'ssh hunter-vps "docker exec hunter-strategy-worker-1 python -m '
        'hunter_strategy_worker.replay.run --drain-queue"'
    )
    assert _REPLAY_VIA_DOCKER_EXEC.search(line), line


def test_the_lint_leaves_the_replay_worker_form_alone() -> None:
    line = (
        "bash infra/vps/compose.sh replay python -m hunter_strategy_worker.replay.run --drain-queue"
    )
    assert not _REPLAY_VIA_DOCKER_EXEC.search(line)


def test_the_lint_leaves_unrelated_docker_exec_commands_alone() -> None:
    """`docker exec` into the strategy-worker for something that is not a
    replay (e.g. checking the deployed code, ACTIVATION.md's existing use)
    must not trip this lint."""
    line = 'ssh hunter-vps "docker exec hunter-strategy-worker-1 python -c \\"import x\\""'
    assert not _REPLAY_VIA_DOCKER_EXEC.search(line)
