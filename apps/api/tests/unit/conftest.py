"""Fixtures shared by the API unit suite."""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

import pytest
import structlog
from structlog.testing import capture_logs

if TYPE_CHECKING:
    from collections.abc import Callable, Generator
    from contextlib import AbstractContextManager


@pytest.fixture
def module_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> Callable[[str], AbstractContextManager[list[dict[str, object]]]]:
    """Capture what ``<module>.logger`` emits, whatever structlog looked like before.

    ``configure_logging`` (any integration test that builds the app runs it) sets
    ``cache_logger_on_first_use``, which freezes each module's bound logger onto the real
    processor chain, so ``capture_logs()`` alone no longer reaches it; and with logging never
    configured at all, records go to stdout and ``caplog`` is empty. Either way a test that
    asserted on logs passed or failed with the *order* of the session. This swaps the module's
    logger for a fresh, unbound one for the duration of the test and captures at the structlog
    layer, so the result no longer depends on what ran before.
    """

    @contextmanager
    def _capture(module: str) -> Generator[list[dict[str, object]]]:
        monkeypatch.setattr(f"{module}.logger", structlog.get_logger())
        with capture_logs() as records:
            yield records  # pyright: ignore[reportReturnType]

    return _capture
