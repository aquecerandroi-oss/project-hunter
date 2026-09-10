"""Two things ``services/admission.py`` needed that would have pushed it over
CLAUDE.md's 350-line budget — split out exactly like ``services/orders.py`` /
``services/orders_derive.py`` before it: this module is *why a write failed*
and *who asked for it*, never the write itself.

Both fixes are T3.68b (the risk-engine-guardian/security-reviewer review of
the uncommitted T3.68 diff, ``.claude/state/notes-T3.68.md``):

- **finding 3.** A Postgres constraint violation used to reach the caller as
  ``str(exc.orig)`` — the driver's own ``DETAIL`` line, which for a unique or
  check violation on this table can echo back the very values just sent. A
  422/409 problem+json is client-facing; :func:`integrity_reason` maps the
  handful of constraints this route's own ``INSERT`` can actually hit to a
  name, never the raw text.
- **finding 2.** The filing act itself wrote no ``audit_logs`` row of its
  own — only the engine's later decision did, as ``hunter_worker``, with the
  actor stamped ``"worker"`` (``hunter_execution_worker.admission_cycle.
  rebuild_request``, out of this task's scope). :func:`record_filing_audit`
  is the row that carries the real operator's identity, written in the
  caller's own transaction through the sink ``hunter_api.deps.org_session``
  already bound.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from hunter_core.audit import AuditEvent, get_audit_sink
from hunter_core.strategies.canonical import params_hash

if TYPE_CHECKING:
    from hunter_core.admission.sources import ProposalRequest

__all__ = ["integrity_reason", "record_filing_audit"]

_INTEGRITY_REASONS: dict[str, str] = {
    "fk_trade_proposals_organization_id_organizations": "organization_unknown",
    "fk_trade_proposals_portfolio_id_portfolios": "wallet_unknown",
    "fk_trade_proposals_market_id_markets": "market_unknown",
    "ck_trade_proposals_request_payload_is_a_geometry": "invalid_order_geometry",
}
"""``trade_proposals``' own constraint names (``hunter_core.db.models.execution``,
Postgres's ``NAMING_CONVENTION``), mapped to a reason a caller may read. Every
one of these is a race this route already checked for before writing (the
wallet, the market, the payload shape), never the ordinary path."""


def integrity_reason(exc_orig: object) -> str:
    """A named reason for a constraint violation, never the driver's own text."""
    rendered = str(exc_orig)
    for needle, reason in _INTEGRITY_REASONS.items():
        if needle in rendered:
            return reason
    return "order_rejected_by_database"


async def record_filing_audit(
    *, request: ProposalRequest, proposal_id: uuid.UUID, key: str, payload: dict[str, object]
) -> None:
    """The filing act's own ``audit_logs`` row.

    ``after`` carries the filed geometry plus a hash of the idempotency key,
    never the key itself — an append-only, tenant-readable table is not where
    a caller's own bearer-style header value belongs verbatim. Deliberately
    **not** written into ``trade_proposals.request_payload``: that column is
    compared byte-for-byte against a freshly rebuilt, actor-free payload by
    ``hunter_core.admission.dedupe._payload_pair`` when the engine decides
    this very row, and adding a key there would make every manual request
    fail its own replay check the moment the worker looked at it — the fix
    would break the feature it fixes. ``get_audit_sink()`` is bound by
    ``hunter_api.deps.org_session`` for every real request; the ``None``
    guard is for a caller that builds its own session by hand instead of
    going through the HTTP dependency (``test_manual_orders.py``'s
    ``TestReplayAcrossWallets``, mirroring
    ``services/execution-worker/tests/test_manual_request_decided.py``'s own
    direct call), which is a real, exercised path rather than defensive dead
    code.
    """
    sink = get_audit_sink()
    if sink is None:
        return
    await sink.record(
        AuditEvent(
            actor_type="user" if request.actor_type == "user" else "system",
            actor_id=request.actor_id,
            organization_id=request.organization_id,
            action="order_request.filed",
            entity_type="trade_proposal",
            entity_id=str(proposal_id),
            after={
                **{k: v for k, v in payload.items() if k != "client_key"},
                "idempotency_key_hash": params_hash({"idempotency_key": key}),
            },
            metadata={"source": "manual"},
        )
    )
