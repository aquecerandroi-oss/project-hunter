"""T3.50 — uma operação concluída do Lab, desenhada: velas, linhas, níveis, saída.

Irmão de ``render_operations.py`` por orçamento de arquivo (350 linhas,
``infra/scripts/check_file_size.py``), não por gosto: aqui mora tudo o que
lê uma linha do JSONL exportado e reconstrói a geometria dela; o desenho em si
está em ``render_operations_draw.py`` (o único módulo que importa matplotlib) e
a CLI, a exportação somente-leitura e as notas do Obsidian estão em
``render_operations.py``.

Três regras que este módulo existe para não violar:

1. **A geometria é a mesma do código congelado.** As linhas vêm de
   ``hunter_core.strategies.tl_scan.tl_scan`` com
   ``pattern_params(TrendlineBreakoutV1.default_parameters)`` — o mesmo código
   que decide de verdade, não uma reimplementação para desenhar.
2. **Nada depois da barra da decisão entra no traçado das linhas.** ``tl_scan``
   aplica o corte uma vez (``bars[: as_of + 1]``), e ``as_of`` é o índice da
   barra da decisão. As barras posteriores existem no gráfico para mostrar o que
   aconteceu com a operação; elas não podem mover uma linha. Provado por
   ``infra/scripts/tests/test_render_operations.py``.
3. **``Decimal`` até a borda.** Nada aqui vira ``float``; ``float`` só existe no
   módulo de desenho, onde estão os pixels.

As linhas de um gráfico de ``momentum``, ``mean_reversion`` ou ``session_orb``
são **contexto calculado depois**, pelo mesmo scanner congelado: nenhuma dessas
versões lê linha de tendência para decidir. A única que lê é
``trendline_breakout_v1``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from hunter_core.domain.enums import Timeframe
from hunter_core.strategies.aggregate import Bar
from hunter_core.strategies.tl_scan import TlScan, tl_scan
from hunter_core.strategies.tl_setup import pattern_params
from hunter_core.strategies.trendline_breakout_v1 import TrendlineBreakoutV1

BRT = timezone(timedelta(hours=-3), "BRT")
STEP = timedelta(minutes=15)

PATTERN_BARS = 96
"""``trendline_breakout_v1.default_parameters['pattern_bars']`` — a janela em que
a geometria é procurada, repetida aqui como constante local para o desenho não
mudar sozinho se outra versão nascer com outra janela."""

MIN_GEOMETRY_BARS = 20
"""Abaixo disto não há geometria a reportar: o ATR de Wilder(14) só existe a
partir da barra 16 e um pivô precisa de ``k = 3`` barras de cada lado. Uma
corrida contígua menor sai como "sem geometria", nunca como "nenhuma linha"."""

PARAMS = pattern_params(TrendlineBreakoutV1.default_parameters)


def _dec(value: Any) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _ts(value: Any) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(UTC)


@dataclass(frozen=True, slots=True)
class Operation:
    """Uma operação concluída: a decisão, os níveis, a saída e as velas."""

    signal_id: str
    symbol: str
    strategy: str
    version: str
    code_ref: str
    cohort: str
    coorte: str
    direction: str
    decision_at: datetime
    decision_bar_close: datetime
    entry: Decimal | None
    entry_ts: datetime | None
    stop: Decimal | None
    targets: tuple[Decimal, ...]
    exit_price: Decimal | None
    exit_ts: datetime | None
    result: str
    r_multiple: Decimal | None
    reason: str
    features: dict[str, str]
    bars: tuple[Bar, ...]

    @property
    def label(self) -> str:
        return f"{self.strategy} {self.version}"

    @property
    def brt(self) -> datetime:
        return self.decision_bar_close.astimezone(BRT)

    @property
    def used_line_id(self) -> str | None:
        """``line_id`` que a estratégia usou — só existe em decisão de linha."""
        return self.features.get("line_id")

    def filename(self) -> str:
        stamp = self.decision_bar_close.astimezone(UTC).strftime("%Y%m%d-%H%M")
        return f"{stamp}Z-{self.symbol}-{self.result}.png"


def _features(raw: dict[str, Any]) -> dict[str, str]:
    """``supporting_features.features`` achatado em ``nome -> valor`` textual."""
    out: dict[str, str] = {}
    items: list[Any] = raw.get("features") or []
    for item in items:
        if not isinstance(item, dict):
            continue
        entry = cast("dict[str, Any]", item)
        name, value = entry.get("name"), entry.get("value")
        if isinstance(name, str) and value is not None:
            out[name] = str(value)
    return out


def _bars(rows: list[Any]) -> tuple[Bar, ...]:
    out: list[Bar] = []
    for row in rows:
        start = _ts(row[0])
        if start is None:
            raise ValueError("bucket sem instante no JSONL exportado")
        out.append(
            Bar(
                open_time=start,
                close_time=start + STEP,
                open=Decimal(str(row[1])),
                high=Decimal(str(row[2])),
                low=Decimal(str(row[3])),
                close=Decimal(str(row[4])),
                volume=Decimal(str(row[5])),
            )
        )
    return tuple(out)


def parse_operation(raw: dict[str, Any]) -> Operation:
    decision_at, bar_close = _ts(raw["decision_at"]), _ts(raw["decision_bar_close"])
    if decision_at is None or bar_close is None:
        raise ValueError("operação sem instante de decisão")
    raw_targets: list[Any] = raw.get("virtual_targets") or []
    targets = tuple(d for d in (_dec(t) for t in raw_targets) if d is not None)
    return Operation(
        signal_id=str(raw["signal_id"]),
        symbol=str(raw["symbol"]),
        strategy=str(raw["strategy"]),
        version=str(raw["version"]),
        code_ref=str(raw.get("code_ref") or ""),
        cohort=str(raw.get("cohort") or ""),
        coorte=str(raw.get("coorte") or ""),
        direction=str(raw.get("direction") or ""),
        decision_at=decision_at,
        decision_bar_close=bar_close,
        entry=_dec(raw.get("virtual_entry")),
        entry_ts=_ts(raw.get("entry_ts")),
        stop=_dec(raw.get("virtual_stop")),
        targets=targets,
        exit_price=_dec(raw.get("exit_price")),
        exit_ts=_ts(raw.get("exit_ts")),
        result=str(raw.get("result") or "open"),
        r_multiple=_dec(raw.get("r_multiple")),
        reason=str(raw.get("reason") or ""),
        features=_features(raw.get("supporting_features") or {}),
        bars=_bars(raw.get("bars") or []),
    )


def load_operations(path: Path) -> list[Operation]:
    with path.open(encoding="utf-8") as handle:
        return [
            parse_operation(json.loads(line, parse_float=Decimal))
            for line in handle
            if line.strip()
        ]


def decision_index(op: Operation) -> int:
    """Índice da barra da decisão, ou ``-1`` se nenhuma barra fechou até o corte.

    Nunca uma barra **posterior** ao corte: a busca é pela última barra cujo
    fechamento é ``<= decision_bar_close``.
    """
    found = -1
    for index, bar in enumerate(op.bars):
        if bar.close_time <= op.decision_bar_close:
            found = index
    return found


def geometry(op: Operation) -> tuple[TlScan | None, int]:
    """A varredura congelada no corte da decisão, e o deslocamento dela.

    Devolve ``(scan, offset)`` com ``scan.as_of`` no índice **local** da barra da
    decisão: a barra global correspondente é ``op.bars[offset + i]``. A janela é
    a corrida **contígua** de até ``PATTERN_BARS`` baldes completos terminando na
    decisão — ``atr_series`` levanta em buraco, e um balde incompleto não é
    exportado.
    """
    cut = decision_index(op)
    if cut < 0:
        return None, 0
    start = cut
    while (
        start > 0
        and cut - start + 1 < PATTERN_BARS
        and op.bars[start].open_time - op.bars[start - 1].open_time == STEP
    ):
        start -= 1
    window = op.bars[start : cut + 1]
    if len(window) < MIN_GEOMETRY_BARS:
        return None, start
    return tl_scan(window, timeframe=Timeframe.M15, params=PARAMS, as_of=len(window) - 1), start
