"""R72 passo 1 — censo de oscilacoes completas na janela de 5 min apos a entrada.

Definicao verbatim do pre-registo de H-009: uma oscilacao completa e uma **queda >= X %
a partir da maxima corrente** seguida de uma **recuperacao >= X % dentro de N s**.

O censo e retrospectivo por natureza (contar o que a fita fez) — mas o detector e escrito
como uma maquina de estados de uma passagem que so olha para tras, porque e exatamente o
mesmo codigo que o simulador de politica usa para decidir. `swing_events` devolve os
instantes em que cada perna FECHA, e e nesses instantes (nunca antes) que a politica pode
agir: e essa a armadilha que matou a primeira versao do R66.
"""

from __future__ import annotations

from decimal import Decimal


def swing_events(points, x_pct: Decimal, n_s: float):
    """Percorre `points` = [(t, ..., mark)] e devolve os eventos da maquina de estados.

    Devolve lista de dicts com:
      kind='dip_open'  t=instante em que a marca cruza abaixo de H*(1-X); low=marca
      kind='swing'     t=instante em que a marca cruza acima de L*(1+X) dentro de N s
      kind='abort'     t=instante em que os N s passam sem recuperacao

    Cada evento so e emitido no ponto em que a condicao ja e verdadeira com dados <= t.
    """
    x = Decimal(x_pct) / 100
    out = []
    if not points:
        return out
    high = points[0][-1]
    state = "up"
    low = None
    dip_t = None
    for p in points:
        t, mark = p[0], p[-1]
        if mark <= 0:
            continue
        if state == "up":
            if mark > high:
                high = mark
            elif Decimal(mark) <= Decimal(high) * (1 - x):
                state = "down"
                low = mark
                dip_t = t
                out.append(dict(kind="dip_open", t=t, low=mark, high=high))
        else:
            if (t - dip_t).total_seconds() > n_s:
                out.append(dict(kind="abort", t=t, low=low))
                state = "up"
                high = mark
                continue
            if mark < low:
                low = mark
            if Decimal(mark) >= Decimal(low) * (1 + x):
                out.append(dict(kind="swing", t=t, low=low, mark=mark,
                                secs=(t - dip_t).total_seconds()))
                state = "up"
                high = mark
    return out


def count_swings(points, x_pct: Decimal, n_s: float) -> int:
    return sum(1 for e in swing_events(points, x_pct, n_s) if e["kind"] == "swing")


def quantiles(values):
    if not values:
        return (0.0, 0.0, 0.0)
    v = sorted(values)

    def q(p):
        i = p * (len(v) - 1)
        lo, hi = int(i), min(int(i) + 1, len(v) - 1)
        return v[lo] + (v[hi] - v[lo]) * (i - lo)

    return (q(0.25), q(0.5), q(0.75))
