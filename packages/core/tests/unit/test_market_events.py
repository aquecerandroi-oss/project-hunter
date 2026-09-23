"""``market_events`` — the shape of the non-meme news row (T4.82, revision
``0059_market_events``, design ``docs/design/tela-confluencia-mercado.md`` §7a
item 4).

The model and the migration's DDL are two hand-written descriptions of one
table, and ``alembic check`` (which would catch a drift between them) needs a
live Postgres. These assertions need none, so the pairs that matter are pinned
here: the column set, what may be ``NULL`` and what may not, the label
vocabularies, and the two properties the design argued for explicitly —

- it is **global**: no ``organization_id``, therefore no RLS, like
  ``meme_events`` and ``meme_live_*``;
- ``symbol`` is ``NOT NULL`` while ``market_id`` is nullable, because a news
  item can be recorded before the pair enters the monitored universe (§9's
  written divergence from Astra's review).
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from types import ModuleType

import pytest

from hunter_core.db.models.market_events import (
    MARKET_EVENT_CONFIDENCES,
    MARKET_EVENT_KINDS,
    MARKET_EVENT_SOURCES,
    MarketEvent,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[4]
MIGRATIONS_DIR = REPO_ROOT / "infra" / "migrations"

EXPECTED_COLUMNS = {
    "id",
    "market_id",
    "exchange",
    "symbol",
    "source",
    "kind",
    "title",
    "url",
    "published_at",
    "observed_at",
    "ingested_at",
    "confidence",
    "notes",
    "recorded_by",
}

NULLABLE = {"market_id", "exchange", "url", "published_at"}


def _ddl() -> ModuleType:
    """``infra/migrations/ddl/market_events.py``, imported by path.

    ``infra/migrations`` is not a uv workspace member, so ``ddl`` only resolves
    once its directory is on ``sys.path`` — the same thing
    ``tests/integration/conftest.py``'s ``migration_ddl`` does, and the same
    thing ``infra/migrations/env.py`` does in production.
    """
    if str(MIGRATIONS_DIR) not in sys.path:
        sys.path.insert(0, str(MIGRATIONS_DIR))
    return importlib.import_module("ddl.market_events")


def _ddl_text() -> str:
    return str(_ddl().CREATE_MARKET_EVENTS)


def _ddl_indexes() -> str:
    return "\n".join(str(statement) for statement in _ddl().MARKET_EVENTS_INDEXES)


class TestModel:
    def test_the_table_is_named_market_events(self) -> None:
        assert MarketEvent.__tablename__ == "market_events"

    def test_the_column_set_is_exactly_the_one_the_spec_lists(self) -> None:
        assert {c.name for c in MarketEvent.__table__.columns} == EXPECTED_COLUMNS

    def test_it_is_global_and_therefore_carries_no_organization(self) -> None:
        """No ``organization_id`` means no RLS policy can key on one — the same
        decision ``meme_events`` took. The gate is the router's, not the row's."""
        assert "organization_id" not in {c.name for c in MarketEvent.__table__.columns}

    @pytest.mark.parametrize("column", sorted(NULLABLE))
    def test_the_nullable_columns_are_nullable(self, column: str) -> None:
        assert MarketEvent.__table__.columns[column].nullable

    @pytest.mark.parametrize("column", sorted(EXPECTED_COLUMNS - NULLABLE))
    def test_every_other_column_is_not_nullable(self, column: str) -> None:
        assert not MarketEvent.__table__.columns[column].nullable

    def test_a_news_item_can_predate_the_market_row_it_is_about(self) -> None:
        """§9: ``symbol`` is the join key and is mandatory; ``market_id`` fills
        in later, if ever. Losing a news item for want of a ``markets`` row
        would be worse than carrying a null for a few days."""
        assert not MarketEvent.__table__.columns["symbol"].nullable
        assert MarketEvent.__table__.columns["market_id"].nullable

    def test_the_two_instants_are_separate_columns(self) -> None:
        """§4C ("depois deste instante") only works because when a thing was
        published and when we learned it are two different facts."""
        assert "published_at" in EXPECTED_COLUMNS
        assert "ingested_at" in EXPECTED_COLUMNS


class TestVocabularies:
    def test_the_labels_are_the_ones_the_spec_named(self) -> None:
        assert MARKET_EVENT_SOURCES == ("baha", "manual", "plantao", "exchange_notice")
        assert MARKET_EVENT_KINDS == (
            "listing",
            "delisting",
            "upgrade",
            "incident",
            "macro",
            "company",
            "narrative",
        )
        assert MARKET_EVENT_CONFIDENCES == ("confirmed", "reported", "rumor")

    @pytest.mark.parametrize(
        ("name", "labels"),
        [
            ("source", MARKET_EVENT_SOURCES),
            ("kind", MARKET_EVENT_KINDS),
            ("confidence", MARKET_EVENT_CONFIDENCES),
        ],
    )
    def test_every_label_is_in_the_migration_check_constraint(
        self, name: str, labels: tuple[str, ...]
    ) -> None:
        ddl = _ddl_text()
        assert f"ck_market_events_{name}_is_a_known_label" in ddl
        for label in labels:
            assert f"'{label}'" in ddl


class TestModelAndDdlAgree:
    def test_every_model_column_appears_in_the_create_table(self) -> None:
        ddl = _ddl_text()
        for column in sorted(EXPECTED_COLUMNS):
            assert f"    {column} " in ddl, f"{column} missing from the 0059 CREATE TABLE"

    def test_the_create_table_declares_the_same_not_nulls(self) -> None:
        lines = {
            line.strip().split(" ", 1)[0]: line
            for line in _ddl_text().splitlines()
            if line.startswith("    ") and not line.strip().startswith("CONSTRAINT")
        }
        for column in sorted(EXPECTED_COLUMNS - NULLABLE - {"id"}):
            assert "NOT NULL" in lines[column], f"{column} should be NOT NULL in the DDL"
        for column in sorted(NULLABLE):
            assert "NOT NULL" not in lines[column], f"{column} should be nullable in the DDL"

    def test_the_partial_unique_index_makes_re_registration_idempotent(self) -> None:
        """§7a item 4: ``(source, url)`` unique where a url exists, so the
        plantão re-running the script on the same link writes one row, not two."""
        indexes = _ddl_indexes()
        assert "uq_market_events_source_url_symbol" in indexes
        assert "(source, url, symbol)" in indexes, (
            "Astra, review of T4.82: on (source, url) alone one announcement naming two "
            "pairs loses its second filing, and that pair's screen never shows it"
        )
        assert "WHERE url IS NOT NULL" in indexes

    def test_the_reading_index_is_the_one_the_screen_queries_by(self) -> None:
        indexes = _ddl_indexes()
        assert "(symbol, published_at)" in indexes
        assert "DESC" not in indexes, (
            "ascending: Postgres reads a b-tree backwards for free, and an ordered index "
            "is something alembic check cannot compare against the model"
        )
