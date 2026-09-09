"""Oráculo da T3.66 / EXP-0024 — séries sintéticas com valor esperado conhecido.

Duas famílias de prova:

1. **o estimador** (`blocos.py`) — o ponto é a média; com uma observação por dia o
   bootstrap de blocos degenera no bootstrap ordinário e tem de concordar dígito a
   dígito com o cálculo direto; diferença constante dá IC degenerado e ``p`` no piso;
   Holm é monótono e multiplica pelo posto;
2. **o controle** (`controle.py`) — a dobra de 15 min recusa balde incompleto, o
   sinal separa doji, a janela recusa buraco em vez de pular minuto, o plano do
   controle reproduz **exatamente** o plano da decisão quando a barra é a mesma
   (a degenerescência que o EXP-0024 declara antes de medir), e o R sai da mesma
   aritmética de ``settle`` — com um caso de stop e um de alvo cujo R é conhecido
   à mão.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
import pytest
from blocos import holm, media_por_blocos
from controle import CUSTOS, Serie, caminhar, plano_do_controle, r_sem_funding, sinal, utc

T0 = datetime(2026, 8, 20, 12, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------- estimador


def test_ponto_e_a_media_simples() -> None:
    obs = [("d1", 1.0), ("d1", 3.0), ("d2", -1.0), ("d2", 1.0)]
    e = media_por_blocos(obs, reamostragens=2000, seed=7)
    assert e.n == 4
    assert e.dias == 2
    assert e.ponto == pytest.approx(1.0)


def test_valor_constante_da_ic_degenerado_e_p_no_piso() -> None:
    obs = [(f"d{i}", 0.25) for i in range(12)]
    e = media_por_blocos(obs, reamostragens=1000, seed=11)
    assert e.ponto == pytest.approx(0.25)
    assert e.ic95 == (pytest.approx(0.25), pytest.approx(0.25))
    assert e.p_bicaudal == pytest.approx(2.0 / 1000)


def test_uma_observacao_por_dia_concorda_com_o_bootstrap_ordinario() -> None:
    rng = np.random.default_rng(2026)
    valores = rng.normal(0.1, 1.0, size=40)
    obs = [(f"d{i:02d}", float(x)) for i, x in enumerate(valores)]
    e = media_por_blocos(obs, reamostragens=5000, seed=99)

    r2 = np.random.default_rng(99)
    idx = np.arange(40)
    direto = np.array([valores[r2.choice(idx, size=40, replace=True)].mean() for _ in range(5000)])
    assert e.ponto == pytest.approx(float(valores.mean()))
    assert e.ic95[0] == pytest.approx(float(np.percentile(direto, 2.5)), abs=1e-12)
    assert e.ic95[1] == pytest.approx(float(np.percentile(direto, 97.5)), abs=1e-12)


def test_amostra_vazia_e_nan_nunca_zero() -> None:
    e = media_por_blocos([], reamostragens=10)
    assert e.n == 0
    assert np.isnan(e.ponto)


def test_holm_e_monotono_e_multiplica_pelo_posto() -> None:
    ajust = holm({"a": 0.01, "b": 0.04})
    assert ajust["a"] == pytest.approx(0.02)
    assert ajust["b"] == pytest.approx(0.04)
    assert ajust["a"] <= ajust["b"]


# ---------------------------------------------------------------- controle


def _serie_plana(n: int, inicio: datetime = T0, preco: float = 100.0) -> Serie:
    s = Serie()
    for k in range(n):
        s.adicionar(inicio + timedelta(minutes=k), preco, preco, preco, preco)
    return s


def test_balde_de_15_min_exige_os_quinze_minutos() -> None:
    s = _serie_plana(15)
    assert s.balde15(T0 + timedelta(minutes=15)) is not None
    s2 = Serie()
    for k in range(15):
        if k == 7:
            continue  # um minuto ausente no meio
        s2.adicionar(T0 + timedelta(minutes=k), 100.0, 100.0, 100.0, 100.0)
    assert s2.balde15(T0 + timedelta(minutes=15)) is None


def test_o_balde_le_a_abertura_do_primeiro_minuto_e_o_fechamento_do_ultimo() -> None:
    s = Serie()
    for k in range(15):
        s.adicionar(T0 + timedelta(minutes=k), 10.0 + k, 20.0, 1.0, 11.0 + k)
    b = s.balde15(T0 + timedelta(minutes=15))
    assert b is not None
    assert b.abertura == pytest.approx(10.0)  # abertura do minuto 0
    assert b.fechamento == pytest.approx(25.0)  # fechamento do minuto 14
    assert sinal(b) == 1


def test_sinal_separa_doji_de_baixa_e_de_alta() -> None:
    from controle import Barra15

    assert sinal(Barra15(T0, 10.0, 9.0)) == -1
    assert sinal(Barra15(T0, 10.0, 11.0)) == 1
    assert sinal(Barra15(T0, 10.0, 10.0)) == 0


def test_janela_recusa_buraco_em_vez_de_pular_minuto() -> None:
    s = _serie_plana(10)
    assert s.janela(T0, 10) is not None
    assert s.janela(T0, 11) is None  # o 11o minuto não existe


def test_o_controle_na_mesma_barra_reproduz_o_plano_da_decisao() -> None:
    """A degenerescência declarada no EXP-0024, provada em aritmética.

    Com ``risco_pct`` e ``tr`` derivados da decisão e a **mesma** abertura, o plano
    do controle é o plano da decisão dígito a dígito. É por isso que C1 não pode ser
    lido como "edge incremental" nas barras em que ele dispara.
    """
    abertura = Decimal("100")
    from hunter_strategy_worker.pricing import entry_price

    p_entry = entry_price(abertura, CUSTOS)
    stop = p_entry - Decimal("2")
    alvo = p_entry + Decimal("3")
    risco = p_entry - stop
    plano = plano_do_controle(
        entrada=T0,
        abertura=abertura,
        risco_pct=risco / p_entry,
        tr=(alvo - p_entry) / risco,
        horizonte_s=14400,
    )
    assert plano.stop == pytest.approx(stop)
    assert plano.target1 == pytest.approx(alvo)


def test_stop_intrabarra_da_r_conhecido() -> None:
    """Entrada a 100 (×1,0006), stop 1 % abaixo, alvo 1,5 %: a barra seguinte fura o stop."""
    s = Serie()
    s.adicionar(T0, 100.0, 100.0, 100.0, 100.0)  # barra de entrada, inofensiva
    s.adicionar(T0 + timedelta(minutes=1), 100.0, 100.0, 98.0, 98.5)  # fura o stop
    plano = plano_do_controle(
        entrada=T0,
        abertura=Decimal("100"),
        risco_pct=Decimal("0.01"),
        tr=Decimal("1.5"),
        horizonte_s=14400,
    )
    velas = s.janela(T0, 2)
    assert velas is not None
    prog = caminhar(plano, velas)
    assert prog.result.value == "stop"
    assert prog.exit_base == plano.stop
    r = r_sem_funding(plano, prog)
    assert r is not None
    # R = ((stop*(1-6e-4) - P) - 4e-4*P - 4e-4*stop*(1-6e-4)) / (P - stop) com P = 100,06
    p = Decimal("100") * (Decimal(1) + Decimal("6") / Decimal("10000"))
    stop = p * (Decimal(1) - Decimal("0.01"))
    saida = stop * (Decimal(1) - Decimal("6") / Decimal("10000"))
    esperado = (saida - p - Decimal("0.0004") * p - Decimal("0.0004") * saida) / (p - stop)
    assert float(r) == pytest.approx(float(esperado), abs=1e-12)
    assert float(r) < -1.0  # o pedágio de 20 bps faz o stop custar mais que 1 R


def test_alvo_no_aberto_nao_credita_acima_do_alvo() -> None:
    plano = plano_do_controle(
        entrada=T0,
        abertura=Decimal("100"),
        risco_pct=Decimal("0.01"),
        tr=Decimal("1.5"),
        horizonte_s=14400,
    )
    s = Serie()
    s.adicionar(T0, 100.0, 100.0, 100.0, 100.0)
    s.adicionar(T0 + timedelta(minutes=1), 200.0, 210.0, 199.0, 205.0)  # gap gigante a favor
    velas = s.janela(T0, 2)
    assert velas is not None
    prog = caminhar(plano, velas)
    assert prog.result.value == "target"
    assert prog.exit_base == plano.target1  # crédito limitado ao alvo, nunca ao aberto


def test_horizonte_expira_no_aberto_da_barra_do_horizonte() -> None:
    plano = plano_do_controle(
        entrada=T0,
        abertura=Decimal("100"),
        risco_pct=Decimal("0.5"),  # stop longe: nada dispara
        tr=Decimal("1.5"),
        horizonte_s=600,  # 10 minutos
    )
    s = _serie_plana(12)
    velas = s.janela(T0, 12)
    assert velas is not None
    prog = caminhar(plano, velas)
    assert prog.result.value == "expired"
    assert prog.exit_ts == T0 + timedelta(minutes=10)


def test_utc_le_o_carimbo_do_csv() -> None:
    assert utc("2026-09-08T20:00:00Z") == datetime(2026, 9, 8, 20, 0, tzinfo=timezone.utc)
