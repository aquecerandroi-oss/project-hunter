"""O estimador estratificado, os dois bootstraps e a permutação dentro do estrato.

Valores esperados calculados à mão. Cenários da Astra: r3 4a (D e p sobre populações
diferentes: o bloco só de `true` fica fora de tudo), r2 4.1 (uma rajada concentra o efeito:
o IC por mint passa e o de blocos não), r5 (estratos vazios nas réplicas, IC não finito).
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from infra.research.exp_m26.estimador import (
    Intervalo,
    estimar,
    ic_blocos,
    ic_mint,
    intervalo,
    p_permutacao,
    unidades,
)


def _base() -> tuple[list[str], list[bool], list[float | None]]:
    estrato = ["a", "a", "a", "b", "b", "b", "b"]
    grupo = [True, True, False, True, False, False, False]
    valor: list[float | None] = [1.0, 3.0, 0.0, 1.0, 0.0, 0.0, 0.0]
    return estrato, grupo, valor


def test_d_estratificado_valor_conhecido() -> None:
    """a: true 2 − false 0, w = 2·1/3; b: 1 − 0, w = 1·3/4 ⇒ D = 25/17."""
    e = estimar(unidades(*_base()))
    assert e.d == pytest.approx(25 / 17)
    assert (e.estratos, e.n_true, e.n_false) == (2, 3, 4)
    assert e.media_true == pytest.approx(5 / 3)


def test_estrato_com_um_grupo_fica_fora_de_tudo() -> None:
    """r3 4a: um bloco só de `true` muito lucrativos não move D, nem n, nem o nível."""
    estrato, grupo, valor = _base()
    e = estimar(unidades(estrato + ["c"] * 5, grupo + [True] * 5, valor + [9.0] * 5))
    assert e.d == pytest.approx(25 / 17)
    assert (e.estratos, e.n_true, e.n_false) == (2, 3, 4)
    assert e.media_true == pytest.approx(5 / 3)


def test_unidade_sem_valor_conta_no_n_e_nao_na_media() -> None:
    """O `false` censurado no estresse: entra no peso do estrato, a média é a observada."""
    estrato, grupo, valor = _base()
    u = unidades(estrato + ["a"], grupo + [False], valor + [None], conta=[True] * 8)
    e = estimar(u)
    w_a, w_b = 2 * 2 / 4, 3 / 4
    assert e.d == pytest.approx((w_a * 2 + w_b * 1) / (w_a + w_b))
    assert e.n_false == 5


def test_sem_estrato_valido_d_nao_finito() -> None:
    e = estimar(unidades(["a", "b"], [True, False], [1.0, 0.0]))
    assert math.isnan(e.d)
    assert e.estratos == 0


def _painel(efeito_rajada: float, blocos: int = 12) -> tuple[list[int], list[bool], list[float]]:
    """`blocos` blocos com 10 true e 30 false; num só, os true ganham `efeito_rajada`."""
    est: list[int] = []
    grp: list[bool] = []
    val: list[float] = []
    for b in range(blocos):
        for i in range(40):
            t = i < 10
            est.append(b)
            grp.append(t)
            if b == 0 and t:
                val.append(efeito_rajada)
            else:
                val.append(-0.005 if t else 0.005)
    return est, grp, val


def test_rajada_passa_no_ic_por_mint_e_nao_no_de_blocos() -> None:
    """r2 4.1: um choque comum num bloco vira muitas réplicas independentes no bootstrap
    por mint; o de blocos o trata como uma informação só."""
    est, grp, val = _painel(1.0)
    u = unidades(est, grp, val)
    d = estimar(u).d
    assert d == pytest.approx((0.995 + 11 * -0.01) / 12)
    mint = ic_mint(u, list(range(len(est))), reps=2000, seed=7)
    blocos = ic_blocos(u, reps=2000, seed=8)
    assert mint.finito and blocos.finito
    assert mint.lo > 0
    assert blocos.lo < 0 < blocos.hi


def test_intervalo_nao_finito_com_replicas_invalidas() -> None:
    """r5: réplicas sem estrato com os dois grupos são inválidas; > 1 % ⇒ não finito."""
    assert not intervalo(np.array([1.0] * 980 + [math.nan] * 20)).finito
    ok = intervalo(np.array([1.0] * 995 + [math.nan] * 5))
    assert ok.finito
    assert (ok.lo, ok.hi) == (1.0, 1.0)
    assert not intervalo(np.array([1.0] * 50)).finito
    assert not Intervalo(math.nan, 1.0, 0.0, 1000).finito


def test_poucos_mints_no_estrato_misto_da_ic_nao_finito() -> None:
    """Um estrato só com os dois grupos, sustentado por 2 mints: muitas réplicas perdem
    um dos grupos e o IC não vale."""
    u = unidades(["a", "a", "b", "b"], [True, False, True, True], [1.0, 0.0, 1.0, 1.0])
    iv = ic_mint(u, ["m1", "m2", "m3", "m4"], reps=1000, seed=1)
    assert iv.invalidas > 0.01
    assert not iv.finito


def test_ic_por_mint_reamostra_o_mint_inteiro() -> None:
    """Duas linhas do mesmo mint andam juntas: com 2 mints só, D só pode ser 0 ou o
    observado (nunca uma mistura de linhas de mints diferentes)."""
    u = unidades(["a"] * 4, [True, False, True, False], [1.0, 0.0, 3.0, 0.0])
    iv = ic_mint(u, ["x", "x", "y", "y"], reps=500, seed=3)
    assert iv.invalidas == 0
    assert {iv.lo, iv.hi} <= {1.0, 2.0, 3.0}


def test_permutacao_dentro_do_estrato() -> None:
    """Estrato 1: quase todos true e todos ganham; estrato 2: quase todos false e todos
    perdem. Dentro de cada estrato não há diferença ⇒ D = 0 e p = 1; a permutação global
    acharia 'sinal'."""
    est = [1] * 20 + [2] * 20
    grp = [i < 18 for i in range(20)] + [i < 2 for i in range(20)]
    val = [0.5] * 20 + [-0.5] * 20
    u = unidades(est, grp, val)
    assert estimar(u).d == pytest.approx(0.0)
    assert p_permutacao(u, reps=500, seed=2) == pytest.approx(1.0)


def test_permutacao_acha_efeito_forte_e_e_bilateral() -> None:
    est = [b for b in range(10) for _ in range(20)]
    grp = [i % 4 == 0 for i in range(200)]
    forte = [(1.0 if g else 0.0) + 0.01 * (i % 3) for i, g in enumerate(grp)]
    assert p_permutacao(unidades(est, grp, forte), reps=999, seed=4) == pytest.approx(1 / 1000)
    negativo = [-v for v in forte]
    assert p_permutacao(unidades(est, grp, negativo), reps=999, seed=4) == pytest.approx(1 / 1000)


def test_reprodutivel_pela_semente() -> None:
    est, grp, val = _painel(0.2)
    u = unidades(est, grp, val)
    a = ic_blocos(u, reps=300, seed=11)
    b = ic_blocos(u, reps=300, seed=11)
    assert (a.lo, a.hi) == (b.lo, b.hi)


def test_bloco_sorteado_duas_vezes_tem_peso_dois() -> None:
    """Revisão do J: repetir as unidades de um bloco dobra n_true e n_false dele, logo o
    peso `w` dobra e a diferença do bloco não muda."""
    estrato, grupo, valor = _base()
    dobro_a = [i for i, s in enumerate(estrato) if s == "a"]
    e = estimar(
        unidades(
            estrato + [estrato[i] for i in dobro_a],
            grupo + [grupo[i] for i in dobro_a],
            valor + [valor[i] for i in dobro_a],
        )
    )
    w_a, w_b = 2 * (2 / 3), 3 / 4
    assert e.d == pytest.approx((w_a * 2 + w_b * 1) / (w_a + w_b))
