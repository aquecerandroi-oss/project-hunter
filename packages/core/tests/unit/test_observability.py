"""Unit tests for hunter_core.observability."""

from typing import Any

import pytest
from pydantic import SecretStr

from hunter_core import observability
from hunter_core.settings import Settings

pytestmark = pytest.mark.unit


def _fake_init(calls: list[dict[str, Any]]) -> Any:
    def init(**kw: Any) -> None:
        calls.append(kw)

    return init


def _fake_set_tag() -> Any:
    def set_tag(*_a: Any, **_kw: Any) -> None:
        return None

    return set_tag


def test_init_sentry_is_a_noop_without_dsn(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(observability.sentry_sdk, "init", _fake_init(calls))
    settings = Settings(sentry_dsn=SecretStr(""))

    observability.init_sentry(settings, role="api")

    assert calls == []


def test_init_sentry_initializes_when_dsn_present(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []
    monkeypatch.setattr(observability.sentry_sdk, "init", _fake_init(calls))
    monkeypatch.setattr(observability.sentry_sdk, "set_tag", _fake_set_tag())
    settings = Settings(
        sentry_dsn=SecretStr("https://public@example.ingest.sentry.io/1"),
        sentry_environment="test",
    )

    observability.init_sentry(settings, role="scanner")

    assert len(calls) == 1
    assert calls[0]["dsn"] == "https://public@example.ingest.sentry.io/1"
    assert calls[0]["send_default_pii"] is False
    assert calls[0]["environment"] == "test"


def test_registry_exposes_documented_metric_names() -> None:
    metric_names = {metric.name for metric in observability.registry.collect()}
    expected = {
        "hunter_events_produced",
        "hunter_events_consumed",
        "hunter_stream_lag",
        "hunter_worker_errors",
        "hunter_exchange_latency_seconds",
        "hunter_candle_gaps",
        "hunter_proposals",
        "hunter_fills_simulated",
    }
    assert expected <= metric_names


def test_metrics_asgi_app_is_callable() -> None:
    app = observability.metrics_asgi_app()
    assert callable(app)
