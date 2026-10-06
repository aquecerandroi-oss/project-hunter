"""pump.fun realtime latency probe (2026-10-06) — the trade half of the analysis (pure, no IO).

What is compared, and what is not (Astra's review of the instrument, 06/10/2026):

* **Programs.** The RPC reference subscribes to the ``pump`` program only, so only NATS trades with
  ``program == "pump"`` are compared with it; PumpSwap (``pump_amm``) legs have no equivalent reference and are
  only counted (``nats_programs``).
* **Exposure is a list of intervals**, one per subscription, closed by an ``UNSUB`` or by the next session
  break of that connection. A reconnect opens a second interval; it never rewrites the first.
* **The cohort is symmetric.** A transaction is in the cohort when *either* source delivered it inside the
  interior of an exposure interval (``INTERIOR_S`` away from both edges); its counterpart is then looked up
  over the whole capture, so an arrival that straddles an edge still finds its partner. An edge-only arrival
  is neither a pair nor a miss.
* **Replay-like** NATS frames — block second earlier than the subscription (in the server's clock, with a
  slack) — are history delivered on subscribe, not live deliveries. The label is an *inference from a
  one-second timestamp*; the slack is varied in ``replay_sensitivity``.
* The key is the **signature** (first news of the transaction); the balance feed is also matched on the
  wallet, because one transaction changes the balance of several wallets.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from pumpfun_rt_probe_stats import Event, describe, first_seen, pair_report, union_coverage

INTERIOR_S, REPLAY_SLACK_S, DELIVERY_SLACK_S, END_GUARD_S, FOLLOW_SETTLE_S = (
    3.0,
    2.0,
    5.0,
    30.0,
    2.0,
)
PROCESSED_PREFIX = "unifiedTradeEvent.processed."
BALANCE_PREFIX = "account_balance_change."
BREAKS = frozenset({"connect", "disconnect", "error", "refused", "send_failed", "crashed", "err"})
INF = float("inf")
Interval = tuple[float, float]
DELAY_NOTE = (
    "Block time is an estimate (the chain's getBlockTime is built from validator timestamps) published with "
    "one-second resolution; its total error was not measured (the check against getBlockTime was not obtained). "
    "The local clock's skew is corrected with the server-time offset (uncertainty about half the sample round "
    "trip). Compare sources with each other (the pair deltas), not with zero."
)


def _sel(events: list[Event], source: str, kind: str) -> list[Event]:
    return [e for e in events if e["s"] == source and e["k"] == kind]


def _closing(starts: list[float], closers: list[float]) -> list[Interval]:
    return [(a, min([c for c in closers if c > a], default=INF)) for a in starts]


def intervals(events: list[Event]) -> tuple[dict[str, list[Interval]], dict[str, list[Interval]]]:
    """Exposure intervals per coin (processed subject) and per followed wallet."""
    breaks_u = sorted(e["t"] for e in _sel(events, "nats_u", "sys") if e["id"] in BREAKS)
    breaks_c = sorted(e["t"] for e in _sel(events, "nats_c", "sys") if e["id"] in BREAKS)
    unsubs: dict[str, list[float]] = {}
    for e in _sel(events, "nats_u", "unsub"):
        unsubs.setdefault(e["id"], []).append(e["t"])
    mints: dict[str, list[Interval]] = {}
    for e in _sel(events, "nats_u", "sub"):
        if e["id"].startswith(PROCESSED_PREFIX):
            closers = sorted(breaks_u + unsubs.get(e["id"], []))
            mints.setdefault(e["id"][len(PROCESSED_PREFIX) :], []).extend(
                _closing([e["t"]], closers)
            )
    wallets: dict[str, list[Interval]] = {}
    for e in _sel(events, "nats_c", "sub"):
        if e["id"].startswith(BALANCE_PREFIX):
            wallet = e["id"][len(BALANCE_PREFIX) :].rsplit(".", 1)[0]
            wallets.setdefault(wallet, []).extend(_closing([e["t"]], breaks_c))
    return mints, wallets


def _containing(ivs: list[Interval], t: float, post: float = 0.0) -> Interval | None:
    return next(((a, b) for a, b in ivs if a <= t <= b + post), None)


def _interior(ivs: list[Interval], t: float) -> bool:
    return any(a + INTERIOR_S <= t <= b - INTERIOR_S for a, b in ivs)


def _live(e: Event, mints: dict[str, list[Interval]], offset: float, slack: float) -> bool | None:
    """True live, False replay-like, None outside any exposure interval."""
    iv = _containing(mints.get(e.get("mint") or "", []), e["t"], DELIVERY_SLACK_S)
    if iv is None:
        return None
    bt = e.get("bt")
    return not (isinstance(bt, (int, float)) and bt < iv[0] + offset - slack)


def _replay_share(
    events: list[Event], mints: dict[str, list[Interval]], offset: float, slack: float
) -> float | None:
    """Share of the NATS frames inside an exposure interval whose block second precedes the subscription."""
    kinds = [k for k in (_live(e, mints, offset, slack) for e in events) if k is not None]
    return (sum(1 for k in kinds if k is False) / len(kinds)) if kinds else None


def _core(
    events: list[Event],
    mints: dict[str, list[Interval]],
    offset: float,
    slack: float,
    t0: float,
    t1: float,
) -> dict[str, Any]:
    """Eligibility (who is in the cohort) is decided on arrivals inside the interior of an exposure interval;
    the counterpart is then searched over the whole capture, so a frame that lands after the unsubscribe still
    pairs. Only a frame positively classified replay-like is kept out of the counterpart search."""
    nats_ev = [e for e in _sel(events, "nats_u", "trade") if e.get("program") == "pump"]
    live_ev = [e for e in nats_ev if _live(e, mints, offset, slack) is not False]
    nats_all = first_seen(live_ev, "nats_u", "trade")
    rpc_ev = [e for e in _sel(events, "rpc", "logs") if e.get("mints")]
    rpc_all = first_seen(rpc_ev, "rpc", "logs")
    elig_n = {e["id"] for e in live_ev if _interior(mints.get(e["mint"], []), e["t"])}
    elig_r = {
        e["id"] for e in rpc_ev if any(_interior(mints.get(m, []), e["t"]) for m in e["mints"])
    }
    cohort = {
        s
        for s in elig_n | elig_r
        if t0 <= min(nats_all.get(s, INF), rpc_all.get(s, INF)) <= t1 - END_GUARD_S
    }
    return {
        "live_ev": live_ev,
        "cohort": cohort,
        "nats": {s: nats_all[s] for s in cohort if s in nats_all},
        "rpc": {s: rpc_all[s] for s in cohort if s in rpc_all},
    }


def _bt_by_sig(events: list[Event]) -> dict[str, float]:
    out: dict[str, float] = {}
    for e in events:
        if isinstance(e.get("bt"), (int, float)):
            out.setdefault(e["id"], e["bt"])
    return out


def _leg(sig: str, wallet: str) -> str:
    return f"{sig}|{wallet}"


def analyze_trades(events: list[Event], t0: float, t1: float, offset: float) -> dict[str, Any]:
    mints, wallets = intervals(events)
    base = _core(events, mints, offset, REPLAY_SLACK_S, t0, t1)
    nats, rpc, cohort = base["nats"], base["rpc"], base["cohort"]
    window = [e for e in _sel(events, "nats_u", "trade") if t0 <= e["t"] <= t1]
    lite = first_seen(
        [
            e
            for e in _sel(events, "nats_u", "lite")
            if _live(e, mints, offset, REPLAY_SLACK_S) is not False
        ],
        "nats_u",
        "lite",
    )
    lite_c = {s: t for s, t in lite.items() if s in cohort}
    # the balance feed: one leg per (signature, followed wallet) of that wallet's own trades
    bal_first: dict[tuple[str, str], float] = {}
    bal_all = _sel(events, "nats_c", "balance")
    for e in sorted(bal_all, key=lambda x: x["t"]):
        bal_first.setdefault((e["id"], str(e.get("wallet"))), e["t"])
    expected: set[tuple[str, str]] = set()
    for e in base["live_ev"]:
        iv = _containing(wallets.get(str(e.get("user")), []), e["t"])
        if e["id"] in cohort and iv is not None and e["t"] >= iv[0] + FOLLOW_SETTLE_S:
            expected.add((e["id"], str(e["user"])))
    got = sorted(leg for leg in expected if leg in bal_first)
    bal_k = {_leg(s, w): bal_first[(s, w)] for s, w in got}
    nats_k = {_leg(s, w): nats[s] for s, w in expected if s in nats}
    rpc_k = {_leg(s, w): rpc[s] for s, w in expected if s in rpc}
    bt = _bt_by_sig(base["live_ev"])
    sens: list[dict[str, Any]] = []
    for slack in (0.0, REPLAY_SLACK_S, 2 * REPLAY_SLACK_S):
        alt = _core(events, mints, offset, slack, t0, t1)
        rep = pair_report(alt["rpc"], alt["nats"])
        sens.append(
            {
                "slack_s": slack,
                "common": rep["common"],
                "p50": rep["delta_s"]["p50"],
                "replay_like_share": _replay_share(window, mints, offset, slack),
            }
        )
    delay_src = {"nats_u": nats, "rpc": rpc, "lite": lite_c}
    delays = {
        name: describe([t + offset - bt[s] for s, t in seen.items() if s in bt])
        for name, seen in delay_src.items()
    }
    delays["balance"] = describe(
        [t + offset - bt[s] for (s, w), t in bal_first.items() if (s, w) in expected and s in bt]
    )
    return {
        "nats_programs": dict(Counter(e.get("program") for e in window)),
        "watched_mints": len(mints),
        "followed_wallets": len(wallets),
        "replay_like_share": _replay_share(window, mints, offset, REPLAY_SLACK_S),
        "replay_sensitivity": sens,
        "cohort": len(cohort),
        "coverage": union_coverage({"nats_u": nats, "rpc": rpc}),
        "pairs": {
            "rpc_vs_nats": pair_report(rpc, nats),
            "lite_vs_nats": pair_report(lite_c, nats),
            "balance_vs_nats": pair_report(bal_k, nats_k),
            "balance_vs_rpc": pair_report(bal_k, rpc_k),
        },
        "balance_coverage": {
            "expected": len(expected),
            "delivered": len(got),
            "share": (len(got) / len(expected)) if expected else None,
        },
        "wire_lower_bound_s": describe(
            [
                e["t"] + offset - e["srv_ts"]
                for e in bal_all
                if t0 <= e["t"] <= t1 and isinstance(e.get("srv_ts"), (int, float))
            ]
        ),
        "delay_vs_block_time_s": delays,
        "delay_note": DELAY_NOTE,
    }
