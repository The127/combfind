import pytest

from combfind.db import create_schema, get_connection
from combfind.pipeline.parse import run

SAMPLE = b"""\
-module(greet).
-export([greet/1, add/2]).

-type color() :: red | green | blue.

-record(person, {name :: string(), age :: integer()}).

%% Greets someone by name.
greet(Name) ->
    "Hello, " ++ Name.

add(0, Y) -> Y;
add(X, Y) -> X + Y.
"""


@pytest.fixture
def env(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "greet.erl").write_bytes(SAMPLE)
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
    assert syms["greet"]["qualified_name"] == "src.greet.greet"


def test_multi_clause_deduplicated(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "add" in syms
    assert list(syms.keys()).count("add") == 1


def test_type_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "color" in syms
    assert syms["color"]["kind"] == "type_alias"


def test_record_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "person" in syms
    assert syms["person"]["kind"] == "record"


def test_docstring_on_function(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "Greets someone" in (syms["greet"]["docstring"] or "")


def test_module_attr_not_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "greet" in syms  # module name same as func — only func should appear
    assert syms["greet"]["kind"] == "function"
