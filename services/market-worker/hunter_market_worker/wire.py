"""Typed boundary for msgpack's untyped extension functions."""

from typing import Any

import msgpack

_codec: Any = msgpack


def packb(value: Any, *, use_bin_type: bool = True) -> bytes:
    return _codec.packb(value, use_bin_type=use_bin_type)


def unpackb(value: bytes) -> Any:
    return _codec.unpackb(value, raw=False)
