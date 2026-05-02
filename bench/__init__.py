"""Autoresearch harness for combfind init speed.

Importing this package silences combfind's telemetry so bench scripts can
emit clean JSON on stdout without combfind log lines mixing in. Bench
diagnostics go to stderr.
"""

from __future__ import annotations

import os

os.environ.setdefault("COMBFIND_LOG_LEVEL", "error")

from combfind import telemetry  # noqa: E402

telemetry.set_handlers([])
