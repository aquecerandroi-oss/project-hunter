# R82 — estatística da H-017 sobre o moinho (infra.research.resampling). Lógica pura.
from collections import defaultdict
from collections.abc import Callable, Sequence

import numpy as np

from infra.research.resampling import block_bootstrap, cluster_bootstrap, permutation_p

REPS, SEED = 10_000, 82


def _stack(a: np.ndarray, b: np.ndarray, ids: Sequence[object]) -> tuple[np.ndarray, np.ndarray, list[object]]:
    y = np.concatenate([np.asarray(a, float), np.asarray(b, float)])
    sel = np.concatenate([np.ones(len(a), bool), np.zeros(len(b), bool)])
    return y, sel, list(ids) + list(ids)


def boot_paired(ra, rc, mints, *, reps: int = REPS, seed: int = SEED) -> tuple[float, float, float]:
    """D = média(r_a − r_c) e IC 95 % reamostrando mints inteiros (braço e controle do mesmo mint juntos)."""
    y, sel, cl = _stack(ra, rc, mints)
    iv = cluster_bootstrap(y, sel, cl, reps=reps, seed=seed)
    return float(np.mean(np.asarray(ra) - np.asarray(rc))), iv.lo, iv.hi


def boot_paired_blocks(ra, rc, blocks, *, reps: int = REPS, seed: int = SEED) -> tuple[float, float, float]:
    """O mesmo D com blocos temporais (descritivo)."""
    y, sel, bl = _stack(ra, rc, blocks)
    iv = block_bootstrap(y, sel, bl, reps=reps, seed=seed)
    return float(np.mean(np.asarray(ra) - np.asarray(rc))), iv.lo, iv.hi


def vs_nothing(ra, mints, *, reps: int = REPS, seed: int = SEED) -> tuple[float, float, float]:
    """Braço contra 'não comprar nada' (retorno 0 em cada decisão)."""
    return boot_paired(ra, np.zeros(len(ra)), mints, reps=reps, seed=seed)


def sign_flip_p(ra, rc, mints, *, reps: int = REPS, seed: int = SEED) -> float:
    """p bilateral: permutar o rótulo braço/controle dentro do mint = trocar o sinal de cada diferença."""
    y, sel, st = _stack(ra, rc, mints)
    return permutation_p(y, sel, st, reps=reps, seed=seed)


def label(n: int, d: tuple[float, float, float], ra: tuple[float, float, float]) -> str:
    """Regra do §2 das notas (texto da H-017, ordem congelada)."""
    if n < 150:
        return f"LIMITE DE DADO ({n} < 150 pares resolvidos)"
    if d[2] < 0.01:
        return "REFUTA (a): IC sup de D < +1 pp"
    if ra[2] < 0:
        return "REFUTA (b): IC sup do braço contra 'nada' < 0"
    if d[0] >= 0.02 and d[1] > 0 and ra[1] > 0:
        return "CONFIRMA"
    lit = " — cláusula (b) literal dispara (braço não mostrou bater 'nada'); pela errata do R76, sozinha não refuta" \
        if ra[0] <= 0 or ra[1] <= 0 else ""
    return "NÃO CONFIRMA" + lit


def decompose(pairs: list[dict], key: Callable[[dict], str]) -> dict[str, tuple[int, float, float]]:
    """{grupo: (n, contribuição = Σ(r_a − r_c) ÷ N total, média no grupo)} — as contribuições somam D."""
    groups: dict[str, list[float]] = defaultdict(list)
    for p in pairs:
        groups[key(p)].append(p["ra"] - p["rc"])
    n = len(pairs)
    return {k: (len(v), sum(v) / n, float(np.mean(v))) for k, v in groups.items()}


def price_gap(p_ctl_fill: float, p_trigger: float) -> float:
    """Melhora de preço que o gatilho oferecia sobre o fill do controle (+ = gatilho mais barato)."""
    return p_ctl_fill / p_trigger - 1


def fixed_exit_counterfactual(rc: float, p_ctl_fill: float, p_trigger: float) -> float:
    """Sensibilidade com saída fixada (NÃO é limite superior — Astra, R82): mesma saída por token do controle,
    entrada ao preço marginal do gatilho. A política real pode render mais ou menos (saída relativa à entrada)."""
    return (1 + rc) * p_ctl_fill / p_trigger - 1


def decision_price_sensitivity(pairs: list[dict]) -> tuple[list[float], list[float], int]:
    """Aproximação proporcional com saídas fixadas (NÃO é execução simulada; descritiva — Astra, R82):
    nas entradas, braço ao preço marginal do gatilho e controle ao de t0; as não-entradas ficam como observadas
    (sem proposta do braço não há t0_price no bloco). Devolve (r_a', r_c', n reprecificados)."""
    import json

    ra2: list[float] = []
    rc2: list[float] = []
    n = 0
    for x in pairs:
        pb = json.loads(x["pb"]) if x["pb"] else None
        if x["cls"] == "entered" and pb and x["arm_mpx_before"] and x["ctl_mpx_before"]:
            ra2.append(fixed_exit_counterfactual(x["ra"], float(x["arm_mpx_before"]), float(pb["trigger_price"])))
            rc2.append(fixed_exit_counterfactual(x["rc"], float(x["ctl_mpx_before"]), float(pb["t0_price"])))
            n += 1
        else:
            ra2.append(x["ra"])
            rc2.append(x["rc"])
    return ra2, rc2, n
