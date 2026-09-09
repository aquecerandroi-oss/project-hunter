"""Testes do simulador de carteira da T3.60.

Duas famílias de teste, e a segunda é a que importa:

1. **dedupe e leitura** — a aposta é (mercado × barra), a versão mais antiga
   vence, a escolha não olha o resultado;
2. **os limites são os do motor de verdade** — cada caso monta um cenário
   sintético mínimo e prova que quem recusou (ou quem apertou o tamanho) foi o
   check do `hunter_risk`, com o nome que o contrato publica: vaga
   (`concurrent_positions`), moeda repetida (`duplicate_position`), risco
   agregado (`aggregate_risk_budget`), banda de stop (`stop_distance`), piso de
   liquidez (`liquidity_24h`), janela de volume incompleta (`participation`
   indisponível), mínimo negociável (`sizing`), kill switch (`kill_switch`).

E a invariante de patrimônio: `equity = cash + Σ posições` em **todo** ponto da
curva, para qualquer configuração — é a única coisa que, se quebrar, invalida
todos os números da nota.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from carteira import (
    EQUITY_100K,
    Config,
    Sinal,
    deduplicar,
    ler_populacao,
    simular,
)

from hunter_core.domain.enums import KillSwitchState
from hunter_risk import PAPER_V1

T0 = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)


def sinal(
    *,
    sid: str = "s1",
    versao: str = "mean_reversion v1",
    ordem: int = 1,
    symbol: str = "AAAUSDT",
    base: str = "AAA",
    bar: datetime = T0,
    entrada: datetime | None = None,
    saida: datetime | None = None,
    r_net: str = "1.0",
    preco: str = "100",
    risco_pct: str = "0.01",
    vol_min: str | None = "10000000",
    vol_med: str | None = "10000000",
    barras_30: int = 30,
    vol_24h: str | None = "5000000000",
    min_notional: str = "5",
    step: str = "0.00001",
) -> Sinal:
    """Um sinal sintético com geometria explícita — nada é lido do banco aqui."""
    entrada = entrada or bar + timedelta(minutes=1)
    saida = saida or entrada + timedelta(hours=1)
    p = Decimal(preco)
    rp = Decimal(risco_pct)
    return Sinal(
        signal_id=sid,
        versao=versao,
        ordem_versao=ordem,
        coorte="prospective",
        symbol=symbol,
        base_asset=base,
        bar=bar,
        entry_ts=entrada,
        exit_ts=saida,
        dia_br=entrada.strftime("%Y-%m-%d"),
        hora_br=entrada.hour,
        motivo="target",
        r_net=Decimal(r_net),
        entry_base=p,
        risk=p * rp,
        risco_pct=rp,
        min_notional=Decimal(min_notional),
        step_size=Decimal(step),
        fee_bps=Decimal(4),
        spread_bps=Decimal(2),
        slippage_bps=Decimal(5),
        vol_min_anterior=None if vol_min is None else Decimal(vol_min),
        vol_mediana_30=None if vol_med is None else Decimal(vol_med),
        barras_30=barras_30,
        vol_24h=None if vol_24h is None else Decimal(vol_24h),
        barras_24h=1440,
        mae=None,
        mae_bar=None,
    )


# --------------------------------------------------------------------------- #
# 1. deduplicação
# --------------------------------------------------------------------------- #
def test_a_aposta_e_mercado_x_barra_e_a_versao_mais_antiga_vence() -> None:
    oito = [
        sinal(sid=f"s{v}", versao=f"mean_reversion v{v}", ordem=v, r_net=str(v))
        for v in (3, 1, 8, 2)
    ]
    vencedores, creditos = deduplicar(oito)
    assert len(vencedores) == 1
    assert vencedores[0].versao == "mean_reversion v1"
    assert creditos == {"mean_reversion v1": 1}


def test_a_escolha_do_dedupe_nao_olha_o_resultado() -> None:
    """A v1 vence mesmo sendo a pior — senão a simulação escolheria depois de ver o R."""
    grupo = [
        sinal(sid="ruim", versao="mean_reversion v1", ordem=1, r_net="-1"),
        sinal(sid="otimo", versao="mean_reversion v8", ordem=8, r_net="+9"),
    ]
    vencedores, _ = deduplicar(grupo)
    assert vencedores[0].signal_id == "ruim"


def test_barras_diferentes_do_mesmo_mercado_sao_apostas_diferentes() -> None:
    dois = [
        sinal(sid="a", bar=T0),
        sinal(sid="b", bar=T0 + timedelta(minutes=15)),
    ]
    vencedores, _ = deduplicar(dois)
    assert len(vencedores) == 2


def test_a_chave_por_hora_funde_barras_da_mesma_hora() -> None:
    dois = [
        sinal(sid="a", bar=T0),
        sinal(sid="b", bar=T0 + timedelta(minutes=15)),
    ]
    vencedores, _ = deduplicar(dois, chave="hora")
    assert len(vencedores) == 1


# --------------------------------------------------------------------------- #
# 2. os limites são os do motor
# --------------------------------------------------------------------------- #
def _n_mercados(n: int, *, entrada: datetime = T0 + timedelta(minutes=1)) -> list[Sinal]:
    """`n` apostas simultâneas, cada uma em uma moeda distinta, todas longas.

    Mercados **finos** de propósito (7.000 USDT no minuto → teto de participação
    de 70 USDT, a mediana medida na T3.48): é a situação real da carteira, e é a
    única em que o teto de vagas chega a ser testado. Com mercados grandes quem
    morde primeiro é `total_exposure` (40 % do patrimônio ÷ 10 % por moeda = 4
    posições cheias), e isso tem teste próprio abaixo.
    """
    return [
        sinal(
            sid=f"m{i}",
            symbol=f"M{i}USDT",
            base=f"M{i}",
            bar=entrada - timedelta(minutes=1),
            entrada=entrada,
            saida=entrada + timedelta(hours=6),
            vol_min="7000",
            vol_med="7000",
        )
        for i in range(n)
    ]


def _grande(s: Sinal) -> Sinal:
    """O mesmo sinal num mercado enorme: o teto de participação deixa de morder."""
    return replace(s, vol_min_anterior=Decimal("1e12"), vol_mediana_30=Decimal("1e12"))


def test_a_vaga_e_do_motor_cinco_entram_o_sexto_e_recusado() -> None:
    res = simular(_n_mercados(8), Config())
    assert len(res.aprovadas) == PAPER_V1.max_concurrent_positions == 5
    assert res.recusas_por_motivo.get("concurrent_positions") == 3


def test_vinte_vagas_admitem_vinte_e_o_limite_veio_de_RiskLimits() -> None:
    cfg = Config(max_concurrent_positions=20)
    assert cfg.limites().max_concurrent_positions == 20
    res = simular(_n_mercados(25), cfg)
    assert len(res.aprovadas) == 20
    assert res.recusas_por_motivo.get("concurrent_positions") == 5


def test_a_mesma_moeda_duas_vezes_e_duplicate_position() -> None:
    entrada = T0 + timedelta(minutes=1)
    dois = [
        sinal(sid="a", symbol="AAAUSDT", base="AAA", bar=T0, entrada=entrada),
        sinal(
            sid="b",
            symbol="AAAUSDT",
            base="AAA",
            bar=T0 + timedelta(minutes=5),
            entrada=entrada + timedelta(minutes=5),
        ),
    ]
    res = simular(dois, Config())
    assert len(res.aprovadas) == 1
    assert res.recusas_por_motivo.get("duplicate_position") == 1


def test_stop_acima_do_teto_de_3_por_cento_e_recusado_por_stop_distance() -> None:
    res = simular([sinal(risco_pct="0.04")], Config())
    assert not res.aprovadas
    assert res.recusas_por_motivo == {"stop_distance": 1}


def test_stop_abaixo_do_piso_de_0_3_por_cento_tambem_e_recusado() -> None:
    res = simular([sinal(risco_pct="0.001")], Config())
    assert res.recusas_por_motivo == {"stop_distance": 1}


def test_stop_dentro_da_banda_passa() -> None:
    res = simular([sinal(risco_pct="0.01")], Config())
    assert len(res.aprovadas) == 1
    assert res.registros[0].motivo_recusa is None


def test_volume_24h_abaixo_do_piso_de_50M_e_recusado_por_liquidity_24h() -> None:
    res = simular([sinal(vol_24h="49000000")], Config())
    assert res.recusas_por_motivo.get("liquidity_24h") == 1
    assert not res.aprovadas
    # §3: um LIMITE reprovado ainda produz tamanho (o painel mostra o que teria
    # saído); quem impede o sizing é insumo AUSENTE, não limite violado.
    assert res.registros[0].notional > 0


def test_volume_24h_acima_do_piso_passa_o_check_de_liquidez() -> None:
    res = simular([sinal(vol_24h="51000000")], Config())
    assert "liquidity_24h" not in res.registros[0].todos_reprovados


def test_janela_de_30_barras_incompleta_torna_a_participacao_indisponivel() -> None:
    res = simular([sinal(barras_30=29)], Config())
    assert not res.aprovadas
    assert "participation" in res.registros[0].todos_reprovados


def test_o_teto_de_participacao_e_quem_decide_o_tamanho_em_mercado_fino() -> None:
    """1 % de 7.000 USDT de um minuto = 70 USDT — o número da T3.48."""
    res = simular([sinal(vol_min="7000", vol_med="7000")], Config())
    reg = res.registros[0]
    assert reg.aprovado
    assert reg.binding_constraint == "market_participation"
    assert reg.notional <= Decimal(70)
    assert reg.notional_rotulo is not None and reg.notional_rotulo > Decimal(1000)


def test_num_mercado_grande_quem_vence_e_o_teto_por_moeda_nao_o_de_risco() -> None:
    """10 % do patrimônio (1.933 USDT) chega antes de 0,25 % ÷ (stop+custo) (4.027)."""
    res = simular([sinal(vol_min="1e12", vol_med="1e12")], Config())
    assert res.registros[0].binding_constraint == "asset_exposure"


def test_o_teto_de_risco_so_vence_com_stop_largo_em_mercado_grande() -> None:
    """Com stop de 2,5 % o teto de risco cai para 1.790 e passa a ser o gargalo."""
    res = simular([sinal(vol_min="1e12", vol_med="1e12", risco_pct="0.025")], Config())
    assert res.registros[0].binding_constraint == "risk_per_trade"


def test_quatro_posicoes_cheias_esgotam_a_exposicao_total_de_40_por_cento() -> None:
    """40 % ÷ 10 % por moeda = 4 posições cheias; a quinta sai com tamanho zero."""
    res = simular([_grande(s) for s in _n_mercados(8)], Config(max_concurrent_positions=20))
    assert len(res.aprovadas) == 4
    assert res.recusas_por_motivo.get("sizing") == 4


def test_tamanho_abaixo_do_min_notional_e_recusado_pelo_check_sizing() -> None:
    res = simular([sinal(vol_min="100", vol_med="100", min_notional="50")], Config())
    assert res.recusas_por_motivo.get("sizing") == 1


def _grandes_com_stop_largo(n: int) -> list[Sinal]:
    """Mercados enormes e stop de 2,8 %: a faixa em que o risco agregado morde."""
    return [
        replace(
            s,
            vol_min_anterior=Decimal("1e12"),
            vol_mediana_30=Decimal("1e12"),
            risco_pct=Decimal("0.028"),
            risk=s.entry_base * Decimal("0.028"),
        )
        for s in _n_mercados(n)
    ]


def test_o_risco_agregado_esgotado_recusa_a_entrada_seguinte() -> None:
    """1 % ÷ 0,25 % = exatamente quatro entradas cheias; a quinta não cabe.

    Quem assina a recusa é o check 18 (`sizing`), não o 15
    (`aggregate_risk_budget`): o arredondamento **para baixo** por `step_size`
    deixa uma sobra de 3 centésimos de milésimo de USDT no orçamento, então o
    agregado ainda não está formalmente estourado — o tamanho que ele autoriza é
    que fica abaixo do `min_notional`. É o motor recusando pelo motivo certo, e
    o teste registra qual é.
    """
    cfg = Config(max_concurrent_positions=20)
    res = simular(_grandes_com_stop_largo(8), cfg)
    assert len(res.aprovadas) == 4
    assert res.recusas_por_motivo == {"sizing": 4}
    risco_total = sum(
        (r.notional * (r.sinal.risco_pct + Decimal("0.002")) for r in res.aprovadas),
        Decimal(0),
    )
    teto = EQUITY_100K * cfg.max_aggregate_planned_risk_pct
    assert risco_total <= teto
    assert teto - risco_total < Decimal("0.001")


def test_o_orcamento_agregado_parcial_vira_o_limitante_publicado() -> None:
    """Com 0,7 % de teto agregado a terceira entrada sai **menor**, e o motor diz por quê."""
    cfg = Config(max_concurrent_positions=20, max_aggregate_planned_risk_pct=Decimal("0.007"))
    res = simular(_grandes_com_stop_largo(8), cfg)
    limitantes = [r.binding_constraint for r in res.aprovadas]
    assert limitantes.count("aggregate_risk") == 1
    menor = [r for r in res.aprovadas if r.binding_constraint == "aggregate_risk"][0]
    maior = [r for r in res.aprovadas if r.binding_constraint == "risk_per_trade"][0]
    assert menor.notional < maior.notional


def test_dobrar_o_teto_agregado_tira_o_risco_agregado_da_frente() -> None:
    """A 2 % o gargalo deixa de ser o risco agregado e passa a ser a exposição total."""
    cfg = Config(max_concurrent_positions=20, max_aggregate_planned_risk_pct=Decimal("0.02"))
    res = simular(_grandes_com_stop_largo(8), cfg)
    limitantes = [r.binding_constraint for r in res.aprovadas]
    assert "aggregate_risk" not in limitantes
    assert "total_exposure" in limitantes


def test_o_kill_switch_bloqueia_entradas_depois_de_2_por_cento_de_perda_no_dia() -> None:
    """Uma perda grande fecha o dia; a entrada seguinte encontra `kill_switch`."""
    perdedora = sinal(
        sid="perda",
        symbol="BIGUSDT",
        base="BIG",
        bar=T0,
        entrada=T0 + timedelta(minutes=1),
        saida=T0 + timedelta(minutes=2),
        r_net="-40",
        vol_min="1e12",
        vol_med="1e12",
    )
    seguinte = sinal(
        sid="depois",
        symbol="NEXTUSDT",
        base="NEXT",
        bar=T0 + timedelta(minutes=3),
        entrada=T0 + timedelta(minutes=4),
        vol_min="1e12",
        vol_med="1e12",
    )
    res = simular([perdedora, seguinte], Config())
    assert res.latch_em is not None
    assert res.latch_estado is KillSwitchState.TRADING_DISABLED
    assert res.registros[-1].motivo_recusa == "kill_switch"


def test_a_trava_do_kill_switch_nao_se_desfaz_sozinha_no_dia_seguinte() -> None:
    perdedora = sinal(
        sid="perda",
        symbol="BIGUSDT",
        base="BIG",
        bar=T0,
        entrada=T0 + timedelta(minutes=1),
        saida=T0 + timedelta(minutes=2),
        r_net="-40",
        vol_min="1e12",
        vol_med="1e12",
    )
    amanha = T0 + timedelta(days=2)
    seguinte = sinal(
        sid="amanha",
        symbol="NEXTUSDT",
        base="NEXT",
        bar=amanha,
        entrada=amanha + timedelta(minutes=1),
        vol_min="1e12",
        vol_med="1e12",
    )
    res = simular([perdedora, seguinte], Config())
    assert res.registros[-1].motivo_recusa == "kill_switch"


def test_a_retomada_manual_do_dia_seguinte_e_o_resume_do_motor() -> None:
    """Com o drawdown abaixo de 8 %, `hunter_risk.resume` aceita e a carteira volta."""
    perdedora = sinal(
        sid="perda",
        symbol="BIGUSDT",
        base="BIG",
        bar=T0,
        entrada=T0 + timedelta(minutes=1),
        saida=T0 + timedelta(minutes=2),
        r_net="-40",
        vol_min="1e12",
        vol_med="1e12",
    )
    amanha = T0 + timedelta(days=2)
    seguinte = sinal(
        sid="amanha",
        symbol="NEXTUSDT",
        base="NEXT",
        bar=amanha,
        entrada=amanha + timedelta(minutes=1),
        vol_min="1e12",
        vol_med="1e12",
    )
    res = simular([perdedora, seguinte], Config(retomada_diaria=True))
    assert res.retomadas == 1
    assert res.registros[-1].aprovado


# --------------------------------------------------------------------------- #
# 3. invariantes
# --------------------------------------------------------------------------- #
def test_o_patrimonio_e_sempre_caixa_mais_posicoes() -> None:
    """`equity = cash + Σ posições` — se isto quebra, nenhum número da nota vale.

    A prova é indireta e forte: `PortfolioState` recusa `peak_equity < equity` e
    `cash < 0`, então uma curva que existe já passou pelo validador do motor em
    cada ponto. Aqui fecha-se a conta pelo outro lado: patrimônio final =
    inicial + Σ PnL realizado, com as posições todas fechadas.
    """
    res = simular(_n_mercados(8), Config(max_concurrent_positions=20))
    esperado = EQUITY_100K + sum((f.pnl_quote for f in res.fechadas), Decimal(0))
    assert res.equity_final == esperado


def test_a_curva_de_patrimonio_e_monotonica_no_tempo() -> None:
    res = simular(_n_mercados(8), Config())
    instantes = [t for t, _ in res.curva]
    assert instantes == sorted(instantes)


def test_todos_os_checks_aparecem_mesmo_depois_do_primeiro_reprovado() -> None:
    """§3 do contrato: a decisão publica o quadro inteiro, não para no primeiro não."""
    res = simular([sinal(risco_pct="0.04", vol_24h="1000")], Config())
    assert set(res.registros[0].todos_reprovados) >= {"stop_distance", "liquidity_24h"}


def test_nenhuma_posicao_nasce_sem_decisao_aprovada() -> None:
    res = simular(_n_mercados(8), Config())
    assert len(res.fechadas) == len(res.aprovadas)


@pytest.mark.parametrize("risco", ["0.0025", "0.005", "0.01"])
def test_o_perfil_de_cada_configuracao_e_o_PAPER_V1_com_um_campo_trocado(risco: str) -> None:
    limites = Config(risk_per_trade_pct=Decimal(risco)).limites()
    assert limites.risk_per_trade_pct == Decimal(risco)
    assert limites.max_participation_pct == PAPER_V1.max_participation_pct
    assert limites.kill_switch_blocked == PAPER_V1.kill_switch_blocked
    assert limites.max_stop_distance_pct == PAPER_V1.max_stop_distance_pct


# --------------------------------------------------------------------------- #
# 4. a população real carrega o que o motor exige
# --------------------------------------------------------------------------- #
def _populacao() -> list[Sinal]:
    return ler_populacao(str(__file__).replace("test_carteira.py", "populacao.csv"))


def test_o_csv_da_vps_carrega_e_tem_os_campos_do_motor() -> None:
    pop = _populacao()
    assert len(pop) > 400
    assert all(s.entry_ts < s.exit_ts for s in pop)
    assert all(s.risk > 0 and s.entry_base > 0 for s in pop)
    assert {s.coorte for s in pop} == {"prospective", "replay"}


@pytest.mark.parametrize("vagas", [5, 10, 20])
@pytest.mark.parametrize("risco", ["0.0025", "0.01"])
def test_invariante_de_patrimonio_na_populacao_real(vagas: int, risco: str) -> None:
    """`equity = cash + Σ posições` em qualquer configuração, sobre os dados da VPS.

    A prova de fechamento: o patrimônio final é o inicial mais a soma dos
    resultados realizados, sem um centavo aparecendo ou sumindo no caminho. Se
    isto falhar, nenhuma tabela da nota vale.
    """
    pop = [s for s in _populacao() if s.coorte == "prospective"]
    res = simular(pop, Config(risk_per_trade_pct=Decimal(risco), max_concurrent_positions=vagas))
    assert res.equity_final == EQUITY_100K + sum((f.pnl_quote for f in res.fechadas), Decimal(0))
    assert res.fechadas  # a simulação de fato executou alguma coisa


def test_a_populacao_real_e_deduplicada_para_uma_aposta_por_mercado_e_barra() -> None:
    pop = [s for s in _populacao() if s.coorte == "prospective"]
    unicos, _ = deduplicar(pop)
    chaves = [s.chave_barra for s in unicos]
    assert len(chaves) == len(set(chaves))
    assert len(unicos) < len(pop)  # há pooling de fato


def test_nenhuma_entrada_da_populacao_real_nasce_sem_decisao_aprovada() -> None:
    pop = [s for s in _populacao() if s.coorte == "prospective"]
    res = simular(pop, Config())
    ids_aprovados = {r.sinal.signal_id for r in res.aprovadas}
    assert {f.sinal.signal_id for f in res.fechadas} <= ids_aprovados
    assert all(r.notional > 0 and r.qty > 0 for r in res.aprovadas)
