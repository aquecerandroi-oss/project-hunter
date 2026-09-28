"""Test doubles for ``test_close_empty_token_accounts.py`` (labelled fixtures,
never production data): one fake per side effect of the ``--apply`` — kill
switch, in-flight SQL, recognized SQL, chain listing, signer, the T4.77 batch
runner, the session. Never a network call, never a key, never a transaction.
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
for extra in (SCRIPTS_DIR, SCRIPTS_DIR / "tests"):
    if str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

import close_empty_token_accounts as script  # noqa: E402
import close_empty_token_accounts_rules as rules  # noqa: E402
from meme_close_atas_plan import TokenAccountRow  # noqa: E402
from meme_close_atas_send import BatchResult  # noqa: E402
from test_close_empty_token_accounts_rules import (  # noqa: E402
    the_28_09_wallet,
)
from test_meme_close_atas_plan import WALLET  # noqa: E402

from hunter_core.domain.enums import KillSwitchState  # noqa: E402

OTHER = "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm"
NOW = datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


class FakeSession:
    """Models PostgreSQL's aborted transaction: the INSERT attempts numbered in
    ``fail_at`` (0-based) raise, and from then on every statement and commit
    raises ``InFailedSQLTransaction`` until ``rollback()`` — what asyncpg does
    after an error inside an open transaction (reproduced on PG16 in review)."""

    def __init__(self, log: list[str], *, fail_at: frozenset[int] = frozenset()) -> None:
        self.log = log
        self.audits: list[dict[str, Any]] = []
        self.fail_at = fail_at
        self.attempts = 0
        self.aborted = False
        self.commits = self.rollbacks = 0

    async def execute(self, statement: Any, parameters: Any = None, /) -> Any:
        assert str(statement).startswith("INSERT INTO audit_logs"), str(statement)
        if self.aborted:
            raise RuntimeError("InFailedSQLTransaction: current transaction is aborted")
        attempt, self.attempts = self.attempts, self.attempts + 1
        if attempt in self.fail_at:
            self.aborted = True
            raise ConnectionError("insert failed")
        row = {
            "action": parameters["action"],
            "after": json.loads(parameters["after"]),
            "metadata": json.loads(parameters["metadata"]),
        }
        self.audits.append(row)
        self.log.append(f"audit:{row['action'].rsplit('.', 1)[1]}")

    async def commit(self) -> None:
        if self.aborted:
            raise RuntimeError("InFailedSQLTransaction: current transaction is aborted")
        self.commits += 1
        if self.log and self.log[-1].startswith("audit:"):
            self.log.append("commit")  # an audit row is durable only from here

    async def rollback(self) -> None:
        self.rollbacks += 1
        self.aborted = False


class FakeSigner:
    def __init__(self, pubkey: str = WALLET) -> None:
        self.pubkey = pubkey

    def sign(self, message: bytes) -> bytes:
        return bytes(64)


class Batches:
    """The T4.77 runner, replaced: records each batch, answers from ``results``."""

    def __init__(self, log: list[str], results: list[str] | None = None) -> None:
        self.log, self.results = log, list(results or [])
        self.seen: list[tuple[TokenAccountRow, ...]] = []

    async def __call__(self, session: Any, rpc: Any, signer: Any, **kw: Any) -> BatchResult:
        batch: tuple[TokenAccountRow, ...] = kw["batch"]
        self.seen.append(batch)
        self.log.append(f"run_batch:{len(batch)}")
        assert signer.pubkey == WALLET and "[run " in kw["reason"]
        status = self.results.pop(0) if self.results else "confirmed"
        expected = sum(row.lamports for row in batch)
        recovered = {"confirmed": expected - 15_000, "short": expected // 2}.get(status, 0)
        return BatchResult(
            "confirmed" if status == "short" else status,
            None if status == "refused" else f"sig{len(self.seen)}",
            len(batch) if recovered else 0,
            recovered,
            expected,
        )


class Rig:
    def __init__(self, tmp_path: Path, **over: Any) -> None:
        self.log: list[str] = []
        (tmp_path / "obsidian").mkdir(exist_ok=True)
        (tmp_path / "obsidian" / "n.md").write_text("close_empty_token_accounts", "utf-8")
        self.session = FakeSession(self.log, fail_at=frozenset(over.pop("fail_at", ())))
        self.batches = Batches(self.log, over.pop("results", None))
        self.listings: list[Any] = list(over.pop("listings", [the_28_09_wallet()]))
        self.in_flight: list[dict[str, int]] = list(over.pop("in_flight", [{"meme": 0, "spot": 0}]))
        self.states: list[Any] = list(over.pop("states", [KillSwitchState.ACTIVE]))
        self.signers = 0
        self.signer_pubkey = over.pop("signer_pubkey", WALLET)
        self.recognized = over.pop("recognized", frozenset())
        self.deps = script.Deps(
            load_signer=self._signer,
            kill_state=self._kill,
            in_flight=self._in_flight,
            recognized=self._recognized,
            list_accounts=self._list,
            run_batch=self.batches,
            now=lambda: NOW,
            repo_root=tmp_path,
            open_positions=self._open,
            balance=self._balance,
        )
        self.open = over.pop("open", {"meme": 0, "spot": 1})
        self.lamports: int | Exception = over.pop("lamports", 384_500_000)
        self.argv = ["--user", WALLET, *over.pop("argv", ["--apply", "--note", "obsidian/n.md"])]

    async def _open(self, session: Any) -> dict[str, int]:
        return self.open

    def _balance(self, rpc: Any, wallet: str) -> int:
        if isinstance(self.lamports, Exception):
            raise self.lamports
        return self.lamports

    def _signer(self) -> FakeSigner:
        self.signers += 1
        self.log.append("load_signer")
        return FakeSigner(self.signer_pubkey)

    async def _kill(self, session: Any, redis: Any) -> KillSwitchState:
        state = self.states.pop(0) if len(self.states) > 1 else self.states[0]
        if isinstance(state, Exception):
            raise state
        return state

    async def _in_flight(self, session: Any) -> dict[str, int]:
        return self.in_flight.pop(0) if len(self.in_flight) > 1 else self.in_flight[0]

    async def _recognized(self, session: Any, *, since: datetime) -> frozenset[str]:
        assert since == datetime(2026, 9, 28, 11, 59, tzinfo=UTC)  # read time − 60 s
        if isinstance(self.recognized, Exception):
            raise self.recognized
        return self.recognized

    def _list(self, rpc: Any, wallet: str) -> Any:
        listing = self.listings.pop(0) if len(self.listings) > 1 else self.listings[0]
        if isinstance(listing, rules.Refused):
            raise listing
        return listing

    async def apply(self) -> int:
        args = script.parse_args(self.argv)
        return await script.apply_with(
            args, session=self.session, redis=None, rpc=None, deps=self.deps
        )

    def actions(self) -> list[str]:
        return [a["action"].rsplit(".", 1)[1] for a in self.session.audits]

    def run_row(self) -> dict[str, Any]:
        [row] = [a for a in self.session.audits if a["action"] == rules.ACTION_RUN]
        return row["after"]
