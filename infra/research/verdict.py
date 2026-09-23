"""O veredito congelado e as ressalvas — a regra que decide, isolada do encanamento.

Três rótulos, nunca "promissor". A ordem das perguntas é a do R68 (E1.9c) mais as
correções que a Astra exigiu na revisão de desenho da T4.87:

1. **Potência** — lados pequenos demais ⇒ `NÃO CONFIRMA` com motivo "amostra
   insuficiente". Falta de potência **nunca** é refutação.
2. **Réplicas independentes** — poucos clusters **em qualquer um dos braços**, IC que
   não fecha, D não finito, ou reamostragem que descartou mais de 1 % das réplicas ⇒
   também `NÃO CONFIRMA`. Contraexemplo da Astra: oito clusters no total mas **um só**
   com linhas selecionadas dava IC `[1,0; 1,0]` com 689 de 2 000 réplicas descartadas.
3. **CONFIRMA** só com todas as condições pré-registadas ao mesmo tempo. Quando há
   dependência temporal declarada (`InferencePlan.block`), o IC de blocos entra como
   condição **adicional** — nunca em vez do de cluster, e nunca à escolha de quem lê.
4. **REFUTA** quando o limite superior do IC 95 % (o mais largo dos dois, se houver
   bloco) fica abaixo do MRE — e o texto diz exatamente o que foi refutado: uma
   vantagem **desse tamanho**, não qualquer efeito.
5. **Split declarado** obriga a fatia de teste a existir e a ter potência: uma fatia
   vazia ou de duas linhas não pode "confirmar" por omissão.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from infra.research.results import Contrast
from infra.research.spec import HypothesisSpec, ObservabilityColumns
from infra.research.stats import Shape

CONFIRMA = "CONFIRMA"
NAO_CONFIRMA = "NÃO CONFIRMA"
REFUTA = "REFUTA"


# -------------------------------------------------------------------------- veredito


def _no_power(c: Contrast, pol: Any) -> str | None:
    """O motivo pelo qual não há inferência possível, ou `None` se há."""
    if c.n_selected < pol.min_per_side or c.n_rest < pol.min_per_side:
        return (
            f"amostra insuficiente: {c.n_selected}/{c.n_rest} contra o mínimo "
            f"{pol.min_per_side} por lado — sem potência, o que não é refutação."
        )
    if not np.isfinite(c.d) or not np.isfinite(c.ci.lo) or not np.isfinite(c.ci.hi):
        return "estimativa ou IC não finitos: sem inferência, nem a favor nem contra."
    support = min(c.ci.groups_selected, c.ci.groups_rest)
    if c.ci.groups < pol.min_clusters or support < pol.min_clusters:
        return (
            f"inferência sem réplicas independentes suficientes: {c.ci.groups} clusters "
            f"no total e {support} no braço mais magro, contra o mínimo "
            f"{pol.min_clusters} — o IC não se sustenta."
        )
    if c.ci.invalid > 0.01:
        return (
            f"{100 * c.ci.invalid:.1f} % das reamostragens foram descartadas por deixar "
            "um braço vazio: o IC está condicionado às réplicas que sobraram."
        )
    return None


def decide(
    spec: HypothesisSpec,
    c: Contrast,
    shape: Shape,
    oos: Contrast | None,
    *,
    has_split: bool = False,
):
    """Devolve `(veredito, motivos)`. Veredito é sempre um dos três rótulos."""
    pol = spec.policy
    reasons: list[str] = []
    blocked = _no_power(c, pol)
    if blocked is not None:
        return NAO_CONFIRMA, (blocked,)
    if has_split:
        oos_blocked = "não há fatia de teste" if oos is None else _no_power(oos, pol)
        if oos_blocked is not None:
            return NAO_CONFIRMA, (
                f"o split foi declarado mas a fatia de teste não sustenta veredito: {oos_blocked}",
            )
    checks = (
        (c.d > 0, f"D = {c.d:+.4f} não é positivo"),
        (c.d >= pol.minimum_effect, f"D = {c.d:+.4f} abaixo do MRE {pol.minimum_effect:+.4f}"),
        (c.ci.lo > 0, f"IC 95 % inferior {c.ci.lo:+.4f} não está acima de zero"),
        (c.p_perm < 0.05, f"p de permutação {c.p_perm:.4f} não é < 0,05"),
    )
    if pol.require_positive_level:
        checks += (
            (
                c.mean_selected > 0,
                f"o braço selecionado perde em nível ({c.mean_selected:+.4f}); "
                "perder menos que o resto não é vantagem",
            ),
        )
    if pol.require_plateau:
        checks += (
            (
                shape.form == "planalto",
                f"a curva de limiares é {shape.form}, não planalto ({shape.detail})",
            ),
        )
    if c.ci_block is not None:
        checks += (
            (
                np.isfinite(c.ci_block.lo) and c.ci_block.lo > 0,
                f"há dependência temporal declarada e o IC 95 % por blocos "
                f"[{c.ci_block.lo:+.4f}, {c.ci_block.hi:+.4f}] cobre zero",
            ),
        )
    if oos is not None:
        checks += (
            (
                np.isfinite(oos.d) and oos.d > 0,
                f"a fatia de teste não repete o sinal (D = {oos.d:+.4f})",
            ),
        )
    failed = [why for ok, why in checks if not ok]
    if not failed:
        return CONFIRMA, (
            f"D = {c.d:+.4f} ≥ MRE {pol.minimum_effect:+.4f}, IC 95 % "
            f"[{c.ci.lo:+.4f}, {c.ci.hi:+.4f}] acima de zero, p = {c.p_perm:.4f}, "
            f"curva {shape.form}.",
        )
    upper = c.ci.hi if c.ci_block is None else max(c.ci.hi, c.ci_block.hi)
    if np.isfinite(upper) and upper < pol.minimum_effect:
        reasons.append(
            f"IC 95 % superior {upper:+.4f} abaixo do MRE {pol.minimum_effect:+.4f}: "
            "evidência CONTRA uma vantagem útil desse tamanho — não é refutação de "
            "qualquer efeito, é refutação de um efeito que pague a mesa."
        )
        return REFUTA, tuple(reasons)
    return NAO_CONFIRMA, tuple(failed)


def caveats(spec: HypothesisSpec, report_bits: dict[str, Any]) -> tuple[str, ...]:
    """Ressalvas por ordem de importância — a primeira é a que o relatório destaca."""
    out: list[str] = []
    obs = spec.observability
    if not isinstance(obs, ObservabilityColumns):
        out.append(
            f"a guarda não correu (dispensa declarada: {obs.reason}) — "
            "causalidade é afirmação do operador, não do moinho"
        )
    c: Contrast = report_bits["contrast"]
    total = report_bits["n_rows"]
    censored = report_bits["censored_outcome"] + report_bits["censored_variable"]
    if total and censored / total > 0.10:
        out.append(
            f"{censored} de {total} linhas censuradas ({100 * censored / total:.1f} %) — "
            "censura assimétrica entre braços inventa vantagem"
        )
    if c.ci.groups and c.ci.groups < 30:
        out.append(f"só {c.ci.groups} clusters independentes sustentam o IC")
    used = int(report_bits.get("n_used", 0))
    if c.ci.groups and used / c.ci.groups > 1.5:
        out.append(
            f"{used / c.ci.groups:.1f} linhas por cluster: a permutação troca rótulos "
            "linha a linha e, com linhas dependentes dentro do cluster, o p sai "
            "otimista — leia o IC de cluster/blocos antes do p"
        )
    if spec.split is None:
        out.append("sem fatia de teste reservada: o resultado é dentro da amostra")
    if report_bits["refused_by_guard"]:
        out.append(
            f"{report_bits['refused_by_guard']} linhas recusadas pela guarda "
            "anti-antecipação e censuradas"
        )
    if not out:
        out.append(
            "nenhuma ressalva estrutural detetada pelo moinho — o que não é "
            "o mesmo que não haver nenhuma"
        )
    return tuple(out)
