"""Unit tests for the pure logic behind T2.6's read models: cursor codecs,
status-filter validation, the envelope helper and the Postgres-failure
translator — no database, no Redis.
"""

from __future__ import annotations

import base64
import uuid
from decimal import Decimal

import pytest
import sqlalchemy.exc as sa_exc
from sqlalchemy.dialects import postgresql

from hunter_api.repositories.anomalies import (
    InvalidAnomalyCursorError,
    decode_anomaly_cursor,
    encode_anomaly_cursor,
)
from hunter_api.repositories.opportunities import (
    InvalidOpportunityCursorError,
    build_list_statement,
    decode_opportunity_cursor,
    encode_opportunity_cursor,
)
from hunter_api.repositories.radar_common import (
    FEATURE_ENVELOPE_PATH,
    FEATURE_KEY_VOLATILITY,
    FEATURE_KEY_VOLUME,
    AnalysisDataUnavailableError,
    InvalidRadarCursorError,
    decode_sort_cursor,
    encode_sort_cursor,
    feature_value_expr,
    like_contains,
    postgres_failures_as_503,
    sentinel_for,
)
from hunter_api.repositories.regime import (
    InvalidRegimeCursorError,
    decode_regime_cursor,
    encode_regime_cursor,
)
from hunter_api.routers.opportunities import (
    EnvelopeHistoryLimitError,
    resolve_history_limit,
)
from hunter_api.schemas.radar import RadarStatusFilter
from hunter_api.services.opportunities import extract_baseline_ids
from hunter_api.services.radar import StatusRequiresOrgError, resolve_status_tokens
from hunter_core.domain.types import utcnow
from hunter_indicators.opportunity import (
    ScoreContext,
    WeightProfile,
    opportunity_envelope,
    score_opportunity,
)
from packages.indicators.tests.scoring import CONFIG, MARKET, baselines_for, ok, vector

pytestmark = pytest.mark.unit

NAIVE_TIMESTAMP = "2026-09-06T12:00:00"
"""A cursor timestamp with no offset — what a hand-built cursor looks like."""


def test_radar_sort_cursor_round_trips() -> None:
    row_id = uuid.uuid4()
    cursor = encode_sort_cursor(Decimal("62.50"), row_id)
    assert decode_sort_cursor(cursor) == (Decimal("62.50"), row_id)


def test_radar_sort_cursor_none_is_none() -> None:
    assert decode_sort_cursor(None) is None


@pytest.mark.parametrize("garbage", ["", "!!!not-valid!!!", "a" * 200])
def test_radar_sort_cursor_rejects_garbage(garbage: str) -> None:
    with pytest.raises(InvalidRadarCursorError):
        decode_sort_cursor(garbage)


def test_opportunity_cursor_rejects_garbage() -> None:
    with pytest.raises(InvalidOpportunityCursorError):
        decode_opportunity_cursor("!!!not-valid!!!")


def test_anomaly_cursor_round_trips() -> None:
    now = utcnow()
    row_id = uuid.uuid4()
    assert decode_anomaly_cursor(encode_anomaly_cursor(now, row_id)) == (now, row_id)


def test_anomaly_cursor_rejects_garbage() -> None:
    with pytest.raises(InvalidAnomalyCursorError):
        decode_anomaly_cursor("!!!not-valid!!!")


def test_regime_cursor_round_trips() -> None:
    now = utcnow()
    row_id = uuid.uuid4()
    assert decode_regime_cursor(encode_regime_cursor(now, row_id)) == (now, row_id)


def test_regime_cursor_rejects_garbage() -> None:
    with pytest.raises(InvalidRegimeCursorError):
        decode_regime_cursor("!!!not-valid!!!")


def test_sentinel_for_desc_is_very_negative_and_asc_is_very_positive() -> None:
    assert sentinel_for("desc") < Decimal("-1000000")
    assert sentinel_for("asc") > Decimal("1000000")


def test_resolve_status_tokens_empty_when_none() -> None:
    assert resolve_status_tokens(None, has_org=False) == ()


def test_resolve_status_tokens_native_status_never_requires_org() -> None:
    tokens = resolve_status_tokens([RadarStatusFilter.HOT], has_org=False)
    assert tokens == ("HOT",)


def test_resolve_status_tokens_in_position_without_org_raises() -> None:
    with pytest.raises(StatusRequiresOrgError):
        resolve_status_tokens([RadarStatusFilter.IN_POSITION], has_org=False)


def test_resolve_status_tokens_risk_blocked_without_org_raises() -> None:
    with pytest.raises(StatusRequiresOrgError):
        resolve_status_tokens([RadarStatusFilter.RISK_BLOCKED], has_org=False)


def test_resolve_status_tokens_in_position_with_org_is_allowed() -> None:
    tokens = resolve_status_tokens([RadarStatusFilter.IN_POSITION], has_org=True)
    assert tokens == ("IN_POSITION",)


def test_extract_baseline_ids_reads_well_formed_uuids() -> None:
    baseline_id = str(uuid.uuid4())
    result = extract_baseline_ids({"baseline_ids": [baseline_id]})
    assert result == [uuid.UUID(baseline_id)]


def test_extract_baseline_ids_missing_key_is_empty_not_an_error() -> None:
    assert extract_baseline_ids({}) == []


def test_extract_baseline_ids_drops_malformed_entries_without_raising() -> None:
    result = extract_baseline_ids({"baseline_ids": ["not-a-uuid", 123, None]})
    assert result == []


def test_extract_baseline_ids_not_a_list_is_empty() -> None:
    assert extract_baseline_ids({"baseline_ids": "not-a-list"}) == []


async def test_postgres_failures_as_503_translates_operational_error() -> None:
    with pytest.raises(AnalysisDataUnavailableError):
        async with postgres_failures_as_503():
            raise sa_exc.OperationalError("SELECT 1", {}, Exception("connection refused"))


async def test_postgres_failures_as_503_translates_interface_error() -> None:
    with pytest.raises(AnalysisDataUnavailableError):
        async with postgres_failures_as_503():
            raise sa_exc.InterfaceError("SELECT 1", {}, Exception("connection closed"))


async def test_postgres_failures_as_503_lets_other_errors_through() -> None:
    """A statement-level error (bad data, a real bug) must not be mistaken
    for "the database is down" — only connection-level failures translate.
    """
    with pytest.raises(sa_exc.IntegrityError):
        async with postgres_failures_as_503():
            raise sa_exc.IntegrityError("INSERT ...", {}, Exception("unique violation"))


async def test_postgres_failures_as_503_passes_through_on_success() -> None:
    async with postgres_failures_as_503():
        value = 1 + 1
    assert value == 2


# --- MUST-FIX round (security-reviewer, 2026-09-06) -------------------------


async def test_postgres_failures_as_503_translates_pool_timeout() -> None:
    """Pool exhaustion is an infrastructure failure, not a bug in the handler.

    ``sqlalchemy.exc.TimeoutError`` is *not* a ``DBAPIError`` — before this it
    fell past the translator and surfaced as a generic 500.
    """
    with pytest.raises(AnalysisDataUnavailableError):
        async with postgres_failures_as_503():
            raise sa_exc.TimeoutError("QueuePool limit of size 5 overflow 5 reached")


async def test_postgres_failures_as_503_translates_a_refused_socket() -> None:
    """asyncpg raises ``ConnectionRefusedError`` before SQLAlchemy has a DBAPI
    error to wrap it in — ``auth/principal.py`` already catches ``OSError`` for
    exactly this."""
    with pytest.raises(AnalysisDataUnavailableError):
        async with postgres_failures_as_503():
            raise ConnectionRefusedError(111, "Connection refused")


@pytest.mark.parametrize("bad", ["NaN", "Infinity", "-Infinity", "sNaN"])
def test_radar_sort_cursor_rejects_non_finite_decimal(bad: str) -> None:
    """A cursor decoding to NaN/Infinity is a 422, never a 500 from Postgres."""
    cursor = base64.urlsafe_b64encode(f"{bad}|{uuid.uuid4()}".encode()).decode()
    with pytest.raises(InvalidRadarCursorError):
        decode_sort_cursor(cursor)


def test_opportunity_cursor_round_trips_score_and_id() -> None:
    row_id = uuid.uuid4()
    cursor = encode_opportunity_cursor(Decimal("71.25"), row_id)
    assert decode_opportunity_cursor(cursor) == (Decimal("71.25"), row_id)


@pytest.mark.parametrize("bad", ["NaN", "Infinity"])
def test_opportunity_cursor_rejects_non_finite_decimal(bad: str) -> None:
    cursor = base64.urlsafe_b64encode(f"{bad}|{uuid.uuid4()}".encode()).decode()
    with pytest.raises(InvalidOpportunityCursorError):
        decode_opportunity_cursor(cursor)


def test_anomaly_cursor_rejects_naive_timestamp() -> None:
    """A naive timestamp compared against a ``timestamptz`` column silently
    means "in whatever the server's timezone is" — refuse it instead."""
    raw = f"{NAIVE_TIMESTAMP}|{uuid.uuid4()}"
    cursor = base64.urlsafe_b64encode(raw.encode()).decode()
    with pytest.raises(InvalidAnomalyCursorError):
        decode_anomaly_cursor(cursor)


def test_regime_cursor_rejects_naive_timestamp() -> None:
    raw = f"{NAIVE_TIMESTAMP}|{uuid.uuid4()}"
    cursor = base64.urlsafe_b64encode(raw.encode()).decode()
    with pytest.raises(InvalidRegimeCursorError):
        decode_regime_cursor(cursor)


def test_like_contains_escapes_wildcards() -> None:
    """``q=%`` must search for a literal percent sign, not for every symbol."""
    assert like_contains("50%_x") == r"%50\%\_x%"
    assert like_contains("a\\b") == "%a\\\\b%"


def test_opportunity_list_statement_does_not_select_decomposition() -> None:
    """The list is a table, not a detail view: the JSONB decomposition of every
    row would be shipped in full for nothing (MF-2).
    """
    compiled = str(
        build_list_statement(
            score_min=None,
            statuses=(),
            stages=(),
            exchange=None,
            symbol_query=None,
            cursor=None,
            limit=50,
        ).compile(dialect=postgresql.dialect())
    )
    assert "decomposition" not in compiled


def test_opportunity_list_statement_is_bounded_by_a_limit() -> None:
    compiled = str(
        build_list_statement(
            score_min=None,
            statuses=(),
            stages=(),
            exchange=None,
            symbol_query=None,
            cursor=None,
            limit=50,
        ).compile(dialect=postgresql.dialect())
    )
    assert "LIMIT" in compiled


@pytest.mark.parametrize(
    ("requested", "include_envelope", "expected"),
    [
        (None, False, 100),
        (None, True, 50),
        (500, False, 500),
        (50, True, 50),
        (7, True, 7),
    ],
)
def test_resolve_history_limit(
    requested: int | None, include_envelope: bool, expected: int
) -> None:
    """An omitted limit adapts to the envelope cap; an explicit one is honoured."""
    assert resolve_history_limit(requested, include_envelope=include_envelope) == expected


def test_resolve_history_limit_explicit_over_the_envelope_cap_is_422() -> None:
    """MF-3: the caller named 500 — silently giving back 50 would be charted as
    a complete trajectory."""
    with pytest.raises(EnvelopeHistoryLimitError) as raised:
        resolve_history_limit(500, include_envelope=True)
    assert raised.value.status_code == 422
    assert raised.value.detail is not None
    assert "50" in raised.value.detail


# --- contract test: the envelope path the radar actually reads (HIGH bug, ----
# --- Astra/T2.7 cross-package review, 2026-09-06) ----------------------------
#
# T2.6 (this package) and T2.4 (`hunter_indicators.opportunity.envelope`) each
# froze a shape for `opportunities.feature_snapshot` without a shared test
# forcing them to agree: this module read `feature_snapshot["features"]
# ["values"][key]["value"]`, but `opportunity_envelope()` actually nests the
# vector under `feature_snapshot["vector"]["values"][key]["value"]`
# (`packages/indicators/hunter_indicators/opportunity/envelope.py::
# opportunity_envelope`, `.../features/vector.py::FeatureVector.as_wire`).
# The consequence was silent: `volatility_min`/`volatility_max` excluded every
# row and `sort=volume` fell back to the NULL sentinel for every row, with no
# error anywhere in the response.
#
# The fixture below builds the envelope by *calling* `opportunity_envelope()`
# with a minimal real `ScoreResult`/`ScoreContext` (the same fixtures
# `packages/indicators/tests/scoring.py` gives its own scorer tests), so this
# test is a statement about the producer's actual output, not about a second
# hand-typed dict that could drift from it exactly the way the first one did.

_CONTRACT_WEIGHTS: dict[str, object] = {
    "components": {
        name: ("1" if name == "momentum" else "0")
        for name in (
            "momentum",
            "volume",
            "order_flow",
            "liquidity",
            "derivatives",
            "market_regime",
            "anomalies",
            "agent_consensus",
            "external_intelligence",
        )
    },
    "early_movement": {"magnitude": "0", "values": [-1, 0, 1]},
    "precision": {
        "score_decimals": 2,
        "confidence_decimals": 4,
        "component_decimals": 4,
        "rounding": "ROUND_HALF_EVEN",
    },
}
"""A minimal but valid weight profile — every component the scorer iterates
needs a weight, or ``WeightProfile.weight_of`` raises. Only ``momentum``
carries any weight; this test cares about the envelope's shape, not the score."""


def _real_envelope(values: dict[str, str]) -> dict[str, object]:
    """A ``feature_snapshot`` produced by the real ``opportunity_envelope()``."""
    ctx = ScoreContext(
        market_id=MARKET,
        vector=vector({key: ok(key, value) for key, value in values.items()}),
        projection=baselines_for(list(values)),
        config=CONFIG,
        profile=WeightProfile.from_weights(_CONTRACT_WEIGHTS, version="contract-test"),
    )
    result = score_opportunity(ctx)
    return opportunity_envelope(result, ctx)


def test_feature_value_expr_path_matches_the_real_envelope_shape() -> None:
    envelope = _real_envelope({FEATURE_KEY_VOLATILITY: "0.05", FEATURE_KEY_VOLUME: "9"})
    outer, inner = FEATURE_ENVELOPE_PATH
    assert envelope[outer][inner][FEATURE_KEY_VOLATILITY]["value"] == Decimal("0.05")  # type: ignore[index]
    assert envelope[outer][inner][FEATURE_KEY_VOLUME]["value"] == Decimal("9")  # type: ignore[index]


def test_feature_value_expr_compiles_to_the_confirmed_json_path() -> None:
    """A cheap, complementary guard: the compiled SQL literally names the two
    path segments, so an edit to the literal keys inside ``feature_value_expr``
    cannot silently drift from :data:`FEATURE_ENVELOPE_PATH`."""
    compiled = str(
        feature_value_expr(FEATURE_KEY_VOLUME).compile(
            dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
        )
    )
    assert "'vector'" in compiled
    assert "'values'" in compiled
    assert f"'{FEATURE_KEY_VOLUME}'" in compiled
