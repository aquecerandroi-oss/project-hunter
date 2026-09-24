"""R77 / H-016 — regra de entrada no recuo, com guarda de cursor, e um braço simulado de ponta a ponta.

A política só vê a cadeia através de uma `View` presa ao cursor do motor: ler um ponto à frente levanta
`LookAheadError` (o mesmo desenho do R74). O braço compra no estado conhecido ao pouso (gatilho + L), monta
o caminho da posição a partir do pouso — já com a nossa compra somada às reservas — e sai pelo
`simulate_current` do R72 **sem alteração** (1,15× · recuo 10 % armado na entrada · 300 s).
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from chain import Pt, state_at

STATE = Path(__file__).resolve().parent.parent


def _mod(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules[name] = m
    spec.loader.exec_module(m)  # type: ignore[union-attr]
    return m


_prev = sys.modules.get("load")
r72 = _mod("load", STATE / "r72" / "load.py")  # sim.py faz `from load import ...`
sim = _mod("r72sim", STATE / "r72" / "sim.py")
if _prev is not None:
    sys.modules["load"] = _prev
else:
    sys.modules.pop("load", None)

COST = sim.COST  # 2,23 % ida e volta
sell_net = r72.sell_net


class LookAheadError(AssertionError):
    pass


class View:
    """Janela da cadeia até ao cursor. Ler além dele é antecipação."""

    def __init__(self, pts: list[Pt]):
        self._pts = pts
        self.cursor = -1

    def __getitem__(self, k: int) -> Pt:
        if k > self.cursor or k < 0:
            raise LookAheadError(f"leitura do ponto {k} com o cursor em {self.cursor}")
        return self._pts[k]


def _le(a: Pt, ref: tuple[int, int], keep_pct: int) -> bool:
    """preço(a) <= preço(ref) * keep/100, em inteiros: a.vsol/a.vtok <= rs/rt * keep/100."""
    rs, rt = ref
    return a.vsol * rt * 100 <= rs * a.vtok * keep_pct


def _gt(a: Pt, ref: tuple[int, int]) -> bool:
    rs, rt = ref
    return a.vsol * rt > rs * a.vtok


class Dip:
    """Compra no primeiro ponto elegível com preço <= máxima corrente × (1 − X)."""

    def __init__(self, x_pct: int, use_photos: bool = False, slot_final: bool = False):
        self.x = x_pct
        self.use_photos = use_photos
        self.slot_final = slot_final
        self.m: tuple[int, int] | None = None

    def reset(self, ref: tuple[int, int]) -> None:
        self.m = ref

    def step(self, view: View, k: int) -> bool:
        p = view[k]
        if p.kind == "photo" and not self.use_photos:
            return False
        if self.slot_final and not p.last_in_slot:
            return False
        assert self.m is not None
        if _le(p, self.m, 100 - self.x):
            return True
        if _gt(p, self.m):
            self.m = (p.vsol, p.vtok)
        return False


class Cheat:
    """CONTROLO DE FUGA: compra no mínimo da janela olhando o ponto seguinte. Tem de ser apanhado."""

    def reset(self, ref: tuple[int, int]) -> None:
        pass

    def step(self, view: View, k: int) -> bool:
        nxt = view[k + 1]
        return _le(view[k], (nxt.vsol, nxt.vtok), 100)


def find_trigger(pts: list[Pt], t0: datetime, policy, w_s: float) -> int | None:
    """Índice do ponto-gatilho em `(t0, t0 + W]`, ou None (não entra)."""
    i0 = state_at(pts, t0)
    policy.reset((pts[i0].vsol, pts[i0].vtok))
    view = View(pts)
    view.cursor = i0
    end = t0 + timedelta(seconds=w_s)
    for k in range(i0 + 1, len(pts)):
        if pts[k].t > end:
            return None
        view.cursor = k
        if policy.step(view, k):
            return k
    return None


def _exit_trigger(P, latency_s: float):
    """Espelho do laço de `simulate_current` (como `r76/load.py:landing`): (motivo, instante do gatilho)."""
    pts = r72.window(P, r72.WINDOW_S, tail_s=latency_s + 2)
    last = P["entry_bt"] + timedelta(seconds=r72.WINDOW_S)
    live = [k for k, p in enumerate(pts) if p[0] <= last]
    high = pts[0][3]
    target = int(Decimal(P["spent"]) * sim.TARGET_X)
    for i in live:
        mark = pts[i][3]
        high = max(high, mark)
        hit = mark >= target
        if hit or mark <= int(Decimal(high) * (1 - sim.TRAILING)):
            return ("target" if hit else "trailing"), pts[i][0]
    return "time_stop", last


def simulate_arm(pts: list[Pt], t_trigger: datetime, size: int, latency_s: float, cost: Decimal = COST,
                 min_index: int = 0) -> dict:
    """Compra `size` lamports no estado conhecido a `t_trigger + L` e sai pela regra congelada."""
    landing = t_trigger + timedelta(seconds=latency_s)
    j = state_at(pts, landing)
    if j < min_index:
        raise LookAheadError(f"fill {j} antes do gatilho {min_index}")
    f = pts[j]
    spend = int(Decimal(size) * (1 - cost / 2))
    tokens = sim.gross_buy_tokens(f.vsol, f.vtok, spend)
    path = [(landing, f.vsol + spend, f.vtok - tokens, sell_net(f.vsol + spend, f.vtok - tokens, tokens))]
    for p in pts[j + 1:]:
        vs, vt = p.vsol + spend, p.vtok - tokens
        path.append((p.t, vs, vt, sell_net(vs, vt, tokens)))
    P = dict(entry_bt=landing, spent=size, tokens=tokens, path=path)
    res = sim.simulate_current(P, cost=cost, latency_s=latency_s)
    ret = sim.per_sol(res, P)
    out = dict(ok=ret is not None, fill_index=j, P=P, landing=landing)
    if ret is None:
        return out
    reason, trig_t = _exit_trigger(P, latency_s)
    if reason != res["reason"]:
        raise AssertionError(f"espelho divergiu de simulate_current: {reason} x {res['reason']}")
    peak = max(p[3] for p in path if p[0] <= trig_t)
    out.update(ret=float(ret), reason=reason, exit_trigger=trig_t, peak_le_cost=peak <= size,
               final=res["final"])
    return out
