import pytest

from combfind.db import create_schema, get_connection
from combfind.pipeline.parse import run

SAMPLE = b"""\
import gleam/io

pub const greeting = "hello"

pub type Color {
  Red
  Green
  Blue
}

pub type Alias = Color

/// Greets someone by name.
pub fn greet(name: String) -> String {
  "Hello, " <> name
}

fn private_helper(x: Int) -> Int {
  x + 1
}
"""


@pytest.fixture
def env(tmp_path):
    src = tmp_path / "src" / "myapp"
    src.mkdir(parents=True)
    (src / "greet.gleam").write_bytes(SAMPLE)
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()
    return str(tmp_path), db_path


def _symbols(db_path):
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT name, kind, qualified_name, docstring FROM symbols"
    ).fetchall()
    conn.close()
    return {r["name"]: dict(r) for r in rows}


def test_function_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "greet" in syms
    assert syms["greet"]["kind"] == "function"
    assert syms["greet"]["qualified_name"] == "src.myapp.greet.greet"


def test_private_function_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "private_helper" in syms
    assert syms["private_helper"]["kind"] == "function"


def test_type_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "Color" in syms
    assert syms["Color"]["kind"] == "enum"
    assert syms["Color"]["qualified_name"] == "src.myapp.greet.Color"


def test_type_alias_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "Alias" in syms
    assert syms["Alias"]["kind"] == "type_alias"


def test_constant_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "greeting" in syms
    assert syms["greeting"]["kind"] == "constant"


def test_docstring_on_function(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "Greets someone" in (syms["greet"]["docstring"] or "")


def test_import_not_extracted_as_symbol(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "io" not in syms
    assert "gleam" not in syms
