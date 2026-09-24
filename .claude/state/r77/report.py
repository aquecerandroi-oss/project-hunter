"""R77 / H-016 — relatório: elegibilidade, contrastes pelo moinho, Holm, regra congelada, descritivos.

Uso: cd .claude/state/r77 && uv run --project ../../.. python report.py > report.txt
"""

from __future__ import annotations

import json
import statistics as st
from decimal import Decimal
from pathlib import Path

from rule import WS, XS, best_cell, combine, decide, holm, mill_paired

HERE = Path(__file__).resolve().parent
CELLS = [(x, w) for w in WS for x in XS]
MAXGAP = 60.0
SOL = Decimal(10**9)


def load():
    return [json.loads(line) for line in (HERE / "cache" / "arms.jsonl").open(encoding="utf-8")]


def eligible(r, rule="exit"):
    if r["censor"] or "arms" not in r:
        return False
    if rule == "370":
        return r["gap370_s"] <= MAXGAP
    return all(v["gap"] <= MAXGAP for k, v in r["arms"].items() if k.startswith(("ctrl@", "main:")))


def col(R, key):
    return [r["arms"][key]["ret"] for r in R]


def contrast(R, key, base, name, reps=10_000):
    pol = col(R, key)
    ref = [0.0] * len(R) if base is None else col(R, base)
    return mill_paired(pol, ref, [r["mint"] for r in R], name, reps=reps)


def fmt(c):
    return "%+.4f [%+.4f, %+.4f] p=%.4f" % (c["D"], c["lo"], c["hi"], c["p"])


def sol(lamports) -> str:
    return "%+.4f" % (Decimal(lamports) / SOL)


def frac_never_above(R, key):
    loss = [r for r in R if r["arms"][key].get("entered", True) and r["arms"][key]["ret"] < 0]
    k = sum(1 for r in loss if r["arms"][key]["peak_le_cost"])
    return k, len(loss), (k / len(loss) if loss else 0.0)


def describe(R, x, w, real: bool) -> list[str]:
    key, ck = f"main:{x}:{w}@1.6", "ctrl@1.6"
    ent = [r for r in R if r["arms"][key].get("entered")]
    out = []
    lvl = st.mean(r["arms"][key]["ret"] for r in ent) if ent else float("nan")
    delays = sorted(r["arms"][key]["delay_s"] for r in ent)
    nls = sum(1 for r in ent if not r["arms"][key]["trig_last_in_slot"])
    out.append("  entradas %d/%d (%.0f %%); atraso mediano do gatilho %.1f s; nível médio das entradas %+.4f; "
               "gatilho fora do fim do slot: %d" % (len(ent), len(R), 100 * len(ent) / len(R),
                                                      st.median(delays) if delays else float("nan"), lvl, nls))
    d_in = sum(r["arms"][key]["ret"] - r["arms"][ck]["ret"] for r in ent) / len(R)
    d_out = sum(0.0 - r["arms"][ck]["ret"] for r in R if not r["arms"][key].get("entered")) / len(R)
    out.append("  D decomposto (por decisão): das entradas %+.4f, das não-entradas %+.4f" % (d_in, d_out))
    cw = [r for r in R if r["arms"][ck]["ret"] > 0]
    lost = [r for r in cw if not r["arms"][key].get("entered")]
    worse = [r for r in cw if r["arms"][key].get("entered") and r["arms"][key]["ret"] <= 0]
    out.append("  vitórias do controlo %d: perdidas por não entrar %d (%s SOL); entrou e não ganhou %d"
               % (len(cw), len(lost), sol(sum(r["arms"][ck]["pnl_lamports"] for r in lost)), len(worse)))
    pw = sum(1 for r in R if r["arms"][key]["ret"] > 0)
    out.append("  vitórias da política %d (controlo %d); PnL somado política %s SOL × controlo %s SOL"
               % (pw, len(cw), sol(sum(r["arms"][key]["pnl_lamports"] for r in R)),
                  sol(sum(r["arms"][ck]["pnl_lamports"] for r in R))))
    big_c = {r["mint"] for r in R if r["arms"][ck]["ret"] <= -0.5}
    big_p = {r["mint"] for r in R if r["arms"][key]["ret"] <= -0.5}
    out.append("  perdas >= 50 %%: controlo %d, política %d (criadas %d, evitadas %d)"
               % (len(big_c), len(big_p), len(big_p - big_c), len(big_c - big_p)))
    kc, nc, fc = frac_never_above(R, ck)
    kp, np_, fp = frac_never_above(R, key)
    out.append("  perdas que nunca passaram do custo (simuladas): controlo %d/%d = %.2f; política %d/%d = %.2f"
               % (kc, nc, fc, kp, np_, fp))
    if real:
        h = [r for r in R if r.get("hist_never_above") and float(r["hist_pnl"]) < 0]
        av = sum(1 for r in h if not r["arms"][key].get("entered"))
        tu = sum(1 for r in h if r["arms"][key].get("entered") and r["arms"][key]["ret"] > 0)
        im = sum(1 for r in h if r["arms"][key].get("entered") and 0 >= r["arms"][key]["ret"] > r["arms"][ck]["ret"])
        out.append("  das perdas históricas que nunca passaram do custo presentes (%d): evitadas %d, viradas %d, "
                   "melhoradas (ainda perda) %d, iguais/piores %d" % (len(h), av, tu, im, len(h) - av - tu - im))
    return out


def block(R, label: str, real: bool, verdict: bool = True, reps: int = 10_000) -> tuple[list[str], str | None]:
    L = [f"### {label} — n = {len(R)} decisões (uma por mint)"]
    if len(R) < 20:
        L.append("  amostra < 20: só contagens")
        return L, None
    c16 = [r["arms"]["ctrl@1.6"]["ret"] for r in R]
    c5 = [r["arms"]["ctrl@5.0"]["ret"] for r in R]
    L.append("  controlo (compra em t0): média por SOL %+.4f a 1,6 s, %+.4f a 5 s; vitórias %d; motivos %s"
             % (st.mean(c16), st.mean(c5), sum(1 for v in c16 if v > 0),
                dict(sorted({k: sum(1 for r in R if r["arms"]["ctrl@1.6"]["reason"] == k)
                             for k in ("target", "trailing", "time_stop")}.items()))))
    if real:
        hr = [r["hist_ret"] for r in R]
        agree = sum(1 for a, b in zip(hr, c16, strict=True) if (a > 0) == (b > 0))
        L.append("  fidelidade: PnL real por SOL médio %+.4f × controlo simulado %+.4f; sinal igual em %d/%d; "
                 "correlação %.2f" % (st.mean(hr), st.mean(c16), agree, len(R), st.correlation(hr, c16)))
    cells, pv = {}, {}
    rows = []
    for x, w in CELLS:
        k16, k5 = f"main:{x}:{w}@1.6", f"main:{x}:{w}@5.0"
        a = contrast(R, k16, "ctrl@1.6", f"H-016 {label} X{x} W{w} 1,6s", reps)
        b = contrast(R, k5, "ctrl@5.0", f"H-016 {label} X{x} W{w} 5s", reps)
        z = contrast(R, k16, None, f"H-016 {label} X{x} W{w} vs nada", reps)
        cells[(x, w)] = dict(D=a["D"], lo=a["lo"], hi=a["hi"], p=a["p"], level=z["D"], D5=b["D"],
                             lvl_lo=z["lo"], lvl_hi=z["hi"], D5lo=b["lo"], D5hi=b["hi"], mill=a["mill"],
                             fp=a["fingerprint"])
        pv[(x, w)] = a["p"]
        rows.append((x, w, a, b, z))
    hp = holm(pv)
    L.append("  | X | W | entradas | D vs controlo [IC 95 %] p | Holm | D a 5 s [IC] | vs nada [IC] | moinho |")
    for x, w, a, b, z in rows:
        ne = sum(1 for r in R if r["arms"][f"main:{x}:{w}@1.6"].get("entered"))
        L.append("  | %d %% | %d s | %d | %s | %.3f | %+.4f [%+.4f, %+.4f] | %+.4f [%+.4f, %+.4f] | %s |"
                 % (x, w, ne, fmt(a), hp[(x, w)], b["D"], b["lo"], b["hi"], z["D"], z["lo"], z["hi"], a["mill"]))
    for x, w in CELLS:
        L.append(f"  X={x} % W={w} s")
        L += describe(R, x, w, real)
    if not verdict:
        return L, None
    ff = {n: frac_never_above(R, f"main:{n[0]}:{n[1]}@1.6")[2] < frac_never_above(R, "ctrl@1.6")[2]
          for n in CELLS} if real else True
    label_v, why = decide(cells, ff)
    L.append(f"  **Veredito ({label}): {label_v}**")
    L += ["    - " + w for w in why]
    b = best_cell(cells)
    L.append("    melhor célula X=%d %% W=%d s; impressão digital do pré-registo no moinho: %s"
             % (b[0], b[1], cells[b]["fp"]))
    return L, label_v


def sens(R0, label, tag, reps=10_000):
    L = [f"  sensibilidade `{tag}` ({label}, 1,6 s):"]
    for x, w in CELLS:
        R = [r for r in R0 if r["arms"][f"{tag}:{x}:{w}@1.6"]["ok"]]
        if len(R) < len(R0):
            L.append("    (X=%d %% W=%d s: %d decisões sem braço resolvido nesta sensibilidade)" % (x, w, len(R0) - len(R)))
        a = contrast(R, f"{tag}:{x}:{w}@1.6", "ctrl@1.6", f"H-016 {label} {tag} X{x} W{w}", reps)
        ne = sum(1 for r in R if r["arms"][f"{tag}:{x}:{w}@1.6"].get("entered"))
        extra = ""
        if tag == "photos":
            extra = "; gatilhos por foto %d" % sum(1 for r in R if r["arms"][f"{tag}:{x}:{w}@1.6"].get(
                "trig_kind") == "photo")
        L.append("    X=%d %% W=%d s: entradas %d; D %s%s" % (x, w, ne, fmt(a), extra))
    return L


def main() -> None:
    recs = load()
    out: list[str] = ["# R77 — saída do relatório (H-016)", ""]
    labels = {}
    for pop, real in (("real", True), ("paper", False)):
        P = [r for r in recs if r["pop"] == pop]
        cens: dict[str, int] = {}
        for r in P:
            k = r["censor"] or ("buraco>60s_ate_saida" if not eligible(r) else "ok")
            cens[k.split(":")[0]] = cens.get(k.split(":")[0], 0) + 1
        R = [r for r in P if eligible(r)]
        out.append(f"## População {pop}: {len(P)} decisões, elegibilidade {cens}")
        if real:
            miss = sum(1 for r in P if not r.get("our_buy_in_archive"))
            inj = sum(1 for r in P if r.get("own_injected"))
            out.append(f"  compra nossa ausente do arquivo: {miss} de {len(P)}; decisões com fills nossos "
                       f"injetados do registo da posição: {inj}")
        L, v = block(R, pop, real)
        labels[pop] = v
        out += L
        out += sens(R, pop, "slotfinal") + sens(R, pop, "photos")
        R370 = [r for r in P if eligible(r, "370")]
        out.append(f"  sensibilidade horizonte fixo 370 s: n = {len(R370)}")
        if len(R370) >= 20:
            for x, w in CELLS:
                a = contrast(R370, f"main:{x}:{w}@1.6", "ctrl@1.6", f"H-016 {pop} 370 X{x} W{w}")
                out.append("    X=%d %% W=%d s: D %s" % (x, w, fmt(a)))
        E = [r for r in R if r["series"] == "meme_event_gate_v1"]
        L, _ = block(E, f"{pop} — só pista de eventos (descritivo)", real, verdict=False)
        out += L
        out.append("")
    out.append("## Hipótese inteira: %s (reais: %s; papel: %s)"
               % (combine(labels["real"] or "NÃO CONFIRMA", labels["paper"] or "NÃO CONFIRMA"),
                  labels["real"], labels["paper"]))
    print("\n".join(out))


if __name__ == "__main__":
    main()
