import importlib
import re
import shutil
from pathlib import Path

from combfind import telemetry
from combfind.pipeline.indexers import (
    BaseIndexer,
    extract_scip_refs,
    parse_scip_index,
    run_scip_binary,
)


class JavaIndexer(BaseIndexer):
    def run(self, conn, *, repo_path: str | None = None) -> int:
        inserted = _inherit(conn)
        if not repo_path:
            return inserted
        if not conn.execute(
            "SELECT 1 FROM files WHERE language = 'java' LIMIT 1"
        ).fetchone():
            return inserted
        if shutil.which("scip-java"):
            inserted += self._run_scip(conn, repo_path)
        else:
            telemetry.warning("scip-java not found, falling back to tree-sitter imports")
            inserted += self._run_treesitter(conn, repo_path)
        return inserted

    def _run_scip(self, conn, repo_path: str) -> int:
        raw = run_scip_binary(["scip-java", "index", "--output"], repo_path)
        if raw is None:
            return 0
        index = parse_scip_index(raw)
        if index is None:
            return 0
        return extract_scip_refs(conn, index, "java", _scip_symbol_to_qname)

    def _run_treesitter(self, conn, repo_path: str) -> int:
        try:
            mod = importlib.import_module("tree_sitter_java")
            from tree_sitter import Language, Parser

            lang = Language(mod.language())
            parser = Parser(lang)
        except Exception:
            return 0

        by_qname: dict[str, int] = {}
        by_name: dict[str, list[int]] = {}
        for row in conn.execute(
            "SELECT s.id, s.name, s.qualified_name "
            "FROM symbols s JOIN files f ON f.id = s.file_id "
            "WHERE f.language = 'java'"
        ).fetchall():
            if row["qualified_name"]:
                by_qname[row["qualified_name"]] = row["id"]
            by_name.setdefault(row["name"], []).append(row["id"])

        first_sym: dict[str, int] = {}
        for row in conn.execute(
            "SELECT s.id, f.path "
            "FROM symbols s JOIN files f ON f.id = s.file_id "
            "WHERE f.language = 'java' "
            "ORDER BY f.path, s.start_line"
        ).fetchall():
            first_sym.setdefault(row["path"], row["id"])

        inserted = 0
        repo = Path(repo_path)

        for rel_path, src_id in first_sym.items():
            full_path = repo / rel_path
            try:
                content = full_path.read_bytes()
            except OSError:
                continue

            tree = parser.parse(content)
            for import_name in _walk_imports(tree.root_node):
                dst_id = _resolve(import_name, by_qname, by_name)
                if dst_id is None or dst_id == src_id:
                    continue
                conn.execute(
                    'INSERT OR IGNORE INTO "references"'
                    "(src_symbol_id, dst_symbol_id, kind) VALUES (?,?,?)",
                    (src_id, dst_id, "import"),
                )
                inserted += 1

        return inserted


# ---------------------------------------------------------------------------
# SCIP symbol parsing
# ---------------------------------------------------------------------------


def _scip_symbol_to_qname(symbol: str) -> str | None:
    """
    scip-java format: 'scip-java java <pkg> <ver> com/example/Foo#method().'
    Convert to dotted qualified name: 'com.example.Foo.method'
    """
    if symbol.startswith("local "):
        return None
    parts = symbol.split(" ", 4)
    if len(parts) < 5:
        return None
    desc = parts[4].rstrip(".")
    paren = desc.find("(")
    if paren >= 0:
        desc = desc[:paren]
    if not desc:
        return None
    return desc.replace("/", ".").replace("#", ".").rstrip(".")


# ---------------------------------------------------------------------------
# Inheritance (always runs)
# ---------------------------------------------------------------------------


def _inherit(conn) -> int:
    by_qname: dict[str, int] = {}
    by_name: dict[str, list[int]] = {}
    for row in conn.execute(
        "SELECT s.id, s.name, s.qualified_name "
        "FROM symbols s JOIN files f ON f.id = s.file_id "
        "WHERE f.language = 'java'"
    ).fetchall():
        by_name.setdefault(row["name"], []).append(row["id"])
        if row["qualified_name"]:
            by_qname[row["qualified_name"]] = row["id"]

    inserted = 0
    for sym in conn.execute(
        "SELECT s.id, s.signature "
        "FROM symbols s JOIN files f ON f.id = s.file_id "
        "WHERE f.language = 'java' AND s.kind IN ('class', 'interface')"
    ).fetchall():
        src_id = sym["id"]
        for base_name in _parse_supertypes(sym["signature"]):
            dst_id = by_qname.get(base_name) or _sole(by_name.get(base_name, []), exclude=src_id)
            if dst_id and dst_id != src_id:
                conn.execute(
                    'INSERT OR IGNORE INTO "references"'
                    "(src_symbol_id, dst_symbol_id, kind) VALUES (?,?,?)",
                    (src_id, dst_id, "inherit"),
                )
                inserted += 1
    return inserted


def _parse_supertypes(signature: str | None) -> list[str]:
    if not signature:
        return []
    names = []
    for kw in ("extends", "implements"):
        m = re.search(rf"\b{kw}\s+([\w,\s<>]+)", signature)
        if not m:
            continue
        raw = m.group(1)
        for stop in ("extends", "implements"):
            if stop != kw:
                idx = raw.find(stop)
                if idx >= 0:
                    raw = raw[:idx]
        for part in raw.split(","):
            name = re.split(r"[<\s]", part.strip())[0]
            if name:
                names.append(name)
    return names


def _sole(candidates: list[int], *, exclude: int) -> int | None:
    filtered = [i for i in candidates if i != exclude]
    return filtered[0] if len(filtered) == 1 else None


# ---------------------------------------------------------------------------
# Tree-sitter import extraction
# ---------------------------------------------------------------------------


def _walk_imports(root) -> list[str]:
    """Return dotted class names from import_declaration nodes."""
    results = []
    for node in root.named_children:
        if node.type != "import_declaration":
            continue
        for child in node.named_children:
            if child.type in ("scoped_identifier", "identifier"):
                results.append(child.text.decode("utf-8"))
    return results


def _resolve(
    qname: str,
    by_qname: dict[str, int],
    by_name: dict[str, list[int]],
) -> int | None:
    if qname in by_qname:
        return by_qname[qname]
    name = qname.rsplit(".", 1)[-1]
    candidates = by_name.get(name, [])
    return candidates[0] if len(candidates) == 1 else None
