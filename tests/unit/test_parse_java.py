import pytest

from combfind.db import create_schema, get_connection
from combfind.pipeline.parse import run

SAMPLE = b"""\
package com.example.auth;

/** Server handles HTTP requests. */
public class Server extends Base implements Runnable {
    private String host;

    /** Construct with host. */
    public Server(String host) {
        this.host = host;
    }

    /** Start listening. */
    public void start() {}

    public static class Inner {
        void hi() {}
    }
}

/** Handler defines the request interface. */
interface Handler {
    String handle(String req);
}

enum Color { RED, GREEN }

record Point(int x, int y) {}
"""


@pytest.fixture
def env(tmp_path):
    src = tmp_path / "src" / "auth"
    src.mkdir(parents=True)
    (src / "Server.java").write_bytes(SAMPLE)
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()
    return str(tmp_path), db_path


def _symbols(db_path):
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT name, kind, qualified_name, signature, docstring FROM symbols"
    ).fetchall()
    conn.close()
    return {r["qualified_name"]: dict(r) for r in rows}


def test_class_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    s = syms["com.example.auth.Server"]
    assert s["kind"] == "class"
    assert "extends Base" in s["signature"]
    assert "implements Runnable" in s["signature"]


def test_interface_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert syms["com.example.auth.Handler"]["kind"] == "interface"


def test_enum_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert syms["com.example.auth.Color"]["kind"] == "enum"


def test_record_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    s = syms["com.example.auth.Point"]
    assert s["kind"] == "record"
    assert "(int x, int y)" in s["signature"]


def test_method_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    s = syms["com.example.auth.Server.start"]
    assert s["kind"] == "method"
    assert s["signature"] == "void start()"


def test_constructor_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    s = syms["com.example.auth.Server.Server"]
    assert s["kind"] == "constructor"
    assert s["signature"] == "Server(String host)"


def test_nested_class_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert syms["com.example.auth.Server.Inner"]["kind"] == "class"


def test_javadoc_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "HTTP requests" in (syms["com.example.auth.Server"]["docstring"] or "")
    assert "Start listening" in (
        syms["com.example.auth.Server.start"]["docstring"] or ""
    )


def test_enum_constants_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert syms["com.example.auth.Color.RED"]["kind"] == "enum_constant"
