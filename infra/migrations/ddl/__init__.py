"""DDL that Alembic's autogenerate cannot express.

Postgres enum types, monthly RANGE partitions, roles/grants and Row Level
Security policies live here so the revision files stay readable and so
``infra/scripts/create_partitions.py`` and the revision share one definition of
what a partition is called and where its bounds are.
"""
