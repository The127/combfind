import json

import numpy as np
import pytest

import combfind.inspect as inspect_mod
from combfind.db import create_schema, get_connection

EMB_0 = np.array([1, 0, 0, 0], dtype=np.float32)
EMB_1 = np.array([0, 1, 0, 0], dtype=np.float32)


@pytest.fixture
def env(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)

    conn.execute(
        "INSERT INTO files(path, language, content_hash, size_bytes) "
        "VALUES ('auth/service.py','python','h1',100)"
    )
    file1 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO files(path, language, content_hash, size_bytes) "
        "VALUES ('auth/mock.py','python','h2',50)"
    )
    file2 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        "INSERT INTO symbols"
        "(file_id, name, qualified_name, kind, signature, "
        "start_line, end_line, docstring) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            file1,
            "AuthService",
            "auth.service.AuthService",
            "class",
            "class AuthService",
            10,
            80,
            "Handles auth.",
        ),
    )
    auth_sym = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        "INSERT INTO symbols"
        "(file_id, name, qualified_name, kind, signature, "
        "start_line, end_line, docstring) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            file1,
            "validate",
            "auth.service.AuthService.validate",
            "method",
            "def validate(self, t)",
            20,
            35,
            None,
        ),
    )
    validate_sym = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        "INSERT INTO symbols"
        "(file_id, name, qualified_name, kind, signature, "
        "start_line, end_line, docstring) "
        "VALUES (?,?,?,?,?,?,?,?)",
        (
            file2,
            "MockAuthService",
            "auth.mock.MockAuthService",
            "class",
            "class MockAuthService(AuthService)",
            5,
            40,
            None,
        ),
    )
    mock_sym = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        'INSERT INTO "references"(src_symbol_id, dst_symbol_id, kind) VALUES (?,?,?)',
        (mock_sym, auth_sym, "inherit"),
    )
    conn.execute(
        'INSERT INTO "references"(src_symbol_id, dst_symbol_id, kind) VALUES (?,?,?)',
        (auth_sym, validate_sym, "call"),
    )

    conn.execute(
        "INSERT INTO concepts(name, description, role, member_count, centroid)"
        " VALUES ('Auth Service','Handles token validation','implementation',2,?)",
        (EMB_0.tobytes(),),
    )
    concept0 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    for sym_id, dist in [(auth_sym, 0.1), (validate_sym, 0.2)]:
        conn.execute(
            "INSERT INTO concept_members(concept_id, symbol_id, distance_to_centroid) "
            "VALUES (?,?,?)",
            (concept0, sym_id, dist),
        )

    conn.commit()
    conn.close()
    return {
        "db_path": db_path,
        "auth_sym": auth_sym,
        "validate_sym": validate_sym,
        "mock_sym": mock_sym,
    }


def test_exact_match_returns_result(env):
    r = inspect_mod.inspect_symbol("auth.service.AuthService", db_path=env["db_path"])
    assert r is not None
    assert r["symbol"] == "auth.service.AuthService"


def test_unknown_symbol_returns_none(env):
    r = inspect_mod.inspect_symbol("does.not.Exist", db_path=env["db_path"])
    assert r is None


def test_metadata_fields(env):
    r = inspect_mod.inspect_symbol("auth.service.AuthService", db_path=env["db_path"])
    assert r["kind"] == "class"
    assert r["file"] == "auth/service.py"
    assert r["lines"] == "10-80"
    assert r["signature"] == "class AuthService"
    assert r["docstring"] == "Handles auth."


def test_concept_and_role(env):
    r = inspect_mod.inspect_symbol("auth.service.AuthService", db_path=env["db_path"])
    assert r["concept"] == "Auth Service"
    assert r["role"] == "implementation"


def test_no_concept_when_not_member(env):
    r = inspect_mod.inspect_symbol("auth.mock.MockAuthService", db_path=env["db_path"])
    assert r["concept"] is None
    assert r["role"] is None


def test_callers(env):
    r = inspect_mod.inspect_symbol("auth.service.AuthService", db_path=env["db_path"])
    caller_syms = [c["symbol"] for c in r["callers"]]
    assert "auth.mock.MockAuthService" in caller_syms


def test_callees(env):
    r = inspect_mod.inspect_symbol("auth.service.AuthService", db_path=env["db_path"])
    callee_syms = [c["symbol"] for c in r["callees"]]
    assert "auth.service.AuthService.validate" in callee_syms


def test_concept_siblings(env):
    r = inspect_mod.inspect_symbol("auth.service.AuthService", db_path=env["db_path"])
    sibling_qnames = [s["qualified_name"] for s in r["concept_siblings"]]
    assert "auth.service.AuthService.validate" in sibling_qnames
    assert "auth.service.AuthService" not in sibling_qnames


def test_find_candidates(env):
    candidates = inspect_mod.find_candidates("AuthService", db_path=env["db_path"])
    assert "auth.service.AuthService" in candidates
    assert "auth.mock.MockAuthService" in candidates


def test_find_candidates_no_match(env):
    candidates = inspect_mod.find_candidates("zzznomatch", db_path=env["db_path"])
    assert candidates == []


def test_print_text_format(env, capsys):
    r = inspect_mod.inspect_symbol("auth.service.AuthService", db_path=env["db_path"])
    inspect_mod.print_inspect(r, fmt="text")
    out = capsys.readouterr().out
    assert "auth.service.AuthService" in out
    assert "Auth Service" in out
    assert "auth.mock.MockAuthService" in out
    assert "auth.service.AuthService.validate" in out


def test_print_json_format(env, capsys):
    r = inspect_mod.inspect_symbol("auth.service.AuthService", db_path=env["db_path"])
    inspect_mod.print_inspect(r, fmt="json")
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["symbol"] == "auth.service.AuthService"
    assert isinstance(parsed["callers"], list)
    assert isinstance(parsed["callees"], list)
    assert isinstance(parsed["concept_siblings"], list)
