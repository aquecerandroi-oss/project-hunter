"""A replication sibling emits under its own cohort (T3.19c, ``0012_replication``).

The pendency REPLICATION.md §4.4 declared, closed from both ends: the schema now
accepts ``replication:<pai>:<k>`` (``ck_shadow_episodes_cohort_format``) and the
worker *stamps* it, reading the sibling's lineage from
``strategy_versions.replication_parent_id``/``replication_index`` instead of
inferring anything from the ``changelog``.

Why it matters, in one line: the execution bridge admits ``prospective`` and
refuses every other cohort with ``cohort_not_live`` (T3.15e). While the label was
unrepresentable, a sibling emitted as ``prospective`` — the one cohort the bridge
admits — so the cheapest of the three barriers was refusing a name nothing could
write. Isolation never depended on it (``purpose = research_only`` and the
absence of an ``agents`` row are the other two, both proved in
``test_replicate_strategy_version.py``); what changes is that it is now three
barriers instead of two.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select, text

from hunter_core.db.models.agents import AgentSignal
from hunter_core.db.models.agents_shadow import ShadowEpisode
from hunter_core.db.session import role_session
from hunter_core.domain.enums import ShadowCohort
from hunter_core.strategies.volume_anomaly_v1 import VOLUME_ANOMALY_V1
from hunter_strategy_worker.catalogue import ActiveVersion, load_active_versions
from hunter_strategy_worker.config import ShadowConfig
from hunter_strategy_worker.decide import evaluate_slot
from hunter_strategy_worker.repo import load_market

from .builders import (
    EXCHANGE,
    SYMBOL,
    activate_version,
    ensure_partitions,
    insert_candles,
    isolate_catalogue,
    only_version,
    seed_market,
    series,
)

CUT = datetime(2026, 9, 5, 12, 0, tzinfo=UTC)
CONFIG = ShadowConfig(eligibility_max_lag_s=300, context_minutes=1560)
ARM = 3


def _version(**overrides: Any) -> ActiveVersion:
    """An :class:`ActiveVersion` with no database behind it — :meth:`cohort` is
    pure, and the three rules below are worth proving without a container."""
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "strategy_key": "volume_anomaly",
        "version": "v1",
        "params": {},
        "params_hash": "hash",
        "strategy": VOLUME_ANOMALY_V1,
        "code_ref": None,
        "purpose": "research_only",
    }
    fields.update(overrides)
    return ActiveVersion(**fields)


class TestTheCohortOneVersionStamps:
    """Pure: which label a version puts on its decisions."""

    def test_an_ordinary_version_keeps_the_process_cohort(self) -> None:
        assert _version().cohort(ShadowCohort.PROSPECTIVE) == ShadowCohort.PROSPECTIVE

    def test_a_sibling_stamps_its_arm(self) -> None:
        parent = uuid.uuid4()
        version = _version(replication_parent_id=parent, replication_index=ARM)
        assert version.cohort(ShadowCohort.PROSPECTIVE) == f"replication:{parent}:{ARM}"
        assert ShadowCohort.is_valid(version.cohort(ShadowCohort.PROSPECTIVE))

    def test_a_replay_of_a_sibling_stays_a_replay(self) -> None:
        """Cohorts separate populations *of the same version*, and a replay is
        never that version's reserved forward evaluation (SHADOW-LAB.md §1).
        Collapsing the two would also let a replay take the slot
        ``uq_shadow_episodes_slot`` keeps for the forward run."""
        replay = ShadowCohort.replay(uuid.uuid4())
        version = _version(replication_parent_id=uuid.uuid4(), replication_index=ARM)
        assert version.cohort(replay) == replay

    def test_half_a_lineage_is_never_a_cohort(self) -> None:
        """The CHECK makes this unrepresentable in the database; the method still
        falls back instead of building ``replication:None:3``."""
        assert _version(replication_index=ARM).cohort(ShadowCohort.PROSPECTIVE) == (
            ShadowCohort.PROSPECTIVE
        )
        assert _version(replication_parent_id=uuid.uuid4()).cohort(ShadowCohort.PROSPECTIVE) == (
            ShadowCohort.PROSPECTIVE
        )


@pytest.fixture
async def sibling_db(db_session_factory: Any) -> dict[str, Any]:
    """A market, a triggering series and one active version that **is a sibling**.

    The lineage is written at ``INSERT``, never by a later ``UPDATE``: the
    freeze trigger covers ``replication_parent_id``/``replication_index`` on an
    activated row since ``0012`` (DATABASE.md §24), which is exactly how
    ``replicate_strategy_version.py`` writes it too. The parent is left
    ``deprecated`` so the roster has one runnable version and the assertions
    below are about *that* one.
    """
    key = f"replication_cohort_{uuid.uuid4().hex[:8]}"
    async with db_session_factory() as owner, owner.begin():
        await ensure_partitions(owner, CUT)
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        for table in ("shadow_outbox", "shadow_episodes", "signal_outcomes", "agent_signals"):
            await session.execute(text(f"DELETE FROM {table}"))  # noqa: S608
        await session.execute(text("DELETE FROM candles"))
        _exchange_id, market_id = await seed_market(session)
        _strategy_id, parent_id = await activate_version(session, key=key)
        await insert_candles(session, market_id, series(CUT))
    sibling_id = uuid.uuid4()
    async with db_session_factory() as owner, owner.begin():
        # Everything that writes ``strategy_versions`` runs on the owner
        # connection, like the CLI does: ``0010``/``0011`` left ``hunter_worker``
        # with ``SELECT`` and nothing else on this table — ``status`` included,
        # which is what ``isolate_catalogue`` moves.
        await isolate_catalogue(owner, keep=key)
        await owner.execute(
            text(
                "INSERT INTO strategy_versions (id, strategy_id, version, status, "
                "parameters_schema, default_parameters, code_ref, params_format, activated_at, "
                "purpose, replication_parent_id, replication_index) "
                "SELECT :id, strategy_id, 'v2', 'active', parameters_schema, "
                "default_parameters, code_ref, params_format, now(), purpose, id, :k "
                "FROM strategy_versions WHERE id = :parent"
            ),
            {"id": sibling_id, "parent": parent_id, "k": ARM},
        )
        await owner.execute(
            text("UPDATE strategy_versions SET status = 'deprecated' WHERE id = :id"),
            {"id": parent_id},
        )
    async with role_session(db_session_factory, db_role="hunter_worker") as session:
        versions = await load_active_versions(session)
        market = await load_market(session, EXCHANGE, SYMBOL)
    assert market is not None
    return {
        "factory": db_session_factory,
        "version": only_version(versions, key),
        "market": market,
        "parent_id": parent_id,
        "sibling_id": sibling_id,
    }


@pytest.mark.integration
class TestASiblingEmitsUnderItsArm:
    async def test_the_roster_reads_the_lineage_from_the_columns(
        self, sibling_db: dict[str, Any]
    ) -> None:
        version = sibling_db["version"]
        assert version.id == sibling_db["sibling_id"]
        assert version.replication_parent_id == sibling_db["parent_id"]
        assert version.replication_index == ARM
        assert version.purpose == "research_only"

    async def test_the_envelope_and_the_slot_carry_the_arm(
        self, sibling_db: dict[str, Any], redis_client: Any
    ) -> None:
        """One decision, end to end: the label the run stamps is the label the
        signal envelope records **and** the label the episode slot is keyed on.

        They have to be the same string or the sweep would lock a slot the
        decision never took (``consumer.sweep_outcomes`` reads the cohort back
        out of ``signal_outcomes.meta``).
        """
        arm = f"replication:{sibling_db['parent_id']}:{ARM}"
        evaluation = await evaluate_slot(
            sibling_db["factory"],
            redis_client,
            version=sibling_db["version"],
            market=sibling_db["market"],
            bar_close=CUT,
            config=CONFIG,
            clock=lambda: CUT + timedelta(seconds=2),
        )
        assert evaluation.state.value == "triggered"
        async with role_session(sibling_db["factory"], db_role="hunter_worker") as session:
            signal = (await session.execute(select(AgentSignal))).scalar_one()
            episode = (await session.execute(select(ShadowEpisode))).scalar_one()
        assert signal.supporting_features["cohort"] == arm
        assert episode.cohort == arm
        assert episode.strategy_version_id == sibling_db["sibling_id"]
        # and the database accepted it: before 0012 this row could not exist
        assert ShadowCohort.is_valid(episode.cohort)
