import pytest

from combfind.db import create_schema, get_connection
from combfind.pipeline.index import run as index_run
from combfind.pipeline.parse import run as parse_run

AUTH = b"""\
package auth

func Validate(token string) bool {
    return token != ""
}
"""

API = b"""\
package api

import "example.com/proj/auth"

func Handle(token string) bool {
    return auth.Validate(token)
}
"""


@pytest.fixture
def two_pkg_env(tmp_path):
    (tmp_path / "auth").mkdir()
    (tmp_path / "auth" / "auth.go").write_bytes(AUTH)
    (tmp_path / "api").mkdir()
    (tmp_path / "api" / "api.go").write_bytes(API)
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()
    parse_run(db_path, repo_path=str(tmp_path))
    return str(tmp_path), db_path


def _refs(db_path):
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT s1.name src, s2.name dst, r.kind "
        'FROM "references" r '
        "JOIN symbols s1 ON s1.id = r.src_symbol_id "
        "JOIN symbols s2 ON s2.id = r.dst_symbol_id"
    ).fetchall()
    conn.close()
    return {(r["src"], r["dst"], r["kind"]) for r in rows}


def test_import_reference(two_pkg_env):
    # No go.mod in tmp_path, so even if scip-go is on PATH the predicate
    # falls through to the tree-sitter import extractor.
    index_run(two_pkg_env[1], repo_path=two_pkg_env[0])
    refs = _refs(two_pkg_env[1])
    assert any(kind == "import" for _, _, kind in refs)


def test_no_self_references(two_pkg_env):
    index_run(two_pkg_env[1], repo_path=two_pkg_env[0])
    refs = _refs(two_pkg_env[1])
    assert all(src != dst for src, dst, _ in refs)


def test_idempotent(two_pkg_env):
    index_run(two_pkg_env[1], repo_path=two_pkg_env[0])
    refs_first = _refs(two_pkg_env[1])
    index_run(two_pkg_env[1], repo_path=two_pkg_env[0])
    refs_second = _refs(two_pkg_env[1])
    assert refs_first == refs_second
