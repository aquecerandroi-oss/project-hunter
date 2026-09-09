"""Simulador de carteira — a família `mean_reversion` como UMA carteira sob o motor real (T3.60).

Não é código de produção: mora em `.claude/state/exp-drafts/` e responde a uma
única pergunta desta nota — *quantos R ÚNICOS por dia sobram depois da
deduplicação, da concorrência, do risco agregado, do teto de participação e do
kill switch, e quanto vale 1 R em reais no tamanho que o motor de fato aprova?*

**O motor é o de verdade.** Nada aqui reimplementa limite nenhum: os tetos, o
sizing, a ordem dos checks e a escada do kill switch vêm de
`packages/risk-core/hunter_risk` — `evaluate`, `assess`, `resume`,
`sao_paulo_day_start_utc`, `advance_peak` e o objeto `PAPER_V1`. As variações de
configuração são feitas por `RiskLimits.model_validate` sobre o
`PAPER_V1.model_dump()`, então **nenhum limiar é redigitado**: se o Everton
mudar um número em `limits.py`, este simulador muda junto.

O que este arquivo faz é só o que o motor puro não pode fazer sozinho, porque
`evaluate` é função dos seus argumentos e nada mais (docs/ARCHITECTURE.md §6):
manter o relógio, o caixa, as posições, a âncora do dia de São Paulo, a trava do
kill switch e o orçamento móvel de participação de 60 s — e montar, para cada
sinal, os insumos que o motor exige.

TRÊS INSUMOS QUE A HISTÓRIA NÃO TEM, E COMO ELES SÃO DECLARADOS
---------------------------------------------------------------
1. **Livro.** Não guardamos profundidade histórica. O book entregue é um nível
   único, fundo, no preço-limite do `max_slippage_pct`: `book_depth` e
   `slippage_estimate` **nunca mordem**. Consequência declarada: todo tamanho
   deste simulador é um **teto superior** do que o motor aprovaria com o livro
   real.
2. **Spread.** Também não é histórico. Usa-se o `spread_bps` da própria hipótese
   de custo do Lab (2 bps), que é menor que `max_spread_pct` (5 bps), então o
   check `spread` passa sempre. Mesma consequência: teto superior.
3. **β contra o BTC.** Não existe em código (KB-0071). Entrega-se `value=0`,
   `validated=True`: o teto de β sai do mínimo por construção (`qty_by_beta` com
   β = 0 é `None`, sizing.py) e o agregado de β é 0 em vez de indefinido. Sem
   isso o motor rejeitaria **tudo** por `beta_validity`, e a pergunta do Everton
   ficaria sem resposta. É a única neutralização que muda o veredito de um check,
   e ela está publicada em cada linha do resultado (`beta_neutralizado=True`).

O DINHEIRO
----------
`r_net` do Lab tem denominador `risk` = |entrada − stop| em preço, **sem** custo
(contrato de `2026-09-08-00-base.sql`). Então o PnL de uma operação é

    pnl_quote = qty × risk × r_net = notional × risco_pct × r_net

e `R$ por 1 R = notional × risco_pct × câmbio`. É a mesma identidade da T3.48.
`r_net` já é líquido de spread, slippage, fee e funding, então o caixa é
debitado do notional na entrada e creditado de `notional + pnl` na saída — cobrar
custo de novo aqui seria cobrá-lo duas vezes.
"""

from __future__ import annotations

import csv
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo

from hunter_core.domain.enums import KillSwitchState, MarketType, TradeDirection
from hunter_core.strategies.envelope import AssumedCosts
from hunter_risk import (
    PAPER_V1,
    BetaEstimate,
    BookLevel,
    EntryProposal,
    KillSwitchInputs,
    MarketIdentity,
    MarketLiquidity,
    MarketSpec,
    OpenPosition,
    PortfolioState,
    ResumeAuthorization,
    RiskLimits,
    advance_peak,
    assess,
    evaluate,
    resume,
    sao_paulo_day_start_utc,
)

ZERO = Decimal(0)
SAO_PAULO = ZoneInfo("America/Sao_Paulo")
CAMBIO_BRL = Decimal("5.1725")
"""R$/USDT implícito do seed da carteira: 19.333,0111164813 USDT = R$100.000
(T3.48). Não é cotação de mercado; é a mesma constante que a proposta usa dos
dois lados, para R$ e USDT nunca discordarem."""

EQUITY_100K = Decimal("19333.0111164813")
"""`portfolios.initial_capital` da carteira paper, lido na VPS."""

EXCHANGE = "binance"
QUOTE = "USDT"
PORTFOLIO_ID = uuid.UUID("01a07a1e-f6ae-7366-a7fe-ab3d9c83d488")
"""O id real da carteira paper — só para a decisão carregar a identidade certa."""


# --------------------------------------------------------------------------- #
# População
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Sinal:
    """Uma decisão do Lab com desfecho terminal, com tudo o que o motor precisa."""

    signal_id: str
    versao: str
    ordem_versao: int
    coorte: str
    symbol: str
    base_asset: str
    bar: datetime
    entry_ts: datetime
    exit_ts: datetime
    dia_br: str
    hora_br: int
    motivo: str
    r_net: Decimal
    entry_base: Decimal
    risk: Decimal
    risco_pct: Decimal
    min_notional: Decimal
    step_size: Decimal
    fee_bps: Decimal
    spread_bps: Decimal
    slippage_bps: Decimal
    vol_min_anterior: Decimal | None
    vol_mediana_30: Decimal | None
    barras_30: int
    vol_24h: Decimal | None
    barras_24h: int
    mae: Decimal | None
    mae_bar: datetime | None

    @property
    def chave_barra(self) -> tuple[str, datetime]:
        """A aposta: mercado × barra de origem. Duas versões aqui são a mesma aposta."""
        return (self.symbol, self.bar)

    @property
    def chave_hora(self) -> tuple[str, datetime]:
        """A aposta contada por hora — o corte mais duro do brief."""
        return (self.symbol, self.bar.replace(minute=0, second=0, microsecond=0))

    @property
    def custos(self) -> AssumedCosts:
        return AssumedCosts(
            spread_bps=self.spread_bps,
            slippage_bps=self.slippage_bps,
            fee_bps=self.fee_bps,
            max_entry_delay_s=120,
        )


def _dec(valor: str) -> Decimal | None:
    return None if valor == "" else Decimal(valor)


def _ts(valor: str) -> datetime | None:
    if valor == "":
        return None
    return datetime.strptime(valor, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)


def ler_populacao(caminho: str) -> list[Sinal]:
    """Lê o CSV de `2026-09-09-t360-q01-populacao-csv.sql`. Decimal desde a borda."""
    linhas: list[Sinal] = []
    with open(caminho, newline="", encoding="utf-8") as fh:
        for linha in csv.DictReader(fh):
            entrada = _ts(linha["entry_utc"])
            saida = _ts(linha["exit_utc"])
            barra = _ts(linha["bar_utc"])
            if entrada is None or saida is None or barra is None:
                continue
            linhas.append(
                Sinal(
                    signal_id=linha["signal_id"],
                    versao=linha["versao"],
                    ordem_versao=int(linha["versao_num"].lstrip("v")),
                    coorte=linha["coorte"],
                    symbol=linha["symbol"],
                    base_asset=linha["base_asset"],
                    bar=barra,
                    entry_ts=entrada,
                    exit_ts=saida,
                    dia_br=linha["dia_br"],
                    hora_br=int(linha["hora_br"]),
                    motivo=linha["motivo"],
                    r_net=Decimal(linha["r_net"]),
                    entry_base=Decimal(linha["entry_base"]),
                    risk=Decimal(linha["risk"]),
                    risco_pct=Decimal(linha["risco_pct"]),
                    min_notional=Decimal(linha["min_notional"]),
                    step_size=Decimal(linha["step_size"]),
                    fee_bps=Decimal(linha["fee_bps"]),
                    spread_bps=Decimal(linha["spread_bps"]),
                    slippage_bps=Decimal(linha["slippage_bps"]),
                    vol_min_anterior=_dec(linha["vol_min_anterior"]),
                    vol_mediana_30=_dec(linha["vol_mediana_30"]),
                    barras_30=int(linha["barras_30"] or 0),
                    vol_24h=_dec(linha["vol_24h"]),
                    barras_24h=int(linha["barras_24h"] or 0),
                    mae=_dec(linha["mae"]),
                    mae_bar=_ts(linha["mae_bar_utc"]),
                )
            )
    return linhas


# --------------------------------------------------------------------------- #
# Deduplicação: oito versões, uma aposta
# --------------------------------------------------------------------------- #
def deduplicar(
    sinais: list[Sinal], *, chave: Literal["barra", "hora"] = "barra"
) -> tuple[list[Sinal], dict[str, int]]:
    """Uma aposta por (mercado × barra) — **a versão mais antiga vence**.

    "Mais antiga" = o menor número de versão (v1 antes de v2), com desempate pelo
    `signal_id` para a escolha ser reprodutível byte a byte. É o critério que não
    olha o resultado: escolher a versão de melhor R seria escolher depois de ver a
    resposta. Devolve também quantas apostas cada versão levou.
    """
    grupos: dict[tuple[str, datetime], list[Sinal]] = defaultdict(list)
    for sinal in sinais:
        grupos[sinal.chave_barra if chave == "barra" else sinal.chave_hora].append(sinal)

    vencedores: list[Sinal] = []
    creditos: dict[str, int] = defaultdict(int)
    for grupo in grupos.values():
        vencedor = min(grupo, key=lambda s: (s.ordem_versao, s.signal_id))
        vencedores.append(vencedor)
        creditos[vencedor.versao] += 1
    vencedores.sort(key=lambda s: (s.entry_ts, s.ordem_versao, s.signal_id))
    return vencedores, dict(creditos)


# --------------------------------------------------------------------------- #
# Configuração
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Config:
    """Uma configuração de carteira. Os três primeiros campos são limites do perfil."""

    risk_per_trade_pct: Decimal = PAPER_V1.risk_per_trade_pct
    max_aggregate_planned_risk_pct: Decimal = PAPER_V1.max_aggregate_planned_risk_pct
    max_concurrent_positions: int = PAPER_V1.max_concurrent_positions
    equity_inicial: Decimal = EQUITY_100K
    roster: frozenset[str] | None = None
    """Versões admitidas; `None` = todas."""
    chave_dedupe: Literal["barra", "hora"] = "barra"
    marca: Literal["custo", "mae"] = "custo"
    """`custo`: posição aberta vale o que custou (o patrimônio só se move na saída).
    `mae`: a partir da barra de MAE a posição vale o pior que valeu — é o teste de
    estresse do kill switch, que com marca a custo nunca enxerga o intradia."""
    retomada_diaria: bool = False
    """Se `True`, tenta `hunter_risk.resume` na virada do dia de São Paulo. A
    retomada é **recusada pelo próprio motor** enquanto a avaliação automática
    ainda bloquear (§5), então isto não é um jeito de ignorar o kill switch."""

    def limites(self) -> RiskLimits:
        """`PAPER_V1` com os três campos trocados — validado, nunca redigitado."""
        base = PAPER_V1.model_dump(mode="json")
        base["risk_per_trade_pct"] = str(self.risk_per_trade_pct)
        base["max_aggregate_planned_risk_pct"] = str(self.max_aggregate_planned_risk_pct)
        base["max_concurrent_positions"] = self.max_concurrent_positions
        return RiskLimits.model_validate(base)

    @property
    def rotulo(self) -> str:
        risco = self.risk_per_trade_pct * 100
        agregado = self.max_aggregate_planned_risk_pct * 100
        return (
            f"risco {risco.normalize():f}% | agregado {agregado.normalize():f}% | "
            f"vagas {self.max_concurrent_positions}"
        )


# --------------------------------------------------------------------------- #
# Estado interno
# --------------------------------------------------------------------------- #
@dataclass
class _Aberta:
    sinal: Sinal
    position_id: uuid.UUID
    qty: Decimal
    notional: Decimal
    planned_risk: Decimal
    marca: Decimal


@dataclass(frozen=True)
class Registro:
    """O que aconteceu com uma aposta candidata."""

    sinal: Sinal
    aprovado: bool
    motivo_recusa: str | None
    """O **primeiro** check reprovado na ordem de `ENTRY_CHECKS`."""
    todos_reprovados: tuple[str, ...]
    binding_constraint: str | None
    notional: Decimal
    notional_rotulo: Decimal | None
    """O teto `risk_per_trade` sozinho — o "tamanho de rótulo" (0,25 % do patrimônio)."""
    qty: Decimal
    kill_switch: KillSwitchState
    multiplicador: Decimal


@dataclass(frozen=True)
class Fechada:
    sinal: Sinal
    notional: Decimal
    qty: Decimal
    pnl_quote: Decimal
    r_net: Decimal
    usdt_por_r: Decimal


@dataclass
class Resultado:
    config: Config
    registros: list[Registro] = field(default_factory=list)
    fechadas: list[Fechada] = field(default_factory=list)
    curva: list[tuple[datetime, Decimal]] = field(default_factory=list)
    """(instante, patrimônio) em cada evento — a curva sobre a qual o drawdown é medido."""
    latch_em: datetime | None = None
    latch_estado: KillSwitchState = KillSwitchState.ACTIVE
    retomadas: int = 0
    retomadas_recusadas: int = 0
    equity_final: Decimal = ZERO

    # -- agregados -------------------------------------------------------- #
    @property
    def aprovadas(self) -> list[Registro]:
        return [r for r in self.registros if r.aprovado]

    @property
    def recusas_por_motivo(self) -> dict[str, int]:
        contagem: dict[str, int] = defaultdict(int)
        for r in self.registros:
            if r.motivo_recusa is not None:
                contagem[r.motivo_recusa] += 1
        return dict(sorted(contagem.items(), key=lambda kv: -kv[1]))

    @property
    def limitantes(self) -> dict[str, int]:
        contagem: dict[str, int] = defaultdict(int)
        for r in self.aprovadas:
            if r.binding_constraint:
                contagem[r.binding_constraint] += 1
        return dict(sorted(contagem.items(), key=lambda kv: -kv[1]))

    @property
    def r_por_dia(self) -> dict[str, Decimal]:
        por_dia: dict[str, Decimal] = defaultdict(lambda: ZERO)
        for f in self.fechadas:
            por_dia[f.sinal.dia_br] += f.r_net
        return dict(sorted(por_dia.items()))

    @property
    def ops_por_dia(self) -> dict[str, int]:
        por_dia: dict[str, int] = defaultdict(int)
        for f in self.fechadas:
            por_dia[f.sinal.dia_br] += 1
        return dict(sorted(por_dia.items()))

    @property
    def pnl_total(self) -> Decimal:
        return sum((f.pnl_quote for f in self.fechadas), ZERO)

    @property
    def r_total(self) -> Decimal:
        return sum((f.r_net for f in self.fechadas), ZERO)

    def drawdown_maximo(self) -> tuple[Decimal, Decimal]:
        """(queda máxima em USDT, queda máxima em fração) sobre a curva de patrimônio."""
        pico = None
        pior_abs = ZERO
        pior_pct = ZERO
        for _, equity in self.curva:
            pico = equity if pico is None or equity > pico else pico
            queda = pico - equity
            if queda > pior_abs:
                pior_abs = queda
            if pico > 0 and queda / pico > pior_pct:
                pior_pct = queda / pico
        return pior_abs, pior_pct


# --------------------------------------------------------------------------- #
# Montagem dos insumos do motor
# --------------------------------------------------------------------------- #
def _identidade(sinal: Sinal) -> MarketIdentity:
    return MarketIdentity(
        exchange=EXCHANGE,
        symbol=sinal.symbol,
        market_type=MarketType.SPOT,
        base_asset=sinal.base_asset,
        quote_asset=QUOTE,
    )


def _liquidez(sinal: Sinal, as_of: datetime, participacao_usada: Decimal) -> MarketLiquidity:
    """O retrato do mercado no instante da entrada, com o volume REAL das velas.

    O livro é o único elemento sintético (ver o cabeçalho): um nível no preço
    limite de `max_slippage_pct`, fundo o bastante para nunca ser o gargalo.
    """
    preco = sinal.entry_base
    meio_spread = preco * sinal.spread_bps / Decimal(20000)
    teto_book = preco * (Decimal(1) + PAPER_V1.max_slippage_pct)
    return MarketLiquidity(
        market=_identidade(sinal),
        data_quality="ok",
        last_price=preco,
        mid_price=preco,
        best_bid=preco - meio_spread,
        best_ask=preco + meio_spread,
        price_ts=as_of,
        asks=(BookLevel(price=teto_book, qty=Decimal("1e12")),),
        book_ts=as_of,
        quote_volume_24h=sinal.vol_24h,
        last_minute_quote_volume=sinal.vol_min_anterior,
        median_30m_quote_volume=sinal.vol_mediana_30,
        volume_window_complete=sinal.barras_30 >= 30,
        participation_used_quote=participacao_usada,
        volume_ts=as_of,
        gap_state="ok",
        in_universe=True,
    )


def _proposta(sinal: Sinal) -> EntryProposal:
    return EntryProposal(
        proposal_id=uuid.uuid5(uuid.NAMESPACE_URL, f"t360:{sinal.signal_id}"),
        portfolio_id=PORTFOLIO_ID,
        market=_identidade(sinal),
        direction=TradeDirection.LONG,
        entry_ref=sinal.entry_base,
        stop=sinal.entry_base - sinal.risk,
        assumed_costs=sinal.custos,
        agent_enabled=True,
        signal_valid=True,
    )


def _beta(as_of: datetime) -> BetaEstimate:
    """β = 0 validado. Neutraliza o teto de β e o agregado — declarado no cabeçalho."""
    return BetaEstimate(value=ZERO, as_of=as_of, validated=True, bars=0)


# --------------------------------------------------------------------------- #
# O laço
# --------------------------------------------------------------------------- #
def simular(sinais: list[Sinal], cfg: Config) -> Resultado:
    """Repassa a família como UMA carteira, em ordem de tempo, sob o motor real."""
    limites = cfg.limites()
    elegiveis = [s for s in sinais if cfg.roster is None or s.versao in cfg.roster]
    candidatos, _ = deduplicar(elegiveis, chave=cfg.chave_dedupe)

    res = Resultado(config=cfg)
    cash = cfg.equity_inicial
    abertas: dict[uuid.UUID, _Aberta] = {}
    por_sinal: dict[str, uuid.UUID] = {}
    peak = cfg.equity_inicial
    dia_atual: str | None = None
    day_start_equity = cfg.equity_inicial
    latch = KillSwitchState.ACTIVE
    consumo: list[tuple[str, datetime, Decimal]] = []

    # eventos: (instante, prioridade, sequência, tipo, carga)
    eventos: list[tuple[datetime, int, int, str, object]] = []
    for i, s in enumerate(candidatos):
        eventos.append((s.entry_ts, 1, i, "entrada", s))
        eventos.append((s.exit_ts, 0, i, "saida", s))
        if cfg.marca == "mae" and s.mae_bar is not None and s.entry_ts < s.mae_bar < s.exit_ts:
            eventos.append((s.mae_bar, 0, i, "marca", s))
    eventos.sort(key=lambda e: (e[0], e[1], e[2]))

    def patrimonio() -> Decimal:
        return cash + sum((a.marca for a in abertas.values()), ZERO)

    for as_of, _, _, tipo, carga in eventos:
        sinal = carga  # type: ignore[assignment]
        assert isinstance(sinal, Sinal)

        # --- saída: libera vaga, realiza o resultado ---------------------- #
        if tipo == "saida":
            pid = por_sinal.pop(sinal.signal_id, None)
            if pid is not None:
                pos = abertas.pop(pid)
                pnl = pos.qty * sinal.risk * sinal.r_net
                cash += pos.notional + pnl
                res.fechadas.append(
                    Fechada(
                        sinal=sinal,
                        notional=pos.notional,
                        qty=pos.qty,
                        pnl_quote=pnl,
                        r_net=sinal.r_net,
                        usdt_por_r=pos.notional * sinal.risco_pct,
                    )
                )
        elif tipo == "marca":
            pid = por_sinal.get(sinal.signal_id)
            if pid is not None and sinal.mae is not None:
                pos = abertas[pid]
                pos.marca = pos.notional - pos.qty * sinal.mae

        equity = patrimonio()
        if equity <= 0:  # carteira zerada: o resto da simulação não tem sentido
            break
        peak = advance_peak(peak, equity)

        # --- âncora do dia de São Paulo ---------------------------------- #
        dia_br = as_of.astimezone(SAO_PAULO).strftime("%Y-%m-%d")
        if dia_br != dia_atual:
            dia_atual = dia_br
            day_start_equity = equity
            if cfg.retomada_diaria and latch is not KillSwitchState.ACTIVE:
                estado = _estado(as_of, equity, cash, peak, day_start_equity, abertas, latch)
                avaliacao = assess(estado, limites, KillSwitchInputs(portfolio=latch))
                try:
                    latch = resume(
                        latch,
                        ResumeAuthorization(
                            authorized_by="everton (simulado)",
                            portfolio_id=PORTFOLIO_ID,
                            from_state=latch,
                            to_state=KillSwitchState.ACTIVE,
                            reason="retomada manual da virada do dia (cenário declarado)",
                        ),
                        avaliacao,
                        PORTFOLIO_ID,
                    )
                    res.retomadas += 1
                except ValueError:
                    res.retomadas_recusadas += 1

        estado = _estado(as_of, equity, cash, peak, day_start_equity, abertas, latch)
        res.curva.append((as_of, equity))

        # --- a trava durável: assess só sobe, e nunca desce sozinha ------- #
        avaliacao = assess(estado, limites, KillSwitchInputs(portfolio=latch))
        if avaliacao.automatic is KillSwitchState.TRADING_DISABLED and latch is not (
            KillSwitchState.TRADING_DISABLED
        ):
            latch = KillSwitchState.TRADING_DISABLED
            if res.latch_em is None:
                res.latch_em = as_of
                res.latch_estado = latch
            estado = _estado(as_of, equity, cash, peak, day_start_equity, abertas, latch)

        if tipo != "entrada":
            continue

        # --- entrada: o motor decide ------------------------------------- #
        consumo = [c for c in consumo if as_of - c[1] < timedelta(seconds=60)]
        usada = sum((c[2] for c in consumo if c[0] == sinal.symbol), ZERO)
        decisao = evaluate(
            _proposta(sinal),
            estado,
            limites,
            _liquidez(sinal, as_of, usada),
            KillSwitchInputs(portfolio=latch),
            _beta(as_of),
            spec=MarketSpec(
                market=_identidade(sinal),
                step_size=sinal.step_size,
                min_notional=sinal.min_notional,
            ),
        )
        reprovados = tuple(c.name for c in decisao.checks if not c.passed)
        rotulo = None
        if decisao.sizing is not None:
            rotulo = next(
                (c.notional for c in decisao.sizing.caps if c.name == "risk_per_trade"), None
            )
        res.registros.append(
            Registro(
                sinal=sinal,
                aprovado=decisao.approved,
                motivo_recusa=reprovados[0] if reprovados else None,
                todos_reprovados=reprovados,
                binding_constraint=(
                    decisao.sizing.binding_constraint if decisao.sizing is not None else None
                ),
                notional=decisao.sizing.notional if decisao.sizing is not None else ZERO,
                notional_rotulo=rotulo,
                qty=decisao.sizing.qty if decisao.sizing is not None else ZERO,
                kill_switch=decisao.effective_kill_switch,
                multiplicador=(
                    decisao.sizing.kill_switch_multiplier if decisao.sizing is not None else ZERO
                ),
            )
        )
        if not decisao.approved or decisao.sizing is None:
            continue

        pid = uuid.uuid4()
        abertas[pid] = _Aberta(
            sinal=sinal,
            position_id=pid,
            qty=decisao.sizing.qty,
            notional=decisao.sizing.notional,
            planned_risk=decisao.sizing.planned_risk_quote,
            marca=decisao.sizing.notional,
        )
        por_sinal[sinal.signal_id] = pid
        cash -= decisao.sizing.notional
        consumo.append((sinal.symbol, as_of, decisao.sizing.notional))

    res.equity_final = cash + sum((a.marca for a in abertas.values()), ZERO)
    res.latch_estado = latch
    return res


def _estado(
    as_of: datetime,
    equity: Decimal,
    cash: Decimal,
    peak: Decimal,
    day_start_equity: Decimal,
    abertas: dict[uuid.UUID, _Aberta],
    latch: KillSwitchState,
) -> PortfolioState:
    """O `PortfolioState` do motor. Nenhum agregado é passado pronto — §1 do contrato."""
    del latch
    return PortfolioState(
        portfolio_id=PORTFOLIO_ID,
        as_of=as_of,
        equity=equity,
        cash=max(ZERO, cash),
        peak_equity=advance_peak(peak, equity),
        day_start_equity=day_start_equity,
        day_start_utc=sao_paulo_day_start_utc(as_of),
        open_positions=tuple(
            OpenPosition(
                position_id=a.position_id,
                market=_identidade(a.sinal),
                qty=a.qty,
                notional=a.marca,
                planned_risk_quote=a.planned_risk,
                beta_btc=ZERO,
            )
            for a in abertas.values()
        ),
        pending_entries=(),
        marks_complete=True,
        is_active=True,
    )
