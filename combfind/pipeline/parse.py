import hashlib
import importlib
import os
import re
from pathlib import Path

from combfind.db import get_connection
from combfind.languages import LANGUAGES
from combfind.pipeline.walkers import get_walker

_SKIP_DIRS = {".git", "__pycache__", "node_modules", ".venv", "venv", "dist", "build", ".tox"}


def run(
    db_path: str,
    *,
    repo_path: str,
    exclude_paths: list[str] | None = None,
    exclude_regex: str | None = None,
    **_,
) -> None:
    conn = get_connection(db_path)

    parsers = _build_parsers()
    ext_map = {ext: lang for lang, ld in LANGUAGES.items() if lang in parsers for ext in ld.extensions}

    repo = Path(repo_path).resolve()
    excluded = {p.rstrip("/") for p in (exclude_paths or [])}
    pattern = re.compile(exclude_regex) if exclude_regex else None
    processed = skipped = 0

    for dirpath, dirnames, filenames in os.walk(repo):
        rel_dir = str(Path(dirpath).relative_to(repo))

        dirnames[:] = [
            d for d in dirnames
            if d not in _SKIP_DIRS
            and not d.startswith(".")
            and not _excluded_by_path("." if rel_dir == "." else f"{rel_dir}/{d}", excluded)
            and not (pattern and pattern.search("." if rel_dir == "." else f"{rel_dir}/{d}"))
        ]

        for filename in filenames:
            ext = Path(filename).suffix
            lang = ext_map.get(ext)
            if lang is None:
                continue

            file_path = Path(dirpath) / filename
            rel_path = str(file_path.relative_to(repo))

            if _excluded_by_path(rel_path, excluded):
                continue
            if pattern and pattern.search(rel_path):
                continue

            try:
                content = file_path.read_bytes()
            except OSError:
                continue
            content_hash = hashlib.sha256(content).hexdigest()

            if conn.execute(
                "SELECT 1 FROM files WHERE path = ? AND content_hash = ?",
                (rel_path, content_hash),
            ).fetchone():
                skipped += 1
                continue

            conn.execute("DELETE FROM files WHERE path = ?", (rel_path,))
            conn.execute(
                "INSERT INTO files(path, language, content_hash, size_bytes) VALUES (?,?,?,?)",
                (rel_path, lang, content_hash, len(content)),
            )
            file_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

            parser = parsers[lang]
            tree = parser.parse(content)
            module = _module_name(repo, file_path)
            walker = get_walker(lang)

            for sym in walker.extract_symbols(tree.root_node, module):
                conn.execute(
                    """INSERT INTO symbols
                         (file_id, name, qualified_name, kind, signature, start_line, end_line, docstring)
                       VALUES (?,?,?,?,?,?,?,?)""",
                    (file_id, sym["name"], sym["qualified_name"], sym["kind"],
                     sym["signature"], sym["start_line"], sym["end_line"], sym["docstring"]),
                )

            processed += 1

    conn.commit()
    conn.close()
    print(f"[combfind] parse: {processed} files processed, {skipped} unchanged")


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------

def _excluded_by_path(rel_path: str, excluded: set[str]) -> bool:
    """Return True if rel_path or any of its parents is in excluded."""
    if not excluded:
        return False
    parts = Path(rel_path).parts
    for i in range(1, len(parts) + 1):
        if str(Path(*parts[:i])) in excluded:
            return True
    return False


def _build_parsers() -> dict:
    from tree_sitter import Parser

    parsers = {}
    for lang_name, lang_def in LANGUAGES.items():
        try:
            mod = importlib.import_module(lang_def.grammar)
            from tree_sitter import Language
            lang = Language(mod.language())
            parsers[lang_name] = Parser(lang)
        except (ImportError, Exception) as exc:
            print(f"[combfind] warning: skipping language {lang_name!r}: {exc}")
    return parsers


def _module_name(repo: Path, file_path: Path) -> str:
    parts = list(file_path.relative_to(repo).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else file_path.stem


