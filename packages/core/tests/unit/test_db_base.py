"""Unit tests for hunter_core.db.base: naming convention, mixins, type map."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import cast

import pytest
from sqlalchemy import TIMESTAMP, Numeric, String, Table
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Mapped, mapped_column

from hunter_core.db.base import Base, TenantMixin, TimestampMixin, UUIDPrimaryKeyMixin

pytestmark = pytest.mark.unit


class _Widget(Base, UUIDPrimaryKeyMixin, TimestampMixin, TenantMixin):
    __tablename__ = "test_widgets"

    name: Mapped[str] = mapped_column(String(50))
    price: Mapped[Decimal]
    seen_at: Mapped[datetime]


def test_uuid_primary_key_mixin_defaults_to_uuid7() -> None:
    column = _Widget.__table__.c.id
    assert column.primary_key
    generated = column.default.arg(None)
    assert isinstance(generated, uuid.UUID)
    assert generated.version == 7


def test_timestamp_mixin_columns_are_server_default() -> None:
    table = _Widget.__table__
    assert table.c.created_at.server_default is not None
    assert table.c.updated_at.server_default is not None
    assert table.c.updated_at.onupdate is not None


def test_tenant_mixin_organization_id_not_null_and_indexed() -> None:
    column = _Widget.__table__.c.organization_id
    assert column.nullable is False
    assert column.index is True
    assert isinstance(column.type, postgresql.UUID)


def test_decimal_maps_to_numeric_28_10() -> None:
    column = _Widget.__table__.c.price
    assert isinstance(column.type, Numeric)
    assert (column.type.precision, column.type.scale) == (28, 10)


def test_datetime_maps_to_timestamptz() -> None:
    column = _Widget.__table__.c.seen_at
    assert isinstance(column.type, TIMESTAMP)
    assert column.type.timezone is True


def test_naming_convention_produces_documented_names() -> None:
    table = cast(Table, _Widget.__table__)
    assert table.primary_key.name == "pk_test_widgets"
    ix_name = next(iter(table.indexes)).name
    assert ix_name == "ix_test_widgets_organization_id"
