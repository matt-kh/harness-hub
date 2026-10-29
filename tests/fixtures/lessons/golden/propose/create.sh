#!/bin/sh
# Written by `harness lessons propose scm-001`; the harness never runs it.
# Read preview.md first, then run it yourself: sh create.sh
set -eu
cd "$(dirname "$0")"
gh issue create -R octocat/hub -t 'Lesson scm-001: pushing a branch named after the ticket' -F body.md -l 'agent-drafted'
