"""Serialisation of the frozen leader list: the JSON document, its hashes, the
write-once file and the screen rendering. Pure apart from ``write_frozen``.

Only public addresses and numbers are kept (no username, bio, image, userId).
Money and ratios are decimal strings; there is no float in the file.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from copy_leaders_http import REQUEST_BUDGET, FollowerRead, ResponseRecord
from copy_leaders_rule import RULE_SHA256, RULE_TEXT, RULE_VERSION, Evaluation, Leader, Selection

SCHEMA = "copy-leaders/1"
SELECTOR_VERSION = "copy_select_leaders/1"
FILE_GLOB = "leaders-*.json"
_FOUR = Decimal("0.0001")


def iso(moment: datetime, *, millis: bool = False) -> str:
    moment = moment.astimezone(UTC)
    if millis:
        return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def ceil_ms(moment: datetime) -> datetime:
    """Round UP to the millisecond: a boundary stamped with it is never earlier than the
    instant it names (a consumer comparing event times against it cannot admit one before).
    ``known_at``, ``cohort_id`` and the file name all derive from this one instant."""
    moment = moment.astimezone(UTC)
    micros = moment.microsecond
    return moment + timedelta(microseconds=1000 - micros % 1000) if micros % 1000 else moment


def iso_ceil(moment: datetime) -> str:
    return iso(ceil_ms(moment), millis=True)


def _dec(value: Decimal | None, *, places: bool = False) -> str | None:
    if value is None:
        return None
    return format(value.quantize(_FOUR) if places else value, "f")


def wallet_dict(leader: Leader, follower: FollowerRead) -> dict[str, Any]:
    return {
        "address": leader.address,
        "stratum": leader.stratum,
        "rule_selected": leader.rule_selected,
        "rule_rank": leader.rule_rank,
        "everton_pick": leader.everton_pick,
        "boards": leader.boards,
        "reference_board": leader.reference_board,
        "realized_pnl_sol": _dec(leader.realized_pnl_sol),
        "unrealized_pnl_sol": _dec(leader.unrealized_pnl_sol),
        "buy_spend_sol": _dec(leader.buy_spend_sol),
        "positions_count": leader.positions_count,
        "positions_per_day": _dec(leader.positions_per_day, places=True),
        "realized_share": _dec(leader.realized_share, places=True),
        "is_verified": leader.is_verified,
        "last_refreshed_at_ms": leader.last_refreshed_at_ms,
        "score": _dec(leader.score, places=True),
        "positions_realized_boards": leader.positions_realized_boards,
        "followers": {
            "count": follower.count,
            "read_at": iso(follower.read_at, millis=True) if follower.read_at else None,
            "status": follower.status,
        },
    }


def _response_dict(record: ResponseRecord) -> dict[str, Any]:
    return {
        "endpoint": record.endpoint,
        "params": record.params,
        "requested_at": iso(record.requested_at, millis=True),
        "received_at": iso(record.received_at, millis=True),
        "status": record.status,
        "body_sha256": record.body_sha256,
        "ratelimit_limit": record.ratelimit_limit,
        "ratelimit_remaining": record.ratelimit_remaining,
        "window_start_sec": record.window_start_sec,
        "rows": record.rows,
        "malformed_rows": record.malformed_rows,
    }


def _evaluation_dict(item: Evaluation) -> dict[str, Any]:
    return {
        "address": item.address,
        "eligible": item.reject_reason is None,
        "reject_reason": item.reject_reason,
        "score": _dec(item.score, places=True),
        "periods": item.periods,
        "rows": [
            {
                "board": f"{r.period}:{r.sort}",
                "position": r.position,
                "realized_pnl_sol": _dec(r.realized_pnl_sol),
                "unrealized_pnl_sol": _dec(r.unrealized_pnl_sol),
                "buy_spend_sol": _dec(r.buy_spend_sol),
                "positions_count": r.positions_count,
                "is_verified": r.is_verified,
                "last_refreshed_at_ms": r.last_refreshed_at_ms,
            }
            for r in item.rows
        ],
    }


def _sha256(value: Any) -> str:
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def list_sha256(wallets: list[dict[str, Any]]) -> str:
    return _sha256(wallets)


def build_document(
    *,
    known_at: datetime,
    selection: Selection,
    followers: dict[str, FollowerRead],
    responses: list[ResponseRecord],
    requests_used: int,
    stop_reason: str | None,
    supersedes: dict[str, str] | None,
) -> dict[str, Any]:
    wallets = [wallet_dict(leader, followers[leader.address]) for leader in selection.leaders]
    document: dict[str, Any] = {
        "schema": SCHEMA,
        "cohort_id": f"copy-pilot-{ceil_ms(known_at):%Y%m%dT%H%M%SZ}",
        "selector_version": SELECTOR_VERSION,
        "known_at": iso_ceil(known_at),
        "t0_not_before": iso_ceil(known_at),
        "t0_note": "t0_not_before is a lower bound only: T0 is set after this file is written and the track is live",
        "supersedes": supersedes,
        "rule": {"version": RULE_VERSION, "sha256": RULE_SHA256, "text": RULE_TEXT},
        "responses": [_response_dict(r) for r in responses],
        "funnel": selection.funnel,
        "universe_wallets": selection.universe_wallets,
        "requests": {"used": requests_used, "budget": REQUEST_BUDGET, "stop_reason": stop_reason},
        "wallets": wallets,
        "list_sha256": list_sha256(wallets),
        "evaluated": [_evaluation_dict(e) for e in selection.evaluated],
    }
    document["content_sha256"] = _sha256(document)  # everything above, this key excluded
    return document


def existing_lists(out_dir: Path) -> list[Path]:
    return sorted(out_dir.glob(FILE_GLOB)) if out_dir.exists() else []


class PredecessorError(Exception):
    """The list a ``--new-cohort`` would replace cannot be read back as a valid frozen list."""


def supersedes_of(previous: Path, reason: str) -> dict[str, str]:
    """Link to the cohort being replaced (it stays on disk, untouched). The predecessor must
    read back as a frozen list whose ``list_sha256`` recomputes; otherwise a clear refusal."""
    try:
        body = json.loads(previous.read_text(encoding="utf-8"))
        recorded = str(body["list_sha256"])
        actual = list_sha256(body["wallets"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PredecessorError(
            f"{previous.name} is not a readable frozen list ({type(exc).__name__}: {exc}); "
            "inspect it by hand, nothing was written"
        ) from exc
    if recorded != actual:
        raise PredecessorError(
            f"{previous.name}: list_sha256 {recorded[:12]}.. does not match its wallets "
            f"({actual[:12]}..); the file was altered or torn, nothing was written"
        )
    return {"file": previous.name, "list_sha256": recorded, "reason": reason}


def write_frozen(out_dir: Path, document: dict[str, Any]) -> Path:
    """Write to a temp file in the same directory, fsync, then publish with ``os.link``, which
    fails if the name exists: all-or-nothing and write-once. The name comes from the document's
    ``cohort_id``, so file name, cohort and ``known_at`` share one instant."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = str(document["cohort_id"]).removeprefix("copy-pilot-")
    path = out_dir / f"leaders-{stamp}.json"
    temp = out_dir / f".partial-{os.getpid()}-{stamp}.tmp"
    try:
        with temp.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(document, handle, indent=2, ensure_ascii=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.link(temp, path)  # FileExistsError if a list with this name already exists
    finally:
        temp.unlink(missing_ok=True)
    return path


def short(address: str) -> str:
    return f"{address[:4]}..{address[-4:]}"


def _cell(value: object) -> str:
    return "-" if value is None else str(value)


def _flag(value: bool | None) -> str:
    return "?" if value is None else ("sim" if value else "nao")


def render_table(document: dict[str, Any]) -> str:
    head = (
        f"{'#':>2} {'wallet':<12} {'stratum':<22} {'realized SOL':>12} {'share':>6} {'pos':>5} "
        f"{'verif':>5} {'followers':>10}  boards"
    )
    lines = [head]
    for index, w in enumerate(document["wallets"], start=1):
        realized = w["realized_pnl_sol"]
        shown_realized = (
            "-" if realized is None else format(Decimal(realized).quantize(Decimal("0.01")), "f")
        )
        count = w["followers"]["count"]
        followers = str(count) if count is not None else f"? {w['followers']['status']}"
        boards = ",".join(
            b.replace(":combined", ":c").replace(":realized", ":r") for b in w["boards"]
        )
        lines.append(
            f"{index:>2} {short(w['address']):<12} {w['stratum']:<22} {shown_realized:>12} "
            f"{_cell(w['realized_share']):>6} {_cell(w['positions_count']):>5} "
            f"{_flag(w['is_verified']):>5} {followers:>10}  {boards or '(fora do quadro)'}"
        )
    return "\n".join(lines)
