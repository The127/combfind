import json

import numpy as np
import pytest

import combfind.pipeline.embed as embed_mod
from combfind.db import create_schema, get_connection
from combfind.pipeline.parse import run as parse_run

SAMPLE = '''\
class Foo:
    """A foo."""
    def bar(self):
        pass

def baz(x):
    """Bazzes x."""
    return x
'''


@pytest.fixture
def env(tmp_path):
    (tmp_path / "mod.py").write_text(SAMPLE)
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)
    conn.close()
    parse_run(db_path, repo_path=str(tmp_path))
    return str(tmp_path), db_path


@pytest.fixture
def mock_model(monkeypatch):
    class FakeModel:
        def __init__(self, name):
            self.name = name

        def encode(self, texts, **kwargs):
            return np.random.rand(len(texts), 64).astype(np.float32)

    monkeypatch.setattr(embed_mod, "SentenceTransformer", FakeModel)
    return FakeModel


def test_embeddings_stored(env, mock_model):
    _, db_path = env
    embed_mod.run(db_path, embed_model="fake-model")

    conn = get_connection(db_path)
    sym_count = conn.execute("SELECT COUNT(*) FROM symbols").fetchone()[0]
    emb_count = conn.execute("SELECT COUNT(*) FROM symbol_embeddings").fetchone()[0]
    conn.close()

    assert emb_count == sym_count > 0


def test_embedding_blob_is_float32(env, mock_model):
    _, db_path = env
    embed_mod.run(db_path, embed_model="fake-model")

    conn = get_connection(db_path)
    blob = conn.execute("SELECT embedding FROM symbol_embeddings LIMIT 1").fetchone()[0]
    conn.close()

    arr = np.frombuffer(blob, dtype=np.float32)
    assert arr.shape == (64,)


def test_build_config_written(env, mock_model):
    _, db_path = env
    embed_mod.run(db_path, embed_model="fake-model")

    conn = get_connection(db_path)
    cfg = {r["key"]: json.loads(r["value"]) for r in conn.execute("SELECT key, value FROM build_config").fetchall()}
    conn.close()

    assert cfg["embed_model"] == "fake-model"
    assert cfg["embed_dim"] == 64


def test_skips_already_embedded(env, mock_model):
    _, db_path = env
    embed_mod.run(db_path, embed_model="fake-model")

    # Second run: model.encode should not be called
    call_count = 0
    original_cls = embed_mod.SentenceTransformer

    class TrackingModel(original_cls):
        def encode(self, texts, **kwargs):
            nonlocal call_count
            call_count += 1
            return super().encode(texts, **kwargs)

    import combfind.pipeline.embed as em2
    em2.SentenceTransformer = TrackingModel
    em2.run(db_path, embed_model="fake-model")
    em2.SentenceTransformer = original_cls

    assert call_count == 0
