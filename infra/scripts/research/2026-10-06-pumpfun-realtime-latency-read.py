"""Reads a capture of ``2026-10-06-pumpfun-realtime-latency.py`` and prints the numbers (markdown) and
writes ``report.json`` next to it. Pure reading: no network.

    uv run --no-sync python infra/scripts/research/2026-10-06-pumpfun-realtime-latency-read.py \\
        --run .claude/state/pumpfun-rt-latency/run1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pumpfun_rt_probe_report import analyze, entry_fields, sample_fields


def _f(x: float | None, nd: int = 3) -> str:
    return "-" if x is None else f"{x:.{nd}f}"


def _pair_row(name: str, rep: dict[str, Any]) -> str:
    d = rep["delta_s"]

    def pct(x: float | None) -> str:
        return "-" if x is None else f"{x:.1%}"

    return (
        f"| {name} | {rep['common']} | {rep['only_a']} | {rep['only_b']} | {_f(d['p10'])} | {_f(d['p50'])} "
        f"| {_f(d['p90'])} | {pct(rep['a_first_share'])} | {pct(rep['b_first_share'])} | {pct(rep['tie_share'])} |"
    )


def _pairs(title: str, pairs: dict[str, dict[str, Any]]) -> list[str]:
    out = [
        f"### {title}",
        "",
        "Delta = `t_a - t_b` in seconds on the same local clock (positive = `a` later than `b`).",
        "",
        "| a vs b | common | only a | only b | p10 | p50 | p90 | a first | b first | tie (<=10 ms) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    out += [_pair_row(n.replace("_vs_", " vs "), r) for n, r in pairs.items()]
    return out + [""]


def _cov(title: str, cov: dict[str, Any]) -> list[str]:
    parts = ", ".join(
        f"{n}: {v['seen']} ({_f(v['share'] * 100 if v['share'] is not None else None, 1)} %)"
        for n, v in cov["by_source"].items()
    )
    return [f"**{title}** — union {cov['union']}, in all {cov['in_all']}; {parts}", ""]


def render(rep: dict[str, Any], meta: dict[str, Any], fields: dict[str, Any]) -> str:
    c, t = rep["create"], rep["trade"]
    lines = [
        "# pump.fun realtime latency probe",
        "",
        f"window analysed: {rep['window_s']:.0f} s; stalls dropped events: {rep['stalls_dropped']}; "
        f"loop lag p50/p99 (whole run; the max includes any sleep): {_f(meta['loop_lag_s']['p50'])}/"
        f"{_f(meta['loop_lag_s']['p99'])} s; refused: {meta['refused'] or 'none'}",
        f"segment analysed {rep['segment']['end'] - rep['segment']['start']:.0f} s of {rep['segment']['segments']} "
        f"unbroken segment(s); connection events inside it: {rep['health'] or 'none'}",
        f"clock offset vs pump.fun server-time: {_f(rep['clock']['offset_s'])} s "
        f"(min {_f(rep['clock']['offset_min_s'])}, max {_f(rep['clock']['offset_max_s'])}, "
        f"n {rep['clock']['samples']}, rtt median {_f(rep['clock']['rtt_median_s'])} s; positive = local behind)",
        "",
        "## Creations (pump program only)",
        "",
    ]
    lines += _cov("coverage by signature", c["coverage"])
    lines += [
        f"trenches `new` board saw {_f((c['tr_new_seen_of_nats_mints'] or 0) * 100, 1)} % of the "
        f"{c['nats_mints']} mints NATS announced.",
        "",
    ]
    lines += _pairs("creation delivery", c["pairs"])
    lines += ["## Trades on the watched coins", ""]
    lines += [
        f"watched coins {t['watched_mints']}, followed wallets {t['followed_wallets']}, "
        f"replay-like share of NATS frames {_f((t['replay_like_share'] or 0) * 100, 1)} % "
        f"(an inference from a one-second timestamp); NATS frames by program {t['nats_programs']}; "
        f"cohort {t['cohort']} signatures (pump program only: PumpSwap legs have no reference here)",
        "",
        "rpc vs nats under different replay slacks (s): "
        + "; ".join(
            f"{x['slack_s']:.0f} s -> n {x['common']}, p50 {_f(x['p50'])}, replay-like "
            f"{_f((x['replay_like_share'] or 0) * 100, 2)} % of frames"
            for x in t["replay_sensitivity"]
        ),
        "",
    ]
    lines += _cov("coverage by signature (watched coins)", t["coverage"])
    lines += _pairs("trade delivery", t["pairs"])
    bc = t["balance_coverage"]
    lines += [
        f"balance feed coverage: delivered {bc['delivered']} of {bc['expected']} expected "
        f"({_f((bc['share'] or 0) * 100, 1)} %)",
        "",
        "delay against block time (s, with the clock offset; see the note):",
        "",
    ]
    lines += ["| source | n | p10 | p50 | p90 |", "|---|---|---|---|---|"]
    for n, d in t["delay_vs_block_time_s"].items():
        lines.append(f"| {n} | {d['n']} | {_f(d['p10'])} | {_f(d['p50'])} | {_f(d['p90'])} |")
    w = t["wire_lower_bound_s"]
    lines += [
        "",
        f"balance feed: our arrival minus the server's own millisecond stamp: n {w['n']} p10 {_f(w['p10'])} "
        f"p50 {_f(w['p50'])} p90 {_f(w['p90'])}",
        "",
        t["delay_note"],
        "",
    ]
    b = rep["block_time_check"]["nats_minus_chain_s"]
    lines += [
        f"NATS block second minus the chain's getBlockTime: n {rep['block_time_check']['n']} "
        f"p10 {_f(b['p10'])} p50 {_f(b['p50'])} p90 {_f(b['p90'])}",
        "",
        "## Migrations",
        "",
        f"PumpPortal migrations {rep['migration']['pp_migrations']}, trenches `graduated` adds "
        f"{rep['migration']['tr_grad_adds']}",
        "",
    ]
    lines += _pairs(
        "graduation delivery (by mint)", {"tr_grad_vs_pp": rep["migration"]["tr_grad_vs_pp"]}
    )
    k = rep["kol"]
    kd = k["kol_update_delay_s"]
    lines += [
        "## KOL flag on the `new` board",
        "",
        f"pump add events {k['add_events_pump']} = {k['adds_pump']} distinct coins (first add in the "
        f"window); kol>0 at first add {k['kol_gt0_at_add']}; kol updates {k['kol_updates']}; "
        f"delay first add -> first kol>0 update: n {kd['n']} p50 {_f(kd['p50'])} s",
        "",
        "## Field inventory (keys on the wire)",
        "",
    ]
    for name, keys in fields.items():
        lines += [f"- `{name}` ({len(keys)}): {', '.join(keys)}"]
    return "\n".join(lines) + "\n"


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--run", required=True)
    args = p.parse_args()
    run = Path(args.run)
    events = [
        json.loads(x) for x in (run / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    meta = json.loads((run / "meta.json").read_text(encoding="utf-8"))
    bt_path = run / "blocktime.json"
    blocktime: dict[str, int | None] = (
        json.loads(bt_path.read_text(encoding="utf-8")) if bt_path.exists() else {}
    )
    samples = json.loads((run / "samples.json").read_text(encoding="utf-8"))
    rep = analyze(events, meta, blocktime)
    fields: dict[str, Any] = dict(sample_fields(samples))
    fields["tr_new entry (union of adds)"] = entry_fields(events, "tr_new")
    fields["tr_grad entry (union of adds)"] = entry_fields(events, "tr_grad")
    (run / "report.json").write_text(
        json.dumps({"report": rep, "fields": fields}, indent=1), encoding="utf-8"
    )
    print(render(rep, meta, fields))


if __name__ == "__main__":
    main()
