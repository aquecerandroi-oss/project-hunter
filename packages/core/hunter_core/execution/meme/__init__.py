"""``hunter_core.execution.meme`` — the inert signing path of ``docs/RISK_ENGINE_MEME.md`` §9.

Built complete and kept inert (T4.8): the key is read once by :mod:`signer`, the
§12 gates are enforced by :mod:`gates` before the key is touched, and
:mod:`submit` verifies, simulates, signs, sends and confirms with the doctrine's
three states. Nothing here imports the pump.fun adapter: the verifier, the RPC
client and the fill decoder are injected by the process that composes them.
"""

from hunter_core.execution.meme.gates import (
    ENV_GATES_FILE,
    ENV_LIVE_FLAG,
    GATES_SCHEMA,
    MemeExecutionMode,
    MemeGates,
    MemeLiveTradingRefused,
    load_execution_mode,
    load_gates,
)
from hunter_core.execution.meme.journal import (
    InMemoryOrderJournal,
    OrderJournal,
    OrderRecord,
    SigningLocked,
    SubmitState,
    client_order_id_for_proposal,
)
from hunter_core.execution.meme.signer import (
    ENV_SECRET_KEY,
    MemeSigner,
    SecretKeyMalformed,
    SecretKeyMissing,
    SignerError,
    boot_meme_execution,
)
from hunter_core.execution.meme.submit import (
    ApprovedSubmission,
    BundleSender,
    MemeLiveTradingDisabled,
    MemeSubmitter,
    SubmitPolicy,
    SubmitResult,
    TxRpc,
)

__all__ = [
    "ENV_GATES_FILE",
    "ENV_LIVE_FLAG",
    "ENV_SECRET_KEY",
    "GATES_SCHEMA",
    "ApprovedSubmission",
    "BundleSender",
    "InMemoryOrderJournal",
    "MemeExecutionMode",
    "MemeGates",
    "MemeLiveTradingDisabled",
    "MemeLiveTradingRefused",
    "MemeSigner",
    "MemeSubmitter",
    "OrderJournal",
    "OrderRecord",
    "SecretKeyMalformed",
    "SecretKeyMissing",
    "SignerError",
    "SigningLocked",
    "SubmitPolicy",
    "SubmitResult",
    "SubmitState",
    "TxRpc",
    "boot_meme_execution",
    "client_order_id_for_proposal",
    "load_execution_mode",
    "load_gates",
]
