import json

import pytest

import combfind.pipeline.label as label_mod
from combfind.db import create_schema, get_connection

_GOOD = {
    "name": "Auth Service",
    "description": "Handles user authentication.",
    "role": "implementation",
}


@pytest.fixture
def env(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)

    conn.execute(
        "INSERT INTO files(path, language, content_hash, size_bytes) "
        "VALUES ('a.py','python','h',10)"
    )
    file_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    for i in range(3):
        conn.execute(
            "INSERT INTO symbols"
            "(file_id, name, kind, signature, start_line, end_line, docstring) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                file_id,
                f"sym_{i}",
                "function",
                f"def sym_{i}()",
                i * 2 + 1,
                i * 2 + 2,
                f"Does {i}.",
            ),
        )

    conn.execute(
        "INSERT INTO concepts(member_count, centroid) VALUES (3, ?)", (b"\x00" * 16,)
    )
    concept_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    for (sym_id,) in conn.execute("SELECT id FROM symbols").fetchall():
        conn.execute(
            "INSERT INTO concept_members(concept_id, symbol_id, distance_to_centroid) "
            "VALUES (?,?,?)",
            (concept_id, sym_id, 0.1),
        )

    conn.commit()
    conn.close()
    return db_path


class FakeBackend:
    def __init__(self, response: dict | str):
        self._response = response if isinstance(response, str) else json.dumps(response)

    def chat(self, messages, max_tokens=None, schema=None):
        return self._response


def test_concept_labeled(env):
    label_mod.run(env, backend=FakeBackend(_GOOD))
    conn = get_connection(env)
    row = conn.execute(
        "SELECT name, description, role FROM concepts LIMIT 1"
    ).fetchone()
    conn.close()
    assert row["name"] == "Auth Service"
    assert row["description"] == "Handles user authentication."
    assert row["role"] == "implementation"


def test_requires_llm_model(env):
    with pytest.raises(ValueError, match="llm backend"):
        label_mod.run(env)


def test_skips_already_labeled(env):
    conn = get_connection(env)
    conn.execute("UPDATE concepts SET name='Already Named'")
    conn.commit()
    conn.close()

    label_mod.run(env, backend=FakeBackend(_GOOD))

    conn = get_connection(env)
    assert (
        conn.execute("SELECT name FROM concepts LIMIT 1").fetchone()[0]
        == "Already Named"
    )
    conn.close()


def test_invalid_role_stored_as_null(env):
    label_mod.run(
        env,
        backend=FakeBackend(
            {"name": "Foo", "description": "Does foo.", "role": "not_valid"}
        ),
    )

    conn = get_connection(env)
    role = conn.execute("SELECT role FROM concepts LIMIT 1").fetchone()[0]
    conn.close()
    assert role is None


def test_malformed_json_skipped(env):
    label_mod.run(env, backend=FakeBackend("not json at all"))

    conn = get_connection(env)
    name = conn.execute("SELECT name FROM concepts LIMIT 1").fetchone()[0]
    conn.close()
    assert name is None  # concept left unlabeled, not crashed


def test_parallel_workers_label_all_concepts(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)

    conn.execute(
        "INSERT INTO files(path, language, content_hash, size_bytes) "
        "VALUES ('a.py','python','h',10)"
    )
    file_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    for c in range(3):
        conn.execute(
            "INSERT INTO symbols(file_id, name, kind, start_line, end_line) "
            "VALUES (?,?,?,?,?)",
            (file_id, f"sym_{c}", "function", c + 1, c + 1),
        )
        sym_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO concepts(member_count, centroid) VALUES (1, ?)",
            (b"\x00" * 16,),
        )
        concept_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        conn.execute(
            "INSERT INTO concept_members(concept_id, symbol_id, distance_to_centroid) "
            "VALUES (?,?,?)",
            (concept_id, sym_id, 0.0),
        )

    conn.commit()
    conn.close()

    label_mod.run(db_path, backend=FakeBackend(_GOOD), llm_workers=3)

    conn = get_connection(db_path)
    unlabeled = conn.execute(
        "SELECT COUNT(*) FROM concepts WHERE name IS NULL"
    ).fetchone()[0]
    conn.close()
    assert unlabeled == 0
