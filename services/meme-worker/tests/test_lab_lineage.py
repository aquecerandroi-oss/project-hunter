# pyright: reportPrivateUsage=false
"""``lab_repo_e2b.lineage_for`` reads nothing for a lane no set judges.

The 24/09/2026 incident: every active set was on the ``15s`` clock (or
``refused``), so the minute lane called ``lineage_for`` with no spec and paid
the pedigree read of ~320 mints — 14 s measured on the VPS, cut at 8 s by its
own statement timeout (``meme_pedigree_read_failed``) — for a result
``_gate_step`` hands to no gate. The reads are replaced by recorders here: the
point is *whether* they run, not what they return.
"""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import datetime
from typing import Any

import pytest

from hunter_indicators.meme.pedigree import PedigreeFeatures
from hunter_meme_worker import lab_repo_e2b
from hunter_meme_worker.lab_models import RuleSetSpec
from hunter_meme_worker.lab_repo_e2b import lineage_for

from .test_proposals import MINT, _row, _spec

pytestmark = pytest.mark.unit

_PEDIGREE = {MINT: PedigreeFeatures(creator_prior_mints_1h=0, symbol_dup_24h=0)}


class _Recorder:
    def __init__(self) -> None:
        self.pedigree_calls: list[Sequence[str]] = []
        self.e2b_calls: list[Sequence[tuple[str, datetime]]] = []

    async def pedigree_for(self, _session: Any, mints: Sequence[str]) -> dict[str, Any]:
        self.pedigree_calls.append(mints)
        return dict(_PEDIGREE)

    async def e2b_for(self, _session: Any, pairs: Sequence[tuple[str, datetime]]) -> dict[Any, Any]:
        self.e2b_calls.append(pairs)
        return {}


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> _Recorder:
    recorder = _Recorder()
    monkeypatch.setattr(lab_repo_e2b, "pedigree_for", recorder.pedigree_for)
    monkeypatch.setattr(lab_repo_e2b, "e2b_for", recorder.e2b_for)
    return recorder


def _once(*specs: RuleSetSpec) -> Iterator[RuleSetSpec]:
    """A one-shot iterable — ``lineage_for`` takes ``Iterable``, not ``Sequence``."""
    yield from specs


@pytest.mark.parametrize("specs", [[], ()], ids=["list", "tuple"])
async def test_no_set_on_the_clock_means_no_read(
    reads: _Recorder, specs: Sequence[RuleSetSpec]
) -> None:
    assert await lineage_for(None, [_row()], specs) == ({}, None)  # type: ignore[arg-type]
    assert reads.pedigree_calls == [] and reads.e2b_calls == []


async def test_an_empty_iterator_is_no_set_either(reads: _Recorder) -> None:
    assert await lineage_for(None, [_row()], _once()) == ({}, None)  # type: ignore[arg-type]
    assert reads.pedigree_calls == [] and reads.e2b_calls == []


async def test_a_one_shot_iterator_with_an_e2b_set_still_reads_both(reads: _Recorder) -> None:
    """The emptiness check must not consume the only set that asks for E2-b."""
    pedigree, e2b = await lineage_for(None, [_row()], _once(_spec(pedigree_e2b=True)))  # type: ignore[arg-type]
    assert pedigree == _PEDIGREE and e2b == {}
    assert reads.pedigree_calls == [[MINT]] and len(reads.e2b_calls) == 1


async def test_a_set_without_e2b_reads_the_pedigree_alone(reads: _Recorder) -> None:
    pedigree, e2b = await lineage_for(None, [_row()], [_spec()])  # type: ignore[arg-type]
    assert pedigree == _PEDIGREE and e2b is None
    assert reads.pedigree_calls == [[MINT]] and reads.e2b_calls == []
