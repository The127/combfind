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
