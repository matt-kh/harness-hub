"""JSON-backed PyYAML stand-in: pins the structured (PyYAML) branch of the work-ticket
preflights whatever the host has installed. JSON is YAML flow style, so the fixture CI files
under fixtures/repos/*-yaml are written as JSON; anything else fails to load, exactly like a
file PyYAML cannot parse. Only the surface the preflights use exists: SafeLoader,
add_multi_constructor and load(stream, Loader=...)."""
import json


class SafeLoader(object):
    constructors = {}

    @classmethod
    def add_multi_constructor(cls, tag, fn):
        cls.constructors = dict(cls.constructors, **{tag: fn})


def load(stream, Loader=SafeLoader):
    return json.loads(stream.read() if hasattr(stream, "read") else stream)
