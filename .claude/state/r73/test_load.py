"""Testes do carregador do R73 — séries sintéticas com valor esperado conhecido.

O teste que manda é `test_guarda_ignora_troca_que_chegou_depois`: a prova de que
`maior_comprador_pct` **não muda** quando entra na fita uma troca que aconteceu antes da
decisão mas só chegou ao nosso coletor depois dela (T4.80).
"""

from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from load import Trade, concentration, tape_matches_curve, tape_starts_at_birth, ts  # noqa: E402

T0 = datetime(2026, 9, 23, 20, 0, 0, tzinfo=timezone.utc)
SOL = 10**9


def tr(sec: int, trader: str, side: str, sol: float, *, lag: float = 1.0, tok: float = 0.0) -> Trade:
    bt = T0 + timedelta(seconds=sec)
    return Trade(
        block_time=bt,
        received_at=bt + timedelta(seconds=lag),
        slot=1000 + sec,
        event_index=0,
        trader=trader,
        side=side,
        sol=int(round(sol * SOL)),
        tok=int(round(tok * 10**6)),
    )


# fita sintética: dev compra 9, três carteiras compram 3+4+5, dev vende 1 → curva 20
BASE = [
    tr(0, "dev", "buy", 9.0),
    tr(2, "alice", "buy", 3.0),
    tr(4, "bob", "buy", 4.0),
    tr(6, "carol", "buy", 5.0),
    tr(8, "dev", "sell", 1.0),
]
DECISION = T0 + timedelta(seconds=30)


def test_valor_esperado_conhecido() -> None:
    c = concentration(BASE, DECISION)
    assert c.curve_lamports == 20 * SOL
    assert c.top_wallet == "dev"
    assert c.top_net_lamports == 8 * SOL  # 9 comprados - 1 vendido, líquido
    assert c.pct == pytest.approx(0.40)
    assert c.n_trades == 5
    assert c.n_wallets == 4
    assert c.blocked_by_guard == 0


def test_guarda_ignora_troca_que_chegou_depois() -> None:
    """A prova anti-antecipação: uma troca com `block_time` antes da decisão mas
    `received_at` depois **não** pode mexer numa única casa decimal do resultado."""
    antes = concentration(BASE, DECISION)
    atrasada = tr(10, "whale", "buy", 100.0, lag=120.0)  # bloco 20:00:10, chegou 20:02:10
    assert atrasada.block_time < DECISION < atrasada.received_at
    depois = concentration([*BASE, atrasada], DECISION)
    assert depois.pct == antes.pct
    assert depois.curve_lamports == antes.curve_lamports
    assert depois.top_wallet == antes.top_wallet
    assert depois.blocked_by_guard == 1
    assert depois.blocked_lamports == 100 * SOL
    # sem guarda a mesma fita dá outra resposta — é a diferença que a guarda protege
    sem_guarda = concentration([*BASE, atrasada], DECISION, guard=False)
    assert sem_guarda.top_wallet == "whale"
    assert sem_guarda.pct == pytest.approx(100 / 120)


def test_guarda_ignora_troca_posterior_a_decisao() -> None:
    """O dump de 21 SOL do `HTkSYn` é 36 s depois da nossa decisão: não conta."""
    dump = tr(90, "dev", "sell", 21.0)
    c = concentration([*BASE, dump], DECISION)
    assert c.pct == pytest.approx(0.40)
    assert c.blocked_by_guard == 0  # bloqueado por ser futuro, não pela guarda de chegada


def test_carteira_propria_fora_do_numerador() -> None:
    """A nossa própria compra não é 'um dono que pode afundar'."""
    from load import OUR

    nosso = tr(9, OUR, "buy", 50.0)
    c = concentration([*BASE, nosso], DECISION)
    assert c.curve_lamports == 70 * SOL  # entra no denominador (é SOL real da curva)
    assert c.top_wallet == "dev"
    assert c.pct == pytest.approx(8 / 70)


def test_decisao_ingenua_recusada() -> None:
    with pytest.raises(ValueError, match="ingénuo"):
        concentration(BASE, datetime(2026, 9, 23, 20, 0, 30))  # noqa: DTZ001


def test_ts_recusa_ingenuo() -> None:
    assert ts("2026-09-23 20:03:18.79+00").tzinfo is not None
    with pytest.raises(ValueError, match="ingénuo"):
        ts("2026-09-23 20:03:18.79")


def test_curva_nao_positiva_devolve_none() -> None:
    c = concentration([tr(0, "dev", "sell", 1.0)], DECISION)
    assert c.pct is None


def test_cobertura_bate_quando_fita_esta_completa() -> None:
    ok, err = tape_matches_curve(BASE, T0 + timedelta(seconds=20), Decimal("20"))  # 9+3+4+5-1
    assert ok and err == 0.0


def test_cobertura_falha_quando_a_fita_comeca_tarde() -> None:
    """Fita sem a compra do dev: reconstrói 11 contra 20 na foto → 45 % de erro."""
    sem_nascimento = BASE[1:]
    ok, err = tape_matches_curve(sem_nascimento, T0 + timedelta(seconds=20), Decimal("20"))
    assert not ok
    assert err == pytest.approx(0.45)


def test_cobertura_tolera_a_janela_de_um_segundo() -> None:
    """Foto no segundo 7: a fita soma 21 (venda do dev é em +8 s) e a banda de 1 s
    aceita também 20, o estado logo a seguir. Corrigido depois de a Astra apanhar o
    valor errado na primeira versão deste teste (somava 16, a fita soma 21)."""
    ok_estado_exato, err = tape_matches_curve(BASE, T0 + timedelta(seconds=7), Decimal("21"))
    assert ok_estado_exato and err == 0.0
    ok_banda, err2 = tape_matches_curve(BASE, T0 + timedelta(seconds=7), Decimal("20"))
    assert ok_banda and err2 == 0.0  # +8 s cai dentro da banda de 1 s
    longe, err3 = tape_matches_curve(BASE, T0 + timedelta(seconds=7), Decimal("30"))
    assert not longe and err3 == pytest.approx(9 / 30)


# ------------------------------------------------- casos exigidos pela Astra (revisão prévia)


def test_guarda_nao_muda_a_elegibilidade_da_populacao() -> None:
    """Contraexemplo 1 da Astra: sem `known_by`, uma compra antiga que chegou atrasada
    faz uma decisão **entrar** na população por informação que não tínhamos. Com
    `known_by` a elegibilidade é decidível no instante da decisão."""
    foto = T0 + timedelta(seconds=20)
    parcial = [tr(2, "alice", "buy", 10.0)]
    atrasada = tr(0, "dev", "buy", 10.0, lag=600.0)  # bloco antes da foto, chegou muito depois
    retro, _ = tape_matches_curve([*parcial, atrasada], foto, Decimal("20"))
    obs, err = tape_matches_curve([*parcial, atrasada], foto, Decimal("20"), known_by=DECISION)
    assert retro is True  # a cadeia tinha 20
    assert obs is False  # nós só sabíamos de 10
    assert err == pytest.approx(0.5)


def test_corte_e_inclusivo_no_instante_exato() -> None:
    """Igualdade exata no corte entra; um microssegundo depois, não."""
    exata = Trade(DECISION, DECISION, 1, 0, "zed", "buy", 5 * SOL)
    um_us = Trade(
        DECISION, DECISION + timedelta(microseconds=1), 1, 1, "zed2", "buy", 5 * SOL
    )
    c = concentration([*BASE, exata, um_us], DECISION)
    assert c.curve_lamports == 25 * SOL  # entrou a exata, não a de +1 µs
    assert c.blocked_by_guard == 1


def test_omissoes_que_se_compensam_passam_na_reconciliacao() -> None:
    """Contraexemplo 3 da Astra, escrito como teste: reserva certa, saldos errados.
    É por isso que a elegibilidade exige **também** a âncora de nascimento."""
    faltam = [t for t in BASE if t.trader not in ("alice", "bob")] + [tr(3, "mallory", "buy", 7.0)]
    ok, err = tape_matches_curve(faltam, T0 + timedelta(seconds=20), Decimal("20"))
    assert ok and err == 0.0  # a reconciliação de reservas não vê o buraco
    c = concentration(faltam, DECISION)
    assert c.top_wallet == "dev"  # mas o maior comprador já está errado (mallory tem 7)
    nasce, atraso = tape_starts_at_birth(faltam, T0 - timedelta(seconds=1))
    assert nasce and atraso == pytest.approx(1.0)  # e nem a âncora apanha este caso


def test_ancora_de_nascimento_apanha_fita_que_comeca_tarde() -> None:
    nasce, atraso = tape_starts_at_birth(BASE, T0 - timedelta(seconds=60))
    assert not nasce and atraso == pytest.approx(60.0)
    nasce2, atraso2 = tape_starts_at_birth(BASE, T0 - timedelta(seconds=2))
    assert nasce2 and atraso2 == pytest.approx(2.0)
    assert tape_starts_at_birth([], T0) == (False, None)


def test_bruto_liquido_e_estoque_divergem() -> None:
    """Contraexemplo 2 da Astra: compra 1 M de tokens por 9 SOL e vende metade por 9.
    Líquido em SOL = 0, estoque = 500 k tokens ainda despejáveis."""
    fita = [
        tr(0, "dev", "buy", 9.0, tok=1_000_000),
        tr(1, "outro", "buy", 11.0, tok=200_000),
        tr(2, "dev", "sell", 9.0, tok=500_000),
    ]
    c = concentration(fita, DECISION)
    assert c.curve_lamports == 11 * SOL
    assert c.top_wallet == "outro"  # líquido: dev = 0, outro = 11
    assert c.pct == pytest.approx(1.0)
    assert c.pct_bruto == pytest.approx(11 / 11)  # bruto: outro 11 > dev 9
    assert c.top_stock_tok == 500_000 * 10**6  # estoque: dev ainda tem meio milhão
    assert c.curve_tok_out == 700_000 * 10**6
    assert c.pct_estoque == pytest.approx(500 / 700)
