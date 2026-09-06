"""What the engine may read from an observation: how old it is, and which price is safe.

Three questions live here because the review of 2026-09-06 found the same shape
of bug behind three findings: a number that arrived with the proposal was trusted
without ever being confronted with the market it claims to describe.

- **which price** (finding 2). ``entry_ref`` is the strategy's reference, built
  when the signal fired. The engine compares it with the observed price and,
  for every arithmetic that produces a size, uses the **worse** of the two - for
  a long, the higher one. A stale, cheaper reference must never make a ceiling
  more generous than the market would actually be;
- **how old the volume is** (finding 3). ``max_volume_age_s`` existed in the
  profile and was never read, so a photograph of the minute volume taken 45
  minutes earlier still sized the participation ceiling;
- **how much the book absorbs**, which is an observation too, and is ``None``
  when the book was not observed at all.

Everything is a function of its arguments: the instant is ``portfolio.as_of``,
never a clock.
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from hunter_core.strategies.numeric import CONTEXT
from hunter_risk.exposure import PortfolioState
from hunter_risk.inputs import BookLevel, EntryProposal, MarketLiquidity
from hunter_risk.limits import RiskLimits

_ZERO = Decimal(0)
_ONE = Decimal(1)


def observed_price(liquidity: MarketLiquidity) -> Decimal:
    """The price the market is at right now: the mid when there is one, else the last trade.

    The mid comes first because it is what an order would actually meet; the
    last trade is the fallback that always exists (``last_price`` is required).
    Its freshness is the ``data_quality`` check's business, not this function's.
    """
    mid = liquidity.reference_mid
    return liquidity.last_price if mid is None else mid


def entry_deviation(proposal: EntryProposal, liquidity: MarketLiquidity) -> Decimal:
    """``|entry_ref - observed| / observed`` - how far the signal's price has moved."""
    observed = observed_price(liquidity)
    with localcontext(CONTEXT):
        return abs(proposal.entry_ref - observed) / observed


def entry_zone_ok(proposal: EntryProposal, liquidity: MarketLiquidity, limits: RiskLimits) -> bool:
    """Is the reference still inside the declared band around the observed price?

    v2 §3.1 check 7, "entrada fora da zona": the band is
    ``max_entry_deviation_pct`` (±0,5 % in ``paper_v1``). Outside it the proposal
    is a decision about a market that no longer exists - the reviewer's case was
    ``entry_ref = 100`` against a market at 110, approved, with a real loss at
    the stop of 1,18 % of the equity against a ceiling of 0,25 %.
    """
    return entry_deviation(proposal, liquidity) <= limits.max_entry_deviation_pct


def stop_below_market(proposal: EntryProposal, liquidity: MarketLiquidity) -> bool:
    """A long's stop has to be under the price the market is at, not only under ``entry_ref``.

    A stop of 97,5 with the market at 90 is a protection that has already been
    breached; opening there is buying a position whose stop fires on arrival.
    """
    return proposal.stop < observed_price(liquidity)


def worst_entry_price(proposal: EntryProposal, liquidity: MarketLiquidity) -> Decimal:
    """The price every ceiling is measured at: the **worse** of reference and market.

    For a long the worse price is the higher one. It is the only choice that
    cannot be gamed by a stale quote: with the market above the reference the
    engine buys fewer units and books a larger planned loss, and with the market
    below it the reference still rules, so the ceiling never widens because a
    price was old.
    """
    observed = observed_price(liquidity)
    return proposal.entry_ref if proposal.entry_ref > observed else observed


def volume_age_s(portfolio: PortfolioState, liquidity: MarketLiquidity) -> Decimal | None:
    """Age of the volume snapshot at ``as_of``; ``None`` when it carries no timestamp."""
    if liquidity.volume_ts is None:
        return None
    return portfolio.age_s(liquidity.volume_ts)


def stale_volume_reason(
    portfolio: PortfolioState, limits: RiskLimits, liquidity: MarketLiquidity
) -> str | None:
    """Why the volume may not be used, or ``None`` when it may (``R-OPS-2``).

    Covers both volumes: the model carries one ``volume_ts`` for the 24 h figure
    and for the minute reference, so one stale snapshot invalidates both. Fails
    closed - no timestamp is not "fresh enough", it is "unknown".
    """
    age = volume_age_s(portfolio, liquidity)
    if age is None:
        return "volume sem carimbo de tempo: idade desconhecida"
    limit = Decimal(limits.max_volume_age_s)
    if age < _ZERO:
        return f"volume carimbado {-age} s no futuro"
    if age > limit:
        return f"volume com {age} s, acima do maximo de {limit} s"
    return None


def book_capacity_qty(
    asks: tuple[BookLevel, ...], mid: Decimal, max_slippage_pct: Decimal
) -> Decimal | None:
    """Largest **quantity** whose VWAP against ``mid`` stays inside ``max_slippage_pct``.

    A quantity, not a spend, and that is the whole point: the spend of a walk
    that ends at a VWAP above the entry price buys *fewer* units than
    ``spend / price`` suggests. Returning 202 for a walk of 2 units at a price of
    100 would authorise 2.02 units, whose real crossing costs 101.0099 against a
    budget of 101 (Astra, diff review of T3.1).

    ``None`` when the book was not observed: in stress the feed is exactly what
    disappears, and "no book" must reject rather than skip the only per-size
    cost measurement there is (``R-OPS-1``).
    """
    if not asks:
        return None
    with localcontext(CONTEXT):
        budget_price = mid * (_ONE + max_slippage_pct)
        filled_qty = _ZERO
        spent = _ZERO
        for level in asks:
            if level.price <= budget_price:
                filled_qty += level.qty
                spent += level.qty * level.price
                continue
            # Partial: take q such that (spent + q*p) / (filled + q) == budget_price.
            room = budget_price * filled_qty - spent
            if room <= _ZERO:
                break
            take = min(level.qty, room / (level.price - budget_price))
            filled_qty += take
            break
        return filled_qty
