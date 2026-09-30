"""schema_lite against hand-made schemas, the three repo schemas and every fixture manifest."""
from __future__ import annotations

import glob
import json
import os
import unittest

from helpers import FIXTURES, REPO  # noqa: E402

from harness import schema_lite as SL
from harness import toml_compat


def load(name):
    with open(os.path.join(REPO, "schema", name), encoding="utf-8") as fh:
        return json.load(fh)


class ValidatorTest(unittest.TestCase):
    SCHEMA = {
        "type": "object", "additionalProperties": False, "required": ["a"],
        "$defs": {"port": {"type": "integer", "minimum": 1, "maximum": 65535}},
        "properties": {
            "a": {"type": "string", "pattern": "^x"},
            "b": {"type": "array", "items": {"enum": ["p", "q"]}, "minItems": 1, "uniqueItems": True},
            "c": {"$ref": "#/$defs/port"},
            "d": {"oneOf": [{"type": "string"}, {"type": "integer"}]},
            "e": {"anyOf": [{"const": 1}, {"const": 2}]},
            "f": {"allOf": [{"type": "number"}, {"minimum": 0}]},
            "g": {"type": "string", "deprecated": True, "x-replaced-by": "a"},
            "h": {"type": "object", "additionalProperties": {"type": "boolean"}},
            "i": {"type": "object", "propertyNames": {"pattern": "^[A-Z]+$"}},
        },
    }

    def v(self, inst):
        return SL.validate(self.SCHEMA, inst)

    def test_ok(self):
        r = self.v({"a": "xy", "b": ["p"], "c": 80, "d": 3, "e": 2, "f": 1.5, "h": {"k": True}, "i": {"AB": 1}})
        self.assertEqual(r.errors, [])

    def test_errors_are_pathed(self):
        r = self.v({"b": ["p", "p", "z"], "c": 0, "d": [], "e": 3, "f": -1, "h": {"k": 1}, "zz": 1, "i": {"ab": 1}})
        e = "\n".join(r.errors)
        for needle in ("a: is required", "b[1]: duplicate item 'p'", "b[2]: must be one of", "c: must be >= 1",
                       "d: does not match any allowed form", "e: does not match any allowed form",
                       "f: must be >= 0", "h.k: expected boolean, got integer", "zz: unknown key", "i.ab: invalid key name"):
            self.assertIn(needle, e)

    def test_type_and_pattern(self):
        self.assertIn("a: expected string, got integer", self.v({"a": 1}).errors)
        self.assertIn("a: does not match ^x", self.v({"a": "y"}).errors)
        self.assertIn("(root): expected object, got array", self.v([]).errors)

    def test_deprecated_warns(self):
        r = self.v({"a": "x", "g": "old"})
        self.assertEqual(r.errors, [])
        self.assertEqual(r.warnings, ["g: is deprecated; use a"])

    def test_booleans_are_not_integers(self):
        self.assertIn("c: expected integer, got boolean", self.v({"a": "x", "c": True}).errors)

    def test_subschema_at(self):
        s = load("harness-config.schema.json")
        self.assertEqual(SL.subschema_at(s, "jira.url")["pattern"], "^https?://")
        self.assertIsNotNone(SL.subschema_at(s, "providers.gemini.ask_as"))
        self.assertIsNone(SL.subschema_at(s, "jira.nope"))


class RepoSchemasTest(unittest.TestCase):
    def test_schemas_parse(self):
        for name in ("harness-config.schema.json", "bundle.schema.json", "provider.schema.json"):
            self.assertEqual(load(name)["$schema"], "https://json-schema.org/draft/2020-12/schema")

    def test_design_example_manifests_validate(self):
        schema = load("bundle.schema.json")
        for path in sorted(glob.glob(os.path.join(FIXTURES, "manifests", "*.bundle.toml"))):
            r = SL.validate(schema, toml_compat.load_file(path))
            self.assertEqual(r.errors, [], path)
            self.assertIn("provides.hook_rules: is deprecated; use provides.guard_rules", r.warnings)

    def test_fixture_bundles_validate(self):
        schema = load("bundle.schema.json")
        for path in sorted(glob.glob(os.path.join(FIXTURES, "bundles", "*", "bundle.toml"))):
            self.assertEqual(SL.validate(schema, toml_compat.load_file(path)).errors, [], path)

    def test_bundle_schema_rejects(self):
        schema = load("bundle.schema.json")
        bad = {"bundle": {"name": "Bad Name", "summary": "x"},
               "doctor_checks": [{"id": "c", "severity": "sometimes"}],
               "manual_steps": [{"id": "s", "title": "t"}]}
        e = "\n".join(SL.validate(schema, bad).errors)
        self.assertIn("bundle.name: does not match", e)
        self.assertIn("doctor_checks[0].severity: must be one of", e)
        self.assertIn("doctor_checks[0]: does not match any allowed form", e)  # neither cmd nor script
        self.assertIn("manual_steps[0].how: is required", e)

    def test_providers_validate(self):
        schema = load("provider.schema.json")
        for path in sorted(glob.glob(os.path.join(REPO, "providers", "*", "provider.toml"))):
            self.assertEqual(SL.validate(schema, toml_compat.load_file(path)).errors, [], path)

    def test_config_fixtures_validate_against_base(self):
        schema = load("harness-config.schema.json")
        for name in ("harness.ci.toml",):
            r = SL.validate(schema, toml_compat.load_file(os.path.join(FIXTURES, name)))
            self.assertEqual(r.errors, [], name)


class TomlCompatTest(unittest.TestCase):
    def test_round_trip_values(self):
        doc = {"s": 'a "q" \\ \n', "i": 3, "f": 1.5, "b": True, "a": [1, "x"], "t": {"k": "v", "n": {"m": 1}}}
        text = "\n".join("%s = %s" % (k, toml_compat.dump_value(v)) for k, v in doc.items())
        self.assertEqual(toml_compat.loads(text), doc)

    def test_table_dump(self):
        text = toml_compat.dump_table("mcp_servers.my-server", {"command": "x", "args": ["-c"]})
        self.assertEqual(toml_compat.loads(text), {"mcp_servers": {"my-server": {"command": "x", "args": ["-c"]}}})


if __name__ == "__main__":
    unittest.main()
