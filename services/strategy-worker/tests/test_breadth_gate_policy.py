"""``hunter_strategy_worker.breadth_gate`` + ``.gate_policy`` — a terceira regra,
sem banco.

T3.77 / H-P8. A metade pura: o que a faixa pode dizer, o que ela **não** pode
dizer (e é recusada em vez de ignorada), onde ficam as fronteiras (``min``
inclusivo, ``max`` exclusivo), como a regra convive com as duas antigas no mesmo
envelope, e o que ``--policy breadth=0.10-0.60`` grava. O caminho do worker
contra um Postgres real — a versão 0,10-0,60 que pula a barra em que a amplitude
é 0,97 com ``breadth_gate:0.97`` — está em ``test_breadth_gate.py``.

Roda: ``uv run pytest services/strategy-worker/tests/test_breadth_gate_policy.py -q``
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

import pytest

from hunter_strategy_worker.activation_db import Refused
from hunter_strategy_worker.breadth_gate import (
    REASON_UNAVAILABLE,
    BreadthPolicy,
    BreadthRow,
    breadth_clause,
    evaluate_breadth_gate,
    parse_breadth_policy,
)
from hunter_strategy_worker.gate_policy import (
    PolicyError,
    parse_policy,
    policy_argument,
    policy_clauses,
)
from hunter_strategy_worker.variant import (
    LINEAGE_RE,
    canonical_policy,
    policy_note,
    resolve_policy,
    stored_policy,
    variant_changelog,
)

BAND: dict[str, Any] = {"breadth": {"window_m": 5, "min": "0.10", "max": "0.60"}}
"""A faixa pré-registrada da EXP-0027, exatamente como o brief a escreve."""

SIDEWAYS_ONLY: dict[str, Any] = {
    "regime": {
        "allow": ["SIDEWAYS"],
        "classifier_version": "regime_hourly_v1",
        "rule": "previous_closed_hour",
        "scope": "btc",
    }
}
MORNING: dict[str, Any] = {"hours": {"utc": [[12, 15]]}}
CUT = datetime(2026, 9, 9, 22, 8, tzinfo=UTC)
ROW_ID = UUID("0192f000-0000-7000-8000-000000000001")


def band(minimum: str = "0.10", maximum: str = "0.60") -> BreadthPolicy:
    return parse_breadth_policy({"window_m": 5, "min": minimum, "max": maximum})


def reading(value: str | None, *, usable: bool = True, reason: str | None = None) -> BreadthRow:
    return BreadthRow(
        id=ROW_ID,
        end_time=CUT,
        value=None if value is None else Decimal(value),
        usable=usable,
        reason=reason,
        covered=200,
        universe_size=200,
    )


class TestLerAFaixa:
    def test_a_faixa_do_brief_faz_round_trip_byte_a_byte(self) -> None:
        parsed = band()
        assert (parsed.window_m, parsed.minimum, parsed.maximum) == (
            5,
            Decimal("0.10"),
            Decimal("0.60"),
        )
        assert parsed.to_body() == BAND["breadth"]
        assert parsed.note == "breadth=0.10-0.60"

    @pytest.mark.parametrize(
        "body",
        [
            {"window_m": 5, "min": "0.10"},
            {"window_m": 5, "min": "0.10", "max": "0.60", "scope": "btc"},
            {"window_m": 15, "min": "0.10", "max": "0.60"},
            {"window_m": 5, "min": 0.10, "max": "0.60"},
            {"window_m": 5, "min": "0.60", "max": "0.10"},
            {"window_m": 5, "min": "0.30", "max": "0.30"},
            {"window_m": 5, "min": "0", "max": "1"},
            {"window_m": 5, "min": "-0.1", "max": "0.60"},
            {"window_m": 5, "min": "0.10", "max": "1.5"},
            {"window_m": True, "min": "0.10", "max": "0.60"},
            {"window_m": 5, "min": "abc", "max": "0.60"},
            ["breadth"],
        ],
    )
    def test_o_que_nao_se_lê_se_recusa_nunca_se_ignora(self, body: object) -> None:
        """Uma versão com portão ilegível **não** pode decidir sem portão: os
        sinais dela seriam atribuídos a um experimento que ninguém rodou."""
        with pytest.raises(PolicyError):
            parse_breadth_policy(body)

    def test_um_limite_numerico_e_recusado_com_o_motivo_da_t3_59(self) -> None:
        """A regra de horas quase morreu por isto (``variant.stored_policy``): a
        forma canônica emite todo número como string decimal. Limites já em
        string atravessam as duas serializações sem mudar."""
        with pytest.raises(PolicyError, match="decimal \\*string\\*"):
            parse_breadth_policy({"window_m": 5, "min": 0.1, "max": "0.60"})

    def test_a_janela_que_este_build_nao_calcula_e_recusada_por_nome(self) -> None:
        with pytest.raises(PolicyError, match="not a window this build computes"):
            parse_breadth_policy({"window_m": 15, "min": "0.10", "max": "0.60"})


class TestAFronteira:
    @pytest.mark.parametrize(
        ("value", "eligible", "detail"),
        [
            ("0.0999", False, "refused"),
            ("0.1000", True, "allowed"),
            ("0.3500", True, "allowed"),
            ("0.5999", True, "allowed"),
            ("0.6000", False, "refused"),
            ("0.9700", False, "refused"),
        ],
    )
    def test_meia_aberta_no_topo(self, value: str, eligible: bool, detail: str) -> None:
        """``[min, max)``: 0,10 passa, 0,60 não. Duas faixas adjacentes ladrilham
        a reta sem sobreposição e sem buraco."""
        gate = evaluate_breadth_gate(band(), reading(value), CUT)
        assert (gate.eligible, gate.detail) == (eligible, detail)

    def test_a_recusa_arredonda_para_duas_casas_e_o_envelope_guarda_o_exato(
        self,
    ) -> None:
        """O histograma de ``ineligible`` agrupa pela string; quatro casas dariam
        um balde por barra. O valor exato viaja na proveniência."""
        gate = evaluate_breadth_gate(band(), reading("0.9749"), CUT)
        assert gate.reason == "breadth_gate:0.97"
        assert gate.to_jsonable()["value"] == "0.9749"
        assert gate.to_jsonable()["row_id"] == str(ROW_ID)

    def test_o_minuto_do_kb_0083_e_recusado_com_o_numero_do_brief(self) -> None:
        gate = evaluate_breadth_gate(band(), reading("0.9700"), CUT)
        assert gate.eligible is False
        assert gate.reason == "breadth_gate:0.97"


class TestQuandoASerieNaoResponde:
    def test_sem_linha_para_o_minuto_a_versao_emudece(self) -> None:
        """Falha fechada: um produtor morto **não** deixa a versão decidir com o
        valor de três minutos atrás — não há tolerância porque não há janela."""
        gate = evaluate_breadth_gate(band(), None, CUT)
        assert (gate.eligible, gate.detail, gate.reason) == (
            False,
            "no_row",
            REASON_UNAVAILABLE,
        )

    def test_uma_linha_inutilizavel_carrega_o_motivo_do_produtor(self) -> None:
        """O portão não inventa um segundo diagnóstico de um fato que o produtor
        já nomeou."""
        row = reading(None, usable=False, reason="insufficient_coverage")
        gate = evaluate_breadth_gate(band(), row, CUT)
        assert (gate.detail, gate.reason) == ("unusable", REASON_UNAVAILABLE)
        assert gate.to_jsonable()["series_reason"] == "insufficient_coverage"


class TestOEnvelopeComTresRegras:
    def test_as_tres_convivem_e_cada_uma_volta_como_entrou(self) -> None:
        stored = {**SIDEWAYS_ONLY, **MORNING, **BAND}
        parsed = parse_policy(stored)
        assert parsed is not None
        assert parsed.regime is not None and parsed.hours is not None
        assert parsed.breadth is not None
        assert parsed.to_jsonable() == stored

    def test_uma_politica_so_de_amplitude_e_valida(self) -> None:
        parsed = parse_policy(BAND)
        assert parsed is not None
        assert (parsed.regime, parsed.hours) == (None, None)
        assert parsed.breadth == band()

    def test_a_linhagem_humana_junta_as_tres_com_ponto_e_virgula(self) -> None:
        parsed = parse_policy({**SIDEWAYS_ONLY, **MORNING, **BAND})
        assert policy_note(parsed) == "btc:SIDEWAYS;hours=12-15;breadth=0.10-0.60"

    def test_a_linhagem_gravada_continua_casando_com_o_formato_congelado(self) -> None:
        parsed = parse_policy({**MORNING, **BAND})
        changelog = variant_changelog("v3", [], "a" * 64, "nota", policy=parsed, policy_moved=True)
        assert LINEAGE_RE.match(changelog)
        assert "policy=hours=12-15;breadth=0.10-0.60" in changelog

    def test_uma_politica_so_de_regime_sai_exatamente_como_antes(self) -> None:
        """Regressão da T3.52/T3.59: acrescentar uma regra não pode reescrever a
        cópia humana das variantes já gravadas."""
        assert policy_note(parse_policy(SIDEWAYS_ONLY)) == "btc:SIDEWAYS"


class TestAGramaticaDoOperador:
    def test_breadth_igual_faixa_vira_o_corpo_que_o_worker_le(self) -> None:
        assert breadth_clause("0.10-0.60") == BAND["breadth"]
        assert policy_argument("breadth=0.10-0.60") == BAND

    @pytest.mark.parametrize("argument", ["breadth=0.10", "breadth=", "breadth=a-b"])
    def test_uma_faixa_malformada_e_recusada_pelo_mesmo_validador(self, argument: str) -> None:
        with pytest.raises(PolicyError):
            policy_argument(argument)

    def test_as_tres_regras_num_argumento_so(self) -> None:
        """A vírgula separa regras **e** rótulos de regime; quem abre uma regra é
        o ``=``. A faixa não tem vírgula, então nada muda nessa leitura."""
        clauses = policy_clauses("regime=btc:SIDEWAYS,BTC_BULL,hours=12-15,breadth=0.10-0.60")
        assert clauses == {
            "regime": "btc:SIDEWAYS,BTC_BULL",
            "hours": "12-15",
            "breadth": "0.10-0.60",
        }

    def test_a_coluna_guarda_strings_e_a_comparacao_passa_pela_forma_canonica(self) -> None:
        """``stored_policy`` grava os tipos que a política tem; como os limites já
        são strings, a forma canônica e a coluna coincidem — que é exatamente o
        que a T3.59 não conseguia dizer dos inteiros dela."""
        column = stored_policy(BAND)
        assert column is not None
        assert json.loads(column)["breadth"]["min"] == "0.10"
        assert canonical_policy(BAND) == canonical_policy(json.loads(column))


class TestHerdarTrocarERemover:
    def test_sem_policy_a_filha_herda_a_faixa_do_pai(self) -> None:
        assert resolve_policy(None, BAND) == BAND

    def test_largar_a_regra_do_pai_em_silencio_e_recusado(self) -> None:
        """A direção perigosa: a filha decidiria em **mais** contexto que o pai."""
        parent = {**MORNING, **BAND}
        with pytest.raises(Refused, match="não menciona o portão breadth"):
            resolve_policy("hours=12-15", parent)

    def test_tirar_so_a_faixa_e_uma_frase_do_operador(self) -> None:
        parent = {**MORNING, **BAND}
        assert resolve_policy("hours=12-15,breadth=none", parent) == MORNING

    def test_policy_none_tira_o_portao_inteiro(self) -> None:
        assert resolve_policy("none", BAND) is None
