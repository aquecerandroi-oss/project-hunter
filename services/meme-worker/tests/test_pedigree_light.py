# pyright: reportPrivateUsage=false
"""EXP-M26 F (01/10/2026): the minute lane reads the two counts of ``PEDIGREE_V1`` and
nothing else, unless a set of that clock asks for the repeat-dumper count.

The instrument defect: with C/L/H active, ``lineage_for`` paid ``_PEDIGREE`` for ~385 mints a
minute — 6-14 s on the VPS, cut at 8 s into ``pedigree_unknown`` on every row, which the
funnel reads as "no proposal by instrument". 99 % of that is ``creator_prior_dump_count`` and
the diagnostic ``creator_prior_dead_count``. Pure part here (the SQL text, which fields come
back, which lane reads what); the Postgres part is ``test_pedigree_light_integration.py``.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from typing import Any

import pytest
from structlog.testing import capture_logs

from hunter_indicators.meme.pedigree import PedigreeFeatures
from hunter_meme_worker import lab_repo_e2b
from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.lab_repo_e2b import lineage_for
from hunter_meme_worker.lab_repo_pedigree import (
    _CREATOR_1H,
    _PEDIGREE,
    _PEDIGREE_COUNTS,
    _SYMBOL_24H,
    pedigree_for,
)
from hunter_meme_worker.proposals import evaluate_gate

from .test_proposals import MINT, T0, _row, _spec

pytestmark = pytest.mark.unit

FULL_SQL_SHA256 = "378a7a4483f18b8e27c8967bde844b8058441f858c556d0cc6bf9789a845b67f"
"""``sha256(str(_PEDIGREE.text))`` (3 635 characters). The 15 s lane — the real desk — must keep
executing exactly this statement. **Changed deliberately on 09/10/2026 (H-037, guardian finding
F1):** the two ``meme_paper_bets`` sources of ``creator_prior_dump_count`` gained
``NOT EXISTS (... prs.params ->> 'clock' = 'copy')``, so a copy bet stamped by the creator watch
is not evidence the desk ever had. Before it: 3 218 characters, sha256 ``6b42935c…ceb74d``. With
no copy set in the database the two statements return the same rows."""


def test_the_full_read_is_byte_identical_to_the_one_the_desk_always_ran() -> None:
    sql = str(_PEDIGREE.text)
    assert len(sql) == 3635
    assert hashlib.sha256(sql.encode()).hexdigest() == FULL_SQL_SHA256


def test_the_light_read_has_the_two_counts_and_no_heavy_source() -> None:
    sql = str(_PEDIGREE_COUNTS.text)
    assert "creator_prior_mints_1h" in sql and "symbol_dup_24h" in sql
    for heavy in (
        "creator_prior_dump_count",
        "creator_prior_dead_count",
        "meme_features_1m",
        "meme_paper_bets",
        ":probe_rule_set_id",
        ":mature_rule_set_ids",
        ":prior_window_s",
    ):
        assert heavy not in sql, heavy


def test_the_light_read_counts_the_two_exactly_as_the_full_one_does() -> None:
    """One definition, two statements: both contain each count's own text."""
    for fragment in (_CREATOR_1H, _SYMBOL_24H):
        assert fragment in str(_PEDIGREE.text)
        assert fragment in str(_PEDIGREE_COUNTS.text)


class _Savepoint:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(self, *exc: object) -> None:
        return None


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def mappings(self) -> _Result:
        return self

    def all(self) -> list[dict[str, Any]]:
        return self._rows


class _Session:
    """Records each statement and its bound parameters; answers the rows it was given."""

    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows
        self.statements: list[tuple[str, dict[str, Any] | None]] = []

    def begin_nested(self) -> Any:
        return _Savepoint()

    async def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Result:
        self.statements.append((str(statement), params))
        return _Result(self.rows)


_COUNTS_ONLY = {"mint": MINT, "creator_prior_mints_1h": 0, "symbol_dup_24h": 2}
_ALL_FOUR = {**_COUNTS_ONLY, "creator_prior_dump_count": 3, "creator_prior_dead_count": 1}


async def test_the_light_read_leaves_the_diagnostics_absent_never_zero() -> None:
    session = _Session([_COUNTS_ONLY])
    result = await pedigree_for(session, [MINT], full=False)  # type: ignore[arg-type]
    assert result == {
        MINT: PedigreeFeatures(
            creator_prior_mints_1h=0,
            symbol_dup_24h=2,
            creator_prior_dump_count=None,
            creator_prior_dead_count=None,
        )
    }
    statement, params = session.statements[-1]
    assert statement == str(_PEDIGREE_COUNTS.text)
    assert params is not None and "probe_rule_set_id" not in params
    assert set(params) == {"mints", "creator_window_s", "symbol_window_s"}


async def test_the_default_read_is_the_full_one_with_every_parameter() -> None:
    session = _Session([_ALL_FOUR])
    result = await pedigree_for(session, [MINT])  # type: ignore[arg-type]
    assert result[MINT] == PedigreeFeatures(0, 2, 3, 1)
    statement, params = session.statements[-1]
    assert statement == str(_PEDIGREE.text)
    assert params is not None
    assert set(params) == {
        "mints",
        "creator_window_s",
        "symbol_window_s",
        "prior_window_s",
        "probe_rule_set_id",
        "pullback_rule_set_id",
        "pullback_control_rule_set_id",
        "mature_rule_set_ids",
    }, "the eight keys of the statement the desk has always run"


class _Recorder:
    def __init__(self) -> None:
        self.calls: list[tuple[Sequence[str], bool]] = []

    async def pedigree_for(
        self, _session: Any, mints: Sequence[str], *, full: bool = True
    ) -> dict[str, Any]:
        self.calls.append((mints, full))
        return {}


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    recorder = _Recorder()
    monkeypatch.setattr(lab_repo_e2b, "pedigree_for", recorder.pedigree_for)
    return recorder


def _mature(**overrides: Any) -> RuleSetSpec:
    """A C/L/H-shaped set: the minute clock, ``pedigree_repeat_dumper: false``."""
    return _spec(exp_ref="EXP-M26", pedigree_repeat_dumper=False, clock="1m", **overrides)


@pytest.mark.parametrize(
    ("specs", "full"),
    [
        ([_mature()], False),
        ([_mature(), _spec(clock="1m")], False),
        ([_spec(clock="1m", pedigree_repeat_dumper=True)], True),
        ([_mature(), _spec(clock="1m", pedigree_repeat_dumper=True)], True),
        ([_spec(clock="15s")], True),
        ([_spec(clock="15s", pedigree_repeat_dumper=True)], True),
        ([_mature(), _spec(clock="15s")], True),
        ([_spec(clock="refused")], True),
    ],
    ids=[
        "1m-no-dumper",
        "1m-two-sets-no-dumper",
        "1m-dumper",
        "1m-one-of-two-dumper",
        "15s-no-dumper-stays-full",
        "15s-dumper",
        "any-15s-forces-full",
        "any-other-clock-falls-back-to-full",
    ],
)
async def test_the_lane_reads_full_unless_every_set_is_1m_without_the_dumper_switch(
    reads: _Recorder, specs: list[RuleSetSpec], full: bool
) -> None:
    await lineage_for(None, [_row()], specs)  # type: ignore[arg-type]
    assert reads.calls == [([MINT], full)]


async def test_a_one_shot_iterator_of_1m_sets_is_still_light(reads: _Recorder) -> None:
    await lineage_for(None, [_row()], iter([_mature()]))  # type: ignore[arg-type]
    assert reads.calls == [([MINT], False)]


@pytest.mark.parametrize(
    ("first", "second"), [(0, 0), (2, 0), (0, 3), (None, 0), (0, None)], ids=str
)
def test_a_1m_set_without_the_dumper_switch_decides_the_same_with_or_without_the_two_fields(
    first: int | None, second: int | None
) -> None:
    """Decision equivalence (EXP-M26 F): for the sets the light read serves, the dump and dead
    counts are only recorded in ``reasons``, never judged — the refusals, the number of drafts
    and every draft field but those two diagnostics are the same."""
    spec = _mature()
    light = PedigreeFeatures(first, second)
    heavy = PedigreeFeatures(first, second, creator_prior_dump_count=3, creator_prior_dead_count=1)
    args: dict[str, Any] = {"now": T0, "ttl_s": 120, "already_open": frozenset()}
    a = evaluate_gate(spec, [_row()], pedigree={MINT: light}, **args)
    b = evaluate_gate(spec, [_row()], pedigree={MINT: heavy}, **args)
    assert dict(a.refusals) == dict(b.refusals) and a.evaluated == b.evaluated
    assert len(a.drafts) == len(b.drafts)
    diagnostics = {"creator_prior_dump_count", "creator_prior_dead_count"}

    def scrub(reasons: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [{k: v for k, v in r.items() if k not in diagnostics} for r in reasons]

    for left, right in zip(a.drafts, b.drafts, strict=True):
        assert (left.status, left.decided_by, left.features_end_time) == (
            right.status,
            right.decided_by,
            right.features_end_time,
        )
        assert scrub(left.reasons) == scrub(right.reasons)


@pytest.mark.parametrize("clock", ["1m", "15s", "refused"])
@pytest.mark.parametrize(
    "others", [[], ["mature"], ["15s"]], ids=["alone", "beside-C", "beside-15s"]
)
async def test_a_set_with_the_dumper_switch_never_receives_the_light_read(
    reads: _Recorder, clock: str, others: list[str]
) -> None:
    lane = [_spec(clock=clock, pedigree_repeat_dumper=True)]
    lane += [_mature() if o == "mature" else _spec(clock=o) for o in others]
    await lineage_for(None, [_row()], lane)  # type: ignore[arg-type]
    assert reads.calls == [([MINT], True)]


async def test_the_1m_lane_says_so_when_a_dumper_set_puts_it_back_on_the_full_read(
    reads: _Recorder,
) -> None:
    """The full read on the minute lane is the 6-14 s one (cut at 8 s): turning the switch on
    for a ``1m`` set must be visible in the logs, by the set's name, every minute it happens."""
    dumper = _spec(clock="1m", pedigree_repeat_dumper=True)
    with capture_logs() as logs:
        await lineage_for(None, [_row()], [_mature(), dumper])  # type: ignore[arg-type]
    (event,) = [e for e in logs if e["event"] == "meme_pedigree_full_read_on_1m_lane"]
    assert event["log_level"] == "warning"
    assert event["sets"] == [dumper.label] and event["mints"] == 1


@pytest.mark.parametrize(
    "lane",
    [[_mature()], [_spec(clock="15s", pedigree_repeat_dumper=True)], [_spec(clock="refused")]],
    ids=["light-1m", "15s-with-dumper", "refused"],
)
async def test_no_other_lane_logs_the_1m_fallback(
    reads: _Recorder, lane: list[RuleSetSpec]
) -> None:
    with capture_logs() as logs:
        await lineage_for(None, [_row()], lane)  # type: ignore[arg-type]
    assert not [e for e in logs if e["event"] == "meme_pedigree_full_read_on_1m_lane"]
