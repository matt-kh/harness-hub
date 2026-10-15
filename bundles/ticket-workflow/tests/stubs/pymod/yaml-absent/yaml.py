"""PyYAML stand-in that is never importable: pins the grep fallback of the work-ticket
preflights (`python3 -c 'import yaml'` fails) whatever the host has installed."""
raise ImportError("yaml: absent by test fixture (PYTHONPATH pymod/yaml-absent)")
