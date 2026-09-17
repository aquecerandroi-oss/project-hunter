"""SPL Token ``CloseAccount`` of a wallet's own ATA (T4.46, R43) — split out of
``tx.py`` only to fit the repo's file-size budget; the instruction a full sell
appends to earn the mint's ATA rent back, Token-2022 or classic alike (the
legacy instruction indices are byte-identical across both programs). Mirrors
``hunter_exchanges.pumpswap.tx.build_close_wsol_instruction``.
"""

from __future__ import annotations

from hunter_exchanges.pumpfun.solana_codec import (
    AccountMeta,
    Instruction,
    associated_token_address,
)

__all__ = ["CLOSE_ACCOUNT_DISCRIMINATOR", "build_close_ata_instruction"]

CLOSE_ACCOUNT_DISCRIMINATOR = bytes([9])


def build_close_ata_instruction(*, owner: str, mint: str, token_program: str) -> Instruction:
    """``owner`` is both the destination of the refund and the signing authority."""
    ata = associated_token_address(owner, mint, token_program=token_program)
    return Instruction(
        token_program,
        (
            AccountMeta(ata, False, True),
            AccountMeta(owner, False, True),
            AccountMeta(owner, True, False),
        ),
        CLOSE_ACCOUNT_DISCRIMINATOR,
    )
