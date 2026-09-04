"""DDL that Alembic's autogenerate cannot express.

Postgres enum types, partitions, roles, grants and Row Level Security live here
so the revision files stay readable, and so ``infra/scripts/create_partitions.py``
and ``infra/scripts/prune_partitions.py`` share one definition with the revision
of what a partition is called, where its bounds are and how it is secured.

- :mod:`ddl.enums` — ``CREATE TYPE`` / ``DROP TYPE``;
- :mod:`ddl.tables` — the frozen catalogue: grant classes, tenant tables;
- :mod:`ddl.grants` — the per-table ``GRANT``s and default privileges;
- :mod:`ddl.policies` — the RLS policies;
- :mod:`ddl.security` — roles, and one import that re-exports the three above;
- :mod:`ddl.partitions` — the initial partitions, each hardened at creation.
"""
