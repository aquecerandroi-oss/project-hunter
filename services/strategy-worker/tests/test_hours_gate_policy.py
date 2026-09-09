"""``hunter_strategy_worker.hours_gate`` + ``.gate_policy`` — a janela de horas
e o envelope de portões, sem banco.

T3.59. A metade pura da regra nova: o que uma janela pode dizer, o que ela **não**
pode dizer (e é recusada em vez de ignorada), onde ficam as fronteiras
(11:59/12:00, 14:59/15:00, a janela que vira a meia-noite) e como as duas regras
convivem num envelope só. O caminho do worker contra um Postgres real — a versão
com ``hours=12-15`` que pula a barra das 10:00 com ``hours_gate:10`` — está em
``test_hours_gate.py``.

Roda: ``uv run pytest services/strategy-worker/tests/test_hours_gate_policy.py -q``
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from hunter_strategy_worker import hours_gate as hours_gate_module
from hunter_strategy_worker.activation_db import Refused
from hunter_strategy_worker.gate_policy import (
    GatePolicy,
    PolicyError,
    parse_policy,
    policy_argument,
    policy_clauses,
)
from hunter_strategy_worker.hours_gate import (
    HoursPolicy,
    evaluate_hours_gate,
    parse_hours_policy,
)
from hunter_strategy_worker.variant import LINEAGE_RE, lineage_of, policy_note, resolve_policy

MORNING: dict[str, Any] = {"hours": {"utc": [[12, 15]]}}
"""A janela pré-registrada da EXP-0023: 12:00-14:59 UTC = 09:00-11:59 BRT."""

SIDEWAYS_ONLY: dict[str, Any] = {
    "regime": {
        "allow": ["SIDEWAYS"],
        "classifier_version": "regime_hourly_v1",
        "rule": "previous_closed_hour",
        "scope": "btc",
    }
}
DAY = datetime(2026, 9, 5, tzinfo=UTC)
BRT = timezone(timedelta(hours=-3))


def window(*pairs: tuple[int, int]) -> HoursPolicy:
    return parse_hours_policy({"utc": [list(pair) for pair in pairs]})


def at(hour: int, minute: int = 0, second: int = 0) -> datetime:
    return DAY + timedelta(hours=hour, minutes=minute, seconds=second)


class TestParseTheWindow:
    def test_a_window_round_trips_and_expands_to_its_hours(self) -> None:
        parsed = window((12, 15))
        assert parsed.windows == ((12, 15),)
        assert parsed.hours == frozenset({12, 13, 14})
        assert parsed.to_body() == MORNING["hours"]

    def test_a_window_that_wraps_midnight_is_the_hours_on_both_sides(self) -> None:
        """``22-02`` é 22, 23, 00 e 01 — meia-aberta dos dois lados da virada."""
        assert window((22, 2)).hours == frozenset({22, 23, 0, 1})

    def test_two_windows_are_the_union_and_are_stored_sorted(self) -> None:
        parsed = window((20, 22), (2, 4))
        assert parsed.windows == ((2, 4), (20, 22))
        assert parsed.hours == frozenset({2, 3, 20, 21})

    def test_the_note_is_the_human_copy_of_the_windows(self) -> None:
        assert window((12, 15)).note == "hours=12-15"
        assert window((22, 2), (12, 15)).note == "hours=12-15+22-02"

    @pytest.mark.parametrize(
        ("raw", "message"),
        [
            ({"brt": [[12, 15]]}, "unknown field"),
            ({}, "non-empty 'utc' list"),
            ({"utc": []}, "non-empty 'utc' list"),
            ({"utc": [[12]]}, "is not a .start, end. pair"),
            ({"utc": [[12, 13, 14]]}, "is not a .start, end. pair"),
            ({"utc": [12]}, "is not a .start, end. pair"),
            ({"utc": [["12", "15"]]}, "is not an integer hour"),
            ({"utc": [[12.5, 15]]}, "is not an integer hour"),
            ({"utc": [[True, 15]]}, "is not an integer hour"),
            ({"utc": [[-1, 15]]}, "outside 0-23"),
            ({"utc": [[24, 15]]}, "outside 0-23"),
            ({"utc": [[12, 25]]}, "outside 0-24"),
            ({"utc": [[12, 12]]}, "is not a window"),
            ({"utc": [[0, 24]]}, "is not a window"),
            ({"utc": [[12, 15], [13, 16]]}, "overlaps another one"),
            ({"utc": [[12, 15], [14, 20]]}, "overlaps another one"),
            ({"utc": [[0, 12], [12, 24]]}, "cover all 24 hours"),
            ([[12, 15]], "must be a JSON object"),
        ],
    )
    def test_everything_unreadable_is_refused(self, raw: object, message: str) -> None:
        """Recusar, nunca ignorar — e recusar também o que é legível e **não é
        um portão**: uma janela que cobre o dia inteiro é um portão em que
        alguém acredita e que não existe."""
        with pytest.raises(PolicyError, match=message):
            parse_hours_policy(raw)


class TestTheBoundaries:
    @pytest.mark.parametrize(
        ("cut", "eligible"),
        [
            (at(11, 59, 59), False),
            (at(12), True),
            (at(12, 0, 1), True),
            (at(14, 59, 59), True),
            (at(15), False),
            (at(15, 0, 1), False),
        ],
    )
    def test_twelve_to_fifteen_is_half_open(self, cut: datetime, eligible: bool) -> None:
        """A fronteira é escrita, não descoberta: 12:00 entra, 15:00 não. Uma
        barra de 15 min que fecha às 15:00 já é da hora seguinte."""
        assert evaluate_hours_gate(window((12, 15)), cut=cut).eligible is eligible

    @pytest.mark.parametrize(
        ("cut", "eligible"),
        [(at(21, 59), False), (at(22), True), (at(1, 59), True), (at(2), False)],
    )
    def test_a_wrapping_window_is_half_open_on_both_ends(
        self, cut: datetime, eligible: bool
    ) -> None:
        assert evaluate_hours_gate(window((22, 2)), cut=cut).eligible is eligible

    def test_the_refusal_names_the_hour_zero_padded(self) -> None:
        """``hours_gate:09`` e não ``hours_gate:9``: o motivo é agrupado por
        string no ledger, e duas grafias da mesma hora seriam duas fatias."""
        gate = evaluate_hours_gate(window((12, 15)), cut=at(9, 30))
        assert (gate.eligible, gate.hour, gate.detail, gate.reason) == (
            False,
            9,
            "refused",
            "hours_gate:09",
        )

    def test_an_allowed_bar_still_says_which_hour_it_was(self) -> None:
        gate = evaluate_hours_gate(window((12, 15)), cut=at(12, 45))
        assert (gate.eligible, gate.hour, gate.detail) == (True, 12, "allowed")
        assert gate.to_jsonable() == {
            "eligible": True,
            "hour": 12,
            "detail": "allowed",
            "policy": {"utc": [[12, 15]]},
        }


class TestItReadsNothingButTheBar:
    def test_the_frame_is_utc_and_not_the_callers_offset(self) -> None:
        """09:30 em Brasília **é** 12:30 UTC: o mesmo instante escrito noutro
        fuso tem de dar o mesmo veredito, senão a janela significaria uma coisa
        no replay e outra na faixa viva."""
        same_instant = datetime(2026, 9, 5, 9, 30, tzinfo=BRT)
        assert same_instant == at(12, 30)
        assert evaluate_hours_gate(window((12, 15)), cut=same_instant).eligible
        assert not evaluate_hours_gate(
            window((12, 15)), cut=datetime(2026, 9, 5, 12, 30, tzinfo=BRT)
        ).eligible

    def test_the_verdict_is_a_function_of_the_bar_close_alone(self) -> None:
        """Não-antecipação, dita da forma mais forte possível para esta regra:
        o veredito é o mesmo objeto para o mesmo corte, quantas vezes for
        avaliado e em que ordem for — não há série que atrase, linha que
        envelheça nem relógio que ande."""
        policy = window((12, 15))
        first = evaluate_hours_gate(policy, cut=at(13, 15))
        second = evaluate_hours_gate(policy, cut=at(13, 15))
        assert first == second

    def test_the_module_never_reads_a_clock(self) -> None:
        """A afirmação acima é estrutural, então vale prendê-la ao código: um
        ``utcnow()`` acrescentado aqui um dia faria a mesma barra ser elegível
        no replay e inelegível na reprodução dele, sem nada acusar."""
        source = inspect.getsource(hours_gate_module)
        for forbidden in ("utcnow", ".now(", ".today(", "time.time"):
            assert forbidden not in source


class TestTheEnvelopeHoldsBothRules:
    def test_a_policy_with_only_hours_has_no_regime_rule(self) -> None:
        parsed = parse_policy(MORNING)
        assert parsed is not None
        assert parsed.regime is None
        assert parsed.hours is not None
        assert parsed.hours.hours == frozenset({12, 13, 14})
        assert parsed.to_jsonable() == MORNING

    def test_both_rules_round_trip_together(self) -> None:
        stored = {**SIDEWAYS_ONLY, **MORNING}
        parsed = parse_policy(stored)
        assert parsed is not None
        assert parsed.regime is not None
        assert parsed.hours is not None
        assert parsed.to_jsonable() == stored

    def test_an_unknown_key_next_to_a_known_one_is_still_refused(self) -> None:
        with pytest.raises(PolicyError, match="unknown key"):
            parse_policy({**MORNING, "session": {"utc": [[12, 15]]}})

    def test_an_unreadable_second_rule_refuses_the_whole_policy(self) -> None:
        """Fail-closed: uma versão cuja segunda regra este build não entende não
        pode decidir com a primeira — decidiria em mais contexto do que declara."""
        with pytest.raises(PolicyError, match="overlaps another one"):
            parse_policy({**SIDEWAYS_ONLY, "hours": {"utc": [[12, 15], [14, 18]]}})


class TestTheOperatorGrammar:
    def test_one_gate(self) -> None:
        assert policy_argument("hours=12-15") == MORNING

    def test_several_windows_in_one_clause(self) -> None:
        assert policy_argument("hours=22-02+12-15") == {"hours": {"utc": [[12, 15], [22, 2]]}}

    def test_two_gates_in_one_argument_split_on_the_key_not_on_the_comma(self) -> None:
        """A vírgula separa rótulos **e** regras; quem as distingue é o ``=``.
        Este é o caso que o momentum v12 da EXP-0023 usa."""
        assert policy_clauses("regime=btc:BTC_BULL,HIGH_VOLATILITY,hours=12-15") == {
            "regime": "btc:BTC_BULL,HIGH_VOLATILITY",
            "hours": "12-15",
        }
        both = policy_argument("regime=btc:BTC_BULL,HIGH_VOLATILITY,hours=12-15")
        assert both is not None
        assert both["regime"]["allow"] == ["BTC_BULL", "HIGH_VOLATILITY"]
        assert both["hours"] == {"utc": [[12, 15]]}

    def test_one_gate_can_be_removed_by_name(self) -> None:
        assert policy_argument("regime=none,hours=12-15") == MORNING
        assert policy_argument("hours=none") is None

    @pytest.mark.parametrize(
        ("argument", "message"),
        [
            ("hours=12", "is not <HH>-<HH>"),
            ("hours=12-", "in whole hours"),
            ("hours=12-30", "outside 0-24"),
            ("hours=doze-quinze", "in whole hours"),
            ("hours=12-15+13-16", "overlaps"),
            ("hours=12.5-15", "in whole hours"),
            ("sessao=12-15", "is not a gate this build knows"),
            ("12-15", "expected <gate>=<value>"),
            ("hours=12-15,hours=16-18", "appears twice"),
        ],
    )
    def test_it_refuses_what_the_worker_would_refuse(self, argument: str, message: str) -> None:
        with pytest.raises(PolicyError, match=message):
            policy_argument(argument)


class TestTheVariantKeepsWhatItDoesNotName:
    def test_a_policy_that_drops_the_parents_other_gate_is_refused(self) -> None:
        """O caso perigoso da T3.59, e o único em que a filha decidiria em
        **mais** contexto que o pai: ``--policy hours=12-15`` sobre um pai com
        portão de regime tiraria o regime em silêncio."""
        with pytest.raises(Refused, match="não menciona o portão regime"):
            resolve_policy("hours=12-15", SIDEWAYS_ONLY)

    def test_naming_both_gates_keeps_both(self) -> None:
        kept = resolve_policy("regime=btc:SIDEWAYS,hours=12-15", SIDEWAYS_ONLY)
        assert kept == {**SIDEWAYS_ONLY, **MORNING}

    def test_dropping_one_gate_on_purpose_is_allowed(self) -> None:
        assert resolve_policy("regime=none,hours=12-15", SIDEWAYS_ONLY) == MORNING

    def test_the_whole_gate_can_still_be_removed(self) -> None:
        assert resolve_policy("none", {**SIDEWAYS_ONLY, **MORNING}) is None

    def test_a_child_of_an_ungated_parent_only_needs_its_own_window(self) -> None:
        assert resolve_policy("hours=12-15", None) == MORNING


class TestTheLineageCarriesTheWindow:
    def test_the_note_of_each_shape(self) -> None:
        assert policy_note(None) == "none"
        hours_only = parse_policy(MORNING)
        assert hours_only is not None
        assert policy_note(hours_only) == "hours=12-15"
        both = parse_policy({**SIDEWAYS_ONLY, **MORNING})
        assert both is not None
        assert policy_note(both) == "btc:SIDEWAYS;hours=12-15"

    def test_a_regime_only_note_is_byte_for_byte_what_t352_wrote(self) -> None:
        """As variantes já gravadas continuam legíveis pela mesma leitura: o
        ``;`` só aparece quando há de fato dois portões."""
        regime_only = parse_policy(SIDEWAYS_ONLY)
        assert regime_only is not None
        assert policy_note(regime_only) == "btc:SIDEWAYS"

    def test_the_frozen_lineage_prefix_still_matches_with_two_gates(self) -> None:
        """O segmento ``| policy=…`` é ``\\S+``: acrescentar a segunda regra não
        reescreve o formato congelado (T3.52), e ``lineage_of`` continua achando
        o prefixo inteiro."""
        changelog = (
            "variante de v11 | derived_from=v11 | overrides= | params_hash=aaaaaaaaaaaa "
            "| policy=btc:BTC_BULL,HIGH_VOLATILITY;hours=12-15 | EXP-0023"
        )
        assert LINEAGE_RE.match(changelog) is not None
        assert lineage_of(changelog).endswith("| policy=btc:BTC_BULL,HIGH_VOLATILITY;hours=12-15")


def test_the_gate_policy_dataclass_is_frozen() -> None:
    """A política é congelada com a versão (``0017``); o objeto que a
    representa também é, para que ninguém a mude no meio de uma passada."""
    parsed = parse_policy(MORNING)
    assert isinstance(parsed, GatePolicy)
    with pytest.raises(AttributeError):
        parsed.hours = None  # type: ignore[misc]
