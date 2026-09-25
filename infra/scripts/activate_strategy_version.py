"""Activate a Shadow Lab ``strategy_version`` — audited, and refusing on doubt.

    uv run python infra/scripts/activate_strategy_version.py momentum v1 \
        --changelog "S2 operational proof" [--dry-run]
    uv run python infra/scripts/activate_strategy_version.py momentum v1 --supersede \
        --changelog "code_ref per version (MUST-FIX 1)"
    uv run python infra/scripts/activate_strategy_version.py momentum v1 --paper-line \
        --changelog "D10: the paper coorte" [--dry-run]
    uv run python infra/scripts/activate_strategy_version.py breakout v1 --deprecate \
        --changelog "K1: 0 decisions" [--successor v2] [--dry-run]

``--deprecate`` (T3.39) sets ``status = 'deprecated'`` on an ``active`` row —
the audited path for a version whose successor is a *parameter* variant
(``derive_variant.py``), or that has no successor at all: ``--supersede``
refuses both, on purpose, because it exists for a *code* change. ``status`` is
the one field the freeze trigger leaves mutable, so nothing frozen moves.
Refuses a ``purpose = 'live'`` row outright, and a ``purpose = 'paper'`` row
unless ``--force-paper`` is given *and* it carries no open ``positions`` or
``shadow_episodes`` slot (:mod:`hunter_strategy_worker.deprecate`).

The first activation is irreversible by design (docs/DATABASE.md §16.1): the
``0002_shadow_lab`` trigger freezes ``code_ref``, ``parameters_schema``,
``default_parameters``, ``params_format`` and ``activated_at`` for good. So this
script writes the definitive values **in the same statement** that sets
``activated_at``, and refuses — loudly, with a non-zero exit — if any of the
prerequisites is not met:

- ``0002_shadow_lab`` applied (``shadow_episodes``, ``shadow_outbox``,
  ``signal_outcomes.tracking_state``);
- this build carries the code for ``(key, version)`` in
  ``hunter_core.strategies.registry``;
- ``default_parameters`` validate against the version's ``parameters_schema``;
- the per-version ``code_ref`` digest can be computed
  (:mod:`hunter_strategy_worker.code_ref`, one resolution, no second answer).

``--supersede`` is the only way to move an *already frozen* version onto a new
digest: it retires the old row (``deprecated`` + a ``changelog`` saying why) and
creates ``version + 1`` carrying the **frozen row's own** ``parameters_schema``,
``default_parameters``, ``params_format`` and ``purpose``, with the new
``code_ref``, both in one transaction. Copying from the row rather than
recomputing from code is the point: the successor continues the frozen
experiment, not today's code — a paper line's successor stays ``purpose =
'paper'``, never the schema default. Retiring the origin carries the same two
structural refusals as ``--deprecate`` (T3.39b review, ALTA-2): ``purpose =
'live'`` is never touched, and ``purpose = 'paper'`` needs ``--force-paper``
*and* a clean ``positions``/``shadow_episodes`` check.

``--paper-line`` (T3.15, D10) derives the coorte that may reach the paper wallet
from a **frozen** ``research_only`` version: a *new* draft row, next free
``v<n>``, with that row's own content byte for byte and ``purpose = 'paper'``;
the source is untouched and nothing is activated (``paper_line.py``). A row that
already carries **its own content** (a paper line, or a research variant of
``infra/scripts/derive_variant.py``, T3.26) is activated by
:mod:`hunter_strategy_worker.activate_derived` — only ``status``, ``activated_at``
and ``changelog`` move; the plain research path would rewrite its parameters
from *today's* code and freeze the wrong experiment (review T3.15-risk).

Recognising such a row has **two** layers, because the first one can be erased:
``carries_own_content`` reads ``purpose`` and the deriving tool's phrase in the
``changelog`` (a column no trigger freezes), and
``refuse_rewriting_own_content`` refuses structurally — a draft whose
``default_parameters`` are non-empty and are not this code's own set is never
rewritten, whatever its changelog says (review T3.26-risk, A1).

Every run writes a ``system_events`` row — activation, refusal or an unexpected
failure alike (T3.15c): an experiment whose start nobody can date is not one.

Connects with ``DATABASE_URL_MIGRATIONS`` (direct, never the pooler), like
``infra/scripts/seed.py``. Shared checks in :mod:`hunter_strategy_worker.activation_db`;
plain activation, ``--supersede``, ``--paper-line``, derived activation and
``--deprecate`` each live in their own module (``activate``/``supersede``/
``paper_line``/``activate_derived``/``deprecate``) — the 350-line budget split
them out one at a time as each mode was added.

Plain activation and ``--paper-line`` also need ``--note`` (T4.93, "Obsidian
primeiro") whenever they are about to write — not ``--dry-run``, not
``--deprecate``/``--supersede`` (a retirement, not "using" the strategy): a
Markdown file under ``obsidian/`` mentioning the strategy's ``key`` and
``version`` together, gated inside ``activate``/``paper_line`` right before
their one write (never before an earlier refusal or a no-op, e.g.
re-activating an already-active version). The note's path and hashes are
written into the same ``system_events`` row each already leaves — no schema
change needed (:func:`hunter_strategy_worker.activation_db.require_note`).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

import obsidian_note_gate
from sqlalchemy.ext.asyncio import create_async_engine

from hunter_strategy_worker.activate import activate
from hunter_strategy_worker.activation_db import (
    Refused,
    migration_url,
    record_failure,
)
from hunter_strategy_worker.deprecate import deprecate
from hunter_strategy_worker.paper_line import paper_line
from hunter_strategy_worker.supersede import supersede

__all__ = ["Refused", "activate", "deprecate", "main", "paper_line", "supersede"]


async def _run(args: argparse.Namespace) -> int:
    engine = create_async_engine(migration_url(), connect_args={"statement_cache_size": 0})
    try:
        try:
            async with engine.connect() as conn, conn.begin():
                if getattr(args, "deprecate", False):
                    message = await deprecate(
                        conn,
                        args.strategy,
                        args.version,
                        args.changelog,
                        dry_run=args.dry_run,
                        successor=getattr(args, "successor", None),
                        force_paper=getattr(args, "force_paper", False),
                    )
                elif getattr(args, "supersede", False):
                    message = await supersede(
                        conn,
                        args.strategy,
                        args.version,
                        args.changelog,
                        dry_run=args.dry_run,
                        force_paper=getattr(args, "force_paper", False),
                    )
                else:
                    if args.dry_run:
                        hint = obsidian_note_gate.describe_required_note(
                            [[f"{args.strategy} {args.version}", f"{args.strategy}/{args.version}"]]
                        )
                        print(hint, file=sys.stderr)
                    action = paper_line if args.paper_line else activate
                    message = await action(
                        conn,
                        args.strategy,
                        args.version,
                        args.changelog,
                        dry_run=args.dry_run,
                        note=getattr(args, "note", None),
                    )
        except Refused as refusal:
            await record_failure(
                engine, "warning", "strategy_version_activation_refused", str(refusal)
            )
            print(f"REFUSED: {refusal}", file=sys.stderr)
            return 1
        except Exception as exc:
            # Every run leaves a system_events row, not only a named refusal
            # (T3.15c, security review T3.15 MEDIUM 5).
            print(f"ERROR: {exc}", file=sys.stderr)
            await record_failure(engine, "error", "strategy_version_activation_error", str(exc))
            raise SystemExit(2) from exc
        print(message)
    finally:
        await engine.dispose()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("strategy", help="strategies.key, e.g. momentum")
    parser.add_argument("version", help="strategy_versions.version, e.g. v1")
    parser.add_argument("--changelog", required=True, help="why this version is being activated")
    parser.add_argument("--dry-run", action="store_true", help="run every check, write nothing")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--supersede",
        action="store_true",
        help="retire this frozen version and activate version+1 with the current code_ref",
    )
    mode.add_argument(
        "--paper-line",
        action="store_true",
        help="derive a draft purpose=paper line (next free v<n>) from this frozen research "
        "version; activates nothing (T3.15, D10)",
    )
    mode.add_argument(
        "--deprecate",
        action="store_true",
        help="set status=deprecated on this active version (T3.39); refuses purpose=live, and "
        "refuses purpose=paper without --force-paper and a clean positions/shadow_episodes check",
    )
    parser.add_argument(
        "--successor",
        default=None,
        help="--deprecate only: the version (v<n>) that replaces this one, named in the audit "
        "trail; must already exist",
    )
    parser.add_argument(
        "--force-paper",
        action="store_true",
        help="--deprecate/--supersede only: required to retire a purpose=paper version",
    )
    parser.add_argument(
        "--note",
        default=None,
        metavar="PATH",
        help="plain activation/--paper-line only, when writing: a .md under obsidian/ "
        "mentioning 'STRATEGY VERSION' or 'STRATEGY/VERSION' together (T4.93, Obsidian primeiro)",
    )
    args = parser.parse_args()
    if args.successor is not None and not args.deprecate:
        parser.error("--successor requires --deprecate")
    if args.force_paper and not (args.deprecate or args.supersede):
        parser.error("--force-paper requires --deprecate or --supersede")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
