"""B3 sessions for the first H-038 weeks (19/10/2026 – 31/12/2026), as data.

Read by the quant-engineer on 17/10/2026 from the official B3 pages (no snippet, the pages
themselves):

- Holidays — "Calendário do mercado 2026":
  https://www.b3.com.br/pt_br/solucoes/plataformas/puma-trading-system/para-participantes-e-traders/calendario-de-negociacao/feriados/
  In the covered window, "não haverá negociação nos mercados de renda variável [...] e de
  derivativos listados" on 02/11 (Finados), 20/11 (Dia Nacional de Zumbi e Consciência
  Negra), 24/12 (Véspera de Natal), 25/12 (Natal) and 31/12 (expediente interno, sem sessão
  de negociação). 11/11 (Veterans Day) and 26/11 (Thanksgiving) only change the FX clearing;
  listed trading is normal. No shortened session is listed in the window.
- Current cash-equity grid — "Horários de negociação no mercado de ações":
  https://www.b3.com.br/pt_br/solucoes/plataformas/puma-trading-system/para-participantes-e-traders/horario-de-negociacao/acoes/
  à vista: negociação 10:00–16:55, call de fechamento 16:55–17:00.
- Grid from 03/11/2026 — Ofício Circular 050/2026-VNC (13/10/2026), Anexo 2:
  https://www.b3.com.br/data/files/99/B7/82/67/8A631A103BBB511AAC094EA8/OC%20050-2026-VNC%20NOVOS%20HORARIOS%20DE%20NEGOCIACAO_PT.pdf
  à vista: negociação 10:00–17:55, call de fechamento 17:55–18:00 (WIN 09:00–18:25, Anexo 1).
- WIN contract — https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/renda-variavel/futuro-mini-de-ibovespa.htm
  R$ 0,20 per point, minimum price variation 5 points, last trading day "quarta-feira mais
  próxima do dia 15 do mês de vencimento" → WINZ26 expires Wed 16/12/2026 (15/12 is a
  Tuesday). Derived from the rule; B3's expiry page is rendered by script and was not read.

Brazil has had no daylight saving since 2019 (Decreto 9.772/2019), so BRT is a fixed UTC−3
here; no tz database is needed. Outside the coverage :func:`b3_session` raises instead of
guessing: extend this table (with its source) before using another date.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal

from hunter_indicators.b3.contract import InstrumentSpec, NoTradeReason, SessionTimes

BRT = timezone(timedelta(hours=-3), "BRT")

COVERAGE_START = date(2026, 10, 19)
COVERAGE_END = date(2026, 12, 31)
_GRID_KNOWN_FROM = date(2026, 10, 13)
"""Earliest date the current grid is vouched for (OC 050 of 13/10 says it holds until 30/10);
used only to find the previous session of the first covered day."""

NO_TRADING_DAYS: dict[date, str] = {
    date(2026, 10, 12): "Nossa Sra. Aparecida",
    date(2026, 11, 2): "Finados",
    date(2026, 11, 20): "Dia Nacional de Zumbi e Consciência Negra",
    date(2026, 12, 24): "Véspera de Natal (sem sessão de negociação)",
    date(2026, 12, 25): "Natal",
    date(2026, 12, 31): "Expediente interno (sem sessão de negociação)",
}

SHORTENED_DAYS: dict[date, str] = {}
"""None in the covered window (B3 2026 calendar, read 17/10/2026)."""

# (valid from, cash-market open O, end of the closing call C), local BRT times.
_GRIDS: tuple[tuple[date, time, time], ...] = (
    (_GRID_KNOWN_FROM, time(10, 0), time(17, 0)),
    (date(2026, 11, 3), time(10, 0), time(18, 0)),
)

WIN_SPEC = InstrumentSpec(root="WIN", tick_size=Decimal("5"), point_value_brl=Decimal("0.20"))

# (last trading day, contract code), in order; the next code trades from the following session.
_WIN_EXPIRIES: tuple[tuple[date, str], ...] = ((date(2026, 12, 16), "WINZ26"),)
_WIN_AFTER_LAST = "WING27"


class OutsideCalendarCoverage(LookupError):
    """The date is outside the B3 data this module was built from."""


def _is_session(day: date) -> bool:
    return day.weekday() < 5 and day not in NO_TRADING_DAYS


def _grid(day: date) -> tuple[time, time]:
    chosen: tuple[time, time] | None = None
    for valid_from, open_t, close_t in _GRIDS:
        if day >= valid_from:
            chosen = (open_t, close_t)
    if chosen is None:
        raise OutsideCalendarCoverage(f"no B3 grid on file for {day.isoformat()}")
    return chosen


def _at(day: date, local: time) -> datetime:
    return datetime.combine(day, local, tzinfo=BRT)


def _previous_session(day: date) -> date:
    prev = day - timedelta(days=1)
    while not _is_session(prev):
        prev -= timedelta(days=1)
    return prev


def b3_session(day: date) -> SessionTimes | None:
    """The B3 session on ``day`` (UTC instants), or ``None`` when B3 does not trade."""
    if not COVERAGE_START <= day <= COVERAGE_END:
        raise OutsideCalendarCoverage(
            f"{day.isoformat()} outside {COVERAGE_START.isoformat()}..{COVERAGE_END.isoformat()}"
        )
    if not _is_session(day):
        return None
    open_t, close_t = _grid(day)
    prev = _previous_session(day)
    exclusions: list[NoTradeReason] = []
    if day in SHORTENED_DAYS:
        exclusions.append(NoTradeReason.SHORTENED_SESSION)
    if any(day == last for last, _ in _WIN_EXPIRIES):
        exclusions.append(NoTradeReason.WIN_EXPIRY_DAY)
    return SessionTimes(
        trading_date=day,
        open_at=_at(day, open_t),
        close_at=_at(day, close_t),
        previous_close_at=_at(prev, _grid(prev)[1]),
        exclusions=tuple(exclusions),
    )


def win_contract(day: date) -> str:
    """The WIN code to trade on ``day``: the current one up to its last day, then the next."""
    if not COVERAGE_START <= day <= COVERAGE_END:
        raise OutsideCalendarCoverage(f"no WIN expiry data for {day.isoformat()}")
    for last, code in _WIN_EXPIRIES:
        if day <= last:
            return code
    return _WIN_AFTER_LAST
