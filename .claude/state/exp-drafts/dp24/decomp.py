"""D-P24 — a decomposicao do Delta(240 - 80) pelo MOTIVO REAL de saida.

DIAGNOSTICO, nao regua causal, nao proposta de mudanca de versao. A pergunta e
**descritiva**: o movimento bruto adicional que o D-P23 mediu entre +80 e
+240 min (media pareada +0,3007 ATR, IC 95 % [+0,0071; +0,5820]) se acumula nas
decisoes que sairam por **time-stop** — onde um horizonte mais longo poderia
tocar esse dinheiro — ou nas que sairam por **stop**, onde ele nunca poderia ser
tocado, porque a posicao ja estava fechada?

Nada aqui diz o que uma politica de saida diferente **teria** rendido; para isso
seria preciso reexecutar o walker com outra geometria, e isso e experimento, nao
leitura (`KB-0054`: o alvo fixo corta a cauda direita **e** evita a reversao; o
efeito liquido e outra medicao).

## As escolhas, todas declaradas

1. **A medida principal e `Delta_i = ret_i(240) - ret_i(80)`**, pareada por
   decisao (MUST-FIX 1 da Astra, `astra-review-plantao-20260911-1030.md`): uma
   trajetoria pode bater +5 ATR aos 60 min, estar em +3 aos 80 e terminar em -1
   aos 240 — MFE enorme e contribuicao **negativa** ao achado. Excursoes entram
   **ao lado**, como coluna auxiliar, nunca como a medida.
2. **A base e o `open` da barra de entrada** (a mesma do D-P23, a correcao que a
   Astra carimbou), entao a leitura e **bruta**: `virtual_entry` ja carrega
   6 bps de spread + slippage (`pricing.py:47`).
3. **Duas unidades:** o ATR congelado da propria decisao
   (`agent_signals.supporting_features->'atr'->>'value'`) e o **% do preco de
   entrada**. A segunda existe porque o ATR e um denominador por decisao: um
   grupo com ATR% tipicamente menor mostra Delta em ATR maior sem que o preco
   tenha andado mais.
4. **Contribuicao do grupo = `soma dos Delta_i do grupo / N_TOTAL`** (nao
   `/ n_do_grupo`). E a unica decomposicao que **recompoe** a media total por
   construcao — e por isso responde "de onde veio o movimento adicional" sem
   dividir por uma soma total proxima de zero (a alternativa que a Astra
   recusou).
5. **IC 95 % por bootstrap de blocos de dia**, reamostrando **todos os grupos de
   uma vez** com o mesmo sorteio de dias: se cada grupo reamostrasse os seus
   proprios dias, as contribuicoes deixariam de somar o total dentro da
   reamostragem e o IC do total nao seria o IC da soma. `blocos90.ic_media` e
   `curva.ic_mediana_blocos` sao **reusados** para as leituras de uma populacao
   so; :func:`bootstrap_conjunto` e novo e existe apenas por essa exigencia de
   sorteio compartilhado — e um teste afirma que, com um grupo so, ele devolve
   **exatamente** o intervalo de `blocos90.ic_media`.
6. **Decis:** o decil e `ceil(n/10)` decisoes (55 de 542), e a contribuicao do
   decil e a soma dele sobre o **N total**. MUST-FIX 3: "cauda, nao maioria" e
   **leitura a confirmar** — media com IC acima de zero e mediana com IC
   cruzando zero nao demonstram concentracao. O numero que separa as duas
   leituras e este: se o decil superior sozinho contribui praticamente toda a
   media, e cauda; se a contribuicao esta espalhada, e deslocamento.
7. **Excursoes sao de CLOSES, e o nome diz isso** (MUST-FIX 2). OHLC nao revela
   ordem intrabar, entao nao existe "o maximo que a posicao viu" sem supor
   ordem; `mfe`/`mae` aqui sao o **maximo e o minimo do retorno de fechamento**
   na janela, com sinal preservado — o minimo de uma janela inteiramente
   lucrativa e **positivo**, e chamar isso de "excursao adversa" seria mentir.
8. **A janela depois da saida comeca na saida**, nunca na entrada (MUST-FIX 2):
   `MFE` desde a entrada pode refletir so uma alta **anterior** ao stop. Com
   `m` = o minuto em que a vela **fecha** (a vela `m` abre em `entrada + m - 1`)
   e `m_saida = (exit_ts - entry_ts)/1min`, a particao e
   `antes = [1, m_saida]` e `depois = [m_saida + 1, 240]` — disjuntas e
   exaustivas. Ela funciona para os dois tipos de saida do walker
   (`walker.py:_close`): saida no **open** carimba `exit_ts = open_time` da barra
   de saida, entao o fechamento **dessa** barra ja e "depois"; saida intrabar
   carimba `exit_ts = close_time`, entao aquela barra e "antes". Em nenhum dos
   dois casos a barra de saida recebe uma ordem temporal que o OHLC nao mostra.
9. **Anti-antecipacao:** so vela `is_final` entra em qualquer janela (PIPELINE
   §2), ausencia e `nan` e **sai do denominador** — nunca preenchida com o preco
   anterior nem com zero.

NumPy sobre janelas em memoria; nada de pandas. Nada aqui e dinheiro persistido,
entao nada aqui e ``Decimal`` (a fronteira ``Decimal`` fica no banco, PIPELINE
§9).
"""

from __future__ import annotations

import math
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np

_RAIZ = Path(__file__).resolve().parent.parent
for _vizinho in ("t362b", "dp23"):  # reuso do que ja tem teste, nunca uma copia
    _p = str(_RAIZ / _vizinho)
    if _p not in sys.path:
        sys.path.insert(0, _p)

from blocos90 import _por_dia, ic_media  # noqa: E402,F401  (reuso declarado)
from curva import ic_mediana_blocos, ret_atr  # noqa: E402,F401  (reuso declarado)

__all__ = [
    "MOTIVOS",
    "Excursao",
    "ParesDelta",
    "ResumoGrupo",
    "Vela",
    "bootstrap_conjunto",
    "contribuicao",
    "contribuicao_decil",
    "decompoe",
    "delta_por_decisao",
    "divide_delta",
    "ic_media",
    "ic_mediana_blocos",
    "janela_de_closes",
    "mfe_mae_closes",
    "motivo_canonico",
    "ret_atr",
    "ret_pct",
    "tamanho_do_decil",
]

_NAN = float("nan")

MOTIVOS: tuple[str, ...] = ("stop", "target", "time-stop", "context-lost", "other")
"""O vocabulario do brief, em ordem congelada. `other` existe para que nenhuma
decisao desapareca da tabela: um `tracking_state` diferente de `terminal` ou um
`result` que o enum ganhe no futuro cai ali e aparece com n proprio."""

_DE_RESULT = {
    "stop": "stop",
    "target": "target",
    "expired": "time-stop",       # o horizonte da versao esgotou (`expected_holding_s`)
    "invalidated": "context-lost",  # as invalidacoes do sinal dispararam
}


def motivo_canonico(result: str, tracking_state: str) -> str:
    """``(signal_outcomes.result, tracking_state)`` no vocabulario do brief.

    So um desfecho ``terminal`` tem motivo: ``no_entry`` e ``censored`` mantem
    ``result = 'open'`` por construcao (`agents.py`, CHECK
    ``tracking_state_matches_result``), e transformar censura em ``time-stop``
    seria exatamente a invencao que o esquema proibe.
    """
    if (tracking_state or "").strip() != "terminal":
        return "other"
    return _DE_RESULT.get((result or "").strip(), "other")


def ret_pct(*, entry_open: float, preco: float) -> float:
    """``(preco - open da entrada) / open da entrada`` em **pontos percentuais**."""
    entry_open = float(entry_open)
    if not entry_open > 0:
        raise ValueError(f"preco de entrada nao positivo nao e unidade: {entry_open!r}")
    return 100.0 * (float(preco) - entry_open) / entry_open


# --------------------------------------------------------------------------
# Delta pareado por decisao
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ParesDelta:
    deltas: dict[str, float]
    so_curto: tuple[str, ...]
    so_longo: tuple[str, ...]


def delta_por_decisao(
    pontos: Mapping[str, Mapping[int, float]],
    *,
    h_longo: int,
    h_curto: int,
) -> ParesDelta:
    """``Delta_i = ret_i(h_longo) - ret_i(h_curto)`` para quem tem **os dois** pontos.

    A decisao que tem so um dos dois e **contada** e fica de fora: inventar o
    ponto que falta e o que a regra "ausencias nao preenchidas" proibe.
    """
    deltas: dict[str, float] = {}
    so_curto: list[str] = []
    so_longo: list[str] = []
    for decisao in sorted(pontos):
        p = pontos[decisao]
        curto, longo = p.get(h_curto), p.get(h_longo)
        tem_curto = curto is not None and not math.isnan(float(curto))
        tem_longo = longo is not None and not math.isnan(float(longo))
        if tem_curto and tem_longo:
            deltas[decisao] = float(longo) - float(curto)
        elif tem_curto:
            so_curto.append(decisao)
        elif tem_longo:
            so_longo.append(decisao)
    return ParesDelta(deltas, tuple(so_curto), tuple(so_longo))


def divide_delta(
    rets: Mapping[int, float],
    *,
    m_saida: int,
    h_curto: int,
    h_longo: int,
) -> tuple[float, float]:
    """Parte ``Delta_i`` em (dentro da posicao real, depois da saida real).

    Com ``c = min(max(m_saida, h_curto), h_longo)``::

        Delta_i = [ret(c) - ret(h_curto)]  +  [ret(h_longo) - ret(c)]
                  \\_ o trecho que a posicao _/    \\_ o trecho que ela _/
                     de verdade atravessou            nao podia tocar

    A identidade e exata por telescopagem — as duas partes somam ``Delta_i`` em
    qualquer ``m_saida`` — e e ela que responde a pergunta do brief: o movimento
    adicional entre +80 e +240 min e dinheiro que a estrategia **poderia ter
    guardado** (parte dentro da posicao) ou dinheiro que ela **nunca poderia
    tocar** (parte depois da saida, porque a posicao ja estava fechada)?

    O corte e o **fechamento que cai exatamente em `exit_ts`** (a vela `m_saida`
    fecha em `entry_ts + m_saida min`), nao o `exit_price`: a leitura inteira e
    de fechamentos brutos, e misturar o preenchimento sintetico da saida (que o
    walker limita em `target1` num gap favoravel, `walker.py:_close`) dentro de
    uma trajetoria bruta de preco daria um numero que nao e nem um nem outro.
    Nada disto e o resultado realizado da operacao — esse e o `r_multiple`, e ele
    ja esta medido em outro lugar (EXP-0025: `r_ex_funding` -0,0910 R em 90 d).
    """
    c = min(max(int(m_saida), int(h_curto)), int(h_longo))
    for minuto in (h_curto, h_longo, c):
        if minuto not in rets:
            raise KeyError(f"o caminho nao tem o minuto {minuto}: ausencia nao se preenche")
    em_posicao = float(rets[c]) - float(rets[h_curto])
    depois = float(rets[h_longo]) - float(rets[c])
    return em_posicao, depois


# --------------------------------------------------------------------------
# Contribuicao e decis
# --------------------------------------------------------------------------


def contribuicao(valores: np.ndarray, *, n_total: int) -> float:
    """``soma(valores) / n_total`` — a parcela do grupo na media da populacao."""
    if n_total <= 0:
        raise ValueError(f"N total tem de ser positivo: {n_total!r}")
    v = np.asarray(valores, dtype=float)
    v = v[~np.isnan(v)]
    return float(v.sum() / n_total)


def tamanho_do_decil(n: int) -> int:
    """``ceil(n/10)`` — 55 decisoes para n = 542. Declarado, nao implicito."""
    if n <= 0:
        return 0
    return int(math.ceil(n / 10.0))


def contribuicao_decil(valores: np.ndarray, *, n_total: int, alto: bool) -> float:
    """Contribuicao do decil **superior** (``alto``) ou **inferior** do grupo.

    O decil e medido no grupo que entra (``ceil(len(valores)/10)``); o divisor e
    o ``n_total`` da populacao, para que a parcela seja comparavel com as
    contribuicoes da tabela. As duas escolhas sao diferentes de proposito e
    estao fixadas em teste.
    """
    v = np.asarray(valores, dtype=float)
    v = np.sort(v[~np.isnan(v)])
    k = tamanho_do_decil(int(v.size))
    if k == 0:
        return 0.0
    recorte = v[-k:] if alto else v[:k]
    return contribuicao(recorte, n_total=n_total)


# --------------------------------------------------------------------------
# Bootstrap de blocos de dia CONJUNTO
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class BootstrapConjunto:
    dias: int
    reamostragens: int
    amostras_total: np.ndarray                    # (R,)
    amostras_media: dict[str, np.ndarray]         # motivo -> (R,), nan quando vazio
    amostras_mediana: dict[str, np.ndarray]
    amostras_contribuicao: np.ndarray             # (G, R), 0.0 quando o grupo esvazia
    amostras_n: dict[str, np.ndarray]             # motivo -> (R,) int
    ordem_grupos: tuple[str, ...]
    identidade_max_erro: float

    @property
    def ic_media_por_grupo(self) -> dict[str, tuple[float, float]]:
        return {g: _ic(self.amostras_media[g]) for g in self.ordem_grupos}

    @property
    def ic_mediana_por_grupo(self) -> dict[str, tuple[float, float]]:
        return {g: _ic(self.amostras_mediana[g]) for g in self.ordem_grupos}

    @property
    def ic_contribuicao_por_grupo(self) -> dict[str, tuple[float, float]]:
        return {
            g: _ic(self.amostras_contribuicao[i])
            for i, g in enumerate(self.ordem_grupos)
        }

    @property
    def validas_por_grupo(self) -> dict[str, int]:
        return {
            g: int((~np.isnan(self.amostras_media[g])).sum()) for g in self.ordem_grupos
        }


def _ic(amostras: np.ndarray) -> tuple[float, float]:
    """Percentis 2,5/97,5 das reamostragens **validas**; ausencia total e `nan`."""
    a = np.asarray(amostras, dtype=float)
    a = a[~np.isnan(a)]
    if a.size == 0:
        return (_NAN, _NAN)
    return (float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5)))


def bootstrap_conjunto(
    dias: Sequence[str],
    motivos: Sequence[str],
    valores: np.ndarray,
    *,
    grupos: Sequence[str] = MOTIVOS,
    reamostragens: int = 20_000,
    seed: int = 20260910,
) -> BootstrapConjunto:
    """Reamostra **dias inteiros** uma vez por passo e le todos os grupos nele.

    O sorteio e identico ao de ``blocos90.ic_media`` (mesma ordem canonica de
    dias, mesmo ``default_rng(seed)``, mesma chamada ``rng.choice``), o que faz
    de um grupo unico aqui o **mesmo** intervalo daquela funcao — afirmado em
    teste. O que muda e so que o mesmo sorteio alimenta G grupos, sem o que as
    contribuicoes nao somariam o total dentro da reamostragem.
    """
    v = np.asarray(valores, dtype=float)
    dias = list(dias)
    motivos = list(motivos)
    if not (len(dias) == len(motivos) == v.size):
        raise ValueError(
            f"dias/motivos/valores com tamanhos diferentes: {len(dias)}/{len(motivos)}/{v.size}"
        )
    ordem, baldes_totais = _por_dia(dias, v)
    indice = {d: i for i, d in enumerate(ordem)}

    # baldes[g][d] = os valores do grupo g no dia d (mesma ordem canonica)
    por_grupo: dict[str, list[list[float]]] = {g: [[] for _ in ordem] for g in grupos}
    for d, m, x in zip(dias, motivos, v, strict=True):
        if m not in por_grupo:
            raise ValueError(f"motivo fora do vocabulario: {m!r}")
        por_grupo[m][indice[d]].append(float(x))
    baldes = {g: [np.array(b, dtype=float) for b in por_grupo[g]] for g in grupos}

    rng = np.random.default_rng(seed)
    idx = np.arange(len(ordem))
    R = int(reamostragens)
    total = np.full(R, _NAN)
    media = {g: np.full(R, _NAN) for g in grupos}
    mediana = {g: np.full(R, _NAN) for g in grupos}
    contrib = np.zeros((len(grupos), R))
    enes = {g: np.zeros(R, dtype=int) for g in grupos}

    for k in range(R):
        escolhidos = rng.choice(idx, size=len(ordem), replace=True)
        cheio = np.concatenate([baldes_totais[i] for i in escolhidos])
        n_total = int(cheio.size)
        total[k] = float(cheio.mean()) if n_total else _NAN
        for gi, g in enumerate(grupos):
            arr = np.concatenate([baldes[g][i] for i in escolhidos])
            enes[g][k] = arr.size
            if arr.size == 0:
                contrib[gi, k] = 0.0
                continue
            media[g][k] = float(arr.mean())
            mediana[g][k] = float(np.percentile(arr, 50, method="linear"))
            contrib[gi, k] = float(arr.sum() / n_total) if n_total else _NAN

    erro = (
        float(np.abs(contrib.sum(axis=0) - total).max())
        if R and not np.isnan(total).all()
        else 0.0
    )
    return BootstrapConjunto(
        dias=len(ordem),
        reamostragens=R,
        amostras_total=total,
        amostras_media=media,
        amostras_mediana=mediana,
        amostras_contribuicao=contrib,
        amostras_n=enes,
        ordem_grupos=tuple(grupos),
        identidade_max_erro=erro,
    )


# --------------------------------------------------------------------------
# A tabela
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ResumoGrupo:
    motivo: str
    n: int
    dias: int
    media: float
    mediana: float
    soma: float
    contribuicao: float
    frac_pos: float
    p25: float
    p75: float
    ic_media: tuple[float, float]
    ic_mediana: tuple[float, float]
    ic_contribuicao: tuple[float, float]
    reamostragens_validas: int
    contrib_decil_sup: float
    contrib_decil_inf: float


def _resumo(
    motivo: str,
    dias_g: list[str],
    v: np.ndarray,
    *,
    n_total: int,
    ic_m: tuple[float, float] = (_NAN, _NAN),
    ic_md: tuple[float, float] = (_NAN, _NAN),
    ic_c: tuple[float, float] = (_NAN, _NAN),
    validas: int = 0,
) -> ResumoGrupo:
    v = np.asarray(v, dtype=float)
    v = v[~np.isnan(v)]
    if v.size == 0:
        return ResumoGrupo(
            motivo, 0, 0, _NAN, _NAN, 0.0, 0.0, _NAN, _NAN, _NAN,
            ic_m, ic_md, ic_c, validas, 0.0, 0.0,
        )
    return ResumoGrupo(
        motivo=motivo,
        n=int(v.size),
        dias=len(set(dias_g)),
        media=float(v.mean()),
        mediana=float(np.percentile(v, 50, method="linear")),
        soma=float(v.sum()),
        contribuicao=contribuicao(v, n_total=n_total),
        frac_pos=float((v > 0).sum() / v.size),
        p25=float(np.percentile(v, 25, method="linear")),
        p75=float(np.percentile(v, 75, method="linear")),
        ic_media=ic_m,
        ic_mediana=ic_md,
        ic_contribuicao=ic_c,
        reamostragens_validas=validas,
        contrib_decil_sup=contribuicao_decil(v, n_total=n_total, alto=True),
        contrib_decil_inf=contribuicao_decil(v, n_total=n_total, alto=False),
    )


def decompoe(
    dias: Sequence[str],
    motivos: Sequence[str],
    valores: np.ndarray,
    *,
    grupos: Sequence[str] = MOTIVOS,
    reamostragens: int = 20_000,
    seed: int = 20260910,
) -> tuple[dict[str, ResumoGrupo], ResumoGrupo]:
    """A tabela do brief: um :class:`ResumoGrupo` por motivo, mais o total.

    ``reamostragens = 0`` devolve a tabela **sem** IC (todos `nan`) — usado nos
    testes de aritmetica, onde o bootstrap nao e o que esta sendo afirmado.
    """
    v = np.asarray(valores, dtype=float)
    dias = list(dias)
    motivos = list(motivos)
    n_total = int(v[~np.isnan(v)].size)
    if n_total == 0:
        raise ValueError("populacao vazia: nao ha Delta a decompor")

    b = (
        bootstrap_conjunto(
            dias, motivos, v, grupos=grupos, reamostragens=reamostragens, seed=seed
        )
        if reamostragens
        else None
    )
    ic_m = b.ic_media_por_grupo if b else {}
    ic_md = b.ic_mediana_por_grupo if b else {}
    ic_c = b.ic_contribuicao_por_grupo if b else {}
    validas = b.validas_por_grupo if b else {}

    saida: dict[str, ResumoGrupo] = {}
    for g in grupos:
        mascara = np.array([m == g for m in motivos], dtype=bool)
        saida[g] = _resumo(
            g,
            [d for d, keep in zip(dias, mascara, strict=True) if keep],
            v[mascara],
            n_total=n_total,
            ic_m=ic_m.get(g, (_NAN, _NAN)),
            ic_md=ic_md.get(g, (_NAN, _NAN)),
            ic_c=ic_c.get(g, (_NAN, _NAN)),
            validas=validas.get(g, 0),
        )
    total = _resumo(
        "todos",
        dias,
        v,
        n_total=n_total,
        ic_m=_ic(b.amostras_total) if b else (_NAN, _NAN),
        ic_md=(_NAN, _NAN),
        ic_c=_ic(b.amostras_total) if b else (_NAN, _NAN),
        validas=int((~np.isnan(b.amostras_total)).sum()) if b else 0,
    )
    return saida, total


# --------------------------------------------------------------------------
# Excursoes de CLOSES (auxiliares), com janelas antes/depois da saida
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class Vela:
    """Uma vela de 1 min do caminho pos-entrada.

    ``minuto`` e o instante em que ela **FECHA**, contado da entrada: a vela
    ``m`` abre em ``entry_ts + (m-1) min`` e fecha em ``entry_ts + m min``. E a
    mesma convencao de ``curva.endpoint_open_time`` do D-P23, escrita do outro
    lado: la o indice era o ``open_time``, aqui e o fechamento.
    """

    minuto: int
    close: float
    is_final: bool = True


@dataclass(frozen=True)
class Excursao:
    n: int
    mfe: float
    mae: float
    minuto_mfe: int | None
    minuto_mae: int | None


def janela_de_closes(velas: Iterable[Vela], *, ini: int, fim: int) -> list[Vela]:
    """As velas **finais** cujo fechamento cai em ``[ini, fim]`` minutos, em ordem.

    Vela nao final **nao existe** para esta leitura (PIPELINE §2,
    anti-look-ahead). Janela invertida (``ini > fim``) e uma janela **vazia** —
    o caso da saida por time-stop, em que nao ha nenhum minuto depois da saida —
    e nao um erro.
    """
    return sorted(
        (v for v in velas if v.is_final and ini <= v.minuto <= fim),
        key=lambda v: v.minuto,
    )


def mfe_mae_closes(
    velas: Iterable[Vela],
    *,
    entry_open: float,
    atr: float | None = None,
    ini: int,
    fim: int,
    unidade: str = "atr",
) -> Excursao:
    """Maximo e minimo do **retorno de fechamento** na janela, com sinal.

    Nao e "o maximo que a posicao viu": o OHLC nao revela ordem intrabar e esta
    leitura nem olha para `high`/`low`. O nome carrega "closes" exatamente para
    que a distincao nao se perca (MUST-FIX 2 da Astra).
    """
    if unidade == "atr":
        if atr is None:
            raise ValueError("unidade 'atr' exige o ATR congelado da decisao")
        conv = lambda p: ret_atr(entry_open=entry_open, preco=p, atr=atr)  # noqa: E731
        conv(float(entry_open))  # valida o ATR antes de qualquer janela vazia
    elif unidade == "pct":
        conv = lambda p: ret_pct(entry_open=entry_open, preco=p)  # noqa: E731
        conv(float(entry_open))
    else:
        raise ValueError(f"unidade desconhecida: {unidade!r}")

    dentro = janela_de_closes(velas, ini=ini, fim=fim)
    if not dentro:
        return Excursao(0, _NAN, _NAN, None, None)
    rets = [(v.minuto, conv(v.close)) for v in dentro]
    m_mfe, mfe = max(rets, key=lambda par: (par[1], -par[0]))
    m_mae, mae = min(rets, key=lambda par: (par[1], par[0]))
    return Excursao(len(rets), float(mfe), float(mae), int(m_mfe), int(m_mae))
