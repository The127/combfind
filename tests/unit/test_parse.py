import pytest

from combfind.db import create_schema, get_connection
from combfind.pipeline.parse import run

SAMPLE = '''\
class MyClass(Base):
    """A simple class."""

    def __init__(self, x: int):
        """Constructor."""
        self.x = x

    def method(self) -> int:
        """Returns x."""
        return self.x


async def top_level(a, b):
    """A top-level function."""
    return a + b
'''


@pytest.fixture
def env(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "sample.py").write_text(SAMPLE)
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()
    return str(tmp_path), db_path


def _symbols(db_path):
    conn = get_connection(db_path)
    rows = conn.execute("SELECT name, kind, qualified_name, docstring FROM symbols").fetchall()
    conn.close()
    return {r["name"]: dict(r) for r in rows}


def test_class_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "MyClass" in syms
    assert syms["MyClass"]["kind"] == "class"
    assert syms["MyClass"]["qualified_name"] == "src.sample.MyClass"


def test_constructor_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert syms["__init__"]["kind"] == "constructor"


def test_method_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert syms["method"]["kind"] == "method"
    assert syms["method"]["qualified_name"] == "src.sample.MyClass.method"


def test_function_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert syms["top_level"]["kind"] == "function"
    assert "top-level function" in (syms["top_level"]["docstring"] or "")


def test_docstring_on_class(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "simple class" in (syms["MyClass"]["docstring"] or "")


def test_cache_skips_unchanged_file(env):
    repo_path, db_path = env
    run(db_path, repo_path=repo_path)
    conn = get_connection(db_path)
    count_before = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
    conn.close()

    run(db_path, repo_path=repo_path)

    conn = get_connection(db_path)
    count_after = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
    conn.close()
    assert count_before == count_after > 0


def test_reruns_on_file_change(env, tmp_path):
    repo_path, db_path = env
    run(db_path, repo_path=repo_path)

    # Add a new function to the file
    sample = (tmp_path / "src" / "sample.py")
    sample.write_text(SAMPLE + "\ndef extra(): pass\n")

    run(db_path, repo_path=repo_path)

    syms = _symbols(db_path)
    assert "extra" in syms


def test_exclude_paths(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("def kept(): pass\n")
    (tmp_path / "generated").mkdir()
    (tmp_path / "generated" / "auto.py").write_text("def excluded(): pass\n")

    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()

    run(db_path, repo_path=str(tmp_path), exclude_paths=["generated"])
    syms = _symbols(db_path)
    assert "kept" in syms
    assert "excluded" not in syms


def test_deleted_file_removed_from_db(tmp_path):
    (tmp_path / "src").mkdir()
    a = tmp_path / "src" / "a.py"
    b = tmp_path / "src" / "b.py"
    a.write_text("def func_a(): pass\n")
    b.write_text("def func_b(): pass\n")

    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()

    run(db_path, repo_path=str(tmp_path))
    syms = _symbols(db_path)
    assert "func_a" in syms
    assert "func_b" in syms

    b.unlink()
    run(db_path, repo_path=str(tmp_path))
    syms = _symbols(db_path)
    assert "func_a" in syms
    assert "func_b" not in syms


def test_unchanged_file_preserves_docstring(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("def nodoc(): pass\n")
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()

    run(db_path, repo_path=str(tmp_path))

    conn = get_connection(db_path)
    conn.execute("UPDATE symbols SET docstring = 'generated' WHERE name = 'nodoc'")
    conn.commit()
    conn.close()

    run(db_path, repo_path=str(tmp_path))

    syms = _symbols(db_path)
    assert syms["nodoc"]["docstring"] == "generated"


def test_changed_file_resets_docstring(tmp_path):
    (tmp_path / "src").mkdir()
    f = tmp_path / "src" / "a.py"
    f.write_text("def nodoc(): pass\n")
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()

    run(db_path, repo_path=str(tmp_path))

    conn = get_connection(db_path)
    conn.execute("UPDATE symbols SET docstring = 'generated' WHERE name = 'nodoc'")
    conn.commit()
    conn.close()

    f.write_text("def nodoc(): pass\n# changed\n")
    run(db_path, repo_path=str(tmp_path))

    syms = _symbols(db_path)
    assert syms["nodoc"]["docstring"] is None


def test_deleted_file_removes_symbols(tmp_path):
    (tmp_path / "src").mkdir()
    f = tmp_path / "src" / "a.py"
    f.write_text("def todelete(): pass\n")
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()

    run(db_path, repo_path=str(tmp_path))
    assert "todelete" in _symbols(db_path)

    f.unlink()
    run(db_path, repo_path=str(tmp_path))
    assert "todelete" not in _symbols(db_path)


def test_exclude_regex(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "service.py").write_text("def real(): pass\n")
    (tmp_path / "src" / "service_pb2.py").write_text("def generated(): pass\n")

    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()

    run(db_path, repo_path=str(tmp_path), exclude_regex=r".*_pb2\.py$")
    syms = _symbols(db_path)
    assert "real" in syms
    assert "generated" not in syms
