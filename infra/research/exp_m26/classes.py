"""`linha_ok` em três classes e o motivo único de cada oportunidade (§2.2, §4).

**Classe** — lida só dos insumos gravados em R1 no tique (`evaluated_at`, o relógio único):

- `true`: linha traçada, coberta, `higher_lows` ∧ `breakout_15m` ∧ distância ∈ [0; teto];
- `false`: traçada e coberta com algum critério falho, ou `flat`/`out_of_range` cobertos
  (o `false` operacional da v1, contado à parte);
- `desconhecida`: falha de coleta — cobertura `gap`/`unread`, `no_snapshot`,
  `too_few_points`, linha ausente, `computed_at` ausente. Nunca vira `false`.

**Motivo** — um por oportunidade, na ordem fidelity → E → U → I → F → C → A:

- `fidelity` ≠ `faithful`: o registro não é a 1.ª passagem provada (DATABASE §68). É
  instrumento (I da classe gravada, ou U se desconhecida) antes de E, porque as recusas
  gravadas não são as da 1.ª oportunidade (J);
- E: recusa substantiva comprovada (`creator_serial`, `symbol_clone`);
- U: classe desconhecida (fora dos grupos);
- I: sem proposta por instrumento (pedigree desconhecido, cotação, falha de escrita, …);
- F: proposta sem fill na leitura (inclui `rule_set_inactive`);
- C: preenchida sem desfecho precificável (aberta na leitura, `indeterminate`, venda sem
  praça pelo estado da foto de venda, qualquer que seja o gatilho);
- A: avaliável.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from infra.research.exp_m26.constantes import (
    COBERTAS,
    EXCLUSOES_SUBSTANTIVAS,
    FALSE_OPERACIONAL,
    FIDEDIGNA,
    PISO_DISTANCIA,
    TETO_DISTANCIA,
)
from infra.research.exp_m26.modelo import Aposta, Oportunidade
from infra.research.guards import Instants, LookAheadError, check_observable

MOTIVOS = ("E", "U", "I", "F", "C", "A")


def verificar_relogio(o: Oportunidade) -> None:
    """A linha julgada fechou e foi dobrada até o tique; senão o export está errado."""
    computed = o.features_end_time if o.features_computed_at is None else o.features_computed_at
    inst = Instants(as_of=o.features_end_time, computed_at=computed)
    why = check_observable(inst, o.evaluated_at, f"H-022 {o.mint}")
    if why is not None:
        raise LookAheadError(f"H-022 {o.mint}: {why}")


def classe_linha(o: Oportunidade, teto: Decimal = TETO_DISTANCIA) -> tuple[str, str]:
    """`(classe, detalhe)`; `teto` só muda no planalto (0,10 / 0,25 / 0,50)."""
    verificar_relogio(o)
    if o.features_computed_at is None:
        return "desconhecida", "computed_at_ausente"
    if o.coverage_status not in COBERTAS:
        return "desconhecida", f"cobertura:{o.coverage_status}"
    if o.line_reason in FALSE_OPERACIONAL:
        return "false", str(o.line_reason)
    if o.line_reason is not None:
        return "desconhecida", f"linha:{o.line_reason}"
    dist = o.distance_to_support_pct
    if o.higher_lows is None or o.breakout_15m is None or dist is None:
        return "desconhecida", "linha:ausente"
    ok = o.higher_lows and o.breakout_15m and PISO_DISTANCIA <= dist <= teto
    return ("true" if ok else "false"), "tracada"


def censura_da_aposta(a: Aposta) -> str | None:
    """O motivo de uma compra preenchida não ter desfecho precificável, ou `None`."""
    if a.status != "closed" or a.exit_at is None:
        return "aberta_na_leitura"
    if a.outcome_quality != "measured":
        return a.outcome_quality
    if a.sale_observed_at is None:
        return "sem_foto_de_venda"
    if a.sale_complete:
        return "venda_sem_praca:complete"
    for nome, quando in (
        ("completed_at", a.token_completed_at),
        ("migrated_at", a.token_migrated_at),
    ):
        if quando is not None and a.sale_observed_at >= quando:
            return f"venda_sem_praca:{nome}"
    if a.pnl_sol is None:
        return "sem_pnl"
    return None


def exclusao(o: Oportunidade) -> str | None:
    hits = [r for r in EXCLUSOES_SUBSTANTIVAS if r in o.proposal_refusals]
    return None if not hits else "exclusao:" + "+".join(hits)


def motivo(o: Oportunidade) -> tuple[str, str]:
    """`(E|U|I|F|C|A, detalhe)` — a classe vem de `classe_linha`, o resto do caminho."""
    classe, detalhe = classe_linha(o)
    if o.fidelity != FIDEDIGNA:
        return ("U" if classe == "desconhecida" else "I"), f"fidelity:{o.fidelity}"
    excl = exclusao(o)
    if excl is not None:
        return "E", excl
    if classe == "desconhecida":
        return "U", detalhe
    if o.proposal_id is None:
        return "I", f"sem_proposta:{o.no_proposal_reason}:{'+'.join(o.proposal_refusals)}"
    if o.aposta is None:
        return "F", f"sem_fill:{o.proposal_status}:{o.proposal_refusal or ''}"
    censura = censura_da_aposta(o.aposta)
    if censura is not None:
        return "C", censura
    return "A", "avaliavel"


def bloco_de(t: datetime) -> str:
    """O estrato e o bloco do bootstrap: `(data UTC, ⌊hora/6⌋)`, semiaberto."""
    u = t.astimezone(UTC)
    return f"{u.date().isoformat()}T{(u.hour // 6) * 6:02d}"


@dataclass(frozen=True)
class Registro:
    """Uma oportunidade de C já classificada, com o seu motivo único."""

    o: Oportunidade
    classe: str
    detalhe_classe: str
    motivo: str
    detalhe: str

    @property
    def bloco(self) -> str:
        return bloco_de(self.o.evaluated_at)

    @property
    def y(self) -> float | None:
        a = self.o.aposta
        return None if self.motivo != "A" or a is None else a.retorno()

    @property
    def perda(self) -> float | None:
        a = self.o.aposta
        return None if self.motivo != "C" or a is None else a.perda_integral()


def registrar(o: Oportunidade) -> Registro:
    classe, detalhe_classe = classe_linha(o)
    m, detalhe = motivo(o)
    return Registro(o, classe, detalhe_classe, m, detalhe)
