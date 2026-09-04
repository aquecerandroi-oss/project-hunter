"""PostHog server-side capture — a no-op unless a project key is configured.

ARCHITECTURE.md lists PostHog as the product-analytics tool; M0's T05 row
requires it "atras de env" (gated behind env, never firing by default in
tests/CI). ``NEXT_PUBLIC_POSTHOG_KEY`` is a public per-project key by design
(SECURITY.md §4: "PostHog key do browser e publica por design") — reused
here for the server-side client too, rather than inventing a second secret
for the same non-secret value. ``capture()`` never inspects or forwards
secrets; callers are responsible for what goes into ``properties``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import posthog

from hunter_core.logging import get_logger

if TYPE_CHECKING:
    from hunter_api.settings import ApiSettings

logger = get_logger(__name__)


def configure(settings: ApiSettings) -> None:
    """Point the PostHog SDK at the configured project, or disable it."""
    key = settings.next_public_posthog_key
    posthog.api_key = key or None
    posthog.host = settings.next_public_posthog_host
    posthog.disabled = not key


def capture(event: str, distinct_id: str, properties: dict[str, Any] | None = None) -> None:
    """Send one product-analytics event. No-op when PostHog isn't configured."""
    if posthog.disabled:
        return
    try:
        posthog.capture(event, distinct_id=distinct_id, properties=properties or {})
    except Exception:
        logger.warning("posthog_capture_failed", analytics_event=event)
