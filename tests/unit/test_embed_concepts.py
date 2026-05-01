import json

import numpy as np
import pytest

import combfind.pipeline.embed_concepts as ec_mod
from combfind.db import create_schema, get_connection


@pytest.fixture
def env(tmp_path):
    db_path = str(tmp_path / "test.db")
    conn = get_connection(db_path)
    create_schema(conn)

    conn.execute(
        "INSERT OR REPLACE INTO build_config(key, value) VALUES ('embed_model', ?)",
        (json.dumps("stored-model"),),
    )

    for i, desc in enumerate(["Handles auth", "Manages DB", None]):
        conn.execute(
            "INSERT INTO concepts(description, member_count, centroid) VALUES (?,1,?)",
            (desc, b"\x00" * 8),
        )

    conn.commit()
    conn.close()
    return db_path


@pytest.fixture
def mock_model(monkeypatch):
    class FakeModel:
        def __init__(self, name):
            self.name = name

        def encode(self, texts, **kwargs):
            return np.random.rand(len(texts), 32).astype(np.float32)

    monkeypatch.setattr(ec_mod, "SentenceTransformer", FakeModel)


def test_embeds_described_concepts(env, mock_model):
    ec_mod.run(env)
    conn = get_connection(env)
    count = conn.execute("SELECT COUNT(*) FROM concept_embeddings").fetchone()[0]
    conn.close()
    assert count == 2  # third concept has no description


def test_skips_null_description(env, mock_model):
    ec_mod.run(env)
    conn = get_connection(env)
    # concept with NULL description must not have an embedding
    null_concept_id = conn.execute(
        "SELECT id FROM concepts WHERE description IS NULL"
    ).fetchone()[0]
    row = conn.execute(
        "SELECT 1 FROM concept_embeddings WHERE concept_id = ?", (null_concept_id,)
    ).fetchone()
    conn.close()
    assert row is None


def test_uses_model_from_build_config(env, monkeypatch):
    used = []

    class TrackingModel:
        def __init__(self, name):
            used.append(name)

        def encode(self, texts, **kwargs):
            return np.random.rand(len(texts), 32).astype(np.float32)

    monkeypatch.setattr(ec_mod, "SentenceTransformer", TrackingModel)
    ec_mod.run(env, embed_model="override-model")
    assert used == ["stored-model"]


def test_idempotent(env, mock_model):
    ec_mod.run(env)
    ec_mod.run(env)
    conn = get_connection(env)
    count = conn.execute("SELECT COUNT(*) FROM concept_embeddings").fetchone()[0]
    conn.close()
    assert count == 2
