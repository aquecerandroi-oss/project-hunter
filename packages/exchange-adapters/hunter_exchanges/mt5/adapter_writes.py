"""The write half of :class:`~hunter_exchanges.mt5.adapter.Mt5Adapter`: three mutations.

``send_entry`` (market or limit, ``sl``/``tp`` attached), ``send_sltp`` and ``cancel_order`` are
the only calls that reach ``order_send``. Each one:

1. refuses **before** sending, raising :class:`~.errors.Mt5NotSent` with a named reason, when
   the IPC lane is latched hung (G5), a read it depends on fails, a number is off its grid, the
   spec pin diverged (entries), or an invariant would be broken (``would_delete_stop``,
   ``would_loosen_stop``, SLTP guards);
2. then sends once, and **always returns a** :class:`~.models.SendOutcome`: a ``None`` result, a
   raised exception or a deadline overrun is ``UNCERTAIN`` (the caller never resends).

It performs no retry of any kind. Rate limiting does not apply to the local IPC lane; the
broker's own ``TOO_MANY_REQUESTS`` is a terminal rejection like any other.
"""

from __future__ import annotations

from collections.abc import Awaitable
from datetime import datetime
from functools import partial
from typing import Any, TypeVar

import structlog

from .adapter_reads import ReadsMixin
from .builders import build_cancel_request, build_entry_request, build_sltp_request
from .constants import ORDER_CHECK_OK, Retcode
from .convert import number_on_grid_or_none
from .errors import Mt5IpcTimeout, Mt5NotSent, Mt5ReadError
from .guards import entry_stop_refusal, sltp_refusal
from .models import (
    EntryRequest,
    Mt5CheckResult,
    Mt5Position,
    Mt5SymbolSpec,
    SendOutcome,
    SltpRequest,
)
from .parse import Grid, parse_check
from .retcodes import Action, classify
from .spec import SpecSnapshot, SpecStatus, SpecWatcher

log = structlog.get_logger(__name__)
T = TypeVar("T")


class WritesMixin(ReadsMixin):
    # ------------------------------------------------------------------ spec watcher

    def pin_spec(self, pin: SpecSnapshot) -> None:
        """Fix the specification at arming (contract §3.9); re-pinning is the Everton's re-arm."""
        if self._watcher is None:
            self._watcher = SpecWatcher(pin)
        else:
            self._watcher.rearm(pin)

    @property
    def spec_status(self) -> SpecStatus | None:
        return None if self._watcher is None else self._watcher.status

    async def refresh_spec(self, symbol: str) -> SpecStatus:
        """One periodic re-read (every 60 s, and on start). Counts a failed read toward UNREADABLE."""
        if self._watcher is None:
            raise Mt5ReadError("spec", reason="not_pinned")
        try:
            snapshot = await self.read_spec_snapshot(symbol)
        except Mt5ReadError:
            return self._watcher.observe_failure()
        return self._watcher.observe(snapshot)

    # ------------------------------------------------------------------ helpers

    def _refuse_if_hung(self) -> None:
        if self._ipc.hung:
            raise Mt5NotSent("guard_ipc_hung", self._ipc.hung_call or "")
        if self._ipc.unresolved:  # a send whose awaiter gave up may have executed
            raise Mt5NotSent("guard_unresolved_send", "collect drain_late_results() first")

    @staticmethod
    async def _or_not_sent(awaitable: Awaitable[T], reason: str) -> T:
        try:
            return await awaitable
        except Mt5ReadError as exc:
            raise Mt5NotSent(reason, exc.reason) from None

    async def _spec_checked_for_entry(self, symbol: str) -> Mt5SymbolSpec:
        if self._watcher is None:
            raise Mt5NotSent("spec_not_pinned")
        try:
            spec, snapshot = await self.read_spec_bundle(symbol)
        except Mt5ReadError as exc:
            self._watcher.observe_failure()
            raise Mt5NotSent("spec_unreadable", exc.reason) from None
        status = self._watcher.observe(snapshot)
        if status is not SpecStatus.OK:
            fields = ",".join(d.field for d in self._watcher.diffs)
            raise Mt5NotSent(
                "spec_changed" if status is SpecStatus.CHANGED else "spec_unreadable", fields
            )
        return spec

    async def _send(
        self,
        action: Action,
        body: dict[str, Any],
        grid: Grid | None = None,
        **correlation: Any,
    ) -> SendOutcome:
        self._refuse_if_hung()
        sent_at = self._clock()
        error: str | None = None
        result: Any = None
        last_error: tuple[int, str] | None = None

        def late(raw_result: Any, raw_error: tuple[int, str] | None) -> SendOutcome:
            return self._outcome(
                action, raw_result, "late_result", raw_error, sent_at, grid, **correlation
            )

        try:
            result, last_error = await self._ipc.call(
                "order_send", partial(self._raw.order_send, body), mutation=True, on_late=late
            )
        except Mt5IpcTimeout as exc:
            if not exc.started:  # abandoned in the queue: it will never run
                raise Mt5NotSent("guard_ipc_hung", "queued behind a stuck call") from None
            error = "ipc_timeout"
        except Exception as exc:  # any failure after sending is an uncertain outcome
            error = f"exception:{type(exc).__name__}"
        if error is None and result is None:
            error = "none_result"
        outcome = self._outcome(action, result, error, last_error, sent_at, grid, **correlation)
        log.info(
            "mt5_order_send",
            action=action.value,
            verdict=outcome.verdict.value,
            retcode=outcome.retcode_name,
            error=outcome.error,
        )
        return outcome

    def _outcome(
        self,
        action: Action,
        result: Any,
        error: str | None,
        last_error: tuple[int, str] | None,
        sent_at: datetime,
        grid: Grid | None,
        **correlation: Any,
    ) -> SendOutcome:
        retcode = getattr(result, "retcode", None) if result is not None else None
        if result is not None and (not isinstance(retcode, int) or isinstance(retcode, bool)):
            retcode, error = None, error or "malformed_result"
        verdict = classify(action, retcode)
        comment = getattr(result, "comment", "")
        order, deal = getattr(result, "order", 0), getattr(result, "deal", 0)
        return SendOutcome(
            action=action,
            verdict=verdict.verdict,
            retcode=verdict.retcode,
            retcode_name=verdict.name,
            broker_comment=comment if isinstance(comment, str) else "",
            order_ticket=order if isinstance(order, int) and order > 0 else None,
            deal_ticket=deal if isinstance(deal, int) and deal > 0 else None,
            volume=number_on_grid_or_none(
                getattr(result, "volume", None), grid and grid.volume_step
            ),
            price=number_on_grid_or_none(getattr(result, "price", None), grid and grid.tick),
            error=error,
            last_error=last_error,
            sent_at=sent_at,
            received_at=self._clock(),
            **correlation,
        )

    # ------------------------------------------------------------------ mutations

    async def send_entry(self, request: EntryRequest) -> SendOutcome:
        self._refuse_if_hung()
        spec = await self._spec_checked_for_entry(request.symbol)
        body = build_entry_request(request, spec)
        positions = await self._or_not_sent(self.positions(request.symbol), "positions_unreadable")
        refusal = entry_stop_refusal(request, positions)
        if refusal is not None:
            log.warning("mt5_not_sent", reason=refusal, symbol=request.symbol)
            raise Mt5NotSent(refusal, request.symbol)
        return await self._send(Action.ENTRY, body, Grid(spec.trade_tick_size, spec.volume_step))

    async def send_sltp(self, request: SltpRequest) -> SendOutcome:
        self._refuse_if_hung()
        spec = await self._or_not_sent(self.symbol_spec(request.symbol), "spec_unreadable")
        positions = await self._or_not_sent(self.positions(request.symbol), "positions_unreadable")
        current: Mt5Position | None = next(
            (p for p in positions if p.symbol == request.symbol), None
        )
        try:
            tick = await self.tick(request.symbol)
        except Mt5ReadError as exc:
            raise Mt5NotSent("quote_unreadable", exc.reason) from None
        refusal = sltp_refusal(request, current, spec, (tick.bid, tick.ask))
        if refusal is not None:
            log.warning("mt5_not_sent", reason=refusal, symbol=request.symbol)
            raise Mt5NotSent(refusal, request.symbol)
        return await self._send(
            Action.SLTP,
            build_sltp_request(request, spec),
            sltp_request_id=request.sltp_request_id,
            request_position_ticket=request.position_ticket,
        )

    async def cancel_order(self, ticket: int, *, magic: int) -> SendOutcome:
        """Remove one pending order of ours. Another magic (the Everton's own order) is refused."""
        self._refuse_if_hung()
        orders = await self._or_not_sent(self.orders(), "orders_unreadable")
        order = next((o for o in orders if o.ticket == ticket), None)
        if order is None:
            raise Mt5NotSent("order_not_found", str(ticket))
        if order.magic != magic:
            raise Mt5NotSent("order_magic_mismatch", str(ticket))
        return await self._send(Action.CANCEL, build_cancel_request(ticket))

    async def check_entry(self, request: EntryRequest) -> Mt5CheckResult:
        """`order_check`: margin and acceptance for exactly the request `send_entry` would send."""
        spec = await self.symbol_spec(request.symbol)
        body = build_entry_request(request, spec)
        raw = await self._read("order_check", partial(self._raw.order_check, body))
        retcode, comment, margin, margin_free = parse_check(raw)
        ok = retcode in (ORDER_CHECK_OK, int(Retcode.DONE))
        return Mt5CheckResult(
            ok=ok,
            retcode=retcode,
            retcode_name="OK"
            if retcode == ORDER_CHECK_OK
            else classify(Action.ENTRY, retcode).name,
            comment=comment,
            margin=margin,
            margin_free=margin_free,
        )
