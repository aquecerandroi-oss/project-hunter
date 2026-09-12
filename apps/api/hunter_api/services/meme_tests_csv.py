"""The test record as a CSV for Excel in pt-BR (T4.13): UTF-8 **with BOM**,
``;`` as the separator, CRLF, decimals with a **comma** (the pt-BR locale
reads ``0.18`` as text when the separator is ``;``), Brasília timestamps with
seconds, ``sim``/``não`` for booleans, and an empty cell for every honest
absence. Column order is ``CSV_COLUMNS`` — a change here is a change of the
byte-exact fixture in ``tests/integration/test_meme_tests_api.py``.
"""

from __future__ import annotations

import csv
import io
from datetime import datetime
from decimal import Decimal
from typing import Final

from hunter_api.schemas.lab_common import decimal_plain
from hunter_api.schemas.meme_tests import TestRowOut
from hunter_api.services.meme_tests import BRASILIA

__all__ = ["CSV_COLUMNS", "CSV_MAX_ROWS", "csv_filename", "render_tests_csv"]

CSV_MAX_ROWS: Final = 5000
"""A day's ceiling for the export; past it the file says so in its last row."""

CSV_COLUMNS: Final[tuple[str, ...]] = (
    "id",
    "tipo",
    "conjunto",
    "perna",
    "moeda",
    "simbolo",
    "mint",
    "estado",
    "entrada_hora_brasilia",
    "entrada_preco_sol_por_token",
    "entrada_mcap_sol",
    "entrada_sol_gasto",
    "entrada_tokens",
    "entrada_taxa_sol",
    "entrada_atraso_fill_s",
    "saida_hora_brasilia",
    "saida_provisoria",
    "saida_preco_sol_por_token",
    "saida_mcap_sol",
    "saida_sol_recebido",
    "saida_taxa_sol",
    "motivo",
    "duracao_s",
    "pnl_sol",
    "pnl_usd",
    "pnl_usd_base",
    "cotacao_sol_usd_entrada",
    "cotacao_sol_usd_saida",
    "cotacao_fonte",
    "r",
    "lab_minuto_brasilia",
    "lab_versao",
    "lab_linha_tracavel",
    "lab_motivo_linha",
    "lab_hype_score",
    "lab_criador_vendeu",
    "lab_progresso",
    "lab_gatilhos",
    "carteira",
)

TRUNCATED_NOTICE = f"limite de {CSV_MAX_ROWS} linhas atingido — filtre por conjunto para o resto"


def _dec(value: Decimal | None) -> str:
    return "" if value is None else decimal_plain(value).replace(".", ",")


def _when(value: datetime | None) -> str:
    return "" if value is None else value.astimezone(BRASILIA).strftime("%d/%m/%Y %H:%M:%S")


def _yes_no(value: bool | None) -> str:
    if value is None:
        return ""
    return "sim" if value else "não"


def _int(value: int | None) -> str:
    return "" if value is None else str(value)


def _text(value: str | None) -> str:
    return value or ""


def _row(r: TestRowOut) -> list[str]:
    lab = r.lab_context
    return [
        r.id,
        "REAL" if r.kind == "real_observed" else "PAPEL",
        r.rule_set.label,
        r.leg,
        _text(r.token_name),
        _text(r.token_symbol),
        r.mint,
        "aberta" if r.status == "open" else "fechada",
        _when(r.entry.at),
        _dec(r.entry.price_sol_per_token),
        _dec(r.entry.mcap_sol),
        _dec(r.entry.sol_spent),
        _dec(r.entry.tokens),
        _dec(r.entry.fee_sol),
        _int(r.entry.fill_delay_s),
        _when(r.exit.at),
        _yes_no(r.exit.provisional),
        _dec(r.exit.price_sol_per_token),
        _dec(r.exit.mcap_sol),
        _dec(r.exit.sol_received),
        _dec(r.exit.fee_sol),
        r.exit.reason_label,
        _int(r.duration_s),
        _dec(r.pnl_sol),
        _dec(r.pnl_usd),
        _text(r.pnl_usd_basis),
        _dec(r.sol_usd_at_entry),
        _dec(r.sol_usd_at_exit),
        _text(r.sol_usd_source),
        _dec(r.r_multiple),
        _when(lab.features_end_time),
        _text(lab.features_version),
        _yes_no(lab.line_drawn),
        _text(lab.line_reason),
        _dec(lab.hype_score),
        _yes_no(lab.creator_sold),
        _dec(lab.curve_progress_pct),
        " ".join(str(g) for g in lab.gate_reasons),
        _text(r.wallet),
    ]


def render_tests_csv(rows: list[TestRowOut], *, truncated: bool = False) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")
    writer.writerow(CSV_COLUMNS)
    for row in rows:
        writer.writerow(_row(row))
    if truncated:
        writer.writerow([TRUNCATED_NOTICE])
    return b"\xef\xbb\xbf" + buffer.getvalue().encode("utf-8")


def csv_filename(day: str) -> str:
    return f"testes-meme-{day}.csv"
