import combfind.pipeline.docgen as docgen_mod
from combfind.db import create_schema, get_connection

_FAKE_DOC = "Handles user authentication and session management."
_FAKE_SKELETON = "def sym(): pass"


class FakeBackend:
    def chat(self, messages, max_tokens=None, schema=None):
        return _FAKE_DOC


def _make_db(tmp_path, n_symbols=2):
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)

    conn.execute(
        "INSERT INTO files(path, language, content_hash, size_bytes) VALUES ('a.py','python','h',10)"
    )
    file_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    conn.execute(
        "INSERT INTO pipeline_runs(stage, status, params) VALUES ('parse','done','{\"repo_path\":null}')"
    )

    for i in range(n_symbols):
        conn.execute(
            "INSERT INTO symbols(file_id, name, kind, start_line, end_line) VALUES (?,?,?,?,?)",
            (file_id, f"sym_{i}", "function", i + 1, i + 1),
        )

    conn.commit()
    conn.close()
    return db_path


def test_docgen_writes_docstrings(tmp_path, monkeypatch):
    db_path = _make_db(tmp_path)
    monkeypatch.setattr(docgen_mod, "_read_skeleton", lambda row, repo_path: _FAKE_SKELETON)
    docgen_mod.run(db_path, backend=FakeBackend())

    conn = get_connection(db_path)
    rows = conn.execute("SELECT docstring FROM symbols").fetchall()
    conn.close()
    assert all(r["docstring"] == _FAKE_DOC for r in rows)


def test_docgen_skips_existing_docstrings(tmp_path, monkeypatch):
    db_path = _make_db(tmp_path, n_symbols=1)
    conn = get_connection(db_path)
    conn.execute("UPDATE symbols SET docstring = 'already set'")
    conn.commit()
    conn.close()

    call_count = 0

    class CountingBackend:
        def chat(self, messages, max_tokens=None, schema=None):
            nonlocal call_count
            call_count += 1
            return "new doc"

    monkeypatch.setattr(docgen_mod, "_read_skeleton", lambda row, repo_path: _FAKE_SKELETON)
    docgen_mod.run(db_path, backend=CountingBackend())
    assert call_count == 0


def test_docgen_skips_without_backend(tmp_path):
    db_path = _make_db(tmp_path)
    docgen_mod.run(db_path)  # no backend, no llm_model → should return without error

    conn = get_connection(db_path)
    rows = conn.execute("SELECT docstring FROM symbols").fetchall()
    conn.close()
    assert all(r["docstring"] is None for r in rows)


def test_parallel_workers_generate_all(tmp_path, monkeypatch):
    db_path = _make_db(tmp_path, n_symbols=4)
    monkeypatch.setattr(docgen_mod, "_read_skeleton", lambda row, repo_path: _FAKE_SKELETON)
    docgen_mod.run(db_path, backend=FakeBackend(), llm_workers=4)

    conn = get_connection(db_path)
    null_count = conn.execute("SELECT COUNT(*) FROM symbols WHERE docstring IS NULL").fetchone()[0]
    conn.close()
    assert null_count == 0
