"""Configuration: locate, layer, override, validate, explain, edit and migrate.

Layering (lowest to highest precedence, ARCHITECTURE §2):

0. ``default`` values of every active bundle's ``[requires.config]`` entries
   (documentation defaults; ``{{ key }}`` references in them are resolved after merging)
1. ``bundles/<b>/defaults.toml`` of every active bundle (in resolved bundle order)
2. org overlay ``<config dir>/harness.org.toml`` (written by ``harness init --from``)
3. the config file itself (``local/harness.toml``)
4. ``<config dir>/harness.user.toml`` (machine-specific)
5. environment ``HARNESS_<SECTION>_<KEY>`` (e.g. ``HARNESS_JIRA_URL``)

Decisions documented here (the contract leaves them open):

* The org and user overlays are looked up next to the resolved config file, so
  ``--config tests/fixtures/harness.ci.toml`` never picks up a developer's ``local/`` files.
* Environment overrides apply only to keys the compiled schema (or the merged config)
  knows; ``HARNESS_HOME``/``HARNESS_CONFIG``/... never collide because they name no key.
  ``HARNESS_JIRA_URL`` is matched by upper-casing the dotted key and replacing dots with
  underscores; an ambiguous match is an error. Values are coerced by the schema type
  (booleans ``1/true/yes/on``, arrays as JSON or comma-separated, objects as JSON).
* Tables merge key by key; arrays and scalars are replaced by the higher layer.
* Secret shapes are rejected: a key whose last segment contains ``token``, ``secret``,
  ``password`` or ``bearer`` (unless it ends in ``_file``/``_path`` and holds a path), or any
  string of 30+ token-alphabet characters with high Shannon entropy, or a well-known token
  prefix (``ghp_``, ``glpat-``, ``xoxb-``, ``AKIA``, JWT ``eyJ``).  # gate-allow: documented token prefixes
"""
from __future__ import annotations

import copy
import json
import math
import os
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from . import schema_lite, toml_compat
from .util import HarnessError, hub_home, read_text

SECRETS_DOC = "docs/reference/secrets.md"

# ----------------------------------------------------------------- location


def resolve_config_path(cli_path: Optional[str] = None, home: Optional[str] = None) -> str:
    """``--config PATH`` > ``$HARNESS_CONFIG`` > ``$HARNESS_HOME/local/harness.toml``."""
    if cli_path:
        return os.path.abspath(os.path.expanduser(cli_path))
    env = os.environ.get("HARNESS_CONFIG")
    if env:
        return os.path.abspath(os.path.expanduser(env))
    return os.path.join(home or hub_home(), "local", "harness.toml")


def overlay_paths(config_path: str) -> Tuple[str, str]:
    d = os.path.dirname(config_path)
    return os.path.join(d, "harness.org.toml"), os.path.join(d, "harness.user.toml")


# ----------------------------------------------------------------- dict helpers


def deep_merge(base: Dict[str, Any], over: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def flatten(d: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """``{"a": {"b": 1}}`` -> ``{"a.b": 1}`` (arrays are leaves)."""
    out: Dict[str, Any] = {}
    for k, v in d.items():
        key = "%s.%s" % (prefix, k) if prefix else k
        if isinstance(v, dict) and v:
            out.update(flatten(v, key))
        else:
            out[key] = v
    return out


_MISSING = object()


def get_path(d: Dict[str, Any], dotted: str, default: Any = _MISSING) -> Any:
    node: Any = d
    for part in dotted.split("."):
        if isinstance(node, dict) and part in node:
            node = node[part]
        else:
            if default is _MISSING:
                raise KeyError(dotted)
            return default
    return node


def has_path(d: Dict[str, Any], dotted: str) -> bool:
    return get_path(d, dotted, _MISSING_SENTINEL) is not _MISSING_SENTINEL


_MISSING_SENTINEL = object()


def set_path(d: Dict[str, Any], dotted: str, value: Any) -> None:
    parts = dotted.split(".")
    node = d
    for part in parts[:-1]:
        nxt = node.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            node[part] = nxt
        node = nxt
    node[parts[-1]] = value


# ----------------------------------------------------------------- secrets

_SECRET_KEY = re.compile(r"token|secret|password|passwd|bearer", re.I)
_PATHY_SUFFIX = re.compile(r"_(file|path)$")
_TOKEN_PREFIX = re.compile(r"^(ghp_|gho_|ghs_|github_pat_|glpat-|xox[abpr]-|AKIA[0-9A-Z]{12,}|eyJ[A-Za-z0-9_-]{10,}\.)")  # gate-allow: detection regex
_TOKEN_ALPHABET = re.compile(r"^[A-Za-z0-9+/_=-]{30,}$")


def shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    counts: Dict[str, int] = {}
    for ch in s:
        counts[ch] = counts.get(ch, 0) + 1
    n = float(len(s))
    return -sum((c / n) * math.log(c / n, 2) for c in counts.values())


def looks_like_secret_value(value: str) -> bool:
    if _TOKEN_PREFIX.match(value):
        return True
    if value.startswith(("/", "~", ".")):
        return False
    if not _TOKEN_ALPHABET.match(value):
        return False
    has_digit = any(c.isdigit() for c in value)
    has_alpha = any(c.isalpha() for c in value)
    return has_digit and has_alpha and shannon_entropy(value) >= 3.5


def secret_findings(cfg: Dict[str, Any]) -> List[str]:
    """Pathed error messages for every secret-shaped key or value."""
    found: List[str] = []

    def walk(node: Any, path: str) -> None:
        if isinstance(node, dict):
            for k, v in node.items():
                sub = "%s.%s" % (path, k) if path else str(k)
                if _SECRET_KEY.search(str(k)):
                    pathy = _PATHY_SUFFIX.search(str(k)) and (
                        isinstance(v, str) and (v == "" or v.startswith(("~", "/", "$")))
                    )
                    if not pathy:
                        found.append("%s: key name looks like a secret; secrets never live in harness.toml "
                                     "(see %s)" % (sub, SECRETS_DOC))
                        continue
                walk(v, sub)
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, "%s[%d]" % (path, i))
        elif isinstance(node, str) and looks_like_secret_value(node):
            found.append("%s: value looks like a secret (token-shaped, high entropy); secrets never live "
                         "in harness.toml (see %s)" % (path, SECRETS_DOC))

    walk(cfg, "")
    return found


# ----------------------------------------------------------------- schema compile


def load_base_schema(home: Optional[str] = None) -> Dict[str, Any]:
    path = os.path.join(home or hub_home(), "schema", "harness-config.schema.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


_SIMPLE_TYPES = ("string", "integer", "number", "boolean", "object", "array")


def config_entry_schema(entry: Dict[str, Any], bundle: str) -> Dict[str, Any]:
    """Translate one ``[requires.config."a.b"]`` entry into a JSON-Schema property."""
    sch: Dict[str, Any] = {}
    if entry.get("type"):
        sch["type"] = entry["type"]
    for k in ("description", "pattern", "enum", "minimum", "maximum", "deprecated"):
        if k in entry:
            sch[k] = entry[k]
    if "default" in entry:
        sch["default"] = entry["default"]
    if "example" in entry:
        sch["examples"] = [entry["example"]]
    if "examples" in entry:
        sch["examples"] = list(entry["examples"])
    if "replaced_by" in entry:
        sch["x-replaced-by"] = entry["replaced_by"]
        sch.setdefault("deprecated", True)
    items = entry.get("items")
    if isinstance(items, str):
        sch["items"] = {"type": items}
    elif isinstance(items, dict):
        sch["items"] = items
    if isinstance(entry.get("schema"), dict):
        sch.update(entry["schema"])
    sch["x-bundle"] = bundle
    return sch


def compile_schema(base: Dict[str, Any], bundles: Iterable[Any], active: Iterable[str] = ()) -> Dict[str, Any]:
    """Merge every bundle's ``requires.config`` into the base schema.

    All known bundles contribute keys (so a config section for an inactive bundle still
    validates); ``required = true`` is enforced only for active bundles.
    """
    schema = copy.deepcopy(base)
    active_set = set(active)
    for b in bundles:
        for dotted, entry in sorted((b.requires_config or {}).items()):
            parts = dotted.split(".")
            node = schema
            for i, part in enumerate(parts):
                node.setdefault("type", "object")
                props = node.setdefault("properties", {})
                last = i == len(parts) - 1
                if last:
                    existing = props.get(part, {})
                    merged = dict(existing)
                    merged.update(config_entry_schema(entry, b.name))
                    props[part] = merged
                    if entry.get("required") and b.name in active_set:
                        req = node.setdefault("required", [])
                        if part not in req:
                            req.append(part)
                else:
                    child = props.get(part)
                    if child is None:
                        child = {"type": "object", "additionalProperties": False, "properties": {},
                                 "x-bundle": b.name}
                        props[part] = child
                    node = child
    return schema


def schema_leaf_keys(schema: Dict[str, Any], prefix: str = "") -> Dict[str, Dict[str, Any]]:
    """Every dotted leaf key the schema names explicitly -> its property schema."""
    out: Dict[str, Dict[str, Any]] = {}
    for k, sub in (schema.get("properties") or {}).items():
        key = "%s.%s" % (prefix, k) if prefix else k
        if isinstance(sub, dict) and sub.get("type") == "object" and sub.get("properties"):
            out.update(schema_leaf_keys(sub, key))
        else:
            out[key] = sub if isinstance(sub, dict) else {}
    return out


# ----------------------------------------------------------------- env overrides

_ENV_PREFIX = "HARNESS_"
_TRUE = ("1", "true", "yes", "on")
_FALSE = ("0", "false", "no", "off", "")


def coerce(raw: str, typ: Optional[str], key: str) -> Any:
    if typ == "boolean":
        low = raw.strip().lower()
        if low in _TRUE:
            return True
        if low in _FALSE:
            return False
        raise HarnessError("%s: cannot read %r as a boolean (env override)" % (key, raw))
    if typ == "integer":
        try:
            return int(raw)
        except ValueError:
            raise HarnessError("%s: cannot read %r as an integer (env override)" % (key, raw))
    if typ == "number":
        try:
            return float(raw)
        except ValueError:
            raise HarnessError("%s: cannot read %r as a number (env override)" % (key, raw))
    if typ == "array":
        s = raw.strip()
        if s.startswith("["):
            try:
                return json.loads(s)
            except ValueError:
                raise HarnessError("%s: invalid JSON array in env override" % key)
        return [p.strip() for p in s.split(",") if p.strip()]
    if typ == "object":
        try:
            val = json.loads(raw)
        except ValueError:
            raise HarnessError("%s: env override must be a JSON object" % key)
        if not isinstance(val, dict):
            raise HarnessError("%s: env override must be a JSON object" % key)
        return val
    return raw


def env_overrides(known: Dict[str, Optional[str]], environ: Optional[Dict[str, str]] = None
                  ) -> Tuple[Dict[str, Any], List[str]]:
    """Map ``HARNESS_<SECTION>_<KEY>`` variables onto ``known`` dotted keys.

    ``known`` maps dotted key -> schema type (or None). Returns (overrides, warnings).
    """
    environ = dict(os.environ if environ is None else environ)
    by_env: Dict[str, List[str]] = {}
    for key in known:
        by_env.setdefault(_ENV_PREFIX + key.replace(".", "_").upper(), []).append(key)
    out: Dict[str, Any] = {}
    warnings: List[str] = []
    for name in sorted(environ):
        if not name.startswith(_ENV_PREFIX):
            continue
        keys = by_env.get(name.upper())
        if not keys:
            continue
        if len(keys) > 1:
            raise HarnessError("%s is ambiguous: matches %s" % (name, ", ".join(sorted(keys))))
        key = keys[0]
        out[key] = coerce(environ[name], known[key], key)
    return out, warnings


# ----------------------------------------------------------------- templating of defaults

TEMPLATE_RE = re.compile(r"(?<![$\\])\{\{ ([a-z][a-z0-9_]*(?:\.[A-Za-z0-9_]+)+) \}\}")


def resolve_default_templates(cfg: Dict[str, Any], templated_keys: Iterable[str]) -> None:
    """Resolve ``{{ key }}`` inside string defaults (one pass, against the merged config)."""
    for key in templated_keys:
        val = get_path(cfg, key, None)
        if not isinstance(val, str) or "{{" not in val:
            continue

        def sub(m: "re.Match[str]") -> str:
            ref = get_path(cfg, m.group(1), None)
            return "" if ref is None or isinstance(ref, (dict, list)) else str(ref)

        set_path(cfg, key, TEMPLATE_RE.sub(sub, val))


# ----------------------------------------------------------------- the loaded config


class Layer:
    def __init__(self, name: str, path: Optional[str], data: Dict[str, Any]):
        self.name = name
        self.path = path
        self.data = data


def read_toml_layer(name: str, path: str, required: bool = False) -> Optional[Layer]:
    if not os.path.exists(path):
        if required:
            raise HarnessError("config not found: %s (run `harness init` or `./bootstrap`)" % path)
        return None
    try:
        return Layer(name, path, toml_compat.load_file(path))
    except toml_compat.TOMLDecodeError as exc:
        raise HarnessError("%s: TOML syntax error: %s" % (path, exc))


class Config:
    """The merged configuration plus provenance, schema and diagnostics."""

    def __init__(self, path: str, layers: List[Layer], schema: Dict[str, Any],
                 environ: Optional[Dict[str, str]] = None):
        self.path = path
        self.layers = layers
        self.schema = schema
        self.data: Dict[str, Any] = {}
        self.origin: Dict[str, str] = {}
        for layer in layers:
            self._merge_layer(layer)
        # environment layer
        known: Dict[str, Optional[str]] = {}
        for key, sub in schema_leaf_keys(schema).items():
            known[key] = sub.get("type") if isinstance(sub.get("type"), str) else None
        for key, val in flatten(self.data).items():
            known.setdefault(key, _json_type(val))
        overrides, self.env_warnings = env_overrides(known, environ)
        env_layer: Dict[str, Any] = {}
        for key, val in overrides.items():
            set_path(env_layer, key, val)
        if env_layer:
            self._merge_layer(Layer("env", None, env_layer))
        templated = [k for k, v in flatten(self.data).items() if isinstance(v, str) and "{{" in v]
        resolve_default_templates(self.data, templated)

    def _merge_layer(self, layer: Layer) -> None:
        self.data = deep_merge(self.data, layer.data)
        label = layer.name if not layer.path else "%s (%s)" % (layer.name, layer.path)
        for key in flatten(layer.data):
            self.origin[key] = label
        # a table replaced by a scalar/array (or vice versa) leaves stale origins behind
        for key in list(self.origin):
            if not has_path(self.data, key):
                del self.origin[key]

    # -- access -------------------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        return get_path(self.data, dotted, default)

    def has(self, dotted: str) -> bool:
        return has_path(self.data, dotted)

    # -- validation ---------------------------------------------------------
    def validate(self) -> schema_lite.ValidationResult:
        res = schema_lite.validate(self.schema, self.data)
        res.errors = res.errors + secret_findings(self.data)
        res.warnings = res.warnings + list(self.env_warnings)
        return res

    def explain(self, dotted: str, bundles: Iterable[Any] = ()) -> List[str]:
        sub = schema_lite.subschema_at(self.schema, dotted)
        lines = ["key:         %s" % dotted]
        if sub is None and not self.has(dotted):
            lines.append("status:      unknown key (not in the compiled schema)")
            return lines
        sub = sub or {}
        if sub.get("type"):
            lines.append("type:        %s" % sub["type"])
        if sub.get("description"):
            lines.append("description: %s" % sub["description"])
        if "default" in sub:
            lines.append("default:     %s" % json.dumps(sub["default"]))
        if sub.get("pattern"):
            lines.append("pattern:     %s" % sub["pattern"])
        if sub.get("enum"):
            lines.append("enum:        %s" % ", ".join(str(x) for x in sub["enum"]))
        if sub.get("deprecated"):
            lines.append("deprecated:  yes%s" % (
                ", use %s" % sub["x-replaced-by"] if sub.get("x-replaced-by") else ""))
        users = []
        secrets = []
        for b in bundles:
            if dotted in (b.requires_config or {}):
                users.append(b.name + (" (required)" if b.requires_config[dotted].get("required") else ""))
            for sid, s in sorted((b.requires_secrets or {}).items()):
                if dotted.split(".")[0] == b.name or dotted.split(".")[0] in b.name:
                    secrets.append("%s: %s (written by %s)" % (sid, s.get("where"), s.get("written_by", "?")))
        if users:
            lines.append("bundles:     %s" % ", ".join(users))
        env = _ENV_PREFIX + dotted.replace(".", "_").upper()
        lines.append("env:         %s" % env)
        if self.has(dotted):
            lines.append("value:       %s" % json.dumps(self.get(dotted)))
            lines.append("from:        %s" % self.origin.get(dotted, "(nested table)"))
        else:
            lines.append("value:       (unset)")
        for s in secrets:
            lines.append("secret:      %s" % s)
        return lines


def _json_type(v: Any) -> Optional[str]:
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
    return None


def user_layers(config_path: str, required: bool = True) -> List[Layer]:
    """Layers 2-4 (org overlay, the config file, machine overlay)."""
    org, user = overlay_paths(config_path)
    layers: List[Layer] = []
    for name, path, req in (("org", org, False), ("config", config_path, required), ("user", user, False)):
        layer = read_toml_layer(name, path, required=req)
        if layer:
            layers.append(layer)
    return layers


def bundle_default_layers(bundles: Iterable[Any]) -> List[Layer]:
    """Layers 0-1 for the given (active, ordered) bundles."""
    layers: List[Layer] = []
    for b in bundles:
        doc: Dict[str, Any] = {}
        for dotted, entry in sorted((b.requires_config or {}).items()):
            if "default" in entry:
                set_path(doc, dotted, copy.deepcopy(entry["default"]))
        if doc:
            layers.append(Layer("default:%s" % b.name, None, doc))
    for b in bundles:
        path = os.path.join(b.path, "defaults.toml")
        layer = read_toml_layer("defaults:%s" % b.name, path)
        if layer:
            layers.append(layer)
    return layers


# ----------------------------------------------------------------- editing (set / migrate)

_SECTION_RE = re.compile(r"^\s*\[\s*([^\[\]]+?)\s*\]\s*(#.*)?$")
_ARRAY_SECTION_RE = re.compile(r"^\s*\[\[")


def _key_line_re(key: str) -> "re.Pattern[str]":
    return re.compile(r"^(\s*)(%s|\"%s\")\s*=" % (re.escape(key), re.escape(key)))


def set_in_text(text: str, dotted: str, value: Any) -> str:
    """Line-edit ``dotted = value`` into TOML text, preserving comments.

    Handles scalars and simple arrays. The key goes into its ``[section]`` (the longest
    existing table prefix); a missing section is appended. Raises for keys inside arrays of
    tables or inline tables ("edit the file").
    """
    rendered = toml_compat.dump_value(value)
    if "\n" in rendered:
        raise HarnessError("%s: complex values cannot be set from the CLI; edit the file" % dotted)
    parts = dotted.split(".")
    lines = text.splitlines()
    # collect section headers
    sections: List[Tuple[int, str]] = [(-1, "")]
    for i, line in enumerate(lines):
        if _ARRAY_SECTION_RE.match(line):
            sections.append((i, "\0array"))
            continue
        m = _SECTION_RE.match(line)
        if m:
            name = ".".join(p.strip().strip('"') for p in m.group(1).split("."))
            sections.append((i, name))
    # choose the longest section that prefixes the key
    best: Optional[Tuple[int, str]] = None
    for start, name in sections:
        if name == "\0array":
            continue
        if name == "" or dotted.startswith(name + "."):
            if best is None or len(name) > len(best[1]):
                best = (start, name)
    assert best is not None
    start, name = best
    rel = dotted[len(name) + 1:] if name else dotted
    # section body range
    end = len(lines)
    for s, _n in sections:
        if s > start:
            end = s
            break
    key_re = _key_line_re(rel)
    for i in range(start + 1, end):
        m = key_re.match(lines[i])
        if m:
            comment = ""
            cm = re.search(r"\s+#.*$", lines[i])
            if cm and lines[i].count('"') % 2 == 0:
                comment = cm.group(0)
            lines[i] = "%s%s = %s%s" % (m.group(1), rel, rendered, comment)
            return "\n".join(lines) + "\n"
    if name == "" and "." in rel:
        # no section yet: append a new one
        sec, leaf = ".".join(parts[:-1]), parts[-1]
        out = list(lines)
        if out and out[-1].strip():
            out.append("")
        out.append("[%s]" % sec)
        out.append("%s = %s" % (leaf, rendered))
        return "\n".join(out) + "\n"
    insert_at = end
    while insert_at > start + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, "%s = %s" % (rel, rendered))
    return "\n".join(lines) + "\n"


def remove_in_text(text: str, dotted: str) -> Tuple[str, Optional[str]]:
    """Remove ``dotted = …`` (single-line values only); return (new text, raw value text)."""
    lines = text.splitlines()
    section = ""
    for i, line in enumerate(lines):
        if _ARRAY_SECTION_RE.match(line):
            section = "\0array"
            continue
        m = _SECTION_RE.match(line)
        if m:
            section = ".".join(p.strip().strip('"') for p in m.group(1).split("."))
            continue
        if section == "\0array":
            continue
        rel = dotted[len(section) + 1:] if section and dotted.startswith(section + ".") else (
            dotted if not section else None)
        if rel is None:
            continue
        km = _key_line_re(rel).match(line)
        if km:
            raw = line[km.end():].strip()
            del lines[i]
            return "\n".join(lines) + "\n", raw
    return text, None


def rename_section_in_text(text: str, old: str, new: str) -> str:
    out = []
    for line in text.splitlines():
        m = _SECTION_RE.match(line)
        if m:
            name = m.group(1).strip()
            if name == old or name.startswith(old + "."):
                line = line.replace("[" + name, "[" + new + name[len(old):], 1)
        out.append(line)
    return "\n".join(out) + "\n"


def deprecations(schema: Dict[str, Any]) -> List[Tuple[str, str]]:
    """(old dotted key, replacement) pairs declared with deprecated + x-replaced-by."""
    out: List[Tuple[str, str]] = []

    def walk(node: Dict[str, Any], prefix: str) -> None:
        for k, sub in (node.get("properties") or {}).items():
            key = "%s.%s" % (prefix, k) if prefix else k
            if isinstance(sub, dict):
                if sub.get("deprecated") and sub.get("x-replaced-by"):
                    out.append((key, sub["x-replaced-by"]))
                walk(sub, key)

    walk(schema, "")
    return out


def migrate_text(text: str, schema: Dict[str, Any]) -> Tuple[str, List[str]]:
    """Apply rename-only migrations for deprecated keys present in ``text``."""
    data = toml_compat.loads(text) if text.strip() else {}
    notes: List[str] = []
    for old, new in deprecations(schema):
        if not has_path(data, old):
            continue
        val = get_path(data, old)
        if isinstance(val, dict):
            if has_path(data, new):
                notes.append("[%s] and [%s] both exist; merge them by hand" % (old, new))
                continue
            text = rename_section_in_text(text, old, new)
            notes.append("renamed [%s] -> [%s]" % (old, new))
        else:
            text, raw = remove_in_text(text, old)
            if raw is None:
                notes.append("could not migrate %s automatically (multi-line value); edit the file" % old)
                continue
            text = set_in_text(text, new, val)
            notes.append("moved %s -> %s" % (old, new))
        data = toml_compat.loads(text)
    return text, notes


def read_config_text(path: str) -> str:
    text = read_text(path)
    if text is None:
        raise HarnessError("config not found: %s" % path)
    return text


def flatten_to_nested(flat: Dict[str, Any]) -> Dict[str, Any]:
    """``{"a.b": 1}`` -> ``{"a": {"b": 1}}``."""
    out: Dict[str, Any] = {}
    for k, v in flat.items():
        set_path(out, k, v)
    return out
