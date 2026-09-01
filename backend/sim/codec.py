"""
A small type-directed codec for the simulation's dataclasses.

Lives at the root of `sim` rather than inside a persistence package because the
entity modules themselves import it for their own `snapshot()`/`restore()`
methods, and a package here would close an import cycle back through the world
state.

Almost every entity in the world — agents, buildings, families, decisions — is
a plain dataclass with annotated fields. Hand-written `to_dict`/`from_dict`
pairs for all of them would be hundreds of lines that drift out of sync with
the model the first time somebody adds a field, and the drift would be silent:
the save would simply lose the new value.

So this walks the annotations instead. Adding a field to a dataclass makes it
persist automatically. The trade-off is that the field's type must be one this
module understands; anything exotic needs its own `snapshot()`/`restore()` on
the owning class, which is how the stateful non-dataclass objects (grid, clock,
economy, registries) are handled.
"""

from __future__ import annotations

import dataclasses
import importlib
import types
import typing
from enum import Enum
from typing import Any, TypeVar, get_args, get_origin

T = TypeVar("T")

#: Resolved annotations are expensive to compute and never change.
_HINTS: dict[type, dict[str, Any]] = {}


def hints_for(cls: type) -> dict[str, Any]:
    cached = _HINTS.get(cls)
    if cached is None:
        module = importlib.import_module(cls.__module__)
        cached = typing.get_type_hints(cls, vars(module))
        _HINTS[cls] = cached
    return cached


def encode(value: Any) -> Any:
    """Any supported value as JSON-compatible data."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Enum):
        return value.value
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: encode(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, (list, tuple, set, frozenset)):
        return [encode(item) for item in value]
    if isinstance(value, dict):
        return {_encode_key(key): encode(item) for key, item in value.items()}
    if hasattr(value, "snapshot"):
        return value.snapshot()
    raise TypeError(f"cannot persist {type(value).__name__}")


def _encode_key(key: Any) -> str:
    if isinstance(key, Enum):
        return str(key.value)
    return str(key)


def decode(annotation: Any, data: Any) -> Any:
    """`data` read back as `annotation`."""
    if annotation is Any or annotation is None:
        return data

    origin = get_origin(annotation)

    # `X | None` and other unions: the value tells us which member it is.
    if origin in (types.UnionType, typing.Union):
        members = [arg for arg in get_args(annotation) if arg is not type(None)]
        if data is None:
            return None
        for member in members:
            try:
                return decode(member, data)
            except (TypeError, ValueError, KeyError):
                continue
        return data

    if origin in (list, set, frozenset):
        (item_type,) = get_args(annotation) or (Any,)
        items = [decode(item_type, item) for item in data]
        return origin(items) if origin is not list else items

    if origin is tuple:
        args = get_args(annotation)
        if len(args) == 2 and args[1] is Ellipsis:
            return tuple(decode(args[0], item) for item in data)
        return tuple(decode(arg, item) for arg, item in zip(args, data))

    if origin is dict:
        key_type, value_type = get_args(annotation) or (Any, Any)
        return {
            _decode_key(key_type, key): decode(value_type, item)
            for key, item in data.items()
        }

    if isinstance(annotation, type):
        if issubclass(annotation, Enum):
            return annotation(data)
        if dataclasses.is_dataclass(annotation):
            return decode_dataclass(annotation, data)
        if annotation in (int, float, str, bool):
            return annotation(data)
        if annotation is dict:
            return data
        if hasattr(annotation, "restore"):
            return annotation.restore(data)

    return data


def _decode_key(key_type: Any, key: str) -> Any:
    if key_type in (int, float):
        return key_type(key)
    if isinstance(key_type, type) and issubclass(key_type, Enum):
        # StrEnum members round-trip through their value; IntEnum through int.
        try:
            return key_type(key)
        except ValueError:
            return key_type(int(key))
    return key


def decode_dataclass(cls: type[T], data: dict) -> T:
    """
    Rebuilds a dataclass, tolerating fields the save predates.

    Old saves are loaded by newer code all the time during development; a
    missing key means "use the default" rather than a crash.
    """
    hints = hints_for(cls)
    kwargs: dict[str, Any] = {}
    for field in dataclasses.fields(cls):
        if field.name not in data:
            continue
        kwargs[field.name] = decode(hints.get(field.name, Any), data[field.name])
    return cls(**kwargs)  # type: ignore[arg-type]
