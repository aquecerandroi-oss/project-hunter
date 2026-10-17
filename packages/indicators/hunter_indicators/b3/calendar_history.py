"""B3 sessions 2021–2026 for the retrospective WIN studies (H-038r, H-039, H-040, H-041), as data.

Transcribed by the quant-engineer on 17/10/2026 from the official B3 page "Calendário do
mercado" (one tab per year, 2021 to 2026):
https://www.b3.com.br/pt_br/solucoes/plataformas/puma-trading-system/para-participantes-e-traders/calendario-de-negociacao/feriados/
Kept: every weekday whose "Segmento BM&FBOVESPA"/"Listado B3" text says "Não haverá
negociação nos mercados de renda variável [...] e de derivativos listados", and the Ash
Wednesdays ("A negociação e o registro terão início às 13h"). Nothing else on the page
changes listed trading hours. The page has no year before 2021, so nothing before
04/01/2021 is covered. The 2022 World Cup did not change B3 hours
(https://www.b3.com.br/pt_br/noticias/funcionamento-na-copa.htm, read 17/10/2026).

WIN expiry — https://www.b3.com.br/pt_br/produtos-e-servicos/negociacao/renda-variavel/futuro-mini-de-ibovespa.htm
(read 17/10/2026): "Quarta-feira mais próxima do dia 15 do mês de vencimento. Caso não
houver sessão de negociação, a data de vencimento será a próxima sessão de negociação";
"Meses de vencimento: Meses pares".

This module says which days trade; it does not vouch for the hours of each day (the
studies treat O = 10:00 BRT as an assumption checked by bar timestamps). Outside the
coverage it raises instead of guessing.
"""

from __future__ import annotations

from datetime import date, timedelta

COVERAGE_START = date(2021, 1, 1)
COVERAGE_END = date(2026, 12, 31)

NO_TRADING_DAYS: dict[date, str] = {
    date(2021, 1, 1): "Confraternização Universal",
    date(2021, 1, 25): "Aniversário de São Paulo",
    date(2021, 2, 15): "Carnaval",
    date(2021, 2, 16): "Carnaval",
    date(2021, 4, 2): "Paixão de Cristo",
    date(2021, 4, 21): "Tiradentes",
    date(2021, 6, 3): "Corpus Christi",
    date(2021, 7, 9): "Revolução Constitucionalista",
    date(2021, 9, 7): "Independência do Brasil",
    date(2021, 10, 12): "Nossa Senhora Aparecida",
    date(2021, 11, 2): "Finados",
    date(2021, 11, 15): "Proclamação da República",
    date(2021, 12, 24): "Véspera de Natal",
    date(2021, 12, 31): "Expediente interno (sem sessão de negociação)",
    date(2022, 2, 28): "Carnaval",
    date(2022, 3, 1): "Carnaval",
    date(2022, 4, 15): "Paixão de Cristo",
    date(2022, 4, 21): "Tiradentes",
    date(2022, 6, 16): "Corpus Christi",
    date(2022, 9, 7): "Independência do Brasil",
    date(2022, 10, 12): "Nossa Senhora Aparecida",
    date(2022, 11, 2): "Finados",
    date(2022, 11, 15): "Proclamação da República",
    date(2022, 12, 30): "Expediente interno (sem sessão de negociação)",
    date(2023, 2, 20): "Carnaval",
    date(2023, 2, 21): "Carnaval",
    date(2023, 4, 7): "Paixão de Cristo",
    date(2023, 4, 21): "Tiradentes",
    date(2023, 5, 1): "Dia do Trabalho",
    date(2023, 6, 8): "Corpus Christi",
    date(2023, 9, 7): "Independência do Brasil",
    date(2023, 10, 12): "Nossa Senhora Aparecida",
    date(2023, 11, 2): "Finados",
    date(2023, 11, 15): "Proclamação da República",
    date(2023, 12, 25): "Natal",
    date(2023, 12, 29): "Expediente interno (sem sessão de negociação)",
    date(2024, 1, 1): "Confraternização Universal",
    date(2024, 2, 12): "Carnaval",
    date(2024, 2, 13): "Carnaval",
    date(2024, 3, 29): "Paixão de Cristo",
    date(2024, 5, 1): "Dia do Trabalho",
    date(2024, 5, 30): "Corpus Christi",
    date(2024, 11, 15): "Proclamação da República",
    date(2024, 11, 20): "Consciência Negra",
    date(2024, 12, 24): "Expediente interno (sem sessão de negociação)",
    date(2024, 12, 25): "Natal",
    date(2024, 12, 31): "Expediente interno (sem sessão de negociação)",
    date(2025, 1, 1): "Confraternização Universal",
    date(2025, 3, 3): "Carnaval",
    date(2025, 3, 4): "Carnaval",
    date(2025, 4, 18): "Sexta-feira Santa",
    date(2025, 4, 21): "Tiradentes",
    date(2025, 5, 1): "Dia do Trabalho",
    date(2025, 6, 19): "Corpus Christi",
    date(2025, 11, 20): "Dia Nacional de Zumbi e Consciência Negra",
    date(2025, 12, 24): "Véspera de Natal (sem sessão de negociação)",
    date(2025, 12, 25): "Natal",
    date(2025, 12, 31): "Expediente interno (sem sessão de negociação)",
    date(2026, 1, 1): "Confraternização Universal",
    date(2026, 2, 16): "Carnaval",
    date(2026, 2, 17): "Carnaval",
    date(2026, 4, 3): "Sexta-feira Santa",
    date(2026, 4, 21): "Tiradentes",
    date(2026, 5, 1): "Dia do Trabalho",
    date(2026, 6, 4): "Corpus Christi",
    date(2026, 9, 7): "Independência do Brasil",
    date(2026, 10, 12): "Nossa Senhora Aparecida",
    date(2026, 11, 2): "Finados",
    date(2026, 11, 20): "Dia Nacional de Zumbi e Consciência Negra",
    date(2026, 12, 24): "Véspera de Natal (sem sessão de negociação)",
    date(2026, 12, 25): "Natal",
    date(2026, 12, 31): "Expediente interno (sem sessão de negociação)",
}
"""Weekdays only (a holiday on a weekend changes nothing)."""

SHORTENED_DAYS: dict[date, str] = {
    date(2021, 2, 17): "Quarta-feira de Cinzas (início às 13h)",
    date(2022, 3, 2): "Quarta-feira de Cinzas (início às 13h)",
    date(2023, 2, 22): "Quarta-feira de Cinzas (início às 13h)",
    date(2024, 2, 14): "Quarta-feira de Cinzas (início às 13h)",
    date(2025, 3, 5): "Quarta-feira de Cinzas (início às 13h)",
    date(2026, 2, 18): "Quarta-feira de Cinzas (início às 13h)",
}


class OutsideHistoryCoverage(LookupError):
    """The date is outside the B3 calendars this module was transcribed from."""


def _check(day: date) -> None:
    if not COVERAGE_START <= day <= COVERAGE_END:
        raise OutsideHistoryCoverage(
            f"{day.isoformat()} outside {COVERAGE_START.isoformat()}..{COVERAGE_END.isoformat()}"
        )


def is_session(day: date) -> bool:
    _check(day)
    return day.weekday() < 5 and day not in NO_TRADING_DAYS


def nearest_wednesday_to_15(year: int, month: int) -> date:
    """The Wednesday closest to the 15th (never a tie: the distances are 0..3 vs 4..6)."""
    fifteenth = date(year, month, 15)
    forward = (2 - fifteenth.weekday()) % 7
    return fifteenth + timedelta(days=forward if forward <= 3 else forward - 7)


def win_expiry(year: int, month: int) -> date:
    """Last trading day of the WIN of ``month`` (even months only)."""
    if month % 2:
        raise ValueError(f"WIN expires in even months only, not {month}")
    day = nearest_wednesday_to_15(year, month)
    while not is_session(day):
        day += timedelta(days=1)
    return day


def is_win_expiry(day: date) -> bool:
    return day.month % 2 == 0 and day == win_expiry(day.year, day.month)


def sessions_between(start: date, end: date) -> list[date]:
    """Every B3 session in ``[start, end]`` (both inside the coverage)."""
    _check(start)
    _check(end)
    out: list[date] = []
    day = start
    while day <= end:
        if is_session(day):
            out.append(day)
        day += timedelta(days=1)
    return out
