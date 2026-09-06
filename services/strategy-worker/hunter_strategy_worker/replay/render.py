"""The human reading of a run — the Markdown beside the canonical JSON.

Every number here comes from the dictionary :mod:`.report` built; nothing is
recomputed, so the tables and the record cannot disagree.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

__all__ = ["render_markdown"]


def _row(cells: Sequence[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _table(header: Sequence[str], rows: Sequence[Sequence[str]]) -> list[str]:
    return [
        _row(header),
        _row(["---"] * len(header)),
        *[_row(row) for row in rows],
    ]


def _na(value: Any) -> str:
    return "—" if value is None else str(value)


def _reproduction_section(document: Mapping[str, Any]) -> list[str]:
    lines = ["## 2. Reprodução da base (passo 1)", ""]
    rows = [
        [
            str(a["version"]),
            str(a["total"]),
            str(a["comparable"]),
            str(a["reproduced"]),
            str(a["diverged"]),
            str(a["not_comparable_late"]),
            str(a["unresolved"]),
            _na(a["reproduction_rate"]),
            _na(a["trajectory_rate"]),
        ]
        for a in document["reproduction"]
    ]
    lines += _table(
        [
            "versão",
            "linhas",
            "comparáveis",
            "reproduzidos",
            "divergentes",
            "late",
            "sem resolver",
            "taxa (tudo)",
            "taxa (trajetória)",
        ],
        rows,
    )
    divergences = [d for a in document["reproduction"] for d in a["divergences"]]
    settlement_only = sum(a["diverged_settlement_only"] for a in document["reproduction"])
    trajectory = [d for d in divergences if d["kind"] == "trajectory"]
    lines += [
        "",
        f"Divergências: **{len(divergences)}** campos em "
        f"**{sum(a['diverged'] for a in document['reproduction'])}** linhas — "
        f"**{settlement_only}** delas só na liquidação (funding) e "
        f"**{len(trajectory)}** campos de trajetória.",
        "",
        "Divergência **só de liquidação** é compatível com um settlement de funding ingerido "
        "depois de o outcome ter sido liquidado: a mesma trajetória, o mesmo `r_ex_funding`, e "
        "um `R_net` que muda porque hoje existe uma linha em `funding_rates` que não existia "
        "quando o worker fechou as contas. **Compatível, não comprovado**: `funding_rates` não "
        "guarda o instante de ingestão, então nada no banco decide *quando* a linha chegou. "
        "Divergência de **trajetória** não teria essa desculpa — seria bug de replay, e o "
        "portão do passo 1 barra a execução.",
        "",
    ]
    if divergences:
        lines += _table(
            ["signal_id", "tipo", "campo", "gravado", "replay"],
            [
                [
                    d["signal_id"],
                    d["kind"],
                    d["field"],
                    _na(d["stored"]),
                    _na(d["replayed"]),
                ]
                for d in divergences[:40]
            ],
        )
        lines.append("")
    return lines


def _coverage_section(document: Mapping[str, Any]) -> list[str]:
    lines = ["## 3. Cobertura e métricas por política", ""]
    rows: list[list[str]] = []
    coverages: list[Any] = list(document["coverage"])
    for cov in coverages:
        m: dict[str, Any] = cov["metrics"]
        rows.append(
            [
                str(cov["policy"]),
                str(cov["resolved"]),
                f"{m['evaluable']} (sem funding: {m['unevaluable']})",
                str(cov["no_entry_inherited"] + cov["no_entry_replayed"]),
                json.dumps(cov["unresolved"], sort_keys=True) if cov["unresolved"] else "—",
                str(cov["matured"]),
                json.dumps(cov["triggers"], sort_keys=True) if cov["triggers"] else "—",
                f"{_na(m['target_rate_among_resolved'])} ({m['targets']}/{m['resolved_touches']})",
                _na(m["net_win_rate"]),
                _na(m["expectancy_r"]),
                f"{_na(m['profit_factor'])} (den. {_na(m['profit_factor_denominator'])})",
            ]
        )
    lines += _table(
        [
            "política",
            "resolvidos",
            "avaliáveis (R_net)",
            "sem entrada",
            "sem resolver",
            "maturados",
            "gatilhos de invalidação",
            "taxa de alvo",
            "taxa de lucro líquido",
            "expectancy líq. (R)",
            "PF",
        ],
        rows,
    )
    lines += [
        "",
        "`target2_missing` / `target3_missing` não é falha: `volume_anomaly_v1/v2` persiste um "
        "único alvo, então os braços de alvo (L1) só existem para `momentum` — os contrastes "
        "`TGT-3 − base` e `TGT-4.5 − base` correm sobre uma subpopulação diferente dos demais, "
        "e isso não é comparável linha a linha com os outros cinco.",
        "",
    ]
    return lines


def _contrast_section(document: Mapping[str, Any]) -> list[str]:
    lines = ["## 4. Os sete contrastes (pareados por sinal)", ""]
    rows = [
        [
            str(c["contrast"]),
            str(c["n_pairs"]),
            str(c["blocks"]),
            _na(c["estimate_r"]),
            (
                f"[{c['ci_low']}, {c['ci_high']}]"
                if c["ci_low"] is not None
                else f"— ({c['ci_reason']})"
            ),
            _na(c["p_value"]),
            _na(c["p_holm"]),
            "sim" if c["holm_rejects"] else "não",
            "sim" if c["abs_effect_at_least_min"] else "não",
        ]
        for c in document["contrasts"]
    ]
    lines += _table(
        [
            "contraste",
            "pares",
            "blocos",
            "Δ médio R_net",
            "IC 95% (blocos)",
            "p",
            "p Holm",
            "rejeita?",
            "abs(Δ) ≥ efeito mín.",
        ],
        rows,
    )
    lines += [
        "",
        "Sensibilidade sem funding (`r_ex_funding`, cobertura própria):",
        "",
    ]
    lines += _table(
        ["contraste", "pares", "Δ médio", "IC 95%"],
        [
            [
                str(c["contrast"]),
                str(c["ex_funding"]["n_pairs"]),
                _na(c["ex_funding"]["estimate_r"]),
                (
                    f"[{c['ex_funding']['ci_low']}, {c['ex_funding']['ci_high']}]"
                    if c["ex_funding"]["ci_low"] is not None
                    else "—"
                ),
            ]
            for c in document["contrasts"]
        ],
    )
    lines.append("")
    return lines


def render_markdown(document: Mapping[str, Any]) -> str:
    """The human reading of the same dictionary."""
    maturity = document["maturity"]
    lines = [
        "# R1 — Replay de políticas de saída sobre as entradas congeladas (EXP-0004)",
        "",
        "**SOMBRA — hipotético, sem capital, custos assumidos.** `purpose=research_only`; "
        "nada foi ativado, nada ordena, nenhuma tabela do Lab foi escrita.",
        "",
        f"- `as_of` (corte de dados, não só de população): `{document['as_of']}`",
        f"- `input_digest`: `{document['input_digest'][:16]}` (registros lidos) · "
        f"`series_digest`: `{document['series_digest'][:16]}` (velas dobradas). O Lab continua "
        "escrevendo; duas execuções só são comparáveis com os mesmos dois dígitos.",
        "- **Limite declarado:** o corte `as_of` vale para as velas; o funding é lido "
        "`as_stored_at_read_time`, porque quem consulta `funding_rates` é o `settle` de "
        "produção, reusado verbatim. Uma linha de funding ingerida depois do corte é visível "
        "à liquidação — é exatamente o que as divergências da §2 mostram.",
        f"- semente: `{document['seed']}` · reamostras: `{document['resamples']}` · "
        f"família Holm: `{document['family_size']}` · efeito mínimo declarado: "
        f"`{document['min_effect_r']} R`",
        f"- políticas: {', '.join(p['key'] for p in document['policies'])}",
        "",
        "## 1. Manifesto e população",
        "",
    ]
    lines += _table(
        ["strategy_version_id", "versão", "params_hash", "ativada em"],
        [
            [m["strategy_version_id"], m["version"], m["params_hash"][:16], _na(m["activated_at"])]
            for m in document["manifest"]
        ],
    )
    lines.append("")
    lines += _table(
        ["versão", "terminal", "no_entry"],
        [
            [label, str(counts.get("terminal", 0)), str(counts.get("no_entry", 0))]
            for label, counts in document["population"].items()
        ],
    )
    lines.append("")
    lines += _reproduction_section(document)
    lines += _coverage_section(document)
    lines += _contrast_section(document)
    gate = document["gate"]
    lines += [
        "## 5. O que é inconclusivo, e por quê",
        "",
        f"**Portão do passo 1:** {'passou' if gate['passed'] else 'NÃO passou'} — reprodução de "
        f"trajetória {gate['trajectory_rate']} sobre {gate['comparable']} linhas comparáveis "
        f"(limiar {gate['threshold']}); reprodução completa {gate['full_rate']}; "
        f"{gate['diverged_settlement_only']} linhas divergiram **só na liquidação**. "
        + (
            "Os contrastes abaixo só existem porque esse portão passou."
            if gate["passed"]
            else "Por isso **nenhum contraste foi calculado**: sem chão, comparar braços "
            "compara bugs."
        ),
        "",
        f"Outcomes da base com horizonte **maturado** no corte: "
        f"**{maturity['matured_outcomes_base']}** (avaliáveis com `R_net`: "
        f"{maturity['evaluable_outcomes_base']}; limiar {maturity['threshold_outcomes']}); "
        f"dias distintos: "
        f"**{maturity['distinct_days']}** (limiar {maturity['threshold_days']}). "
        f"Veredito editorial: **{maturity['verdict']}**.",
        "",
        "Com menos de 100 outcomes maduros ou menos de 30 dias distintos o resultado é "
        "**inconclusivo por contrato** (SHADOW-LAB.md §9). O que este piloto entrega é "
        "**aprendizado operacional** — quanto do acompanhamento real o replay reproduz *nesta "
        "leitura*, quanta cobertura cada política tem e qual é a ordem de grandeza das "
        "diferenças —, **não confirmação**. Os p-valores são exploratórios: vêm de inversão de "
        "sinal por blocos de dia, cuja validade exige simetria dos efeitos de bloco que nada "
        "aqui estabeleceu; com poucos blocos o menor p atingível já é maior que o limiar de "
        "Holm, e com um único bloco o teste devolve `p = 1` **por construção** — o que não é "
        "evidência de equivalência, é ausência de replicação.",
        "",
    ]
    return "\n".join(lines) + "\n"
