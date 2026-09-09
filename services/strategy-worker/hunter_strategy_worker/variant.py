"""The pure half of ``infra/scripts/derive_variant.py`` — overrides, canonical
form, lineage. No database, no clock, no argparse.

Pulled out of the script for the reason :mod:`hunter_strategy_worker.activation_db`
and :mod:`hunter_strategy_worker.paper_line` were pulled out of
``activate_strategy_version.py``: the 350-line budget, and along the same seam —
this decides *what the variant is*, the script decides *whether to write it and
where*. The script re-exports every name, so nothing that imported them from
there had to move.

It also has to live in an installed package for a second reason. The audited way
to run the deriving tool on the VPS is the script **inside the published image**
(``compose.sh run --rm ops python infra/scripts/derive_variant.py``), with a
stdin fallback that pipes the local file into the image; in both cases only
installed packages can be imported, never a sibling file under ``infra/``.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

from hunter_core.strategies.canonical import canonical_json
from hunter_core.strategies.constraints import check_ranges
from hunter_strategy_worker.activation import validate_parameters
from hunter_strategy_worker.activation_db import Refused
from hunter_strategy_worker.gate_policy import PolicyError, policy_argument, policy_clauses

if TYPE_CHECKING:
    from hunter_core.strategies.base import Strategy
    from hunter_strategy_worker.gate_policy import GatePolicy

__all__ = [
    "LINEAGE_RE",
    "NO_POLICY",
    "NUMERIC",
    "build_parameters",
    "canonical_policy",
    "lineage_of",
    "parse_overrides",
    "policy_note",
    "resolve_policy",
    "stored_policy",
    "variant_changelog",
]

NUMERIC = re.compile(r"^-?[0-9]+(\.[0-9]+)?$")
"""O que ``hunter_core.strategies.schema`` aceita como número: forma posicional,
sem expoente. Um valor que casa isto **e** cujo schema declara ``number``/
``integer`` entra como número canônico; o resto entra como a string que veio,
para o validador recusá-lo com a mensagem do próprio schema."""

LINEAGE_RE = re.compile(
    r"^variante de v\d+ \| derived_from=v\d+ \| overrides=[^|]* \| params_hash=[0-9a-f]{12}"
    r"( \| policy=\S+)?"
)
"""O prefixo de linhagem que a ativação preserva. É formato congelado: mudá-lo
tornaria ilegíveis as variantes já gravadas, então uma mudança é um formato
novo — nunca uma edição deste.

O segmento ``| policy=…`` (T3.52) é **opcional** e vem depois do ``params_hash``,
e é por isso que acrescentá-lo não reescreve o formato: toda variante gravada
antes dele casa exatamente como casava, e uma variante que só muda o portão
(``overrides=`` vazio, mesmo ``params_hash`` do pai) não fica com uma linhagem
que diz "nada mudou". ``activate_derived.keep_lineage`` só preserva o que este
prefixo cobre, então um segmento fora dele seria apagado na ativação."""


def parse_overrides(pairs: list[str]) -> dict[str, str]:
    """``["atr_pct_min=0.0089"] -> {"atr_pct_min": "0.0089"}``, cru e sem juízo."""
    overrides: dict[str, str] = {}
    for pair in pairs:
        name, separator, raw = pair.partition("=")
        name, raw = name.strip(), raw.strip()
        if not separator or not name:
            raise Refused(f"--set {pair!r} não tem a forma parametro=valor")
        if name in overrides:
            raise Refused(f"--set {name} aparece duas vezes: qual dos dois valeria?")
        if "|" in raw or "\n" in raw:
            raise Refused(f"--set {name}: o valor não pode conter '|' nem quebra de linha")
        overrides[name] = raw
    return overrides


def _coerce(name: str, raw: str, rule: dict[str, Any]) -> Any:
    """O valor na forma que o schema congelado espera, nunca numa forma nova."""
    declared = rule.get("type")
    allowed = {declared} if isinstance(declared, str) else set(declared or ())
    if not allowed & {"number", "integer"} or NUMERIC.fullmatch(raw) is None:
        return raw
    try:
        return Decimal(raw)
    except InvalidOperation as exc:  # pragma: no cover - NUMERIC já garante
        raise Refused(f"--set {name}={raw!r} não é um número finito") from exc


def build_parameters(
    schema: dict[str, Any],
    parent: dict[str, Any],
    overrides: dict[str, str],
    strategy: Strategy,
    *,
    policy_moved: bool = False,
) -> tuple[dict[str, Any], list[tuple[str, str, str]]]:
    """O conjunto da variante e o que nele se moveu, na forma canônica.

    Canonizar **antes** de comparar e de validar é o que faz ``0.00890`` e
    ``0.0089`` serem o mesmo parâmetro (e não duas variantes com hashes
    diferentes), e é a mesma passagem que ``activate()`` faz antes de congelar.

    ``strategy`` é obrigatória, e não um argumento opcional, porque a checagem de
    faixa que ela habilita (:func:`check_ranges`) é a única que olha o *conteúdo*
    do número: uma trava que se pode esquecer de ligar não é uma trava.

    ``policy_moved`` (T3.52) é o que autoriza uma variante **sem** ``--set``: o
    portão de regime é conteúdo da versão sem ser parâmetro dela, então uma
    variante que só muda o portão tem o mesmo conjunto do pai de propósito — e
    continua sendo outro experimento.
    """
    properties: dict[str, Any] = schema.get("properties") or {}
    if not overrides and not policy_moved:
        raise Refused("uma variante sem --set nem --policy é o próprio pai: nada seria derivado")
    merged = dict(parent)
    for name, raw in overrides.items():
        if name not in properties:
            raise Refused(f"--set {name}: o schema congelado do pai não declara esse parâmetro")
        if name not in parent:
            raise Refused(f"--set {name}: o pai não tem esse parâmetro em default_parameters")
        merged[name] = _coerce(name, raw, properties[name])
    canonical: dict[str, Any] = json.loads(canonical_json(merged))
    before: dict[str, Any] = json.loads(canonical_json(parent))
    report = validate_parameters(schema, canonical)
    if not report.ok:
        raise Refused(
            "os parâmetros da variante não validam contra o schema congelado do pai: "
            + "; ".join(report.errors)
        )
    if problems := check_ranges(strategy, before, canonical):
        raise Refused("a variante sai da faixa declarada: " + "; ".join(problems))
    changes = [
        (name, str(before[name]), str(canonical[name]))
        for name in sorted(overrides)
        if before[name] != canonical[name]
    ]
    if not changes and not policy_moved:
        raise Refused(
            "nenhum parâmetro se moveu: a variante teria o mesmo params_hash do pai e seria "
            "o mesmo experimento com outro nome"
        )
    return canonical, changes


def lineage_of(changelog: str | None) -> str:
    """O prefixo de linhagem de um ``changelog`` congelado, ou ``""``."""
    match = LINEAGE_RE.match(changelog or "")
    return match.group(0) if match else ""


def policy_note(policy: GatePolicy | None) -> str:
    """Como o portão aparece na linhagem: ``btc:SIDEWAYS``, ``hours=12-15``,
    ``btc:SIDEWAYS;hours=12-15`` ou ``none``.

    Legível pelo operador e analisável por quem for reconciliar as páginas do
    Obsidian; a verdade continua sendo a coluna ``eligibility_policy``, que é
    congelada pelo gatilho — isto é a cópia humana dela, como
    ``overrides=`` é a cópia humana do conjunto.

    Uma política **só** de regime sai exatamente como saía antes da T3.59
    (``btc:SIDEWAYS``, sem prefixo): as variantes já gravadas continuam legíveis
    pela mesma leitura, e o ``;`` só aparece quando há de fato dois portões.
    """
    if policy is None:
        return "none"
    parts: list[str] = []
    if policy.regime is not None:
        parts.append(f"{policy.regime.scope}:{','.join(policy.regime.allow)}")
    if policy.hours is not None:
        parts.append(policy.hours.note)
    return ";".join(parts)


def variant_changelog(
    version: str,
    changes: list[tuple[str, str, str]],
    digest: str,
    note: str,
    *,
    policy: GatePolicy | None = None,
    policy_moved: bool = False,
) -> str:
    """A linhagem primeiro — é por ela que a variante é encontrada e ligada."""
    moved = ",".join(f"{name}={after}" for name, _, after in changes)
    lineage = (
        f"variante de {version} | derived_from={version} | overrides={moved} "
        f"| params_hash={digest[:12]}"
    )
    if policy_moved:
        lineage = f"{lineage} | policy={policy_note(policy)}"
    return f"{lineage} | {note}"


NO_POLICY = "none"
"""O único valor de ``--policy`` que **tira** o portão. Escrito por extenso para
que remover um portão seja uma frase do operador, nunca a ausência dele."""


def canonical_policy(policy: dict[str, Any] | None) -> str:
    """A forma comparável de uma política: ``""`` quando não há portão."""
    return "" if policy is None else canonical_json(policy).decode("utf-8")


def stored_policy(policy: dict[str, Any] | None) -> str | None:
    """O JSON que vai para a **coluna** — que não é a forma canônica, e o motivo
    de estarem separadas é um bug pego por teste antes de qualquer escrita.

    ``canonical_json`` emite todo número como string decimal normalizada: é o
    contrato de ``params_format = 1``, existe para ``Decimal("1.50")`` e ``1.5``
    serem o mesmo parâmetro, e é a coisa certa para ``default_parameters``. A
    janela de horas da T3.59 é feita de **inteiros**: gravada por ali, voltaria
    do JSONB como ``[["12","15"]]``, o parser recusaria (``start '12' is not an
    integer hour``) e a versão inteira sairia do roster com ``policy_unreadable``
    — a coorte emudeceria atrás de um ``/ready`` verde. Aqui vai o JSON com os
    tipos que a política tem. A **comparação** continua em
    :func:`canonical_policy`, onde os dois lados passam pela mesma função.
    """
    return None if policy is None else json.dumps(policy, separators=(",", ":"), sort_keys=True)


def resolve_policy(argument: str | None, parent: dict[str, Any] | None) -> dict[str, Any] | None:
    """A política da variante: herdada, trocada ou removida — nunca adivinhada.

    Sem ``--policy`` a variante **herda** a do pai (que pode ser ``None``): o
    resto do conteúdo é copiado byte a byte e o portão é conteúdo. ``--policy
    none`` remove tudo, e recusa quando não há o que remover, porque um comando
    que não faz nada não deve parecer que fez.

    Com ``--policy``, o argumento é o portão **inteiro** da filha — e é por isso
    que ele **recusa** quando deixa de fora uma regra que o pai tinha (T3.59).
    Escrever ``--policy hours=12-15`` sobre um pai com portão de regime tiraria
    o portão de regime em silêncio: a filha decidiria em *mais* contexto que o
    pai, que é a única direção perigosa, e a coorte mediria outra coisa. Para
    tirar uma regra e manter a outra existe ``<portão>=none``, que é uma frase.
    """
    if argument is None:
        return parent
    if argument.strip().lower() == NO_POLICY:
        if parent is None:
            raise Refused("--policy none: o pai já não tem portão, não há o que remover")
        return None
    try:
        chosen = policy_argument(argument)
        named = set(policy_clauses(argument))
    except PolicyError as invalid:
        raise Refused(f"--policy {argument!r}: {invalid}") from invalid
    if dropped := sorted(set(parent or {}) - named):
        raise Refused(
            f"--policy {argument!r} não menciona o portão {', '.join(dropped)}, que o pai tem: "
            "repita-o no argumento, escreva <portão>=none para tirá-lo, ou --policy none para "
            "tirar o portão inteiro — largar uma regra em silêncio faria a filha decidir em "
            "mais contexto que o pai"
        )
    return chosen
