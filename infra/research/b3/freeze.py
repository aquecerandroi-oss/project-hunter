"""What the WIN-family freeze pins, and the checks the later phases run before any outcome.

The freeze pins four things: the population (which carries the sha256 of both exports), the
plans of every variant, the **code** that decides and simulates (rules, harness, statistics,
and the frozen pre-registration itself) and the **configuration** (replicates, seed, MRE,
thresholds, costs, library versions). ``primary`` and ``holdout`` recompute all four and
refuse to simulate anything if one differs, and refuse before computing if their own output
already exists.
"""

from __future__ import annotations

import hashlib
import platform
from collections.abc import Sequence
from pathlib import Path

import numpy as np

from infra.research.b3.evaluate import MAX_CENSOR_SHARE, MAX_DATA_SHARE, MIN_MONTHS, MRE_BP
from infra.research.b3.simulate import TOLERANCE, WIN_COSTS
from infra.research.b3.stats_b3 import CI_TAIL, SEED
from infra.research.b3.variants import MIN_TRADES

ROOT = Path(__file__).resolve().parents[3]
FROZEN_SOURCES = (
    ".claude/state/h039-041/prereg_frozen.md",
    ".claude/state/h039-041/emenda_1.md",
    "packages/indicators/hunter_indicators/b3/bars.py",
    "packages/indicators/hunter_indicators/b3/calendar_2026.py",
    "packages/indicators/hunter_indicators/b3/calendar_history.py",
    "packages/indicators/hunter_indicators/b3/contract.py",
    "packages/indicators/hunter_indicators/b3/contraction.py",
    "packages/indicators/hunter_indicators/b3/intraday_plan.py",
    "packages/indicators/hunter_indicators/b3/orb.py",
    "packages/indicators/hunter_indicators/b3/reversal15.py",
    "infra/research/stats.py",
    "infra/research/stats_core.py",
    "infra/research/b3/evaluate.py",
    "infra/research/b3/freeze.py",
    "infra/research/b3/mt5_csv.py",
    "infra/research/b3/report_b3.py",
    "infra/research/b3/run_family.py",
    "infra/research/b3/sessions.py",
    "infra/research/b3/simulate.py",
    "infra/research/b3/stats_b3.py",
    "infra/research/b3/variants.py",
)


class FreezeViolation(RuntimeError):
    """A later phase found data, plans, code or configuration different from the freeze."""


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def source_lines(root: Path = ROOT, sources: Sequence[str] = FROZEN_SOURCES) -> list[str]:
    """``sha256  path`` per pinned file (line endings normalised, so a checkout cannot move it)."""
    out: list[str] = []
    for rel in sources:
        data = (root / rel).read_bytes().replace(b"\r\n", b"\n")
        out.append(f"{hashlib.sha256(data).hexdigest()}  {rel}")
    return out


def config_text(reps: int, root: Path = ROOT) -> str:
    lines = [
        f"reps={reps} seed={SEED} ci_tail={CI_TAIL!r} mre_bp={MRE_BP}",
        f"min_months={MIN_MONTHS} max_data_share={MAX_DATA_SHARE} max_censor_share={MAX_CENSOR_SHARE}",
        f"min_trades={MIN_TRADES}",
        f"costs={WIN_COSTS} tolerance={TOLERANCE}",
        f"python={platform.python_version()} numpy={np.__version__}",
        *source_lines(root),
    ]
    return "\n".join(lines) + "\n"


def write_new(path: Path, text: str) -> None:
    if path.exists():
        raise FreezeViolation(f"{path} already exists; a phase never overwrites its output")
    path.write_text(text, encoding="utf-8", newline="\n")


def refuse_existing(path: Path) -> None:
    if path.exists():
        raise FreezeViolation(f"{path} already exists; this phase already ran once")


def check_frozen(out: Path, current: dict[str, str]) -> None:
    """Every frozen file must exist and match what was recomputed now, byte for byte."""
    for name, text in current.items():
        frozen = (out / name).read_text(encoding="utf-8")
        if sha(frozen) != sha(text):
            raise FreezeViolation(
                f"{name} differs from the freeze: data, code or configuration changed"
            )
