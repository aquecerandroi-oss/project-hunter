"""R74 — H-011, onde deve ficar o alvo: motor de saida causal e as politicas da grade.

Reaproveita, sem reescrever, o carregador e as pernas do R72 (`.claude/state/r72/`):
  * `load.window` (cauda de 1,6 s + 2 s para o pouso terminal),
  * `sim._leg_sell` (relogio de execucao = gatilho + latencia, `Guard` que recusa pouso
    anterior ao gatilho), `sim._leg_sell_at_deadline` (gatilho terminal = entrada + 300 s),
  * `sim.per_sol` (a entrada ja pagou a sua taxa; cada saida paga c/2).

O que e novo aqui e so a forma: a politica deixa de ser uma funcao que ve a lista inteira de
pontos e passa a ser um objeto que recebe uma `View` presa ao cursor. Ler um indice a frente do
cursor levanta `LookAheadError` — a guarda e estrutural, nao disciplina. O recuo de 10 % armado
na entrada e o tempo maximo de 300 s ficam no motor, congelados na regra da mesa, iguais para
todas as politicas.

Politicas:
  * `Target(tx)`     — vende quando a marca do lote >= custo * tx (regra atual com tx = 1,15).
  * `FirstPop(x)`    — pre-registo H-011: "primeiro repique de X % apos uma queda": queda >= X %
                       a partir da maxima corrente, depois recuperacao >= X % a partir do fundo;
                       vende e nao volta. Sem prazo N (a fila nao o fixa); o recuo e os 300 s
                       continuam armados.
  * `EntryPop(x)`    — DIAGNOSTICO: a regra que o R72 realmente mediu no fragmento (o primeiro
                       gatilho de venda do `simulate_scalp` e marca >= marca_de_entrada * (1+X),
                       sem exigir queda). Nao e a politica pre-registada.

Medidas ex post (fora da decisao, depois de ela estar tomada): quanto fica na mesa.
"""

from __future__ import annotations

import sys
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

R72 = Path(__file__).resolve().parent.parent / "r72"
if str(R72) not in sys.path:
    sys.path.insert(0, str(R72))

from load import WINDOW_S, window  # noqa: E402
from sim import (  # noqa: E402
    COST,
    LATENCY_S,
    TRAILING,
    Guard,
    LookAheadError,
    _leg_sell,
    _leg_sell_at_deadline,
    gross_sell,
    per_sol,
)

CONTROL_X = Decimal("1.15")


class View:
    """Janela de leitura presa ao cursor: `view[k]` com k > cursor levanta LookAheadError."""

    def __init__(self, pts):
        self._p = pts
        self.cursor = -1

    def __getitem__(self, k):
        if not isinstance(k, int):
            raise LookAheadError("fatias proibidas na View (espreitariam o futuro)")
        if k < 0:
            k += self.cursor + 1
        if k < 0 or k > self.cursor:
            raise LookAheadError("leitura do ponto %d com cursor em %d" % (k, self.cursor))
        return self._p[k]

    def __len__(self):
        return self.cursor + 1


class Target:
    def __init__(self, tx):
        self.tx = Decimal(str(tx))
        self.name = "alvo %sx" % self.tx
        self.level = 0

    def reset(self, spent, mark0):
        self.level = int(Decimal(spent) * self.tx)

    def step(self, view, i):
        return "policy" if view[i][3] >= self.level else None


class FirstPop:
    """Queda >= X % da maxima corrente, depois recuperacao >= X % do fundo: vende e sai."""

    def __init__(self, x_pct):
        self.x = Decimal(str(x_pct)) / 100
        self.name = "repique %s%%" % x_pct
        self.high = self.low = 0
        self.down = False

    def reset(self, spent, mark0):
        self.high, self.low, self.down = mark0, 0, False

    def step(self, view, i):
        mark = view[i][3]
        if not self.down:
            if mark > self.high:
                self.high = mark
            elif Decimal(mark) <= Decimal(self.high) * (1 - self.x):
                self.down, self.low = True, mark
            return None
        if mark < self.low:
            self.low = mark
            return None
        return "policy" if Decimal(mark) >= Decimal(self.low) * (1 + self.x) else None


class EntryPop:
    """DIAGNOSTICO: o primeiro gatilho de venda do R72 (marca >= marca de entrada * (1+X))."""

    def __init__(self, x_pct):
        self.x = Decimal(str(x_pct)) / 100
        self.name = "R72 +%s%% da marca" % x_pct
        self.ref = 0

    def reset(self, spent, mark0):
        self.ref = mark0

    def step(self, view, i):
        return "policy" if Decimal(view[i][3]) >= Decimal(self.ref) * (1 + self.x) else None


def _after_exit(P, pts, ft, final, tokens, cost, latency_s, seconds):
    """Ex post: o que o MESMO lote renderia vendido depois do nosso pouso, dentro da janela.

    `left_max` = max(0, melhor venda liquida apos o pouso - o que recebemos) — teto oraculo,
                 ninguem o captura; diz se o alvo e cedo (grande) ou tarde (pequeno).
    `left_end` = venda liquida no fim da janela (entrada + 300 s + latencia) - o que recebemos,
                 com sinal; e o "se tivessemos segurado ate ao fim a partir dali".
    Ambos em lamports; so leem pontos com t > pouso e t <= entrada + 300 s + latencia.
    """
    end = P["entry_bt"] + timedelta(seconds=seconds + latency_s)
    after = [p for p in pts if ft < p[0] <= end]
    if not after:
        return None, None  # sem observacao depois do pouso: indisponivel, nao zero (Astra)
    net = [int(Decimal(gross_sell(p[1], p[2], tokens)) * (1 - cost / 2)) for p in after]
    return max(0, max(net) - final), net[-1] - final


def run_exit(P, policy, cost=COST, latency_s=LATENCY_S, trailing=TRAILING, seconds=WINDOW_S):
    """Uma saida: a politica, o recuo de 10 % armado na entrada e o tempo maximo de 300 s.

    `trailing=None` desliga o recuo (so em diagnostico declarado).
    """
    pts = window(P, seconds, tail_s=latency_s + 2)
    last_trigger = P["entry_bt"] + timedelta(seconds=seconds)
    live = [k for k, p in enumerate(pts) if p[0] <= last_trigger]
    # elegibilidade SEMPRE na janela de 300 s: um max_hold curto (H-012) nao pode mudar a populacao
    if len(window(P, WINDOW_S)) < 3:
        return dict(ok=False)
    guard, view, tokens = Guard(), View(pts), P["tokens"]
    tr = None if trailing is None else Decimal(trailing)
    view.cursor = 0
    # Astra (pre-corrida): passar `P` ao reset deixava a politica ler `P["path"]` inteiro e
    # contornar a View. O reset recebe so dois inteiros do instante da entrada.
    policy.reset(int(P["spent"]), int(pts[0][3]))
    high = pts[0][3]
    for i in live:
        view.cursor = i
        mark = view[i][3]
        if mark > high:
            high = mark
        why = policy.step(view, i)
        if why is None and tr is not None and mark <= int(Decimal(high) * (1 - tr)):
            why = "trailing"
        if why:
            j, final, ft = _leg_sell(pts, i, tokens, cost, latency_s, guard)
            break
    else:
        why = "time_stop"
        j, final, ft = _leg_sell_at_deadline(
            pts, live[-1], tokens, cost, latency_s, seconds, P["entry_bt"], guard)
    left_max, left_end = _after_exit(P, pts, ft, final, tokens, cost, latency_s, seconds)
    res = dict(ok=True, final=final, reason=why, fill_j=j, legs=guard.legs,
               hold_s=(ft - P["entry_bt"]).total_seconds(),
               left_max=left_max, left_end=left_end)
    res["pnl"] = per_sol(res, P)
    size = Decimal(P["spent"])
    res["left_max_pct"] = None if left_max is None else Decimal(left_max) / size
    res["left_end_pct"] = None if left_end is None else Decimal(left_end) / size
    return res


__all__ = ["CONTROL_X", "COST", "LATENCY_S", "EntryPop", "FirstPop", "LookAheadError",
           "Target", "View", "run_exit"]
