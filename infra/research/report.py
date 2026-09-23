"""Relatório em português, no mesmo formato das notas R65–R69, para ficarem comparáveis.

Regras do formato, herdadas dos cinco estudos:

* o veredito é um de **três** rótulos e aparece antes de qualquer tabela — nunca
  "promissor", nunca "parece que";
* 5 a 8 números-chave, não trinta;
* a curva de limiares vem sempre, mesmo quando não decide nada (é o diagnóstico
  planalto-vs-pico da KB-0149 §5, item 26);
* **a ressalva que mais importa** tem secção própria, no singular;
* as suposições numéricas são declaradas, não escondidas no código;
* dinheiro publicado é `Decimal`, impresso tal como somado.
"""

from __future__ import annotations

from infra.research.protocol import Contrast, Report

_NA = "—"


def _f(value: float, digits: int = 4) -> str:
    return _NA if value != value else f"{value:+.{digits}f}"


def _ci(contrast: Contrast) -> str:
    if contrast.ci.lo != contrast.ci.lo:
        return _NA
    return f"[{contrast.ci.lo:+.4f}, {contrast.ci.hi:+.4f}]  P(D≤0) = {contrast.ci.p_le0:.3f}"


def _head(report: Report) -> list[str]:
    pre = report.pre_registration
    return [
        f"# {report.name} — {report.verdict}",
        "",
        f"> Origem: {report.origin}  ·  impressão digital do pré-registo: `{report.fingerprint}`",
        f"> Limiar congelado: **{report.threshold:g}**  ·  "
        f"efeito mínimo relevante (MRE): **{report.minimum_effect:+.4f}**",
        "",
        "## Pré-registo (escrito antes de correr)",
        "",
        f"- **Previsão:** {pre.prediction}",
        f"- **Refutação:** {pre.refutation}",
        f"- **Regra de decisão:** {pre.decision_rule}",
        f"- **Política de limiar:** {pre.threshold_policy}",
        f"- **Congelado em:** {pre.registered_on}",
        "",
    ]


def _numbers(report: Report) -> list[str]:
    c = report.contrast
    lines = [
        "## Os números",
        "",
        "| # | o quê | valor |",
        "|---|---|---|",
        f"| 1 | população usada (de {report.n_rows} linhas lidas) | "
        f"**{report.n_used}** em {c.ci.groups} clusters |",
        f"| 2 | selecionados / resto no limiar congelado | {c.n_selected} / {c.n_rest} |",
        f"| 3 | média do desfecho: selecionados / resto | "
        f"{_f(c.mean_selected)} / {_f(c.mean_rest)} |",
        f"| 4 | **D = média(selecionados) − média(resto)** | **{_f(c.d)}** |",
        f"| 5 | IC 95 % de D (bootstrap de cluster por `{report.cluster_column}`) | {_ci(c)} |",
    ]
    n = 6
    if c.ci_block is not None:
        lines.append(
            f"| {n} | IC 95 % de D (bootstrap de blocos) | "
            f"[{c.ci_block.lo:+.4f}, {c.ci_block.hi:+.4f}] em {c.ci_block.groups} blocos |"
        )
        n += 1
    strat = f"estratificada por `{report.stratum_column}`" if report.stratum_column else "global"
    lines.append(f"| {n} | p de permutação ({strat}) | {_p(c.p_perm)} |")
    n += 1
    if report.out_of_sample is not None:
        oos = report.out_of_sample
        lines.append(
            f"| {n} | fatia de teste reservada: D | {_f(oos.d)} "
            f"({oos.n_selected}/{oos.n_rest}; {report.purged} linhas purgadas) |"
        )
        n += 1
    if report.money_total is not None:
        lines.append(f"| {n} | dinheiro somado na população (Decimal) | `{report.money_total}` |")
    lines += [
        "",
        f"Censura: {report.censored_outcome} linhas sem desfecho, "
        f"{report.censored_variable} sem a variável, "
        f"{report.refused_by_guard} recusadas pela guarda anti-antecipação. "
        "Ausente nunca virou zero.",
        "",
    ]
    return lines


def _p(value: float) -> str:
    return _NA if value != value else f"{value:.4f}"


def _verdict(report: Report) -> list[str]:
    lines = [f"## VEREDITO: {report.verdict}", ""]
    lines += [f"- {r}" for r in report.reasons]
    lines.append("")
    return lines


def _curve(report: Report) -> list[str]:
    lines = [
        "## Curva de limiares — planalto ou pico?",
        "",
        f"Diagnóstico: **{report.shape.form}** ({report.shape.detail}).",
        "",
        "| limiar | n sel/resto | D | IC 95 % |",
        "|---|---|---|---|",
    ]
    for point in report.curve:
        if not point.evaluable:
            lines.append(
                f"| {point.threshold:g} | {point.n_selected}/{point.n_rest} | "
                f"{_NA} | amostra insuficiente |"
            )
            continue
        lines.append(
            f"| {point.threshold:g} | {point.n_selected}/{point.n_rest} | {_f(point.d)} | "
            f"[{point.ci.lo:+.4f}, {point.ci.hi:+.4f}] |"
        )
    lines.append("")
    return lines


def _buckets(report: Report) -> list[str]:
    if not report.buckets:
        return []
    lines = [
        "## Baldes por tercis (descritivo, não decide nada)",
        "",
        "| balde | n | média | mediana |",
        "|---|---|---|---|",
    ]
    for b in report.buckets:
        lines.append(f"| {b.label} | {b.n} | {_f(b.mean)} | {_f(b.median)} |")
    lines.append("")
    return lines


def _tail(report: Report) -> list[str]:
    lines = ["## A ressalva que mais importa", "", report.caveats[0], ""]
    if len(report.caveats) > 1:
        lines += ["Outras ressalvas:", ""]
        lines += [f"- {c}" for c in report.caveats[1:]]
        lines.append("")
    lines += ["## Suposições numéricas declaradas", ""]
    declared = report.assumptions or (
        "nenhuma além das do próprio export — o que é, em si, uma suposição",
    )
    lines += [f"- {a}" for a in declared]
    lines += [
        "",
        "Estatística em `float` (contrastes de retorno); dinheiro publicado em `Decimal`. "
        "Tempo em UTC.",
        "",
        "> Nada aqui autoriza dinheiro real. Um CONFIRMA é candidato a **braço de papel "
        "pré-registado**, nunca parâmetro de mesa.",
    ]
    return lines


def render(report: Report) -> str:
    """Devolve o relatório Markdown completo, pronto para virar nota do estudo."""
    parts = (
        _head(report)
        + _numbers(report)
        + _verdict(report)
        + _curve(report)
        + _buckets(report)
        + _tail(report)
    )
    return "\n".join(parts).rstrip() + "\n"
