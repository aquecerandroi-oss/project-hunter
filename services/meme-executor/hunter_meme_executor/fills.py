"""The fill, as a landed pump.fun transaction reports it (§9.6) — split out of
``build.py`` only to fit the repo's file-size budget.

The ``TradeEvent``, ``meta.fee`` and — the ledger's truth — the payer's real
balance delta (``pre − post`` of index 0), which carries everything the wallet
lost or gained: curve, every fee the program has, rent, tips. T4.46 (R43)
names the rent apart from that delta: a buy's ATA + one-time
``user_volume_accumulator`` PDA, a full sell's ``CloseAccount`` refund.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from hunter_exchanges.pumpfun.decode import PUMP_PROGRAM_ID
from hunter_exchanges.pumpfun.trade_event import TradeEvent, trade_events_from_transaction
from hunter_exchanges.pumpfun.wallet_fills import ata_close_refund_lamports, rent_labels

__all__ = ["FillRecord", "decode_fills"]


@dataclass(frozen=True, slots=True)
class FillRecord:
    """The fill as the chain reported it (§9.6): the ``TradeEvent``, ``meta.fee`` and — the
    ledger's truth — the payer's real balance delta (``pre − post`` of index 0), which carries
    everything the wallet lost or gained: curve, every fee the program has, rent, tips."""

    event: TradeEvent
    signature: str
    slot: int
    block_time: datetime | None
    network_fee_lamports: int
    payer_delta_lamports: int | None = None
    """``post − pre`` of the payer (negative on a buy); ``None`` without balances."""
    ata_rent_lamports: int | None = None
    """T4.46 (R43) — a buy's Token-2022/SPL ATA rent, named from the wallet's own
    ``system::createAccount``: part of ``buy_total_lamports`` (cash out), split
    out here so the ledger can tell trading cost from a refundable rent."""
    account_rent_lamports: int | None = None
    """The ``user_volume_accumulator`` PDA's one-time rent (R43: 1 346 200
    lamports), the wallet's only per-wallet (never per-coin) creation cost."""
    ata_rent_refund_lamports: int | None = None
    """A sell's ``CloseAccount`` refund (T4.46) — cash in, folded into
    ``sell_net_lamports``. ``None`` when the sell did not close the ATA."""

    @property
    def event_buy_total_lamports(self) -> int:
        """Curve + the event's fees + network fee — lamport-exact on the recorded fills."""
        return self.event.buy_total_cost + self.network_fee_lamports

    @property
    def event_sell_net_lamports(self) -> int:
        return self.event.sell_net_proceeds - self.network_fee_lamports

    @property
    def buy_total_lamports(self) -> int:
        """Everything the buy took from the wallet — the chain's delta when known.
        Rent-inclusive on purpose (T4.46): it *is* cash out, whether or not it
        later comes back through a ``CloseAccount``."""
        if self.payer_delta_lamports is not None:
            return -self.payer_delta_lamports
        return self.event_buy_total_lamports

    @property
    def sell_net_lamports(self) -> int:
        """What reached the wallet — the ATA-rent refund of a closed account
        folded in (T4.46: cash in, same as the trading leg)."""
        if self.payer_delta_lamports is not None:
            return self.payer_delta_lamports
        return self.event_sell_net_lamports + (self.ata_rent_refund_lamports or 0)

    @property
    def unexplained_lamports(self) -> int | None:
        """Beyond the event's arithmetic, the network fee and the named rent
        (ATA + the one-time accumulator PDA on a buy; the ATA-rent refund on a
        sell): ``0`` on a transaction this executor builds and reads back with
        the rent named; ``None`` without balances (T4.8b)."""
        if self.payer_delta_lamports is None:
            return None
        if self.event.is_buy:
            rent = (self.ata_rent_lamports or 0) + (self.account_rent_lamports or 0)
            return -self.payer_delta_lamports - self.event_buy_total_lamports - rent
        refund = self.ata_rent_refund_lamports or 0
        return self.event_sell_net_lamports - self.payer_delta_lamports + refund

    def as_json(self) -> dict[str, Any]:
        e = self.event
        return {
            "signature": self.signature,
            "slot": self.slot,
            "block_time": None if self.block_time is None else self.block_time.isoformat(),
            "mint": e.mint,
            "is_buy": e.is_buy,
            "sol_amount": e.sol_amount,
            "token_amount": e.token_amount,
            "fee": e.fee,
            "fee_basis_points": e.fee_basis_points,
            "creator_fee": e.creator_fee,
            "creator_fee_basis_points": e.creator_fee_basis_points,
            "cashback": e.cashback,
            "holder_rewards": e.holder_rewards,
            "holder_rewards_basis_points": e.holder_rewards_basis_points,
            "event_layout": e.layout,
            "network_fee_lamports": self.network_fee_lamports,
            "payer_delta_lamports": self.payer_delta_lamports,
            "unexplained_lamports": self.unexplained_lamports,
            "buy_total_lamports": self.buy_total_lamports if e.is_buy else None,
            "event_buy_total_lamports": self.event_buy_total_lamports if e.is_buy else None,
            "ata_rent_lamports": self.ata_rent_lamports if e.is_buy else None,
            "account_rent_lamports": self.account_rent_lamports if e.is_buy else None,
            "sell_net_lamports": self.sell_net_lamports if not e.is_buy else None,
            "event_sell_net_lamports": self.event_sell_net_lamports if not e.is_buy else None,
            "ata_rent_refund_lamports": self.ata_rent_refund_lamports if not e.is_buy else None,
            "virtual_sol_reserves_after": e.virtual_sol_reserves,
            "virtual_token_reserves_after": e.virtual_token_reserves,
            "real_token_reserves_after": e.real_token_reserves,
            "timestamp": e.timestamp,
        }


def _payer_delta(meta: dict[str, Any]) -> int | None:
    pre = cast(list[Any], meta.get("preBalances") or [])
    post = cast(list[Any], meta.get("postBalances") or [])
    if not pre or not post:
        return None
    try:
        return int(post[0]) - int(pre[0])
    except (TypeError, ValueError):
        return None


def decode_fills(transaction: dict[str, Any]) -> list[FillRecord]:
    """``decode_fill`` for the submitter: the ``TradeEvent``s of a ``getTransaction`` result."""
    events = trade_events_from_transaction(transaction, program_id=PUMP_PROGRAM_ID)
    if not events:
        return []
    meta = cast(dict[str, Any], transaction.get("meta") or {})
    tx = cast(dict[str, Any], transaction.get("transaction") or {})
    signatures = cast(list[Any], tx.get("signatures") or [""])
    block_time = transaction.get("blockTime")
    # One transaction, one payer delta: attributed to the first event (no bundles built here).
    delta = _payer_delta(meta)
    fills: list[FillRecord] = []
    for index, event in enumerate(events):
        ata_rent = account_rent = refund = None
        if index == 0:
            # R43: named from the wallet's own inner instructions, never guessed —
            # ``{}`` (both ``None``) on a transaction this decoder cannot attribute rent in.
            if event.is_buy:
                ata_rent, account_rent = rent_labels(transaction, event.user)
            else:
                refund = ata_close_refund_lamports(transaction, event.user)
        fills.append(
            FillRecord(
                event=event,
                signature=str(signatures[0]),
                slot=int(transaction.get("slot") or 0),
                block_time=(
                    None if block_time is None else datetime.fromtimestamp(int(block_time), UTC)
                ),
                network_fee_lamports=int(meta.get("fee") or 0),
                payer_delta_lamports=delta if index == 0 else None,
                ata_rent_lamports=ata_rent,
                account_rent_lamports=account_rent,
                ata_rent_refund_lamports=refund,
            )
        )
    return fills
