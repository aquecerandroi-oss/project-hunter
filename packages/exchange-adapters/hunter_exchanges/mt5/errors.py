"""Errors of the MT5 adapter.

The split that matters to the caller (``docs/RISK_ENGINE_B3.md`` §3.6, §4.3):

* :class:`Mt5NotSent` — raised **before** ``order_send`` is called. Nothing left the process;
  the caller may record "not sent" (``b3_sltp_request_status = not_sent``) and move on.
* a returned :class:`~hunter_exchanges.mt5.models.SendOutcome` — ``order_send`` was (or may
  have been) called. A ``None`` result, an exception or a timeout is an *uncertain* outcome,
  never an exception: raising there would let a caller treat "maybe sent" as "not sent".
"""

from __future__ import annotations


class Mt5Error(Exception):
    """Base of every MT5 adapter error."""


class Mt5NotAvailable(Mt5Error):
    """The vendor package or the platform is missing (Linux CI, or no terminal installed)."""


class Mt5ReadError(Mt5Error):
    """A read failed or returned something unusable. The value is *unavailable*, never zero.

    ``last_error`` is the terminal's ``(code, message)`` when it gave one; ``reason`` is a short
    machine-readable tag (``none_result``, ``malformed:<field>``, ``ipc_timeout``, ...).
    """

    def __init__(
        self, what: str, *, reason: str, last_error: tuple[int, str] | None = None
    ) -> None:
        super().__init__(
            f"{what}: {reason}" + (f" (last_error={last_error})" if last_error else "")
        )
        self.what = what
        self.reason = reason
        self.last_error = last_error


class Mt5IpcTimeout(Mt5ReadError):
    """One IPC call exceeded ``ipc_call_timeout_s``.

    ``started`` says whether the call had begun inside the terminal. If it had, the lane is now
    latched ``ipc_hung`` and a mutation may have taken effect (uncertain). If it had not (it was
    still queued), it was abandoned and will never run: nothing was sent.
    """

    def __init__(self, what: str, *, started: bool) -> None:
        super().__init__(what, reason="ipc_timeout")
        self.started = started


class Mt5NotSent(Mt5Error):
    """A mutation was refused before ``order_send``. ``reason`` is the named refusal."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason + (f": {detail}" if detail else ""))
        self.reason = reason
        self.detail = detail
