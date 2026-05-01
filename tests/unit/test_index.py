import pytest

from combfind.db import create_schema, get_connection
from combfind.pipeline.index import run as index_run
from combfind.pipeline.parse import run as parse_run

ANIMALS = '''\
class Animal:
    """Base animal."""
    def speak(self):
        pass

class Dog(Animal):
    """A dog."""
    def speak(self):
        return "woof"

class Cat(Animal):
    """A cat."""
    def speak(self):
        return "meow"

class Labrador(Dog):
    """A specific dog breed."""
    pass
'''

NO_BASES = '''\
class Standalone:
    pass

class AlsoStandalone:
    pass
'''


@pytest.fixture
def env(tmp_path):
    src = tmp_path / "zoo"
    src.mkdir()
    (src / "animals.py").write_text(ANIMALS)
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()
    parse_run(db_path, repo_path=str(tmp_path))
    return str(tmp_path), db_path


def _refs(db_path):
    conn = get_connection(db_path)
    rows = conn.execute(
        'SELECT s1.name src, s2.name dst, r.kind '
        'FROM "references" r '
        'JOIN symbols s1 ON s1.id = r.src_symbol_id '
        'JOIN symbols s2 ON s2.id = r.dst_symbol_id'
    ).fetchall()
    conn.close()
    return {(r["src"], r["dst"], r["kind"]) for r in rows}


def test_direct_inherit(env):
    index_run(env[1])
    refs = _refs(env[1])
    assert ("Dog", "Animal", "inherit") in refs
    assert ("Cat", "Animal", "inherit") in refs


def test_transitive_base(env):
    index_run(env[1])
    refs = _refs(env[1])
    assert ("Labrador", "Dog", "inherit") in refs


def test_no_self_references(env):
    index_run(env[1])
    refs = _refs(env[1])
    assert all(src != dst for src, dst, _ in refs)


def test_no_refs_without_bases(tmp_path):
    src = tmp_path / "pkg"
    src.mkdir()
    (src / "mod.py").write_text(NO_BASES)
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()
    parse_run(db_path, repo_path=str(tmp_path))
    index_run(db_path)
    assert _refs(db_path) == set()


def test_idempotent(env):
    index_run(env[1])
    refs_first = _refs(env[1])
    index_run(env[1])
    refs_second = _refs(env[1])
    assert refs_first == refs_second
