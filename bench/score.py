"""Run combfind init against the fixture and score it.

Two modes:
  --mode=cold         fresh DB, full init from scratch
  --mode=incremental  warmed DB, apply canonical edit, time the second init

Correctness gate (binary; failure aborts before any timing is reported):
  1. Fixture manifest matches bench/fixture.manifest (no tampering).
  2. parse_symbols.tsv byte-equal to the appropriate golden.
  3. index_refs.tsv byte-equal to the appropriate golden.

On pass: prints JSON to stdout with elapsed_seconds and counts; exit 0.
On fail: prints diagnostic to stderr; exits with a code identifying the
failure mode so the runner can distinguish bugs from regressions.

Exit codes:
  0  OK
  2  fixture tampered
  3  parse_symbols mismatch
  4  index_refs mismatch
  5  pipeline crashed
  6  invalid usage
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from bench._manifest import FIXTURE_DIR, verify
from bench.capture import (
    INDEX_REFS_COLD,
    INDEX_REFS_INCR,
    PARSE_SYMBOLS_COLD,
    PARSE_SYMBOLS_INCR,
    dump_index_refs,
    dump_parse_symbols,
    init_pipeline,
    reinit_pipeline,
)
from bench.incremental_edit import apply_canonical_edit


def _diff_summary(expected: str, actual: str, label: str) -> str:
    exp_lines = expected.splitlines()
    act_lines = actual.splitlines()
    exp_set = set(exp_lines)
    act_set = set(act_lines)
    missing = exp_set - act_set
    extra = act_set - exp_set
    parts = [f"{label} mismatch:"]
    if missing:
        parts.append(f"  missing {len(missing)} row(s) (expected but absent):")
        for line in sorted(missing)[:5]:
            parts.append(f"    - {line}")
        if len(missing) > 5:
            parts.append(f"    (+ {len(missing) - 5} more)")
    if extra:
        parts.append(f"  extra {len(extra)} row(s) (present but unexpected):")
        for line in sorted(extra)[:5]:
            parts.append(f"    + {line}")
        if len(extra) > 5:
            parts.append(f"    (+ {len(extra) - 5} more)")
    return "\n".join(parts)


def _score_cold() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "bench.db")
        t0 = time.perf_counter()
        try:
            init_pipeline(db_path, str(FIXTURE_DIR))
        except Exception as exc:
            print(f"pipeline crashed: {exc}", file=sys.stderr)
            sys.exit(5)
        elapsed = time.perf_counter() - t0
        parse_dump = dump_parse_symbols(db_path)
        index_dump = dump_index_refs(db_path)

    expected_parse = PARSE_SYMBOLS_COLD.read_text()
    expected_index = INDEX_REFS_COLD.read_text()
    if parse_dump != expected_parse:
        print(
            _diff_summary(expected_parse, parse_dump, "parse_symbols"), file=sys.stderr
        )
        sys.exit(3)
    if index_dump != expected_index:
        print(_diff_summary(expected_index, index_dump, "index_refs"), file=sys.stderr)
        sys.exit(4)
    return {
        "status": "OK",
        "mode": "cold",
        "elapsed_seconds": elapsed,
        "parse_rows": len(parse_dump.splitlines()),
        "index_rows": len(index_dump.splitlines()),
    }


def _score_incremental() -> dict:
    with tempfile.TemporaryDirectory() as tmp:
        repo_copy = Path(tmp) / "fixture"
        shutil.copytree(FIXTURE_DIR, repo_copy)
        db_path = os.path.join(tmp, "bench.db")
        # Warmup: full init on the unmodified copy. Untimed.
        try:
            init_pipeline(db_path, str(repo_copy))
        except Exception as exc:
            print(f"warmup pipeline crashed: {exc}", file=sys.stderr)
            sys.exit(5)
        # Apply canonical edit and time the re-init.
        apply_canonical_edit(repo_copy)
        t0 = time.perf_counter()
        try:
            reinit_pipeline(db_path, str(repo_copy))
        except Exception as exc:
            print(f"pipeline crashed: {exc}", file=sys.stderr)
            sys.exit(5)
        elapsed = time.perf_counter() - t0
        parse_dump = dump_parse_symbols(db_path)
        index_dump = dump_index_refs(db_path)

    expected_parse = PARSE_SYMBOLS_INCR.read_text()
    expected_index = INDEX_REFS_INCR.read_text()
    if parse_dump != expected_parse:
        print(
            _diff_summary(expected_parse, parse_dump, "parse_symbols"), file=sys.stderr
        )
        sys.exit(3)
    if index_dump != expected_index:
        print(_diff_summary(expected_index, index_dump, "index_refs"), file=sys.stderr)
        sys.exit(4)
    return {
        "status": "OK",
        "mode": "incremental",
        "elapsed_seconds": elapsed,
        "parse_rows": len(parse_dump.splitlines()),
        "index_rows": len(index_dump.splitlines()),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score one combfind init run.")
    parser.add_argument(
        "--mode",
        choices=["cold", "incremental"],
        default="cold",
        help="cold: fresh DB; incremental: warmed DB + canonical edit",
    )
    args = parser.parse_args(argv)

    try:
        verify()
    except SystemExit as exc:
        # _manifest.verify() raises SystemExit(<msg>) on tampering; re-emit as code 2.
        print(str(exc), file=sys.stderr)
        return 2

    if args.mode == "cold":
        result = _score_cold()
    else:
        result = _score_incremental()

    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
