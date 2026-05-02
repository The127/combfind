import bisect
import os
import subprocess
import tempfile
from abc import ABC, abstractmethod
from typing import Callable

from combfind import telemetry


class BaseIndexer(ABC):
    @abstractmethod
    def run(self, conn, *, repo_path: str | None = None) -> int:
        """Extract references and insert into the references table. Returns count inserted."""
        ...


def get_indexer(language: str) -> BaseIndexer | None:
    from combfind.pipeline.indexers.go import GoIndexer
    from combfind.pipeline.indexers.java import JavaIndexer
    from combfind.pipeline.indexers.python import PythonIndexer

    _registry: dict[str, type[BaseIndexer]] = {
        "python": PythonIndexer,
        "go": GoIndexer,
        "java": JavaIndexer,
    }
    cls = _registry.get(language)
    return cls() if cls else None


# ---------------------------------------------------------------------------
# Shared SCIP utilities
# ---------------------------------------------------------------------------


def run_scip_binary(args: list[str], repo_path: str) -> bytes | None:
    fd, tmp = tempfile.mkstemp(suffix=".scip")
    os.close(fd)
    try:
        result = subprocess.run(
            args + [tmp],
            cwd=repo_path,
            capture_output=True,
        )
        if result.returncode != 0:
            telemetry.warning(
                "scip binary failed",
                cmd=args[0],
                stderr=result.stderr.decode(errors="replace")[:500],
            )
            return None
        with open(tmp, "rb") as f:
            return f.read()
    finally:
        os.unlink(tmp)


def parse_scip_index(raw: bytes):
    try:
        from combfind import scip_pb2

        index = scip_pb2.Index()
        index.ParseFromString(raw)
        return index
    except Exception as exc:
        telemetry.warning("failed to parse SCIP index", reason=str(exc))
        return None


def extract_scip_refs(
    conn,
    index,
    lang: str,
    symbol_to_qname: Callable[[str], str | None],
) -> int:
    _DEFINITION_ROLE = 0x1
    _IMPORT_ROLE = 0x2

    file_syms: dict[str, list[tuple[int, int, int]]] = {}
    for row in conn.execute(
        "SELECT s.id, s.start_line, s.end_line, f.path "
        "FROM symbols s JOIN files f ON f.id = s.file_id "
        "WHERE f.language = ?",
        (lang,),
    ).fetchall():
        file_syms.setdefault(row["path"], []).append(
            (row["start_line"], row["end_line"], row["id"])
        )
    for v in file_syms.values():
        v.sort()

    by_qname: dict[str, int] = {}
    for row in conn.execute(
        "SELECT s.id, s.qualified_name "
        "FROM symbols s JOIN files f ON f.id = s.file_id "
        "WHERE f.language = ? AND s.qualified_name IS NOT NULL",
        (lang,),
    ).fetchall():
        by_qname[row["qualified_name"]] = row["id"]

    inserted = 0
    for doc in index.documents:
        syms = file_syms.get(doc.relative_path)
        if not syms:
            continue
        starts = [s[0] for s in syms]

        for occ in doc.occurrences:
            if not occ.symbol or occ.symbol.startswith("local "):
                continue
            if occ.symbol_roles & _DEFINITION_ROLE:
                continue
            if not occ.range:
                continue

            line_1 = occ.range[0] + 1
            src_id = containing_symbol(syms, starts, line_1)
            if src_id is None:
                continue

            qname = symbol_to_qname(occ.symbol)
            if qname is None:
                continue
            dst_id = by_qname.get(qname)
            if dst_id is None or dst_id == src_id:
                continue

            kind = "import" if (occ.symbol_roles & _IMPORT_ROLE) else "call"
            conn.execute(
                'INSERT OR IGNORE INTO "references"'
                "(src_symbol_id, dst_symbol_id, kind) VALUES (?,?,?)",
                (src_id, dst_id, kind),
            )
            inserted += 1

    return inserted


def containing_symbol(
    syms: list[tuple[int, int, int]],
    starts: list[int],
    line_1: int,
) -> int | None:
    idx = bisect.bisect_right(starts, line_1) - 1
    result = None
    for i in range(idx, -1, -1):
        start, end, sym_id = syms[i]
        if start > line_1:
            continue
        if end >= line_1:
            if result is None or start > result[0]:
                result = (start, end, sym_id)
        else:
            break
    return result[2] if result else None
