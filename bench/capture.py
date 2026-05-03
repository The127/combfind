"""Seed bench/golden/ from fresh combfind runs on the fixture.

Re-run this only when intentionally rebaselining (e.g., the parse walker
changes a docstring extraction rule and we accept the new output).

Outputs:
  bench/golden/parse_symbols.tsv             — cold-mode parse output
  bench/golden/index_refs.tsv                — cold-mode index output
  bench/golden/parse_symbols.incremental.tsv — after canonical edit
  bench/golden/index_refs.incremental.tsv    — after canonical edit

All four files are sorted and deterministic, intended for byte-equal
comparison by score.py.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

from bench._manifest import FIXTURE_DIR, verify
from bench.incremental_edit import apply_canonical_edit
from combfind.db import create_schema, get_connection
from combfind.pipeline.run import run as pipeline_run

GOLDEN_DIR = Path(__file__).parent / "golden"
PARSE_SYMBOLS_COLD = GOLDEN_DIR / "parse_symbols.tsv"
INDEX_REFS_COLD = GOLDEN_DIR / "index_refs.tsv"
PARSE_SYMBOLS_INCR = GOLDEN_DIR / "parse_symbols.incremental.tsv"
INDEX_REFS_INCR = GOLDEN_DIR / "index_refs.incremental.tsv"


def dump_parse_symbols(db_path: str) -> str:
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT f.path, s.qualified_name, s.signature, s.kind, s.content_hash
           FROM symbols s
           JOIN files f ON f.id = s.file_id"""
    ).fetchall()
    conn.close()
    tuples = sorted(
        (
            r["path"] or "",
            r["qualified_name"] or "",
            r["signature"] or "",
            r["kind"] or "",
            r["content_hash"] or "",
        )
        for r in rows
    )
    return "\n".join("\t".join(t) for t in tuples) + "\n"


def dump_index_refs(db_path: str) -> str:
    conn = get_connection(db_path)
    rows = conn.execute(
        """SELECT s1.qualified_name AS src, s2.qualified_name AS dst, r.kind
           FROM "references" r
           JOIN symbols s1 ON s1.id = r.src_symbol_id
           JOIN symbols s2 ON s2.id = r.dst_symbol_id"""
    ).fetchall()
    conn.close()
    tuples = sorted((r["src"] or "", r["dst"] or "", r["kind"] or "") for r in rows)
    return "\n".join("\t".join(t) for t in tuples) + "\n"


def init_pipeline(db_path: str, repo_path: str) -> None:
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()
    pipeline_run(db_path, stages=["parse", "index"], repo_path=repo_path)


def reinit_pipeline(db_path: str, repo_path: str) -> None:
    """Run init against an existing DB (incremental path)."""
    pipeline_run(db_path, stages=["parse", "index"], repo_path=repo_path)


def capture_cold() -> tuple[str, str]:
    """Run pipeline against the pristine fixture, return (parse, index) dumps."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "bench.db")
        init_pipeline(db_path, str(FIXTURE_DIR))
        return dump_parse_symbols(db_path), dump_index_refs(db_path)


def capture_incremental() -> tuple[str, str]:
    """Run pipeline twice on a copy of the fixture: first cold, then post-edit.

    Returns the (parse, index) dumps from after the canonical edit was
    applied — i.e., the expected post-edit state of the index.
    """
    with tempfile.TemporaryDirectory() as tmp:
        repo_copy = Path(tmp) / "fixture"
        shutil.copytree(FIXTURE_DIR, repo_copy)
        db_path = os.path.join(tmp, "bench.db")
        # Warmup cold run.
        init_pipeline(db_path, str(repo_copy))
        # Apply the canonical edit and re-init.
        apply_canonical_edit(repo_copy)
        reinit_pipeline(db_path, str(repo_copy))
        return dump_parse_symbols(db_path), dump_index_refs(db_path)


def main() -> int:
    verify()
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    parse_cold, index_cold = capture_cold()
    PARSE_SYMBOLS_COLD.write_text(parse_cold)
    INDEX_REFS_COLD.write_text(index_cold)
    print(f"wrote {PARSE_SYMBOLS_COLD} ({len(parse_cold.splitlines())} rows)")
    print(f"wrote {INDEX_REFS_COLD} ({len(index_cold.splitlines())} rows)")

    parse_incr, index_incr = capture_incremental()
    PARSE_SYMBOLS_INCR.write_text(parse_incr)
    INDEX_REFS_INCR.write_text(index_incr)
    print(f"wrote {PARSE_SYMBOLS_INCR} ({len(parse_incr.splitlines())} rows)")
    print(f"wrote {INDEX_REFS_INCR} ({len(index_incr.splitlines())} rows)")

    # Idempotency: each capture must be byte-identical across two consecutive
    # runs, otherwise the byte-equal gate downstream is flaky.
    parse_cold_2, index_cold_2 = capture_cold()
    parse_incr_2, index_incr_2 = capture_incremental()
    if (
        parse_cold != parse_cold_2
        or index_cold != index_cold_2
        or parse_incr != parse_incr_2
        or index_incr != index_incr_2
    ):
        print(
            "WARNING: capture is not deterministic — two consecutive runs differ. "
            "The scorer will be flaky. Investigate before relying on byte-equal gates.",
            file=sys.stderr,
        )
        return 1
    print("idempotency check: OK (cold and incremental captures both byte-stable)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
