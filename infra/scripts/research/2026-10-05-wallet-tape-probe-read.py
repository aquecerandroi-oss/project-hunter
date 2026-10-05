"""Lê uma corrida da sondagem da onda 0 (``--run .claude/state/carteiras-lucro/probe/run1``) e imprime
as tabelas em Markdown que a seção "Onda 0 — medição" do desenho cola. Só leitura de arquivos.

A janela válida termina no último snapshot antes de qualquer salto de relógio (> 150 s entre dois
snapshots de 60 s): a primeira corrida de 05/10 congelou 4 651 s quando a máquina dormiu, e os
contadores finais (que usam o relógio de parede) não valem depois disso.

    uv run --no-sync python infra/scripts/research/2026-10-05-wallet-tape-probe-read.py --run <dir>
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, cast


def load(run: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows = [
        cast(dict[str, Any], json.loads(line))
        for line in (run / "snapshots.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    valid = rows
    for i in range(1, len(rows)):
        if rows[i]["snapshot"]["elapsed_s"] - rows[i - 1]["snapshot"]["elapsed_s"] > 150:
            valid = rows[:i]
            break
    summary = cast(dict[str, Any], json.loads((run / "summary.json").read_text(encoding="utf-8")))
    return valid, summary


def table(header: list[str], body: list[list[Any]]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)]
    out += ["| " + " | ".join(str(c) for c in row) + " |" for row in body]
    return "\n".join(out)


def f(x: float | None, nd: int = 1) -> str:
    return "—" if x is None else f"{x:,.{nd}f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True)
    ap.add_argument(
        "--slots-per-s",
        default="3.73",
        help="measured slot rate (getRecentPerformanceSamples, 05/10)",
    )
    args = ap.parse_args()
    run = Path(args.run)
    rows, summary = load(run)
    snap = cast(dict[str, Any], rows[-1]["snapshot"])
    el = float(snap["elapsed_s"])
    print(
        f"Janela válida: {el:.0f} s ({el / 60:.1f} min) de {len(rows)} snapshots; suspensões: {snap.get('suspensions')}"
    )
    print("\n## Fluxo por programa\n")
    body: list[list[Any]] = []
    for sub in ("pump", "amm"):
        n, fr = snap["notifications"][sub], snap["frames"][sub]
        down = snap["reconnects"][sub]["downtime_s_incl_open"]
        act = max(1.0, el - down)
        body.append([sub, f(n["n"] / act), f(fr["bytes"] / act / 1e6, 2), f(n["failed"] / n["n"] * 100) + " %",
                     f(fr["bytes"] / act * 86400 / 1e9), f(n["bytes"] / n["n"], 0), f(down, 0)])  # fmt: skip
    print(table(["programa", "notif/s (tempo ativo)", "MB/s sem compressão", "falhas", "GB/dia sem compressão",
                 "bytes/notif", "downtime s"], body))  # fmt: skip
    print("\n## Eventos (decodificação)\n")
    ev = cast(dict[str, dict[str, Any]], snap["events"])
    body = [[k, f"{v['n']:,}", f(v["n"] / el, 2), v["decoded_ok"], v["decode_failed"], v["not_attempted_raw"]]
            for k, v in sorted(ev.items(), key=lambda kv: -kv[1]["n"])[:12]]  # fmt: skip
    print(table(["evento", "n", "por s (tempo total)", "decodificados", "falharam", "crus"], body))
    print("\n## Atraso e reconexões a cada 10 min (contra getSlot HTTP confirmed)\n")
    body = []
    lag10 = cast(dict[str, list[dict[str, Any]]], snap["lag_slots_vs_http_tip_by_10min"])
    for w in range(int(el // 600) + (1 if el % 600 >= 300 else 0)):
        row: list[Any] = [f"{w * 10}–{w * 10 + 10}"]
        for sub in ("pump", "amm"):
            b = next((x for x in lag10.get(sub, []) if x["w"] == w), None)
            row += [f(b["p50"], 0) if b else "—", f(b["p90"], 0) if b else "—"]
        end = min(len(rows) - 1, (w + 1) * 10 - 1)
        rc = rows[end]["snapshot"]["reconnects"]
        row += [rc["pump"]["disconnects"], rc["amm"]["disconnects"]]
        body.append(row)
    print(table(["min", "pump p50", "pump p90", "amm p50", "amm p90", "desconexões pump (acum.)",
                 "desconexões amm (acum.)"], body))  # fmt: skip
    print("\n## Auditoria independente por bloco\n")
    audit = cast(dict[str, Any], summary["independent_block_audit"])
    if not audit["per_block"] and not audit.get("truth", {}).get("blocks_ok"):
        print("- (esta corrida não fez auditoria por bloco: --audit-every 0)")
        return
    print(f"- origem: summary.json final da corrida (início {summary.get('started_utc')}, fim {summary.get('ended_utc')}); "
          f"a janela dos contadores acima é o snapshot {len(rows)}")  # fmt: skip
    per_block = cast(list[list[Any]], audit["per_block"])
    for i in range(1, len(per_block)):  # a slot jump this big is the suspension, not the chain
        if per_block[i][0] - per_block[i - 1][0] > 2000:
            per_block = per_block[:i]
            break
    for tainted in (False, True):
        sel = [b for b in per_block if b[1] is tainted]
        if not sel:
            continue
        cells: list[str] = []
        for k, sub in ((2, "pump"), (3, "PumpSwap")):
            txs, miss = sum(b[k][0] for b in sel), sum(b[k][1] for b in sel)
            cells.append(f"{sub} {txs - miss}/{txs} ({(txs - miss) / max(1, txs) * 100:.1f} %)")
        label = "janela com reconexão (< 150 s)" if tainted else "sem reconexão"
        print(f"- **{label}**: {len(sel)} blocos; " + "; ".join(cells))
    buckets = audit.get("settled") or {k: audit[k] for k in ("clean", "affected_by_reconnect")}
    print(f"- baldes completos (corrida inteira): {json.dumps(buckets)}")
    if "at_fetch" in audit:
        print(f"- no instante do fetch (confundido por atraso): {json.dumps(audit['at_fetch'])}; "
              f"censurados no fim: {audit['pending_censored_at_end']}")  # fmt: skip
    raw = cast(dict[str, Any], audit.get("truth") or {})
    if not raw.get("blocks_ok"):
        print("- (formato antigo da auditoria: sem a contagem da cadeia por bloco)")
        return
    sps = float(args.slots_per_s)
    print(
        f"\n## O que a cadeia emitiu (blocos auditados, independente do websocket; {sps} slots/s)\n"
    )
    keep = (
        "TradeEvent",
        "SellEvent",
        "BuyEvent",
        "CreateEvent",
        "CreatePoolEvent",
        "DepositEvent",
        "WithdrawEvent",
    )
    n = raw["blocks_ok"]
    for sub in ("pump", "amm"):
        t = raw[sub]
        ev = {
            k: f"{v / n * sps:.1f}/s = {round(v / n * sps * 86400):,}/dia"
            for k, v in t["events"].items()
            if k in keep
        }
        print(f"- {sub}: {t['txs'] / n * sps:.0f} tx/s mencionando ({t['success_txs'] / n * sps:.0f} "
              f"com sucesso) em {n} blocos; {ev}")  # fmt: skip


if __name__ == "__main__":
    main()
