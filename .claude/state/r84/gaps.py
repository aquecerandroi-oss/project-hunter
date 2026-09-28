"""R84 — classificação manual das lacunas ≥ 14 d (notes §4): (símbolo, dia UTC da volta) do MESMO ativo → não parte.

Partidas (ticker reaproveitado por outro ativo ou fora do período/universo): LUNAUSDT 2022-05-31 (Terra 2.0 ≠ Terra
Classic), USDSUSDT 2026-04-09 (USDS da Sky ≠ StableUSD; E1), VENUSDT 2018-10-19 (antes do 1.º T), BCHUP/BCHDOWN e
ETHBULL/ETHBEAR (E2), USDC/USDP/TUSD (E1) — as de E1/E2 não entram no universo de qualquer forma.
"""

import datetime as _dt


def _d(y: int, m: int, d: int) -> int:
    return (_dt.date(y, m, d) - _dt.date(1970, 1, 1)).days


KEEP_TOGETHER: frozenset[tuple[str, int]] = frozenset({
    ("FTTUSDT", _d(2023, 9, 22)),  # FTX Token parado 2022-11-15 → volta 2023-09-22: o mesmo ativo
    ("CVCUSDT", _d(2023, 5, 12)),  # Civic: o mesmo ativo
    ("KEYUSDT", _d(2023, 3, 10)),  # SelfKey: o mesmo ativo
    ("NBTUSDT", _d(2022, 10, 1)),  # NanoByte: o mesmo ativo
})
