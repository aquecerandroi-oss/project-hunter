"""Onda 0 de "seguir carteiras que ganham de verdade" — sondagem do programa INTEIRO (pump.fun +
PumpSwap) por RPC público, desta máquina (nunca da VPS). Desenho: docs/design/seguir-carteiras-lucrativas.md
§2 e §6 (linha 0); aprovação: obsidian/06-DECISIONS/2026-10-05-seguir-carteiras-lucrativas-aprovado.md.

Só leitura de rede: ``logsSubscribe`` (``mentions`` = o programa, ``confirmed``) em cada programa, uma
conexão por programa, mais ``slotSubscribe`` na mesma conexão (o relógio de slots para medir o atraso), e
uma amostra de ``getTransaction`` por HTTP (1 a cada ``--sample-every`` s) para conferir se os logs
trazem tudo o que o programa emitiu como evento. Nunca envia transação, nunca lê ``.env``: as URLs só
vêm do argv. Decodifica com os decodificadores COMMITADOS (``TradeEvent`` com a cauda da T4.8e;
``SellEvent`` da PumpSwap); o ``BuyEvent`` da PumpSwap não tem decodificador: é contado cru.

Saídas em ``--out`` (padrão ``.claude/state/carteiras-lucro/probe/``): ``snapshots.jsonl`` (uma linha por
minuto), ``summary.json`` (final), ``samples.json`` (frames crus de exemplo e eventos que não decodificaram).

    uv run --no-sync python infra/scripts/research/2026-10-05-wallet-tape-probe.py --seconds 7140 \\
        > .claude/state/carteiras-lucro/probe/run.log 2>&1

Reconexão: backoff exponencial com jitter (teto 30 s), nunca laço apertado; recusa do servidor
(HTTP 429/403, erro de assinatura) vira registro ``rejects`` com o texto, não retentativa silenciosa.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from wallet_tape_probe_net import run
from wallet_tape_probe_rt import PUBLIC_HTTP, PUBLIC_WS, Runtime


def main() -> None:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--seconds", type=float, default=7200)
    p.add_argument("--ws-url", default=PUBLIC_WS)
    p.add_argument("--http-url", default=PUBLIC_HTTP)
    p.add_argument(
        "--commitment", default="confirmed", choices=["processed", "confirmed", "finalized"]
    )
    p.add_argument(
        "--sample-every", type=float, default=2.0, help="getTransaction/getSlot cadence; 0 = off"
    )
    p.add_argument(
        "--audit-every", type=float, default=45.0, help="getBlock coverage audit cadence; 0 = off"
    )
    p.add_argument(
        "--keep-awake",
        action="store_true",
        help="Windows: ask the OS not to sleep while this process runs (cleared when it exits)",
    )
    p.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[3] / ".claude/state/carteiras-lucro/probe"),
    )
    args = p.parse_args()
    if args.keep_awake and sys.platform == "win32":
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(
            0x80000001
        )  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    asyncio.run(run(Runtime(args)))


if __name__ == "__main__":
    main()
