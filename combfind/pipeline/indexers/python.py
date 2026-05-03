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


_BUILD_FILES = ("pyproject.toml", "setup.py", "setup.cfg")


def _has_build_tool(repo: Path) -> bool:
    """True if the repo root has a Python project descriptor.

    scip-python requires one of these to index a project; without one
    the subprocess fails with no useful output.
    """
    return any((repo / name).exists() for name in _BUILD_FILES)


class PythonIndexer(BaseIndexer):
    def run(self, conn, *, repo_path: str | None = None) -> int:
        inserted = _inherit(conn)
        if not repo_path:
            return inserted
        if shutil.which("scip-python") and _has_build_tool(Path(repo_path)):
            inserted += self._run_scip(conn, repo_path)
        else:
            telemetry.warning(
                "scip-python unavailable for this repo "
                "(missing binary or no pyproject.toml/setup.py/setup.cfg); "
                "falling back to tree-sitter imports"
            )
            inserted += self._run_treesitter(conn, repo_path)
        return inserted

    def _run_scip(self, conn, repo_path: str) -> int:
        raw = run_scip_binary(
            ["scip-python", "index", "--project-name=combfind", "--quiet", "--output"],
            repo_path,
        )
        if raw is None:
            return 0
        index = parse_scip_index(raw)
        if index is None:
            return 0
        return extract_scip_refs(conn, index, "python", _scip_symbol_to_qname)

    def _run_treesitter(self, conn, repo_path: str) -> int:
        try:
            mod = importlib.import_module("tree_sitter_python")
            from tree_sitter import Language, Parser

            lang = Language(mod.language())
            parser = Parser(lang)
        except Exception:
            return 0

        # qualified_name → id, and name → [ids] for resolution
        by_qname: dict[str, int] = {}
        by_name: dict[str, list[int]] = {}
        for row in conn.execute(
            "SELECT s.id, s.name, s.qualified_name "
            "FROM symbols s JOIN files f ON f.id = s.file_id "
            "WHERE f.language = 'python'"
        ).fetchall():
            if row["qualified_name"]:
                by_qname[row["qualified_name"]] = row["id"]
            by_name.setdefault(row["name"], []).append(row["id"])

        # file path → first symbol id (representative src)
        first_sym: dict[str, int] = {}
        for row in conn.execute(
            "SELECT s.id, f.path "
            "FROM symbols s JOIN files f ON f.id = s.file_id "
            "WHERE f.language = 'python' "
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
            for module_path, sym_name in _walk_imports(tree.root_node):
                dst_id = _resolve_python_import(module_path, sym_name, by_qname, by_name)
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
    scip-python format: 'scip-python python <pkg> <ver> `module.path`/Desc'
    Examples:
      `combfind.pipeline.index`/run().     → combfind.pipeline.index.run
      `combfind.pipeline.indexers`/BaseIndexer#run(). → combfind.pipeline.indexers.BaseIndexer.run
    """
    if symbol.startswith("local "):
        return None
    parts = symbol.split(" ", 4)
    if len(parts) < 5:
        return None

    descriptor = parts[4]
    if not descriptor.startswith("`"):
        return None

    end_bt = descriptor.find("`", 1)
    if end_bt < 0:
        return None

    module = descriptor[1:end_bt]
    rest = descriptor[end_bt + 1:]
    if not rest.startswith("/"):
        return None

    sym_desc = rest[1:].rstrip(".")
    if sym_desc.endswith(":"):  # module-level meta, e.g. __init__:
        return None
    if sym_desc.endswith(")") and not sym_desc.endswith("()"):  # parameter e.g. run().(db_path)
        return None
    if sym_desc.endswith("()"):
        sym_desc = sym_desc[:-2]

    if not sym_desc:
        return None

    if "#" in sym_desc:
        type_name, _, method = sym_desc.partition("#")
        if method:
            return f"{module}.{type_name}.{method}"
        return f"{module}.{type_name}"

    return f"{module}.{sym_desc}"


# ---------------------------------------------------------------------------
# Python inheritance (always runs)
# ---------------------------------------------------------------------------


def _inherit(conn) -> int:
    by_name: dict[str, list[int]] = {}
    by_qname: dict[str, int] = {}
    for row in conn.execute(
        "SELECT id, name, qualified_name FROM symbols"
    ).fetchall():
        by_name.setdefault(row["name"], []).append(row["id"])
        if row["qualified_name"]:
            by_qname[row["qualified_name"]] = row["id"]

    inserted = 0
    for cls in conn.execute(
        "SELECT id, signature FROM symbols WHERE kind = 'class'"
    ).fetchall():
        src_id = cls["id"]
        for base_raw in _parse_bases(cls["signature"]):
            base_name = _clean_name(base_raw)
            if not base_name or base_name in ("object", "ABC", "Protocol"):
                continue
            dst_id = (
                by_qname.get(base_raw)
                or by_qname.get(base_name)
                or _sole(by_name.get(base_name, []), exclude=src_id)
            )
            if dst_id and dst_id != src_id:
                conn.execute(
                    'INSERT OR IGNORE INTO "references"'
                    "(src_symbol_id, dst_symbol_id, kind) VALUES (?,?,?)",
                    (src_id, dst_id, "inherit"),
                )
                inserted += 1
    return inserted


def _parse_bases(signature: str | None) -> list[str]:
    if not signature:
        return []
    m = re.match(r"class\s+\w+\s*\(([^)]*)\)", signature)
    if not m:
        return []
    return [b.strip() for b in m.group(1).split(",") if b.strip()]


def _clean_name(name: str) -> str:
    return re.split(r"[\[\(<]", name)[0].strip()


def _sole(candidates: list[int], *, exclude: int) -> int | None:
    filtered = [i for i in candidates if i != exclude]
    return filtered[0] if len(filtered) == 1 else None


# ---------------------------------------------------------------------------
# Tree-sitter import extraction
# ---------------------------------------------------------------------------


def _walk_imports(root) -> list[tuple[str, str | None]]:
    """Return (module_path, symbol_name_or_None) for each import in the file."""
    results = []
    for node in root.named_children:
        if node.type == "import_statement":
            for child in node.named_children:
                if child.type == "dotted_name":
                    results.append((child.text.decode("utf-8"), None))
                elif child.type == "aliased_import":
                    name = child.child_by_field_name("name")
                    if name:
                        results.append((name.text.decode("utf-8"), None))
        elif node.type == "import_from_statement":
            module_node = node.child_by_field_name("module_name")
            module = module_node.text.decode("utf-8") if module_node else None
            if not module:
                continue
            for child in node.named_children:
                if child.type == "dotted_name":
                    results.append((module, child.text.decode("utf-8")))
                elif child.type == "aliased_import":
                    name = child.child_by_field_name("name")
                    if name:
                        results.append((module, name.text.decode("utf-8")))
    return results


def _resolve_python_import(
    module: str,
    sym_name: str | None,
    by_qname: dict[str, int],
    by_name: dict[str, list[int]],
) -> int | None:
    if sym_name:
        # from foo.bar import Baz → look for foo.bar.Baz
        qname = f"{module}.{sym_name}"
        if qname in by_qname:
            return by_qname[qname]
        # fallback: match by name alone
        candidates = by_name.get(sym_name, [])
        return candidates[0] if len(candidates) == 1 else None
    else:
        # import foo.bar → any symbol in foo.bar.*
        prefix = module + "."
        for qn, sid in by_qname.items():
            if qn.startswith(prefix):
                return sid
        return None
