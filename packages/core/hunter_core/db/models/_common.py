"""Column helpers shared by every ORM module.

DATABASE.md §1 fixes the numeric contracts: money/quantity is ``NUMERIC(28,10)``
(already the ``Decimal`` entry of ``Base.type_annotation_map``), percentages are
``NUMERIC(9,6)`` as a fraction, scores ``NUMERIC(5,2)`` and confidence
``NUMERIC(5,4)``. Postgres ``ENUM`` types are declared with ``create_type=False``
because the initial migration creates every type explicitly, before any table.
"""

from __future__ import annotations

import enum
from functools import cache
from typing import Any

from sqlalchemy import ForeignKeyConstraint, Numeric, text
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import TextClause

from hunter_core.domain.enums import ALL_ENUMS

PERCENT = Numeric(9, 6)
"""``NUMERIC(9,6)`` — percentages stored as a fraction (0.012 = 1.2%)."""

SCORE = Numeric(5, 2)
"""``NUMERIC(5,2)`` — 0-100 scores (opportunity score, anomaly severity)."""

CONFIDENCE = Numeric(5, 4)
"""``NUMERIC(5,4)`` — 0-1 confidence."""

JSONB_EMPTY: TextClause = text("'{}'::jsonb")
"""Server default for non-nullable JSONB columns."""

JSONB_EMPTY_LIST: TextClause = text("'[]'::jsonb")
"""Server default for non-nullable JSONB columns holding a list."""

TEXT_ARRAY_EMPTY: TextClause = text("'{}'::text[]")
"""Server default for non-nullable ``TEXT[]`` columns."""

UUID_ARRAY_EMPTY: TextClause = text("'{}'::uuid[]")
"""Server default for non-nullable ``UUID[]`` columns."""

SQL_FALSE: TextClause = text("false")
"""Boolean ``DEFAULT false`` (``func.false()`` would render an invalid ``false()``)."""

SQL_TRUE: TextClause = text("true")
"""Boolean ``DEFAULT true``."""


def _enum_values(enum_cls: type[enum.Enum]) -> list[str]:
    """Persist the enum *value* (``"1m"``), never the Python member name (``M1``)."""
    return [str(member.value) for member in enum_cls]


@cache
def pg_enum(name: str) -> postgresql.ENUM[Any]:
    """The Postgres ``ENUM`` type called ``name``, from ``domain.enums.ALL_ENUMS``.

    Cached so a type used by several tables is one object in the metadata.
    ``create_type=False``: the initial migration owns ``CREATE TYPE``.
    """
    return postgresql.ENUM(
        ALL_ENUMS[name],
        name=name,
        create_type=False,
        values_callable=_enum_values,
    )


def org_fk(ondelete: str = "CASCADE") -> ForeignKeyConstraint:
    """``organization_id`` -> ``organizations.id`` for tables using ``TenantMixin``.

    ``TenantMixin`` only declares the column (it cannot carry a foreign key that
    applies to every subclass), so tenant tables add the constraint here to keep
    "todo FK indexado" and referential integrity honest.
    """
    return ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete=ondelete)
