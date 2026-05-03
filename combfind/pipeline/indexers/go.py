import importlib
import re
from pathlib import Path

from combfind.pipeline.indexers import BaseIndexer


class GoIndexer(BaseIndexer):
    language = "go"
    scip_binary = "scip-go"
    scip_args = ("index", "./...", "--output")
    build_files = ("go.mod", "go.work")
    build_files_label = "go.mod/go.work"

    @staticmethod
    def _scip_symbol_to_qname(symbol: str) -> str | None:
        return _scip_symbol_to_qname(symbol)

    def _run_treesitter(self, conn, repo_path: str) -> int:
        try:
            mod = importlib.import_module("tree_sitter_go")
            from tree_sitter import Language, Parser

            lang = Language(mod.language())
            parser = Parser(lang)
        except Exception:
            return 0

        # package short name → list of symbol ids in that package
        pkg_syms: dict[str, list[int]] = {}
        for row in conn.execute(
            "SELECT s.id, s.qualified_name "
            "FROM symbols s JOIN files f ON f.id = s.file_id "
            "WHERE f.language = 'go' AND s.qualified_name IS NOT NULL"
        ).fetchall():
            pkg = row["qualified_name"].split(".")[0]
            pkg_syms.setdefault(pkg, []).append(row["id"])

        # file path → first symbol id (representative src)
        first_sym: dict[str, int] = {}
        for row in conn.execute(
            "SELECT s.id, f.path "
            "FROM symbols s JOIN files f ON f.id = s.file_id "
            "WHERE f.language = 'go' "
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
            for pkg_name in _walk_imports(tree.root_node):
                for dst_id in pkg_syms.get(pkg_name, [])[:1]:  # one representative per package
                    if dst_id == src_id:
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
    scip-go format: 'scip-go go <module> <version> <descriptors>'
    Examples:
      internal/auth/Validate().     → auth.Validate
      internal/auth/Service#Validate(). → auth.Service.Validate
      internal/auth/Service#          → auth.Service
    """
    if symbol.startswith("local "):
        return None
    parts = symbol.split(" ", 4)
    if len(parts) < 5:
        return None

    desc = parts[4].rstrip(".")
    desc = re.sub(r"\([^)]*\)$", "", desc)
    if not desc:
        return None

    if "#" in desc:
        last_slash = desc.rfind("/")
        if last_slash < 0:
            return None
        pkg_short = desc[:last_slash].rsplit("/", 1)[-1]
        rest = desc[last_slash + 1:]
        type_name, _, method_name = rest.partition("#")
        if method_name:
            return f"{pkg_short}.{type_name}.{method_name}"
        return f"{pkg_short}.{type_name}"
    else:
        last_slash = desc.rfind("/")
        if last_slash < 0:
            return None
        pkg_short = desc[:last_slash].rsplit("/", 1)[-1]
        sym_name = desc[last_slash + 1:]
        return f"{pkg_short}.{sym_name}" if sym_name else None


# ---------------------------------------------------------------------------
# Tree-sitter import extraction
# ---------------------------------------------------------------------------


def _walk_imports(root) -> list[str]:
    """Return package short names (last path component) from import declarations."""
    results = []
    for node in root.named_children:
        if node.type == "import_declaration":
            for spec in node.named_children:
                if spec.type == "import_spec":
                    path_node = spec.child_by_field_name("path")
                    if path_node:
                        raw = path_node.text.decode("utf-8").strip('"')
                        pkg = raw.rsplit("/", 1)[-1]
                        if pkg:
                            results.append(pkg)
    return results
