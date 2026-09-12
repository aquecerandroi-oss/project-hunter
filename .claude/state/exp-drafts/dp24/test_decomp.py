"""D-P24 — testes da aritmetica da decomposicao, com valores calculados a mao.

TDD: este arquivo existiu antes de `decomp.py` (a primeira passada foi
`ModuleNotFoundError`). Nenhum teste aqui le banco, rede ou relogio: as series
sao sinteticas e o valor esperado esta escrito na propria linha do assert.

Os seis blocos:
  1. vocabulario do motivo de saida (`signal_outcomes.result` -> brief);
  2. contribuicao por grupo e a IDENTIDADE (as contribuicoes recompoem a media
     total) -- o que a Astra exigiu no MUST-FIX 1;
  3. decis superior/inferior (MUST-FIX 3: "cauda" e leitura a confirmar);
  4. bootstrap de blocos de dia CONJUNTO (a mesma reamostragem para todos os
     grupos) e a equivalencia com `blocos90.ic_media` num grupo so;
  5. excursoes de closes, janelas antes/depois da saida e ANTI-ANTECIPACAO
     (uma vela nao final mudando nao muda a leitura);
  6. o Delta pareado e as duas unidades (ATR e % do preco).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from decomp import (
    MOTIVOS,
    Vela,
    bootstrap_conjunto,
    contribuicao,
    contribuicao_decil,
    decompoe,
    delta_por_decisao,
    janela_de_closes,
    mfe_mae_closes,
    motivo_canonico,
    ret_pct,
    tamanho_do_decil,
)

# ---------------------------------------------------------------- 1. motivo


def test_o_vocabulario_do_brief_mapeia_os_quatro_terminais_conhecidos():
    assert motivo_canonico("stop", "terminal") == "stop"
    assert motivo_canonico("target", "terminal") == "target"
    assert motivo_canonico("expired", "terminal") == "time-stop"
    assert motivo_canonico("invalidated", "terminal") == "context-lost"


def test_tudo_que_nao_e_terminal_conhecido_cai_em_other_e_nunca_some():
    assert motivo_canonico("open", "no_entry") == "other"
    assert motivo_canonico("open", "censored") == "other"
    assert motivo_canonico("open", "active") == "other"
    assert motivo_canonico("", "") == "other"
    # um result terminal desconhecido (enum novo no futuro) tambem e `other`,
    # nunca um grupo inventado nem uma linha descartada em silencio
    assert motivo_canonico("trailing_stop", "terminal") == "other"


def test_a_ordem_dos_grupos_e_congelada_e_inclui_other():
    assert MOTIVOS == ("stop", "target", "time-stop", "context-lost", "other")


# ------------------------------------------------- 2. contribuicao e identidade


def test_contribuicao_e_soma_do_grupo_sobre_o_N_TOTAL_nao_sobre_o_n_do_grupo():
    # stop: -1 -2 +3  soma 0 ; target: +2 +4 soma 6 ; time-stop: +5 soma 5
    # N total = 6 -> contribuicoes 0/6, 6/6, 5/6
    assert contribuicao(np.array([-1.0, -2.0, 3.0]), n_total=6) == pytest.approx(0.0)
    assert contribuicao(np.array([2.0, 4.0]), n_total=6) == pytest.approx(1.0)
    assert contribuicao(np.array([5.0]), n_total=6) == pytest.approx(5.0 / 6.0)


def test_as_contribuicoes_recompoem_a_media_total_a_identidade_do_mustfix_1():
    dias = ["d1", "d1", "d2", "d2", "d3", "d3"]
    motivos = ["stop", "stop", "stop", "target", "target", "time-stop"]
    valores = np.array([-1.0, -2.0, 3.0, 2.0, 4.0, 5.0])
    grupos, total = decompoe(dias, motivos, valores, reamostragens=0)
    assert total.n == 6
    assert total.media == pytest.approx(11.0 / 6.0)  # (-1-2+3+2+4+5)/6
    soma_contrib = sum(g.contribuicao for g in grupos.values())
    assert soma_contrib == pytest.approx(total.media, abs=1e-12)
    assert grupos["stop"].contribuicao == pytest.approx(0.0)
    assert grupos["target"].contribuicao == pytest.approx(1.0)
    assert grupos["time-stop"].contribuicao == pytest.approx(5.0 / 6.0)


def test_grupo_ausente_tem_n_zero_contribuicao_zero_e_media_NAN_nunca_zero():
    dias = ["d1", "d1"]
    motivos = ["stop", "stop"]
    valores = np.array([1.0, 3.0])
    grupos, total = decompoe(dias, motivos, valores, reamostragens=0)
    vazio = grupos["context-lost"]
    assert vazio.n == 0 and vazio.dias == 0
    assert vazio.contribuicao == 0.0          # soma de conjunto vazio e zero
    assert math.isnan(vazio.media)            # media de conjunto vazio NAO e zero
    assert math.isnan(vazio.mediana)
    assert grupos["stop"].media == pytest.approx(2.0)
    assert total.media == pytest.approx(2.0)


def test_n_e_dias_por_grupo_contam_decisoes_e_dias_DISTINTOS():
    dias = ["d1", "d1", "d2", "d3"]
    motivos = ["stop", "stop", "stop", "target"]
    valores = np.array([1.0, 1.0, 1.0, 9.0])
    grupos, total = decompoe(dias, motivos, valores, reamostragens=0)
    assert (grupos["stop"].n, grupos["stop"].dias) == (3, 2)
    assert (grupos["target"].n, grupos["target"].dias) == (1, 1)
    assert (total.n, total.dias) == (4, 3)


def test_mediana_de_amostra_par_e_a_media_dos_dois_centrais():
    dias = ["d1"] * 4
    motivos = ["stop"] * 4
    valores = np.array([1.0, 2.0, 4.0, 8.0])
    grupos, _ = decompoe(dias, motivos, valores, reamostragens=0)
    assert grupos["stop"].mediana == pytest.approx(3.0)  # (2+4)/2


# ------------------------------------------------------------------ 3. decis


def test_o_decil_e_o_teto_de_um_decimo_do_N_declarado():
    assert tamanho_do_decil(25) == 3    # ceil(2.5)
    assert tamanho_do_decil(542) == 55  # ceil(54.2)
    assert tamanho_do_decil(10) == 1
    assert tamanho_do_decil(1) == 1
    assert tamanho_do_decil(0) == 0


def test_contribuicao_dos_decis_superior_e_inferior_com_valores_a_mao():
    v = np.arange(1.0, 26.0)  # 1..25, n = 25, decil = 3
    # superior: 25+24+23 = 72 -> 72/25 = 2.88 ; inferior: 1+2+3 = 6 -> 0.24
    assert contribuicao_decil(v, n_total=25, alto=True) == pytest.approx(2.88)
    assert contribuicao_decil(v, n_total=25, alto=False) == pytest.approx(0.24)
    assert float(v.mean()) == pytest.approx(13.0)


def test_o_decil_superior_pode_explicar_o_total_inteiro_e_isso_e_o_achado():
    # nove decisoes em zero e uma em +10: a media e +1,0 e o decil superior
    # sozinho contribui +1,0 -- o caso "cauda" no seu extremo, para que o numero
    # que separa cauda de deslocamento tenha um caso conhecido.
    v = np.array([0.0] * 9 + [10.0])
    assert float(v.mean()) == pytest.approx(1.0)
    assert contribuicao_decil(v, n_total=10, alto=True) == pytest.approx(1.0)
    assert contribuicao_decil(v, n_total=10, alto=False) == pytest.approx(0.0)


# -------------------------------------------------------------- 4. bootstrap


def test_bootstrap_conjunto_com_um_grupo_so_e_IDENTICO_a_blocos90_ic_media():
    """A prova de que o reuso nao mudou o estimador: mesmo seed, mesmo sorteio."""
    from blocos90 import ic_media

    rng = np.random.default_rng(7)
    dias = [f"d{i % 9}" for i in range(60)]
    valores = rng.normal(size=60)
    motivos = ["stop"] * 60
    esperado = ic_media(dias, valores, reamostragens=500, seed=20260910)
    obtido = bootstrap_conjunto(dias, motivos, valores, reamostragens=500, seed=20260910)
    assert obtido.ic_media_por_grupo["stop"][0] == pytest.approx(esperado.ic95[0], abs=1e-12)
    assert obtido.ic_media_por_grupo["stop"][1] == pytest.approx(esperado.ic95[1], abs=1e-12)


def test_dentro_de_CADA_reamostragem_as_contribuicoes_somam_o_total():
    rng = np.random.default_rng(11)
    dias = [f"d{i % 7}" for i in range(40)]
    motivos = [MOTIVOS[i % 3] for i in range(40)]
    valores = rng.normal(size=40)
    b = bootstrap_conjunto(dias, motivos, valores, reamostragens=200, seed=20260910)
    erro = np.abs(b.amostras_contribuicao.sum(axis=0) - b.amostras_total).max()
    assert erro < 1e-12, f"identidade quebrada em alguma reamostragem: {erro}"


def test_a_reamostragem_e_a_MESMA_para_todos_os_grupos_no_mesmo_passo():
    """Dois grupos que so aparecem juntos: o n reamostrado tem de andar junto."""
    dias = ["d1", "d1", "d2", "d2"]
    motivos = ["stop", "target", "stop", "target"]
    valores = np.array([1.0, 1.0, 1.0, 1.0])
    b = bootstrap_conjunto(dias, motivos, valores, reamostragens=50, seed=20260910)
    # cada dia tem exatamente um `stop` e um `target`, entao qualquer sorteio de
    # dias produz n(stop) == n(target) em toda reamostragem
    assert np.array_equal(b.amostras_n["stop"], b.amostras_n["target"])


def test_um_dia_so_faz_o_IC_degenerar_no_proprio_ponto():
    dias = ["d1", "d1", "d1"]
    motivos = ["stop", "stop", "target"]
    valores = np.array([2.0, 4.0, 9.0])
    grupos, total = decompoe(dias, motivos, valores, reamostragens=50)
    assert grupos["stop"].ic_media == pytest.approx((3.0, 3.0))
    assert total.ic_media == pytest.approx((5.0, 5.0))  # (2+4+9)/3


def test_reamostragem_que_esvazia_um_grupo_nao_entra_no_IC_e_e_CONTADA():
    # `context-lost` so existe em d3; um sorteio de 3 dias sem d3 esvazia o grupo
    dias = ["d1", "d2", "d3"]
    motivos = ["stop", "stop", "context-lost"]
    valores = np.array([1.0, 2.0, 3.0])
    grupos, _ = decompoe(dias, motivos, valores, reamostragens=300, seed=20260910)
    g = grupos["context-lost"]
    assert 0 < g.reamostragens_validas < 300
    assert not math.isnan(g.ic_media[0])


def test_o_IC_da_CONTRIBUICAO_nao_e_o_IC_da_MEDIA_do_grupo():
    """Contribuicao divide pelo N total; media divide pelo n do grupo."""
    rng = np.random.default_rng(3)
    dias = [f"d{i % 6}" for i in range(30)]
    motivos = ["stop" if i % 3 else "target" for i in range(30)]
    valores = rng.normal(loc=1.0, size=30)
    grupos, _ = decompoe(dias, motivos, valores, reamostragens=200, seed=20260910)
    g = grupos["target"]
    assert g.ic_contribuicao[0] != pytest.approx(g.ic_media[0])
    assert g.ic_contribuicao[0] < g.ic_media[0]  # divisor maior encolhe


# ------------------------------------------------- 5. excursoes e antecipacao


def _velas(closes: list[float], *, is_final: bool = True) -> list[Vela]:
    """Velas de 1 min: a vela do minuto ``m`` FECHA em ``entrada + m``."""
    return [Vela(minuto=i + 1, close=c, is_final=is_final) for i, c in enumerate(closes)]


def test_a_janela_de_h_minutos_termina_na_vela_que_FECHA_em_h():
    velas = _velas([101.0, 102.0, 103.0, 104.0])
    assert [v.close for v in janela_de_closes(velas, ini=1, fim=2)] == [101.0, 102.0]
    assert [v.close for v in janela_de_closes(velas, ini=3, fim=4)] == [103.0, 104.0]
    assert janela_de_closes(velas, ini=5, fim=4) == []  # janela vazia, nao erro


def test_mfe_e_mae_de_closes_sao_os_extremos_SINALIZADOS_do_retorno():
    # entry_open = 100, atr = 1 -> ret = close - 100
    velas = _velas([101.0, 103.0, 99.0, 102.0])
    ex = mfe_mae_closes(velas, entry_open=100.0, atr=1.0, ini=1, fim=4)
    assert ex.mfe == pytest.approx(+3.0)  # close 103
    assert ex.mae == pytest.approx(-1.0)  # close 99
    assert ex.minuto_mfe == 2 and ex.minuto_mae == 3
    assert ex.n == 4


def test_o_MAE_de_uma_janela_so_de_lucro_e_POSITIVO_e_isso_nao_e_defeito():
    # a janela DEPOIS da saida por stop pode viver inteira acima da entrada:
    # chamar isso de "excursao adversa" seria mentir sobre o sinal.
    velas = _velas([101.0, 103.0, 99.0, 102.0, 105.0])
    depois = mfe_mae_closes(velas, entry_open=100.0, atr=2.0, ini=4, fim=5)
    assert depois.mfe == pytest.approx(+2.5)  # (105-100)/2
    assert depois.mae == pytest.approx(+1.0)  # (102-100)/2


def test_janelas_antes_e_depois_da_saida_particionam_a_janela_cheia():
    velas = _velas([101.0, 103.0, 99.0, 102.0, 105.0])
    antes = janela_de_closes(velas, ini=1, fim=3)     # m_saida = 3
    depois = janela_de_closes(velas, ini=4, fim=5)
    assert [v.minuto for v in antes] + [v.minuto for v in depois] == [1, 2, 3, 4, 5]
    assert not (set(v.minuto for v in antes) & set(v.minuto for v in depois))


def test_janela_vazia_devolve_ausencia_NAN_e_n_zero_nunca_zero_como_valor():
    velas = _velas([101.0, 103.0])
    ex = mfe_mae_closes(velas, entry_open=100.0, atr=1.0, ini=5, fim=8)
    assert ex.n == 0
    assert math.isnan(ex.mfe) and math.isnan(ex.mae)
    assert ex.minuto_mfe is None and ex.minuto_mae is None


def test_ANTI_ANTECIPACAO_vela_nao_final_nao_entra_na_janela():
    finais = _velas([101.0, 103.0, 99.0])
    com_provisoria = finais + [Vela(minuto=4, close=999.0, is_final=False)]
    esperado = mfe_mae_closes(finais, entry_open=100.0, atr=1.0, ini=1, fim=4)
    obtido = mfe_mae_closes(com_provisoria, entry_open=100.0, atr=1.0, ini=1, fim=4)
    assert obtido.mfe == pytest.approx(esperado.mfe) == pytest.approx(3.0)
    assert obtido.n == esperado.n == 3


def test_ANTI_ANTECIPACAO_mudar_a_vela_nao_final_NAO_muda_a_leitura():
    """A prova exigida pelo contrato: a leitura nao se move com a vela em formacao."""
    finais = _velas([101.0, 103.0, 99.0])
    leituras = []
    for provisoria in (+10_000.0, -10_000.0, 100.0):
        velas = finais + [Vela(minuto=4, close=provisoria, is_final=False)]
        ex = mfe_mae_closes(velas, entry_open=100.0, atr=1.0, ini=1, fim=4)
        leituras.append((ex.mfe, ex.mae, ex.n))
    sem_ela = mfe_mae_closes(finais, entry_open=100.0, atr=1.0, ini=1, fim=4)
    assert leituras == [(sem_ela.mfe, sem_ela.mae, sem_ela.n)] * 3


def test_ANTI_ANTECIPACAO_virar_is_final_para_true_e_o_que_faz_o_ponto_nascer():
    """O espelho: e o bit virando (o que o coletor faz ao fechar o minuto)."""
    base = _velas([101.0, 103.0, 99.0])
    provisoria = base + [Vela(minuto=4, close=120.0, is_final=False)]
    fechada = base + [Vela(minuto=4, close=120.0, is_final=True)]
    assert mfe_mae_closes(provisoria, entry_open=100.0, atr=1.0, ini=1, fim=4).mfe == 3.0
    assert mfe_mae_closes(fechada, entry_open=100.0, atr=1.0, ini=1, fim=4).mfe == 20.0


def test_ANTI_ANTECIPACAO_vela_depois_do_fim_nao_muda_o_horizonte_curto():
    velas = _velas([101.0, 103.0, 99.0, 500.0])
    curta = mfe_mae_closes(velas, entry_open=100.0, atr=1.0, ini=1, fim=3)
    assert curta.mfe == pytest.approx(3.0)  # a vela 4 existe e NAO entra


# ------------------------------------------------------- 6. Delta e unidades


def test_delta_por_decisao_e_pareado_e_a_decisao_sem_um_dos_pontos_SAI():
    pontos = {
        "a": {80: 1.0, 240: 1.5},
        "b": {80: -2.0, 240: 0.5},
        "c": {80: 0.25},            # sem o ponto de 240 -> fora
        "d": {240: 4.0},            # sem o ponto de 80  -> fora
    }
    res = delta_por_decisao(pontos, h_longo=240, h_curto=80)
    assert res.deltas == {"a": pytest.approx(0.5), "b": pytest.approx(2.5)}
    assert res.so_curto == ("c",)
    assert res.so_longo == ("d",)


def test_delta_nunca_preenche_ausencia_com_zero_nem_com_o_ponto_anterior():
    res = delta_por_decisao({"a": {80: 1.0}}, h_longo=240, h_curto=80)
    assert res.deltas == {}
    assert res.so_curto == ("a",)


def test_ret_pct_e_percentual_do_preco_de_ENTRADA_com_valor_a_mao():
    assert ret_pct(entry_open=100.0, preco=101.5) == pytest.approx(1.5)
    assert ret_pct(entry_open=200.0, preco=199.0) == pytest.approx(-0.5)
    assert ret_pct(entry_open=0.0098220, preco=0.0103360) == pytest.approx(
        100 * (0.0103360 - 0.0098220) / 0.0098220
    )


def test_as_duas_unidades_sao_proporcionais_pela_razao_atr_sobre_preco():
    from curva import ret_atr

    entry_open, preco, atr = 100.0, 102.0, 4.0
    em_atr = ret_atr(entry_open=entry_open, preco=preco, atr=atr)
    em_pct = ret_pct(entry_open=entry_open, preco=preco)
    assert em_atr == pytest.approx(0.5)
    assert em_pct == pytest.approx(2.0)
    assert em_pct == pytest.approx(em_atr * 100.0 * atr / entry_open)


def test_atr_nao_positivo_e_recusa_nao_um_numero_inventado():
    velas = _velas([101.0])
    with pytest.raises(ValueError):
        mfe_mae_closes(velas, entry_open=100.0, atr=0.0, ini=1, fim=1)


# ------------------------------------------------- 7. fronteiras e recusas


def test_o_decil_e_do_GRUPO_e_o_divisor_e_do_TOTAL():
    """As duas escolhas sao diferentes de proposito; este teste as congela."""
    v = np.arange(1.0, 11.0)  # n do grupo = 10 -> decil = 1 decisao (a de +10)
    assert contribuicao_decil(v, n_total=100, alto=True) == pytest.approx(0.10)
    assert contribuicao_decil(v, n_total=100, alto=False) == pytest.approx(0.01)
    assert contribuicao_decil(v, n_total=10, alto=True) == pytest.approx(1.00)


def test_populacao_vazia_e_recusa_nao_uma_tabela_de_zeros():
    with pytest.raises(ValueError):
        decompoe([], [], np.array([]), reamostragens=0)


def test_motivo_fora_do_vocabulario_e_recusa_nunca_silencio():
    with pytest.raises(ValueError):
        bootstrap_conjunto(["d1"], ["inventado"], np.array([1.0]), reamostragens=2)


def test_saida_por_time_stop_no_horizonte_tem_janela_DEPOIS_vazia():
    """m_saida = 240 -> [241, 240] e vazia: nao existe minuto depois do horizonte."""
    velas = _velas([101.0, 102.0])
    depois = mfe_mae_closes(velas, entry_open=100.0, atr=1.0, ini=241, fim=240)
    assert depois.n == 0 and math.isnan(depois.mfe)


def test_empate_no_extremo_devolve_o_PRIMEIRO_minuto_a_atingi_lo():
    velas = _velas([103.0, 103.0, 99.0, 99.0])
    ex = mfe_mae_closes(velas, entry_open=100.0, atr=1.0, ini=1, fim=4)
    assert ex.minuto_mfe == 1 and ex.minuto_mae == 3


# ------- 8. o Delta partido em "dentro da posicao" e "depois da saida real"


def test_a_soma_das_duas_partes_e_EXATAMENTE_o_delta_em_todo_m_saida():
    from decomp import divide_delta

    rets = {80: 1.0, 100: 1.2, 120: 1.5, 200: 1.9, 240: 2.0}
    delta = rets[240] - rets[80]
    for m_saida in (1, 40, 80, 100, 120, 200, 240, 999):
        em_posicao, depois = divide_delta(rets, m_saida=m_saida, h_curto=80, h_longo=240)
        assert em_posicao + depois == pytest.approx(delta, abs=1e-12), m_saida


def test_saida_ANTES_dos_80_poe_TUDO_na_parte_depois_da_saida():
    from decomp import divide_delta

    rets = {80: 1.0, 240: 2.0}
    em_posicao, depois = divide_delta(rets, m_saida=43, h_curto=80, h_longo=240)
    assert em_posicao == pytest.approx(0.0)
    assert depois == pytest.approx(1.0)


def test_saida_NO_HORIZONTE_poe_TUDO_na_parte_em_posicao():
    from decomp import divide_delta

    rets = {80: 1.0, 240: 2.0}
    em_posicao, depois = divide_delta(rets, m_saida=240, h_curto=80, h_longo=240)
    assert em_posicao == pytest.approx(1.0)
    assert depois == pytest.approx(0.0)


def test_saida_NO_MEIO_parte_o_delta_no_fechamento_que_cai_em_exit_ts():
    from decomp import divide_delta

    rets = {80: 1.0, 120: 1.5, 240: 2.0}
    em_posicao, depois = divide_delta(rets, m_saida=120, h_curto=80, h_longo=240)
    assert em_posicao == pytest.approx(0.5)  # 1,5 - 1,0
    assert depois == pytest.approx(0.5)      # 2,0 - 1,5


def test_a_divisao_recusa_um_minuto_de_corte_que_nao_existe_no_caminho():
    from decomp import divide_delta

    with pytest.raises(KeyError):
        divide_delta({80: 1.0, 240: 2.0}, m_saida=137, h_curto=80, h_longo=240)
