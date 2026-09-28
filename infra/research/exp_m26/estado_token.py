"""`completed_at`/`migrated_at` do token COMO CONHECIDOS EM L — puro.

`meme_tokens.completed_at` é escrito por `LEAST` e pode recuar (o `gd` retrospectivo do
indexador); `migrated_at` é escrito uma vez, mas com o instante do evento, não o da
escrita. Ler a linha corrente no export deixaria um fato chegado entre L e o export mudar
a leitura de L (must-fix 2 da revisão do J, Astra). A fonte é o histórico só de acréscimo
`meme_token_state_history` (`0067`, DATABASE §70): uma linha por mudança efetiva, escrita
por um gatilho **adiado para o commit**, com `recorded_at` = o relógio do banco no commit
(um lote que escreve antes de L e commita depois é registrado depois de L). "Conhecido em
L" é, operacionalmente, **carimbado no commit até L**: o valor em L é o da última mudança
(na ordem do `id`, a de commit dentro do mint — nunca a do relógio, que pode recuar) com
`recorded_at <= L`. Para que todo export da janela veja o mesmo conjunto de carimbos até
L, o export prova visibilidade (`provar_visibilidade`): nenhuma transação escritora aberta
desde antes de L ainda em voo quando ele começa, lida antes do snapshot dos dados.

Vias (a do mint é a pior das duas colunas; só `history` é estado conhecido em L):

- `history` — o histórico decide;
- `current_row_pre_history` — o valor não passou pelo gatilho (o `antes` da 1.ª mudança
  posterior a L, ou a linha corrente sem mudança nenhuma): anterior ao histórico, ou
  gatilho desligado. Só vale se `<= L`, e mesmo assim a leitura não o afirma (Astra, J
  rodada 3: "valor do evento ≤ L não prova escrita ≤ L");
- `historico_diverge` — a linha corrente difere da última mudança registrada (as duas saem
  do mesmo snapshot do export): alguém escreveu sem o gatilho;
- `token_ausente` — sem linha e sem histórico: estado desconhecido, nunca "não concluiu".
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

COLUNAS = ("completed_at", "migrated_at")
VIAS = ("history", "current_row_pre_history", "historico_diverge", "token_ausente")
"""Em ordem de gravidade."""


RECUO_TOLERADO_S = Decimal("1")
"""Premissa: o relógio do servidor não recua (NTP em *slew*). Detector: no histórico
inteiro, na ordem do `id`, nenhum carimbo mais de 1 s abaixo do maior anterior (dois
commits concorrentes podem se cruzar por microssegundos entre o `nextval` e o relógio)."""


class ExportSemProvaDeVisibilidade(RuntimeError):
    """O export não prova que toda mudança carimbada até L estava visível nele."""


@dataclass(frozen=True)
class ProvaDeVisibilidade:
    """A linha 'meta' do export, lida ANTES do snapshot dos dados. O padrão é a prova que
    recusa (`ve_toda_atividade` falso): um export sem os campos não prova nada."""

    escritoras_abertas_desde: datetime | None = None
    """O `xact_start` mais antigo das transações com xid (qualquer backend) desta base."""
    escritoras_sem_inicio: int = 0
    """Transações com xid cujo `xact_start` não aparece (`track_activities` desligado)."""
    preparadas: int = 0
    """Transações preparadas (2PC): o `PREPARE` carimba e a visibilidade vem depois."""
    relogio_recuou_s: Decimal = Decimal("0")
    """O maior recuo do carimbo na ordem do `id`, no histórico inteiro."""
    ve_toda_atividade: bool = False
    """Superusuário ou `pg_read_all_stats` com privilégio efetivo (`USAGE`, não `MEMBER`)."""


def provar_visibilidade(prova: ProvaDeVisibilidade, *, leitura: datetime) -> None:
    """Recusa o export que não prova que toda mudança carimbada até L estava visível nele
    (Astra, J rodadas 2 e 3). Tira-se outro export na janela."""
    if not prova.ve_toda_atividade:
        motivo = "o papel do export não enxerga a atividade de todos (pg_stat_activity)"
    elif prova.escritoras_sem_inicio > 0:
        motivo = f"{prova.escritoras_sem_inicio} transações com xid sem início conhecido"
    elif prova.preparadas > 0:
        motivo = f"{prova.preparadas} transações preparada(s) (2PC) no banco"
    elif prova.relogio_recuou_s > RECUO_TOLERADO_S:
        motivo = f"o relógio do banco recuou {prova.relogio_recuou_s} s no histórico"
    elif prova.escritoras_abertas_desde is not None and prova.escritoras_abertas_desde <= leitura:
        motivo = (
            f"transação escritora aberta desde {prova.escritoras_abertas_desde.isoformat()} "
            f"(<= L = {leitura.isoformat()}) ainda em voo no export"
        )
    else:
        return
    raise ExportSemProvaDeVisibilidade(f"{motivo}: sem prova de visibilidade em L")


@dataclass(frozen=True)
class Mudanca:
    """Uma linha de `meme_token_state_history`."""

    id: int
    coluna: str
    antes: datetime | None
    depois: datetime | None
    registrado_em: datetime


@dataclass(frozen=True)
class EstadoToken:
    """A linha `estado_token` do export: o token corrente e todo o seu histórico."""

    mint: str
    existe: bool
    completed_at_atual: datetime | None
    migrated_at_atual: datetime | None
    historico: tuple[Mudanca, ...]


@dataclass(frozen=True)
class EstadoEmL:
    completed_at: datetime | None
    migrated_at: datetime | None
    via: str


def _ordem(mudancas: Sequence[Mudanca]) -> list[Mudanca]:
    return sorted(mudancas, key=lambda m: m.id)


def _coluna(
    ordem: Sequence[Mudanca], atual: datetime | None, leitura: datetime
) -> tuple[datetime | None, str]:
    conhecidas = [m for m in ordem if m.registrado_em <= leitura]
    if conhecidas:
        return conhecidas[-1].depois, "history"
    anterior = ordem[0].antes if ordem else atual
    if anterior is None:
        return None, "history"
    return (anterior if anterior <= leitura else None), "current_row_pre_history"


def em(estado: EstadoToken, leitura: datetime) -> EstadoEmL:
    """O estado do token em `leitura` (L), e por qual via ele é conhecido."""
    if not estado.existe and not estado.historico:
        return EstadoEmL(None, None, "token_ausente")
    atual = {"completed_at": estado.completed_at_atual, "migrated_at": estado.migrated_at_atual}
    valores: dict[str, datetime | None] = {}
    vias: list[str] = []
    for c in COLUNAS:
        ordem = _ordem([m for m in estado.historico if m.coluna == c])
        valores[c], via = _coluna(ordem, atual[c], leitura)
        vias.append(via)
        if ordem and ordem[-1].depois != atual[c]:
            vias.append("historico_diverge")
    return EstadoEmL(valores["completed_at"], valores["migrated_at"], max(vias, key=VIAS.index))


def _dt(v: Any, campo: str) -> datetime | None:
    if v is None:
        return None
    if not isinstance(v, str):
        raise ValueError(f"{campo}: esperado instante ISO, veio {v!r}")
    t = datetime.fromisoformat(v)
    if t.tzinfo is None or t.utcoffset() is None:
        raise ValueError(f"{campo}: instante sem fuso ({v}); o moinho só lê UTC aware")
    return t


def prova_de_registro(meta: Mapping[str, Any]) -> ProvaDeVisibilidade:
    """A prova da linha 'meta' (JSON com `parse_float=Decimal`); campo ausente = a recusa."""
    return ProvaDeVisibilidade(
        escritoras_abertas_desde=_dt(meta.get("escritoras_abertas_desde"), "escritoras"),
        escritoras_sem_inicio=int(meta.get("escritoras_sem_inicio") or 0),
        preparadas=int(meta.get("preparadas") or 0),
        relogio_recuou_s=Decimal(str(meta.get("relogio_recuou_s") or 0)),
        ve_toda_atividade=meta.get("ve_toda_atividade") is True,
    )


def de_registro(r: Mapping[str, Any]) -> EstadoToken:
    """Uma linha `estado_token` do export (JSON já decodificado)."""
    hist: list[Mudanca] = []
    for h in r.get("historico") or ():
        if h.get("coluna") not in COLUNAS:
            raise ValueError(f"{r['mint']}: coluna fora do histórico ({h.get('coluna')!r})")
        quando = _dt(h["registrado_em"], "registrado_em")
        if quando is None:
            raise ValueError(f"{r['mint']}: mudança sem registrado_em")
        hist.append(
            Mudanca(
                id=int(h["id"]),
                coluna=str(h["coluna"]),
                antes=_dt(h.get("antes"), "antes"),
                depois=_dt(h.get("depois"), "depois"),
                registrado_em=quando,
            )
        )
    return EstadoToken(
        mint=str(r["mint"]),
        existe=bool(r["token_existe"]),
        completed_at_atual=_dt(r.get("completed_at_atual"), "completed_at_atual"),
        migrated_at_atual=_dt(r.get("migrated_at_atual"), "migrated_at_atual"),
        historico=tuple(hist),
    )


__all__ = [
    "COLUNAS",
    "VIAS",
    "EstadoEmL",
    "EstadoToken",
    "RECUO_TOLERADO_S",
    "ExportSemProvaDeVisibilidade",
    "Mudanca",
    "ProvaDeVisibilidade",
    "de_registro",
    "em",
    "prova_de_registro",
    "provar_visibilidade",
]
