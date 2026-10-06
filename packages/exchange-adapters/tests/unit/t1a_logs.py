"""Wave 1a of H-030: shared helpers of the program-logs tests (names of the REAL fixtures and the
few functions that turn a ``getTransaction`` fixture into the inputs of ``read_program_logs``)."""

from __future__ import annotations

import base64
from datetime import UTC, datetime
from typing import Any

from hunter_exchanges.pumpfun.program_logs import ProgramLogsRead, read_program_logs

from .t1a_chain import tx_fixture

RECEIVED = datetime(2026, 10, 5, 23, 59, 0, tzinfo=UTC)
PREFIX = "Program data: "

AMM_BUY = "t1a_rpc_amm_buy_5SmrD75SgxDd_raw.json"
AMM_BUY_EXACT = "t1a_rpc_amm_buy_exact_5tKuWqTWBw8y_raw.json"
AMM_SELL = "t1a_rpc_amm_sell_551G1CF8C3Bx_raw.json"
AMM_SELL_NEXT = "t1a_rpc_amm_sell_4xuvoJjc286y_raw.json"
AMM_SELL_CASHBACK_X2 = "t1a_rpc_amm_sell_cashback_two_events_3gYxvcFECiai_raw.json"
V1_AMM_SELL = "t1a_rpc_v1_amm_sell_5Ls5TV77aYS3_raw.json"
V1_AMM_BUY_ROUTED = "t1a_rpc_v1_amm_buy_exact_holder_rewards_4JMsAJNT9otk_raw.json"
V1_PUMP_BUY = "t1a_rpc_v1_pump_buy_4b5YwBKdr5_raw.json"
V1_PUMP_SELL = "t1a_rpc_v1_pump_sell_37gcmBFxPWmF_raw.json"


def amm(name: str) -> dict[str, Any]:
    return tx_fixture("pumpswap", name)


def pump(name: str) -> dict[str, Any]:
    return tx_fixture("pumpfun", name)


def logs_of(tx: dict[str, Any]) -> list[str]:
    return [str(line) for line in tx["meta"]["logMessages"]]


def sig_of(tx: dict[str, Any]) -> str:
    return str(tx["transaction"]["signatures"][0])


def read(tx: dict[str, Any], logs: list[str] | None = None, err: Any = None) -> ProgramLogsRead:
    return read_program_logs(
        signature=sig_of(tx),
        slot=int(tx["slot"]),
        logs=logs_of(tx) if logs is None else logs,
        received_at=RECEIVED,
        err=err,
    )


def data_line_index(logs: list[str], nth: int = 0) -> int:
    return [i for i, line in enumerate(logs) if line.startswith(PREFIX)][nth]


def with_payload(logs: list[str], index: int, payload: bytes) -> list[str]:
    out = list(logs)
    out[index] = PREFIX + base64.b64encode(payload).decode()
    return out


def payload_of(logs: list[str], index: int) -> bytes:
    return base64.b64decode(logs[index][len(PREFIX) :])
