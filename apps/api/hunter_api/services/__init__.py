"""Application services: the mutations, each one audited (ARCHITECTURE.md §9).

Routers stay thin — parse, authorize, delegate; services own the rules
(last-OWNER protection, invitation expiry, onboarding idempotency) and the
``@audited`` decoration, so a rule cannot be bypassed by calling a different
route.
"""
