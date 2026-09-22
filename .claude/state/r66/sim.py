"""R66 Q3 - a regra da mesa aplicada DEPOIS da graduacao, com o custo do nosso codigo.

Honestidade do exercicio (ver notes-R66.md S3 e a segunda opiniao da Astra):
- a serie e de SNAPSHOTS a ~60 s, nao barras OHLC: o pico e o vale intra-minuto nao
  existem aqui. Isto NAO e um limite superior nem inferior do PnL - e monitorizacao
  discreta, com vies de direcao indeterminada. Esta declarado no relatorio.
- o relogio da entrada e a PRIMEIRA leitura do board em ou depois de `migrated_at`
  (mediana +29 s). Todas as janelas contam a partir DESSA leitura, nunca da graduacao.
- nenhuma leitura posterior ao instante da decisao entra na decisao.

Dinheiro em Decimal. Taxas do pool = tabela real do FeeConfig do PumpSwap (mainnet
2026-09-16), faixa escolhida pelo market cap em SOL do instante.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from load import HERE, entry_point, load_board, load_tokens
from metrics import pct, pool_fee_pct

TICKET = Decimal("0.07")
NETWORK_ROUNDTRIP = Decimal("0.000091")  # R65: 0,007919 SOL / 87 operacoes
ATA_RENT = Decimal("0.00151384")  # R65: o rent exato de cada ATA criada
IMPACT_PCT = Decimal("0.10")  # 0,07 SOL contra ~79 SOL de reserva do pool na graduacao


@dataclass(frozen=True)
class Rule:
    name: str
    target: Decimal
    trail: Decimal
    max_hold_s: int


RULES = (
    Rule("mesa 1,15x / trail 10 % / 300 s", Decimal("1.15"), Decimal("0.10"), 300),
    Rule("lenta 1,30x / trail 15 % / 3600 s", Decimal("1.30"), Decimal("0.15"), 3600),
)


def _mark(price: Decimal, tokens: Decimal, mcap_sol: Decimal) -> Decimal:
    """SOL liquido de vender tudo agora: preco x tokens, menos impacto e taxa da faixa."""
    gross = price * tokens
    return gross * (1 - IMPACT_PCT / 100) * (1 - pool_fee_pct(mcap_sol) / 100)


MAX_GAP_S = 150
"""Lacuna maxima aceite entre duas leituras (2,5x a cadencia de 60 s). Acima disto a
posicao e declarada CENSURADA, nao vendida: atribuir a saida a uma leitura que chegou
7 minutos depois nao e "monitorizacao a 60 s" (must-fix 2 da Astra, 22/09)."""


def simulate(obs: list[dict], entry: dict, rule: Rule, rent_recovered: bool) -> dict | None:
    """Devolve a operacao, ou `censored=True` quando a serie nao permite decidir.

    Uma operacao censurada NAO entra no PnL: nao ha preco de saida observavel. Vender na
    ultima leitura seria antecipacao (naquele instante ninguem sabia que era a ultima).
    """
    p0 = entry["mcap_sol"]
    if not p0 or p0 <= 0:
        return None
    fee_in = pool_fee_pct(p0)
    tokens = TICKET * (1 - IMPACT_PCT / 100) * (1 - fee_in / 100) / p0
    t0 = entry["observed_at"]
    peak = _mark(p0, tokens, p0)
    reason, exit_mark, hold, fee_out = None, None, None, None
    prev_t = t0
    for o in obs:
        dt = (o["observed_at"] - t0).total_seconds()
        if dt <= 0 or not o["mcap_sol"] or o["mcap_sol"] <= 0:
            continue
        if (o["observed_at"] - prev_t).total_seconds() > MAX_GAP_S:
            reason, hold = "censurado_lacuna", (prev_t - t0).total_seconds()
            break
        prev_t = o["observed_at"]
        mark = _mark(o["mcap_sol"], tokens, o["mcap_sol"])
        if o["mcap_sol"] / p0 >= rule.target:
            reason, exit_mark, hold = "target", mark, dt
            fee_out = pool_fee_pct(o["mcap_sol"])
            break
        if mark <= peak * (1 - rule.trail):
            reason, exit_mark, hold = "trailing", mark, dt
            fee_out = pool_fee_pct(o["mcap_sol"])
            break
        peak = max(peak, mark)
        if dt >= rule.max_hold_s:
            reason, exit_mark, hold = "time_stop", mark, dt
            fee_out = pool_fee_pct(o["mcap_sol"])
            break
    if reason is None:  # a serie acabou antes de qualquer gatilho
        reason, hold = "censurado_fim", (prev_t - t0).total_seconds()
    day = entry["observed_at"].date()
    if exit_mark is None:
        return dict(reason=reason, censored=True, pnl=None, hold=hold, fee_in=fee_in,
                    fee_out=None, day=day)
    rent = Decimal(0) if rent_recovered else ATA_RENT
    pnl = exit_mark - TICKET - NETWORK_ROUNDTRIP - rent
    return dict(reason=reason, censored=False, pnl=pnl, hold=hold, fee_in=fee_in,
                fee_out=fee_out, day=day)


def pullback_entry(obs: list[dict], entry: dict, drop: Decimal = Decimal("0.10"),
                   within_s: int = 900) -> dict | None:
    """Primeira leitura que esta `drop` abaixo do maximo pos-graduacao visto ATE ali."""
    t0 = entry["observed_at"]
    high = entry["mcap_sol"]
    for o in obs:
        dt = (o["observed_at"] - t0).total_seconds()
        if dt <= 0:
            continue
        if dt > within_s:
            return None
        if not o["mcap_sol"] or o["mcap_sol"] <= 0:
            continue
        if o["mcap_sol"] <= high * (1 - drop):
            return o
        high = max(high, o["mcap_sol"])
    return None


def summarize(all_trades: list[dict], label: str, out: list[str]) -> None:
    censored = [t for t in all_trades if t["censored"]]
    trades = [t for t in all_trades if not t["censored"]]
    cens_reasons: dict[str, int] = {}
    for t in censored:
        cens_reasons[t["reason"]] = cens_reasons.get(t["reason"], 0) + 1
    if not trades:
        out.append(f"{label}: sem operacoes decidiveis "
                   f"(censuradas: {json.dumps(cens_reasons, sort_keys=True)})")
        return
    fees = [float(t["fee_in"] + t["fee_out"]) for t in trades]
    out.append(f"{label}\n"
               f"  censuradas (excluidas do PnL): {len(censored)} de {len(all_trades)} "
               f"({100*len(censored)/len(all_trades):.1f} %) "
               f"{json.dumps(cens_reasons, sort_keys=True)}\n"
               f"  custo de taxa REALIZADO ida-e-volta (entrada+saida, %): "
               f"mediana {statistics.median(fees):.2f} | media {statistics.mean(fees):.2f}")
    pnls = [t["pnl"] for t in trades]
    total = sum(pnls, Decimal(0))
    wins = [t for t in trades if t["pnl"] > 0]
    holds = [float(t["hold"]) for t in trades]
    by_reason: dict[str, int] = {}
    for t in trades:
        by_reason[t["reason"]] = by_reason.get(t["reason"], 0) + 1
    by_day: dict[str, Decimal] = {}
    for t in trades:
        by_day[str(t["day"])] = by_day.get(str(t["day"]), Decimal(0)) + t["pnl"]
    green = sum(1 for v in by_day.values() if v > 0)
    out.append(
        f"{label}\n"
        f"  n={len(trades)}  total={total:+.4f} SOL  por operacao={total/len(trades):+.6f} SOL "
        f"({total/len(trades)/TICKET*100:+.2f} % do ticket)\n"
        f"  acerto (PnL>0)={100*len(wins)/len(trades):.1f} %  hold mediano={statistics.median(holds):.0f} s"
        f"  pior={min(pnls):+.4f}  melhor={max(pnls):+.4f}\n"
        f"  saidas={json.dumps(by_reason, sort_keys=True)}\n"
        f"  dias verdes={green}/{len(by_day)}  "
        f"por dia={ {k: f'{v:+.3f}' for k, v in sorted(by_day.items())} }"
    )


def main() -> None:
    tokens = load_tokens()
    series = load_board(tokens)
    out: list[str] = []
    w = out.append

    w("== R66 Q3 - simulacao pos-graduacao (monitorizacao discreta ~60 s) ==")
    w(f"ticket {TICKET} SOL | rede {NETWORK_ROUNDTRIP} SOL/op | rent ATA {ATA_RENT} SOL | "
      f"impacto {IMPACT_PCT} %/perna | taxa = faixa real do FeeConfig do PumpSwap")
    w("")

    entries = {m: e for m, e in ((m, entry_point(o)) for m, o in series.items()) if e}
    fees = [float(pool_fee_pct(e["mcap_sol"])) for e in entries.values()]
    w(f"taxa por perna nas {len(entries)} entradas: mediana {pct(fees,0.5):.2f} %, "
      f"p10 {pct(fees,0.1):.2f} %, p90 {pct(fees,0.9):.2f} % -> ida-e-volta mediana "
      f"{2*pct(fees,0.5):.2f} %")
    w("")

    results: dict[str, list[dict]] = {}
    for rule in RULES:
        for rent_recovered in (True, False):
            tag = "rent devolvido" if rent_recovered else "rent perdido"
            trades = []
            for mint, e in entries.items():
                r = simulate(series[mint], e, rule, rent_recovered)
                if r:
                    trades.append(r)
            key = f"entrada na graduacao | {rule.name} | {tag}"
            results[key] = trades
            summarize(trades, key, out)
            w("")

    w("== entrada no pullback (primeira leitura -10 % do maximo pos-graduacao, ate +15 min) ==")
    pb = {}
    for mint, e in entries.items():
        p = pullback_entry(series[mint], e)
        if p:
            pb[mint] = p
    w(f"mints com pullback observado: {len(pb)} de {len(entries)} "
      f"({100*len(pb)/len(entries):.1f} %)")
    w("")
    for rule in RULES:
        trades = []
        for mint, p in pb.items():
            r = simulate(series[mint], p, rule, True)
            if r:
                trades.append(r)
        key = f"entrada no pullback | {rule.name} | rent devolvido"
        results[key] = trades
        summarize(trades, key, out)
        w("")

    text = "\n".join(out)
    print(text)
    Path(HERE / "sim.txt").write_text(text + "\n", encoding="utf-8")
    json.dump(
        {k: [{"reason": t["reason"], "censored": t["censored"],
              "pnl": None if t["pnl"] is None else str(t["pnl"]), "hold": t["hold"],
              "day": str(t["day"])} for t in v] for k, v in results.items()},
        open(HERE / "sim.json", "w"),
    )


if __name__ == "__main__":
    main()
