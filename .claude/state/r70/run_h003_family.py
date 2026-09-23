"""R70 / H-003 — a família congelada: 5 preditores × 3 horizontes = 15 células.

A fila pré-registou "pelo menos uma célula ... com Holm < 0,05": a família é montada
pelo operador (o moinho corre uma célula por chamada) e ajustada por
`infra.research.stats.adjust_family`, que faz BH e Holm sobre a mesma família.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from infra.research.protocol import run_hypothesis  # noqa: E402
from infra.research.report import render  # noqa: E402
from infra.research.stats import adjust_family  # noqa: E402
from run_h003 import PREDICTORS, spec_for  # noqa: E402

HORIZONS = (60, 120, 240)
HERE = Path(__file__).resolve().parent


def main() -> None:
    rows = []
    for h in HORIZONS:
        for predictor in PREDICTORS:
            report = run_hypothesis(spec_for(h, predictor))
            (HERE / f"H-003-{predictor}-h{h}.md").write_text(render(report), encoding="utf-8")
            rows.append((h, predictor, report))
    family = adjust_family([r.contrast.p_perm for _, _, r in rows])
    lines = [
        "# H-003 — família congelada de 15 células (5 preditores × h ∈ {60, 120, 240})",
        "",
        f"Impressão digital de uma célula (as 15 diferem só no nome/horizonte): "
        f"`{rows[0][2].fingerprint}`",
        "",
        "| h | preditor | n | sel/resto | D (líq.) | IC 95 % cluster | IC 95 % blocos | "
        "p perm | Holm | BH | teste (fora) | veredito |",
        "|---|---|---:|---:|---:|---|---|---:|---:|---:|---:|---|",
    ]
    for (h, predictor, r), holm, bh in zip(
        rows, family.holm_adjusted, family.bh_adjusted, strict=True
    ):
        c = r.contrast
        block = (
            "—" if c.ci_block is None else f"[{c.ci_block.lo:+.5f}, {c.ci_block.hi:+.5f}]"
        )
        oos = "—" if r.out_of_sample is None else f"{r.out_of_sample.d:+.5f}"
        lines.append(
            f"| {h} | {predictor} | {r.n_used} | {c.n_selected}/{c.n_rest} | {c.d:+.5f} | "
            f"[{c.ci.lo:+.5f}, {c.ci.hi:+.5f}] | {block} | {c.p_perm:.4f} | {holm:.4f} | "
            f"{bh:.4f} | {oos} | {r.verdict} |"
        )
    confirmed = [r for _, _, r in rows if r.verdict == "CONFIRMA"]
    refuted = [r for _, _, r in rows if r.verdict == "REFUTA"]
    lines += [
        "",
        f"**CONFIRMA: {len(confirmed)} de 15. REFUTA: {len(refuted)} de 15.**",
        "",
        "Previsão da fila: *pelo menos uma célula rende ≥ +0,10 % líquido por operação com "
        "Holm < 0,05 ao custo medido de 0,14 %*. "
        f"Menor p de permutação da família: {min(c.contrast.p_perm for _, _, c in rows):.4f}; "
        f"menor Holm ajustado: {min(family.holm_adjusted):.4f}.",
        "",
        "Refutação da fila: *limite superior do IC 95 % abaixo do MRE de +0,10 % em todas as "
        "células*. Células com IC superior < +0,0010: "
        f"{sum(1 for _, _, r in rows if r.contrast.ci.hi < 0.0010)} de 15.",
        "",
        "## O que o moinho NÃO reproduziu do desenho do R68",
        "",
        "- **walk-forward de várias dobras** (treino 14 d / teste 7 d, passo 7 d): aqui há "
        "uma fronteira única treino/teste (`Split` em blocos de 3 dias, treino até "
        "`b06899`, purga de 1 bloco). Uma dobra não mede estabilidade ao longo do tempo — "
        "mede se o sinal sobrevive a **um** corte;",
        "- **baseline 'sempre dentro'**: o moinho contrasta selecionados contra o resto e "
        "publica o nível dos dois braços, com `require_positive_level` a impedir que "
        "'perder menos' vire CONFIRMA. Não é a mesma pergunta que 'bate o sempre-long';",
        "- **a família correndo junta**: `adjust_family` foi chamado aqui, pelo operador, "
        "sobre os 15 p de permutação — o moinho não o faz sozinho.",
    ]
    (HERE / "H-003.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
