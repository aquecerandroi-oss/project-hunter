# R82 — H-017 (EXP-M25) veredito. cd .claude/state/r82 && PYTHONPATH=C:/dev/project-hunter uv run --project C:/dev/project-hunter python h017_run.py
import csv
import json
import sys
from collections import Counter, defaultdict

import numpy as np

from h017 import classify_arm, classify_ctl, load, pair_rows, part, population, ts
from h017_stats import (
    boot_paired, boot_paired_blocks, decision_price_sensitivity, decompose, fixed_exit_counterfactual, label, price_gap, sign_flip_p, vs_nothing,
)


def fmt(t: tuple[float, float, float]) -> str:
    return f"{t[0]:+.4f} [{t[1]:+.4f}, {t[2]:+.4f}]"


def q(v: list[float], ps=(10, 50, 90)) -> str:
    return " · ".join(f"p{p} {np.percentile(v, p):.2f}" for p in ps) if v else "-"


def block6h(t0: str) -> str:
    t = ts(t0)
    return f"{t.date()}T{t.hour // 6 * 6:02d}"


def show(tag: str, pairs: list[dict]) -> None:
    if len(pairs) < 2:
        print(f"   {tag}: n {len(pairs)}")
        return
    ra, rc, m = np.array([p["ra"] for p in pairs]), np.array([p["rc"] for p in pairs]), [p["mint"] for p in pairs]
    print(f"   {tag}: n {len(pairs)} | D {fmt(boot_paired(ra, rc, m))} | braço {fmt(vs_nothing(ra, m))}"
          f" | controle {fmt(vs_nothing(rc, m))} | melhor {int((ra > rc).sum())}, pior {int((ra < rc).sum())},"
          f" igual {int((ra == rc).sum())}")


def main() -> None:
    rows = load(sys.argv[1] if len(sys.argv) > 1 else None)
    pop, cnt = population(rows)
    pairs, why = pair_rows(pop)
    rearm = [r["symbol"] for r in rows if int(r["n_armed"]) != 1]
    print(f"## Guarda: rearmações (n_armed != 1) = {len(rearm)} {rearm}; mints repetidos = {len(rows) - len({r['mint'] for r in rows})}")
    ext = ts(rows[0]["extracted_at"])
    for r in pop:
        ca, cc = classify_arm(r)[0], classify_ctl(r)[0]
        if classify_arm(r)[1] is None or classify_ctl(r)[1] is None:
            print(f"   fora: {r['t0'][:19]} {r['symbol'][:14]:14} braço {ca} / controle {cc} | idade na extração"
                  f" {(ext - ts(r['t0'])).total_seconds() / 3600:.1f} h")
    print(f"## Extração {rows[0]['extracted_at']} | armações 1.ª por mint {len(rows)} | população {dict(cnt)}")
    print(f"   t0 {pop[0]['t0'][:19]} → {pop[-1]['t0'][:19]} | exclusões {dict(why)}")
    ra, rc = np.array([p["ra"] for p in pairs]), np.array([p["rc"] for p in pairs])
    mints = [p["mint"] for p in pairs]
    d, a, c = boot_paired(ra, rc, mints), vs_nothing(ra, mints), vs_nothing(rc, mints)
    p = sign_flip_p(ra, rc, mints)
    direct = (ra - rc)[np.random.default_rng(821).integers(0, ra.size, (10_000, ra.size))].mean(1)
    print(f"\n## PRIMÁRIA — n pares {len(pairs)}")
    print(f"   (a) D = braço − controle: {fmt(d)} (bootstrap por mint 10 000, moinho; numpy direto"
          f" [{np.percentile(direct, 2.5):+.4f}, {np.percentile(direct, 97.5):+.4f}]); p troca de sinal {p:.4f}")
    print(f"   (b) braço contra 'nada': {fmt(a)} | controle contra 'nada': {fmt(c)}")
    print(f"   Σ SOL braço {sum(float(x['arm_pnl'] or 0) for x in pairs):+.4f} | Σ SOL controle"
          f" {sum(float(x['ctl_pnl']) for x in pairs):+.4f} | melhor {int((ra > rc).sum())}, pior {int((ra < rc).sum())},"
          f" igual {int((ra == rc).sum())}")
    print(f"   → RÓTULO: {label(len(pairs), d, a)}")
    print(f"   composição: {dict(Counter(x['cls'] for x in pairs))}")

    print("\n## Por dia UTC e blocos")
    byday: dict[str, list] = defaultdict(list)
    for x in pairs:
        byday[x["t0"][:10]].append(x)
    for k in sorted(byday):
        show(f"dia UTC {k}", byday[k])
    print(f"   bootstrap por blocos de 6 h ({len(set(block6h(x['t0']) for x in pairs))} blocos): D"
          f" {fmt(boot_paired_blocks(ra, rc, [block6h(x['t0']) for x in pairs]))}")
    big = max(pairs, key=lambda x: abs(x["ra"] - x["rc"]))
    rest = [x for x in pairs if x is not big]
    show(f"sem o maior |D| ({big['symbol']}, {big['ra'] - big['rc']:+.4f}: braço {big['ra']:+.4f}"
         f" {big['arm_exit'] or big['cls']}, controle {big['rc']:+.4f} {big['ctl_exit']})", rest)
    rng = np.sort(ra - rc)
    print(f"   D aparado 5 % de cada cauda: {rng[int(0.05 * rng.size):int(0.95 * rng.size)].mean():+.4f}"
          f" | mediana de D {np.median(ra - rc):+.4f}")

    print("\n## Decomposição de D (Σ ÷ n pares) — como o R79, com 'mesma foto' por observed_at + reservas")
    dec = decompose(pairs, key=lambda x: part(x) if x["cls"] == "entered" else x["cls"])
    for k, (n, contrib, mean) in sorted(dec.items()):
        print(f"   {k}: n {n} | contribuição {contrib:+.4f} | média no grupo {mean:+.4f}")
    print(f"   soma {sum(v[1] for v in dec.values()):+.4f} = D {d[0]:+.4f}")
    same_rt = sum(1 for x in pairs if part(x) == "mesma_foto" and x["arm_entry_at"] == x["ctl_entry_at"])
    print(f"   conferência com o critério do R79 (entry_at igual): {same_rt} pares")
    for k in ("foto_posterior", "foto_desconhecida", "nao_entrou"):
        sub = [x for x in pairs if part(x) == k]
        show(f"só {k}", sub)
    show("sem os pares de mesma foto", [x for x in pairs if part(x) != "mesma_foto"])

    print("\n## Ressalva do papel quantificada")
    ent = [x for x in pairs if x["cls"] == "entered"]
    same = [x for x in ent if part(x) == "mesma_foto"]
    print(f"   entraram {len(ent)}: mesma foto {len(same)} ({len(same) / len(ent):.1%}), {dict(Counter(part(x) for x in ent if part(x) != 'mesma_foto'))}")
    pbs = [(x, json.loads(x["pb"])) for x in ent if x["pb"]]
    trig = [(ts(pb["trigger_at"]) - ts(x["t0"])).total_seconds() for x, pb in pbs]
    cfill = [(ts(x["ctl_snap_at"]) - ts(x["t0"])).total_seconds() for x in pairs if x["ctl_snap_at"]]
    afill = [(ts(x["arm_snap_at"]) - ts(pb["trigger_at"])).total_seconds() for x, pb in pbs if x["arm_snap_at"]]
    print(f"   gatilho − t0 (s): {q(trig)} | foto de fill do controle − t0 (s): {q(cfill)} | foto do braço − gatilho (s): {q(afill)}")
    tr_t0 = [float(pb["trigger_price"]) / float(pb["t0_price"]) for _, pb in pbs]
    print(f"   preço do gatilho ÷ preço de t0: {q(tr_t0)}; acima de t0 em {sum(v > 1 for v in tr_t0)} de {len(tr_t0)}")
    bad = sum(float(pb["trigger_price"]) > float(pb["armed_max_price"]) * 0.97 * (1 + 1e-12) for _, pb in pbs)
    print(f"   mecanismo EXP-M24 item 1: {len(pbs)} blocos, {bad} com trigger_price > armed_max × 0,97")
    eq = sum(1 for x in same if x["ra"] == x["rc"])
    eqpx = sum(1 for x in same if x["arm_avg_px"] == x["ctl_avg_px"])
    print(f"   conferência da mesma foto: retorno idêntico em {eq} de {len(same)}, preço médio de fill idêntico em {eqpx} de {len(same)}")
    for x in same:
        if x["ra"] != x["rc"]:
            print(f"     mesma foto, retorno diferente: {x['symbol']} braço {x['ra']:+.4f} ({x['arm_exit']}) controle {x['rc']:+.4f} ({x['ctl_exit']})")
    gaps = [price_gap(float(x["ctl_mpx_before"]), float(json.loads(x["pb"])["trigger_price"])) for x in same]
    print(f"   mesma foto: preço marginal da foto de fill ÷ gatilho − 1 (denominador = gatilho): média {np.mean(gaps):+.4f},"
          f" {q(gaps)}; gatilho mais barato que o fill em {sum(g > 0 for g in gaps)} de {len(gaps)}")
    later = [x for x in ent if part(x) == "foto_posterior"]
    lg = [price_gap(float(x["ctl_mpx_before"]), float(x["arm_mpx_before"])) for x in later]
    print(f"   foto posterior: preço de fill do controle ÷ fill do braço − 1 (o que o papel mediu): média {np.mean(lg):+.4f}, {q(lg)}")
    ub = {id(x): fixed_exit_counterfactual(x["rc"], float(x["ctl_mpx_before"]), float(json.loads(x["pb"])["trigger_price"]))
          for x in same}
    ra_ub = np.array([ub.get(id(x), x["ra"]) for x in pairs])
    print(f"   SENSIBILIDADE com saída fixada (mesma foto ao preço marginal do gatilho, saída por token do controle;"
          f" NÃO é limite superior, sem peso no rótulo):"
          f" D {fmt(boot_paired(ra_ub, rc, mints))} | braço contra 'nada' {fmt(vs_nothing(ra_ub, mints))}")

    # os dois lados ao preço marginal do próprio instante de decisão (braço: gatilho; controle: t0), saída por token fixada
    dec_ok = [x for x in ent if x["pb"] and x["arm_mpx_before"] and x["ctl_mpx_before"]]
    t0g = [float(json.loads(x["pb"])["t0_price"]) / float(json.loads(x["pb"])["trigger_price"]) - 1 for x in dec_ok]
    print(f"   preço de t0 ÷ gatilho − 1 (a melhora de preço que o gatilho oferecia na decisão): média {np.mean(t0g):+.4f}, {q(t0g)}")
    ra2, rc2, n_rep = decision_price_sensitivity(pairs)
    print(f"   SENSIBILIDADE PARCIAL preço de decisão (aproximação proporcional, saídas fixadas; preços de decisão nas"
          f" {n_rep} entradas — braço no gatilho, controle em t0; as {len(pairs) - n_rep} não-entradas ficam como observadas; descritiva):"
          f" D {fmt(boot_paired(np.array(ra2), np.array(rc2), mints))} | braço contra 'nada' {fmt(vs_nothing(np.array(ra2), mints))}")

    print("\n## Mecanismo do controle (EXP-M25 itens 1–3, toda a coorte)")
    print(f"   par em t0: {sum(1 for r in pop if r['ctl_prop'])} de {len(pop)}; ausências {dict(Counter(classify_ctl(r)[0] for r in pop if not r['ctl_prop']))}")
    print(f"   decided_by: {dict(Counter(r['ctl_decided_by'] for r in pop if r['ctl_prop']))} | posições reais do controle:"
          f" {sum(int(r['ctl_live_n'] or 0) for r in pop)}")
    print(f"   op5 na mesma decisão: {dict(Counter(r['op_prop_status'] or 'sem proposta' for r in pop))}")

    allres = [(r, *classify_arm(r)) for r in pop]
    v = np.array([x for _, _, x in allres if x is not None])
    mm = [r["mint"] for r, _, x in allres if x is not None]
    print(f"\n## Descritivo: braço em todas as decisões resolvidas (sem exigir controle): n {v.size} | {fmt(vs_nothing(v, mm))}")
    print(f"   saídas do braço: {dict(Counter(x['arm_exit'] or x['cls'] for x in pairs))}")
    print(f"   saídas do controle: {dict(Counter(x['ctl_exit'] for x in pairs))}")
    for k, lab in (("no_pullback", "não recuou"), ("killed", "morto na rechecagem")):
        sub = [x["rc"] for x in pairs if x["cls"] == k]
        if sub:
            print(f"   controle quando o braço {lab} (n {len(sub)}): média {np.mean(sub):+.4f}, ganhou em"
                  f" {sum(s > 0 for s in sub)}; motivos {dict(Counter(x['outcomes'].split('@')[0] for x in pairs if x['cls'] == k))}")

    with open("pairs.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["t0", "mint", "symbol", "classe", "parte", "r_braco", "r_controle", "D", "saida_braco", "saida_controle"])
        for x in pairs:
            w.writerow([x["t0"][:19], x["mint"], x["symbol"], x["cls"], part(x), f"{x['ra']:.6f}", f"{x['rc']:.6f}",
                        f"{x['ra'] - x['rc']:.6f}", x["arm_exit"], x["ctl_exit"]])
    print("\n   pares um a um: r82/pairs.csv")


if __name__ == "__main__":
    main()
