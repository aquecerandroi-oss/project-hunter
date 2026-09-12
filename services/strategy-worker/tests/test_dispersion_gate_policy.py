"""A regra ``dispersion`` como texto: o corpo gravado, as fronteiras, os sinais.

T3.90 / H-P18. Puro, sem banco: o que este arquivo prova é o **parser** e o
**veredito**, que é onde a regra pode estar errada de um jeito que nenhum
testcontainer pegaria — um limite negativo lido ao contrário, uma faixa fechada no
topo, uma política sem série completada com o padrão do build.

A metade que precisa de Postgres (a barra pulada pelo nome, a âncora exata, a
ordem das quatro regras) está em ``test_dispersion_gate.py``.

Run: ``uv run pytest services/strategy-worker/tests/test_dispersion_gate_policy.py -q``
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest

from hunter_core.strategies.canonical import canonical_json
from hunter_indicators.dispersion import CURRENT_DISPERSION_VERSION
from hunter_strategy_worker.dispersion_gate import (
    REASON_UNAVAILABLE,
    DispersionPolicy,
    DispersionRow,
    dispersion_clause,
    evaluate_dispersion_gate,
    parse_dispersion_policy,
)
from hunter_strategy_worker.gate_policy import PolicyError, parse_policy, policy_argument
from hunter_strategy_worker.variant import policy_note

pytestmark = pytest.mark.unit

CUT = datetime(2026, 9, 11, 12, 15, tzinfo=UTC)
V1 = CURRENT_DISPERSION_VERSION

BAND: dict[str, Any] = {"min": "-0.05", "max": "0.00", "version": V1}
"""A faixa do brief: a discordância leve, meia-aberta no topo."""


def row(value: str | None, *, usable: bool = True, reason: str | None = None) -> DispersionRow:
    return DispersionRow(
        id=uuid.uuid4(),
        end_time=CUT,
        dispersion=None if value is None else Decimal(value),
        usable=usable,
        reason=reason,
        covered=16,
        universe_size=16,
    )


def policy(minimum: str = "-0.05", maximum: str = "0.00") -> DispersionPolicy:
    return parse_dispersion_policy({"min": minimum, "max": maximum, "version": V1})


class TestOCorpoGravado:
    def test_o_corpo_e_tres_campos_com_os_limites_como_string(self) -> None:
        parsed = parse_dispersion_policy(BAND)
        assert parsed.minimum == Decimal("-0.05")
        assert parsed.maximum == Decimal("0.00")
        assert parsed.version == V1
        assert parsed.to_body() == {"max": "0.00", "min": "-0.05", "version": V1}

    def test_o_round_trip_e_byte_a_byte(self) -> None:
        """``Decimal`` guarda o expoente com que foi construído, então a política
        gravada nunca difere da que o operador digitou — inclusive o ``-0.05`` com
        duas casas e o ``0.00`` que não virou ``0``."""
        body = parse_dispersion_policy(BAND).to_body()
        assert parse_dispersion_policy(body).to_body() == body == BAND

    def test_nao_ha_campo_de_horizonte_e_um_a_mais_e_recusado(self) -> None:
        """O horizonte, o universo e a referência vivem **na versão**. Um
        ``horizon_h`` na política seria um botão capaz de reapontar uma célula
        pré-registrada, que é exatamente o que a T3.88 fechou para a amplitude."""
        with pytest.raises(PolicyError, match="unknown field"):
            parse_dispersion_policy({**BAND, "horizon_h": 24})

    def test_uma_politica_sem_versao_e_recusada_nao_completada(self) -> None:
        with pytest.raises(PolicyError, match="missing version"):
            parse_dispersion_policy({"min": "-0.05", "max": "0.00"})

    def test_uma_serie_que_este_build_nao_le_e_recusada(self) -> None:
        with pytest.raises(PolicyError, match="not a series this build reads"):
            parse_dispersion_policy({**BAND, "version": "dispersion_24h_v2"})

    def test_um_limite_numerico_e_recusado_porque_a_forma_canonica_o_mudaria(self) -> None:
        with pytest.raises(PolicyError, match="decimal \\*string\\*"):
            parse_dispersion_policy({**BAND, "min": -0.05})

    def test_a_forma_canonica_preserva_os_limites(self) -> None:
        """``variant.canonical_policy`` emite todo número como string decimal: com
        os limites já em string, o corpo sobrevive à serialização que quebrou a
        regra de horas da T3.59."""
        body = {"dispersion": parse_dispersion_policy(BAND).to_body()}
        assert canonical_json(body).decode("utf-8") == (
            '{"dispersion":{"max":"0.00","min":"-0.05","version":"dispersion_24h_v1"}}'
        )


class TestOsLimitesEAsFaixasVazias:
    def test_min_maior_ou_igual_ao_max_e_recusado(self) -> None:
        with pytest.raises(PolicyError, match="is empty"):
            parse_dispersion_policy({"min": "0.00", "max": "-0.05", "version": V1})
        with pytest.raises(PolicyError, match="is empty"):
            parse_dispersion_policy({"min": "-0.05", "max": "-0.05", "version": V1})

    def test_a_faixa_inteira_e_recusada_porque_nao_recusa_nada(self) -> None:
        with pytest.raises(PolicyError, match="lets every reading through"):
            parse_dispersion_policy({"min": "-1", "max": "1", "version": V1})

    def test_um_limite_fora_de_menos_um_a_mais_um_e_recusado(self) -> None:
        with pytest.raises(PolicyError, match="outside -1..\\+1"):
            parse_dispersion_policy({"min": "-1.5", "max": "0.00", "version": V1})
        with pytest.raises(PolicyError, match="outside -1..\\+1"):
            parse_dispersion_policy({"min": "0.00", "max": "2", "version": V1})

    def test_nan_e_infinito_nao_sao_limites(self) -> None:
        for bad in ("NaN", "Infinity", "-Infinity"):
            with pytest.raises(PolicyError):
                parse_dispersion_policy({"min": bad, "max": "0.00", "version": V1})


class TestAGramaticaDoOperadorComSinal:
    """O ponto do brief: ``partition("-")`` não serve para um limite negativo."""

    def test_a_faixa_do_brief_e_lida_com_os_dois_limites_certos(self) -> None:
        assert dispersion_clause("-0.05-0.00@dispersion_24h_v1") == {
            "max": "0.00",
            "min": "-0.05",
            "version": V1,
        }

    def test_os_dois_limites_negativos_o_braco_a_da_exp_0029(self) -> None:
        """``-0.10--0.03``: quatro ``-`` na mesma string, e o separador é o
        terceiro. Um ``str.partition('-')`` devolveria ``min=''``."""
        assert dispersion_clause("-0.10--0.03") == {
            "max": "-0.03",
            "min": "-0.10",
            "version": V1,
        }

    def test_os_dois_limites_positivos_o_braco_b(self) -> None:
        assert dispersion_clause("0.00-0.10") == {"max": "0.10", "min": "0.00", "version": V1}

    def test_sem_arroba_a_serie_e_a_atual_e_fica_gravada(self) -> None:
        """Resolvida **na derivação** e escrita no corpo: um build posterior não
        relê o padrão dele."""
        assert dispersion_clause("-0.05-0.00")["version"] == V1

    def test_uma_faixa_sem_separador_e_recusada_com_o_exemplo(self) -> None:
        with pytest.raises(PolicyError, match="expected <min>-<max>"):
            dispersion_clause("-0.05")

    def test_uma_faixa_com_tres_numeros_e_recusada(self) -> None:
        with pytest.raises(PolicyError, match="expected <min>-<max>"):
            dispersion_clause("-0.05-0.00-0.10")

    def test_notacao_de_expoente_e_recusada(self) -> None:
        with pytest.raises(PolicyError, match="expected <min>-<max>"):
            dispersion_clause("-5e-2-0.00")

    def test_a_gramatica_da_amplitude_recusa_um_limite_negativo_em_vez_de_ler_errado(
        self,
    ) -> None:
        """O achado que o brief manda checar, travado como teste em vez de escrito
        só num docstring: ``breadth_clause`` parte a faixa em ``str.partition('-')``,
        que para ``-0.05-0.00`` devolveria ``min=''``. Isso **recusa**
        (``Decimal('')`` levanta) em vez de ler errado, e é por isso que a T3.77/T3.88
        fica como foi entregue: os limites dela vivem em ``[0, 1]`` e um negativo já
        era proibido. A gramática com sinal é desta regra, e só dela."""
        from hunter_strategy_worker.breadth_gate import breadth_clause

        with pytest.raises(PolicyError, match="is not a decimal"):
            breadth_clause("-0.05-0.00")
        # e a positiva continua byte a byte o que era
        assert breadth_clause("0.10-0.60")["min"] == "0.10"

    def test_o_envelope_do_operador_aceita_a_regra_ao_lado_das_outras(self) -> None:
        """``policy_clauses`` separa as regras por vírgula e o valor negativo não
        tem vírgula, então o portão inteiro é escrito numa linha."""
        stored = policy_argument("hours=12-15,dispersion=-0.05-0.00@dispersion_24h_v1")
        assert stored == {
            "hours": {"utc": [[12, 15]]},
            "dispersion": {"max": "0.00", "min": "-0.05", "version": V1},
        }

    def test_dispersion_none_tira_so_esta_regra(self) -> None:
        assert policy_argument("hours=12-15,dispersion=none") == {"hours": {"utc": [[12, 15]]}}

    def test_a_nota_da_linhagem_carrega_os_sinais_e_nao_a_serie(self) -> None:
        parsed = parse_policy({"dispersion": BAND})
        assert parsed is not None
        assert policy_note(parsed) == "dispersion=-0.05-0.00"

    def test_as_quatro_regras_juntas_saem_na_ordem_da_avaliacao(self) -> None:
        parsed = parse_policy(
            {
                "regime": {
                    "allow": ["SIDEWAYS"],
                    "classifier_version": "regime_hourly_v1",
                    "rule": "previous_closed_hour",
                    "scope": "btc",
                },
                "hours": {"utc": [[12, 15]]},
                "breadth": {"window_m": 5, "min": "0.10", "max": "0.60", "version": "breadth_v2"},
                "dispersion": BAND,
            }
        )
        assert parsed is not None
        assert policy_note(parsed) == (
            "btc:SIDEWAYS;hours=12-15;breadth=0.10-0.60;dispersion=-0.05-0.00"
        )


class TestOEnvelope:
    def test_a_regra_e_reconhecida_pelo_envelope_e_volta_igual(self) -> None:
        parsed = parse_policy({"dispersion": BAND})
        assert parsed is not None
        assert parsed.dispersion is not None
        assert parsed.regime is None
        assert parsed.hours is None
        assert parsed.breadth is None
        assert parsed.to_jsonable() == {"dispersion": {**BAND}}

    def test_uma_chave_desconhecida_continua_recusada(self) -> None:
        with pytest.raises(PolicyError, match="unknown key"):
            parse_policy({"dispersao": BAND})


class TestOVeredito:
    """A faixa é meia-aberta no topo, e um valor ausente nunca é um zero."""

    def test_o_limite_inferior_entra_e_o_superior_nao(self) -> None:
        assert evaluate_dispersion_gate(policy(), row("-0.050000"), CUT).eligible is True
        assert evaluate_dispersion_gate(policy(), row("0.000000"), CUT).eligible is False

    def test_um_pouco_dentro_de_cada_ponta(self) -> None:
        assert evaluate_dispersion_gate(policy(), row("-0.049999"), CUT).eligible is True
        assert evaluate_dispersion_gate(policy(), row("-0.000001"), CUT).eligible is True
        assert evaluate_dispersion_gate(policy(), row("-0.050001"), CUT).eligible is False

    def test_o_motivo_por_valor_arredonda_para_duas_casas_com_sinal(self) -> None:
        """O caso do brief: uma barra com dispersão -0,08 é recusada **pelo nome**."""
        gate = evaluate_dispersion_gate(policy(), row("-0.080000"), CUT)
        assert gate.eligible is False
        assert gate.detail == "refused"
        assert gate.reason == "dispersion_gate:-0.08"

    def test_duas_recusas_proximas_caem_no_mesmo_balde_do_histograma(self) -> None:
        first = evaluate_dispersion_gate(policy(), row("-0.081234"), CUT)
        second = evaluate_dispersion_gate(policy(), row("-0.084000"), CUT)
        assert first.reason == second.reason == "dispersion_gate:-0.08"
        # ...e o valor exato sobrevive no envelope, que é onde ele tem de ser exato
        assert first.to_jsonable()["value"] == "-0.081234"

    def test_uma_dispersao_positiva_tambem_e_recusada_pelo_nome(self) -> None:
        assert evaluate_dispersion_gate(policy(), row("0.070000"), CUT).reason == (
            "dispersion_gate:0.07"
        )

    def test_sem_linha_a_versao_emudece(self) -> None:
        gate = evaluate_dispersion_gate(policy(), None, CUT)
        assert gate.eligible is False
        assert gate.detail == "no_row"
        assert gate.reason == REASON_UNAVAILABLE
        assert gate.value is None
        assert gate.end_time is None

    def test_uma_linha_inutilizavel_carrega_o_motivo_do_produtor(self) -> None:
        """Duas palavras, dois problemas de operação — e o portão não inventa um
        segundo diagnóstico do que o produtor já nomeou."""
        for series_reason in ("insufficient_coverage", "btc_missing", "no_alts", "empty_universe"):
            gate = evaluate_dispersion_gate(
                policy(), row(None, usable=False, reason=series_reason), CUT
            )
            assert gate.reason == REASON_UNAVAILABLE
            assert gate.detail == "unusable"
            assert gate.series_reason == series_reason

    def test_o_envelope_publica_o_valor_exato_a_linha_e_a_faixa(self) -> None:
        source = row("-0.033000")
        gate = evaluate_dispersion_gate(policy(), source, CUT)
        assert gate.to_jsonable() == {
            "eligible": True,
            "value": "-0.033000",
            "row_id": str(source.id),
            "end_time": CUT.isoformat(),
            "detail": "allowed",
            "series_reason": None,
            "policy": {"max": "0.00", "min": "-0.05", "version": V1},
        }
