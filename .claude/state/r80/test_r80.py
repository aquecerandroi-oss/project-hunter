# R80 — testes sintéticos com valores esperados conhecidos.
# cd .claude/state/r80 && uv run --project C:/dev/project-hunter pytest -q test_r80.py
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from r80 import (
    TokenIndex,
    first_per_mint,
    golpe_ficha,
    golpe_raw,
    normalize_twitter,
)
from infra.research.guards import Instants, LookAheadError, assert_observable

UTC = timezone.utc
T = datetime(2026, 9, 20, 12, tzinfo=UTC)


# ---------- normalização do link ----------
@pytest.mark.parametrize(
    ("url", "key", "kind"),
    [
        ("https://x.com/ElonMusk", "profile:elonmusk", "profile"),
        ("https://twitter.com/elonmusk/", "profile:elonmusk", "profile"),
        ("http://www.twitter.com/elonmusk?s=21", "profile:elonmusk", "profile"),
        ("https://mobile.twitter.com/ElonMusk#top", "profile:elonmusk", "profile"),
        ("x.com/elonmusk", "profile:elonmusk", "profile"),
        ("https://x.com/elonmusk/status/1234567890123456789?s=46&t=abc", "post:1234567890123456789", "post"),
        ("https://twitter.com/SomeoneElse/status/1234567890123456789", "post:1234567890123456789", "post"),
        ("https://x.com/i/status/1234567890123456789", "post:1234567890123456789", "post"),
        ("https://x.com/i/communities/1900000000000000000", "community:1900000000000000000", "community"),
        ("https://x.com/search?q=%24DOG", "other:x.com/search?q=%24dog", "other"),
        ("https://x.com/search?q=%24CAT", "other:x.com/search?q=%24cat", "other"),
    ],
)
def test_normalize_known_values(url: str, key: str, kind: str) -> None:
    got = normalize_twitter(url)
    assert got is not None
    assert got == (key, kind)


def test_normalize_blank_is_none() -> None:
    assert normalize_twitter(None) is None
    assert normalize_twitter("") is None
    assert normalize_twitter("   ") is None


def test_other_keeps_query_so_distinct_searches_do_not_merge() -> None:
    a = normalize_twitter("https://x.com/search?q=%24DOG")
    b = normalize_twitter("https://x.com/search?q=%24CAT")
    assert a != b


# ---------- reuso_social e cobertura ----------
def _tok(mint: str, created: datetime, twitter: str | None, observed: datetime | None) -> dict:
    return {"mint": mint, "created_at": created, "twitter": twitter, "social_observed_at": observed}


def _universe(extra: list[dict] | None = None) -> list[dict]:
    h = timedelta(hours=1)
    rows = [
        _tok("SELF", T - 2 * h, "https://x.com/dev1", T - 2 * h),
        _tok("A", T - 5 * h, "https://twitter.com/Dev1/", T - 5 * h),  # mesmo perfil → conta
        _tok("B", T - 23 * h, "x.com/dev1?s=20", T - 23 * h),  # dentro das 24 h → conta
        _tok("C", T - 25 * h, "x.com/dev1", T - 25 * h),  # fora das 24 h → não conta
        _tok("D", T - 1 * h, "x.com/dev2", T - 1 * h),  # outro link → não conta
        _tok("E", T - 3 * h, None, T - 3 * h),  # observado, sem twitter
        _tok("F", T - 4 * h, None, None),  # não observado (escuro)
    ]
    return rows + (extra or [])


def test_reuse_known_value() -> None:
    idx = TokenIndex(_universe())
    assert idx.reuse("SELF", T) == 2  # A e B; nunca a própria, nunca C (25 h) nem D (outro link)


def test_reuse_does_not_change_with_coins_created_at_or_after_the_decision() -> None:
    """Anti-antecipação: moedas com created_at >= decisão nunca entram, nem mudando o que elas dizem."""
    base = TokenIndex(_universe()).reuse("SELF", T)
    later = [
        _tok("G", T, "x.com/dev1", T),  # exatamente no instante: fora (created_at < decisão é estrito)
        _tok("H", T + timedelta(seconds=1), "x.com/dev1", T + timedelta(seconds=1)),
        _tok("I", T + timedelta(hours=3), "https://twitter.com/DEV1", T + timedelta(hours=3)),
    ]
    assert TokenIndex(_universe(later)).reuse("SELF", T) == base
    mutated = [dict(r, twitter="x.com/dev2") if r["mint"] in {"G", "H", "I"} else r for r in _universe(later)]
    assert TokenIndex(mutated).reuse("SELF", T) == base


def test_reuse_none_when_own_identity_not_observed() -> None:
    idx = TokenIndex(_universe())
    assert idx.reuse("F", T) is None  # escuro: ausente, nunca zero
    assert idx.reuse("E", T) == 0  # observado sem link: nenhum link a reutilizar
    assert idx.has_twitter("E") is False
    assert idx.has_twitter("F") is None


def test_known_only_variant_drops_coins_observed_after_the_decision() -> None:
    late_obs = [dict(r, social_observed_at=T + timedelta(minutes=5)) if r["mint"] == "A" else r for r in _universe()]
    idx = TokenIndex(late_obs)
    assert idx.reuse("SELF", T) == 2  # link é da criação (imutável): conta
    assert idx.reuse("SELF", T, known_only=True) == 1  # o que a base sabia na decisão: só B


def test_lookback_coverage_known_value() -> None:
    idx = TokenIndex(_universe())
    # criadas em [T-24h, T): SELF, A, B, D, E, F = 6; observadas 5
    assert idx.coverage(T) == pytest.approx(5 / 6)


# ---------- guarda do moinho ----------
def test_guard_catches_a_cheat_that_counts_coins_created_after_the_decision() -> None:
    dec = T
    ok = Instants(as_of=dec - timedelta(hours=1), computed_at=dec, tape_as_of=dec - timedelta(hours=1))
    assert_observable(ok, dec, "ok")
    cheat = Instants(as_of=dec + timedelta(hours=2), computed_at=dec, tape_as_of=dec + timedelta(hours=2))
    with pytest.raises(LookAheadError):
        assert_observable(cheat, dec, "cheat")


# ---------- população e classe de perda ----------
def _bet(**k: object) -> dict:
    base: dict = {"lane": "paper", "mint": "M", "decided_at": "2026-09-20 12:00:00+00", "entry_at": "2026-09-20 12:00:01+00"}
    base.update(k)
    return base


def test_first_per_mint_ties_go_to_real() -> None:
    rows = [
        _bet(bet_id="p2", decided_at="2026-09-20 12:05:00+00"),
        _bet(bet_id="p1"),
        _bet(bet_id="r1", lane="real"),
        _bet(bet_id="x", mint="N"),
    ]
    out = {r["mint"]: r["bet_id"] for r in first_per_mint(rows)}
    assert out == {"M": "r1", "N": "x"}


def test_golpe_rules() -> None:
    d = Decimal
    # perda com creator_dump e pico acima do custo → golpe (ficha e cru)
    assert golpe_ficha(pnl=d("-0.01"), peak_le_cost=False, exit_reason="creator_dump", sellers=None) is True
    # perda com 10 vendedores num slot → golpe
    assert golpe_ficha(pnl=d("-0.01"), peak_le_cost=False, exit_reason="trailing", sellers=10) is True
    assert golpe_ficha(pnl=d("-0.01"), peak_le_cost=False, exit_reason="trailing", sellers=9) is False
    # a ficha checa comprou_no_topo antes: pico <= custo leva a perda para lá
    assert golpe_ficha(pnl=d("-0.01"), peak_le_cost=True, exit_reason="creator_dump", sellers=50) is False
    assert golpe_raw(pnl=d("-0.01"), exit_reason="creator_dump", sellers=None) is True
    # ganho nunca é golpe
    assert golpe_ficha(pnl=d("0.01"), peak_le_cost=False, exit_reason="creator_dump", sellers=50) is False
    assert golpe_raw(pnl=d("0.01"), exit_reason="creator_dump", sellers=50) is False
    # vendedores desconhecidos: pula a regra, não presume
    assert golpe_ficha(pnl=d("-0.01"), peak_le_cost=None, exit_reason="trailing", sellers=None) is False


# ---------- adendo (Astra, desenho) ----------
def test_community_id_must_end_the_segment() -> None:
    assert normalize_twitter("https://x.com/i/communities/123")[0] == "community:123"
    assert normalize_twitter("https://x.com/i/communities/123/")[0] == "community:123"
    assert normalize_twitter("https://x.com/i/communities/123abc")[1] == "other"


def test_coverage_known_only_uses_the_same_cut() -> None:
    late = [dict(r, social_observed_at=T + timedelta(minutes=1)) if r["mint"] in {"A", "B"} else r for r in _universe()]
    idx = TokenIndex(late)
    assert idx.coverage(T) == pytest.approx(5 / 6)
    assert idx.coverage(T, known_only=True) == pytest.approx(3 / 6)  # só SELF, D, E sabidas antes de T


def test_duplicate_mint_is_refused() -> None:
    with pytest.raises(ValueError):
        TokenIndex(_universe([_tok("A", T - timedelta(hours=5), "x.com/other", T)]))


def test_candidate_created_at_or_after_decision_is_refused() -> None:
    idx = TokenIndex(_universe())
    with pytest.raises(ValueError):
        idx.reuse("SELF", T - timedelta(hours=3))  # a própria moeda nasceu depois desta "decisão"


def test_golpe_raw_unknown_when_tape_missing() -> None:
    d = Decimal
    assert golpe_raw(pnl=d("-0.01"), exit_reason="trailing", sellers=None) is None  # não comprova ausência
    assert golpe_raw(pnl=d("-0.01"), exit_reason="creator_dump", sellers=None) is True
    assert golpe_raw(pnl=d("0.01"), exit_reason="trailing", sellers=None) is False  # ganho nunca é golpe


def test_r_of_uses_decimal_and_refuses_zero_size() -> None:
    from r80 import r_of, resolved

    assert r_of({"pnl_sol": "-0.0284", "size_sol": "0.0700000000"}) == pytest.approx(-0.405714285714)
    assert resolved({"status": "closed", "pnl_sol": "0.01", "size_sol": "0.0000000000", "oq": ""}) is False


def test_golpe_ratio_condition() -> None:
    from h020 import golpe_ok

    assert golpe_ok(0.10, 0.0) is True  # B zero e A positivo: duplicação trivialmente satisfeita
    assert golpe_ok(0.0, 0.0) is False  # ambas zero: não é evidência
    assert golpe_ok(0.20, 0.10) is True
    assert golpe_ok(0.329, 0.323) is False
    assert golpe_ok(float("nan"), 0.1) is False
