"""Tenant-scoped repositories (ARCHITECTURE.md §9).

Every repository is constructed with the organization it may see and a session
whose transaction already carries ``app.current_org`` — belt (the ``WHERE
organization_id`` in code) and braces (Row Level Security in Postgres), which
is what CLAUDE.md means by "tenant isolation is double".
"""
