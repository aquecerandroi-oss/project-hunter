"""``hunter_strategy_worker.regime_gate`` — a política e o veredito, sem banco.

A metade pura do portão da T3.52: o que uma ``eligibility_policy`` pode dizer, o
que ela **não** pode dizer (e é recusada em vez de ignorada), e o veredito sobre
uma linha horária já lida. A regra de corte contra o Postgres real — a decisão
das 15:30 que enxerga a linha das 14:00 — está em ``test_regime_gate.py``.

Roda: ``uv run pytest services/strategy-worker/tests/test_regime_gate_policy.py -q``
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from hunter_strategy_worker.activate_derived import (
    LINEAGE_RE as ACTIVATE_DERIVED_LINEAGE_RE,
)
from hunter_strategy_worker.activate_derived import keep_lineage
from hunter_strategy_worker.activation_db import Refused
from hunter_strategy_worker.regime_gate import (
    DEFAULT_CLASSIFIER,
    MAX_STALENESS,
    RULE_PREVIOUS_CLOSED_HOUR,
    EligibilityPolicy,
    PolicyError,
    RegimeRow,
    evaluate_gate,
    parse_policy,
    policy_argument,
)
from hunter_strategy_worker.variant import (
    LINEAGE_RE,
    lineage_of,
    policy_note,
    resolve_policy,
    variant_changelog,
)

CUT = datetime(2026, 9, 5, 15, 30, tzinfo=UTC)
HOUR = timedelta(hours=1)
PREVIOUS_HOUR = datetime(2026, 9, 5, 14, 0, tzinfo=UTC)
SIDEWAYS_ONLY = {
    "regime": {
        "allow": ["SIDEWAYS"],
        "classifier_version": DEFAULT_CLASSIFIER,
        "rule": RULE_PREVIOUS_CLOSED_HOUR,
        "scope": "btc",
    }
}


def row(regime: str, *, hour: datetime = PREVIOUS_HOUR) -> RegimeRow:
    return RegimeRow(id=uuid.uuid4(), regime=regime, start_time=hour, end_time=hour + HOUR)


def policy(*labels: str) -> EligibilityPolicy:
    parsed = parse_policy({"regime": {"allow": list(labels)}})
    assert parsed is not None
    return parsed


class TestParsePolicy:
    def test_null_is_no_gate_and_not_a_default(self) -> None:
        """Toda versão anterior à ``0017`` tem ``NULL`` e decide em qualquer
        regime — ``None`` é a resposta, nunca uma política implícita."""
        assert parse_policy(None) is None

    def test_a_complete_policy_round_trips(self) -> None:
        parsed = parse_policy(SIDEWAYS_ONLY)
        assert parsed is not None
        assert parsed.scope == "btc"
        assert parsed.classifier_version == DEFAULT_CLASSIFIER
        assert parsed.rule == RULE_PREVIOUS_CLOSED_HOUR
        assert parsed.allow == ("SIDEWAYS",)
        assert parsed.to_jsonable() == SIDEWAYS_ONLY

    def test_the_defaults_are_the_hourly_series(self) -> None:
        """``allow`` é o único campo obrigatório: os outros três só têm um valor
        que este build sabe honrar, e escrevê-los é opcional, não livre."""
        parsed = policy("SIDEWAYS", "BTC_BULL")
        assert (parsed.scope, parsed.classifier_version, parsed.rule) == (
            "btc",
            DEFAULT_CLASSIFIER,
            RULE_PREVIOUS_CLOSED_HOUR,
        )

    def test_labels_are_sorted_so_two_spellings_are_one_policy(self) -> None:
        assert policy("BTC_BULL", "SIDEWAYS").allow == policy("SIDEWAYS", "BTC_BULL").allow

    @pytest.mark.parametrize(
        ("raw", "message"),
        [
            ({"session": {"allow": ["SIDEWAYS"]}}, "unknown key"),
            ({}, "has no 'regime' policy"),
            ({"regime": {"allow": ["SIDEWAYS"], "maximo": 3}}, "unknown field"),
            ({"regime": {"allow": ["SIDEWAYS"], "scope": "moon"}}, "is not a RegimeScope"),
            ({"regime": {"allow": ["SIDEWAYS"], "rule": "containing_hour"}}, "is not a rule"),
            ({"regime": {"allow": []}}, "non-empty 'allow'"),
            ({"regime": {"allow": "SIDEWAYS"}}, "non-empty 'allow'"),
            ({"regime": {"allow": ["LATERAL"]}}, "is not a MarketRegime label"),
            ({"regime": {"allow": ["SIDEWAYS", "SIDEWAYS"]}}, "appears twice"),
            ({"regime": ["SIDEWAYS"]}, "must be a JSON object"),
            (["regime"], "must be a JSON object"),
        ],
    )
    def test_everything_unreadable_is_refused(self, raw: object, message: str) -> None:
        """Recusar, nunca ignorar: uma política que este build não entende
        inteira faria a versão decidir *sem* o portão que ela declara."""
        with pytest.raises(PolicyError, match=message):
            parse_policy(raw)

    def test_unknown_cannot_be_allowed(self) -> None:
        with pytest.raises(PolicyError, match="UNKNOWN cannot be allowed"):
            parse_policy({"regime": {"allow": ["UNKNOWN"]}})


class TestPolicyArgument:
    def test_the_operator_grammar(self) -> None:
        assert policy_argument("regime=BTC:SIDEWAYS") == SIDEWAYS_ONLY

    def test_two_labels(self) -> None:
        assert policy_argument("regime=btc:SIDEWAYS,BTC_BULL")["regime"]["allow"] == [
            "BTC_BULL",
            "SIDEWAYS",
        ]

    @pytest.mark.parametrize(
        "argument", ["regime=btc", "sessao=btc:SIDEWAYS", "regime=btc:LATERAL", "regime=btc:"]
    )
    def test_it_refuses_what_the_worker_would_refuse(self, argument: str) -> None:
        with pytest.raises(PolicyError):
            policy_argument(argument)


class TestVerdict:
    def test_an_allowed_label_lets_the_decision_through(self) -> None:
        gate = evaluate_gate(policy("SIDEWAYS"), row("SIDEWAYS"), CUT)
        assert (gate.eligible, gate.detail, gate.label) == (True, "allowed", "SIDEWAYS")

    def test_a_label_outside_allow_refuses_by_name(self) -> None:
        gate = evaluate_gate(policy("SIDEWAYS"), row("BTC_BEAR"), CUT)
        assert (gate.eligible, gate.detail, gate.reason) == (
            False,
            "refused",
            "regime_gate:BTC_BEAR",
        )

    def test_the_classifier_warmup_refuses_as_unknown(self) -> None:
        gate = evaluate_gate(policy("SIDEWAYS"), row("UNKNOWN"), CUT)
        assert (gate.eligible, gate.detail, gate.reason) == (
            False,
            "classifier_warmup",
            "regime_gate:unknown",
        )

    def test_no_row_refuses_as_unknown_and_says_so(self) -> None:
        gate = evaluate_gate(policy("SIDEWAYS"), None, CUT)
        assert (gate.eligible, gate.detail, gate.reason) == (False, "no_row", "regime_gate:unknown")
        assert gate.row_id is None

    def test_a_row_older_than_the_ceiling_is_stale_not_context(self) -> None:
        """O produtor horário morto é exatamente quando a versão **não** pode
        continuar decidindo com o regime de ontem."""
        old = CUT - timedelta(hours=5)  # termina 4 h antes do corte, teto de 2 h
        gate = evaluate_gate(policy("SIDEWAYS"), row("SIDEWAYS", hour=old), CUT)
        assert (gate.eligible, gate.detail, gate.reason) == (False, "stale", "regime_gate:unknown")

    def test_the_ceiling_boundary_is_inclusive(self) -> None:
        """``cut - end_time == MAX_STALENESS`` ainda é contexto; um segundo a
        mais não é. A fronteira é escrita, não descoberta."""
        edge = CUT - MAX_STALENESS - HOUR
        assert evaluate_gate(policy("SIDEWAYS"), row("SIDEWAYS", hour=edge), CUT).eligible
        past = edge - timedelta(seconds=1)
        assert not evaluate_gate(policy("SIDEWAYS"), row("SIDEWAYS", hour=past), CUT).eligible

    def test_the_envelope_block_names_the_row_that_gated_it(self) -> None:
        allowed = row("SIDEWAYS")
        assert allowed.end_time is not None
        block = evaluate_gate(policy("SIDEWAYS"), allowed, CUT).to_jsonable()
        assert block["row_id"] == str(allowed.id)
        assert block["hour_start"] == allowed.start_time.isoformat()
        assert block["hour_end"] == allowed.end_time.isoformat()
        assert block["policy"]["allow"] == ["SIDEWAYS"]


class TestVariantPolicy:
    def test_without_the_flag_the_child_inherits_the_parents_gate(self) -> None:
        assert resolve_policy(None, SIDEWAYS_ONLY) == SIDEWAYS_ONLY

    def test_none_removes_it_and_only_when_there_is_one(self) -> None:
        assert resolve_policy("none", SIDEWAYS_ONLY) is None
        with pytest.raises(Refused, match="não há o que remover"):
            resolve_policy("none", None)

    def test_a_new_gate_replaces_the_inherited_one(self) -> None:
        replaced = resolve_policy("regime=btc:BTC_BULL", SIDEWAYS_ONLY)
        assert replaced is not None
        assert replaced["regime"]["allow"] == ["BTC_BULL"]

    def test_the_lineage_carries_the_gate_when_only_the_gate_moved(self) -> None:
        """Uma variante que só muda o portão tem ``overrides=`` vazio e o mesmo
        ``params_hash`` do pai: sem o segmento ``policy=`` a linhagem diria que
        nada mudou."""
        changelog = variant_changelog(
            "v6", [], "a" * 12, "T3.52", policy=policy("SIDEWAYS"), policy_moved=True
        )
        assert changelog.startswith(
            "variante de v6 | derived_from=v6 | overrides= | params_hash=aaaaaaaaaaaa "
            "| policy=btc:SIDEWAYS | T3.52"
        )
        assert lineage_of(changelog).endswith("| policy=btc:SIDEWAYS")

    def test_a_changelog_written_before_this_format_still_matches(self) -> None:
        """O segmento é opcional: acrescentá-lo não reescreve o formato que as
        variantes já gravadas usam."""
        old = "variante de v2 | derived_from=v2 | overrides=atr_pct_min=0.0089 | params_hash=abc123abc123 | KB-0008"
        assert LINEAGE_RE.match(old) is not None
        assert lineage_of(old) == (
            "variante de v2 | derived_from=v2 | overrides=atr_pct_min=0.0089 "
            "| params_hash=abc123abc123"
        )

    def test_policy_note_reads_none_when_there_is_no_gate(self) -> None:
        assert policy_note(None) == "none"

    def test_the_two_written_out_copies_of_the_lineage_prefix_agree(self) -> None:
        """``activate_derived.py`` cannot import from this package's sibling in
        ``infra/scripts`` (the reason ``test_derive_variant_lineage.py`` keeps its
        own copy honest against ``derive_variant.py``), so it keeps its own
        literal copy of the prefix. This is the same kind of test for the other
        pair: ``variant.py`` (what ``derive_variant.py --policy`` freezes) and
        ``activate_derived.py`` (what reads it back at activation) must agree on
        exactly the same pattern, ``| policy=...`` segment included, or one side
        could drift and either reject a real lineage or keep a fake one."""
        assert ACTIVATE_DERIVED_LINEAGE_RE.pattern == LINEAGE_RE.pattern

    def test_activation_keeps_the_policy_segment_when_only_the_gate_moved(self) -> None:
        """The row's frozen ``changelog`` is exactly what ``derive_variant.py
        --policy`` writes; ``activate_derived.keep_lineage`` is what the derived
        route puts in front of the operator's activation note. Losing the
        ``| policy=...`` segment here would silently un-gate a variant at the
        only write it ever gets (``activate_derived.activate_derived``)."""
        frozen = variant_changelog(
            "v6", [], "a" * 12, "T3.52", policy=policy("SIDEWAYS"), policy_moved=True
        )
        kept = keep_lineage(frozen, "ativada para a coorte prospectiva")
        assert kept.startswith(
            "variante de v6 | derived_from=v6 | overrides= | params_hash=aaaaaaaaaaaa "
            "| policy=btc:SIDEWAYS"
        )
        assert kept.endswith(" | ativada para a coorte prospectiva")
