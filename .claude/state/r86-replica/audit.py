"""r86-replica — auditoria de antecipação: 20 sinais sorteados (semente 86), os 20 fechamentos diários usados,
conferidos contra uma busca direta por chave primária no banco (caminho diferente do agregado diário).

uso: python audit.py sql   > q_audit.sql      (gera a consulta)
     python audit.py check cache/audit.csv    (confere)
"""

from __future__ import annotations

import csv
import random
import sys
from datetime import datetime, time, timedelta
from decimal import Decimal

from replica import enrich, load, ts


def pick():
    sig, days, win = load()
    rows = [r for r in enrich(sig, days, win) if r["rn"] is not None and r["razao"] is not None
            and r["dlow"] is not None and r["r4"] is not None and r["atr"] is not None and r["strategy"] != "mean_reversion"]
    random.seed(86)
    return random.sample(rows, 20), days


def main(argv):
    chosen, days = pick()
    if argv[1] == "sql":
        vals = []
        for r in chosen:
            d_last = r["obs_t"].date() - timedelta(days=1)
            for i in range(20):
                d = d_last - timedelta(days=i)
                vals.append(f"('{r['signal_id']}'::uuid,'{r['market_id']}'::uuid,'{d}T23:59:00Z'::timestamptz)")
        print("SET statement_timeout='60s';\nCOPY (SELECT v.sid, v.mid, v.ot, k.close, k.is_final, k.received_at, s.emitted_at,"
              " (s.supporting_features->>'observation_ts') AS obs FROM (VALUES " + ",".join(vals) +
              ") AS v(sid, mid, ot) JOIN agent_signals s ON s.id = v.sid"
              " LEFT JOIN candles_1m k ON k.market_id = v.mid AND k.timeframe = '1m' AND k.open_time = v.ot"
              " ORDER BY v.sid, v.ot) TO STDOUT WITH (FORMAT csv);")
        return
    db = {}
    for sid, mid, ot, close, fin, recv, em, obs in csv.reader(open(argv[2], encoding="utf-8")):
        db[(sid, ts(ot))] = (Decimal(close) if close else None, fin == "t", ts(recv), ts(em), ts(obs))
    bad = 0
    for r in chosen:
        em, obs = r["em_t"], r["obs_t"]
        d_last = obs.date() - timedelta(days=1)
        closes, lines = [], []
        for i in range(19, -1, -1):
            d = d_last - timedelta(days=i)
            ot = datetime.combine(d, time(23, 59), tzinfo=obs.tzinfo)
            c, fin, recv, em_db, obs_db = db[(r["signal_id"], ot)]
            agg = days[r["market_id"]][d]
            day_end = ot + timedelta(minutes=1)
            ok = (fin and c == agg.c2359 and recv <= em and day_end <= obs <= em and em_db == em and obs_db == obs
                  and agg.max_recv_final <= em)
            bad += not ok
            closes.append(c)
            lines.append(f"    {d} close={c} recv={recv:%m-%d %H:%M:%S} fecho_dia={day_end:%m-%d %H:%M} ok={ok}")
        rz = float(closes[-1] / (sum(closes, Decimal(0)) / 20) - 1)
        print(f"{r['strategy']} {r['version']} {r['symbol']} obs={obs:%Y-%m-%d %H:%M} emitted={em:%Y-%m-%d %H:%M:%S} "
              f"D={d_last} razão(DB direto)={rz:+.6f} razão(replica)={r['razao']:+.6f} igual={abs(rz - r['razao']) < 1e-12}")
        print(f"  dias {d_last - timedelta(days=19)}..{d_last}; maior recv dos 23:59 = {max(db[(r['signal_id'], datetime.combine(d_last - timedelta(days=i), time(23, 59), tzinfo=obs.tzinfo))][2] for i in range(20)):%m-%d %H:%M:%S}; "
              f"maior recv do dia inteiro (agregado) = {max(days[r['market_id']][d_last - timedelta(days=i)].max_recv_final for i in range(20)):%m-%d %H:%M:%S}")
        if "-v" in argv:
            print("\n".join(lines))
        bad += abs(rz - r["razao"]) >= 1e-12
    print(f"\nFALHAS: {bad} (de {20 * 20} dias + 20 razões)")


if __name__ == "__main__":
    main(sys.argv)
