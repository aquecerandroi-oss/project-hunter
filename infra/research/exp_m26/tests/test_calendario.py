"""O corte e a leitura única (§4): 1.º 00:00Z depois de 7 dias completos desde T0 com
≥ 150 `true` e ≥ 450 `false` inscritas em C, no máximo o 00:00Z do dia 21; leitura fixa em
corte + 2 h (revisão do J: executar mais tarde nunca transforma censura em retorno);
parada pela guarda encerra a inscrição (r3 must-fix 5)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from infra.research.exp_m26.calendario import LeituraAntecipada, corte, meia_noite, t0_de

T0 = datetime(2026, 10, 1, 12, 30, tzinfo=UTC)


def _inscricoes(ate: datetime, por_dia_true: int, por_dia_false: int) -> list[tuple[datetime, str]]:
    out: list[tuple[datetime, str]] = []
    t = T0
    while t < ate:
        out += [(t + timedelta(minutes=i), "true") for i in range(por_dia_true)]
        out += [(t + timedelta(minutes=100 + i), "false") for i in range(por_dia_false)]
        t += timedelta(days=1)
    return out


def test_t0_e_meia_noite() -> None:
    seed = datetime(2026, 9, 29, 12, 30, tzinfo=UTC)
    assert t0_de(seed) == T0
    assert meia_noite(T0) == datetime(2026, 10, 2, tzinfo=UTC)
    exata = datetime(2026, 10, 2, tzinfo=UTC)
    assert meia_noite(exata) == exata


def test_corte_no_minimo_quando_as_metas_ja_bateram() -> None:
    ins = _inscricoes(T0 + timedelta(days=30), 30, 80)
    c = corte(T0, ins, parada=None, agora=T0 + timedelta(days=40))
    assert c.instante == datetime(2026, 10, 9, tzinfo=UTC)  # T0 + 7 d = 10-08 12:30
    assert c.motivo == "metas"
    assert c.leitura == c.instante + timedelta(hours=2)


def test_corte_espera_as_metas_dos_dois_grupos() -> None:
    """21 true/dia bate 150 com 8 dias (10-09), mas 50 false/dia só bate 450 com 9 (10-10)."""
    ins = _inscricoes(T0 + timedelta(days=30), 21, 50)
    c = corte(T0, ins, parada=None, agora=T0 + timedelta(days=40))
    assert c.instante == datetime(2026, 10, 10, tzinfo=UTC)
    contados = [t for t, _ in ins if t < c.instante]
    assert sum(1 for t, k in ins if t < c.instante and k == "false") >= 450
    assert len(contados) < len(ins)


def test_inscricao_exatamente_na_meia_noite_nao_conta_para_ela() -> None:
    m = datetime(2026, 10, 9, tzinfo=UTC)
    ins = [(T0, "true")] * 149 + [(T0, "false")] * 450 + [(m, "true")]
    c = corte(T0, ins, parada=None, agora=T0 + timedelta(days=30))
    assert c.instante == datetime(2026, 10, 10, tzinfo=UTC)


def test_dia_21_sem_metas() -> None:
    ins = _inscricoes(T0 + timedelta(days=30), 2, 5)
    c = corte(T0, ins, parada=None, agora=T0 + timedelta(days=30))
    assert c.instante == datetime(2026, 10, 23, tzinfo=UTC)
    assert c.motivo == "dia_21"


def test_parada_pela_guarda_encerra_a_inscricao() -> None:
    parada = T0 + timedelta(days=3, hours=5)
    ins = _inscricoes(T0 + timedelta(days=30), 30, 80)
    c = corte(T0, ins, parada=parada, agora=parada + timedelta(hours=3))
    assert (c.instante, c.motivo) == (parada, "parada_guarda")
    assert c.leitura == parada + timedelta(hours=2)


def test_aposentar_no_instante_do_corte_nao_e_parada() -> None:
    """Metas batidas na meia-noite M e braços aposentados exatamente em M: a inscrição já
    terminou em M, o corte é das metas. Sem as metas em M, a mesma aposentadoria é parada."""
    m = datetime(2026, 10, 9, tzinfo=UTC)
    cheio = _inscricoes(T0 + timedelta(days=30), 30, 80)
    assert corte(T0, cheio, parada=m, agora=m + timedelta(days=1)).motivo == "metas"
    ralo = _inscricoes(T0 + timedelta(days=30), 1, 1)
    c = corte(T0, ralo, parada=m, agora=m + timedelta(days=1))
    assert (c.instante, c.motivo) == (m, "parada_guarda")


def test_leitura_antecipada_recusa() -> None:
    ins = _inscricoes(T0 + timedelta(days=30), 30, 80)
    with pytest.raises(LeituraAntecipada):
        corte(T0, ins, parada=None, agora=datetime(2026, 10, 9, 1, 59, tzinfo=UTC))
    c = corte(T0, ins, parada=None, agora=datetime(2026, 10, 9, 2, 0, tzinfo=UTC))
    assert c.instante == datetime(2026, 10, 9, tzinfo=UTC)
    with pytest.raises(LeituraAntecipada):
        corte(
            T0,
            _inscricoes(T0 + timedelta(days=9), 1, 1),
            parada=None,
            agora=T0 + timedelta(days=12),
        )


def test_corte_so_ve_o_que_ja_chegou_em_cada_meia_noite() -> None:
    """Inscrições futuras não antecipam o corte (a regra é causal)."""
    ins = _inscricoes(T0 + timedelta(days=30), 10, 30)
    c = corte(T0, ins, parada=None, agora=T0 + timedelta(days=40))
    mais = ins + [(c.instante + timedelta(minutes=1), "true")] * 1000
    assert corte(T0, mais, parada=None, agora=T0 + timedelta(days=40)).instante == c.instante
