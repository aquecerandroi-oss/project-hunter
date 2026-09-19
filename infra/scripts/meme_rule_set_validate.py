"""``meme_rule_set.py --set-param``'s pre-write guard (T4.64).

Two incidents on 18/09/2026, both a bare JSON number where the Lab reads a
JSON **string**: 14:19 BRT ``max_sol_per_bet=0.28`` (``RuleSetSpec.from_params``
raises ``a float is not an exact number`` — ``hunter_meme_worker.lab_params
.decimal_of``), crash-looping the worker 10 minutes; 19:47 BRT
``trailing_arm_x="1.0"`` reached ``ExitRules.__post_init__``'s ``trailing_arm_
multiple must be greater than 1 when set`` (T4.65 later made the *reader*
tolerant of an armed-at-1x value — see ``lab_params.arm_multiple_or_none`` —
but a bad value should never have reached the table), crash-looping it ~3.5h.

``validate_set_param`` runs before every ``--set-param`` write **and** every
dry-run (a dry-run is the operator's chance to see this without ``--apply``):
it merges the one key into the target row's own live ``params``, then loads
the merge through the exact code the worker loads a rule set with —
``RuleSetSpec.from_params`` (the entry gate, ``_gate_from_params``, included),
plus the exit rules built the way a bet actually builds them
(``effective_params(spec, {}).exit_rules()``). Anything that function raises
or refuses is surfaced verbatim, wrapped in :class:`WouldNotLoad`
(``meme_rule_set_types``); the caller writes nothing.

Before that (cheaper, and a better message): :func:`_check_decimal_convention`
catches the shape of both incidents directly — a bare ``int``/``float`` for a
key whose value in the *live* document is already a JSON string. A frozen set
never mixes the two for one key, so this is refused before it can even reach
``RuleSetSpec.from_params``, with the exact fix to type.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from meme_rule_set_types import WouldNotLoad

from hunter_meme_worker.lab_models import RuleSetSpec, effective_params

if TYPE_CHECKING:
    from meme_rule_set import RuleSetRow

__all__ = ["validate_live", "validate_set_param"]


def _check_decimal_convention(row: RuleSetRow, key: str, value: Any, raw: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return
    if isinstance(row.params.get(key), str):
        raise WouldNotLoad(f"decimals are strings: use '{key}=\"{raw}\"'")


def validate_params(row: RuleSetRow, params: dict[str, Any]) -> None:
    """``params`` loaded the way the worker loads them, or :class:`WouldNotLoad`
    naming the row and carrying the worker's own error verbatim."""
    try:
        spec = RuleSetSpec.from_params(
            id=row.id,
            name=row.name,
            version=row.version,
            kind=row.kind,
            exp_ref=row.exp_ref,
            status=row.status,
            code_ref="meme_rule_set_validate",
            params=params,
        )
        effective = effective_params(spec, {})
        if isinstance(effective, str):
            raise ValueError(f"effective_params refused: {effective}")
        effective.exit_rules()
    except WouldNotLoad:
        raise
    except Exception as exc:  # the worker's own exception, verbatim
        raise WouldNotLoad(f"{row.label}: {exc}") from exc


def validate_set_param(row: RuleSetRow, key: str, value: Any, raw: str) -> None:
    """One target of ``--set-param``: the coercion check, then the full load."""
    _check_decimal_convention(row, key, value, raw)
    validate_params(row, {**row.params, key: value})


def validate_live(row: RuleSetRow) -> None:
    """``--validate NAME/VERSION``: the row's own live ``params``, unchanged."""
    validate_params(row, dict(row.params))
