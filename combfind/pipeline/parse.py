import hashlib
import importlib
import os
import re
from pathlib import Path

from combfind import telemetry
from combfind.db import get_connection
from combfind.languages import LANGUAGES
from combfind.pipeline.walkers import get_walker

_SKIP_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".tox",
}


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
    ext_map = {
        ext: lang
        for lang, ld in LANGUAGES.items()
        if lang in parsers
        for ext in ld.extensions
    }

    repo = Path(repo_path).resolve()
    excluded = {p.rstrip("/") for p in (exclude_paths or [])}
    pattern = re.compile(exclude_regex) if exclude_regex else None
    processed = skipped = 0
    seen_paths: set[str] = set()

    for dirpath, dirnames, filenames in os.walk(repo):
        rel_dir = str(Path(dirpath).relative_to(repo))

        dirnames[:] = [
            d
            for d in dirnames
            if d not in _SKIP_DIRS
            and not d.startswith(".")
            and not _excluded_by_path(
                "." if rel_dir == "." else f"{rel_dir}/{d}", excluded
            )
            and not (
                pattern and pattern.search("." if rel_dir == "." else f"{rel_dir}/{d}")
            )
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

            seen_paths.add(rel_path)

            try:
                content = file_path.read_bytes()
            except OSError:
                continue
            content_hash = hashlib.sha256(content).hexdigest()

            existing_file = conn.execute(
                "SELECT id, content_hash FROM files WHERE path = ?", (rel_path,)
            ).fetchone()

            if existing_file and existing_file["content_hash"] == content_hash:
                skipped += 1
                continue

            parser = parsers[lang]
            tree = parser.parse(content)
            module = _module_name(repo, file_path)
            walker = get_walker(lang)
            new_symbols = walker.extract_symbols(tree.root_node, module)

            if existing_file:
                file_id = existing_file["id"]
                conn.execute(
                    "UPDATE files SET content_hash = ?, language = ?, "
                    "size_bytes = ? WHERE id = ?",
                    (content_hash, lang, len(content), file_id),
                )
                _diff_symbols(conn, file_id, new_symbols)
            else:
                conn.execute(
                    "INSERT INTO files(path, language, content_hash, size_bytes) "
                    "VALUES (?,?,?,?)",
                    (rel_path, lang, content_hash, len(content)),
                )
                file_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                for sym in new_symbols:
                    _insert_symbol(conn, file_id, sym)

            processed += 1

    deleted = 0
    for (path,) in conn.execute("SELECT path FROM files").fetchall():
        if path not in seen_paths:
            conn.execute("DELETE FROM files WHERE path = ?", (path,))
            deleted += 1

    conn.commit()
    conn.close()
    telemetry.info(
        "parse complete",
        files_processed=processed,
        files_unchanged=skipped,
        files_deleted=deleted,
    )


# ---------------------------------------------------------------------------
# internals
# ---------------------------------------------------------------------------


def _symbol_hash(sym: dict) -> str:
    parts = [sym["qualified_name"] or sym["name"]]
    if sym["signature"] and sym["signature"] != sym["name"]:
        parts.append(sym["signature"])
    if sym["docstring"]:
        parts.append(sym["docstring"])
    return hashlib.sha256(" ".join(parts).encode("utf-8")).hexdigest()


def _insert_symbol(conn, file_id: int, sym: dict) -> None:
    conn.execute(
        "INSERT INTO symbols"
        "(file_id, name, qualified_name, kind, signature, "
        "start_line, end_line, docstring, content_hash) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (
            file_id,
            sym["name"],
            sym["qualified_name"],
            sym["kind"],
            sym["signature"],
            sym["start_line"],
            sym["end_line"],
            sym["docstring"],
            _symbol_hash(sym),
        ),
    )


def _diff_symbols(conn, file_id: int, new_symbols: list[dict]) -> None:
    existing: dict[tuple[str, str | None], dict] = {}
    for row in conn.execute(
        "SELECT id, qualified_name, signature, content_hash, start_line, end_line "
        "FROM symbols WHERE file_id = ?",
        (file_id,),
    ).fetchall():
        existing[(row["qualified_name"], row["signature"])] = row

    new_keys: set[tuple[str, str | None]] = set()
    for sym in new_symbols:
        key = (sym["qualified_name"], sym["signature"])
        new_keys.add(key)
        sym_hash = _symbol_hash(sym)

        if key in existing:
            old = existing[key]
            if old["content_hash"] == sym_hash:
                if (
                    old["start_line"] != sym["start_line"]
                    or old["end_line"] != sym["end_line"]
                ):
                    conn.execute(
                        "UPDATE symbols SET start_line = ?, end_line = ? WHERE id = ?",
                        (sym["start_line"], sym["end_line"], old["id"]),
                    )
            else:
                conn.execute("DELETE FROM symbols WHERE id = ?", (old["id"],))
                _insert_symbol(conn, file_id, sym)
        else:
            _insert_symbol(conn, file_id, sym)

    for key, old in existing.items():
        if key not in new_keys:
            conn.execute("DELETE FROM symbols WHERE id = ?", (old["id"],))


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
    from tree_sitter import Language, Parser

    parsers = {}
    for lang_name, lang_def in LANGUAGES.items():
        if lang_def.grammar:
            try:
                mod = importlib.import_module(lang_def.grammar)
                parsers[lang_name] = Parser(Language(mod.language()))
            except (ImportError, Exception) as exc:
                telemetry.warning(
                    "skipping language", language=lang_name, reason=str(exc)
                )
        elif lang_def.pack_name:
            try:
                from tree_sitter_language_pack import get_parser

                parsers[lang_name] = get_parser(lang_def.pack_name)
            except Exception as exc:
                telemetry.warning(
                    "skipping language", language=lang_name, reason=str(exc)
                )
    return parsers


def _module_name(repo: Path, file_path: Path) -> str:
    parts = list(file_path.relative_to(repo).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts) if parts else file_path.stem
