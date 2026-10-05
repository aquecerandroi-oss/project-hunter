"""A failed cycle in a few hundred bytes, and nothing that was bound in the line.

Each failure used to write the SQL with its tens of thousands of parameters; the
Docker log rotated in 30 minutes and the first error of the 30/09 and 02/10 stops
went with it. These tests pin the summary to the five facts an operator needs and
to an allow-list for the two fields that can echo data (Astra, 05/10).
"""

from __future__ import annotations

import json
from typing import Any, cast
from uuid import UUID

import pytest
from asyncpg.exceptions import (
    InvalidTextRepresentationError,
    NotNullViolationError,
    UniqueViolationError,
)
from sqlalchemy.exc import IntegrityError

from hunter_scanner_worker import writers
from hunter_scanner_worker.failure_summary import summarize_exception

pytestmark = pytest.mark.unit

CONSTRAINT = "uq_opportunities_open_per_market"
KEY = "Key (market_id)=(01a073bb-9bab-7704-b083-6ce85d7b72ad) already exists."


def _postgres_error(kind: type[Exception], fields: dict[str, str]) -> Exception:
    return cast("Any", kind).new(fields)  # asyncpg ships no stubs for ``new``


def unique_violation() -> IntegrityError:
    """What production raised, shaped like production: the SQLAlchemy wrapper
    around the asyncpg error, carrying a statement and parameters of real size."""
    orig = _postgres_error(
        UniqueViolationError,
        {
            "M": f'duplicate key value violates unique constraint "{CONSTRAINT}"',
            "n": CONSTRAINT,
            "D": KEY,
            "C": "23505",
            "t": "opportunities",
        },
    )
    values = ", ".join(f"(${i * 2}::UUID, ${i * 2 + 1}::UUID)" for i in range(1, 1500))
    statement = f"INSERT INTO opportunities (id, market_id) VALUES {values}"  # noqa: S608
    params = {f"id__{i}": "x" * 40 for i in range(1500)}
    return IntegrityError(statement, params, orig)


class _RefusingSession:
    async def execute(self, *args: Any, **kwargs: Any) -> None:
        raise unique_violation()


async def test_a_unique_violation_is_summarised_in_a_few_hundred_bytes() -> None:
    # Raised from a real project function, so the traceback has a project frame.
    with pytest.raises(IntegrityError) as caught:
        await writers.write_opportunities(cast("Any", _RefusingSession()), [{"id": UUID(int=1)}])
    error = caught.value
    assert len(str(error)) > 20_000, "the premise: SQLAlchemy's own text is huge"

    summary = summarize_exception(error)

    encoded = json.dumps(summary)
    assert len(encoded) < 900
    assert summary["constraint"] == CONSTRAINT
    assert summary["detail"] == KEY
    assert summary["root_type"].endswith("UniqueViolationError")
    assert summary["message"].startswith("duplicate key value violates")
    assert any("write_opportunities" in frame for frame in summary["frames"])
    assert "INSERT INTO" not in encoded
    assert "x" * 40 not in encoded


def test_a_plain_error_keeps_its_type_and_message() -> None:
    summary = summarize_exception(TimeoutError("Timeout reading from redis:6379"))

    assert summary["error_type"] == "TimeoutError"
    assert summary["message"] == "Timeout reading from redis:6379"
    assert "constraint" not in summary


def test_a_message_is_cut_to_one_line_of_bounded_size() -> None:
    assert summarize_exception(ValueError("first line\n" + "boom " * 500))["message"] == (
        "first line"
    )
    assert len(summarize_exception(ValueError("y" * 5000))["message"]) <= 240


def test_a_not_null_violation_never_echoes_the_failing_row() -> None:
    error = _postgres_error(
        NotNullViolationError,
        {
            "M": 'null value in column "score" of relation "opportunities" violates '
            "not-null constraint",
            "D": "Failing row contains (SECRET-ROW-VALUE, null, 12.5).",
            "C": "23502",
        },
    )

    encoded = json.dumps(summarize_exception(error))

    assert "SECRET-ROW-VALUE" not in encoded
    assert "not-null constraint" in encoded, "the message of an integrity error is safe"


def test_a_data_exception_message_is_replaced_by_a_fixed_sentence() -> None:
    error = _postgres_error(
        InvalidTextRepresentationError,
        {"M": 'invalid input syntax for type uuid: "SECRET-TOKEN-9"', "C": "22P02"},
    )

    summary = summarize_exception(error)

    assert "SECRET-TOKEN-9" not in json.dumps(summary)
    assert "22P02" in summary["message"]


def test_a_unique_detail_that_is_not_a_uuid_key_is_dropped() -> None:
    error = _postgres_error(
        UniqueViolationError,
        {
            "M": 'duplicate key value violates unique constraint "uq_x"',
            "n": "uq_x",
            "D": "Key (symbol)=(SECRET-SYMBOL) already exists.",
            "C": "23505",
        },
    )

    summary = summarize_exception(error)

    assert "SECRET-SYMBOL" not in json.dumps(summary)
    assert "detail" not in summary
    assert summary["constraint"] == "uq_x"
