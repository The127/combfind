import json

import numpy as np
import pytest

import combfind.query as query_mod
from combfind.db import create_schema, get_connection

DIM = 4

# Known embeddings: concept 0 = [1,0,0,0], concept 1 = [0,1,0,0]
# Query [1,0,0,0] should rank concept 0 first.
EMB_0 = np.array([1, 0, 0, 0], dtype=np.float32)
EMB_1 = np.array([0, 1, 0, 0], dtype=np.float32)
QUERY_EMB = np.array([1, 0, 0, 0], dtype=np.float32)


@pytest.fixture
def env(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)

    conn.execute(
        "INSERT OR REPLACE INTO build_config(key, value) VALUES ('embed_model', ?)",
        (json.dumps("test-model"),),
    )

    # Two files
    conn.execute(
        "INSERT INTO files(path, language, content_hash, size_bytes) VALUES ('auth/service.py','python','h1',100)"
    )
    file1 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO files(path, language, content_hash, size_bytes) VALUES ('auth/mock.py','python','h2',50)"
    )
    file2 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Symbols: AuthService, AuthService.validate, MockAuthService
    conn.execute(
        "INSERT INTO symbols(file_id, name, qualified_name, kind, signature, start_line, end_line)"
        " VALUES (?,?,?,?,?,?,?)",
        (file1, "AuthService", "auth.service.AuthService", "class", "class AuthService", 10, 80),
    )
    auth_sym = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        "INSERT INTO symbols(file_id, name, qualified_name, kind, signature, start_line, end_line)"
        " VALUES (?,?,?,?,?,?,?)",
        (file1, "validate", "auth.service.AuthService.validate", "method", "def validate(self, t)", 20, 35),
    )
    validate_sym = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        "INSERT INTO symbols(file_id, name, qualified_name, kind, signature, start_line, end_line)"
        " VALUES (?,?,?,?,?,?,?)",
        (file2, "MockAuthService", "auth.mock.MockAuthService", "class", "class MockAuthService(AuthService)", 5, 40),
    )
    mock_sym = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # MockAuthService inherits AuthService
    conn.execute(
        'INSERT INTO "references"(src_symbol_id, dst_symbol_id, kind) VALUES (?,?,?)',
        (mock_sym, auth_sym, "inherit"),
    )

    # Two concepts
    conn.execute(
        "INSERT INTO concepts(name, description, role, member_count, centroid)"
        " VALUES ('Auth Service','Handles token validation','implementation',2,?)",
        (EMB_0.tobytes(),),
    )
    concept0 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    conn.execute(
        "INSERT INTO concepts(name, description, role, member_count, centroid)"
        " VALUES ('Mock Auth','Test double for auth','implementation',1,?)",
        (EMB_1.tobytes(),),
    )
    concept1 = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    # Concept members
    for sym_id, dist in [(auth_sym, 0.1), (validate_sym, 0.2)]:
        conn.execute(
            "INSERT INTO concept_members(concept_id, symbol_id, distance_to_centroid) VALUES (?,?,?)",
            (concept0, sym_id, dist),
        )
    conn.execute(
        "INSERT INTO concept_members(concept_id, symbol_id, distance_to_centroid) VALUES (?,?,?)",
        (concept1, mock_sym, 0.0),
    )

    # Concept embeddings
    conn.execute(
        "INSERT INTO concept_embeddings(concept_id, embedding) VALUES (?,?)",
        (concept0, EMB_0.tobytes()),
    )
    conn.execute(
        "INSERT INTO concept_embeddings(concept_id, embedding) VALUES (?,?)",
        (concept1, EMB_1.tobytes()),
    )

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def mock_model(monkeypatch):
    class FakeModel:
        def __init__(self, name):
            pass

        def encode(self, texts, **kwargs):
            return np.array([QUERY_EMB for _ in texts])

    monkeypatch.setattr(query_mod, "SentenceTransformer", FakeModel)


def test_returns_top_k(env, mock_model):
    results = query_mod.query("validate tokens", db_path=env, top_k=1)
    assert len(results) == 1


def test_top_result_is_auth_service(env, mock_model):
    results = query_mod.query("validate tokens", db_path=env, top_k=2)
    assert results[0]["concept"] == "Auth Service"


def test_result_fields(env, mock_model):
    results = query_mod.query("validate tokens", db_path=env, top_k=1)
    r = results[0]
    assert r["rank"] == 1
    assert r["role"] == "implementation"
    assert 0.0 <= r["score"] <= 1.0
    assert isinstance(r["files"], list)
    assert isinstance(r["sibling_implementations"], list)
    assert isinstance(r["why_relevant"], str)


def test_files_have_symbols(env, mock_model):
    results = query_mod.query("validate tokens", db_path=env, top_k=1)
    f = results[0]["files"][0]
    assert f["path"] == "auth/service.py"
    assert isinstance(f["symbols"], list)
    assert len(f["symbols"]) == 2
    qnames = [s["qualified_name"] for s in f["symbols"]]
    assert "auth.service.AuthService" in qnames
    assert "auth.service.AuthService.validate" in qnames


def test_symbol_entries_have_line_ranges(env, mock_model):
    results = query_mod.query("validate tokens", db_path=env, top_k=1)
    syms = results[0]["files"][0]["symbols"]
    auth = next(s for s in syms if s["qualified_name"] == "auth.service.AuthService")
    assert auth["start_line"] == 10
    assert auth["end_line"] == 80


def test_sibling_found_for_auth_service(env, mock_model):
    # Auth Service concept contains AuthService; MockAuthService inherits it → sibling
    results = query_mod.query("validate tokens", db_path=env, top_k=2)
    auth_result = next(r for r in results if r["concept"] == "Auth Service")
    sibling_names = [s["name"] for s in auth_result["sibling_implementations"]]
    assert "MockAuthService" in sibling_names


def test_empty_db_returns_empty(tmp_path, mock_model):
    db_path = str(tmp_path / "empty.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()
    results = query_mod.query("anything", db_path=db_path)
    assert results == []


def test_ranks_are_sequential(env, mock_model):
    results = query_mod.query("validate tokens", db_path=env, top_k=2)
    assert [r["rank"] for r in results] == [1, 2]


def test_print_text_format(env, mock_model, capsys):
    results = query_mod.query("validate tokens", db_path=env, top_k=1)
    query_mod.print_results(results, fmt="text")
    out = capsys.readouterr().out
    assert "Auth Service" in out
    assert "implementation" in out
    assert "auth/service.py" in out


def test_print_json_format(env, mock_model, capsys):
    results = query_mod.query("validate tokens", db_path=env, top_k=1)
    query_mod.print_results(results, fmt="json")
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert isinstance(parsed, list)
    assert parsed[0]["concept"] == "Auth Service"
