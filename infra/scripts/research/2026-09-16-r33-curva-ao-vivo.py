"""R33 — read the *live* bonding curve of a list of mints straight from the chain.

Read-only research probe for KB-0115: the 1-minute series says half the coins
"go back to the empty-curve floor" (``mcap_sol`` ~28 SOL, progress < 5 %).  This
script asks the chain itself, with no worker and no database in the path, so the
answer cannot be an artefact of our own pipeline:

* derive the ``["bonding-curve", mint]`` PDA with the production helper
  (``hunter_exchanges.pumpfun.tx.bonding_curve_address``),
* ``getAccountInfo`` on the public mainnet RPC at ``finalized``,
* decode with the production decoder (``decode_bonding_curve_account``), which
  refuses anything whose owner or discriminator is not pump's.

Usage (local, never on the VPS)::

    uv run python infra/scripts/research/2026-09-16-r33-curva-ao-vivo.py MINT [MINT ...]

It prints one line per mint with ``real_sol_reserves``, ``virtual_sol_reserves``,
``complete``, ``is_mayhem_mode`` and the derived ``mcap_sol`` so the reading can
be put next to the last ``meme_features_1m`` row of the same mint.
"""

from __future__ import annotations

import json
import sys
import urllib.request

from hunter_exchanges.pumpfun.decode import decode_bonding_curve_account
from hunter_exchanges.pumpfun.tx import bonding_curve_address

RPC_URL = "https://api.mainnet-beta.solana.com"
LAMPORTS = 1_000_000_000


def _rpc(method: str, params: list[object]) -> dict[str, object]:
    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode()
    req = urllib.request.Request(RPC_URL, data=body, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def read_curve(mint: str) -> dict[str, object]:
    curve = bonding_curve_address(mint)
    out = _rpc("getAccountInfo", [curve, {"encoding": "base64", "commitment": "finalized"}])
    result = out.get("result") or {}
    slot = (result.get("context") or {}).get("slot")
    value = result.get("value")
    if value is None:
        return {"mint": mint, "curve": curve, "slot": slot, "reason": "curve_not_found"}
    account = decode_bonding_curve_account(value["data"][0], owner=value["owner"])
    vsol = account.virtual_sol_reserves / LAMPORTS
    vtok = account.virtual_token_reserves
    supply = account.token_total_supply
    mcap = (vsol / vtok * supply) if vtok else None
    return {
        "mint": mint,
        "curve": curve,
        "slot": slot,
        "lamports": value["lamports"] / LAMPORTS,
        "real_sol_reserves": account.real_sol_reserves / LAMPORTS,
        "virtual_sol_reserves": vsol,
        "real_token_reserves": account.real_token_reserves,
        "complete": account.complete,
        "is_mayhem_mode": account.is_mayhem_mode,
        "mcap_sol": mcap,
    }


def main(mints: list[str]) -> int:
    for mint in mints:
        try:
            row = read_curve(mint)
        except Exception as exc:
            row = {"mint": mint, "reason": f"{type(exc).__name__}: {exc}"}
        print(json.dumps(row, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
