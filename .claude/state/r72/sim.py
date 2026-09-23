"""R72 passo 2/3 — simulador da politica de giros contra a regra atual, na mesma fita.

Contabilidade (declarada, para nao haver custo contado duas vezes):

  * A **marca** (`load.sell_net`, taxa de curva 1,25 %) e o que a mesa ve e o que dispara os
    gatilhos — igual a R64/R65.
  * Uma **transacao** move a curva pelo produto constante (e esse o modelo de derrapagem do
    R64: vender 0,07 SOL de lote numa curva de ~30-70 SOL move o preco, e `gross_*` calcula
    isso exatamente) e paga um custo explicito de `c/2` por perna. `c` = 2,23 % por ida e
    volta (R65 §3, sem o aluguel da ATA, que agora e reembolsado). Sensibilidade: 2,5 % e 3 %.
  * A entrada JA pagou a sua taxa nos dados (`fill.buy_total_lamports`), por isso o braco
    "regra atual" (entrada + 1 saida) paga exatamente `c` no total, e um braco de giros com
    k voltas extra paga mais `k * c`.

Anti-antecipacao: o unico dado que uma decisao no ponto `i` ve e `pontos[0..i]`. O fill usa as
reservas do ultimo ponto com `t <= t_gatilho + latencia` e o `Guard` recusa qualquer fill cujo
indice seja anterior ao do gatilho. O braco `cheat` (que olha o maximo futuro) existe de
proposito como controlo de fuga: se a guarda estivesse solta, o braco causal empataria com ele.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from load import FEE, WINDOW_S, sell_net, window

COST = Decimal("0.0223")  # ida e volta, R65 sec.3 sem aluguel de ATA
LATENCY_S = 1.6  # R62 sec.5: mediana gatilho -> pouso 1,64 s
TARGET_X = Decimal("1.15")  # comparador CONGELADO (must-fix 4 da Astra): a regra atual
TRAILING = Decimal("0.10")  # de 19-23/09, e nao os parametros historicos de cada posicao


class LookAheadError(AssertionError):
    pass


class Guard:
    """Recusa qualquer fill anterior ao gatilho e qualquer leitura a frente do cursor."""

    def __init__(self):
        self.legs = 0

    def check(self, trigger_i: int, fill_i: int, trigger_t, fill_t, latency_s: float):
        if fill_i < trigger_i:
            raise LookAheadError("fill %d antes do gatilho %d" % (fill_i, trigger_i))
        if fill_t > trigger_t + timedelta(seconds=latency_s):
            raise LookAheadError("fill %s depois de gatilho+latencia" % fill_t)
        self.legs += 1


def gross_sell(vsol: int, vtok: int, amount: int) -> int:
    if amount <= 0 or vtok <= 0:
        return 0
    return vsol - (vsol * vtok) // (vtok + amount)


def gross_buy_tokens(vsol: int, vtok: int, lamports: int) -> int:
    if lamports <= 0 or vsol <= 0:
        return 0
    return vtok - (vsol * vtok) // (vsol + lamports)


def _fill_index(points, i: int, latency_s: float) -> int:
    """Indice do ultimo ponto com t <= t_i + latencia. So avanca — nunca olha para tras."""
    deadline = points[i][0] + timedelta(seconds=latency_s)
    j = i
    while j + 1 < len(points) and points[j + 1][0] <= deadline:
        j += 1
    return j


def _fill_time(points, i: int, latency_s: float):
    """RELOGIO DE EXECUCAO: a ordem pousa em t_gatilho + latencia, e nao no carimbo do
    ultimo estado conhecido da cadeia (must-fix 1 da Astra: usar points[j][0] como hora do
    pouso encurta o prazo da recompra em ate 1,6 s e PREJUDICA a politica de giros)."""
    return points[i][0] + timedelta(seconds=latency_s)


def _leg_sell(points, i, tokens, cost, latency_s, guard):
    j = _fill_index(points, i, latency_s)
    ft = _fill_time(points, i, latency_s)
    guard.check(i, j, points[i][0], points[j][0], latency_s)
    _t, vsol, vtok, _m = points[j]
    gross = gross_sell(vsol, vtok, tokens)
    return j, int(Decimal(gross) * (1 - cost / 2)), ft


def _leg_buy(points, i, cash, cost, latency_s, guard):
    j = _fill_index(points, i, latency_s)
    ft = _fill_time(points, i, latency_s)
    guard.check(i, j, points[i][0], points[j][0], latency_s)
    _t, vsol, vtok, _m = points[j]
    spend = int(Decimal(cash) * (1 - cost / 2))
    return j, gross_buy_tokens(vsol, vtok, spend), ft


def _leg_sell_at_deadline(points, end_i, tokens, cost, latency_s, seconds, entry_bt, guard):
    """Saida por tempo: o gatilho e o instante `entry+seconds`, nao o ultimo ponto antes dele.

    Astra (2.a ronda): com o ultimo ponto aos 290 s e o seguinte aos 301 s, disparar no ponto
    dos 290 s liquidava aos 291,6 s e ignorava o estado dos 301 s — liquidacao retroativa.
    Aqui o pouso e `entry + seconds + latencia` e usa o ultimo estado conhecido ate la.
    """
    deadline = entry_bt + timedelta(seconds=seconds)
    fill_t = deadline + timedelta(seconds=latency_s)
    j = end_i
    while j + 1 < len(points) and points[j + 1][0] <= fill_t:
        j += 1
    guard.check(end_i, j, deadline, points[j][0], latency_s)
    _t, vsol, vtok, _m = points[j]
    gross = gross_sell(vsol, vtok, tokens)
    return j, int(Decimal(gross) * (1 - cost / 2)), fill_t


def simulate_scalp(P, x_pct, n_s, cost=COST, latency_s=LATENCY_S, seconds=WINDOW_S):
    """Politica do Everton: vender a cada repique de X %, recomprar a cada queda de X %.

    Referencia do repique = marca do ultimo negocio nosso. Referencia da queda = valor do
    lote no instante da venda. Se a queda de X % nao vier em N s depois da venda, ficamos
    de fora ate ao fim da janela (variante declarada: nao ha "correr atras").
    """
    pts = window(P, seconds, tail_s=latency_s + 2)
    guard = Guard()
    out = dict(x=x_pct, n=n_s, legs=0, cycles=0, rebuys=0, drains=0, abandoned=False,
               guard=guard, ok=False, censored=False)
    last_trigger = P["entry_bt"] + timedelta(seconds=seconds)
    live = [k for k, p in enumerate(pts) if p[0] <= last_trigger]
    if len(live) < 3:
        return out
    out["ok"] = True
    x = Decimal(x_pct) / 100
    tokens = P["tokens"]
    sold_tokens = P["tokens"]
    cash = 0
    ref = pts[0][3]  # marca do lote na entrada
    state, sell_t, sell_ref, buy_cash = "hold", None, None, None
    rebuy_log = []
    i = 0
    end_i = live[-1]
    while i <= end_i:
        t, vsol, vtok, _m = pts[i]
        if state == "hold":
            mark = sell_net(vsol, vtok, tokens)
            if ref and Decimal(mark) >= Decimal(ref) * (1 + x):
                j, proceeds, ft = _leg_sell(pts, i, tokens, cost, latency_s, guard)
                sold_tokens = tokens
                cash, tokens = proceeds, 0
                state, sell_t = "flat", ft
                sell_ref = sell_net(pts[j][1], pts[j][2], sold_tokens)
                out["legs"] += 1
                i = j + 1
                continue
        else:
            # o que o lote VENDIDO valeria se nao tivessemos vendido; o prazo N conta do POUSO
            virt = sell_net(vsol, vtok, sold_tokens)
            if (t - sell_t).total_seconds() > n_s:
                out["abandoned"] = True
                break
            if sell_ref and Decimal(virt) <= Decimal(sell_ref) * (1 - x):
                buy_cash = cash
                j, got, _ft = _leg_buy(pts, i, cash, cost, latency_s, guard)
                if got <= 0:
                    break
                tokens, cash = got, 0
                ref = sell_net(pts[j][1], pts[j][2], tokens)
                state = "hold"
                out["legs"] += 1
                out["cycles"] += 1
                out["rebuys"] += 1
                rebuy_log.append(dict(i=j, paid=buy_cash, tokens=got, sold=sold_tokens))
                i = j + 1
                continue
        i += 1
    if state == "hold" and tokens > 0:
        j, proceeds, _ft = _leg_sell_at_deadline(
            pts, end_i, tokens, cost, latency_s, seconds, P["entry_bt"], guard)
        cash += proceeds
        out["legs"] += 1
        out["censored"] = end_i == len(pts) - 1
    out["final"] = cash
    for rb in rebuy_log:
        worth = sell_net(pts[-1][1], pts[-1][2], rb["tokens"])
        for k in range(rb["i"], len(pts)):
            worth = min(worth, sell_net(pts[k][1], pts[k][2], rb["tokens"]))
        rb["worst"] = worth
        rb["drain"] = worth <= rb["paid"] // 2
    out["rebuy_log"] = rebuy_log
    out["drains"] = sum(1 for rb in rebuy_log if rb["drain"])
    return out


def simulate_current(P, cost=COST, latency_s=LATENCY_S, seconds=WINDOW_S,
                     target_x=None, trailing=None):
    """Regra atual da mesa: alvo 1,15x, trailing 10 % armado na entrada, max_hold 300 s."""
    pts = window(P, seconds, tail_s=latency_s + 2)
    guard = Guard()
    last_trigger = P["entry_bt"] + timedelta(seconds=seconds)
    live = [k for k, p in enumerate(pts) if p[0] <= last_trigger]
    out = dict(legs=0, reason=None, guard=guard, ok=len(live) >= 3)
    if not out["ok"]:
        return out
    tx = Decimal(TARGET_X if target_x is None else target_x)
    tr = Decimal(TRAILING if trailing is None else trailing)
    spent = P["spent"]
    tokens = P["tokens"]
    high = pts[0][3]
    target = int(Decimal(spent) * tx)
    for i in live:
        _t, vsol, vtok, _m = pts[i]
        mark = sell_net(vsol, vtok, tokens)
        if mark > high:
            high = mark
        hit = mark >= target
        trail = mark <= int(Decimal(high) * (1 - tr))
        if hit or trail:
            _j, proceeds, _ft = _leg_sell(pts, i, tokens, cost, latency_s, guard)
            out.update(final=proceeds, legs=1, reason="target" if hit else "trailing")
            return out
    _j, proceeds, _ft = _leg_sell_at_deadline(
        pts, live[-1], tokens, cost, latency_s, seconds, P["entry_bt"], guard)
    out.update(final=proceeds, legs=1, reason="time_stop")
    return out


def simulate_cheat(P, cost=COST, seconds=WINDOW_S):
    """CONTROLO DE FUGA — vende no maximo da janela olhando o futuro. Nao e uma politica."""
    pts = window(P, seconds)
    if len(pts) < 3:
        return dict(ok=False)
    best = max(range(len(pts)), key=lambda k: sell_net(pts[k][1], pts[k][2], P["tokens"]))
    vsol, vtok = pts[best][1], pts[best][2]
    gross = gross_sell(vsol, vtok, P["tokens"])
    return dict(ok=True, final=int(Decimal(gross) * (1 - cost / 2)), legs=1)


def per_sol(res, P, cost=COST):
    """PnL liquido por SOL arriscado.

    `P["spent"]` e `fill.buy_total_lamports`: a taxa da perna de ENTRADA ja esta la dentro
    (must-fix 3 da Astra — a versao anterior cobrava-a outra vez). Cada braco paga entao
    so `c/2` nas pernas que simula: o braco "regra atual" paga entrada (ja nos dados) +
    c/2 na saida = uma ida e volta; um braco de giros com k voltas extra paga mais k*c.
    """
    if not res.get("ok") or res.get("final") is None:
        return None
    size = Decimal(P["spent"])
    return (Decimal(res["final"]) - size) / size


__all__ = ["COST", "FEE", "LATENCY_S", "Guard", "LookAheadError", "per_sol",
           "simulate_cheat", "simulate_current", "simulate_scalp"]
