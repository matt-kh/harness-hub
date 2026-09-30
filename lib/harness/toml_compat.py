"""TOML reading (stdlib ``tomllib`` on 3.11+, vendored ``tomli`` 2.x below) and a small writer.

The writer covers exactly what the engine emits (Codex ``config.toml`` managed blocks and
``harness init`` / ``config set`` values): tables, arrays of tables, strings, ints, floats,
bools, arrays and inline tables. It is not a general-purpose TOML serializer.
"""
from __future__ import annotations

import math
import re
from typing import Any, Dict, List

try:  # python >= 3.11
    import tomllib as _toml  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - exercised on python 3.9/3.10
    from ._vendor import tomli as _toml  # type: ignore[no-redef]

TOMLDecodeError = _toml.TOMLDecodeError

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")


def loads(text: str) -> Dict[str, Any]:
    return _toml.loads(text)


def load_file(path: str) -> Dict[str, Any]:
    with open(path, "rb") as fh:
        return _toml.load(fh)


def quote_key(key: str) -> str:
    return key if _BARE_KEY.match(key) else dump_string(key)


def dump_string(value: str) -> str:
    out = ['"']
    for ch in value:
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append("\\u%04x" % ord(ch))
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def dump_value(value: Any) -> str:
    """Serialize a scalar, array or inline table."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        if math.isnan(value):
            return "nan"
        if math.isinf(value):
            return "inf" if value > 0 else "-inf"
        return repr(value)
    if isinstance(value, str):
        return dump_string(value)
    if isinstance(value, (list, tuple)):
        return "[" + ", ".join(dump_value(v) for v in value) + "]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        return "{ " + ", ".join(
            "%s = %s" % (quote_key(k), dump_value(v)) for k, v in value.items()
        ) + " }"
    raise TypeError("cannot serialize %r to TOML" % (type(value).__name__,))


def dump_table(name: str, table: Dict[str, Any], array: bool = False) -> str:
    """Serialize one ``[name]`` (or ``[[name]]``) table. Nested dicts become inline tables."""
    dotted = ".".join(quote_key(p) for p in name.split("."))
    head = "[[%s]]" % dotted if array else "[%s]" % dotted
    lines: List[str] = [head]
    for key, val in table.items():
        lines.append("%s = %s" % (quote_key(key), dump_value(val)))
    return "\n".join(lines) + "\n"
