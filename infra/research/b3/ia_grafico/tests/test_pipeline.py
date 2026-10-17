"""Ponta a ponta com o cliente falso numa série sintética: coleta (só passado) → avaliação."""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from infra.research.b3.ia_grafico.barras import Barra
from infra.research.b3.ia_grafico.modelo import ClienteFalso, Pedido
from infra.research.b3.ia_grafico.pipeline import (
    Instante,
    avaliar,
    coletar,
    gravar_jsonl,
    instantes_do_pregao,
)
from infra.research.b3.ia_grafico.render import renderizar
from infra.research.b3.ia_grafico.resposta import Lado
from infra.research.b3.ia_grafico.tests.fabrica import brt, pregao


class _Queda(BaseException):
    """Queda do processo simulada (não é Exception: o cliente não a engole)."""


DIAS = [date(2026, 3, 9) + timedelta(days=k) for k in (0, 1, 2, 3, 4)]


def _serie() -> list[Barra]:
    barras: list[Barra] = []
    for k, d in enumerate(DIAS):
        barras += pregao(d, inicio_pts=120_000 + 300 * k, semente=10 + k)
    return barras


def _resposta(lado: str) -> str:
    sinal = 1 if lado == "buy" else -1
    return json.dumps(
        {
            "side": lado,
            "entry_type": "market",
            "entry_y": None,
            "stop_y": -0.2 * sinal,
            "target_y": 0.3 * sinal,
            "confidence": 0.5,
            "levels": [],
            "rationale": "teste",
        }
    )


def _relogio() -> Iterator[datetime]:

    t = datetime(2026, 10, 17, tzinfo=UTC)
    while True:
        t += timedelta(seconds=1)
        yield t


def test_instantes_do_pregao_na_grade_fixa() -> None:
    inst = instantes_do_pregao(DIAS[1], abertura=brt(DIAS[1], 10, 0), fim=brt(DIAS[1], 17, 0))
    assert [i.t for i in inst][:2] == [brt(DIAS[1], 10, 30), brt(DIAS[1], 11, 0)]
    assert len(inst) == 12 and inst[-1].t == brt(DIAS[1], 16, 0) and inst[-1].slot == 11


def test_coleta_so_ve_o_passado_e_marca_janela_curta() -> None:
    serie = _serie()
    vistos: list[Pedido] = []
    relogio = _relogio()

    def politica(p: Pedido) -> str:
        vistos.append(p)
        return _resposta("buy")

    cliente = ClienteFalso(politica, relogio=lambda: next(relogio))
    inst = instantes_do_pregao(DIAS[0], abertura=brt(DIAS[0], 10, 0), fim=brt(DIAS[0], 17, 0))
    inst += instantes_do_pregao(DIAS[1], abertura=brt(DIAS[1], 10, 0), fim=brt(DIAS[1], 17, 0))
    coletas = coletar(serie, inst, cliente)
    # 1.º pregão: 10:30 tem só 18 barras de 5 min (< 120) → inelegível, sem chamada
    assert coletas[0].motivo_inelegivel and coletas[0].resposta is None
    assert all(c.resposta is not None for c in coletas[12:])
    # o pedido carrega exatamente a imagem causal do instante
    alvo = coletas[12]
    assert alvo.grafico_sha256 == renderizar(serie, alvo.instante.t).sha256_pixels
    assert len(vistos) == sum(1 for c in coletas if not c.motivo_inelegivel)


def test_avaliacao_produz_celulas_com_os_dois_lados_e_o_braco_completo(tmp_path: Path) -> None:
    serie = _serie()
    relogio = _relogio()
    cliente = ClienteFalso(lambda _p: _resposta("sell"), relogio=lambda: next(relogio))
    inst = [
        i
        for d in DIAS[1:]
        for i in instantes_do_pregao(d, abertura=brt(d, 10, 0), fim=brt(d, 17, 0))
    ]
    coletas = coletar(serie, inst, cliente)
    av = avaliar(serie, coletas)
    assert len(av.celulas) == 48 and all(c.lado_ia is Lado.VENDA for c in av.celulas)
    c = av.celulas[0]
    assert c.compra_bp is not None and c.venda_bp is not None
    assert c.compra_pior_bp < 0 < c.compra_melhor_bp
    assert len(av.completo_bp) == 48 and av.n_sem_preco_entrada == 0
    # o caminho de gravação guarda a resposta crua e os hashes, uma linha por tentativa
    destino = tmp_path / "coleta.jsonl"
    gravar_jsonl(coletas, destino)
    linhas = destino.read_text(encoding="utf-8").splitlines()
    assert len(linhas) == 48
    primeira = json.loads(linhas[0])
    assert primeira["resposta_crua"] == _resposta("sell")
    assert primeira["grafico_sha256"] == coletas[0].grafico_sha256
    assert Decimal(primeira["referencia"]) > 0


def test_braco_espelhado_desfaz_a_chamada_antes_de_simular() -> None:
    serie = _serie()
    relogio = _relogio()
    d = DIAS[2]
    normal = instantes_do_pregao(d, abertura=brt(d, 10, 0), fim=brt(d, 17, 0))[:3]
    espelho = [Instante(i.id + "-e", i.t, i.slot, i.fim_sessao, espelho=True) for i in normal]
    cliente = ClienteFalso(lambda _p: _resposta("buy"), relogio=lambda: next(relogio))
    av = avaliar(serie, coletar(serie, espelho, cliente))
    # "compra" no gráfico espelhado = venda no mercado real
    assert all(c.lado_ia is Lado.VENDA for c in av.celulas)


def test_orcamento_e_cumulativo_entre_lotes() -> None:
    """Astra R2: o teto não pode reiniciar a cada chamada de ``coletar``."""
    from infra.research.b3.ia_grafico.pipeline import Orcamento, OrcamentoEsgotado

    serie = _serie()
    relogio = _relogio()
    chamadas: list[int] = []

    def politica(_p: Pedido) -> str:
        chamadas.append(1)
        return "lixo"  # inválida: gasta duas tentativas por instante

    cliente = ClienteFalso(politica, relogio=lambda: next(relogio))
    d = DIAS[2]
    inst = instantes_do_pregao(d, abertura=brt(d, 10, 0), fim=brt(d, 17, 0))
    orcamento = Orcamento(maximo=5)
    assert len(coletar(serie, inst[:1], cliente, orcamento=orcamento)) == 1  # 2 gastas
    try:
        coletar(serie, inst[1:], cliente, orcamento=orcamento)
    except OrcamentoEsgotado as e:
        assert len(e.coletas) == 1  # 2 + 2 = 4; o próximo instante estouraria 5
    else:
        raise AssertionError("o teto não parou a coleta")
    assert len(chamadas) == 4 and orcamento.gastas == 4


def test_cada_instante_e_gravado_antes_do_proximo_e_a_retomada_nao_reenvia(tmp_path: Path) -> None:
    """Astra R2: persistir cada tentativa antes de avançar; retomar por id sem reenviar."""
    from infra.research.b3.ia_grafico.pipeline import ler_jsonl

    serie = _serie()
    relogio = _relogio()
    vistos: list[int] = []
    destino = tmp_path / "coleta.jsonl"

    def politica(_p: Pedido) -> str:
        vistos.append(1)
        if len(vistos) == 3:
            raise _Queda  # o processo cai no meio do 3.º instante
        return _resposta("buy")

    cliente = ClienteFalso(politica, relogio=lambda: next(relogio))
    d = DIAS[2]
    inst = instantes_do_pregao(d, abertura=brt(d, 10, 0), fim=brt(d, 17, 0))[:4]
    try:
        coletar(serie, inst, cliente, destino=destino)
    except _Queda:
        pass
    tipos = [json.loads(x)["tipo"] for x in destino.read_text(encoding="utf-8").splitlines()]
    # intenção e resultado dos 2 primeiros, e a intenção do 3.º (caiu durante o envio)
    assert tipos == ["intencao", "tentativa", "intencao", "tentativa", "intencao"]
    vistos.clear()
    coletar(serie, inst, cliente, destino=destino)
    assert len(vistos) == 2  # só os instantes 3 e 4
    lidas = ler_jsonl(destino)
    assert [c.instante.id for c in lidas] == [i.id for i in inst]
    assert all(c.resposta is not None and c.resposta.lado is Lado.COMPRA for c in lidas)
    assert lidas[0].instante.fim_sessao == inst[0].fim_sessao


def _queda_na(n_queda: int, respostas: list[str]):  # type: ignore[no-untyped-def]
    vistos: list[int] = []
    total: list[int] = []  # não é zerado entre execuções: a queda acontece uma vez só

    def politica(_p: Pedido) -> str:
        vistos.append(1)
        total.append(1)
        if len(total) == n_queda:
            raise _Queda  # o processo cai DURANTE esta tentativa
        return respostas.pop(0)

    return politica, vistos


def test_queda_entre_as_duas_tentativas_nao_ganha_tentativas_novas(tmp_path: Path) -> None:
    """Sonda da Astra R3: 1.ª inválida, queda na 2.ª → a retomada não reenvia (2 já usadas)."""
    from infra.research.b3.ia_grafico.pipeline import Orcamento
    from infra.research.b3.ia_grafico.registro_jsonl import estado

    serie = _serie()
    relogio = _relogio()
    destino = tmp_path / "coleta.jsonl"
    d = DIAS[2]
    inst = instantes_do_pregao(d, abertura=brt(d, 10, 0), fim=brt(d, 17, 0))[:1]
    politica, vistos = _queda_na(2, ["lixo"])
    orcamento = Orcamento(maximo=10)
    cliente = ClienteFalso(politica, relogio=lambda: next(relogio))
    try:
        coletar(serie, inst, cliente, destino=destino, orcamento=orcamento)
    except _Queda:
        pass
    assert orcamento.gastas == 2  # o débito vem ANTES do envio
    e = estado(destino)[inst[0].id]
    assert (e.usadas, e.concluido) == (2, True)
    vistos.clear()
    coletar(serie, inst, cliente, destino=destino)
    assert vistos == []


def test_queda_na_primeira_tentativa_permite_so_a_segunda(tmp_path: Path) -> None:
    from infra.research.b3.ia_grafico.pipeline import ler_jsonl

    serie = _serie()
    relogio = _relogio()
    destino = tmp_path / "coleta.jsonl"
    d = DIAS[2]
    inst = instantes_do_pregao(d, abertura=brt(d, 10, 0), fim=brt(d, 17, 0))[:1]
    politica, vistos = _queda_na(1, [_resposta("sell")])
    cliente = ClienteFalso(politica, relogio=lambda: next(relogio))
    try:
        coletar(serie, inst, cliente, destino=destino)
    except _Queda:
        pass
    vistos.clear()
    coletar(serie, inst, cliente, destino=destino)
    assert len(vistos) == 1  # a 1.ª tentativa ficou consumida (desfecho desconhecido)
    (c,) = ler_jsonl(destino)
    assert c.resposta is not None and c.resposta.lado is Lado.VENDA
    assert [r.tentativa for r in c.registros] == [2]
    assert c.tentativas_sem_desfecho == (1,)


def test_orcamento_se_reconstroi_do_registro_num_processo_novo(tmp_path: Path) -> None:
    from infra.research.b3.ia_grafico.registro_jsonl import tentativas_consumidas

    serie = _serie()
    relogio = _relogio()
    destino = tmp_path / "coleta.jsonl"
    d = DIAS[2]
    inst = instantes_do_pregao(d, abertura=brt(d, 10, 0), fim=brt(d, 17, 0))[:3]
    politica, _ = _queda_na(4, ["lixo", _resposta("buy"), "lixo"])
    cliente = ClienteFalso(politica, relogio=lambda: next(relogio))
    try:
        coletar(serie, inst, cliente, destino=destino)
    except _Queda:
        pass
    # 1.º: inválida + válida (2); 2.º: inválida (1) + intenção órfã da 2.ª (1) → 4, sem contar duas vezes
    assert tentativas_consumidas(destino) == 4
