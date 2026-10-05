"""What can still refuse an admitted entry **at the signature boundary** (T4.8f).

An approval is not a safe-conduct (§7, §9.5): the admission is followed by awaits (RPC, database)
and the world moves meanwhile. The effective kill switch was always re-read right before signing;
the program identity (an upgrade, or an identity unreadable for too long) is re-read the same way
now — an entry that passed the admission just before the tick found the block must not be signed.
Both entry paths (``entries.py``, ``launch_entries.py``) take this one decision.
"""

from __future__ import annotations

from typing import Any

from hunter_meme_executor.context import ExecutorContext

__all__ = ["pre_sign_reason", "signing_block"]


def signing_block(ctx: ExecutorContext) -> tuple[str, dict[str, Any]] | None:
    """``(refusal reason, log detail)`` while the admitted row must be refused, else ``None``.
    The caller has just awaited ``ctx.kill.refresh()``."""
    if ctx.kill.blocks_entries:
        return "kill_switch_blocked_before_signing", {"kill_switch": ctx.kill.effective.value}
    if (block := ctx.state.program_block) is not None:
        return f"{block[0]}_before_signing", {"detail": block[1]}
    return None


def pre_sign_reason(ctx: ExecutorContext) -> str | None:
    """The gate an **entry** hands its submitter (``MemeSubmitter(pre_sign_gate=...)``), called
    from the submit thread right before ``signer.sign`` — after the simulation, which can take
    seconds: the same decision as :func:`signing_block`, read from the state as it is *now*.
    Exits never pass one."""
    block = signing_block(ctx)
    return None if block is None else block[0]
