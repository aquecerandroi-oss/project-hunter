"""R1 — replay eight exit policies over the Lab's frozen entries (EXP-0004).

    uv run python infra/scripts/replay_exits.py \
        --database-url postgresql+asyncpg://... \
        --versions momentum,volume_anomaly \
        --as-of 2026-09-06T20:00:00Z \
        --out .claude/state/r1-proof.md

Research only, and read only: the transaction is opened ``READ ONLY``, so no
table of the Lab can be written even by accident, no episode slot is taken or
re-armed, and nothing is activated. The exit rules are **not** reimplemented
here — every arm is folded by ``hunter_strategy_worker.walker.walk`` and closed
by ``hunter_strategy_worker.settle.settle``.

The run writes two files, byte-identical for the same database and the same
``--as-of``: the Markdown named by ``--out`` and the canonical JSON beside it
(same name, ``.json``).

``--reproduce-only`` stops after step 1 (does the replay land on the outcome the
Lab recorded?), which is the gate: without it the contrasts have no floor.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import SecretStr

from hunter_core.db.session import create_engine, create_session_factory
from hunter_core.logging import get_logger
from hunter_core.settings import Settings
from hunter_core.strategies.canonical import canonical_json
from hunter_indicators.replay.policies import BASE, POLICIES, policy
from hunter_strategy_worker.replay.contrast import coverage, run_contrasts
from hunter_strategy_worker.replay.engine import load_series, replay_case
from hunter_strategy_worker.replay.load import (
    input_digest,
    load_cases,
    load_manifest,
    read_only_session,
)
from hunter_strategy_worker.replay.render import render_markdown
from hunter_strategy_worker.replay.report import build_document, render_json
from hunter_strategy_worker.replay.reproduce import audit_case, gate, summarise

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from hunter_strategy_worker.replay.engine import ArmOutcome
    from hunter_strategy_worker.replay.load import ReplayCase

logger = get_logger(__name__)

DEFAULT_SEED = 20260906
DEFAULT_RESAMPLES = 10_000


def _as_of(raw: str | None) -> datetime:
    """The declared cut. A naive timestamp is refused, not localised.

    ``astimezone`` on a naive value would read it in the machine's timezone, so
    the same argument would select a different cut on a different box (Astra,
    R1 diff review).
    """
    if raw is None:
        return datetime.now(tz=UTC).replace(microsecond=0)
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise SystemExit("--as-of needs a timezone (e.g. 2026-09-06T20:30:00Z)")
    return parsed.astimezone(UTC)


async def _replay_all(
    session: AsyncSession,
    cases: list[ReplayCase],
    *,
    policy_keys: list[str],
    as_of: datetime,
) -> tuple[dict[Any, dict[str, ArmOutcome]], str]:
    """Replay every requested policy over every case, one candle load per case."""
    policies = [policy(key) for key in policy_keys]
    outcomes: dict[Any, dict[str, ArmOutcome]] = {}
    digest = hashlib.sha256()
    for index, case in enumerate(cases, start=1):
        series = await load_series(session, case, as_of=as_of)
        # The candles are an input too: a backfill can change a contrast without
        # changing a single ``signal_outcomes`` row (Astra, R1 fixes review).
        digest.update(
            canonical_json([[b.open_time, b.open, b.high, b.low, b.close] for b in series.bars])
        )
        outcomes[case.signal_id] = dict(
            await replay_case(session, case, policies=policies, series=series)
        )
        if index % 25 == 0:
            logger.info("replay_progress", done=index, total=len(cases))
    return outcomes, digest.hexdigest()


def _population(cases: list[ReplayCase]) -> dict[str, dict[str, int]]:
    counts: dict[str, Counter[str]] = {}
    for case in cases:
        counts.setdefault(case.version.label, Counter())[case.stored.tracking_state.value] += 1
    return {label: dict(counter) for label, counter in counts.items()}


def _distinct_days(outcomes: dict[Any, dict[str, ArmOutcome]]) -> int:
    days: set[Any] = set()
    for arms in outcomes.values():
        base = arms.get(BASE)
        if base is not None and base.entry_ts is not None:
            days.add(base.entry_ts.date())
    return len(days)


async def _collect(args: argparse.Namespace) -> dict[str, Any]:
    """Everything that touches the database and the CPU; no file IO (ASYNC240)."""
    as_of = _as_of(args.as_of)
    keys = [key.strip() for key in args.versions.split(",") if key.strip()]
    policy_keys = (
        [BASE, *[k.strip() for k in args.policies.split(",") if k.strip() and k.strip() != BASE]]
        if args.policies
        else list(POLICIES)
    )
    if args.reproduce_only:
        policy_keys = [BASE]
    settings = Settings(database_url=SecretStr(args.database_url))
    engine = create_engine(settings)
    try:
        factory = create_session_factory(engine)
        async with read_only_session(factory) as session:
            versions = await load_manifest(session, keys=keys)
            cases = await load_cases(session, versions=versions, as_of=as_of)
            logger.info("replay_loaded", versions=len(versions), cases=len(cases))
            outcomes, series_digest = await _replay_all(
                session, cases, policy_keys=policy_keys, as_of=as_of
            )
    finally:
        await engine.dispose()

    audits = summarise(
        [(case.version.label, *audit_case(case, outcomes[case.signal_id][BASE])) for case in cases]
    )
    coverages = [
        coverage(key, [arms[key] for arms in outcomes.values() if key in arms])
        for key in policy_keys
    ]
    step_one = gate(audits, threshold=args.gate_rate)
    contrasts = (
        run_contrasts(outcomes, seed=args.seed, resamples=args.resamples)
        if step_one["passed"] and not args.reproduce_only
        else []
    )
    if not step_one["passed"]:
        logger.warning("replay_gate_failed", **{k: str(v) for k, v in step_one.items()})
    document = build_document(
        as_of=as_of,
        seed=args.seed,
        resamples=args.resamples,
        versions=versions,
        population=_population(cases),
        audits=audits,
        coverages=coverages,
        contrasts=contrasts,
        policy_keys=policy_keys,
        distinct_days=_distinct_days(outcomes),
        gate=step_one,
        input_digest=input_digest(cases),
        series_digest=series_digest,
    )
    logger.info(
        "replay_collected",
        cases=len(cases),
        comparable=sum(a.comparable for a in audits),
        reproduced=sum(a.reproduced for a in audits),
    )
    return document


def _write(document: dict[str, Any], destination: str) -> None:
    """File IO lives outside the event loop (ASYNC240)."""
    out = Path(destination)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_markdown(document), encoding="utf-8", newline="\n")
    out.with_suffix(".json").write_bytes(render_json(document))
    logger.info("replay_written", out=str(out), json=str(out.with_suffix(".json")))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True, help="asyncpg URL, read only")
    parser.add_argument(
        "--versions",
        default="momentum,volume_anomaly",
        help="comma-separated strategy keys (every activated version of each is replayed)",
    )
    parser.add_argument("--out", default=".claude/state/r1-proof.md")
    parser.add_argument("--policies", default=None, help="subset to run; the base is always in")
    parser.add_argument("--reproduce-only", action="store_true", help="stop after step 1")
    parser.add_argument("--as-of", default=None, help="UTC cut; defaults to now")
    parser.add_argument(
        "--gate-rate",
        type=float,
        default=0.99,
        help="minimum trajectory reproduction before any contrast is computed",
    )
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--resamples", type=int, default=DEFAULT_RESAMPLES)
    args = parser.parse_args()
    _write(asyncio.run(_collect(args)), args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
