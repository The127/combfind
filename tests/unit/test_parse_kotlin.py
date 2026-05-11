import pytest

from combfind.db import create_schema, get_connection
from combfind.pipeline.parse import run

SAMPLE = b"""\
package com.example.auth

import kotlin.io.println

/** Server handles HTTP requests. */
class Server(private val host: String) : Base(), Runnable {

    /** Start listening. */
    fun start() {}

    fun stop(): Boolean = true

    companion object {
        const val DEFAULT_PORT = 8080
        fun create(): Server = Server("localhost")
    }

    class Inner {
        fun hi() {}
    }
}

/** Handler defines the request interface. */
interface Handler {
    fun handle(req: String): String
}

enum class Color { RED, GREEN, BLUE }

data class Point(val x: Int, val y: Int)

object Util {
    fun ping() = 1
}

/** A top-level helper. */
fun topLevel(x: Int): Int = x + 1

fun String.shout(): String = this.uppercase()

const val GREETING = "hello"

val pi = 3.14
"""


@pytest.fixture
def env(tmp_path):
    src = tmp_path / "src" / "auth"
    src.mkdir(parents=True)
    (src / "Server.kt").write_bytes(SAMPLE)
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
    assert s["name"] == "Server"
    assert "Server" in s["signature"]
    assert "Base()" in s["signature"]
    assert "Runnable" in s["signature"]


def test_interface_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    s = syms["com.example.auth.Handler"]
    assert s["kind"] == "interface"


def test_enum_class_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    s = syms["com.example.auth.Color"]
    assert s["kind"] == "enum"
    assert "enum class Color" in s["signature"]


def test_data_class_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    s = syms["com.example.auth.Point"]
    assert s["kind"] == "class"
    assert "data class Point" in s["signature"]
    assert "(val x: Int, val y: Int)" in s["signature"]


def test_object_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    s = syms["com.example.auth.Util"]
    assert s["kind"] == "class"
    assert s["signature"].startswith("object Util")


def test_method_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    s = syms["com.example.auth.Server.start"]
    assert s["kind"] == "method"
    assert s["signature"] == "fun start()"


def test_method_with_return_type(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    s = syms["com.example.auth.Server.stop"]
    assert s["kind"] == "method"
    assert s["signature"] == "fun stop(): Boolean"


def test_companion_object_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    s = syms["com.example.auth.Server.Companion"]
    assert s["kind"] == "class"
    assert "companion object" in s["signature"]


def test_companion_members_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert syms["com.example.auth.Server.Companion.DEFAULT_PORT"]["kind"] == "constant"
    assert syms["com.example.auth.Server.Companion.create"]["kind"] == "method"


def test_nested_class_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert syms["com.example.auth.Server.Inner"]["kind"] == "class"
    assert syms["com.example.auth.Server.Inner.hi"]["kind"] == "method"


def test_top_level_function_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    s = syms["com.example.auth.topLevel"]
    assert s["kind"] == "function"
    assert s["signature"] == "fun topLevel(x: Int): Int"


def test_extension_function_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    s = syms["com.example.auth.shout"]
    assert s["kind"] == "function"
    assert "fun String.shout()" in s["signature"]


def test_const_val_is_constant(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    s = syms["com.example.auth.GREETING"]
    assert s["kind"] == "constant"
    assert "const val GREETING" in s["signature"]


def test_top_level_val_is_property(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    s = syms["com.example.auth.pi"]
    assert s["kind"] == "property"


def test_enum_entries_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert syms["com.example.auth.Color.RED"]["kind"] == "enum_constant"
    assert syms["com.example.auth.Color.GREEN"]["kind"] == "enum_constant"
    assert syms["com.example.auth.Color.BLUE"]["kind"] == "enum_constant"


def test_kdoc_extracted(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    assert "HTTP requests" in (syms["com.example.auth.Server"]["docstring"] or "")
    assert "Start listening" in (
        syms["com.example.auth.Server.start"]["docstring"] or ""
    )
    assert "top-level helper" in (syms["com.example.auth.topLevel"]["docstring"] or "")


def test_import_not_extracted_as_symbol(env):
    run(env[1], repo_path=env[0])
    syms = _symbols(env[1])
    # The `import kotlin.io.println` statement should not produce a symbol.
    assert not any(qn and qn.endswith(".println") for qn in syms)
