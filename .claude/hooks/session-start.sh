#!/bin/bash
# SessionStart (cloud sessions only): install the Backlog.md CLI when it is missing, so the
# project's task workflow (CLAUDE.md: Backlog.md) works in a fresh container. Idempotent: a
# session that already has `backlog` (a resumed one, or a cached container) skips the install.
# It never blocks a session: without npm, or when the install fails, it says so and carries on.
set -euo pipefail

if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0  # on your own machine, install it yourself: npm install -g backlog.md
fi

if command -v backlog >/dev/null 2>&1; then
  exit 0
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "session-start: npm is not installed, so the Backlog.md CLI (backlog) was not installed" >&2
  exit 0
fi

if npm install --global --no-fund --no-audit --loglevel=error backlog.md >&2; then
  echo "session-start: installed the Backlog.md CLI: $(backlog --version 2>/dev/null)" >&2
else
  echo "session-start: npm could not install backlog.md; install it by hand: npm install -g backlog.md" >&2
fi
exit 0
