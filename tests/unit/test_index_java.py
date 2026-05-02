import pytest

from combfind.db import create_schema, get_connection
from combfind.pipeline.index import run as index_run
from combfind.pipeline.parse import run as parse_run

ANIMAL = b"""\
package com.example;

public class Animal {
    public void speak() {}
}
"""

DOG = b"""\
package com.example;

import com.example.Animal;

public class Dog extends Animal {
    @Override
    public void speak() {}
}
"""

INTERFACES = b"""\
package com.example;

public interface Runnable {
    void run();
}

public interface Closeable {
    void close();
}

public class Worker implements Runnable, Closeable {
    public void run() {}
    public void close() {}
}
"""


@pytest.fixture
def two_class_env(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "Animal.java").write_bytes(ANIMAL)
    (src / "Dog.java").write_bytes(DOG)
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()
    parse_run(db_path, repo_path=str(tmp_path))
    return str(tmp_path), db_path


@pytest.fixture
def interface_env(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "Types.java").write_bytes(INTERFACES)
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()
    parse_run(db_path, repo_path=str(tmp_path))
    return str(tmp_path), db_path


def _refs(db_path):
    conn = get_connection(db_path)
    rows = conn.execute(
        "SELECT s1.name src, s2.name dst, r.kind "
        'FROM "references" r '
        "JOIN symbols s1 ON s1.id = r.src_symbol_id "
        "JOIN symbols s2 ON s2.id = r.dst_symbol_id"
    ).fetchall()
    conn.close()
    return {(r["src"], r["dst"], r["kind"]) for r in rows}


def test_inherit_extends(two_class_env):
    index_run(two_class_env[1], repo_path=two_class_env[0])
    refs = _refs(two_class_env[1])
    assert ("Dog", "Animal", "inherit") in refs


def test_inherit_implements(interface_env):
    index_run(interface_env[1], repo_path=interface_env[0])
    refs = _refs(interface_env[1])
    assert ("Worker", "Runnable", "inherit") in refs
    assert ("Worker", "Closeable", "inherit") in refs


def test_import_reference(two_class_env):
    index_run(two_class_env[1], repo_path=two_class_env[0])
    refs = _refs(two_class_env[1])
    # Dog.java imports com.example.Animal — src is first sym in Dog.java (Dog class)
    assert any(dst == "Animal" and kind == "import" for _, dst, kind in refs)


def test_no_self_references(two_class_env):
    index_run(two_class_env[1], repo_path=two_class_env[0])
    refs = _refs(two_class_env[1])
    assert all(src != dst for src, dst, _ in refs)


def test_idempotent(two_class_env):
    index_run(two_class_env[1], repo_path=two_class_env[0])
    refs_first = _refs(two_class_env[1])
    index_run(two_class_env[1], repo_path=two_class_env[0])
    refs_second = _refs(two_class_env[1])
    assert refs_first == refs_second
