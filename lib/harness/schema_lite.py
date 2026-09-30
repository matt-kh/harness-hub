"""A JSON Schema (draft 2020-12) subset validator with pathed error messages.

Supported keywords: ``type`` (string or list), ``properties``, ``required``,
``additionalProperties`` (bool or schema), ``patternProperties``, ``propertyNames``, ``enum``, ``const``,
``pattern``, ``items``, ``minItems``, ``maxItems``, ``uniqueItems``, ``minimum``,
``maximum``, ``minLength``, ``oneOf``, ``anyOf``, ``allOf``, ``not``, intra-document
``$ref`` (``#/...`` JSON pointers, ``$defs``), plus the annotations ``deprecated``,
``x-replaced-by`` and ``x-bundle`` (reported as warnings, never errors).

Everything else (``format``, ``$id``, ``title``, ``description``, ``default``, ``examples``,
``x-*``) is accepted and ignored. CI cross-checks the same fixtures with the real
``jsonschema`` package so the subset cannot silently diverge.

Paths are rendered dotted (``jira.url``, ``hub.bundles[2]``); the document root is ``(root)``.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

_TYPES = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def join_path(base: str, key: Any) -> str:
    if isinstance(key, int):
        return "%s[%d]" % (base, key)
    key = str(key)
    if not re.match(r"^[A-Za-z0-9_-]+$", key):
        key = '"%s"' % key
    return key if not base else "%s.%s" % (base, key)


class ValidationResult:
    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []

    @property
    def ok(self) -> bool:
        return not self.errors

    def __repr__(self) -> str:  # pragma: no cover
        return "ValidationResult(errors=%r, warnings=%r)" % (self.errors, self.warnings)


class Validator:
    def __init__(self, schema: Dict[str, Any]):
        self.root = schema

    # -- public -------------------------------------------------------------
    def validate(self, instance: Any) -> ValidationResult:
        res = ValidationResult()
        errs, warns = self._check(self.root, instance, "")
        res.errors = errs
        res.warnings = warns
        return res

    # -- internals ----------------------------------------------------------
    def _resolve(self, ref: str) -> Dict[str, Any]:
        if not ref.startswith("#"):
            raise ValueError("only intra-document $ref is supported: %s" % ref)
        node: Any = self.root
        for part in ref[1:].split("/"):
            if not part:
                continue
            part = part.replace("~1", "/").replace("~0", "~")
            node = node[part]
        return node

    def _check(self, schema: Any, value: Any, path: str) -> Tuple[List[str], List[str]]:
        where = path or "(root)"
        errors: List[str] = []
        warns: List[str] = []
        if schema is True or schema == {}:
            return errors, warns
        if schema is False:
            return ["%s: is not allowed" % where], warns

        if "$ref" in schema:
            e, w = self._check(self._resolve(schema["$ref"]), value, path)
            errors += e
            warns += w

        if schema.get("deprecated"):
            repl = schema.get("x-replaced-by")
            warns.append("%s: is deprecated%s" % (where, "; use %s" % repl if repl else ""))

        t = schema.get("type")
        if t is not None:
            types = t if isinstance(t, list) else [t]
            if not any(_TYPES[x](value) for x in types):
                errors.append("%s: expected %s, got %s" % (where, " or ".join(types), _typename(value)))
                return errors, warns

        if "const" in schema and value != schema["const"]:
            errors.append("%s: must be %r" % (where, schema["const"]))
        if "enum" in schema and value not in schema["enum"]:
            errors.append("%s: must be one of %s (got %r)" % (
                where, ", ".join(repr(x) for x in schema["enum"]), value))

        if isinstance(value, str):
            if "pattern" in schema and not re.search(schema["pattern"], value):
                errors.append("%s: does not match %s" % (where, schema["pattern"]))
            if "minLength" in schema and len(value) < schema["minLength"]:
                errors.append("%s: shorter than %d characters" % (where, schema["minLength"]))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if "minimum" in schema and value < schema["minimum"]:
                errors.append("%s: must be >= %s" % (where, schema["minimum"]))
            if "maximum" in schema and value > schema["maximum"]:
                errors.append("%s: must be <= %s" % (where, schema["maximum"]))

        if isinstance(value, list):
            if "minItems" in schema and len(value) < schema["minItems"]:
                errors.append("%s: needs at least %d item(s)" % (where, schema["minItems"]))
            if "maxItems" in schema and len(value) > schema["maxItems"]:
                errors.append("%s: allows at most %d item(s)" % (where, schema["maxItems"]))
            if schema.get("uniqueItems"):
                seen: List[Any] = []
                for i, item in enumerate(value):
                    if item in seen:
                        errors.append("%s: duplicate item %r" % (join_path(path, i), item))
                    seen.append(item)
            if "items" in schema:
                for i, item in enumerate(value):
                    e, w = self._check(schema["items"], item, join_path(path, i))
                    errors += e
                    warns += w

        if isinstance(value, dict):
            props = schema.get("properties", {})
            for req in schema.get("required", []):
                if req not in value:
                    errors.append("%s: is required" % join_path(path, req))
            pn = schema.get("propertyNames")
            if isinstance(pn, dict):
                for key in value:
                    e, _ = self._check(pn, key, join_path(path, key))
                    if e:
                        errors.append("%s: invalid key name (%s)" % (join_path(path, key), e[0].split(": ", 1)[-1]))
            pattern_props = schema.get("patternProperties", {})
            addl = schema.get("additionalProperties", True)
            for key in value:
                sub = join_path(path, key)
                if key in props:
                    e, w = self._check(props[key], value[key], sub)
                    errors += e
                    warns += w
                    continue
                matched = False
                for pat, psch in pattern_props.items():
                    if re.search(pat, key):
                        matched = True
                        e, w = self._check(psch, value[key], sub)
                        errors += e
                        warns += w
                if matched:
                    continue
                if addl is False:
                    errors.append("%s: unknown key" % sub)
                elif isinstance(addl, dict):
                    e, w = self._check(addl, value[key], sub)
                    errors += e
                    warns += w

        for kw in ("allOf",):
            for sub in schema.get(kw, []):
                e, w = self._check(sub, value, path)
                errors += e
                warns += w
        if "anyOf" in schema:
            results = [self._check(s, value, path) for s in schema["anyOf"]]
            if not any(not e for e, _ in results):
                errors.append("%s: does not match any allowed form (%s)" % (
                    where, "; ".join(e[0] for e, _ in results if e)))
        if "oneOf" in schema:
            results = [self._check(s, value, path) for s in schema["oneOf"]]
            n_ok = sum(1 for e, _ in results if not e)
            if n_ok == 0:
                errors.append("%s: does not match any allowed form (%s)" % (
                    where, "; ".join(e[0] for e, _ in results if e)))
            elif n_ok > 1:
                errors.append("%s: matches more than one allowed form" % where)
        if "not" in schema:
            e, _ = self._check(schema["not"], value, path)
            if not e:
                errors.append("%s: matches a forbidden form" % where)
        return errors, warns


def _typename(v: Any) -> str:
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    if v is None:
        return "null"
    return type(v).__name__


def validate(schema: Dict[str, Any], instance: Any) -> ValidationResult:
    return Validator(schema).validate(instance)


def subschema_at(schema: Dict[str, Any], dotted: str) -> Optional[Dict[str, Any]]:
    """Return the property schema at ``a.b.c`` (following $ref and additionalProperties)."""
    v = Validator(schema)
    node: Any = schema
    for part in dotted.split("."):
        while isinstance(node, dict) and "$ref" in node:
            node = v._resolve(node["$ref"])
        if not isinstance(node, dict):
            return None
        props = node.get("properties", {})
        if part in props:
            node = props[part]
            continue
        addl = node.get("additionalProperties")
        if isinstance(addl, dict):
            node = addl
            continue
        return None
    while isinstance(node, dict) and "$ref" in node:
        node = v._resolve(node["$ref"])
    return node
