"""``CREATE TYPE`` / ``DROP TYPE`` for every Postgres enum.

The models declare their enum columns with ``create_type=False`` so exactly one
place owns the types: this module, driven by ``hunter_core.domain.enums.ALL_ENUMS``.
Adding a value to an enum is therefore always a migration, as DATABASE.md §1
requires. Labels come from our own ``StrEnum`` members, never from user input.
"""

from __future__ import annotations

from alembic import op

from hunter_core.domain.enums import ALL_ENUMS


def create_enum_types() -> None:
    """Create every enum type in ``ALL_ENUMS``, before any table is created."""
    for name, enum_cls in ALL_ENUMS.items():
        labels = ", ".join(f"'{member.value}'" for member in enum_cls)
        op.execute(f"CREATE TYPE {name} AS ENUM ({labels})")


def drop_enum_types() -> None:
    """Drop every enum type, after every table that uses one is gone."""
    for name in reversed(list(ALL_ENUMS)):
        op.execute(f"DROP TYPE IF EXISTS {name}")
