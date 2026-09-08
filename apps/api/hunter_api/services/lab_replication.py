"""Assembling ``ScoreboardRowOut.replication`` — briefs T3.18b (item 2) e T3.18c.

Pure wiring: every statistic in the payload comes straight out of
``hunter_indicators.replication.protocol.replication_report`` (the same
pure function ``hunter_strategy_worker.replication_stats.build_report``
calls) — this module never recomputes an expectancy, a bootstrap interval or
a verdict. What it adds is the API's own bookkeeping, stitched onto the
report's JSON *after the fact* rather than smuggled into the statistics:

- ``evidence`` por braço (D15) e a **janela** dos replays dele;
- o rótulo do bloco 2 quando qualquer braço amadureceu por replay
  (``REPLICATION.md`` §3.5, item 4: "o relatório tem de dizer ``siblings:
  replay sobre <janela>`` e nunca apresentar o bloco como se fosse
  prospectivo");
- ``seed_source`` (T3.18c, item 6): se a semente do bootstrap é a **registrada**
  na rodada ou uma derivada do id da versão porque nenhuma rodada existe.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from hunter_api.repositories.lab_replication import (
    SEED_SOURCE_DERIVED,
    SEED_SOURCE_REGISTERED,
    SiblingPopulation,
)
from hunter_api.schemas.lab_replication import ReplicationBlockOut
from hunter_indicators.replication import STATUS_NONE, SiblingArm, replication_report

if TYPE_CHECKING:
    from datetime import datetime

    from hunter_indicators.replication import Outcome

__all__ = ["REPLAY_SIBLINGS_LABEL", "build_replication_block", "resolve_seed", "siblings_label"]

REPLAY_SIBLINGS_LABEL = "siblings: replay sobre"
"""Prefixo do rótulo exigido por ``REPLICATION.md`` §3.5 (item 4)."""


def resolve_seed(version_id: uuid.UUID, registered: int | None) -> tuple[int, str]:
    """A semente do bootstrap e **de onde ela veio**.

    ``registrada`` quando o evento ``strategy_version_replicated`` da rodada a
    guardou; senão uma semente derivada do próprio id da versão —
    determinística, escolhida antes de olhar a amostra, e **declarada como
    derivada**. O defeito que isto fecha não é estatístico (o fallback já era
    determinístico): era de contrato, porque o payload apresentava os dois
    casos com a mesma cara (quant, revisão T3.18b, achado 4).
    """
    if registered is not None:
        return registered, SEED_SOURCE_REGISTERED
    return int.from_bytes(version_id.bytes[:4], "big"), SEED_SOURCE_DERIVED


def siblings_label(siblings: list[SiblingPopulation]) -> str | None:
    """``siblings: replay sobre <janela>`` — ou ``None`` quando ninguém replayou.

    A janela é a união das janelas dos braços que de fato contaram replay. Um
    braço replayado cuja corrida não deixou recibo dentro do corte entra como
    "janela não declarada": o rótulo continua obrigatório, o que falta é a
    janela, e omitir o rótulo seria apresentar o bloco como prospectivo.
    """
    replayed = [s for s in siblings if s.evidence in ("replay", "mixed")]
    if not replayed:
        return None
    starts = [s.replay_window.window_from for s in replayed if s.replay_window.window_from]
    ends = [s.replay_window.window_to for s in replayed if s.replay_window.window_to]
    if not starts or not ends:
        return f"{REPLAY_SIBLINGS_LABEL} janela não declarada"
    return f"{REPLAY_SIBLINGS_LABEL} {min(starts):%Y-%m-%d} → {max(ends):%Y-%m-%d}"


def build_replication_block(
    *,
    version_id: uuid.UUID,
    promising_at: datetime | None,
    parent_outcomes: list[Outcome],
    siblings: list[SiblingPopulation],
    registered_seed: int | None = None,
) -> ReplicationBlockOut | None:
    """``None`` when the version was never ``validada`` (``promising_at`` never
    gravado): the protocol has not started and a scoreboard row for a version
    that never entered it should not carry a block of nulls.

    O caminho barato é o de cima (T3.18c, item 8): sem ``promising_at`` este
    módulo **não** roda ``replication_report`` — mil reamostras, um bootstrap
    por dias e um teste de sinal — para depois jogar o resultado fora. Hoje
    nenhuma versão tem o carimbo, então esse era o caso de **todas** as linhas
    do placar.
    """
    if promising_at is None:
        return None
    arms = [
        SiblingArm(k=sibling.meta.k, version=sibling.meta.version, outcomes=sibling.outcomes)
        for sibling in siblings
    ]
    seed, seed_source = resolve_seed(version_id, registered_seed)
    report = replication_report(
        parent_outcomes=parent_outcomes,
        promising_at=promising_at,
        siblings=arms,
        seed=seed,
    )
    if report.status == STATUS_NONE:  # pragma: no cover - promising_at is not None here
        return None

    payload = report.to_jsonable()
    _tag_arms(payload["siblings"]["arms"], siblings)
    payload["siblings"]["label"] = siblings_label(siblings)
    payload["bootstrap"]["seed_source"] = seed_source
    payload["bootstrap"]["day_cluster"]["seed_source"] = seed_source
    return ReplicationBlockOut.model_validate(payload)


def _tag_arms(arms: list[dict[str, Any]], siblings: list[SiblingPopulation]) -> None:
    by_k = {sibling.meta.k: sibling for sibling in siblings}
    for arm in arms:
        sibling = by_k.get(arm["k"])
        if sibling is None:  # pragma: no cover - arms come from these siblings
            continue
        arm["evidence"] = sibling.evidence
        arm["window_from"] = sibling.replay_window.window_from
        arm["window_to"] = sibling.replay_window.window_to
        arm["duplicates_dropped"] = sibling.duplicates_dropped
