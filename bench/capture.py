"""Seed bench/golden/ from a fresh combfind run on the fixture.

Re-run this only when intentionally rebaselining (e.g., the parse walker
changes a docstring extraction rule and we accept the new output).

Outputs:
  bench/golden/parse_symbols.tsv  — file,qualified_name,signature,kind,content_hash
  bench/golden/index_refs.tsv     — src_qname,dst_qname,kind

Both are sorted, deterministic, and intended for byte-equal comparison.
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from bench._manifest import FIXTURE_DIR, verify
from combfind.db import create_schema, get_connection
from combfind.pipeline.run import run as pipeline_run

GOLDEN_DIR = Path(__file__).parent / "golden"
PARSE_SYMBOLS = GOLDEN_DIR / "parse_symbols.tsv"
INDEX_REFS = GOLDEN_DIR / "index_refs.tsv"


def _dump_parse_symbols(db_path: str) -> str:
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


def _dump_index_refs(db_path: str) -> str:
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


def run_pipeline_against_fixture(db_path: str) -> None:
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()
    pipeline_run(
        db_path,
        stages=["parse", "index"],
        repo_path=str(FIXTURE_DIR),
    )


def capture_to(target_dir: Path) -> tuple[str, str]:
    """Run pipeline in a temp DB, return (parse_dump, index_dump)."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "bench.db")
        run_pipeline_against_fixture(db_path)
        parse_dump = _dump_parse_symbols(db_path)
        index_dump = _dump_index_refs(db_path)
    return parse_dump, index_dump


def main() -> int:
    verify()
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)

    parse_dump, index_dump = capture_to(GOLDEN_DIR)
    PARSE_SYMBOLS.write_text(parse_dump)
    INDEX_REFS.write_text(index_dump)

    print(f"wrote {PARSE_SYMBOLS} ({len(parse_dump.splitlines())} rows)")
    print(f"wrote {INDEX_REFS} ({len(index_dump.splitlines())} rows)")

    # Idempotency check: a second capture should produce identical bytes.
    parse_dump_2, index_dump_2 = capture_to(GOLDEN_DIR)
    if parse_dump != parse_dump_2 or index_dump != index_dump_2:
        print(
            "WARNING: capture is not deterministic — two consecutive runs differ. "
            "The scorer will be flaky. Investigate before relying on byte-equal gates.",
            file=sys.stderr,
        )
        return 1
    print("idempotency check: OK (two captures byte-identical)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
